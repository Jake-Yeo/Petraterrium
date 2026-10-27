import time
from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient

from petraterrium.rust_core import RustCoreClient
from petraterrium.simulation.interactions import (
    InteractionQuery,
    InteractionRunRegistry,
    create_interaction_router,
)
from petraterrium.simulation.locations import LocationPlace, LocationRunRegistry
from petraterrium.simulation.run_persistence import SimulationRunRecorder
from petraterrium.simulation.run_routes import create_simulation_run_router
from petraterrium.simulation.run_service import (
    PreparedRustRun,
    SimulationPlaceScope,
    SimulationRunConfig,
    SimulationRunService,
)
from petraterrium.simulation.runtime_decision_compiler import RuntimeDecisionCompilationError


def evidence(probability: float) -> dict:
    return {
        "conditions": [],
        "probability": probability,
        "provenance": {
            "source": "FAKE deterministic run-panel fixture",
            "version": "fixture-v1",
            "status": "present",
            "uncertainty": 0.01,
        },
    }


def prepared_run(config: SimulationRunConfig) -> PreparedRustRun:
    population = config.population_size
    return PreparedRustRun(
        rust_request={
            "seed": config.seed,
            "ticks": 1,
            "tick_hours": config.tick_interval_hours,
            "start_hour": 8,
            "start_weekday": 1,
            "places": [{"id": "Vancouver", "state": {}}],
            "agents": {
                "module": ["day"] * population,
                "state": ["choose"] * population,
                "place": [0] * population,
                "traits": {"age": [20 + index for index in range(population)]},
                "trait_dictionaries": {},
                "memory": {},
            },
            "modules": [
                {
                    "id": "day",
                    "entry_state": "choose",
                    "exit_states": ["home", "outside"],
                    "inputs": [],
                    "outputs": [],
                    "states": ["choose", "home", "outside"],
                    "transitions": [
                        {
                            "id": "stay-home",
                            "from_state": "choose",
                            "to_state": "home",
                            "rules": [evidence(0.4)],
                            "effects": [],
                        },
                        {
                            "id": "go-outside",
                            "from_state": "choose",
                            "to_state": "outside",
                            "rules": [evidence(0.6)],
                            "effects": [],
                        },
                    ],
                }
            ],
            "routes": [],
            "network": None,
            "schedules": [
                {
                    "id": "weekday",
                    "action": "commute",
                    "weekdays": [1],
                    "start_hour": 0,
                    "end_hour": 24,
                    "modules": [],
                    "states": [],
                }
            ],
            "meaningful_actions": [],
            "synchronization": {},
        },
        agent_ids=[f"agent-{index + 1}" for index in range(population)],
        agent_names=[f"Person {index + 1}" for index in range(population)],
        data_version="fixture-data-v1",
        program_version="fixture-program-v1",
    )


def run_config(**updates) -> SimulationRunConfig:
    values = {
        "population_size": 8,
        "seed": 2718,
        "days": 3,
        "tick_interval_hours": 6,
        "start_date": "2026-10-27",
        "place_scope": SimulationPlaceScope(level="city", identifier="Vancouver"),
        "agent_type_mix": {"ResidentAgent": 1.0},
    }
    values.update(updates)
    return SimulationRunConfig.model_validate(values)


def test_launch_rejects_blocked_preparation_without_queueing_a_run():
    message = (
        "Run blocked: 1 selected agent has no applicable confirmed executable decision tree: "
        "agent-1 (worker). Confirm ready decision trees with measured-joint or fitted-model "
        "evidence for every selected agent type in Simulation > Decision Trees, then run again."
    )

    def blocked_preparation(_: SimulationRunConfig) -> PreparedRustRun:
        raise RuntimeDecisionCompilationError(message)

    service = SimulationRunService(blocked_preparation, RustCoreClient())
    application = FastAPI()
    application.include_router(create_simulation_run_router(service), prefix="/api")
    client = TestClient(application, raise_server_exceptions=False)

    response = client.post(
        "/api/simulation/runs",
        json=run_config().model_dump(mode="json"),
    )

    assert response.status_code == 409
    assert response.json() == {"detail": message}
    assert service.list() == []
    service.shutdown()


def wait_for_terminal(service: SimulationRunService, run_id: str):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        run = service.get(run_id)
        if run.status in {"completed", "cancelled", "failed"}:
            return run
        time.sleep(0.02)
    raise AssertionError("Simulation run did not finish")


class LinearCheckpointRustClient:
    def __init__(self):
        self.requests: list[dict] = []

    def run_agents(self, request: dict) -> dict:
        self.requests.append(deepcopy(request))
        continuation = request.get("continuation", {})
        start_tick = int(continuation.get("completed_tick", 0))
        completed_tick = start_tick + int(request["ticks"])
        agents = deepcopy(request["agents"])
        agents["state"] = [f"checkpoint-{completed_tick}"] * len(agents["state"])
        return {
            "protocol_version": "1",
            "engine_version": "test-rust",
            "seed": request["seed"],
            "ticks": completed_tick,
            "agents": agents,
            "transition_counts": [
                {
                    "tick": completed_tick,
                    "module": "day",
                    "transition": f"checkpoint-{completed_tick}",
                    "count": len(agents["state"]),
                }
            ],
            "transition_evidence": [],
            "transition_outcomes": [],
            "events": [],
            "routine_actions": [],
            "routine_unavailable": [],
            "location_transitions": [],
            "interactions": [],
            "blocked_interactions": [],
            "relationships": [],
            "synchronization": [],
            "shard_populations": [],
            "continuation": {
                "completed_tick": completed_tick,
                "rng_word_position": str(completed_tick),
                "active_travel": [None] * len(agents["state"]),
                "relationships": [],
            },
        }


class DailyInteractionRustClient(LinearCheckpointRustClient):
    def run_agents(self, request: dict) -> dict:
        output = super().run_agents(request)
        tick = output["ticks"]
        provenance = {
            "source": "FAKE daily interaction fixture",
            "version": "fixture-v1",
            "status": "measured_joint",
            "uncertainty": 0.01,
        }
        output["interactions"] = [
            {
                "tick": tick,
                "hour": 12.0,
                "weekday": tick % 7,
                "rule_id": "daily-talk",
                "interaction_type": "talk",
                "channel": "in_person",
                "initiator_index": 0,
                "initiator_id": "agent-1",
                "target_index": 1,
                "target_id": "agent-2",
                "place_index": 0,
                "place_id": "Vancouver",
                "relationship_type": "friend",
                "relationship_weight": 0.8,
                "trust": 0.7,
                "similarity": 0.6,
                "probability": 0.5,
                "factors": [
                    {
                        "kind": "base",
                        "factor": {
                            "id": "base",
                            "label": "Base",
                            "value": 0.5,
                            "provenance": provenance,
                        },
                    },
                    {
                        "kind": "relationship",
                        "factor": {
                            "id": "friend",
                            "label": "Friend",
                            "value": 1.0,
                            "provenance": provenance,
                        },
                    },
                ],
                "state_deltas": [
                    {
                        "agent_id": "agent-1",
                        "state": "mood",
                        "before": 0.2,
                        "delta": 0.3,
                        "after": 0.5,
                    },
                    {
                        "agent_id": "agent-2",
                        "state": "mood",
                        "before": 0.4,
                        "delta": 0.1,
                        "after": 0.5,
                    },
                ],
                "relationship_deltas": [
                    {
                        "source_agent_id": "agent-1",
                        "target_agent_id": "agent-2",
                        "field": "trust",
                        "before": 0.7,
                        "delta": 0.05,
                        "after": 0.75,
                    }
                ],
                "interaction_tree": {
                    "tree_id": "daily-talk-tree",
                    "tree_version": "v2",
                    "outcome_node": "friends",
                    "outcome": "became_friends",
                    "path": [
                        {
                            "tree_id": "daily-talk-tree",
                            "node_id": "opening",
                            "transition_id": "opening-to-topic",
                            "outcome": "continue_talking",
                            "probability": 0.8,
                            "draw": 0.2,
                            "evidence": {
                                "source": "FAKE daily interaction fixture",
                                "version": "fixture-v1",
                                "status": "measured_joint",
                                "uncertainty": 0.01,
                                "source_date": "2026-01-01",
                                "evidence_id": "daily-talk-opening",
                            },
                        },
                        {
                            "tree_id": "friendship-subtree",
                            "node_id": "topic",
                            "transition_id": "topic-to-friends",
                            "outcome": "became_friends",
                            "probability": 0.6,
                            "draw": 0.3,
                            "evidence": {
                                "source": "FAKE daily interaction fixture",
                                "version": "fixture-v1",
                                "status": "measured_joint",
                                "uncertainty": 0.02,
                                "source_date": "2026-01-01",
                                "evidence_id": "daily-talk-friendship",
                            },
                        },
                    ],
                },
            }
        ]
        if tick % 2 == 0:
            output["interactions"][0].pop("interaction_tree")
        return output


def test_rust_tick_work_is_linear_and_each_chunk_becomes_one_daily_snapshot():
    rust = LinearCheckpointRustClient()
    service = SimulationRunService(prepared_run, rust)
    config = run_config(population_size=2, days=3, tick_interval_hours=6)

    launched = service.launch(config)
    completed = wait_for_terminal(service, launched.run_id)

    assert completed.status == "completed"
    assert completed.result is not None
    assert sum(int(request["ticks"]) for request in rust.requests) == config.total_ticks
    assert [
        int(request.get("continuation", {}).get("completed_tick", 0)) for request in rust.requests
    ] == [0, 4, 8]
    assert [snapshot.tick for snapshot in completed.result.snapshots] == [4, 8, 12]
    assert [list(snapshot.state_counts) for snapshot in completed.result.snapshots] == [
        ["day / checkpoint-4"],
        ["day / checkpoint-8"],
        ["day / checkpoint-12"],
    ]
    service.shutdown()


def test_chunked_interaction_catalog_matches_durable_restart(tmp_path):
    path = tmp_path / "simulation-runs.sqlite3"
    first_registry = InteractionRunRegistry()
    rust = DailyInteractionRustClient()
    first_service = SimulationRunService(
        prepared_run,
        rust,
        record_interactions=first_registry.record,
        persistence=SimulationRunRecorder(path),
    )
    first_application = FastAPI()
    first_application.include_router(create_interaction_router(first_registry), prefix="/api")
    launched = first_service.launch(run_config(population_size=2, days=2, tick_interval_hours=24))
    completed = wait_for_terminal(first_service, launched.run_id)

    assert completed.status == "completed"
    assert [request["ticks"] for request in rust.requests] == [1, 1]
    live_response = TestClient(first_application).get(
        f"/api/simulation/runs/{launched.run_id}/interactions"
    )
    assert live_response.status_code == 200
    live_catalog = live_response.json()
    assert live_catalog["total"] == 2
    assert [event["tick"] for event in live_catalog["items"]] == [2, 1]
    assert completed.result is not None
    assert [
        snapshot.model_dump()["interaction_outcome_counts"]
        for snapshot in completed.result.snapshots
    ] == [
        {"became_friends": 1},
        {"talk": 1},
    ]
    first_agent = first_service.agent(launched.run_id, "agent-1")
    second_agent = first_service.agent(launched.run_id, "agent-2")
    first_interaction = first_agent.timeline[0].model_dump()["interaction_details"][0]
    second_interaction = second_agent.timeline[0].model_dump()["interaction_details"][0]
    assert first_agent.timeline[0].interactions == ["talk"]
    assert second_agent.timeline[0].interactions == ["talk"]
    assert first_interaction["role"] == "initiator"
    assert first_interaction["other_agent_id"] == "agent-2"
    assert first_interaction["other_agent_name"] == "Person 2"
    assert first_interaction["place"] == "Vancouver"
    assert first_interaction["interaction_tree"]["outcome"] == "became_friends"
    assert [step["tree_id"] for step in first_interaction["interaction_tree"]["path"]] == [
        "daily-talk-tree",
        "friendship-subtree",
    ]
    assert first_interaction["state_deltas"] == [
        {
            "agent_id": "agent-1",
            "state": "mood",
            "before": 0.2,
            "delta": 0.3,
            "after": 0.5,
        }
    ]
    assert second_interaction["role"] == "target"
    assert second_interaction["other_agent_id"] == "agent-1"
    assert second_interaction["other_agent_name"] == "Person 1"
    assert second_interaction["state_deltas"] == [
        {
            "agent_id": "agent-2",
            "state": "mood",
            "before": 0.4,
            "delta": 0.1,
            "after": 0.5,
        }
    ]
    assert first_interaction["relationship_deltas"] == second_interaction["relationship_deltas"]
    first_service.shutdown()

    restored_registry = InteractionRunRegistry()
    restored_service = SimulationRunService(
        prepared_run,
        DailyInteractionRustClient(),
        record_interactions=restored_registry.record,
        persistence=SimulationRunRecorder(path),
    )
    restored_application = FastAPI()
    restored_application.include_router(create_interaction_router(restored_registry), prefix="/api")
    restored_response = TestClient(restored_application).get(
        f"/api/simulation/runs/{launched.run_id}/interactions"
    )

    assert restored_response.status_code == 200
    assert restored_response.json() == live_catalog
    assert restored_service.agent(launched.run_id, "agent-1") == first_agent
    assert restored_service.agent(launched.run_id, "agent-2") == second_agent
    restored_service.shutdown()


def test_long_day_is_split_into_bounded_resumable_rust_chunks():
    rust = LinearCheckpointRustClient()
    service = SimulationRunService(prepared_run, rust)
    config = run_config(
        population_size=1,
        days=1,
        tick_interval_hours=24 / 2048,
    )

    launched = service.launch(config)
    completed = wait_for_terminal(service, launched.run_id)

    assert completed.status == "completed"
    assert [int(request["ticks"]) for request in rust.requests] == [1024, 1024]
    assert sum(int(request["ticks"]) for request in rust.requests) == config.total_ticks
    assert completed.result is not None
    assert [snapshot.tick for snapshot in completed.result.snapshots] == [2048]
    assert list(completed.result.snapshots[0].state_counts) == ["day / checkpoint-2048"]
    service.shutdown()


def test_same_config_and_seed_produce_identical_rust_timelines():
    service = SimulationRunService(prepared_run, RustCoreClient(), max_workers=2)
    config = run_config()
    first = service.launch(config)
    second = service.launch(config)
    first_complete = wait_for_terminal(service, first.run_id)
    second_complete = wait_for_terminal(service, second.run_id)

    assert first_complete.status == "completed"
    assert second_complete.status == "completed"
    assert first_complete.result is not None
    assert second_complete.result is not None
    assert first_complete.result.output_hash == second_complete.result.output_hash
    assert first_complete.result.snapshots == second_complete.result.snapshots
    assert first_complete.result.engine_version == "0.1.0"
    assert first_complete.result.source == "rust"
    assert [snapshot.day for snapshot in first_complete.result.snapshots] == [1, 2, 3]
    assert [snapshot.tick for snapshot in first_complete.result.snapshots] == [4, 8, 12]
    assert sum(first_complete.result.snapshots[-1].state_counts.values()) == 8

    agents = service.agents(first.run_id, search="Person 1")
    assert agents.total == 1
    detail = service.agent(first.run_id, "agent-1")
    assert [point.day for point in detail.timeline] == [1, 2, 3]
    assert detail.initial_state == "choose"
    assert detail.final_state in {"home", "outside"}
    assert detail.timeline[0].routine_actions.count("commute") == 3
    service.shutdown()


def test_place_restricted_module_records_unavailable_events_without_executing():
    def place_restricted_run(config: SimulationRunConfig) -> PreparedRustRun:
        prepared = prepared_run(config)
        request = deepcopy(prepared.rust_request)
        request["places"][0].update(
            {
                "kind": "home",
                "accepts_arrivals": True,
                "capacity": config.population_size,
            }
        )
        request["modules"][0]["available_place_kinds"] = ["bar"]
        request["schedules"] = []
        return prepared.model_copy(update={"rust_request": request})

    service = SimulationRunService(place_restricted_run, RustCoreClient())
    launched = service.launch(run_config(population_size=2, days=1))
    completed = wait_for_terminal(service, launched.run_id)

    assert completed.status == "completed"
    availability = service.events(launched.run_id, kind="availability")
    assert availability.total == 8
    assert all(item.agent_ids for item in availability.items)
    assert all("requires place kind bar" in item.label for item in availability.items)
    detail = service.agent(launched.run_id, "agent-1")
    assert detail.final_state == "choose"
    assert detail.timeline[0].decision_path == []
    service.shutdown()


def prepared_constrained_move_run(
    config: SimulationRunConfig,
    *,
    accepts_arrivals: bool,
    capacity: int,
) -> PreparedRustRun:
    prepared = prepared_run(config)
    request = deepcopy(prepared.rust_request)
    request["places"] = [
        {
            "id": "home",
            "kind": "home",
            "accepts_arrivals": True,
            "allows_in_person": True,
            "capacity": config.population_size,
            "state": {},
        },
        {
            "id": "work",
            "kind": "work",
            "accepts_arrivals": accepts_arrivals,
            "allows_in_person": True,
            "capacity": capacity,
            "state": {},
        },
    ]
    request["agents"]["place"] = [0] * config.population_size
    request["schedules"][0].update(
        {
            "destination_place_index": 1,
            "required_place_indices": [1],
        }
    )
    return prepared.model_copy(update={"rust_request": request})


def test_run_service_records_capacity_block_without_exceeding_place_occupancy():
    service = SimulationRunService(
        lambda config: prepared_constrained_move_run(
            config,
            accepts_arrivals=True,
            capacity=1,
        ),
        RustCoreClient(),
    )
    launched = service.launch(run_config(population_size=2, days=1))
    completed = wait_for_terminal(service, launched.run_id)

    assert completed.status == "completed"
    availability = service.events(launched.run_id, kind="availability")
    locations = service.events(launched.run_id, kind="location")
    assert availability.total == 1
    assert "capacity 1" in availability.items[0].label
    assert locations.total == 1
    agents = service.agents(launched.run_id)
    assert sorted(agent.final_location for agent in agents.items) == ["home", "work"]
    service.shutdown()


def test_run_service_records_closed_destination_for_every_blocked_move():
    service = SimulationRunService(
        lambda config: prepared_constrained_move_run(
            config,
            accepts_arrivals=False,
            capacity=2,
        ),
        RustCoreClient(),
    )
    launched = service.launch(run_config(population_size=2, days=1))
    completed = wait_for_terminal(service, launched.run_id)

    assert completed.status == "completed"
    availability = service.events(launched.run_id, kind="availability")
    assert availability.total == 2
    assert all("does not accept arrivals" in item.label for item in availability.items)
    assert service.events(launched.run_id, kind="location").total == 0
    assert all(agent.final_location == "home" for agent in service.agents(launched.run_id).items)
    service.shutdown()


def test_thirty_day_thousand_agent_run_replays_identically():
    service = SimulationRunService(prepared_run, RustCoreClient(), max_workers=2)
    config = run_config(
        population_size=1000,
        seed=1,
        days=30,
        tick_interval_hours=24,
    )

    first = service.launch(config)
    second = service.launch(config)
    first_complete = wait_for_terminal(service, first.run_id)
    second_complete = wait_for_terminal(service, second.run_id)

    assert first_complete.status == "completed"
    assert second_complete.status == "completed"
    assert first_complete.result is not None
    assert second_complete.result is not None
    assert len(first_complete.result.snapshots) == 30
    assert first_complete.result.snapshots == second_complete.result.snapshots
    assert first_complete.result.output_hash == second_complete.result.output_hash
    assert first_complete.result.snapshots[-1].day == 30
    assert first_complete.result.snapshots[-1].tick == 30
    assert sum(first_complete.result.snapshots[-1].state_counts.values()) == 1000

    detail = service.agent(first.run_id, "agent-1")
    assert len(detail.timeline) == 30
    assert detail.timeline[0].decision_path
    assert (
        detail.timeline[0].decision_path
        == service.agent(second.run_id, "agent-1").timeline[0].decision_path
    )
    service.shutdown()


def test_completed_run_records_hierarchical_agent_locations():
    registry = LocationRunRegistry()

    def run_with_locations(config: SimulationRunConfig) -> PreparedRustRun:
        prepared = prepared_run(config)
        country = LocationPlace(id="canada", name="Canada", level="country")
        region = LocationPlace(
            id="british-columbia",
            name="British Columbia",
            level="region",
            parent_id="canada",
        )
        city = LocationPlace(
            id="vancouver",
            name="Vancouver",
            level="city",
            parent_id="british-columbia",
        )
        return prepared.model_copy(
            update={
                "location_places": [country, region, city],
                "initial_location_ids": ["vancouver"] * config.population_size,
                "runtime_place_location_ids": ["vancouver"],
            }
        )

    service = SimulationRunService(
        run_with_locations,
        RustCoreClient(),
        record_locations=registry.record,
    )
    launched = service.launch(run_config(population_size=2, days=1))
    completed = wait_for_terminal(service, launched.run_id)

    assert completed.status == "completed"
    snapshot = registry.catalog(launched.run_id).snapshot()
    assert snapshot.tick == 4
    assert snapshot.root_location_ids == ("canada",)
    assert [agent.current_location_id for agent in snapshot.agents] == [
        "vancouver",
        "vancouver",
    ]
    service.shutdown()


class LocationTransitionRustClient:
    def run_agents(self, request: dict) -> dict:
        agents = deepcopy(request["agents"])
        agents["place"][0] = 2
        return {
            "protocol_version": "1",
            "engine_version": "test-rust",
            "seed": request["seed"],
            "ticks": request["ticks"],
            "agents": agents,
            "live_places": [
                {
                    "place_index": index,
                    "place_id": place["id"],
                    "kind": "place",
                    "accepts_arrivals": True,
                    "allows_in_person": True,
                    "capacity": None,
                    "occupancy": [1, 0, 1][index],
                    "crowd_density": None,
                    "state": {"occupancy": float([1, 0, 1][index])},
                }
                for index, place in enumerate(request["places"])
            ],
            "transition_counts": [],
            "transition_evidence": [],
            "transition_outcomes": [],
            "events": [],
            "routine_actions": [],
            "routine_unavailable": [
                {
                    "tick": 1,
                    "schedule": "bar-visit",
                    "agent_index": 1,
                    "current_place_index": 0,
                    "destination_place_index": 2,
                    "decision_module": "bar-choice",
                    "reason": (
                        "Bar choice unavailable — agent is at home and no confirmed route applies"
                    ),
                }
            ],
            "location_transitions": [
                {
                    "tick": 1,
                    "agent_index": 0,
                    "source": "weekday-commute",
                    "phase": "travel_started",
                    "from_place_index": 0,
                    "to_place_index": 1,
                    "destination_place_index": 2,
                    "provenance": {
                        "source_title": "Vancouver travel survey",
                        "source_version": "2025",
                        "source_date": "2025-04-01",
                        "licence": "Open Government Licence",
                        "evidence_id": "commute-2025",
                        "status": "measured",
                    },
                },
                {
                    "tick": 2,
                    "agent_index": 0,
                    "source": "weekday-commute",
                    "phase": "travel_arrived",
                    "from_place_index": 1,
                    "to_place_index": 2,
                    "destination_place_index": 2,
                    "provenance": {
                        "source_title": "Vancouver travel survey",
                        "source_version": "2025",
                        "source_date": "2025-04-01",
                        "licence": "Open Government Licence",
                        "evidence_id": "commute-2025",
                        "status": "measured",
                    },
                },
            ],
            "interactions": [],
            "synchronization": [],
            "shard_populations": [],
        }


def prepared_location_transition_run(config: SimulationRunConfig) -> PreparedRustRun:
    prepared = prepared_run(config)
    request = deepcopy(prepared.rust_request)
    request["places"] = [
        {"id": "home-agent-1", "state": {}},
        {"id": "transit-vancouver", "state": {}},
        {"id": "workplace-vancouver", "state": {}},
    ]
    places = [
        LocationPlace(id="canada", name="Canada", level="country"),
        LocationPlace(
            id="british-columbia",
            name="British Columbia",
            level="region",
            parent_id="canada",
        ),
        LocationPlace(
            id="vancouver",
            name="Vancouver",
            level="city",
            parent_id="british-columbia",
        ),
        LocationPlace(
            id="downtown",
            name="Downtown",
            level="district",
            parent_id="vancouver",
        ),
        LocationPlace(
            id="home-agent-1",
            name="Home",
            level="building",
            parent_id="downtown",
        ),
        LocationPlace(
            id="transit-vancouver",
            name="Transit",
            level="building",
            parent_id="downtown",
        ),
        LocationPlace(
            id="workplace-vancouver",
            name="Workplace",
            level="building",
            parent_id="downtown",
        ),
    ]
    return prepared.model_copy(
        update={
            "rust_request": request,
            "location_places": places,
            "initial_location_ids": ["home-agent-1"] * config.population_size,
            "runtime_place_location_ids": [
                "home-agent-1",
                "transit-vancouver",
                "workplace-vancouver",
            ],
        }
    )


def test_location_transitions_are_recorded_as_events_and_agent_history():
    registry = LocationRunRegistry()
    service = SimulationRunService(
        prepared_location_transition_run,
        LocationTransitionRustClient(),
        record_locations=registry.record,
    )
    launched = service.launch(run_config(population_size=2, days=1))
    completed = wait_for_terminal(service, launched.run_id)

    assert completed.status == "completed"
    locations = service.events(launched.run_id, kind="location")
    assert locations.total == 2
    assert [item.label for item in locations.items] == [
        "home-agent-1 → transit-vancouver",
        "transit-vancouver → workplace-vancouver",
    ]
    assert locations.items[0].location == "transit-vancouver"
    assert locations.items[0].details["kind"] == "travel_started"
    assert locations.items[0].details["schedule"] == "weekday-commute"
    assert locations.items[0].details["destination_location"] == "workplace-vancouver"
    assert locations.items[0].details["provenance"] == {
        "recorded_by": "rust_numeric_core",
        "record": "location_transitions",
        "source_kind": "schedule",
        "source_title": "Vancouver travel survey",
        "source_version": "2025",
        "source_date": "2025-04-01",
        "licence": "Open Government Licence",
        "evidence_id": "commute-2025",
        "status": "measured",
    }
    availability = service.events(launched.run_id, kind="availability")
    assert availability.total == 1
    assert availability.items[0].agent_ids == ["agent-2"]
    assert availability.items[0].location == "home-agent-1"
    assert availability.items[0].details["decision_module"] == "bar-choice"
    assert "no confirmed route" in availability.items[0].label

    detail = service.agent(launched.run_id, "agent-1")
    history = detail.timeline[0].location_transitions
    assert [(item.kind, item.from_location, item.to_location) for item in history] == [
        ("travel_started", "home-agent-1", "transit-vancouver"),
        ("travel_arrived", "transit-vancouver", "workplace-vancouver"),
    ]
    assert history[0].schedule == "weekday-commute"
    recorded_history = registry.catalog(launched.run_id).agent_detail("agent-1").history
    assert [(item.from_location_id, item.to_location_id) for item in recorded_history] == [
        ("home-agent-1", "transit-vancouver"),
        ("transit-vancouver", "workplace-vancouver"),
    ]
    assert detail.timeline[0].actions == []
    assert service.agent(launched.run_id, "agent-2").timeline[0].location_transitions == []
    service.shutdown()


class BlockingRustClient:
    def __init__(self):
        self.calls = 0
        self.executed_ticks = 0

    def run_agents(self, request: dict) -> dict:
        self.calls += 1
        self.executed_ticks += int(request["ticks"])
        time.sleep(0.05)
        agents = deepcopy(request["agents"])
        agents["state"] = ["home"] * len(agents["state"])
        return {
            "protocol_version": "1",
            "engine_version": "test-rust",
            "seed": request["seed"],
            "ticks": request["ticks"],
            "agents": agents,
            "transition_counts": [],
            "transition_evidence": [],
            "events": [],
            "routine_actions": [],
            "synchronization": [],
            "shard_populations": [
                {"place_index": 0, "place": "Vancouver", "agents": len(agents["state"])}
            ],
        }


def test_cancel_stops_before_the_next_rust_checkpoint():
    rust = BlockingRustClient()
    service = SimulationRunService(prepared_run, rust)
    config = run_config(population_size=2, seed=11, days=20)
    launched = service.launch(config)
    deadline = time.monotonic() + 2
    while rust.calls == 0 and time.monotonic() < deadline:
        time.sleep(0.005)
    cancelling = service.cancel(launched.run_id)
    assert cancelling.status in {"cancelling", "cancelled"}
    cancelled = wait_for_terminal(service, launched.run_id)
    assert cancelled.status == "cancelled"
    assert rust.calls == 1
    assert rust.executed_ticks == config.ticks_per_day
    assert cancelled.completed_ticks == config.ticks_per_day
    assert cancelled.progress == 1 / config.days
    service.shutdown()


def test_active_run_cannot_be_deleted():
    rust = BlockingRustClient()
    service = SimulationRunService(prepared_run, rust)
    application = FastAPI()
    application.include_router(create_simulation_run_router(service), prefix="/api")
    client = TestClient(application)
    launched = service.launch(run_config(population_size=2, days=20))
    deadline = time.monotonic() + 2
    while rust.calls == 0 and time.monotonic() < deadline:
        time.sleep(0.005)

    response = client.delete(
        f"/api/simulation/runs/{launched.run_id}",
        params={"confirm_run_id": launched.run_id},
    )
    assert response.status_code == 409
    service.cancel(launched.run_id)
    assert wait_for_terminal(service, launched.run_id).status == "cancelled"
    service.shutdown()


def test_router_exposes_launch_progress_results_agents_and_cancel():
    service = SimulationRunService(prepared_run, RustCoreClient())
    application = FastAPI()
    application.include_router(create_simulation_run_router(service), prefix="/api")
    client = TestClient(application)

    response = client.post(
        "/api/simulation/runs",
        json={
            "population_size": 4,
            "seed": 44,
            "days": 2,
            "tick_interval_hours": 6,
            "start_date": "2026-10-27",
            "place_scope": {"level": "city", "identifier": "Vancouver"},
            "agent_type_mix": {"ResidentAgent": 1.0},
        },
    )
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    completed = wait_for_terminal(service, run_id)
    assert completed.status == "completed"

    run_response = client.get(f"/api/simulation/runs/{run_id}")
    assert run_response.status_code == 200
    assert run_response.json()["result"]["source"] == "rust"
    assert client.get(f"/api/simulation/runs/{run_id}/agents").json()["total"] == 4
    assert client.get(f"/api/simulation/runs/{run_id}/agents/agent-1").status_code == 200
    assert client.get(f"/api/simulation/runs/{run_id}/events").status_code == 200
    assert client.get(f"/api/simulation/runs/{run_id}/events?kind=location").status_code == 200
    assert client.post("/api/simulation/runs/not-a-run/cancel").status_code == 404
    service.shutdown()


def test_completed_run_reopens_from_durable_recorder_after_service_restart(tmp_path):
    recorder = SimulationRunRecorder(tmp_path / "simulation-runs.sqlite3")
    first_service = SimulationRunService(
        prepared_run,
        RustCoreClient(),
        persistence=recorder,
    )
    launched = first_service.launch(run_config(population_size=4, days=2))
    completed = wait_for_terminal(first_service, launched.run_id)
    assert completed.status == "completed"
    first_detail = first_service.agent(launched.run_id, "agent-1")
    first_events = first_service.events(launched.run_id)
    first_service.shutdown()

    restored_service = SimulationRunService(
        prepared_run,
        RustCoreClient(),
        persistence=SimulationRunRecorder(tmp_path / "simulation-runs.sqlite3"),
    )
    restored = restored_service.get(launched.run_id)

    assert restored == completed
    assert restored_service.list() == [completed]
    assert restored_service.agent(launched.run_id, "agent-1") == first_detail
    assert restored_service.events(launched.run_id) == first_events
    restored_service.shutdown()


def test_completed_run_restores_location_and_interaction_catalogs(tmp_path):
    path = tmp_path / "simulation-runs.sqlite3"
    first_locations = LocationRunRegistry()
    first_interactions = InteractionRunRegistry()
    first_service = SimulationRunService(
        prepared_location_transition_run,
        LocationTransitionRustClient(),
        record_locations=first_locations.record,
        record_interactions=first_interactions.record,
        persistence=SimulationRunRecorder(path),
    )
    launched = first_service.launch(run_config(population_size=2, days=1))
    completed = wait_for_terminal(first_service, launched.run_id)
    assert completed.status == "completed"
    first_service.shutdown()

    restored_locations = LocationRunRegistry()
    restored_interactions = InteractionRunRegistry()
    restored_service = SimulationRunService(
        prepared_location_transition_run,
        LocationTransitionRustClient(),
        record_locations=restored_locations.record,
        record_interactions=restored_interactions.record,
        persistence=SimulationRunRecorder(path),
    )

    snapshot = restored_locations.catalog(launched.run_id).snapshot()
    interactions = restored_interactions.catalog(launched.run_id).query(InteractionQuery())

    assert snapshot.tick == completed.completed_ticks
    assert snapshot.agents[0].current_location_id == "workplace-vancouver"
    assert len(snapshot.agents) == 2
    assert interactions.total == 0
    restored_service.shutdown()


class LivePlaceReceiptRustClient(LinearCheckpointRustClient):
    def run_agents(self, request: dict) -> dict:
        output = super().run_agents(request)
        tick = output["ticks"]
        agents = output["agents"]
        agents["place"] = [0, 1] if tick == 1 else [0, 0]
        clean_occupancy = 1 if tick == 1 else 2
        dirty_occupancy = 1 if tick == 1 else 0
        live_places = [
            {
                "place_index": 0,
                "place_id": "clean-bar-runtime",
                "kind": "bar",
                "accepts_arrivals": True,
                "allows_in_person": True,
                "capacity": 4,
                "occupancy": clean_occupancy,
                "crowd_density": clean_occupancy / 4,
                "state": {
                    "contamination": 0.2,
                    "occupancy": float(clean_occupancy),
                    "crowd_density": clean_occupancy / 4,
                },
            },
            {
                "place_index": 1,
                "place_id": "dirty-bar-runtime",
                "kind": "bar",
                "accepts_arrivals": False,
                "allows_in_person": True,
                "capacity": 2,
                "occupancy": dirty_occupancy,
                "crowd_density": dirty_occupancy / 2,
                "state": {
                    "contamination": 0.8,
                    "occupancy": float(dirty_occupancy),
                    "crowd_density": dirty_occupancy / 2,
                },
            },
        ]
        output["live_places"] = live_places
        output["continuation"]["live_places"] = deepcopy(live_places)
        return output


def prepared_live_place_receipt_run(config: SimulationRunConfig) -> PreparedRustRun:
    prepared = prepared_run(config)
    request = deepcopy(prepared.rust_request)
    request["places"] = [
        {
            "id": "clean-bar-runtime",
            "kind": "bar",
            "accepts_arrivals": True,
            "allows_in_person": True,
            "capacity": 4,
            "state": {"contamination": 0.2},
        },
        {
            "id": "dirty-bar-runtime",
            "kind": "bar",
            "accepts_arrivals": False,
            "allows_in_person": True,
            "capacity": 2,
            "state": {"contamination": 0.8},
        },
    ]
    request["agents"]["place"] = [0, 1]
    places = [
        LocationPlace(
            id="clean-bar",
            name="Clean bar",
            level="country",
            capacity=4,
            state={"contamination": 0.2},
        ),
        LocationPlace(
            id="dirty-bar",
            name="Dirty bar",
            level="country",
            accepts_arrivals=False,
            capacity=2,
            state={"contamination": 0.8},
        ),
    ]
    return prepared.model_copy(
        update={
            "rust_request": request,
            "location_places": places,
            "initial_location_ids": ["clean-bar", "dirty-bar"],
            "runtime_place_location_ids": ["clean-bar", "dirty-bar"],
        }
    )


def test_live_place_receipts_change_between_snapshots_and_survive_restart(tmp_path):
    path = tmp_path / "simulation-runs.sqlite3"
    first_locations = LocationRunRegistry()
    first_service = SimulationRunService(
        prepared_live_place_receipt_run,
        LivePlaceReceiptRustClient(),
        record_locations=first_locations.record,
        persistence=SimulationRunRecorder(path),
    )
    launched = first_service.launch(
        run_config(population_size=2, days=2, tick_interval_hours=24)
    )
    completed = wait_for_terminal(first_service, launched.run_id)

    assert completed.status == "completed"
    assert completed.result is not None
    first_frame, second_frame = completed.result.snapshots
    assert [(place.occupancy, place.crowd_density) for place in first_frame.live_places] == [
        (1, 0.25),
        (1, 0.5),
    ]
    assert [(place.occupancy, place.crowd_density) for place in second_frame.live_places] == [
        (2, 0.5),
        (0, 0.0),
    ]
    assert [place.state["contamination"] for place in second_frame.live_places] == [0.2, 0.8]
    live_snapshot = first_locations.catalog(launched.run_id).snapshot()
    live_clean, live_dirty = live_snapshot.places
    assert live_clean.state == {
        "contamination": 0.2,
        "occupancy": 2.0,
        "crowd_density": 0.5,
    }
    assert live_clean.current_agent_count == 2
    assert live_clean.capacity == 4
    assert live_dirty.state == {
        "contamination": 0.8,
        "occupancy": 0.0,
        "crowd_density": 0.0,
    }
    assert not live_dirty.accepts_arrivals
    live_agent = first_locations.catalog(launched.run_id).agent_detail("agent-1")
    assert live_agent.current_location.state_source == "rust_numeric_core"
    assert live_agent.effective_place_state == live_clean.state
    assert [agent.agent_id for agent in live_agent.co_located_agents] == ["agent-2"]
    assert live_agent.elsewhere_agents == ()
    first_service.shutdown()

    restored_locations = LocationRunRegistry()
    restored_service = SimulationRunService(
        prepared_live_place_receipt_run,
        LivePlaceReceiptRustClient(),
        record_locations=restored_locations.record,
        persistence=SimulationRunRecorder(path),
    )

    restored_catalog = restored_locations.catalog(launched.run_id)
    assert restored_catalog.snapshot() == live_snapshot
    assert restored_catalog.agent_detail("agent-1") == live_agent
    assert restored_service.get(launched.run_id) == completed
    restored_service.shutdown()


class FailingRustClient:
    def run_agents(self, request: dict) -> dict:
        raise RuntimeError("fixture Rust failure")


def test_failed_run_reopens_with_error_after_service_restart(tmp_path):
    path = tmp_path / "simulation-runs.sqlite3"
    first_service = SimulationRunService(
        prepared_run,
        FailingRustClient(),
        persistence=SimulationRunRecorder(path),
    )
    launched = first_service.launch(run_config(population_size=2, days=1))
    failed = wait_for_terminal(first_service, launched.run_id)
    assert failed.status == "failed"
    assert failed.error == "fixture Rust failure"
    first_service.shutdown()

    restored_service = SimulationRunService(
        prepared_run,
        RustCoreClient(),
        persistence=SimulationRunRecorder(path),
    )
    restored = restored_service.get(launched.run_id)
    assert restored.status == "failed"
    assert restored.error == "fixture Rust failure"
    assert restored.config == launched.config
    restored_service.shutdown()


def test_delete_requires_matching_run_id_and_removes_durable_output(tmp_path):
    path = tmp_path / "simulation-runs.sqlite3"
    service = SimulationRunService(
        prepared_run,
        RustCoreClient(),
        persistence=SimulationRunRecorder(path),
    )
    application = FastAPI()
    application.include_router(create_simulation_run_router(service), prefix="/api")
    client = TestClient(application)
    launched = service.launch(run_config(population_size=2, days=1))
    wait_for_terminal(service, launched.run_id)

    mismatch = client.delete(
        f"/api/simulation/runs/{launched.run_id}",
        params={"confirm_run_id": "another-run"},
    )
    assert mismatch.status_code == 422
    assert service.get(launched.run_id).status == "completed"

    deleted = client.delete(
        f"/api/simulation/runs/{launched.run_id}",
        params={"confirm_run_id": launched.run_id},
    )
    assert deleted.status_code == 204
    assert client.get(f"/api/simulation/runs/{launched.run_id}").status_code == 404
    service.shutdown()

    restored_service = SimulationRunService(
        prepared_run,
        RustCoreClient(),
        persistence=SimulationRunRecorder(path),
    )
    assert restored_service.list() == []
    restored_service.shutdown()
