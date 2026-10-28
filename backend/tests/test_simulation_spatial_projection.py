import sqlite3
import time
from copy import deepcopy
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from petraterrium.simulation.locations import LocationPlace
from petraterrium.simulation.run_persistence import SimulationRunRecorder
from petraterrium.simulation.run_routes import create_simulation_run_router
from petraterrium.simulation.run_service import (
    PreparedRustRun,
    SimulationPlaceScope,
    SimulationRunConfig,
    SimulationRunService,
)
from petraterrium.simulation.spatial_projection import (
    project_spatial_snapshot,
    project_spatial_snapshot_series,
    query_spatial_snapshot,
)


class DailySpatialRustClient:
    def run_agents(self, request: dict) -> dict:
        start_tick = int(request.get("continuation", {}).get("completed_tick", 0))
        completed_tick = start_tick + int(request["ticks"])
        agents = deepcopy(request["agents"])
        agents["state"] = [f"day-{completed_tick}:{state}" for state in agents["state"]]
        return {
            "protocol_version": "1",
            "engine_version": "spatial-test-rust",
            "seed": request["seed"],
            "ticks": completed_tick,
            "agents": agents,
            "transition_counts": [],
            "transition_evidence": [],
            "transition_outcomes": [],
            "events": [],
            "routine_actions": [],
            "routine_unavailable": [],
            "location_transitions": [],
            "interactions": [],
            "blocked_interactions": [],
            "relationships": [],
            "state_ticks": [],
            "synchronization": [],
            "shard_populations": [],
            "continuation": {
                "completed_tick": completed_tick,
                "rng_word_position": str(completed_tick),
                "active_travel": [None] * len(agents["state"]),
                "relationships": [],
            },
        }


def spatial_prepared(config: SimulationRunConfig) -> PreparedRustRun:
    profiles = [
        {
            "agent_id": "agent-vancouver-1",
            "geography": {
                "city_id": "6173331",
                "city": "Vancouver",
                "latitude": 49.2827,
                "longitude": -123.1207,
            },
        },
        {
            "agent_id": "agent-vancouver-2",
            "geography": {
                "city_id": "6173331",
                "city": "Vancouver",
                "latitude": 49.2827,
                "longitude": -123.1207,
            },
        },
        {
            "agent_id": "agent-suva",
            "geography": {
                "city_id": "2198148",
                "city": "Suva",
                "latitude": -18.1416,
                "longitude": 178.4419,
            },
        },
        {
            "agent_id": "agent-labasa",
            "geography": {
                "city_id": "2204582",
                "city": "Labasa",
                "latitude": -16.4332,
                "longitude": -179.3707,
            },
        },
    ][: config.population_size]
    return PreparedRustRun(
        rust_request={
            "seed": config.seed,
            "ticks": 1,
            "tick_hours": config.tick_interval_hours,
            "start_hour": 0,
            "start_weekday": config.start_date.weekday(),
            "places": [{"id": "global", "state": {}}],
            "agents": {
                "agent_ids": [profile["agent_id"] for profile in profiles],
                "module": ["day"] * len(profiles),
                "state": ["active"] * len(profiles),
                "place": [0] * len(profiles),
                "traits": {},
                "trait_dictionaries": {},
                "memory": {},
            },
            "modules": [],
            "routes": [],
            "network": None,
            "schedules": [],
            "meaningful_actions": [],
            "synchronization": {},
        },
        agent_ids=[profile["agent_id"] for profile in profiles],
        data_version="spatial-fixture-v1",
        program_version="spatial-program-v1",
        initial_agent_profiles=profiles,
    )


def spatial_config(
    *, seed: int = 41, days: int = 2, tick_interval_hours: float = 24
) -> SimulationRunConfig:
    return SimulationRunConfig(
        population_size=4,
        seed=seed,
        days=days,
        tick_interval_hours=tick_interval_hours,
        start_date="2026-10-27",
        place_scope=SimulationPlaceScope(level="global"),
        agent_type_mix={"person": 1.0},
    )


def wait_for_completion(service: SimulationRunService, run_id: str):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        run = service.get(run_id)
        if run.status in {"completed", "failed", "cancelled"}:
            return run
        time.sleep(0.01)
    raise AssertionError("Spatial run did not finish")


def test_spatial_projection_is_seeded_non_address_and_filters_antimeridian():
    prepared = spatial_prepared(spatial_config())
    output = {"agents": deepcopy(prepared.rust_request["agents"])}
    first = project_spatial_snapshot(
        run_id="run-1",
        seed=41,
        day=1,
        current_date=date(2026, 10, 27),
        tick=1,
        agent_ids=prepared.agent_ids,
        profiles=prepared.initial_agent_profiles,
        output=output,
    )
    repeated = project_spatial_snapshot(
        run_id="run-1",
        seed=41,
        day=1,
        current_date=date(2026, 10, 27),
        tick=1,
        agent_ids=prepared.agent_ids,
        profiles=prepared.initial_agent_profiles,
        output=output,
    )
    changed_seed = project_spatial_snapshot(
        run_id="run-2",
        seed=42,
        day=1,
        current_date=date(2026, 10, 27),
        tick=1,
        agent_ids=prepared.agent_ids,
        profiles=prepared.initial_agent_profiles,
        output=output,
    )

    assert first == repeated
    assert first.latitudes != changed_seed.latitudes
    assert (first.latitudes[0], first.longitudes[0]) != (49.2827, -123.1207)
    assert first.agent_ids == tuple(prepared.agent_ids)
    assert first.city_ids == ("6173331", "6173331", "2198148", "2204582")

    dateline = query_spatial_snapshot(
        first,
        north=-15,
        east=-175,
        south=-20,
        west=175,
        city_ids=(),
        offset=0,
        limit=10,
    )
    assert dateline.total_in_bounds == 2
    assert {point.place_id for point in dateline.points} == {"2198148", "2204582"}

    vancouver = query_spatial_snapshot(
        first,
        north=50,
        east=-122,
        south=48,
        west=-124,
        city_ids=("6173331",),
        offset=1,
        limit=1,
    )
    assert vancouver.total_in_bounds == 2
    assert len(vancouver.points) == 1
    assert vancouver.points[0].place_id == "6173331"


def test_spatial_projection_uses_recorded_runtime_location():
    profiles = [
        {
            "agent_id": "traveller",
            "geography": {
                "country_id": "AA",
                "country": "Alpha",
                "region": "Alpha region",
                "city_id": "alpha-city",
                "city": "Alpha City",
                "latitude": 10.0,
                "longitude": 20.0,
            },
        },
        {
            "agent_id": "resident",
            "geography": {
                "country_id": "BB",
                "country": "Beta",
                "region": "Beta region",
                "city_id": "beta-city",
                "city": "Beta City",
                "latitude": 40.0,
                "longitude": 50.0,
            },
        },
    ]
    places = [
        LocationPlace(id="country-a", name="Alpha", level="country"),
        LocationPlace(
            id="region-a", name="Alpha region", level="region", parent_id="country-a"
        ),
        LocationPlace(id="city-a", name="Alpha City", level="city", parent_id="region-a"),
        LocationPlace(id="country-b", name="Beta", level="country"),
        LocationPlace(
            id="region-b", name="Beta region", level="region", parent_id="country-b"
        ),
        LocationPlace(id="city-b", name="Beta City", level="city", parent_id="region-b"),
    ]
    snapshot = project_spatial_snapshot(
        run_id="runtime-place-run",
        seed=9,
        day=1,
        current_date=date(2026, 10, 27),
        tick=1,
        agent_ids=("traveller", "resident"),
        profiles=profiles,
        output={"agents": {"state": ["active", "active"], "place": [1, 1]}},
        location_places=places,
        initial_location_ids=("city-a", "city-b"),
        runtime_place_location_ids=("city-a", "city-b"),
    )

    assert snapshot.city_ids == ("beta-city", "beta-city")
    assert all(latitude > 39 for latitude in snapshot.latitudes)
    assert all(longitude > 49 for longitude in snapshot.longitudes)


def test_spatial_series_replays_recorded_state_and_location_each_tick():
    profiles = [
        {
            "agent_id": "traveller",
            "geography": {
                "country_id": "AA",
                "country": "Alpha",
                "region": "Alpha region",
                "city_id": "alpha-city",
                "city": "Alpha City",
                "latitude": 10.0,
                "longitude": 20.0,
            },
        },
        {
            "agent_id": "resident",
            "geography": {
                "country_id": "BB",
                "country": "Beta",
                "region": "Beta region",
                "city_id": "beta-city",
                "city": "Beta City",
                "latitude": 40.0,
                "longitude": 50.0,
            },
        },
    ]
    places = [
        LocationPlace(id="country-a", name="Alpha", level="country"),
        LocationPlace(
            id="region-a", name="Alpha region", level="region", parent_id="country-a"
        ),
        LocationPlace(id="city-a", name="Alpha City", level="city", parent_id="region-a"),
        LocationPlace(id="country-b", name="Beta", level="country"),
        LocationPlace(
            id="region-b", name="Beta region", level="region", parent_id="country-b"
        ),
        LocationPlace(id="city-b", name="Beta City", level="city", parent_id="region-b"),
    ]
    series = project_spatial_snapshot_series(
        run_id="tick-series",
        seed=7,
        day=1,
        current_date=date(2026, 10, 27),
        start_tick=0,
        end_tick=2,
        agent_ids=("traveller", "resident"),
        profiles=profiles,
        initial_agents={
            "module": ["day", "day"],
            "state": ["home", "home"],
            "place": [0, 1],
        },
        output={
            "agents": {
                "module": ["day", "day"],
                "state": ["away", "home"],
                "place": [1, 1],
            },
            "transition_outcomes": [
                {
                    "tick": 1,
                    "agent_index": 0,
                    "module": "day",
                    "to_state": "away",
                }
            ],
            "location_transitions": [
                {"tick": 2, "agent_index": 0, "to_place_index": 1}
            ],
        },
        modules=({"id": "day", "entry_state": "home"},),
        routes=(),
        location_places=places,
        initial_location_ids=("city-a", "city-b"),
        runtime_place_location_ids=("city-a", "city-b"),
    )

    assert [snapshot.tick for snapshot in series.snapshots] == [1, 2]
    assert series.snapshots[0].states == ("away", "home")
    assert series.snapshots[0].city_ids == ("alpha-city", "beta-city")
    assert series.snapshots[1].states == ("away", "home")
    assert series.snapshots[1].city_ids == ("beta-city", "beta-city")


def test_spatial_snapshots_are_one_blob_per_day_and_survive_restart(tmp_path):
    path = tmp_path / "runs.sqlite3"
    recorder = SimulationRunRecorder(path)
    first_service = SimulationRunService(
        spatial_prepared,
        DailySpatialRustClient(),
        persistence=recorder,
    )
    launched = first_service.launch(spatial_config())
    completed = wait_for_completion(first_service, launched.run_id)
    assert completed.status == "completed", completed.error

    first_page = first_service.spatial_points(
        launched.run_id,
        day=2,
        tick=2,
        north=50,
        east=-122,
        south=48,
        west=-124,
        city_ids=("6173331",),
        offset=0,
        limit=1,
    )
    assert first_page.total_in_bounds == 2
    assert len(first_page.points) == 1
    assert all(point.state == "day-2:day-1:active" for point in first_page.points)
    first_service.shutdown()

    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            "SELECT day, tick, length(payload) FROM simulation_run_spatial_snapshots "
            "WHERE run_id = ? ORDER BY day",
            (launched.run_id,),
        ).fetchall()
    assert [row[:2] for row in rows] == [(1, 1), (2, 2)]
    assert all(row[2] > 0 for row in rows)

    restored = SimulationRunService(
        spatial_prepared,
        DailySpatialRustClient(),
        persistence=SimulationRunRecorder(path),
    )
    application = FastAPI()
    application.include_router(create_simulation_run_router(restored), prefix="/api")
    client = TestClient(application)
    response = client.get(
        f"/api/simulation/runs/{launched.run_id}/spatial-points",
        params={
            "day": 2,
            "tick": 2,
            "detail_level": "city",
            "north": 50,
            "east": -122,
            "south": 48,
            "west": -124,
            "city_id": "6173331",
            "offset": 0,
            "limit": 10,
        },
    )
    assert response.status_code == 200
    assert response.json()["total_in_bounds"] == 2
    assert {point["agent_id"] for point in response.json()["points"]} == {
        "agent-vancouver-1",
        "agent-vancouver-2",
    }
    assert all(point["place_id"] == "6173331" for point in response.json()["points"])
    assert (
        client.get(
            f"/api/simulation/runs/{launched.run_id}/spatial-points",
            params={
                "day": 2,
                "tick": 2,
                "detail_level": "city",
                "north": 48,
                "east": -122,
                "south": 50,
                "west": -124,
            },
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/api/simulation/runs/{launched.run_id}/spatial-points",
            params={
                "day": 2,
                "tick": 1,
                "detail_level": "city",
                "north": 50,
                "east": -122,
                "south": 48,
                "west": -124,
            },
        ).status_code
        == 409
    )
    restored.shutdown()


def test_spatial_blob_exposes_every_recorded_tick(tmp_path):
    service = SimulationRunService(
        spatial_prepared,
        DailySpatialRustClient(),
        persistence=SimulationRunRecorder(tmp_path / "runs.sqlite3"),
    )
    launched = service.launch(spatial_config(days=1, tick_interval_hours=12))
    completed = wait_for_completion(service, launched.run_id)
    assert completed.status == "completed", completed.error

    for tick in (1, 2):
        page = service.spatial_points(
            launched.run_id,
            day=1,
            tick=tick,
            north=90,
            east=180,
            south=-90,
            west=-180,
            limit=10,
        )
        assert page.total_in_bounds == 4

    with pytest.raises(RuntimeError, match="no recorded spatial snapshot at tick 3"):
        service.spatial_points(
            launched.run_id,
            day=1,
            tick=3,
            north=90,
            east=180,
            south=-90,
            west=-180,
        )
    service.shutdown()


def test_spatial_query_rejects_unbounded_pagination():
    prepared = spatial_prepared(spatial_config())
    output = {"agents": deepcopy(prepared.rust_request["agents"])}
    snapshot = project_spatial_snapshot(
        run_id="run-1",
        seed=41,
        day=1,
        current_date=date(2026, 10, 27),
        tick=1,
        agent_ids=prepared.agent_ids,
        profiles=prepared.initial_agent_profiles,
        output=output,
    )

    with pytest.raises(ValueError, match="limit"):
        query_spatial_snapshot(
            snapshot,
            north=90,
            east=180,
            south=-90,
            west=-180,
            city_ids=(),
            offset=0,
            limit=50_001,
        )
