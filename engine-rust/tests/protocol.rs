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
