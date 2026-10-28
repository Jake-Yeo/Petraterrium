from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import Field

from ..llm_gateway import AIProviderError
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
    SearchPlan,
    SourceCandidate,
    SourceKind,
    SourceVerification,
    UserSourceInput,
    apply_confirmed_mapping,
    build_search_plan,
    derive_estimate,
    pipeline_fallback_candidate,
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
        attempt = AutoImportAttempt(
            attempt_id=self.identity(),
            target=target,
            requirement=requirement,
            status="draft",
            user_sources=tuple(user_sources),
            search_plan=build_search_plan(target),
            created_at=now,
            updated_at=now,
        )
        self.repository.save(attempt)
        return attempt

    def rerun(
        self,
        attempt_id: str,
        source_kinds: tuple[SourceKind, ...] = (),
    ) -> AutoImportAttempt:
        previous = self.repository.get(attempt_id)
        repeated = self.create_attempt(previous.target, previous.user_sources)
        if source_kinds:
            selected = [
                step
                for step in repeated.search_plan.steps
                if step.source_kind in source_kinds
            ]
            repeated = repeated.model_copy(
                update={
                    "search_plan": SearchPlan(
                        languages=tuple(
                            dict.fromkeys(step.language for step in selected)
                        ),
                        steps=tuple(
                            step.model_copy(update={"sequence": index})
                            for index, step in enumerate(selected, start=1)
                        ),
                    )
                }
            )
            self.repository.save(repeated)
        return self.research(repeated.attempt_id)

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
        ai_failures: list[str] = []
        seen_candidates = {candidate.candidate_id for candidate in attempt.sources}
        researched_candidates: list[SourceCandidate] = []
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
                researched_candidates.append(candidate)
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
            except AIProviderError as error:
                candidate_ids = ()
                rejection_reasons = (str(error),)
                outcome = "error"
                ai_failures.append(str(error))
            except Exception as error:
                candidate_ids = ()
                rejection_reasons = (str(error),)
                outcome = "error"
                ai_failures.append(str(error))
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
                    searched_at=self.clock(),
                )
            )

        for source in attempt.user_sources:
            sequence += 1
            try:
                candidates = self.provider.inspect_user_source(
                    source, attempt.target, attempt.requirement
                )
                candidate_ids, rejection_reasons, accepted_count = evaluate(candidates)
                outcome = self._outcome(candidates, accepted_count)
            except AIProviderError as error:
                candidates = []
                candidate_ids = ()
                rejection_reasons = (str(error),)
                outcome = "error"
                ai_failures.append(str(error))
            except Exception as error:
                candidates = []
                candidate_ids = ()
                rejection_reasons = (str(error),)
                outcome = "error"
                ai_failures.append(str(error))
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
                    searched_at=self.clock(),
                )
            )

        result_kind: EvidenceKind | None = None
        selected_source_ids: tuple[str, ...] = ()
        proposed_distribution = None
        estimate_trace = None
        mapping_preview = None
        status = "awaiting_mapping_confirmation"
        failure_reason = None
        complete_direct = [
            candidate
            for candidate in direct
            if self._direct_mapping_complete(candidate, attempt.requirement)
        ]
        if complete_direct:
            chosen = complete_direct[0]
            result_kind = "measured"
            selected_source_ids = (chosen.candidate_id,)
            proposed_distribution = chosen.distribution
            mapping_preview = propose_label_mapping(chosen.distribution, attempt.requirement)
            status = "awaiting_mapping_confirmation"
            failure_reason = None
        else:
            synthesis = getattr(self.provider, "synthesize_estimate", None)
            if callable(synthesis):
                sequence += 1
                try:
                    synthesized = synthesis(
                        attempt.target,
                        attempt.requirement,
                        tuple(logs),
                        tuple(researched_candidates),
                    )
                    synthesis_ids, synthesis_reasons, accepted_count = evaluate(
                        [synthesized]
                    )
                    synthesis_outcome = self._outcome([synthesized], accepted_count)
                    if accepted_count == 0:
                        ai_failures.append("Research synthesis did not pass validation")
                except Exception as error:
                    ai_failures.append(str(error))
                    synthesis_ids = ()
                    synthesis_reasons = (str(error),)
                    synthesis_outcome = "error"
                logs.append(
                    ResearchLogEntry(
                        sequence=sequence,
                        origin="automatic",
                        language="en",
                        engine="Configured AI synthesis",
                        query_or_source=(
                            f"Canonical estimate synthesis for "
                            f"{attempt.target.place_label} {attempt.requirement.name}"
                        ),
                        source_kind="expert_commentary",
                        outcome=synthesis_outcome,
                        candidate_ids=synthesis_ids,
                        rejection_reasons=synthesis_reasons,
                        searched_at=self.clock(),
                    )
                )

            def fallback_estimate() -> SourceCandidate:
                nonlocal sequence
                fallback = pipeline_fallback_candidate(
                    attempt.target,
                    attempt.requirement,
                    logs,
                    ai_failures,
                )
                _candidate_ids, _reasons, accepted_count = evaluate([fallback])
                if accepted_count == 0:
                    raise RuntimeError("Pipeline fallback estimate failed validation")
                sequence += 1
                logs.append(
                    ResearchLogEntry(
                        sequence=sequence,
                        origin="automatic",
                        language="en",
                        engine="Petraterrium deterministic estimator",
                        query_or_source=(
                            f"Maximum-uncertainty estimate for "
                            f"{attempt.target.place_label} {attempt.requirement.name}"
                        ),
                        source_kind="expert_commentary",
                        outcome="candidate",
                        candidate_ids=(fallback.candidate_id,),
                        searched_at=self.clock(),
                    )
                )
                return fallback

            estimate_candidates = list(hints)
            if not estimate_candidates:
                estimate_candidates = [fallback_estimate()]
            try:
                proposed_distribution, estimate_trace, excluded = derive_estimate(
                    estimate_candidates, attempt.requirement
                )
            except Exception as error:
                ai_failures.append(str(error))
                fallback = fallback_estimate()
                estimate_candidates = [fallback]
                proposed_distribution, estimate_trace, excluded = derive_estimate(
                    estimate_candidates, attempt.requirement
                )
            result_kind = "estimated"
            selected_source_ids = tuple(
                candidate.candidate_id
                for candidate in estimate_candidates
                if candidate.candidate_id not in excluded
            )
            mapping_preview = propose_label_mapping(proposed_distribution, attempt.requirement)
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

    def ensure_estimated_draft(self, attempt_id: str) -> AutoImportAttempt:
        attempt = self.repository.get(attempt_id)
        if (
            attempt.result_kind in {"measured", "estimated"}
            and attempt.proposed_distribution
            and attempt.mapping_preview
        ):
            return attempt
        if attempt.status == "promoted":
            raise ValueError("A promoted attempt is immutable")
        errors = (attempt.failure_reason,) if attempt.failure_reason else ()
        fallback = pipeline_fallback_candidate(
            attempt.target,
            attempt.requirement,
            attempt.search_log,
            errors,
        )
        verification = verify_candidate(fallback, attempt.target, attempt.requirement)
        if not verification.accepted:
            raise RuntimeError("Pipeline fallback estimate failed validation")
        distribution, trace, _excluded = derive_estimate(
            [fallback], attempt.requirement
        )
        sequence = max((entry.sequence for entry in attempt.search_log), default=0) + 1
        log = ResearchLogEntry(
            sequence=sequence,
            origin="automatic",
            language="en",
            engine="Petraterrium deterministic estimator",
            query_or_source=(
                f"Maximum-uncertainty estimate for "
                f"{attempt.target.place_label} {attempt.requirement.name}"
            ),
            source_kind="expert_commentary",
            outcome="candidate",
            candidate_ids=(fallback.candidate_id,),
            searched_at=self.clock(),
        )
        return self._save(
            attempt,
            status="awaiting_mapping_confirmation",
            result_kind="estimated",
            search_log=(*attempt.search_log, log),
            sources=(*attempt.sources, fallback),
            selected_source_ids=(fallback.candidate_id,),
            verifications=(*attempt.verifications, verification),
            mapping_preview=propose_label_mapping(distribution, attempt.requirement),
            mapping_confirmed=False,
            proposed_distribution=distribution,
            mapped_distribution=None,
            estimate_trace=trace,
            languages_searched=tuple(
                dict.fromkeys((*attempt.languages_searched, "en"))
            ),
            failure_reason=None,
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
        confirmed_targets = {
            row.source_label: row.target_label for row in confirmation.mappings
        }
        confirmed_preview = attempt.mapping_preview.model_copy(
            update={
                "rows": tuple(
                    row.model_copy(
                        update={
                            "proposed_label": confirmed_targets[row.source_label],
                            "confidence": (
                                "exact"
                                if confirmed_targets[row.source_label] == row.source_label
                                else "alias"
                            ),
                            "reason": "Human-confirmed mapping",
                        }
                    )
                    for row in attempt.mapping_preview.rows
                )
            }
        )
        return self._save(
            attempt,
            status="ready",
            mapping_preview=confirmed_preview,
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

    @staticmethod
    def _outcome(candidates, accepted_count):
        if not candidates:
            return "no_result"
        return "candidate" if accepted_count else "rejected"

    @staticmethod
    def _direct_mapping_complete(candidate, requirement) -> bool:
        preview = propose_label_mapping(candidate.distribution, requirement)
        if any(row.confidence == "unknown" for row in preview.rows):
            return False
        if requirement.feature_id != "specialization":
            return True
        mapped = {row.proposed_label for row in preview.rows}
        return set(requirement.canonical_values) <= mapped

    def _save(self, attempt: AutoImportAttempt, **changes) -> AutoImportAttempt:
        updated = attempt.model_copy(update={**changes, "updated_at": self.clock()})
        self.repository.save(updated)
        return updated

