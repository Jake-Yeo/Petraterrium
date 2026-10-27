use petraterrium_engine::execute_json;
use serde_json::{Value, json};

fn aggregate_request(seed: u64) -> Value {
    json!({
        "operation": "run_aggregate_dsl",
        "seed": seed,
        "ticks": 3,
        "tick_hours": 24.0,
        "snapshot_every_ticks": 1,
        "dsl": {
            "states": [{
                "id": "health",
                "values": ["well", "sick"],
                "initial": {
                    "values": {"well": 0.8, "sick": 0.2},
                    "provenance": {"source": "fixture"}
                }
            }],
            "parameters": [{
                "id": "recovery",
                "value": 0.25,
                "unit": "probability/day"
            }],
            "systems": [{
                "id": "illness",
                "state": "health",
                "transitions": [{
                    "id": "recover",
                    "from_state": "sick",
                    "to_state": "well",
                    "probability": {
                        "base": 0.0,
                        "mode": "probability",
                        "time_unit": "day",
                        "parameter": "recovery",
                        "source_state": null,
                        "mixing_parameter": null,
                        "modifiers": {}
                    }
                }]
            }],
            "population": {
                "id": "fixture",
                "version": "1",
                "size": 100,
                "places": ["A", "B"],
                "place_populations": {"A": 60, "B": 40},
                "place_coordinates": {},
                "place_hierarchy": {},
                "initial_state_overrides": {}
            }
        }
    })
}

fn location_request() -> Value {
    json!({
        "operation": "run_location_tick",
        "tick": 9,
        "places": [
            {
                "id": "canada",
                "name": "Canada",
                "level": "country",
                "parent_id": null,
                "accepts_arrivals": true,
                "allows_in_person": true,
                "capacity": null,
                "state": {"tax_rate": 0.2}
            },
            {
                "id": "mexico",
                "name": "Mexico",
                "level": "country",
                "parent_id": null,
                "accepts_arrivals": true,
                "allows_in_person": true,
                "capacity": null,
                "state": {"tax_rate": 0.16}
            }
        ],
        "agents": {
            "agent_ids": ["traveler"],
            "current_location_ids": ["canada"]
        },
        "movements": [{
            "agent_index": 0,
            "destination_location_id": "mexico",
            "expected_parent_id": null
        }],
        "history": []
    })
}

fn interaction_tree_request() -> Value {
    json!({
        "operation": "run_interaction_tree",
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
                {"id": "offered", "label": "Message sent", "terminal": false},
                {"id": "accepted", "label": "Invitation accepted", "terminal": true}
            ],
            "transitions": [{
                "id": "accept",
                "from_node": "offered",
                "to_node": "accepted",
                "outcome": "accepted",
                "probability": 1.0,
                "evidence": {
                    "source": "Observed communication panel",
                    "version": "2026-01",
                    "status": "measured_joint",
                    "uncertainty": 0.08,
                    "source_date": "2026-01-15",
                    "evidence_id": "message-acceptance"
                },
                "conditions": [],
                "effects": [{
                    "kind": "relationship_kind",
                    "relationship_type": "friend"
                }]
            }]
        },
        "context": {
            "actor": {"agent_id": "agent-a", "place_id": "home-a"},
            "target": {"agent_id": "agent-b", "place_id": "home-b"},
            "relationship": {
                "source_agent_id": "agent-a",
                "target_agent_id": "agent-b",
                "eligible": true,
                "relationship_type": "acquaintance"
            },
            "place": {"id": "home-a", "kind": "home"},
            "time": {"weekday": 5, "hour": 19.0},
            "channel": "phone_message"
        }
    })
}

#[test]
fn json_protocol_is_deterministic_and_accepts_current_dsl_shapes() {
    let encoded = aggregate_request(44).to_string();
    let first = execute_json(&encoded);
    let second = execute_json(&encoded);
    let first_json = serde_json::to_value(first).unwrap();
    let second_json = serde_json::to_value(second).unwrap();
    assert_eq!(first_json, second_json);
    assert_eq!(first_json["ok"], true);
    for snapshot in first_json["result"]["snapshots"].as_array().unwrap() {
        assert_eq!(snapshot["state_totals"]["health"], 100);
    }
}

#[test]
fn protocol_reports_structured_errors_without_panicking() {
    let response = serde_json::to_value(execute_json("{bad json")).unwrap();
    assert_eq!(response["ok"], false);
    assert_eq!(response["error"]["code"], "INVALID_REQUEST");
}

#[test]
fn location_tick_operation_preserves_results_and_structured_errors() {
    let success = serde_json::to_value(execute_json(&location_request().to_string())).unwrap();

    assert_eq!(success["ok"], true);
    assert_eq!(success["result"]["current_location_ids"], json!(["mexico"]));
    assert_eq!(
        success["result"]["movements"][0]["route_location_ids"],
        json!(["canada", "mexico"])
    );

    let mut invalid = location_request();
    invalid["movements"][0]["destination_location_id"] = json!("canada");
    let failure = serde_json::to_value(execute_json(&invalid.to_string())).unwrap();

    assert_eq!(failure["ok"], false);
    assert_eq!(failure["error"]["code"], "UNCHANGED_LOCATION");
    assert_eq!(
        failure["error"]["path"],
        "movements.0.destination_location_id"
    );
}

#[test]
fn interaction_tree_operation_preserves_provenance_and_structured_errors() {
    let success =
        serde_json::to_value(execute_json(&interaction_tree_request().to_string())).unwrap();

    assert_eq!(success["ok"], true);
    assert_eq!(success["result"]["outcome"], "accepted");
    assert_eq!(
        success["result"]["path"][0]["evidence"]["evidence_id"],
        "message-acceptance"
    );
    assert_eq!(
        success["result"]["relationship_after"]["relationship_type"],
        "friend"
    );

    let mut invalid = interaction_tree_request();
    invalid["tree"]["transitions"][0]["evidence"]["status"] = json!("unknown");
    let failure = serde_json::to_value(execute_json(&invalid.to_string())).unwrap();

    assert_eq!(failure["ok"], false);
    assert_eq!(
        failure["error"]["code"],
        "NON_PREDICTIVE_TRANSITION_EVIDENCE"
    );
    assert_eq!(
        failure["error"]["path"],
        "tree.transitions.0.evidence.status"
    );
}
