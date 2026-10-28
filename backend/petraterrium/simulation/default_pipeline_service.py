from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from .default_pipeline_contracts import (
    ActivateDefaultPipelineRunRequest,
    DefaultPipelineActivation,
    DefaultPipelineDurationChange,
    DefaultPipelineResearchChange,
    DefaultPipelineRun,
    DefaultPipelineRunDiff,
    DefaultPipelineRunList,
    DefaultPipelineRunSummary,
    DefaultStateRestoreReceipt,
    DurationCandidate,
    DurationChosenResult,
    DurationSearchLogEntry,
    RestoreDefaultPipelineRunRequest,
)
from .default_pipeline_persistence import (
    JsonDefaultPipelineRepository,
    calculate_run_hash,
)
from .registry_store import SimulationRegistryStore

DEFAULT_STATE_SECTIONS = (
    "default_actions",
    "default_sources",
    "agent_states",
    "coefficient_registry",
    "finance_initialization",
    "specialization_pipeline",
    "initial_population",
)
OPTIONAL_DEFAULT_STATE_SECTIONS = ("decision_trees", "aggregate_statistics")


class DurationResearcher(Protocol):
    pipeline_version: str

    def research(self, actions: list[dict] | tuple[dict, ...]): ...


class DefaultStateProvider(Protocol):
    def snapshot_sections(self) -> dict[str, Any]: ...


class DefaultStateRestorer(Protocol):
    def restore_sections(self, sections: dict[str, Any], version: int) -> None: ...


class SimulationRegistryDefaultStateAdapter:
    def __init__(self, store: SimulationRegistryStore):
        self.store = store

    def snapshot_sections(self) -> dict[str, Any]:
        payload = self.store.payload_snapshot()
        missing = [section for section in DEFAULT_STATE_SECTIONS if section not in payload]
        if missing:
            raise ValueError(
                "Simulation registry cannot produce a default snapshot; missing "
                f"{', '.join(missing)}"
            )
        selected = (
            *DEFAULT_STATE_SECTIONS,
            *(section for section in OPTIONAL_DEFAULT_STATE_SECTIONS if section in payload),
        )
        return {section: deepcopy(payload[section]) for section in selected}

    def restore_sections(self, sections: dict[str, Any], _version: int) -> None:
        unexpected = sorted(
            set(sections) - set(DEFAULT_STATE_SECTIONS) - set(OPTIONAL_DEFAULT_STATE_SECTIONS)
        )
        missing = sorted(set(DEFAULT_STATE_SECTIONS) - set(sections))
        if unexpected or missing:
            raise ValueError(
                "Default-state snapshot sections differ from the restore contract: "
                f"missing={missing}, unexpected={unexpected}"
            )
        receipt = self.store.default_dsl_receipt()
        if receipt is None:
            raise ValueError("Install the default DSL before restoring a cached pipeline result")
        self.store.restore_default_dsl_sections(
            deepcopy(sections),
            receipt.model_dump(mode="json"),
        )


class DefaultPipelineRunService:
    def __init__(
        self,
        repository: JsonDefaultPipelineRepository,
        duration_researcher: DurationResearcher,
        state_provider: DefaultStateProvider,
        state_restorer: DefaultStateRestorer,
        clock: Callable[[], datetime] | None = None,
        identity: Callable[[], str] | None = None,
    ):
        self.repository = repository
        self.duration_researcher = duration_researcher
        self.state_provider = state_provider
        self.state_restorer = state_restorer
        self.clock = clock or (lambda: datetime.now(UTC))
        self.identity = identity or (lambda: uuid4().hex)
        self._restore_hooks: list[Callable[[dict[str, Any], int], None]] = []

    def add_restore_hook(
        self,
        hook: Callable[[dict[str, Any], int], None],
    ) -> None:
        self._restore_hooks.append(hook)

    def run_duration_research(self) -> DefaultPipelineRun:
        created_at = self.clock()
        sections = self.state_provider.snapshot_sections()
        actions = sections["default_actions"]
        output = self.duration_researcher.research(actions)
        expected_actions = {action["id"] for action in actions}
        chosen_actions = {result.action_id for result in output.chosen_results}
        if chosen_actions != expected_actions:
            raise ValueError(
                "Duration research results do not cover every default action: "
                f"missing={sorted(expected_actions - chosen_actions)}, "
                f"unexpected={sorted(chosen_actions - expected_actions)}"
            )
        if any(
            result.evidence_kind not in {"measured", "estimated"}
            for result in output.chosen_results
        ):
            raise ValueError("Every duration result must be measured or estimated")
        if any(not result.source_provenance for result in output.chosen_results):
            raise ValueError("Every duration result must retain source provenance")
        snapshot_sections = _apply_duration_results(
            sections,
            output.chosen_results,
            output.candidates,
            output.search_log,
        )
        snapshot = self.repository.store_snapshot(snapshot_sections)
        version, previous_run_id = self.repository.next_version()
        run = DefaultPipelineRun(
            run_id=self.identity(),
            version=version,
            previous_run_id=previous_run_id,
            pipeline_version=self.duration_researcher.pipeline_version,
            created_at=created_at,
            completed_at=self.clock(),
            requests=output.requests,
            search_log=output.search_log,
            candidates=output.candidates,
            chosen_results=output.chosen_results,
            snapshot=snapshot,
            run_hash=f"sha256:{'0' * 64}",
        )
        run = run.model_copy(update={"run_hash": calculate_run_hash(run)})
        self.repository.save(run)
        return run

    def inspect(self, run_id: str) -> DefaultPipelineRun:
        return self.repository.get(run_id)

    def list_runs(self) -> DefaultPipelineRunList:
        active_run_id = self.repository.active_run_id()
        return DefaultPipelineRunList(
            active_run_id=active_run_id,
            runs=tuple(_summary(run, active_run_id) for run in self.repository.list()),
        )

    def active_snapshot(self) -> tuple[DefaultPipelineRun, dict[str, Any]] | None:
        run_id = self.repository.active_run_id()
        if run_id is None:
            return None
        run = self.repository.get(run_id)
        return run, self.repository.read_snapshot(run.snapshot)

    def diff(self, from_run_id: str, to_run_id: str) -> DefaultPipelineRunDiff:
        before = self.repository.get(from_run_id)
        after = self.repository.get(to_run_id)
        before_research = {_research_signature(entry) for entry in before.search_log}
        after_research = {_research_signature(entry) for entry in after.search_log}
        before_results = {result.action_id: result for result in before.chosen_results}
        after_results = {result.action_id: result for result in after.chosen_results}
        changes = tuple(
            _duration_change(action_id, before_results.get(action_id), after_results.get(action_id))
            for action_id in sorted(before_results.keys() | after_results.keys())
            if before_results.get(action_id) != after_results.get(action_id)
        )
        changed_sections = tuple(
            section
            for section in sorted(
                before.snapshot.section_hashes.keys() | after.snapshot.section_hashes.keys()
            )
            if before.snapshot.section_hashes.get(section)
            != after.snapshot.section_hashes.get(section)
        )
        return DefaultPipelineRunDiff(
            from_run_id=from_run_id,
            to_run_id=to_run_id,
            researched_data=DefaultPipelineResearchChange(
                added=tuple(sorted(after_research - before_research)),
                removed=tuple(sorted(before_research - after_research)),
            ),
            chosen_data=changes,
            changed_snapshot_sections=changed_sections,
        )

    def activate(
        self,
        run_id: str,
        request: ActivateDefaultPipelineRunRequest,
    ) -> DefaultPipelineActivation:
        run = self.repository.get(run_id)
        if run.run_hash != request.expected_run_hash:
            raise ValueError("Default pipeline run changed; inspect it again before activation")
        self.repository.activate(run_id)
        return DefaultPipelineActivation(
            run_id=run.run_id,
            version=run.version,
            activated_at=self.clock(),
            run_hash=run.run_hash,
        )

    def restore(
        self,
        request: RestoreDefaultPipelineRunRequest,
    ) -> DefaultStateRestoreReceipt:
        run_id = request.run_id or self.repository.active_run_id()
        if run_id is None:
            raise ValueError("Activate a cached default pipeline run before restoring it")
        run = self.repository.get(run_id)
        if run.run_hash != request.expected_run_hash:
            raise ValueError("Default pipeline run changed; inspect it again before restore")
        return self._restore_run(run)

    def restore_active(self) -> DefaultStateRestoreReceipt | None:
        run_id = self.repository.active_run_id()
        if run_id is None:
            return None
        return self._restore_run(self.repository.get(run_id))

    def _restore_run(self, run: DefaultPipelineRun) -> DefaultStateRestoreReceipt:
        sections = self.repository.read_snapshot(run.snapshot)
        for hook in self._restore_hooks:
            hook(sections, run.version)
        self.state_restorer.restore_sections(sections, run.version)
        receipt = DefaultStateRestoreReceipt(
            run_id=run.run_id,
            version=run.version,
            snapshot_id=run.snapshot.snapshot_id,
            restored_at=self.clock(),
            restored_sections=tuple(sorted(sections)),
            section_hashes=run.snapshot.section_hashes,
            run_hash=run.run_hash,
        )
        return receipt


def _apply_duration_results(
    sections: dict[str, Any],
    results: tuple[DurationChosenResult, ...],
    candidates: tuple[DurationCandidate, ...],
    search_log: tuple[DurationSearchLogEntry, ...],
) -> dict[str, Any]:
    updated = deepcopy(sections)
    result_by_action = {result.action_id: result for result in results}
    candidates_by_action: dict[str, list[DurationCandidate]] = {}
    for candidate in candidates:
        candidates_by_action.setdefault(candidate.action_id, []).append(candidate)
    candidate_places: dict[str, tuple[str, str]] = {}
    for entry in search_log:
        for candidate_id in entry.candidate_ids:
            target = (entry.place_id, entry.place_label)
            existing = candidate_places.setdefault(candidate_id, target)
            if existing != target:
                raise ValueError(
                    f"Duration candidate {candidate_id} is attached to multiple places"
                )
    source_by_id = {
        source.source_id: source
        for item in (*results, *candidates)
        for source in item.source_provenance
    }
    for action in updated["default_actions"]:
        result = result_by_action[action["id"]]
        action["duration"] = {
            "duration_min_hours": result.duration.minimum_hours,
            "duration_median_hours": result.duration.median_hours,
            "duration_max_hours": result.duration.maximum_hours,
            "shape": result.duration.shape,
            "shape_parameters": {},
            "evidence": {
                "status": "default_estimated",
                "explicit_default_reason": result.reasoning,
                "uncertainty_low": 0.0,
                "uncertainty_high": 1.0,
                "source_ids": [source.source_id for source in result.source_provenance],
            },
        }
        action["duration_resolutions"] = [
            {
                "id": candidate.candidate_id,
                "place_level": _duration_place_level(
                    candidate_places.get(candidate.candidate_id, ("", ""))[0]
                ),
                "place_ids": list(
                    dict.fromkeys(
                        value
                        for value in candidate_places.get(
                            candidate.candidate_id,
                            (
                                candidate.source_provenance[0].place_id,
                                candidate.source_provenance[0].place_label,
                            ),
                        )
                        if value
                    )
                ),
                "agent_type_ids": [],
                "duration": {
                    "duration_min_hours": candidate.duration.minimum_hours,
                    "duration_median_hours": candidate.duration.median_hours,
                    "duration_max_hours": candidate.duration.maximum_hours,
                    "shape": candidate.duration.shape,
                    "shape_parameters": {},
                    "evidence": {
                        "status": (
                            "measured"
                            if candidate.evidence_kind == "measured"
                            else "default_estimated"
                        ),
                        "explicit_default_reason": candidate.reasoning,
                        "uncertainty_low": 0.0,
                        "uncertainty_high": 1.0,
                        "source_ids": [
                            source.source_id for source in candidate.source_provenance
                        ],
                    },
                },
            }
            for candidate in sorted(
                candidates_by_action.get(action["id"], []),
                key=lambda item: item.candidate_id,
            )
            if candidate.source_provenance
        ]
    existing_sources = {source["id"]: source for source in updated.get("default_sources", [])}
    for source_id, source in source_by_id.items():
        existing_sources[source_id] = {
            "id": source.source_id,
            "original_title": source.title,
            "english_title": source.title,
            "publisher": source.publisher,
            "publication_date": source.source_date,
            "population": source.population,
            "place": source.place_label,
            "language": source.language,
            "discovery_source": source.engine,
            "url": source.url,
            "supports": sorted(
                result.action_id
                for result in (*results, *candidates)
                if any(item.source_id == source_id for item in result.source_provenance)
            ),
        }
    updated["default_sources"] = [existing_sources[key] for key in sorted(existing_sources)]
    return updated


def _duration_place_level(place_id: str) -> str:
    normalized = place_id.strip()
    if normalized.casefold() == "global":
        return "global"
    if len(normalized) == 2 and normalized.isalpha():
        return "country"
    return "region"


def _summary(run: DefaultPipelineRun, active_run_id: str | None) -> DefaultPipelineRunSummary:
    measured = sum(result.evidence_kind == "measured" for result in run.chosen_results)
    estimated = sum(result.evidence_kind == "estimated" for result in run.chosen_results)
    return DefaultPipelineRunSummary(
        run_id=run.run_id,
        version=run.version,
        previous_run_id=run.previous_run_id,
        created_at=run.created_at,
        completed_at=run.completed_at,
        action_count=len(run.chosen_results),
        measured_count=measured,
        estimated_count=estimated,
        active=run.run_id == active_run_id,
        run_hash=run.run_hash,
        snapshot_id=run.snapshot.snapshot_id,
    )


def _research_signature(entry) -> str:
    return " | ".join(
        (
            entry.place_id,
            entry.language,
            entry.engine,
            entry.source_kind,
            entry.query_or_source,
            entry.outcome,
            entry.detail,
        )
    )


def _source_ids(result: DurationChosenResult | None) -> tuple[str, ...]:
    if result is None:
        return ()
    return tuple(source.source_id for source in result.source_provenance)


def _duration_change(
    action_id: str,
    before: DurationChosenResult | None,
    after: DurationChosenResult | None,
) -> DefaultPipelineDurationChange:
    reason = (
        f"{after.reasoning} Assumptions: {' '.join(after.assumptions)}"
        if after is not None
        else "The action result was removed"
    )
    return DefaultPipelineDurationChange(
        action_id=action_id,
        before=before.duration if before else None,
        after=after.duration if after else None,
        before_evidence_kind=before.evidence_kind if before else None,
        after_evidence_kind=after.evidence_kind if after else None,
        before_source_ids=_source_ids(before),
        after_source_ids=_source_ids(after),
        reason=reason,
    )
