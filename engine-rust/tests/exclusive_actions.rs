use petraterrium_engine::agent_types::AgentProgramRequest;
use petraterrium_engine::agents::run;
use serde_json::{Value, json};

fn provenance() -> Value {
    json!({
        "source": "Fixture default",
        "version": "fixture-v1",
        "status": "default_estimated",
        "uncertainty": 1.0
    })
}

fn action(id: &str, group: Option<&str>, probability: f64) -> Value {
    json!({
        "id": id,
        "exclusive_choice_group": group,
        "rules": [{
            "conditions": [{"input": "context.hour", "operator": "eq", "value": 12.0}],
            "probability": probability,
            "provenance": provenance()
        }]
    })
}

fn state_rule(target: &str) -> Value {
    json!({
        "target_state_id": target,
        "intercept": 0.0,
        "coefficients": {},
        "minimum": 0.0,
        "maximum": 1.0,
        "formula": format!("{target}[t+1] = clamp({target}[t] + event_delta, 0, 1)"),
        "evidence": {
            "status": "default_estimated",
            "source": "Fixture default",
            "source_version": "fixture-v1",
            "uncertainty": 1.0
        }
    })
}

fn request(seed: u64, eat_probability: f64, skip_probability: f64) -> AgentProgramRequest {
    let population = 64;
    serde_json::from_value(json!({
        "seed": seed,
        "ticks": 1,
        "tick_hours": 1.0,
        "start_hour": 12.0,
        "start_weekday": 0,
        "places": [{"id": "global", "kind": "region"}],
        "agents": {
            "agent_ids": (0..population).map(|index| format!("agent-{index}")).collect::<Vec<_>>(),
            "module": vec!["idle"; population],
            "state": vec!["idle"; population],
            "place": vec![0; population],
            "memory": {
                "hunger": vec![0.5; population],
                "stress": vec![0.5; population],
                "finance.money": vec![10.0; population],
                "finance.income": vec![0.0; population],
                "finance.expenses": vec![0.0; population],
                "finance.savings": vec![0.0; population],
                "finance.debt": vec![0.0; population]
            }
        },
        "modules": [{
            "id": "idle",
            "entry_state": "idle",
            "exit_states": ["idle"],
            "states": ["idle"],
            "transitions": []
        }],
        "meaningful_actions": [
            action("eat_lunch", Some("midday_meal"), eat_probability),
            action("skip_lunch", Some("midday_meal"), skip_probability),
            action("work", None, 1.0)
        ],
        "state_dynamics": {
            "events": [
                {
                    "id": "eat_lunch",
                    "effects": [{"target": "memory.hunger", "operation": "subtract", "value": 0.1}],
                    "cash_flow": {"food": 2.0},
                    "evidence": {
                        "status": "default_estimated",
                        "source": "Fixture default",
                        "source_version": "fixture-v1",
                        "uncertainty": 1.0
                    }
                },
                {
                    "id": "skip_lunch",
                    "effects": [{"target": "memory.hunger", "operation": "add", "value": 0.1}],
                    "cash_flow": {},
                    "evidence": {
                        "status": "default_estimated",
                        "source": "Fixture default",
                        "source_version": "fixture-v1",
                        "uncertainty": 1.0
                    }
                },
                {
                    "id": "work",
                    "effects": [{"target": "memory.stress", "operation": "add", "value": 0.05}],
                    "cash_flow": {},
                    "evidence": {
                        "status": "default_estimated",
                        "source": "Fixture default",
                        "source_version": "fixture-v1",
                        "uncertainty": 1.0
                    }
                }
            ],
            "state_rules": [state_rule("hunger"), state_rule("stress")],
            "finance": {
                "currency": vec!["USD"; population],
                "status": vec!["default_estimated"; population],
                "source": vec!["Fixture default"; population]
            },
            "finance_rules": [
                {
                    "id": "expenses",
                    "target": "finance.expenses",
                    "terms": {"finance.expenses": 1.0, "cash_flow.food": 1.0},
                    "minimum": 0.0,
                    "maximum": null,
                    "formula": "expenses[t+1] = expenses[t] + food",
                    "evidence": {
                        "status": "default_estimated",
                        "source": "Fixture default",
                        "source_version": "fixture-v1",
                        "uncertainty": 1.0
                    }
                },
                {
                    "id": "money",
                    "target": "finance.money",
                    "terms": {"finance.money": 1.0, "cash_flow.food": -1.0},
                    "minimum": 0.0,
                    "maximum": null,
                    "formula": "money[t+1] = max(0, money[t] - food)",
                    "evidence": {
                        "status": "default_estimated",
                        "source": "Fixture default",
                        "source_version": "fixture-v1",
                        "uncertainty": 1.0
                    }
                }
            ]
        }
    }))
    .unwrap()
}

#[test]
fn grouped_actions_use_one_seeded_categorical_draw_and_independent_actions_still_run() {
    let result = run(request(17, 0.4, 0.6)).unwrap();
    let repeated = run(request(17, 0.4, 0.6)).unwrap();
    let different_seed = run(request(18, 0.4, 0.6)).unwrap();

    assert_eq!(result, repeated);
    assert_ne!(result.events, different_seed.events);
    for agent in 0..64 {
        let agent_events = result
            .events
            .iter()
            .filter(|event| event.agent_index == agent)
            .collect::<Vec<_>>();
        assert_eq!(agent_events.len(), 2);
        assert_eq!(
            agent_events
                .iter()
                .filter(|event| matches!(event.action.as_str(), "eat_lunch" | "skip_lunch"))
                .count(),
            1
        );
        assert!(agent_events.iter().any(|event| event.action == "work"));
        let meal = agent_events
            .iter()
            .find(|event| matches!(event.action.as_str(), "eat_lunch" | "skip_lunch"))
            .unwrap();
        let expected_hunger = if meal.action == "eat_lunch" { 0.4 } else { 0.6 };
        assert!((result.agents.memory["hunger"][agent] - expected_hunger).abs() < 1e-12);
        assert!((result.agents.memory["stress"][agent] - 0.55).abs() < 1e-12);
        let finance = result.state_ticks[0]
            .finance_changes
            .iter()
            .find(|receipt| receipt.agent_index == agent);
        let expected_food = if meal.action == "eat_lunch" { 2.0 } else { 0.0 };
        if meal.action == "eat_lunch" {
            assert_eq!(finance.unwrap().flows.food, expected_food);
        } else {
            assert!(finance.is_none());
        }
        assert_eq!(
            result.agents.memory["finance.money"][agent],
            10.0 - expected_food
        );
        assert_eq!(
            result.agents.memory["finance.expenses"][agent],
            expected_food
        );
    }
    let first_tick = &result.state_ticks[0];
    assert_eq!(first_tick.event_counts["work"], 64);
    assert_eq!(
        first_tick
            .event_counts
            .get("eat_lunch")
            .copied()
            .unwrap_or(0)
            + first_tick
                .event_counts
                .get("skip_lunch")
                .copied()
                .unwrap_or(0),
        64
    );
}

#[test]
fn grouped_actions_reject_matching_probabilities_that_do_not_sum_to_one() {
    let error = run(request(17, 0.4, 0.5)).unwrap_err();

    assert_eq!(error.code, "INVALID_DISTRIBUTION");
    assert!(error.message.contains("sum to 0.900000000000"));
    assert!(
        error
            .path
            .as_deref()
            .is_some_and(|path| path.contains("exclusive_choice_group.midday_meal"))
    );
}

#[test]
fn grouped_actions_require_at_least_two_branches() {
    let mut invalid = request(17, 0.4, 0.6);
    invalid
        .meaningful_actions
        .retain(|action| action.id != "skip_lunch");

    let error = run(invalid).unwrap_err();

    assert_eq!(error.code, "INVALID_ACTION_CHOICE_GROUP");
    assert!(error.message.contains("at least two branches"));
}
