from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from math import isclose
from threading import RLock
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

LocationLevel = Literal[
    "country",
    "region",
    "state",
    "city",
    "district",
    "building",
    "room",
]
LocationEvidenceStatus = Literal["measured", "user_defined"]

PARENT_LEVELS: dict[str, frozenset[str]] = {
    "region": frozenset({"country"}),
    "state": frozenset({"country"}),
    "city": frozenset({"region", "state"}),
    "district": frozenset({"city"}),
    "building": frozenset({"district"}),
    "room": frozenset({"building"}),
}


class LocationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class LocationEvidence(LocationModel):
    source_title: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    source_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    licence: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    status: LocationEvidenceStatus
    uncertainty: float = Field(ge=0, le=1)


class LocationDecisionTreeAvailability(LocationModel):
    tree_id: str = Field(min_length=1)
    tree_name: str = Field(min_length=1)
    available: bool
    required_place_kinds: tuple[str, ...] = Field(min_length=1)
    reason: str | None = None

    @model_validator(mode="after")
    def availability_reason(self):
        if self.available and self.reason is not None:
            raise ValueError("Available decision trees cannot have an unavailable reason")
        if not self.available and self.reason is None:
            raise ValueError("Unavailable decision trees require a reason")
        return self


class LocationPlace(LocationModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    level: LocationLevel
    parent_id: str | None = None
    accepts_arrivals: bool = True
    allows_in_person: bool = True
    capacity: int | None = Field(default=None, ge=1)
    state: dict[str, float] = Field(default_factory=dict)
    evidence: LocationEvidence | None = None
    decision_trees: tuple[LocationDecisionTreeAvailability, ...] = ()

    @model_validator(mode="after")
    def root_parent(self):
        if self.level == "country" and self.parent_id is not None:
            raise ValueError("Countries cannot have a parent location")
        if self.level != "country" and self.parent_id is None:
            raise ValueError(f"{self.level} locations require a parent")
        return self


class AgentLocationColumns(LocationModel):
    agent_ids: tuple[str, ...] = Field(min_length=1)
    current_location_ids: tuple[str, ...]

    @model_validator(mode="after")
    def aligned_columns(self):
        if len(self.agent_ids) != len(self.current_location_ids):
            raise ValueError("Agent ids and current location ids must have equal lengths")
        if len(set(self.agent_ids)) != len(self.agent_ids):
            raise ValueError("Agent ids must be unique")
        return self


class LocationMovement(LocationModel):
    agent_id: str = Field(min_length=1)
    destination_location_id: str = Field(min_length=1)
    expected_parent_id: str | None


class LocationHistoryRecord(LocationModel):
    tick: int = Field(ge=0)
    agent_id: str = Field(min_length=1)
    from_location_id: str = Field(min_length=1)
    to_location_id: str = Field(min_length=1)
    route_location_ids: tuple[str, ...] = Field(min_length=2)


class AppliedLocationMovement(LocationHistoryRecord):
    pass


class LocationLivePlaceState(LocationModel):
    runtime_place_index: int = Field(ge=0)
    runtime_place_id: str = Field(min_length=1)
    location_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    accepts_arrivals: bool
    allows_in_person: bool
    capacity: int | None = Field(default=None, ge=1)
    occupancy: int = Field(ge=0)
    crowd_density: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    state: dict[str, float]

    @model_validator(mode="after")
    def coherent_live_state(self):
        occupancy = self.state.get("occupancy")
        if occupancy is None or not isclose(
            occupancy, float(self.occupancy), rel_tol=0, abs_tol=1e-12
        ):
            raise ValueError("Live place state occupancy must match its occupancy field")
        state_density = self.state.get("crowd_density")
        if self.capacity is None:
            if self.crowd_density is not None or state_density is not None:
                raise ValueError("Unbounded live places cannot report crowd density")
            return self
        expected = self.occupancy / self.capacity
        if self.crowd_density is None or not isclose(
            self.crowd_density, expected, rel_tol=0, abs_tol=1e-12
        ):
            raise ValueError("Live place crowd density must equal occupancy divided by capacity")
        if state_density is None or not isclose(
            state_density, expected, rel_tol=0, abs_tol=1e-12
        ):
            raise ValueError("Live place state crowd density must match its density field")
        return self


class LocationRuntimeState(LocationModel):
    agents: AgentLocationColumns
    history: tuple[LocationHistoryRecord, ...] = ()
    live_places: tuple[LocationLivePlaceState, ...] = ()


class LocationStepResult(LocationModel):
    state: LocationRuntimeState
    movements: tuple[AppliedLocationMovement, ...]
    co_located_agent_ids: dict[str, tuple[str, ...]]
    effective_place_state: dict[str, dict[str, float]]


class LocationPlaceSummary(LocationModel):
    id: str
    name: str
    level: LocationLevel
    parent_id: str | None
    child_ids: tuple[str, ...]
    current_agent_count: int = Field(ge=0)
    accepts_arrivals: bool
    allows_in_person: bool
    capacity: int | None
    state: dict[str, float]
    state_source: Literal["rust_numeric_core", "location_registry"] = "location_registry"
    runtime_place_id: str | None = None
    runtime_place_kind: str | None = None
    evidence: LocationEvidence | None
    decision_trees: tuple[LocationDecisionTreeAvailability, ...]


class LocationAgentSummary(LocationModel):
    agent_id: str
    current_location_id: str


class LocationRunSnapshot(LocationModel):
    run_id: str
    tick: int = Field(ge=0)
    root_location_ids: tuple[str, ...]
    places: tuple[LocationPlaceSummary, ...]
    agents: tuple[LocationAgentSummary, ...]


class LocationAgentDetail(LocationModel):
    agent_id: str
    current_location: LocationPlaceSummary
    ancestry: tuple[LocationPlaceSummary, ...]
    history: tuple[LocationHistoryRecord, ...]
    co_located_agents: tuple[LocationAgentSummary, ...]
    elsewhere_agents: tuple[LocationAgentSummary, ...]
    effective_place_state: dict[str, float]


class LocationRegistry:
    def __init__(self, places: Sequence[LocationPlace]):
        self.places = tuple(places)
        self.by_id = {place.id: place for place in self.places}
        if not self.places:
            raise ValueError("At least one location is required")
        if len(self.by_id) != len(self.places):
            raise ValueError("Location ids must be unique")
        self._validate_hierarchy()
        children: dict[str, list[str]] = {place.id: [] for place in self.places}
        for place in self.places:
            if place.parent_id:
                children[place.parent_id].append(place.id)
        self.children = {
            place_id: tuple(sorted(child_ids))
            for place_id, child_ids in children.items()
        }

    def _validate_hierarchy(self) -> None:
        for place in self.places:
            if place.level == "country":
                continue
            parent = self.by_id.get(place.parent_id or "")
            if parent is None:
                raise ValueError(
                    f"Location {place.id!r} references unknown parent {place.parent_id!r}"
                )
            if parent.level not in PARENT_LEVELS[place.level]:
                raise ValueError(
                    f"Location {place.id!r} at level {place.level!r} cannot have "
                    f"parent {parent.id!r} at level {parent.level!r}"
                )

    def place(self, place_id: str) -> LocationPlace:
        try:
            return self.by_id[place_id]
        except KeyError as error:
            raise KeyError(f"Unknown location {place_id}") from error

    def ancestry(self, place_id: str) -> tuple[LocationPlace, ...]:
        ancestry = [self.place(place_id)]
        while ancestry[-1].parent_id:
            ancestry.append(self.place(ancestry[-1].parent_id or ""))
        return tuple(reversed(ancestry))

    def travel_route(self, source_id: str, destination_id: str) -> tuple[str, ...]:
        source = tuple(reversed(self.ancestry(source_id)))
        destination = tuple(reversed(self.ancestry(destination_id)))
        destination_positions = {
            place.id: position for position, place in enumerate(destination)
        }
        shared_parent = next(
            (
                (source_position, destination_positions[place.id])
                for source_position, place in enumerate(source)
                if place.id in destination_positions
            ),
            None,
        )
        if shared_parent is None:
            source_path = source
            destination_path = destination
        else:
            source_common, destination_common = shared_parent
            source_path = source[: source_common + 1]
            destination_path = destination[:destination_common]
        return tuple(
            [place.id for place in source_path]
            + [place.id for place in reversed(destination_path)]
        )

    def effective_state(self, place_id: str) -> dict[str, float]:
        state: dict[str, float] = {}
        for place in self.ancestry(place_id):
            state.update(place.state)
        return state


def _current_locations(state: LocationRuntimeState) -> dict[str, str]:
    return dict(zip(state.agents.agent_ids, state.agents.current_location_ids, strict=True))


def _validate_runtime_state(
    registry: LocationRegistry,
    state: LocationRuntimeState,
) -> None:
    for agent_id, place_id in _current_locations(state).items():
        if place_id not in registry.by_id:
            raise ValueError(f"Agent {agent_id!r} references unknown location {place_id!r}")
    if not state.live_places:
        return
    location_ids = [place.location_id for place in state.live_places]
    runtime_indices = [place.runtime_place_index for place in state.live_places]
    runtime_ids = [place.runtime_place_id for place in state.live_places]
    if len(set(location_ids)) != len(location_ids):
        raise ValueError("Live place states must map to unique hierarchy locations")
    if len(set(runtime_indices)) != len(runtime_indices):
        raise ValueError("Live place state indices must be unique")
    if len(set(runtime_ids)) != len(runtime_ids):
        raise ValueError("Live place state ids must be unique")
    current_occupancy = Counter(_current_locations(state).values())
    for place in state.live_places:
        if place.location_id not in registry.by_id:
            raise ValueError(
                f"Live place {place.runtime_place_id!r} maps to unknown location "
                f"{place.location_id!r}"
            )
        if current_occupancy[place.location_id] != place.occupancy:
            raise ValueError(
                f"Live place {place.runtime_place_id!r} occupancy does not match agent locations"
            )
    if sum(place.occupancy for place in state.live_places) != len(state.agents.agent_ids):
        raise ValueError("Live place occupancies must cover every agent")


def co_located_agent_ids(
    registry: LocationRegistry,
    state: LocationRuntimeState,
) -> dict[str, tuple[str, ...]]:
    _validate_runtime_state(registry, state)
    occupants: dict[str, list[str]] = {place.id: [] for place in registry.places}
    for agent_id, place_id in _current_locations(state).items():
        occupants[place_id].append(agent_id)
    result: dict[str, tuple[str, ...]] = {}
    for agent_id, place_id in _current_locations(state).items():
        if not registry.place(place_id).allows_in_person:
            result[agent_id] = ()
            continue
        result[agent_id] = tuple(
            other_id for other_id in occupants[place_id] if other_id != agent_id
        )
    return result


def face_to_face_allowed(
    registry: LocationRegistry,
    state: LocationRuntimeState,
    first_agent_id: str,
    second_agent_id: str,
) -> bool:
    current = _current_locations(state)
    if first_agent_id not in current or second_agent_id not in current:
        raise KeyError("Face-to-face participants must exist in the location state")
    place_id = current[first_agent_id]
    return (
        first_agent_id != second_agent_id
        and place_id == current[second_agent_id]
        and registry.place(place_id).allows_in_person
    )


def apply_movements(
    registry: LocationRegistry,
    state: LocationRuntimeState,
    tick: int,
    movements: Sequence[LocationMovement],
) -> LocationStepResult:
    if tick < 0:
        raise ValueError("Movement tick cannot be negative")
    _validate_runtime_state(registry, state)
    current = _current_locations(state)
    movement_agents = [movement.agent_id for movement in movements]
    if len(set(movement_agents)) != len(movement_agents):
        raise ValueError("An agent can move at most once per tick")
    events: list[AppliedLocationMovement] = []
    next_locations = dict(current)
    for movement in movements:
        if movement.agent_id not in current:
            raise ValueError(f"Unknown moving agent {movement.agent_id!r}")
        destination = registry.place(movement.destination_location_id)
        if not destination.accepts_arrivals:
            raise ValueError(f"Location {destination.id!r} does not accept arrivals")
        if movement.expected_parent_id != destination.parent_id:
            raise ValueError(
                f"Location {destination.id!r} parent is {destination.parent_id!r}, "
                f"not {movement.expected_parent_id!r}"
            )
        source_id = current[movement.agent_id]
        if source_id == destination.id:
            raise ValueError(f"Agent {movement.agent_id!r} is already at {destination.id!r}")
        route = registry.travel_route(source_id, destination.id)
        events.append(
            AppliedLocationMovement(
                tick=tick,
                agent_id=movement.agent_id,
                from_location_id=source_id,
                to_location_id=destination.id,
                route_location_ids=route,
            )
        )
        next_locations[movement.agent_id] = destination.id
    occupancy = Counter(next_locations.values())
    for place in registry.places:
        if place.capacity is not None and occupancy[place.id] > place.capacity:
            raise ValueError(
                f"Location {place.id!r} capacity {place.capacity} would be exceeded by "
                f"occupancy {occupancy[place.id]}"
            )
    next_state = LocationRuntimeState(
        agents=AgentLocationColumns(
            agent_ids=state.agents.agent_ids,
            current_location_ids=tuple(
                next_locations[agent_id] for agent_id in state.agents.agent_ids
            ),
        ),
        history=state.history + tuple(events),
    )
    return LocationStepResult(
        state=next_state,
        movements=tuple(events),
        co_located_agent_ids=co_located_agent_ids(registry, next_state),
        effective_place_state={
            agent_id: registry.effective_state(next_locations[agent_id])
            for agent_id in state.agents.agent_ids
        },
    )


class LocationRunCatalog:
    def __init__(
        self,
        run_id: str,
        tick: int,
        registry: LocationRegistry,
        state: LocationRuntimeState,
    ):
        if tick < 0:
            raise ValueError("Location run tick cannot be negative")
        _validate_runtime_state(registry, state)
        self.run_id = run_id
        self.tick = tick
        self.registry = registry
        self.state = state
        self._current = _current_locations(state)
        self._co_located = co_located_agent_ids(registry, state)
        occupancy = Counter(self._current.values())
        live_by_location = {place.location_id: place for place in state.live_places}
        self._summaries = {
            place.id: LocationPlaceSummary(
                **(
                    place.model_dump()
                    | {
                        "accepts_arrivals": live.accepts_arrivals,
                        "allows_in_person": live.allows_in_person,
                        "capacity": live.capacity,
                        "state": live.state,
                        "state_source": "rust_numeric_core",
                        "runtime_place_id": live.runtime_place_id,
                        "runtime_place_kind": live.kind,
                    }
                    if (live := live_by_location.get(place.id)) is not None
                    else place.model_dump()
                ),
                child_ids=registry.children[place.id],
                current_agent_count=(
                    live_by_location[place.id].occupancy
                    if place.id in live_by_location
                    else occupancy[place.id]
                ),
            )
            for place in registry.places
        }

    def snapshot(self) -> LocationRunSnapshot:
        agents = tuple(
            LocationAgentSummary(
                agent_id=agent_id,
                current_location_id=place_id,
            )
            for agent_id, place_id in self._current.items()
        )
        return LocationRunSnapshot(
            run_id=self.run_id,
            tick=self.tick,
            root_location_ids=tuple(
                place.id for place in self.registry.places if place.parent_id is None
            ),
            places=tuple(self._summaries[place.id] for place in self.registry.places),
            agents=agents,
        )

    def agent_detail(self, agent_id: str) -> LocationAgentDetail:
        try:
            place_id = self._current[agent_id]
        except KeyError as error:
            raise KeyError(f"Unknown location agent {agent_id}") from error
        co_located = tuple(
            LocationAgentSummary(
                agent_id=other_id,
                current_location_id=self._current[other_id],
            )
            for other_id in self._co_located[agent_id]
        )
        elsewhere = tuple(
            LocationAgentSummary(
                agent_id=other_id,
                current_location_id=other_place_id,
            )
            for other_id, other_place_id in self._current.items()
            if other_id != agent_id and other_place_id != place_id
        )
        return LocationAgentDetail(
            agent_id=agent_id,
            current_location=self._summaries[place_id],
            ancestry=tuple(
                self._summaries[place.id]
                for place in self.registry.ancestry(place_id)
            ),
            history=tuple(
                record for record in self.state.history if record.agent_id == agent_id
            ),
            co_located_agents=co_located,
            elsewhere_agents=elsewhere,
            effective_place_state=self._effective_place_state(place_id),
        )

    def _effective_place_state(self, place_id: str) -> dict[str, float]:
        state: dict[str, float] = {}
        for place in self.registry.ancestry(place_id):
            state.update(self._summaries[place.id].state)
        return state


class LocationRunRegistry:
    def __init__(self):
        self._catalogs: dict[str, LocationRunCatalog] = {}
        self._loaders: dict[str, Callable[[], LocationRunCatalog]] = {}
        self._lock = RLock()

    def record(
        self,
        run_id: str,
        tick: int,
        places: Sequence[LocationPlace],
        state: LocationRuntimeState,
    ) -> LocationRunCatalog:
        catalog = LocationRunCatalog(
            run_id,
            tick,
            LocationRegistry(places),
            state,
        )
        with self._lock:
            self._catalogs[run_id] = catalog
            self._loaders.pop(run_id, None)
        return catalog

    def register_loader(
        self,
        run_id: str,
        loader: Callable[[], LocationRunCatalog],
    ) -> None:
        with self._lock:
            if run_id not in self._catalogs:
                self._loaders[run_id] = loader

    def catalog(self, run_id: str) -> LocationRunCatalog:
        with self._lock:
            catalog = self._catalogs.get(run_id)
            if catalog is not None:
                return catalog
            loader = self._loaders.get(run_id)
            if loader is not None:
                return loader()
        raise KeyError(f"No locations recorded for run {run_id}")

    def discard(self, run_id: str) -> None:
        with self._lock:
            self._catalogs.pop(run_id, None)
            self._loaders.pop(run_id, None)


def create_location_router(registry: LocationRunRegistry) -> APIRouter:
    router = APIRouter(prefix="/simulation/runs", tags=["simulation-locations"])

    @router.get("/{run_id}/locations", response_model=LocationRunSnapshot)
    def location_snapshot(run_id: str) -> LocationRunSnapshot:
        try:
            return registry.catalog(run_id).snapshot()
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get(
        "/{run_id}/locations/agents/{agent_id}", response_model=LocationAgentDetail
    )
    def agent_location_detail(run_id: str, agent_id: str) -> LocationAgentDetail:
        try:
            return registry.catalog(run_id).agent_detail(agent_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    return router
