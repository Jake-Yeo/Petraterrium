import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from .contracts import (
    DailySnapshot,
    Metrics,
    RunComplete,
    RunConfig,
    RunDetail,
    RunError,
    RunFailed,
    RunStatus,
    RunSummary,
    Totals,
)


@dataclass(frozen=True)
class RecordedEvent:
    sequence: int
    kind: Literal["snapshot", "run-complete", "run-failed"]
    data: DailySnapshot | RunComplete | RunFailed

    def as_sse(self) -> str:
        return f"id: {self.sequence}\nevent: {self.kind}\ndata: {self.data.model_dump_json()}\n\n"


@dataclass
class RunRecord:
    run_id: str
    config: RunConfig
    config_hash: str
    status: RunStatus = "queued"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    snapshots: list[DailySnapshot] = field(default_factory=list)
    events: list[RecordedEvent] = field(default_factory=list)
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
            metrics=self.metrics,
            error=self.error,
        )

    def detail(self) -> RunDetail:
        return RunDetail(**self.summary().model_dump(), snapshots=list(self.snapshots))

    async def append(self, snapshot: DailySnapshot) -> None:
        async with self.changed:
            self.snapshots.append(snapshot)
            self.events.append(RecordedEvent(len(self.events) + 1, "snapshot", snapshot))
            self.changed.notify_all()

    async def complete(self) -> None:
        totals = {key: 0 for key in ("susceptible", "exposed", "infected", "recovered")}
        for place in self.snapshots[-1].places:
            for key in totals:
                totals[key] += getattr(place, key)
        infections = [sum(p.infected for p in s.places) for s in self.snapshots]
        peak_index = max(range(len(infections)), key=infections.__getitem__)
        self.metrics = Metrics(
            totals=Totals(population=sum(totals.values()), **totals),
            peak_day=self.snapshots[peak_index].day,
            peak_infected=infections[peak_index],
            days_recorded=len(self.snapshots),
        )
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
    # TODO(persistence): durable run storage is outside this scaffold.
    def __init__(self) -> None:
        self.records: dict[str, RunRecord] = {}

    def get(self, run_id: str) -> RunRecord | None:
        return self.records.get(run_id)
