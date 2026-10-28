from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .locations import LocationPlace
from .runtime_geography import resolve_runtime_agent_geographies

SPATIAL_SNAPSHOT_VERSION = "spatial-projection-v1"
MAX_SPATIAL_QUERY_LIMIT = 50_000
MAX_SPATIAL_CITY_FILTERS = 1_000
EARTH_KILOMETRES_PER_DEGREE = 111.32
MINIMUM_JITTER_KILOMETRES = 0.35
JITTER_RANGE_KILOMETRES = 0.9


class SpatialProjectionModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class SpatialSnapshot(SpatialProjectionModel):
    version: str = SPATIAL_SNAPSHOT_VERSION
    run_id: str = Field(min_length=1)
    day: int = Field(ge=1)
    date: date
    tick: int = Field(ge=1)
    agent_ids: tuple[str, ...]
    states: tuple[str, ...]
    city_ids: tuple[str, ...]
    latitudes: tuple[float, ...]
    longitudes: tuple[float, ...]

    @model_validator(mode="after")
    def aligned_columns(self):
        lengths = {
            len(self.agent_ids),
            len(self.states),
            len(self.city_ids),
            len(self.latitudes),
            len(self.longitudes),
        }
        if len(lengths) != 1:
            raise ValueError("Spatial snapshot columns must have equal lengths")
        if len(set(self.agent_ids)) != len(self.agent_ids):
            raise ValueError("Spatial snapshot agent IDs must be unique")
        if any(not value for value in (*self.agent_ids, *self.states, *self.city_ids)):
            raise ValueError("Spatial snapshot identity columns cannot be empty")
        if any(not math.isfinite(value) or value < -90 or value > 90 for value in self.latitudes):
            raise ValueError("Spatial snapshot latitudes must be finite and valid")
        if any(
            not math.isfinite(value) or value < -180 or value > 180 for value in self.longitudes
        ):
            raise ValueError("Spatial snapshot longitudes must be finite and valid")
        return self


class SpatialSnapshotSeries(SpatialProjectionModel):
    version: str = SPATIAL_SNAPSHOT_VERSION
    run_id: str = Field(min_length=1)
    day: int = Field(ge=1)
    date: date
    tick: int = Field(ge=1)
    snapshots: tuple[SpatialSnapshot, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def coherent_series(self):
        ticks = [snapshot.tick for snapshot in self.snapshots]
        if ticks != sorted(set(ticks)):
            raise ValueError("Spatial snapshot series ticks must be unique and increasing")
        if ticks[-1] != self.tick:
            raise ValueError("Spatial snapshot series final tick must match its tick")
        if any(
            snapshot.run_id != self.run_id
            or snapshot.day != self.day
            or snapshot.date != self.date
            for snapshot in self.snapshots
        ):
            raise ValueError("Spatial snapshot series identities must match every snapshot")
        return self

    def at_tick(self, tick: int) -> SpatialSnapshot | None:
        return next((snapshot for snapshot in self.snapshots if snapshot.tick == tick), None)


class SpatialPoint(SpatialProjectionModel):
    agent_id: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    state: str = Field(min_length=1)
    place_id: str = Field(min_length=1)


class SpatialPointPage(SpatialProjectionModel):
    points: tuple[SpatialPoint, ...]
    total_in_bounds: int = Field(ge=0)


def project_spatial_snapshot(
    *,
    run_id: str,
    seed: int,
    day: int,
    current_date: date,
    tick: int,
    agent_ids: Sequence[str],
    profiles: Sequence[Mapping[str, Any]],
    output: Mapping[str, Any],
    location_places: Sequence[LocationPlace] = (),
    initial_location_ids: Sequence[str] = (),
    runtime_place_location_ids: Sequence[str] = (),
) -> SpatialSnapshot:
    agents = output.get("agents")
    if not isinstance(agents, Mapping):
        raise ValueError("Rust spatial snapshot is missing agent columns")
    raw_states = agents.get("state")
    if not isinstance(raw_states, Sequence) or isinstance(raw_states, (str, bytes)):
        raise ValueError("Rust spatial snapshot states must be a sequence")
    if len(raw_states) != len(agent_ids):
        raise ValueError("Rust spatial snapshot states must match the prepared population")
    if profiles and len(profiles) != len(agent_ids):
        raise ValueError("Spatial profiles must match the prepared population")

    geographies = resolve_runtime_agent_geographies(
        profiles=profiles,
        output=output,
        location_places=location_places,
        initial_location_ids=initial_location_ids,
        runtime_place_location_ids=runtime_place_location_ids,
    )

    projected_agent_ids: list[str] = []
    states: list[str] = []
    city_ids: list[str] = []
    latitudes: list[float] = []
    longitudes: list[float] = []
    for index, geography in enumerate(geographies):
        latitude = geography.latitude
        longitude = geography.longitude
        city_id = geography.city_id or geography.location_id
        state = str(raw_states[index]).strip()
        agent_id = str(agent_ids[index]).strip()
        if latitude is None or longitude is None or city_id is None or not state or not agent_id:
            continue
        projected_latitude, projected_longitude = _non_address_coordinate(
            seed=seed,
            agent_id=agent_id,
            city_id=city_id,
            latitude=latitude,
            longitude=longitude,
        )
        projected_agent_ids.append(agent_id)
        states.append(state)
        city_ids.append(city_id)
        latitudes.append(projected_latitude)
        longitudes.append(projected_longitude)
    return SpatialSnapshot(
        run_id=run_id,
        day=day,
        date=current_date,
        tick=tick,
        agent_ids=tuple(projected_agent_ids),
        states=tuple(states),
        city_ids=tuple(city_ids),
        latitudes=tuple(latitudes),
        longitudes=tuple(longitudes),
    )


def project_spatial_snapshot_series(
    *,
    run_id: str,
    seed: int,
    day: int,
    current_date: date,
    start_tick: int,
    end_tick: int,
    agent_ids: Sequence[str],
    profiles: Sequence[Mapping[str, Any]],
    initial_agents: Mapping[str, Any],
    output: Mapping[str, Any],
    modules: Sequence[Mapping[str, Any]] = (),
    routes: Sequence[Mapping[str, Any]] = (),
    location_places: Sequence[LocationPlace] = (),
    initial_location_ids: Sequence[str] = (),
    runtime_place_location_ids: Sequence[str] = (),
) -> SpatialSnapshotSeries:
    if start_tick < 0 or end_tick <= start_tick:
        raise ValueError("Spatial snapshot series requires an increasing tick range")
    states = _text_column(initial_agents, "state", len(agent_ids))
    agent_modules = _text_column(initial_agents, "module", len(agent_ids))
    places = _integer_column(initial_agents, "place", len(agent_ids))
    final_agents = output.get("agents")
    if not isinstance(final_agents, Mapping):
        raise ValueError("Spatial snapshot series requires final agent columns")
    final_states = _text_column(final_agents, "state", len(agent_ids))
    final_places = _integer_column(final_agents, "place", len(agent_ids))
    entry_states = {
        str(module.get("id", "")): str(module.get("entry_state", ""))
        for module in modules
        if str(module.get("id", "")) and str(module.get("entry_state", ""))
    }
    route_targets = {
        (str(route.get("from_module", "")), str(route.get("exit_state", ""))): str(
            route.get("to_module", "")
        )
        for route in routes
    }
    outcomes_by_tick = _rows_by_tick(output.get("transition_outcomes", []))
    locations_by_tick = _rows_by_tick(output.get("location_transitions", []))
    snapshots: list[SpatialSnapshot] = []
    for tick in range(start_tick + 1, end_tick + 1):
        for outcome in outcomes_by_tick.get(tick, ()):
            agent_index = _agent_index(outcome.get("agent_index"), len(agent_ids))
            source_module = str(outcome.get("module", agent_modules[agent_index]))
            to_state = str(outcome.get("to_state", "")).strip()
            if not to_state:
                raise ValueError("Spatial transition outcome requires a destination state")
            target_module = route_targets.get((source_module, to_state))
            if target_module is None:
                agent_modules[agent_index] = source_module
                states[agent_index] = to_state
            else:
                entry_state = entry_states.get(target_module)
                if entry_state is None:
                    raise ValueError(
                        f"Spatial route target {target_module!r} has no prepared entry state"
                    )
                agent_modules[agent_index] = target_module
                states[agent_index] = entry_state
        for transition in locations_by_tick.get(tick, ()):
            agent_index = _agent_index(transition.get("agent_index"), len(agent_ids))
            destination = transition.get("to_place_index")
            if isinstance(destination, bool) or not isinstance(destination, int):
                raise ValueError("Spatial location transition requires an integer destination")
            places[agent_index] = destination
        if tick == end_tick:
            states = final_states
            places = final_places
        snapshots.append(
            project_spatial_snapshot(
                run_id=run_id,
                seed=seed,
                day=day,
                current_date=current_date,
                tick=tick,
                agent_ids=agent_ids,
                profiles=profiles,
                output={"agents": {"state": states, "place": places}},
                location_places=location_places,
                initial_location_ids=initial_location_ids,
                runtime_place_location_ids=runtime_place_location_ids,
            )
        )
    return SpatialSnapshotSeries(
        run_id=run_id,
        day=day,
        date=current_date,
        tick=end_tick,
        snapshots=tuple(snapshots),
    )


def query_spatial_snapshot(
    snapshot: SpatialSnapshot,
    *,
    north: float,
    east: float,
    south: float,
    west: float,
    city_ids: Sequence[str],
    offset: int,
    limit: int,
) -> SpatialPointPage:
    _validate_bounds(north=north, east=east, south=south, west=west)
    if offset < 0:
        raise ValueError("Spatial query offset cannot be negative")
    if limit < 1 or limit > MAX_SPATIAL_QUERY_LIMIT:
        raise ValueError(f"Spatial query limit must be between 1 and {MAX_SPATIAL_QUERY_LIMIT}")
    normalized_city_ids = tuple(dict.fromkeys(value.strip() for value in city_ids if value.strip()))
    if len(normalized_city_ids) > MAX_SPATIAL_CITY_FILTERS:
        raise ValueError(f"Spatial query accepts at most {MAX_SPATIAL_CITY_FILTERS} city filters")
    city_filter = set(normalized_city_ids)
    selected: list[SpatialPoint] = []
    total = 0
    end = offset + limit
    for agent_id, state, city_id, latitude, longitude in zip(
        snapshot.agent_ids,
        snapshot.states,
        snapshot.city_ids,
        snapshot.latitudes,
        snapshot.longitudes,
        strict=True,
    ):
        if city_filter and city_id not in city_filter:
            continue
        if latitude < south or latitude > north:
            continue
        longitude_inside = (
            west <= longitude <= east if west <= east else longitude >= west or longitude <= east
        )
        if not longitude_inside:
            continue
        if offset <= total < end:
            selected.append(
                SpatialPoint(
                    agent_id=agent_id,
                    latitude=latitude,
                    longitude=longitude,
                    state=state,
                    place_id=city_id,
                )
            )
        total += 1
    return SpatialPointPage(points=tuple(selected), total_in_bounds=total)


def _non_address_coordinate(
    *,
    seed: int,
    agent_id: str,
    city_id: str,
    latitude: float,
    longitude: float,
) -> tuple[float, float]:
    digest = hashlib.sha256(f"{seed}:{agent_id}:{city_id}".encode()).digest()
    radial_unit = int.from_bytes(digest[:8], "big") / ((1 << 64) - 1)
    angular_unit = int.from_bytes(digest[8:16], "big") / ((1 << 64) - 1)
    radius = MINIMUM_JITTER_KILOMETRES + math.sqrt(radial_unit) * JITTER_RANGE_KILOMETRES
    angle = 2 * math.pi * angular_unit
    base_latitude = round(latitude, 3)
    base_longitude = round(longitude, 3)
    projected_latitude = base_latitude + math.cos(angle) * radius / EARTH_KILOMETRES_PER_DEGREE
    longitude_scale = EARTH_KILOMETRES_PER_DEGREE * max(
        abs(math.cos(math.radians(base_latitude))),
        0.1,
    )
    projected_longitude = base_longitude + math.sin(angle) * radius / longitude_scale
    bounded_latitude = min(90.0, max(-90.0, projected_latitude))
    wrapped_longitude = ((projected_longitude + 180) % 360) - 180
    return round(bounded_latitude, 6), round(wrapped_longitude, 6)


def _rows_by_tick(value: Any) -> dict[int, tuple[Mapping[str, Any], ...]]:
    if value is None:
        return {}
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("Spatial tick receipts must be a sequence")
    grouped: dict[int, list[Mapping[str, Any]]] = {}
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("Spatial tick receipts must contain objects")
        tick = item.get("tick")
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 1:
            raise ValueError("Spatial tick receipts require positive integer ticks")
        grouped.setdefault(tick, []).append(item)
    return {tick: tuple(items) for tick, items in grouped.items()}


def _text_column(agents: Mapping[str, Any], name: str, length: int) -> list[str]:
    value = agents.get(name)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != length:
        raise ValueError(f"Spatial agent column {name} must match the population")
    result = [str(item).strip() for item in value]
    if any(not item for item in result):
        raise ValueError(f"Spatial agent column {name} cannot contain empty values")
    return result


def _integer_column(agents: Mapping[str, Any], name: str, length: int) -> list[int]:
    value = agents.get(name)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != length:
        raise ValueError(f"Spatial agent column {name} must match the population")
    if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        raise ValueError(f"Spatial agent column {name} must contain integers")
    return list(value)


def _agent_index(value: Any, population: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < population:
        raise ValueError(f"Spatial receipt agent index {value!r} is invalid")
    return value


def _validate_bounds(*, north: float, east: float, south: float, west: float) -> None:
    values = (north, east, south, west)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("Spatial query bounds must be finite")
    if north < -90 or north > 90 or south < -90 or south > 90:
        raise ValueError("Spatial query latitude bounds must be between -90 and 90")
    if east < -180 or east > 180 or west < -180 or west > 180:
        raise ValueError("Spatial query longitude bounds must be between -180 and 180")
    if south > north:
        raise ValueError("Spatial query south bound cannot exceed north bound")
