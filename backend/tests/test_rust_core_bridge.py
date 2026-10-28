from copy import deepcopy

import pytest

from petraterrium.rust_core import RustCoreClient, RustCoreError


@pytest.fixture(scope="module")
def rust_core() -> RustCoreClient:
    return RustCoreClient()


def test_rust_core_defaults_to_optimized_release_profile(monkeypatch, tmp_path):
    binary = tmp_path / "petraterrium-engine"
    binary.touch()
    monkeypatch.delenv("PETRATERRIUM_RUST_CORE_PROFILE", raising=False)

    client = RustCoreClient(binary, build_if_missing=False)

    assert client.profile == "release"


def location_request() -> dict:
    return {
        "operation": "health",
        "tick": 9,
        "places": [
            {
                "id": "canada",
                "name": "Canada",
                "level": "country",
                "parent_id": None,
                "accepts_arrivals": True,
                "allows_in_person": True,
                "capacity": None,
                "state": {"tax_rate": 0.2},
            },
            {
                "id": "mexico",
                "name": "Mexico",
                "level": "country",
                "parent_id": None,
                "accepts_arrivals": True,
                "allows_in_person": True,
                "capacity": None,
                "state": {"tax_rate": 0.16},
            },
        ],
        "agents": {
            "agent_ids": ["traveler"],
            "current_location_ids": ["canada"],
        },
        "movements": [
            {
                "agent_index": 0,
                "destination_location_id": "mexico",
                "expected_parent_id": None,
            }
        ],
        "history": [],
    }


def interaction_tree_request() -> dict:
    return {
        "operation": "health",
        "seed": 13,
        "tick": 48,
        "tree": {
            "id": "message_friend",
            "name": "Message a friend",
            "version": "1",
            "entry_node": "offered",
            "allowed_channels": ["phone_message"],
            "co_location_policy": "remote_allowed",
            "nodes": [
                {"id": "offered", "label": "Message sent", "terminal": False},
                {"id": "accepted", "label": "Invitation accepted", "terminal": True},
            ],
            "transitions": [
                {
                    "id": "accept",
                    "from_node": "offered",
                    "to_node": "accepted",
                    "outcome": "accepted",
                    "probability": 1,
                    "evidence": {
                        "source": "Observed communication panel",
                        "version": "2026-01",
                        "status": "measured_joint",
                        "uncertainty": 0.08,
                        "source_date": "2026-01-15",
                        "evidence_id": "message-acceptance",
                    },
                    "conditions": [],
                    "effects": [
                        {
                            "kind": "relationship_kind",
                            "relationship_type": "friend",
                        }
                    ],
                }
            ],
        },
        "context": {
            "actor": {"agent_id": "agent-a", "place_id": "home-a"},
            "target": {"agent_id": "agent-b", "place_id": "home-b"},
            "relationship": {
                "source_agent_id": "agent-a",
                "target_agent_id": "agent-b",
                "eligible": True,
                "relationship_type": "acquaintance",
            },
            "place": {"id": "home-a", "kind": "home"},
            "time": {"weekday": 5, "hour": 19},
            "channel": "phone_message",
        },
    }


def live_place_state_request() -> dict:
    probability_evidence = {
        "source": "Measured place-state fixture",
        "version": "v1",
        "status": "present",
        "uncertainty": 0,
    }
    interaction_evidence = {
        "source": "Measured interaction fixture",
        "version": "v1",
        "status": "measured_joint",
        "uncertainty": 0,
    }
    factor = {
        "id": "certain",
        "label": "Certain",
        "value": 1,
        "provenance": interaction_evidence,
    }

    def crowd_rules(sparse_probability: float) -> list[dict]:
        return [
            {
                "conditions": [
                    {
                        "input": "place.crowd_density",
                        "operator": "lt",
                        "value": 0.4,
                    }
                ],
                "probability": sparse_probability,
                "provenance": probability_evidence,
            },
            {
                "conditions": [
                    {
                        "input": "place.crowd_density",
                        "operator": "gte",
                        "value": 0.4,
                    }
                ],
                "probability": 1 - sparse_probability,
                "provenance": probability_evidence,
            },
        ]

    tree = {
        "id": "place-context",
        "name": "Place context",
        "version": "v1",
        "entry_node": "start",
        "allowed_channels": ["in_person"],
        "co_location_policy": "required",
        "nodes": [
            {"id": "start", "label": "Start", "terminal": False},
            {"id": "dirty", "label": "Dirty crowded bar", "terminal": True},
            {"id": "clean", "label": "Clean filling bar", "terminal": True},
        ],
        "transitions": [
            {
                "id": "dirty-context",
                "from_node": "start",
                "to_node": "dirty",
                "outcome": "dirty",
                "probability": 1,
                "evidence": interaction_evidence,
                "conditions": [
                    {"input": "place.state.contamination", "operator": "eq", "value": 0.8},
                    {"input": "place.state.occupancy", "operator": "eq", "value": 2},
                    {"input": "place.state.crowd_density", "operator": "eq", "value": 1},
                ],
                "effects": [],
            },
            {
                "id": "clean-context",
                "from_node": "start",
                "to_node": "clean",
                "outcome": "clean",
                "probability": 1,
                "evidence": interaction_evidence,
                "conditions": [
                    {"input": "place.state.contamination", "operator": "eq", "value": 0.2},
                    {"input": "place.state.occupancy", "operator": "eq", "value": 2},
                    {"input": "place.state.crowd_density", "operator": "eq", "value": 0.5},
                ],
                "effects": [],
            },
        ],
    }
    return {
        "seed": 19,
        "ticks": 2,
        "tick_hours": 1,
        "start_hour": 0,
        "start_weekday": 0,
        "places": [
            {
                "id": "clean-bar",
                "kind": "bar",
                "accepts_arrivals": True,
                "allows_in_person": True,
                "capacity": 4,
                "state": {"contamination": 0.2},
            },
            {
                "id": "dirty-bar",
                "kind": "bar",
                "accepts_arrivals": True,
                "allows_in_person": True,
                "capacity": 2,
                "state": {"contamination": 0.8},
            },
        ],
        "agents": {
            "agent_ids": ["clean-resident", "mover", "dirty-resident"],
            "module": ["crowd-choice"] * 3,
            "state": ["decide"] * 3,
            "place": [0, 1, 1],
            "traits": {},
            "trait_dictionaries": {},
            "memory": {},
        },
        "modules": [
            {
                "id": "crowd-choice",
                "entry_state": "decide",
                "exit_states": [],
                "inputs": ["place.crowd_density"],
                "outputs": [],
                "states": ["decide"],
                "transitions": [
                    {
                        "id": "sparse",
                        "from_state": "decide",
                        "to_state": "decide",
                        "rules": crowd_rules(1),
                        "effects": [],
                    },
                    {
                        "id": "crowded",
                        "from_state": "decide",
                        "to_state": "decide",
                        "rules": crowd_rules(0),
                        "effects": [],
                    },
                ],
            }
        ],
        "routes": [],
        "network": None,
        "schedules": [
            {
                "id": "talk-dirty",
                "action": "talk",
                "weekdays": [0],
                "start_hour": 0,
                "end_hour": 1,
                "eligible_agent_indices": [1],
                "required_place_indices": [1],
            },
            {
                "id": "move-and-talk-clean",
                "action": "talk",
                "weekdays": [0],
                "start_hour": 1,
                "end_hour": 2,
                "eligible_agent_indices": [1],
                "required_place_indices": [0],
                "destination_place_index": 0,
            },
        ],
        "meaningful_actions": [],
        "interactions": {
            "relationships": [
                {
                    "source_index": 1,
                    "target_index": 0,
                    "kind": "friend",
                    "weight": 1,
                    "trust": 1,
                    "similarity": 1,
                },
                {
                    "source_index": 1,
                    "target_index": 2,
                    "kind": "friend",
                    "weight": 1,
                    "trust": 1,
                    "similarity": 1,
                },
            ],
            "trees": {"place-context": tree},
            "rules": [
                {
                    "id": "talk",
                    "source_action": "talk",
                    "interaction_type": "talk",
                    "channel": "in_person",
                    "max_targets_per_initiator": 1,
                    "allowed_relationships": ["friend"],
                    "allowed_place_kinds": ["bar"],
                    "base_factor": factor,
                    "relationship_factors": {"friend": factor},
                    "colocation_factors": {"same_specific_place": factor},
                    "place_factors": {"bar": factor},
                    "time_factors": [
                        {
                            "weekdays": [0],
                            "start_hour": 0,
                            "end_hour": 2,
                            "factor": factor,
                        }
                    ],
                    "context_factors": [],
                    "unrelated_relationship": None,
                    "agent_effects": [],
                    "relationship_effects": [],
                    "interaction_tree_id": "place-context",
                    "interaction_tree_context": {},
                }
            ],
        },
        "synchronization": {},
    }


def test_location_tick_bridge_runs_rust_operation(rust_core: RustCoreClient):
    result = rust_core.run_location_tick(location_request())

    assert result["current_location_ids"] == ["mexico"]
    assert result["movements"][0]["route_location_ids"] == ["canada", "mexico"]
    assert result["protocol_version"] == "1"


def test_location_tick_bridge_preserves_structured_error(rust_core: RustCoreClient):
    invalid = location_request()
    invalid["movements"][0]["destination_location_id"] = "canada"

    with pytest.raises(RustCoreError) as captured:
        rust_core.run_location_tick(invalid)

    assert captured.value.code == "UNCHANGED_LOCATION"
    assert captured.value.path == "movements.0.destination_location_id"


def test_interaction_tree_bridge_preserves_evidence_and_changes(
    rust_core: RustCoreClient,
):
    result = rust_core.run_interaction_tree(interaction_tree_request())

    assert result["outcome"] == "accepted"
    assert result["path"][0]["evidence"]["evidence_id"] == "message-acceptance"
    assert result["relationship_after"]["relationship_type"] == "friend"


def test_interaction_tree_bridge_preserves_structured_error(
    rust_core: RustCoreClient,
):
    invalid = deepcopy(interaction_tree_request())
    invalid["tree"]["transitions"][0]["evidence"]["status"] = "unknown"

    with pytest.raises(RustCoreError) as captured:
        rust_core.run_interaction_tree(invalid)

    assert captured.value.code == "NON_PREDICTIVE_TRANSITION_EVIDENCE"
    assert captured.value.path == "tree.transitions.0.evidence.status"


def test_live_place_occupancy_and_density_reach_decisions_and_interactions_each_tick(
    rust_core: RustCoreClient,
):
    request = live_place_state_request()
    request["ticks"] = 1
    first = rust_core.run_agents(request)
    continued = deepcopy(request)
    continued["agents"] = {
        **first["agents"],
        "agent_ids": request["agents"]["agent_ids"],
    }
    continued["continuation"] = first["continuation"]
    second = rust_core.run_agents(continued)

    first_agent_path = [
        (outcome["tick"], outcome["transition"])
        for result in (first, second)
        for outcome in result["transition_outcomes"]
        if outcome["agent_index"] == 0
    ]
    interaction_paths = [
        (event["tick"], event["place_id"], event["interaction_tree"]["path"][0]["transition_id"])
        for result in (first, second)
        for event in result["interactions"]
    ]

    assert first_agent_path == [(1, "sparse"), (2, "crowded")]
    assert interaction_paths == [
        (1, "dirty-bar", "dirty-context"),
        (2, "clean-bar", "clean-context"),
    ]
    assert first["live_places"] == [
        {
            "place_index": 0,
            "place_id": "clean-bar",
            "kind": "bar",
            "accepts_arrivals": True,
            "allows_in_person": True,
            "capacity": 4,
            "occupancy": 1,
            "crowd_density": 0.25,
            "state": {"contamination": 0.2, "crowd_density": 0.25, "occupancy": 1.0},
        },
        {
            "place_index": 1,
            "place_id": "dirty-bar",
            "kind": "bar",
            "accepts_arrivals": True,
            "allows_in_person": True,
            "capacity": 2,
            "occupancy": 2,
            "crowd_density": 1.0,
            "state": {"contamination": 0.8, "crowd_density": 1.0, "occupancy": 2.0},
        },
    ]
    assert second["live_places"] == [
        {
            "place_index": 0,
            "place_id": "clean-bar",
            "kind": "bar",
            "accepts_arrivals": True,
            "allows_in_person": True,
            "capacity": 4,
            "occupancy": 2,
            "crowd_density": 0.5,
            "state": {"contamination": 0.2, "crowd_density": 0.5, "occupancy": 2.0},
        },
        {
            "place_index": 1,
            "place_id": "dirty-bar",
            "kind": "bar",
            "accepts_arrivals": True,
            "allows_in_person": True,
            "capacity": 2,
            "occupancy": 1,
            "crowd_density": 0.5,
            "state": {"contamination": 0.8, "crowd_density": 0.5, "occupancy": 1.0},
        },
    ]
    assert first["continuation"]["live_places"] == first["live_places"]
    assert second["continuation"]["live_places"] == second["live_places"]
    assert second["agents"]["place"] == [0, 0, 1]
