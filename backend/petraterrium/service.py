import asyncio
import logging

from . import engine
from .contracts import EnsembleUpdate, MissingFallback, RunConfig, RunError, StoryRecord
from .dsl import DSLConfig, validate_dsl
from .events import Event, detect_events, generate_story
from .population import generate_population
from .recorder import RunRecord, RunStore
from .runtime import resolve_runtime
from .versions import ENGINE_VERSION, config_hash

logger = logging.getLogger(__name__)


def evidence_fallbacks(dsl: DSLConfig) -> list[MissingFallback]:
    candidates = []
    candidates.extend((f"parameter.{item.id}", item.provenance) for item in dsl.parameters)
    candidates.extend((f"state.{item.id}", item.initial.provenance) for item in dsl.states)
    candidates.extend(
        (f"default.{item.id}", item.distribution.provenance) for item in dsl.default_states
    )
    candidates.extend((f"behaviour.{item.id}", item.provenance) for item in dsl.behaviour_bundles)
    candidates.extend((f"leader_action.{item.id}", item.evidence) for item in dsl.leader_actions)
    results = []
    seen = set()
    for field_name, evidence in candidates:
        if evidence.status == "present" or field_name in seen:
            continue
        seen.add(field_name)
        results.append(
            MissingFallback(
                field=field_name,
                status=evidence.status,
                fallback=evidence.source,
                impact=(
                    f"Uncertainty {evidence.uncertainty:.2f}; treat outputs that depend on "
                    f"{field_name} as conditional."
                ),
            )
        )
    return results


def snapshot_metrics(snapshot) -> dict[str, dict[str, float]]:
    return {place.country: dict(place.metrics) for place in snapshot.places}


def final_status_story(record: RunRecord) -> StoryRecord | None:
    if not record.snapshots or not record.outputs.stories:
        return None
    snapshot = record.snapshots[-1]
    place = snapshot.places[0]
    if not place.metrics:
        return None
    metric, value = max(place.metrics.items(), key=lambda item: (item[1], item[0]))
    event = Event(
        event_id=f"{record.run_id[:12]}-final",
        definition_id="run-status",
        place=place.country,
        day=snapshot.day,
        metric=metric,
        previous_value=float(value),
        value=float(value),
        change=0,
        severity=0,
        cause="recorded-final-snapshot",
    )
    return StoryRecord(**generate_story(event, snapshot_metrics(snapshot)).model_dump())


def single_sample_update(record: RunRecord) -> EnsembleUpdate:
    final = record.snapshots[-1]
    totals = {}
    for place in final.places:
        for metric, value in place.metrics.items():
            totals[metric] = totals.get(metric, 0.0) + value
    return EnsembleUpdate(
        run_id=record.run_id,
        completed=1,
        total=1,
        seeds=[record.config.seed],
        quantiles={
            metric: {"p10": value, "p50": value, "p90": value}
            for metric, value in sorted(totals.items())
        },
        evidence_table_version=record.evidence_table_version,
    )


class RunService:
    def __init__(self, store: RunStore) -> None:
        self.store = store

    def create(self, config: RunConfig) -> tuple[RunRecord, bool]:
        runtime = resolve_runtime(config)
        validation = validate_dsl(runtime.dsl)
        if not validation.valid:
            messages = "; ".join(validation.error_messages)
            raise ValueError(f"Invalid DSL: {messages}")
        identity = config_hash(
            config,
            evidence_version=config.evidence_table_version,
            resolved_population_version=runtime.population.version,
        )
        existing = self.store.get(identity)
        if existing is not None:
            return existing, True
        record = RunRecord(
            run_id=identity,
            config=config,
            config_hash=identity,
            outputs=runtime.outputs,
            evidence_table_version=config.evidence_table_version,
            population_version=runtime.population.version,
            missing_fallbacks=evidence_fallbacks(runtime.dsl),
        )
        self.store.records[identity] = record
        return record, False

    async def execute(self, record: RunRecord) -> None:
        if self.store.get(record.run_id) is not record:
            return
        record.status = "running"
        try:
            runtime = resolve_runtime(record.config)
            record.population = generate_population(runtime.dsl, None, record.config.seed)
            previous = None
            for snapshot in engine.simulate(record.config, record.run_id, ENGINE_VERSION):
                if self.store.get(record.run_id) is not record:
                    return
                await record.append(snapshot)
                current = snapshot_metrics(snapshot)
                if previous is not None and record.outputs.stories:
                    detected = detect_events(runtime.dsl, current, previous, snapshot.day)
                    record.stories.extend(
                        StoryRecord(**generate_story(event, current).model_dump())
                        for event in detected
                    )
                previous = current
                await asyncio.sleep(0)
            if self.store.get(record.run_id) is not record:
                return
            if not record.stories:
                story = final_status_story(record)
                if story:
                    record.stories.append(story)
            if record.outputs.ensemble_updates:
                await record.append_ensemble(single_sample_update(record))
            await record.complete()
        except asyncio.CancelledError:
            await record.fail(RunError(code="interrupted", message="Run worker was interrupted"))
            raise
        except Exception as exc:
            logger.exception("Simulation failed: %s", record.run_id)
            await record.fail(
                RunError(code="engine_failure", message=str(exc) or type(exc).__name__)
            )

    async def delete(self, record: RunRecord) -> None:
        if record.status in ("queued", "running"):
            await record.fail(RunError(code="run_deleted", message="Run was deleted"))
        self.store.records.pop(record.run_id, None)
