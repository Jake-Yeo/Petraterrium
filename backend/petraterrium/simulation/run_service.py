from __future__ import annotations

import hashlib
import json
import threading
import uuid
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, timedelta
from math import isclose
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .interactions import (
    AppliedRelationshipDelta,
    AppliedStateDelta,
    InteractionTreeTrace,
)
from .locations import AgentLocationColumns as LocationAgentColumns
from .locations import (
    LocationHistoryRecord,
    LocationLivePlaceState,
    LocationPlace,
    LocationRuntimeState,
)
from .run_persistence import SimulationRunRecorder, StoredSimulationRun

RunStatus = Literal["queued", "running", "cancelling", "cancelled", "completed", "failed"]
MAX_RUST_CHUNK_TICKS = 1024
CHUNK_EVENT_FIELDS = (
    "transition_counts",
    "transition_outcomes",
    "events",
    "routine_actions",
    "routine_unavailable",
    "location_transitions",
    "interactions",
    "blocked_interactions",
    "synchronization",
)


class SimulationRunModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class SimulationPlaceScope(SimulationRunModel):
    level: Literal["global", "region", "country", "city"]
    identifier: str | None = None

    @model_validator(mode="after")
    def identifier_matches_level(self):
        if self.level == "global" and self.identifier is not None:
            raise ValueError("Global scope cannot have a place identifier")
        if self.level != "global" and not self.identifier:
            raise ValueError(f"{self.level.title()} scope requires a place identifier")
        return self


class SimulationRunConfig(SimulationRunModel):
    population_size: int = Field(ge=1, le=10_000_000)
    seed: int = Field(ge=0, le=18_446_744_073_709_551_615)
    days: int = Field(ge=1, le=365_000)
    tick_interval_hours: float = Field(gt=0, le=24, allow_inf_nan=False)
    start_date: date
    place_scope: SimulationPlaceScope
    agent_type_mix: dict[str, float] = Field(default_factory=dict)

    @field_validator("start_date", mode="before")
    @classmethod
    def parse_start_date(cls, value):
        if isinstance(value, str):
            return date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def exact_tick_count(self):
        ticks_per_day = 24 / self.tick_interval_hours
        if not isclose(ticks_per_day, round(ticks_per_day), rel_tol=0, abs_tol=1e-9):
            raise ValueError("Tick interval must divide a 24-hour day exactly")
        if self.days * round(ticks_per_day) > 1_000_000:
            raise ValueError("A run cannot exceed 1,000,000 ticks")
        if self.agent_type_mix:
            if any(not name.strip() for name in self.agent_type_mix):
                raise ValueError("Agent type mix names cannot be empty")
            if any(value <= 0 or value > 1 for value in self.agent_type_mix.values()):
                raise ValueError("Agent type mix shares must be greater than zero and at most one")
            if not isclose(sum(self.agent_type_mix.values()), 1, rel_tol=0, abs_tol=1e-9):
                raise ValueError("Agent type mix shares must sum to one")
        return self

    @property
    def total_ticks(self) -> int:
        return self.days * self.ticks_per_day

    @property
    def ticks_per_day(self) -> int:
        return round(24 / self.tick_interval_hours)


class PreparedRustRun(SimulationRunModel):
    rust_request: dict[str, Any]
    agent_ids: list[str] = Field(min_length=1)
    agent_names: list[str] = Field(default_factory=list)
    data_version: str = Field(min_length=1)
    program_version: str = Field(min_length=1)
    location_places: list[LocationPlace] = Field(default_factory=list)
    initial_location_ids: list[str] = Field(default_factory=list)
    runtime_place_location_ids: list[str] = Field(default_factory=list)
    initial_agent_profiles: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def complete_agent_identity(self):
        if len(set(self.agent_ids)) != len(self.agent_ids):
            raise ValueError("Prepared Rust agent IDs must be unique")
        if self.agent_names and len(self.agent_names) != len(self.agent_ids):
            raise ValueError("Prepared Rust agent names must match the agent ID count")
        if self.initial_agent_profiles and len(self.initial_agent_profiles) != len(self.agent_ids):
            raise ValueError("Prepared initial agent profiles must match the agent ID count")
        location_fields = (
            bool(self.location_places),
            bool(self.initial_location_ids),
            bool(self.runtime_place_location_ids),
        )
        if any(location_fields) and not all(location_fields):
            raise ValueError("Prepared hierarchical location data must be complete")
        if self.initial_location_ids and len(self.initial_location_ids) != len(self.agent_ids):
            raise ValueError("Prepared location identities must match the agent count")
        location_ids = {place.id for place in self.location_places}
        if any(place_id not in location_ids for place_id in self.initial_location_ids):
            raise ValueError("Prepared agent locations must exist in the location registry")
        if any(place_id not in location_ids for place_id in self.runtime_place_location_ids):
            raise ValueError("Prepared runtime places must map to the location registry")
        runtime_places = self.rust_request.get("places")
        if self.runtime_place_location_ids and (
            not isinstance(runtime_places, list)
            or len(self.runtime_place_location_ids) != len(runtime_places)
        ):
            raise ValueError("Prepared runtime location mappings must match Rust places")
        return self

    def display_names(self) -> list[str]:
        return self.agent_names or self.agent_ids


class RustRunClient(Protocol):
    def run_agents(self, request: Mapping[str, Any]) -> dict[str, Any]: ...


PreparedRunFactory = Callable[[SimulationRunConfig], PreparedRustRun]
InteractionRecorder = Callable[[str, Mapping[str, Any], Mapping[str, str]], Any]
LocationRecorder = Callable[
    [
        str,
        int,
        Sequence[LocationPlace],
        LocationRuntimeState,
        Mapping[str, str],
    ],
    Any,
]


class SnapshotSummary(SimulationRunModel):
    day: int = Field(ge=1)
    date: date
    tick: int = Field(ge=1)
    elapsed_hours: float = Field(gt=0)
    state_counts: dict[str, int]
    place_counts: dict[str, int]
    live_places: list[LocationLivePlaceState] = Field(default_factory=list)
    transition_counts: list[dict[str, Any]]
    interaction_outcome_counts: dict[str, int] = Field(default_factory=dict)
    event_count: int = Field(ge=0)
    interaction_count: int = Field(ge=0)


class SimulationResult(SimulationRunModel):
    source: Literal["rust"] = "rust"
    protocol_version: str
    engine_version: str
    data_version: str
    program_version: str
    input_hash: str
    output_hash: str
    snapshots: list[SnapshotSummary]


class SimulationRunView(SimulationRunModel):
    run_id: str
    config: SimulationRunConfig
    status: RunStatus
    progress: float = Field(ge=0, le=1)
    completed_ticks: int = Field(ge=0)
    total_ticks: int = Field(ge=1)
    result: SimulationResult | None = None
    error: str | None = None


class RunAgentSummary(SimulationRunModel):
    agent_id: str
    display_name: str
    final_module: str
    final_state: str
    final_location: str


class RunAgentPage(SimulationRunModel):
    items: list[RunAgentSummary]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    pages: int = Field(ge=0)


class DecisionPathStep(SimulationRunModel):
    tick: int = Field(ge=1)
    module: str
    transition: str
    from_state: str
    to_state: str
    probability: float = Field(ge=0, le=1)
    provenance: dict[str, Any]


class LocationTransitionStep(SimulationRunModel):
    tick: int = Field(ge=1)
    kind: str = Field(min_length=1)
    source: str = Field(min_length=1)
    schedule: str | None = None
    from_location: str = Field(min_length=1)
    to_location: str = Field(min_length=1)
    destination_location: str = Field(min_length=1)
    provenance: dict[str, Any]


class AgentInteractionDetail(SimulationRunModel):
    tick: int = Field(ge=1)
    role: Literal["initiator", "target"]
    interaction_type: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    other_agent_id: str = Field(min_length=1)
    other_agent_name: str = Field(min_length=1)
    place: str = Field(min_length=1)
    state_deltas: list[AppliedStateDelta]
    relationship_deltas: list[AppliedRelationshipDelta]
    interaction_tree: InteractionTreeTrace | None = None


class AgentTimelinePoint(SimulationRunModel):
    day: int = Field(ge=1)
    date: date
    tick: int = Field(ge=1)
    elapsed_hours: float = Field(gt=0)
    module: str
    state: str
    location: str
    actions: list[str]
    routine_actions: list[str]
    interactions: list[str]
    interaction_details: list[AgentInteractionDetail] = Field(default_factory=list)
    decision_path: list[DecisionPathStep]
    location_transitions: list[LocationTransitionStep]


class RunAgentDetail(RunAgentSummary):
    initial_module: str
    initial_state: str
    initial_location: str
    traits: dict[str, str | float]
    memory: dict[str, float]
    initial_profile: dict[str, Any] = Field(default_factory=dict)
    timeline: list[AgentTimelinePoint]


class RunEvent(SimulationRunModel):
    day: int = Field(ge=1)
    date: date
    tick: int = Field(ge=1)
    kind: Literal[
        "action",
        "routine",
        "transition",
        "location",
        "availability",
        "synchronization",
        "interaction",
    ]
    label: str
    agent_ids: list[str]
    location: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class RunEventPage(SimulationRunModel):
    items: list[RunEvent]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    pages: int = Field(ge=0)


@dataclass(frozen=True)
class _AgentTick:
    day: int
    date: date
    tick: int
    modules: tuple[str, ...]
    states: tuple[str, ...]
    locations: tuple[str, ...]
    actions: tuple[tuple[str, ...], ...]
    routines: tuple[tuple[str, ...], ...]
    interactions: tuple[tuple[str, ...], ...]
    interaction_details: tuple[tuple[AgentInteractionDetail, ...], ...]
    decisions: tuple[tuple[DecisionPathStep, ...], ...]
    location_transitions: tuple[tuple[LocationTransitionStep, ...], ...]
    live_places: tuple[LocationLivePlaceState, ...] = ()


@dataclass
class _RunRecord:
    run_id: str
    config: SimulationRunConfig
    status: RunStatus = "queued"
    progress: float = 0
    completed_ticks: int = 0
    result: SimulationResult | None = None
    error: str | None = None
    prepared: PreparedRustRun | None = None
    agent_ticks: list[_AgentTick] = field(default_factory=list)
    events: list[RunEvent] = field(default_factory=list)
    final_output: dict[str, Any] | None = None
    location_ids: list[str] = field(default_factory=list)
    location_history: list[LocationHistoryRecord] = field(default_factory=list)
    cancel_requested: threading.Event = field(default_factory=threading.Event)


class RunNotFoundError(KeyError):
    pass


class RunNotReadyError(RuntimeError):
    pass


class RunDeletionConflictError(RuntimeError):
    pass


class RunDeletionConfirmationError(ValueError):
    pass


class RunPreparationError(ValueError):
    pass


class SimulationRunService:
    def __init__(
        self,
        prepare_run: PreparedRunFactory,
        rust_client: RustRunClient,
        *,
        max_workers: int = 1,
        record_interactions: InteractionRecorder | None = None,
        record_locations: LocationRecorder | None = None,
        persistence: SimulationRunRecorder | None = None,
    ):
        self._prepare_run = prepare_run
        self._rust_client = rust_client
        self._record_interactions = record_interactions
        self._record_locations = record_locations
        self._persistence = persistence
        self._records: dict[str, _RunRecord] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="petraterrium-rust-run",
        )
        self._restore()

    def launch(self, config: SimulationRunConfig) -> SimulationRunView:
        try:
            prepared = self._prepare_run(config)
            self._validate_prepared(prepared, config)
        except ValueError as error:
            raise RunPreparationError(str(error)) from error
        run_id = uuid.uuid4().hex
        record = _RunRecord(
            run_id=run_id,
            config=config,
            prepared=prepared,
            location_ids=list(prepared.initial_location_ids),
        )
        with self._lock:
            self._records[run_id] = record
            self._persist_metadata(record)
        self._executor.submit(self._execute, run_id)
        return self.get(run_id)

    def list(self) -> list[SimulationRunView]:
        with self._lock:
            return [self._view(record) for record in reversed(self._records.values())]

    def get(self, run_id: str) -> SimulationRunView:
        with self._lock:
            return self._view(self._record(run_id))

    def cancel(self, run_id: str) -> SimulationRunView:
        with self._lock:
            record = self._record(run_id)
            if record.status in {"queued", "running"}:
                record.cancel_requested.set()
                record.status = "cancelling"
                self._persist_metadata(record)
            return self._view(record)

    def delete(self, run_id: str, confirmation: str) -> None:
        with self._lock:
            record = self._record(run_id)
            if confirmation != run_id:
                raise RunDeletionConfirmationError(
                    "Run deletion confirmation must match the run ID"
                )
            if record.status in {"queued", "running", "cancelling"}:
                raise RunDeletionConflictError("Active simulation runs cannot be deleted")
            if self._persistence is not None:
                self._persistence.delete(run_id)
            del self._records[run_id]

    def agents(
        self,
        run_id: str,
        *,
        search: str = "",
        page: int = 1,
        page_size: int = 100,
    ) -> RunAgentPage:
        if page < 1 or page_size < 1 or page_size > 500:
            raise ValueError("Agent page and page size are outside the allowed range")
        with self._lock:
            record = self._completed_record(run_id)
            prepared = self._required_prepared(record)
            final = self._required_final(record)
            columns = self._agent_columns(final)
            places = self._place_labels(prepared.rust_request)
            names = prepared.display_names()
            summaries = [
                RunAgentSummary(
                    agent_id=agent_id,
                    display_name=names[index],
                    final_module=str(columns["module"][index]),
                    final_state=str(columns["state"][index]),
                    final_location=self._location_label(columns, index, places),
                )
                for index, agent_id in enumerate(prepared.agent_ids)
            ]
        normalized = search.strip().casefold()
        if normalized:
            summaries = [
                item
                for item in summaries
                if normalized
                in " ".join(
                    (
                        item.agent_id,
                        item.display_name,
                        item.final_module,
                        item.final_state,
                        item.final_location,
                    )
                ).casefold()
            ]
        total = len(summaries)
        start = (page - 1) * page_size
        pages = (total + page_size - 1) // page_size
        return RunAgentPage(
            items=summaries[start : start + page_size],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    def agent(self, run_id: str, agent_id: str) -> RunAgentDetail:
        with self._lock:
            record = self._completed_record(run_id)
            prepared = self._required_prepared(record)
            try:
                index = prepared.agent_ids.index(agent_id)
            except ValueError as error:
                raise RunNotFoundError(agent_id) from error
            final = self._required_final(record)
            columns = self._agent_columns(final)
            places = self._place_labels(prepared.rust_request)
            initial_columns = self._agent_columns({"agents": prepared.rust_request["agents"]})
            names = prepared.display_names()
            timeline = [
                AgentTimelinePoint(
                    day=frame.day,
                    date=frame.date,
                    tick=frame.tick,
                    elapsed_hours=frame.tick * record.config.tick_interval_hours,
                    module=frame.modules[index],
                    state=frame.states[index],
                    location=frame.locations[index],
                    actions=list(frame.actions[index]),
                    routine_actions=list(frame.routines[index]),
                    interactions=list(frame.interactions[index]),
                    interaction_details=list(frame.interaction_details[index]),
                    decision_path=list(frame.decisions[index]),
                    location_transitions=list(frame.location_transitions[index]),
                )
                for frame in record.agent_ticks
            ]
            return RunAgentDetail(
                agent_id=agent_id,
                display_name=names[index],
                final_module=str(columns["module"][index]),
                final_state=str(columns["state"][index]),
                final_location=self._location_label(columns, index, places),
                initial_module=str(initial_columns["module"][index]),
                initial_state=str(initial_columns["state"][index]),
                initial_location=self._location_label(initial_columns, index, places),
                traits=self._agent_traits(columns, index),
                memory=self._agent_memory(columns, index),
                initial_profile=(
                    prepared.initial_agent_profiles[index]
                    if prepared.initial_agent_profiles
                    else {}
                ),
                timeline=timeline,
            )

    def events(
        self,
        run_id: str,
        *,
        kind: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> RunEventPage:
        if page < 1 or page_size < 1 or page_size > 500:
            raise ValueError("Event page and page size are outside the allowed range")
        with self._lock:
            record = self._completed_record(run_id)
            items = [item for item in record.events if kind is None or item.kind == kind]
        total = len(items)
        start = (page - 1) * page_size
        return RunEventPage(
            items=items[start : start + page_size],
            total=total,
            page=page,
            page_size=page_size,
            pages=(total + page_size - 1) // page_size,
        )

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)

    def _record(self, run_id: str) -> _RunRecord:
        try:
            return self._records[run_id]
        except KeyError as error:
            raise RunNotFoundError(run_id) from error

    def _completed_record(self, run_id: str) -> _RunRecord:
        record = self._record(run_id)
        if record.status != "completed":
            raise RunNotReadyError(f"Run {run_id} is {record.status}")
        return record

    @staticmethod
    def _view(record: _RunRecord) -> SimulationRunView:
        return SimulationRunView(
            run_id=record.run_id,
            config=record.config,
            status=record.status,
            progress=record.progress,
            completed_ticks=record.completed_ticks,
            total_ticks=record.config.total_ticks,
            result=record.result,
            error=record.error,
        )

    @staticmethod
    def _required_prepared(record: _RunRecord) -> PreparedRustRun:
        if record.prepared is None:
            raise RunNotReadyError(f"Run {record.run_id} has no prepared population")
        return record.prepared

    @staticmethod
    def _required_final(record: _RunRecord) -> dict[str, Any]:
        if record.final_output is None:
            raise RunNotReadyError(f"Run {record.run_id} has no Rust output")
        return record.final_output

    def _execute(self, run_id: str) -> None:
        try:
            with self._lock:
                record = self._record(run_id)
                config = record.config
                prepared = self._required_prepared(record)
            request = deepcopy(prepared.rust_request)
            request.pop("operation", None)
            request["seed"] = config.seed
            request["tick_hours"] = config.tick_interval_hours
            request["start_weekday"] = config.start_date.weekday()
            input_hash = self._hash(
                {
                    "config": config.model_dump(mode="json"),
                    "request": request,
                    "data_version": prepared.data_version,
                    "program_version": prepared.program_version,
                }
            )
            output_digest = hashlib.sha256()
            summaries: list[SnapshotSummary] = []
            with self._lock:
                if record.cancel_requested.is_set():
                    record.status = "cancelled"
                    self._persist_metadata(record)
                    return
                record.status = "running"
                self._persist_metadata(record)
            previous_snapshot_tick = 0
            completed_tick = 0
            daily_output: dict[str, Any] | None = None
            accumulated_output: dict[str, Any] | None = None
            agent_names = dict(zip(prepared.agent_ids, prepared.display_names(), strict=True))
            while completed_tick < config.total_ticks:
                with self._lock:
                    if record.cancel_requested.is_set():
                        record.status = "cancelled"
                        self._persist_metadata(record)
                        return
                ticks_until_snapshot = config.ticks_per_day - (
                    completed_tick % config.ticks_per_day
                )
                chunk_ticks = min(ticks_until_snapshot, MAX_RUST_CHUNK_TICKS)
                request["ticks"] = chunk_ticks
                output = self._rust_client.run_agents(request)
                self._validate_output(output, prepared)
                tick = completed_tick + chunk_ticks
                if int(output.get("ticks", tick)) != tick:
                    raise ValueError(
                        f"Rust output completed tick {output.get('ticks')} does not match {tick}"
                    )
                if self._record_interactions is not None:
                    self._record_interactions(
                        run_id,
                        {"events": output.get("interactions", [])},
                        agent_names,
                    )
                if self._record_locations is not None and prepared.location_places:
                    location_state = self._location_state(record, output, prepared, tick)
                    self._record_locations(
                        run_id,
                        tick,
                        prepared.location_places,
                        location_state,
                        agent_names,
                    )
                encoded = self._canonical_json(output)
                output_digest.update(len(encoded).to_bytes(8, "big"))
                output_digest.update(encoded)
                accumulated_output = self._merge_chunk_output(accumulated_output, output)
                daily_output = self._merge_chunk_output(daily_output, output)
                completed_tick = tick
                with self._lock:
                    record.final_output = accumulated_output
                    record.completed_ticks = tick
                    record.progress = tick / config.total_ticks
                    self._persist_metadata(record)
                if completed_tick < config.total_ticks:
                    self._prepare_continuation_request(request, output, prepared, tick)
                if tick % config.ticks_per_day:
                    continue
                day = tick // config.ticks_per_day
                if daily_output is None:
                    raise ValueError(f"Rust output for day {day} is missing")
                frame, summary, events = self._frame(
                    daily_output,
                    prepared,
                    config,
                    day,
                    previous_snapshot_tick,
                    tick,
                )
                with self._lock:
                    first_event_index = len(record.events)
                    record.agent_ticks.append(frame)
                    record.events.extend(events)
                    summaries.append(summary)
                    self._persist_checkpoint(
                        record,
                        len(record.agent_ticks) - 1,
                        frame,
                        first_event_index,
                        events,
                    )
                previous_snapshot_tick = tick
                daily_output = None
            with self._lock:
                if record.cancel_requested.is_set():
                    record.status = "cancelled"
                    self._persist_metadata(record)
                    return
                final = self._required_final(record)
                record.result = SimulationResult(
                    protocol_version=str(final["protocol_version"]),
                    engine_version=str(final["engine_version"]),
                    data_version=prepared.data_version,
                    program_version=prepared.program_version,
                    input_hash=input_hash,
                    output_hash=output_digest.hexdigest(),
                    snapshots=summaries,
                )
                record.status = "completed"
                self._persist_metadata(record)
        except Exception as error:
            with self._lock:
                record = self._records.get(run_id)
                if record is not None:
                    if record.cancel_requested.is_set():
                        record.status = "cancelled"
                    else:
                        record.status = "failed"
                        record.error = str(error)
                    self._persist_metadata(record)

    @staticmethod
    def _merge_chunk_output(
        accumulated: Mapping[str, Any] | None,
        output: Mapping[str, Any],
    ) -> dict[str, Any]:
        merged = deepcopy(dict(output))
        if accumulated is None:
            return merged
        for field_name in CHUNK_EVENT_FIELDS:
            earlier = accumulated.get(field_name, [])
            current = output.get(field_name, [])
            if not isinstance(earlier, list) or not isinstance(current, list):
                raise ValueError(f"Rust output {field_name} must be a list")
            merged[field_name] = deepcopy(earlier) + deepcopy(current)
        return merged

    @classmethod
    def _prepare_continuation_request(
        cls,
        request: dict[str, Any],
        output: Mapping[str, Any],
        prepared: PreparedRustRun,
        completed_tick: int,
    ) -> None:
        continuation = output.get("continuation")
        if not isinstance(continuation, Mapping):
            raise ValueError("Rust output is missing continuation state")
        if int(continuation.get("completed_tick", -1)) != completed_tick:
            raise ValueError("Rust continuation completed tick does not match its output")
        agents = deepcopy(dict(cls._agent_columns(output)))
        request_agents = request.get("agents")
        if not isinstance(request_agents, Mapping):
            raise ValueError("Rust continuation request is missing initial agent columns")
        agent_ids = request_agents.get("agent_ids")
        if isinstance(agent_ids, list):
            agents["agent_ids"] = deepcopy(agent_ids)
        if len(agents.get("state", [])) != len(prepared.agent_ids):
            raise ValueError("Rust continuation agent state does not match the population")
        request["agents"] = agents
        request["continuation"] = deepcopy(dict(continuation))

    def _restore(self) -> None:
        if self._persistence is None:
            return
        for stored in self._persistence.load():
            record = self._stored_record(stored)
            if record.status in {"queued", "running", "cancelling"}:
                record.status = "failed"
                record.error = "The API restarted before this Rust run reached a recorded result."
                self._persist_metadata(record)
            self._records[record.run_id] = record
            self._restore_derived_catalogs(record)

    def _restore_derived_catalogs(self, record: _RunRecord) -> None:
        if record.status != "completed" or record.prepared is None:
            return
        prepared = record.prepared
        names = dict(zip(prepared.agent_ids, prepared.display_names(), strict=True))
        if self._record_interactions is not None and record.final_output is not None:
            self._record_interactions(
                record.run_id,
                {"events": record.final_output.get("interactions", [])},
                names,
            )
        if self._record_locations is None or not prepared.location_places:
            return
        current_location_ids = record.location_ids or prepared.initial_location_ids
        state = LocationRuntimeState(
            agents=LocationAgentColumns(
                agent_ids=tuple(prepared.agent_ids),
                current_location_ids=tuple(current_location_ids),
            ),
            history=tuple(record.location_history),
            live_places=(record.agent_ticks[-1].live_places if record.agent_ticks else ()),
        )
        self._record_locations(
            record.run_id,
            record.completed_ticks,
            prepared.location_places,
            state,
            names,
        )

    def _persist_metadata(self, record: _RunRecord) -> None:
        if self._persistence is None:
            return
        self._persistence.save_metadata(record.run_id, self._metadata_payload(record))

    def _persist_checkpoint(
        self,
        record: _RunRecord,
        frame_index: int,
        frame: _AgentTick,
        first_event_index: int,
        events: list[RunEvent],
    ) -> None:
        if self._persistence is None:
            return
        self._persistence.append_checkpoint(
            record.run_id,
            self._metadata_payload(record),
            frame_index,
            self._frame_payload(frame),
            first_event_index,
            [event.model_dump(mode="json") for event in events],
        )

    @staticmethod
    def _metadata_payload(record: _RunRecord) -> dict[str, Any]:
        return {
            "run_id": record.run_id,
            "config": record.config.model_dump(mode="json"),
            "status": record.status,
            "progress": record.progress,
            "completed_ticks": record.completed_ticks,
            "result": record.result.model_dump(mode="json") if record.result else None,
            "error": record.error,
            "prepared": record.prepared.model_dump(mode="json") if record.prepared else None,
            "final_output": record.final_output,
            "location_ids": record.location_ids,
            "location_history": [item.model_dump(mode="json") for item in record.location_history],
        }

    @staticmethod
    def _frame_payload(frame: _AgentTick) -> dict[str, Any]:
        return {
            "day": frame.day,
            "date": frame.date.isoformat(),
            "tick": frame.tick,
            "modules": list(frame.modules),
            "states": list(frame.states),
            "locations": list(frame.locations),
            "actions": [list(values) for values in frame.actions],
            "routines": [list(values) for values in frame.routines],
            "interactions": [list(values) for values in frame.interactions],
            "interaction_details": [
                [item.model_dump(mode="json") for item in values]
                for values in frame.interaction_details
            ],
            "decisions": [
                [item.model_dump(mode="json") for item in values] for values in frame.decisions
            ],
            "location_transitions": [
                [item.model_dump(mode="json") for item in values]
                for values in frame.location_transitions
            ],
            "live_places": [place.model_dump(mode="json") for place in frame.live_places],
        }

    @classmethod
    def _stored_record(cls, stored: StoredSimulationRun) -> _RunRecord:
        metadata = stored.metadata
        return _RunRecord(
            run_id=str(metadata["run_id"]),
            config=SimulationRunConfig.model_validate(metadata["config"]),
            status=str(metadata["status"]),
            progress=float(metadata["progress"]),
            completed_ticks=int(metadata["completed_ticks"]),
            result=(
                SimulationResult.model_validate_json(json.dumps(metadata["result"]))
                if metadata.get("result") is not None
                else None
            ),
            error=str(metadata["error"]) if metadata.get("error") is not None else None,
            prepared=(
                PreparedRustRun.model_validate(metadata["prepared"])
                if metadata.get("prepared") is not None
                else None
            ),
            agent_ticks=[cls._stored_frame(frame) for frame in stored.frames],
            events=[RunEvent.model_validate_json(json.dumps(event)) for event in stored.events],
            final_output=(
                dict(metadata["final_output"]) if metadata.get("final_output") is not None else None
            ),
            location_ids=[str(value) for value in metadata.get("location_ids", [])],
            location_history=[
                LocationHistoryRecord.model_validate(item)
                for item in metadata.get("location_history", [])
            ],
        )

    @staticmethod
    def _stored_frame(payload: Mapping[str, Any]) -> _AgentTick:
        return _AgentTick(
            day=int(payload["day"]),
            date=date.fromisoformat(str(payload["date"])),
            tick=int(payload["tick"]),
            modules=tuple(str(value) for value in payload["modules"]),
            states=tuple(str(value) for value in payload["states"]),
            locations=tuple(str(value) for value in payload["locations"]),
            actions=tuple(tuple(str(value) for value in row) for row in payload["actions"]),
            routines=tuple(tuple(str(value) for value in row) for row in payload["routines"]),
            interactions=tuple(
                tuple(str(value) for value in row) for row in payload["interactions"]
            ),
            interaction_details=tuple(
                tuple(AgentInteractionDetail.model_validate(value) for value in row)
                for row in payload.get(
                    "interaction_details",
                    [[] for _ in payload["states"]],
                )
            ),
            decisions=tuple(
                tuple(DecisionPathStep.model_validate(value) for value in row)
                for row in payload["decisions"]
            ),
            location_transitions=tuple(
                tuple(LocationTransitionStep.model_validate(value) for value in row)
                for row in payload["location_transitions"]
            ),
            live_places=tuple(
                LocationLivePlaceState.model_validate(value)
                for value in payload.get("live_places", [])
            ),
        )

    @classmethod
    def _location_state(
        cls,
        record: _RunRecord,
        output: Mapping[str, Any],
        prepared: PreparedRustRun,
        tick: int,
    ) -> LocationRuntimeState:
        columns = cls._agent_columns(output)
        initial_columns = cls._agent_columns({"agents": prepared.rust_request["agents"]})
        previous = record.location_ids or list(prepared.initial_location_ids)
        previous_tick = record.completed_ticks

        def runtime_location(agent_index: int, runtime_place_index: int) -> str:
            initial_runtime_place = int(initial_columns["place"][agent_index])
            if runtime_place_index == initial_runtime_place:
                return prepared.initial_location_ids[agent_index]
            return prepared.runtime_place_location_ids[runtime_place_index]

        registry = {place.id: place for place in prepared.location_places}
        moved_agents: set[int] = set()
        for item in cls._list_of_mappings(output.get("location_transitions", [])):
            event_tick = int(item.get("tick", -1))
            if not previous_tick < event_tick <= tick:
                continue
            agent_index = cls._agent_index(item.get("agent_index"), len(prepared.agent_ids))
            from_index = cls._place_index(
                item.get("from_place_index"), len(prepared.runtime_place_location_ids)
            )
            to_index = cls._place_index(
                item.get("to_place_index"), len(prepared.runtime_place_location_ids)
            )
            before = runtime_location(agent_index, from_index)
            after = runtime_location(agent_index, to_index)
            if before == after:
                continue
            moved_agents.add(agent_index)
            record.location_history.append(
                LocationHistoryRecord(
                    tick=event_tick,
                    agent_id=prepared.agent_ids[agent_index],
                    from_location_id=before,
                    to_location_id=after,
                    route_location_ids=cls._location_route(registry, before, after),
                )
            )
        current: list[str] = []
        for index, runtime_place in enumerate(columns["place"]):
            runtime_place_index = int(runtime_place)
            current.append(runtime_location(index, runtime_place_index))
        for index, (before, after) in enumerate(zip(previous, current, strict=True)):
            if before == after or index in moved_agents:
                continue
            record.location_history.append(
                LocationHistoryRecord(
                    tick=tick,
                    agent_id=prepared.agent_ids[index],
                    from_location_id=before,
                    to_location_id=after,
                    route_location_ids=cls._location_route(registry, before, after),
                )
            )
        record.location_ids = current
        return LocationRuntimeState(
            agents=LocationAgentColumns(
                agent_ids=tuple(prepared.agent_ids),
                current_location_ids=tuple(current),
            ),
            history=tuple(record.location_history),
            live_places=cls._live_places(output, prepared),
        )

    @staticmethod
    def _location_route(
        registry: Mapping[str, LocationPlace], source_id: str, destination_id: str
    ) -> tuple[str, ...]:
        def ancestry(place_id: str) -> list[str]:
            result = [place_id]
            while registry[result[-1]].parent_id is not None:
                result.append(str(registry[result[-1]].parent_id))
            return result

        source = ancestry(source_id)
        destination = ancestry(destination_id)
        destination_positions = {
            place_id: position for position, place_id in enumerate(destination)
        }
        shared = next(
            (
                (position, destination_positions[place_id])
                for position, place_id in enumerate(source)
                if place_id in destination_positions
            ),
            None,
        )
        if shared is None:
            return tuple(source + list(reversed(destination)))
        source_common, destination_common = shared
        return tuple(source[: source_common + 1] + list(reversed(destination[:destination_common])))

    @classmethod
    def _live_places(
        cls,
        output: Mapping[str, Any],
        prepared: PreparedRustRun,
    ) -> tuple[LocationLivePlaceState, ...]:
        raw_places = cls._list_of_mappings(output.get("live_places", []))
        runtime_places = prepared.rust_request.get("places")
        if not isinstance(runtime_places, list):
            raise ValueError("Prepared Rust run requires place definitions")
        if len(raw_places) != len(runtime_places):
            raise ValueError("Rust live place state does not match the runtime place count")
        continuation = output.get("continuation")
        if isinstance(continuation, Mapping) and "live_places" in continuation:
            continuation_places = cls._list_of_mappings(continuation["live_places"])
            if continuation_places != raw_places:
                raise ValueError("Rust continuation live place state differs from its output")
        live_places: list[LocationLivePlaceState] = []
        for expected_index, item in enumerate(raw_places):
            runtime = runtime_places[expected_index]
            if not isinstance(runtime, Mapping):
                raise ValueError("Prepared Rust place definitions must be objects")
            place_index = int(item.get("place_index", -1))
            runtime_place_id = str(item.get("place_id", ""))
            if place_index != expected_index:
                raise ValueError("Rust live place indices must follow runtime place order")
            if runtime_place_id != str(runtime.get("id", "")):
                raise ValueError("Rust live place id does not match its prepared runtime place")
            kind = str(item.get("kind", ""))
            accepts_arrivals = item.get("accepts_arrivals")
            allows_in_person = item.get("allows_in_person")
            capacity = item.get("capacity")
            if kind != str(runtime.get("kind", "place")):
                raise ValueError("Rust live place kind does not match its prepared runtime place")
            if accepts_arrivals is not runtime.get("accepts_arrivals", True):
                raise ValueError("Rust live arrival state does not match its prepared place")
            if allows_in_person is not runtime.get("allows_in_person", True):
                raise ValueError("Rust live contact state does not match its prepared place")
            if capacity != runtime.get("capacity"):
                raise ValueError("Rust live capacity does not match its prepared place")
            live_places.append(
                LocationLivePlaceState.model_validate(
                    {
                        "runtime_place_index": place_index,
                        "runtime_place_id": runtime_place_id,
                        "location_id": prepared.runtime_place_location_ids[place_index],
                        "kind": kind,
                        "accepts_arrivals": accepts_arrivals,
                        "allows_in_person": allows_in_person,
                        "capacity": capacity,
                        "occupancy": item.get("occupancy"),
                        "crowd_density": item.get("crowd_density"),
                        "state": item.get("state"),
                    }
                )
            )
        return tuple(live_places)

    @staticmethod
    def _validate_prepared(prepared: PreparedRustRun, config: SimulationRunConfig) -> None:
        agents = prepared.rust_request.get("agents")
        if not isinstance(agents, Mapping):
            raise ValueError("Prepared Rust run requires agent columns")
        for key in ("module", "state", "place"):
            values = agents.get(key)
            if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
                raise ValueError(f"Prepared Rust agent column {key} is missing")
            if len(values) != config.population_size:
                raise ValueError(
                    f"Prepared Rust agent column {key} has {len(values)} values; "
                    f"expected {config.population_size}"
                )
        if len(prepared.agent_ids) != config.population_size:
            raise ValueError("Prepared Rust identities do not match the configured population")

    @classmethod
    def _validate_output(cls, output: Mapping[str, Any], prepared: PreparedRustRun) -> None:
        for key in ("protocol_version", "engine_version", "agents"):
            if key not in output:
                raise ValueError(f"Rust output is missing {key}")
        columns = cls._agent_columns(output)
        expected = len(prepared.agent_ids)
        for key in ("module", "state", "place"):
            values = columns.get(key)
            if not isinstance(values, list) or len(values) != expected:
                raise ValueError(f"Rust output column {key} does not match the initial population")
        if prepared.location_places:
            cls._live_places(output, prepared)

    @classmethod
    def _frame(
        cls,
        output: dict[str, Any],
        prepared: PreparedRustRun,
        config: SimulationRunConfig,
        day: int,
        previous_tick: int,
        tick: int,
    ) -> tuple[_AgentTick, SnapshotSummary, list[RunEvent]]:
        columns = cls._agent_columns(output)
        places = cls._place_labels(prepared.rust_request)
        modules = tuple(str(value) for value in columns["module"])
        states = tuple(str(value) for value in columns["state"])
        locations = tuple(
            cls._location_label(columns, index, places) for index in range(len(states))
        )
        live_places = cls._live_places(output, prepared) if prepared.location_places else ()
        events = cls._events_for_range(
            output,
            prepared.agent_ids,
            places,
            config,
            previous_tick,
            tick,
        )
        actions: list[list[str]] = [[] for _ in states]
        routines: list[list[str]] = [[] for _ in states]
        interactions: list[list[str]] = [[] for _ in states]
        interaction_details: list[list[AgentInteractionDetail]] = [[] for _ in states]
        decisions: list[list[DecisionPathStep]] = [[] for _ in states]
        location_transitions: list[list[LocationTransitionStep]] = [[] for _ in states]
        id_indices = {agent_id: index for index, agent_id in enumerate(prepared.agent_ids)}
        agent_names = dict(zip(prepared.agent_ids, prepared.display_names(), strict=True))
        for event in events:
            if event.kind == "transition":
                for agent_id in event.agent_ids:
                    index = id_indices.get(agent_id)
                    if index is not None:
                        decisions[index].append(
                            DecisionPathStep(
                                tick=event.tick,
                                module=str(event.details.get("module", "")),
                                transition=str(event.details.get("transition", event.label)),
                                from_state=str(event.details.get("from_state", "")),
                                to_state=str(event.details.get("to_state", "")),
                                probability=float(event.details.get("probability", 0)),
                                provenance=dict(event.details.get("provenance", {})),
                            )
                        )
                continue
            if event.kind == "location":
                for agent_id in event.agent_ids:
                    index = id_indices.get(agent_id)
                    if index is not None:
                        location_transitions[index].append(
                            LocationTransitionStep(
                                tick=event.tick,
                                kind=str(event.details["kind"]),
                                source=str(event.details["source"]),
                                schedule=(
                                    str(event.details["schedule"])
                                    if "schedule" in event.details
                                    else None
                                ),
                                from_location=str(event.details["from_location"]),
                                to_location=str(event.details["to_location"]),
                                destination_location=str(event.details["destination_location"]),
                                provenance=dict(event.details["provenance"]),
                            )
                        )
                continue
            if event.kind == "interaction":
                for agent_id in event.agent_ids:
                    index = id_indices.get(agent_id)
                    if index is not None:
                        interactions[index].append(event.label)
                        interaction_details[index].append(
                            cls._agent_interaction_detail(event, agent_id, agent_names)
                        )
                continue
            target = routines if event.kind == "routine" else actions
            for agent_id in event.agent_ids:
                index = id_indices.get(agent_id)
                if index is not None:
                    target[index].append(event.label)
        state_counts = Counter(
            f"{module} / {state}" for module, state in zip(modules, states, strict=True)
        )
        place_counts = Counter(locations)
        transitions = [
            dict(item)
            for item in cls._list_of_mappings(output.get("transition_counts", []))
            if previous_tick < int(item.get("tick", -1)) <= tick
        ]
        frame = _AgentTick(
            day=day,
            date=config.start_date + timedelta(days=day - 1),
            tick=tick,
            modules=modules,
            states=states,
            locations=locations,
            actions=tuple(tuple(values) for values in actions),
            routines=tuple(tuple(values) for values in routines),
            interactions=tuple(tuple(values) for values in interactions),
            interaction_details=tuple(tuple(values) for values in interaction_details),
            decisions=tuple(tuple(values) for values in decisions),
            location_transitions=tuple(tuple(values) for values in location_transitions),
            live_places=live_places,
        )
        summary = SnapshotSummary(
            day=day,
            date=config.start_date + timedelta(days=day - 1),
            tick=tick,
            elapsed_hours=tick * config.tick_interval_hours,
            state_counts=dict(sorted(state_counts.items())),
            place_counts=dict(sorted(place_counts.items())),
            live_places=list(live_places),
            transition_counts=transitions,
            interaction_outcome_counts=cls._interaction_outcome_counts(events),
            event_count=sum(event.kind in {"action", "routine"} for event in events),
            interaction_count=sum(event.kind == "interaction" for event in events),
        )
        return frame, summary, events

    @classmethod
    def _agent_interaction_detail(
        cls,
        event: RunEvent,
        agent_id: str,
        agent_names: Mapping[str, str],
    ) -> AgentInteractionDetail:
        if len(event.agent_ids) != 2:
            raise ValueError("Rust interaction output must identify two participants")
        details = event.details
        initiator_id = str(
            details.get(
                "initiator_id",
                details.get("source_agent_id", event.agent_ids[0]),
            )
        )
        target_id = str(
            details.get(
                "target_id",
                details.get("target_agent_id", event.agent_ids[1]),
            )
        )
        if agent_id == initiator_id:
            role = "initiator"
            other_agent_id = target_id
        elif agent_id == target_id:
            role = "target"
            other_agent_id = initiator_id
        else:
            raise ValueError(f"Interaction participant {agent_id} is not an endpoint")
        state_deltas = [
            AppliedStateDelta.model_validate(item)
            for item in cls._list_of_mappings(details.get("state_deltas", []))
            if str(item.get("agent_id", "")) == agent_id
        ]
        relationship_deltas = [
            AppliedRelationshipDelta.model_validate(item)
            for item in cls._list_of_mappings(details.get("relationship_deltas", []))
        ]
        tree_payload = details.get("interaction_tree")
        interaction_tree = (
            InteractionTreeTrace.model_validate(tree_payload) if tree_payload is not None else None
        )
        place = event.location or str(details.get("place_id", "")).strip()
        if not place:
            raise ValueError("Rust interaction output must identify a place")
        return AgentInteractionDetail(
            tick=event.tick,
            role=role,
            interaction_type=str(details.get("interaction_type", event.label)),
            channel=str(details.get("channel", "unknown")),
            other_agent_id=other_agent_id,
            other_agent_name=agent_names.get(other_agent_id, other_agent_id),
            place=place,
            state_deltas=state_deltas,
            relationship_deltas=relationship_deltas,
            interaction_tree=interaction_tree,
        )

    @staticmethod
    def _interaction_outcome_counts(events: Sequence[RunEvent]) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for event in events:
            if event.kind != "interaction":
                continue
            tree = event.details.get("interaction_tree")
            outcome = str(tree.get("outcome", "")).strip() if isinstance(tree, Mapping) else ""
            counts[outcome or event.label] += 1
        return dict(sorted(counts.items()))

    @classmethod
    def _events_for_range(
        cls,
        output: Mapping[str, Any],
        agent_ids: list[str],
        places: list[str],
        config: SimulationRunConfig,
        previous_tick: int,
        tick: int,
    ) -> list[RunEvent]:
        result: list[RunEvent] = []
        for item in cls._list_of_mappings(output.get("events", [])):
            event_tick = int(item.get("tick", -1))
            if not previous_tick < event_tick <= tick:
                continue
            index = cls._agent_index(item.get("agent_index"), len(agent_ids))
            place_index = cls._place_index(item.get("place_index"), len(places))
            result.append(
                RunEvent(
                    day=cls._event_day(event_tick, config.ticks_per_day),
                    date=cls._event_date(event_tick, config),
                    tick=event_tick,
                    kind="action",
                    label=str(item.get("action", "action")),
                    agent_ids=[agent_ids[index]],
                    location=places[place_index],
                    details=dict(item),
                )
            )
        for item in cls._list_of_mappings(output.get("routine_actions", [])):
            event_tick = int(item.get("tick", -1))
            if not previous_tick < event_tick <= tick:
                continue
            indices = [
                cls._agent_index(value, len(agent_ids))
                for value in cls._list_values(item.get("agent_indices", []))
            ]
            result.append(
                RunEvent(
                    day=cls._event_day(event_tick, config.ticks_per_day),
                    date=cls._event_date(event_tick, config),
                    tick=event_tick,
                    kind="routine",
                    label=str(item.get("action", item.get("schedule", "routine"))),
                    agent_ids=[agent_ids[index] for index in indices],
                    details=dict(item),
                )
            )
        for item in cls._list_of_mappings(output.get("routine_unavailable", [])):
            event_tick = int(item.get("tick", -1))
            if not previous_tick < event_tick <= tick:
                continue
            index = cls._agent_index(item.get("agent_index"), len(agent_ids))
            place_index = cls._place_index(item.get("current_place_index"), len(places))
            reason = cls._required_event_text(item, "reason", "routine availability record")
            result.append(
                RunEvent(
                    day=cls._event_day(event_tick, config.ticks_per_day),
                    date=cls._event_date(event_tick, config),
                    tick=event_tick,
                    kind="availability",
                    label=reason,
                    agent_ids=[agent_ids[index]],
                    location=places[place_index],
                    details=dict(item),
                )
            )
        for item in cls._list_of_mappings(output.get("location_transitions", [])):
            event_tick = int(item.get("tick", -1))
            if not previous_tick < event_tick <= tick:
                continue
            index = cls._agent_index(item.get("agent_index"), len(agent_ids))
            from_location = places[cls._place_index(item.get("from_place_index"), len(places))]
            to_location = places[cls._place_index(item.get("to_place_index"), len(places))]
            destination_location = places[
                cls._place_index(item.get("destination_place_index"), len(places))
            ]
            phase = cls._required_event_text(item, "phase", "location transition")
            source = cls._required_event_text(item, "source", "location transition")
            if phase in {"schedule_move", "travel_started", "travel_arrived"}:
                source_kind = "schedule"
            elif phase == "module_effect":
                source_kind = "transition"
            else:
                source_kind = "unknown"
            explicit_provenance = item.get("provenance", {})
            if not isinstance(explicit_provenance, Mapping):
                raise ValueError("Rust location transition provenance must be an object")
            provenance = {
                "recorded_by": "rust_numeric_core",
                "record": "location_transitions",
                "source_kind": source_kind,
                **dict(explicit_provenance),
            }
            details = {
                **dict(item),
                "kind": phase,
                "source": source,
                "from_location": from_location,
                "to_location": to_location,
                "destination_location": destination_location,
                "provenance": provenance,
            }
            if source_kind == "schedule":
                details["schedule"] = source
            elif source_kind == "transition":
                details["transition"] = source
            result.append(
                RunEvent(
                    day=cls._event_day(event_tick, config.ticks_per_day),
                    date=cls._event_date(event_tick, config),
                    tick=event_tick,
                    kind="location",
                    label=f"{from_location} → {to_location}",
                    agent_ids=[agent_ids[index]],
                    location=to_location,
                    details=details,
                )
            )
        for item in cls._list_of_mappings(output.get("transition_outcomes", [])):
            event_tick = int(item.get("tick", -1))
            if not previous_tick < event_tick <= tick:
                continue
            index = cls._agent_index(item.get("agent_index"), len(agent_ids))
            result.append(
                RunEvent(
                    day=cls._event_day(event_tick, config.ticks_per_day),
                    date=cls._event_date(event_tick, config),
                    tick=event_tick,
                    kind="transition",
                    label=str(item.get("transition", "transition")),
                    agent_ids=[agent_ids[index]],
                    details=dict(item),
                )
            )
        for item in cls._list_of_mappings(output.get("synchronization", [])):
            event_tick = int(item.get("tick", -1))
            if not previous_tick < event_tick <= tick:
                continue
            result.append(
                RunEvent(
                    day=cls._event_day(event_tick, config.ticks_per_day),
                    date=cls._event_date(event_tick, config),
                    tick=event_tick,
                    kind="synchronization",
                    label=str(item.get("kind", "synchronization")),
                    agent_ids=[],
                    details=dict(item),
                )
            )
        for item in cls._list_of_mappings(output.get("interactions", [])):
            event_tick = int(item.get("tick", -1))
            if not previous_tick < event_tick <= tick:
                continue
            indices = cls._interaction_agent_indices(item, len(agent_ids))
            place_value = item.get("place_index")
            location = None
            if place_value is not None:
                location = places[cls._place_index(place_value, len(places))]
            result.append(
                RunEvent(
                    day=cls._event_day(event_tick, config.ticks_per_day),
                    date=cls._event_date(event_tick, config),
                    tick=event_tick,
                    kind="interaction",
                    label=str(
                        item.get(
                            "interaction_type",
                            item.get("action", item.get("kind", "interaction")),
                        )
                    ),
                    agent_ids=[agent_ids[index] for index in indices],
                    location=location,
                    details=dict(item),
                )
            )
        result.sort(key=lambda item: item.tick)
        return result

    @staticmethod
    def _event_day(tick: int, ticks_per_day: int) -> int:
        return (tick - 1) // ticks_per_day + 1

    @classmethod
    def _event_date(cls, tick: int, config: SimulationRunConfig) -> date:
        return config.start_date + timedelta(days=cls._event_day(tick, config.ticks_per_day) - 1)

    @staticmethod
    def _interaction_agent_indices(item: Mapping[str, Any], population: int) -> list[int]:
        values = []
        for key in (
            "source_agent_index",
            "initiator_index",
            "target_agent_index",
            "target_index",
            "actor_index",
            "counterpart_index",
            "agent_index",
        ):
            if key in item:
                values.append(SimulationRunService._agent_index(item[key], population))
        return list(dict.fromkeys(values))

    @staticmethod
    def _agent_columns(output: Mapping[str, Any]) -> Mapping[str, Any]:
        agents = output.get("agents")
        if not isinstance(agents, Mapping):
            raise ValueError("Rust output agents must be an object")
        return agents

    @staticmethod
    def _place_labels(request: Mapping[str, Any]) -> list[str]:
        places = request.get("places")
        if not isinstance(places, list) or not places:
            raise ValueError("Prepared Rust run requires place shards")
        result = []
        for index, place in enumerate(places):
            if not isinstance(place, Mapping) or not str(place.get("id", "")).strip():
                raise ValueError(f"Prepared Rust place {index} needs an ID")
            result.append(str(place["id"]))
        return result

    @staticmethod
    def _location_label(columns: Mapping[str, Any], index: int, places: list[str]) -> str:
        values = columns.get("location", columns.get("place"))
        if not isinstance(values, list):
            raise ValueError("Rust output requires a place or location column")
        value = values[index]
        if isinstance(value, int):
            return places[SimulationRunService._place_index(value, len(places))]
        if isinstance(value, float) and value.is_integer():
            return places[SimulationRunService._place_index(value, len(places))]
        return str(value)

    @staticmethod
    def _agent_traits(columns: Mapping[str, Any], index: int) -> dict[str, str | float]:
        traits = columns.get("traits", {})
        dictionaries = columns.get("trait_dictionaries", {})
        if not isinstance(traits, Mapping) or not isinstance(dictionaries, Mapping):
            raise ValueError("Rust trait output must be column mappings")
        result: dict[str, str | float] = {}
        for name, raw_values in traits.items():
            if not isinstance(raw_values, list):
                raise ValueError(f"Rust trait {name} must be a column")
            value = raw_values[index]
            dictionary = dictionaries.get(name)
            if isinstance(dictionary, Mapping) and isinstance(dictionary.get("values"), list):
                labels = dictionary["values"]
                code = int(value)
                if 0 <= code < len(labels):
                    result[str(name)] = str(labels[code])
                    continue
            result[str(name)] = float(value)
        return result

    @staticmethod
    def _agent_memory(columns: Mapping[str, Any], index: int) -> dict[str, float]:
        memory = columns.get("memory", {})
        if not isinstance(memory, Mapping):
            raise ValueError("Rust memory output must be a column mapping")
        result = {}
        for name, values in memory.items():
            if not isinstance(values, list):
                raise ValueError(f"Rust memory {name} must be a column")
            result[str(name)] = float(values[index])
        return result

    @staticmethod
    def _agent_index(value: Any, population: int) -> int:
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < population:
            raise ValueError(f"Rust output references invalid agent index {value}")
        return value

    @staticmethod
    def _place_index(value: Any, place_count: int) -> int:
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < place_count:
            raise ValueError(f"Rust output references invalid place index {value}")
        return value

    @staticmethod
    def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
        if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
            raise ValueError("Rust output event collections must contain objects")
        return value

    @staticmethod
    def _list_values(value: Any) -> list[Any]:
        if not isinstance(value, list):
            raise ValueError("Rust output agent index collection must be a list")
        return value

    @staticmethod
    def _required_event_text(item: Mapping[str, Any], key: str, collection: str) -> str:
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Rust {collection} {key} must be non-empty text")
        return value

    @staticmethod
    def _canonical_json(value: Any) -> bytes:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()

    @classmethod
    def _hash(cls, value: Any) -> str:
        return hashlib.sha256(cls._canonical_json(value)).hexdigest()
