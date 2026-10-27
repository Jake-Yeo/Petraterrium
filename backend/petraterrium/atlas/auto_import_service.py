from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import Field

from .auto_import_requirements import canonical_requirement
from .auto_import_research import (
    AutoImportAttempt,
    ConfirmedLabelMapping,
    EstimateTrace,
    EvidenceKind,
    MappingConfirmation,
    MappingPreview,
    PlaceFeatureTarget,
    RejectedSource,
    ResearchLogEntry,
    ResearchModel,
    ResearchProvider,
    SourceCandidate,
    SourceVerification,
    UserSourceInput,
    apply_confirmed_mapping,
    build_search_plan,
    derive_estimate,
    propose_label_mapping,
    verify_candidate,
)


class AttemptRepository(Protocol):
    def save(self, attempt: AutoImportAttempt) -> None: ...

    def get(self, attempt_id: str) -> AutoImportAttempt: ...

    def list(self) -> list[AutoImportAttempt]: ...


class PromotionCommand(ResearchModel):
    confirmed: bool


class PromotionPayload(ResearchModel):
    attempt_id: str
    target: PlaceFeatureTarget
    evidence_status: EvidenceKind
    distribution: dict[str, float]
    unit: str
    coverage_percent: float = Field(ge=0, le=100)
    sources: tuple[SourceCandidate, ...]
    mapping: MappingPreview
    verifications: tuple[SourceVerification, ...]
    estimate_trace: EstimateTrace | None = None
    search_log: tuple[ResearchLogEntry, ...]
    languages_searched: tuple[str, ...]
    predictive_evidence_eligible: bool


class PromotionWriter(Protocol):
    def promote(self, payload: PromotionPayload) -> str: ...


class MemoryAttemptRepository:
    def __init__(self):
        self.attempts: dict[str, AutoImportAttempt] = {}

    def save(self, attempt: AutoImportAttempt) -> None:
        self.attempts[attempt.attempt_id] = attempt

    def get(self, attempt_id: str) -> AutoImportAttempt:
        try:
            return self.attempts[attempt_id]
        except KeyError as error:
            raise KeyError(f"Auto-import attempt {attempt_id} does not exist") from error

    def list(self) -> list[AutoImportAttempt]:
        return sorted(self.attempts.values(), key=lambda attempt: attempt.created_at)


class JsonAttemptRepository:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, attempt_id: str) -> Path:
        if not attempt_id or any(character not in "0123456789abcdef" for character in attempt_id):
            raise ValueError("Attempt id must be a hexadecimal identifier")
        return self.root / f"{attempt_id}.json"

    def save(self, attempt: AutoImportAttempt) -> None:
        destination = self._path(attempt.attempt_id)
        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(attempt.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(destination)

    def get(self, attempt_id: str) -> AutoImportAttempt:
        path = self._path(attempt_id)
        if not path.exists():
            raise KeyError(f"Auto-import attempt {attempt_id} does not exist")
        return AutoImportAttempt.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self) -> list[AutoImportAttempt]:
        attempts = [
            AutoImportAttempt.model_validate_json(path.read_text(encoding="utf-8"))
            for path in self.root.glob("*.json")
        ]
        return sorted(attempts, key=lambda attempt: attempt.created_at)


class AutoImportResearchService:
    def __init__(
        self,
        repository: AttemptRepository,
        provider: ResearchProvider,
        promotion_writer: PromotionWriter | None = None,
        clock: Callable[[], datetime] | None = None,
        identity: Callable[[], str] | None = None,
    ):
        self.repository = repository
        self.provider = provider
        self.promotion_writer = promotion_writer
        self.clock = clock or (lambda: datetime.now(UTC))
        self.identity = identity or (lambda: uuid4().hex)

    def create_attempt(
        self,
        target: PlaceFeatureTarget,
        user_sources: list[UserSourceInput] | tuple[UserSourceInput, ...] = (),
    ) -> AutoImportAttempt:
        requirement = canonical_requirement(target.feature_id)
        now = self.clock()
        previous = self._latest_attempt(target)
        attempt = AutoImportAttempt(
            attempt_id=self.identity(),
            target=target,
            requirement=requirement,
            status="draft",
            user_sources=tuple(user_sources),
            search_plan=build_search_plan(target),
            search_log=previous.search_log if previous else (),
            languages_searched=previous.languages_searched if previous else (),
            created_at=now,
            updated_at=now,
        )
        self.repository.save(attempt)
        return attempt

    def get_attempt(self, attempt_id: str) -> AutoImportAttempt:
        return self.repository.get(attempt_id)

    def research(self, attempt_id: str) -> AutoImportAttempt:
        attempt = self.repository.get(attempt_id)
        if attempt.status == "promoted":
            raise ValueError("A promoted attempt is immutable")
        if attempt.status in {"awaiting_mapping_confirmation", "ready"}:
            raise ValueError("Review or promote the current result before starting another attempt")
        attempt = self._save(attempt, status="researching", failure_reason=None)
        logs = list(attempt.search_log)
        accepted: list[SourceCandidate] = []
        rejected = list(attempt.rejected_sources)
        verifications = list(attempt.verifications)
        languages = list(attempt.languages_searched)
        direct: list[SourceCandidate] = []
        hints: list[SourceCandidate] = []
        seen_candidates = {candidate.candidate_id for candidate in attempt.sources}
        completed_automatic = {
            (entry.language, entry.engine, entry.query_or_source, entry.source_kind)
            for entry in logs
            if entry.origin == "automatic" and entry.outcome != "error"
        }
        sequence = max((entry.sequence for entry in logs), default=0)

        def evaluate(candidates: list[SourceCandidate]):
            candidate_ids = []
            rejection_reasons = []
            accepted_count = 0
            for candidate in candidates:
                if candidate.candidate_id in seen_candidates:
                    continue
                seen_candidates.add(candidate.candidate_id)
                candidate_ids.append(candidate.candidate_id)
                verification = verify_candidate(candidate, attempt.target, attempt.requirement)
                verifications.append(verification)
                if verification.accepted:
                    accepted_count += 1
                    accepted.append(candidate)
                    if verification.direct_measurement:
                        direct.append(candidate)
                    else:
                        hints.append(candidate)
                else:
                    rejected.append(RejectedSource(candidate=candidate, verification=verification))
                    rejection_reasons.extend(
                        f"{candidate.title}: {reason}" for reason in verification.reasons
                    )
            return tuple(candidate_ids), tuple(rejection_reasons), accepted_count

        for source in attempt.user_sources:
            sequence += 1
            try:
                candidates = self.provider.inspect_user_source(
                    source, attempt.target, attempt.requirement
                )
                candidate_ids, rejection_reasons, accepted_count = evaluate(candidates)
                outcome = self._outcome(candidates, accepted_count)
            except Exception as error:
                candidates = []
                candidate_ids = ()
                rejection_reasons = (str(error),)
                outcome = "error"
            source_kind = {
                "url": "user_url",
                "upload": "user_upload",
                "text": "user_text",
            }[source.kind]
            source_languages = [candidate.language for candidate in candidates]
            if not source_languages and source.language:
                source_languages.append(source.language)
            for language in source_languages:
                if language not in languages:
                    languages.append(language)
            logs.append(
                ResearchLogEntry(
                    sequence=sequence,
                    origin="user",
                    language=source.language
                    or (source_languages[0] if source_languages else "unknown"),
                    engine="User supplied",
                    query_or_source=source.locator or source.name,
                    source_kind=source_kind,
                    outcome=outcome,
                    candidate_ids=candidate_ids,
                    rejection_reasons=rejection_reasons,
                )
            )

        if not direct:
            for step in attempt.search_plan.steps:
                key = (step.language, step.engine, step.query, step.source_kind)
                if key in completed_automatic:
                    continue
                sequence += 1
                if step.language not in languages:
                    languages.append(step.language)
                try:
                    candidates = self.provider.search(step, attempt.target, attempt.requirement)
                    candidate_ids, rejection_reasons, accepted_count = evaluate(candidates)
                    outcome = self._outcome(candidates, accepted_count)
                except Exception as error:
                    candidate_ids = ()
                    rejection_reasons = (str(error),)
                    outcome = "error"
                logs.append(
                    ResearchLogEntry(
                        sequence=sequence,
                        origin="automatic",
                        language=step.language,
                        engine=step.engine,
                        query_or_source=step.query,
                        source_kind=step.source_kind,
                        outcome=outcome,
                        candidate_ids=candidate_ids,
                        rejection_reasons=rejection_reasons,
                    )
                )

        result_kind: EvidenceKind | None = None
        selected_source_ids: tuple[str, ...] = ()
        proposed_distribution = None
        estimate_trace = None
        mapping_preview = None
        status = "not_found"
        failure_reason = (
            "No credible source met the feature, place, denominator, date, and unit checks"
        )
        if direct:
            chosen = direct[0]
            result_kind = "measured"
            selected_source_ids = (chosen.candidate_id,)
            proposed_distribution = chosen.distribution
            mapping_preview = propose_label_mapping(chosen.distribution, attempt.requirement)
            status = "awaiting_mapping_confirmation"
            failure_reason = None
        elif hints:
            proposed_distribution, estimate_trace, excluded = derive_estimate(
                hints, attempt.requirement
            )
            result_kind = "estimated"
            selected_source_ids = tuple(
                candidate.candidate_id
                for candidate in hints
                if candidate.candidate_id not in excluded
            )
            mapping_preview = propose_label_mapping(proposed_distribution, attempt.requirement)
            status = "awaiting_mapping_confirmation"
            failure_reason = None
        return self._save(
            attempt,
            status=status,
            result_kind=result_kind,
            search_log=tuple(logs),
            sources=tuple((*attempt.sources, *accepted)),
            rejected_sources=tuple(rejected),
            selected_source_ids=selected_source_ids,
            verifications=tuple(verifications),
            mapping_preview=mapping_preview,
            mapping_confirmed=False,
            proposed_distribution=proposed_distribution,
            mapped_distribution=None,
            estimate_trace=estimate_trace,
            languages_searched=tuple(languages),
            failure_reason=failure_reason,
        )

    def confirm_mapping(
        self, attempt_id: str, confirmation: MappingConfirmation
    ) -> AutoImportAttempt:
        attempt = self.repository.get(attempt_id)
        if attempt.status != "awaiting_mapping_confirmation":
            raise ValueError("Research must produce a mapping preview before confirmation")
        if attempt.mapping_preview is None or attempt.proposed_distribution is None:
            raise ValueError("Attempt has no proposed distribution to map")
        mapped = apply_confirmed_mapping(
            attempt.proposed_distribution,
            attempt.mapping_preview,
            confirmation,
            attempt.requirement,
        )
        return self._save(
            attempt,
            status="ready",
            mapping_confirmed=True,
            mapped_distribution=mapped,
        )

    def confirm_proposed_mapping(self, attempt_id: str) -> AutoImportAttempt:
        attempt = self.repository.get(attempt_id)
        if attempt.mapping_preview is None:
            raise ValueError("Attempt has no mapping preview")
        confirmation = MappingConfirmation(
            confirmed=True,
            mappings=tuple(
                ConfirmedLabelMapping(
                    source_label=row.source_label,
                    target_label=row.proposed_label,
                )
                for row in attempt.mapping_preview.rows
            ),
        )
        return self.confirm_mapping(attempt_id, confirmation)

    def promotion_payload(self, attempt_id: str) -> PromotionPayload:
        attempt = self.repository.get(attempt_id)
        if (
            attempt.status != "ready"
            or not attempt.mapping_confirmed
            or attempt.mapped_distribution is None
            or attempt.mapping_preview is None
            or attempt.result_kind is None
        ):
            raise ValueError("Confirm a verified mapping before promotion")
        selected = set(attempt.selected_source_ids)
        source_populations = [
            source.population
            for source in attempt.sources
            if source.candidate_id in selected and source.population is not None
        ]
        coverage_percent = 100.0
        if attempt.target.population > 0 and source_populations:
            coverage_percent = min(
                100.0,
                max(source_populations) * 100.0 / attempt.target.population,
            )
        return PromotionPayload(
            attempt_id=attempt.attempt_id,
            target=attempt.target,
            evidence_status=attempt.result_kind,
            distribution=attempt.mapped_distribution,
            unit="percent",
            coverage_percent=coverage_percent,
            sources=tuple(source for source in attempt.sources if source.candidate_id in selected),
            mapping=attempt.mapping_preview,
            verifications=tuple(
                result for result in attempt.verifications if result.candidate_id in selected
            ),
            estimate_trace=attempt.estimate_trace,
            search_log=attempt.search_log,
            languages_searched=attempt.languages_searched,
            predictive_evidence_eligible=attempt.result_kind == "measured",
        )

    def promote(self, attempt_id: str, command: PromotionCommand) -> AutoImportAttempt:
        if not command.confirmed:
            raise ValueError("Promotion requires an explicit confirmation")
        if self.promotion_writer is None:
            raise RuntimeError("No auto-import promotion writer is configured")
        existing = self.repository.get(attempt_id)
        if existing.status == "promoted":
            return existing
        payload = self.promotion_payload(attempt_id)
        promotion_id = self.promotion_writer.promote(payload)
        attempt = self.repository.get(attempt_id)
        return self._save(attempt, status="promoted", promotion_id=promotion_id)

    def _latest_attempt(self, target: PlaceFeatureTarget) -> AutoImportAttempt | None:
        matches = [
            attempt
            for attempt in self.repository.list()
            if attempt.target.level == target.level
            and attempt.target.place_id == target.place_id
            and attempt.target.feature_id == target.feature_id
            and attempt.target.scope == target.scope
        ]
        return max(matches, key=lambda attempt: attempt.updated_at) if matches else None

    @staticmethod
    def _outcome(candidates, accepted_count):
        if not candidates:
            return "no_result"
        return "candidate" if accepted_count else "rejected"

    def _save(self, attempt: AutoImportAttempt, **changes) -> AutoImportAttempt:
        updated = attempt.model_copy(update={**changes, "updated_at": self.clock()})
        self.repository.save(updated)
        return updated

