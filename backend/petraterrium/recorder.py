import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from .contracts import (
    BacktestComparison,
    DailySnapshot,
    EnsembleUpdate,
    MetricPeak,
    Metrics,
    MissingFallback,
    RunComplete,
    RunConfig,
    RunDetail,
    RunError,
    RunFailed,
    RunStatus,
    RunSummary,
    StoryRecord,
    Totals,
)
from .dsl import OutputSpec
from .population import PopulationTable


@dataclass(frozen=True)
class RecordedEvent:
    sequence: int
    kind: Literal["snapshot", "ensemble_update", "run-complete", "run-failed"]
    data: DailySnapshot | EnsembleUpdate | RunComplete | RunFailed

    def as_sse(self) -> str:
        return f"id: {self.sequence}\nevent: {self.kind}\ndata: {self.data.model_dump_json()}\n\n"


@dataclass
class RunRecord:
    run_id: str
    config: RunConfig
    config_hash: str
    outputs: OutputSpec = field(default_factory=OutputSpec)
    evidence_table_version: str = "FAKE-evidence-v1"
    population_version: str = "FAKE-population-v1"
    missing_fallbacks: list[MissingFallback] = field(default_factory=list)
    status: RunStatus = "queued"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    snapshots: list[DailySnapshot] = field(default_factory=list)
    ensemble_updates: list[EnsembleUpdate] = field(default_factory=list)
    stories: list[StoryRecord] = field(default_factory=list)
    backtests: list[BacktestComparison] = field(default_factory=list)
    events: list[RecordedEvent] = field(default_factory=list)
    population: PopulationTable | None = None
    metrics: Metrics | None = None
    error: RunError | None = None
    changed: asyncio.Condition = field(default_factory=asyncio.Condition)

    def summary(self) -> RunSummary:
        return RunSummary(
            run_id=self.run_id,
            config_hash=self.config_hash,
            config=self.config,
            status=self.status,
            created_at=self.created_at,
            last_sequence=len(self.events),
            outputs=self.outputs,
            evidence_table_version=self.evidence_table_version,
            population_version=self.population_version,
            missing_fallbacks=list(self.missing_fallbacks),
            metrics=self.metrics,
            error=self.error,
        )

    def detail(self) -> RunDetail:
        return RunDetail(
            **self.summary().model_dump(),
            snapshots=list(self.snapshots),
            ensemble_updates=list(self.ensemble_updates),
            stories=list(self.stories),
            backtests=list(self.backtests),
        )

    async def append(self, snapshot: DailySnapshot) -> None:
        async with self.changed:
            self.snapshots.append(snapshot)
            self.events.append(RecordedEvent(len(self.events) + 1, "snapshot", snapshot))
            self.changed.notify_all()

    async def append_ensemble(self, update: EnsembleUpdate) -> None:
        async with self.changed:
            self.ensemble_updates.append(update)
            self.events.append(RecordedEvent(len(self.events) + 1, "ensemble_update", update))
            self.changed.notify_all()

    def calculate_metrics(self) -> Metrics:
        final = self.snapshots[-1]
        legacy = {key: 0 for key in ("susceptible", "exposed", "infected", "recovered")}
        state_totals: dict[str, dict[str, int]] = {}
        for place in final.places:
            for key in legacy:
                legacy[key] += getattr(place, key)
            for state_id, values in place.states.items():
                aggregate = state_totals.setdefault(state_id, {})
                for value, count in values.items():
                    aggregate[value] = aggregate.get(value, 0) + count
        infections = [sum(place.infected for place in item.places) for item in self.snapshots]
        peak_index = max(range(len(infections)), key=infections.__getitem__)
        metric_names = sorted(
            {
                metric
                for snapshot in self.snapshots
                for place in snapshot.places
                for metric in place.metrics
            }
        )
        metric_peaks = {}
        for metric in metric_names:
            values = [
                sum(place.metrics.get(metric, 0) for place in snapshot.places)
                for snapshot in self.snapshots
            ]
            index = max(range(len(values)), key=values.__getitem__)
            metric_peaks[metric] = MetricPeak(day=self.snapshots[index].day, value=values[index])
        population = 0
        if final.places:
            first_state = next(iter(final.places[0].states), None)
            if first_state:
                population = sum(sum(place.states[first_state].values()) for place in final.places)
            else:
                population = sum(legacy.values())
        return Metrics(
            totals=Totals(population=population, **legacy),
            peak_day=self.snapshots[peak_index].day,
            peak_infected=infections[peak_index],
            days_recorded=len(self.snapshots),
            state_totals=state_totals,
            metric_peaks=metric_peaks,
            stories_generated=len(self.stories),
        )

    async def complete(self) -> None:
        self.metrics = self.calculate_metrics()
        async with self.changed:
            self.status = "done"
            result = RunComplete(run_id=self.run_id, metrics=self.metrics)
            self.events.append(RecordedEvent(len(self.events) + 1, "run-complete", result))
            self.changed.notify_all()

    async def fail(self, error: RunError) -> None:
        async with self.changed:
            self.status = "failed"
            self.error = error
            result = RunFailed(run_id=self.run_id, error=error)
            self.events.append(RecordedEvent(len(self.events) + 1, "run-failed", result))
            self.changed.notify_all()

    async def follow(self, after: int) -> AsyncIterator[RecordedEvent | None]:
        cursor = after
        while True:
            async with self.changed:
                if cursor == len(self.events) and self.status not in ("done", "failed"):
                    try:
                        await asyncio.wait_for(self.changed.wait(), timeout=10)
                    except TimeoutError:
                        pass
                pending = list(self.events[cursor:])
                terminal = self.status in ("done", "failed")
            for event in pending:
                yield event
                cursor = event.sequence
            if terminal:
                return
            if not pending:
                yield None


class RunStore:
    def __init__(self) -> None:
        self.records: dict[str, RunRecord] = {}

    def get(self, run_id: str) -> RunRecord | None:
        return self.records.get(run_id)
