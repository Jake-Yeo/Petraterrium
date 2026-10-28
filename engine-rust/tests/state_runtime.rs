use petraterrium_engine::agent_types::AgentProgramRequest;
use petraterrium_engine::agents::run;
use serde_json::json;

fn request(seed: u64) -> AgentProgramRequest {
    serde_json::from_value(json!({
        "seed": seed,
        "ticks": 2,
        "tick_hours": 1.0,
        "start_hour": 12.0,
        "start_weekday": 0,
        "places": [{"id": "CA", "kind": "country"}],
        "agents": {
            "agent_ids": ["low-stress", "high-stress"],
            "module": ["idle", "idle"],
            "state": ["idle", "idle"],
            "place": [0, 0],
            "memory": {
                "stress": [0.2, 0.8],
                "health": [1.0, 1.0],
                "finance.money": [100.0, 100.0],
                "finance.income": [0.0, 0.0],
                "finance.expenses": [0.0, 0.0],
                "finance.savings": [20.0, 20.0],
                "finance.debt": [0.0, 0.0]
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
            {
                "id": "bad_work",
                "rules": [{
                    "conditions": [],
                    "probability": 1.0,
                    "provenance": {
                        "source": "Shipped work outcome default",
                        "version": "base-v1",
                        "status": "default_estimated",
                        "uncertainty": 1.0
                    }
                }]
            },
            {
                "id": "skip_lunch",
                "rules": [
                    {
                        "conditions": [{"input": "memory.stress", "operator": "lt", "value": 0.5}],
                        "probability": 0.0,
                        "provenance": {
                            "source": "Shipped meal default",
                            "version": "base-v1",
                            "status": "default_estimated",
                            "uncertainty": 1.0
                        }
                    },
                    {
                        "conditions": [{"input": "memory.stress", "operator": "gte", "value": 0.5}],
                        "probability": 1.0,
                        "provenance": {
                            "source": "Shipped meal default",
                            "version": "base-v1",
                            "status": "default_estimated",
                            "uncertainty": 1.0
                        }
                    }
                ]
            },
            {
                "id": "exercise",
                "rules": [
                    {
                        "conditions": [{"input": "memory.stress", "operator": "lt", "value": 0.5}],
                        "probability": 0.0,
                        "provenance": {
                            "source": "Shipped activity default",
                            "version": "base-v1",
                            "status": "default_estimated",
                            "uncertainty": 1.0
                        }
                    },
                    {
                        "conditions": [{"input": "memory.stress", "operator": "gte", "value": 0.5}],
                        "probability": 1.0,
                        "provenance": {
                            "source": "Shipped activity default",
                            "version": "base-v1",
                            "status": "default_estimated",
                            "uncertainty": 1.0
                        }
                    }
                ]
            }
        ],
        "state_dynamics": {
            "events": [
                {
                    "id": "bad_work",
                    "effects": [{"target": "memory.stress", "operation": "add", "value": 0.2}],
                    "cash_flow": {"wages": 10.0},
                    "evidence": {
                        "status": "default_estimated",
                        "source": "Shipped work outcome default",
                        "source_version": "base-v1",
                        "uncertainty": 1.0
                    }
                },
                {
                    "id": "exercise",
                    "effects": [{"target": "memory.stress", "operation": "subtract", "value": 0.1}],
                    "cash_flow": {"other_expenses": 2.0},
                    "evidence": {
                        "status": "default_estimated",
                        "source": "Shipped activity default",
                        "source_version": "base-v1",
                        "uncertainty": 1.0
                    }
                },
                {
                    "id": "skip_lunch",
                    "effects": [],
                    "cash_flow": {},
                    "evidence": {
                        "status": "default_estimated",
                        "source": "Shipped meal default",
                        "source_version": "base-v1",
                        "uncertainty": 1.0
                    }
                }
            ],
            "state_rules": [
                {
                    "target_state_id": "stress",
                    "intercept": 0.0,
                    "coefficients": {},
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "formula": "stress[t+1] = clamp(stress[t] + event_delta, 0, 1)",
                    "evidence": {
                        "status": "default_estimated",
                        "source": "Shipped stress dynamics default",
                        "source_version": "base-v1",
                        "uncertainty": 1.0
                    }
                },
                {
                    "target_state_id": "health",
                    "intercept": 0.0,
                    "coefficients": {"stress": -0.05},
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "formula": "health[t+1] = clamp(health[t] - 0.05 * stress[t], 0, 1)",
                    "evidence": {
                        "status": "default_estimated",
                        "source": "Shipped stress-health default",
                        "source_version": "base-v1",
                        "uncertainty": 1.0
                    }
                }
            ],
            "finance": {
                "currency": ["CAD", "CAD"],
                "status": ["default_estimated", "default_estimated"],
                "source": ["Shipped finance default", "Shipped finance default"]
            },
            "finance_rules": [
                {
                    "id": "income",
                    "target": "finance.income",
                    "terms": {"finance.income": 1.0, "cash_flow.wages": 1.0},
                    "minimum": 0.0,
                    "maximum": null,
                    "formula": "income[t+1] = income[t] + wages",
                    "evidence": {"status": "default_estimated", "source": "Shipped ledger rule", "source_version": "base-v1", "uncertainty": 1.0}
                },
                {
                    "id": "expenses",
                    "target": "finance.expenses",
                    "terms": {"finance.expenses": 1.0, "cash_flow.other_expenses": 1.0},
                    "minimum": 0.0,
                    "maximum": null,
                    "formula": "expenses[t+1] = expenses[t] + other_expenses",
                    "evidence": {"status": "default_estimated", "source": "Shipped ledger rule", "source_version": "base-v1", "uncertainty": 1.0}
                },
                {
                    "id": "money",
                    "target": "finance.money",
                    "terms": {"finance.money": 1.0, "cash_flow.wages": 1.0, "cash_flow.other_expenses": -1.0},
                    "minimum": 0.0,
                    "maximum": null,
                    "formula": "money[t+1] = max(0, money[t] + wages - other_expenses)",
                    "evidence": {"status": "default_estimated", "source": "Shipped ledger rule", "source_version": "base-v1", "uncertainty": 1.0}
                },
                {
                    "id": "savings",
                    "target": "finance.savings",
                    "terms": {"finance.savings": 1.0},
                    "minimum": 0.0,
                    "maximum": null,
                    "formula": "savings[t+1] = savings[t]",
                    "evidence": {"status": "default_estimated", "source": "Shipped ledger rule", "source_version": "base-v1", "uncertainty": 1.0}
                },
                {
                    "id": "debt",
                    "target": "finance.debt",
                    "terms": {"finance.debt": 1.0},
                    "minimum": 0.0,
                    "maximum": null,
                    "formula": "debt[t+1] = debt[t]",
                    "evidence": {"status": "default_estimated", "source": "Shipped ledger rule", "source_version": "base-v1", "uncertainty": 1.0}
                }
            ]
        }
    }))
    .unwrap()
}

#[test]
fn action_events_drive_state_and_finance_through_generic_dsl_payloads() {
    let result = run(request(1)).unwrap();
    let memory = &result.agents.memory;

    assert_eq!(memory["stress"], vec![0.6000000000000001, 1.0]);
    assert!(memory["health"][1] < memory["health"][0]);
    assert_eq!(memory["finance.income"], vec![20.0, 20.0]);
    assert_eq!(memory["finance.expenses"], vec![0.0, 4.0]);
    assert_eq!(memory["finance.money"], vec![120.0, 116.0]);
    assert!(
        result
            .events
            .iter()
            .any(|event| event.action == "skip_lunch" && event.agent_index == 1)
    );
    assert!(
        !result
            .events
            .iter()
            .any(|event| event.action == "skip_lunch" && event.agent_index == 0)
    );
    assert!(
        result
            .events
            .iter()
            .any(|event| event.action == "exercise" && event.agent_index == 1)
    );
    assert!(
        !result
            .events
            .iter()
            .any(|event| event.action == "exercise" && event.agent_index == 0)
    );
    assert_eq!(result.state_ticks.len(), 2);
    assert_eq!(result.state_ticks[0].event_counts["bad_work"], 2);
    assert_eq!(result.state_ticks[0].event_counts["exercise"], 1);
    assert_eq!(result.state_ticks[0].event_counts["skip_lunch"], 1);

    let first_bad_work = result
        .events
        .iter()
        .find(|event| event.tick == 1 && event.action == "bad_work" && event.agent_index == 0)
        .unwrap();
    assert_eq!(first_bad_work.rule_index, 0);
    assert_eq!(first_bad_work.probability, 1.0);
    assert!(first_bad_work.draw >= 0.0 && first_bad_work.draw < first_bad_work.probability);
    assert_eq!(
        first_bad_work.provenance.source,
        "Shipped work outcome default"
    );
    let first_skip_lunch = result
        .events
        .iter()
        .find(|event| event.tick == 1 && event.action == "skip_lunch")
        .unwrap();
    assert_eq!(first_skip_lunch.agent_index, 1);
    assert_eq!(first_skip_lunch.rule_index, 1);
    assert_eq!(first_skip_lunch.probability, 1.0);
    let first_exercise = result
        .events
        .iter()
        .find(|event| event.tick == 1 && event.action == "exercise")
        .unwrap();
    assert_eq!(first_exercise.agent_index, 1);
    assert_eq!(first_exercise.rule_index, 1);
    assert_eq!(first_exercise.probability, 1.0);

    let first_tick = &result.state_ticks[0];
    let low_stress = first_tick
        .agent_state_changes
        .iter()
        .find(|change| change.agent_index == 0 && change.target_state_id == "stress")
        .unwrap();
    assert_eq!(low_stress.rule_index, 0);
    assert_eq!(low_stress.before, 0.2);
    assert!((low_stress.event_delta - 0.2).abs() < 1e-12);
    assert_eq!(low_stress.equation_delta, 0.0);
    assert!((low_stress.after - 0.4).abs() < 1e-12);
    let low_stress_events = first_tick
        .event_effects
        .iter()
        .filter(|effect| effect.agent_index == 0 && effect.target_state_id == "stress")
        .collect::<Vec<_>>();
    assert_eq!(low_stress_events.len(), 1);
    assert_eq!(low_stress_events[0].event, "bad_work");
    assert_eq!(low_stress_events[0].operation, "add");
    assert_eq!(low_stress_events[0].configured_value, 0.2);
    assert_eq!(low_stress_events[0].delta, 0.2);
    assert_eq!(
        low_stress_events[0].evidence.source,
        "Shipped work outcome default"
    );
    let high_stress = first_tick
        .agent_state_changes
        .iter()
        .find(|change| change.agent_index == 1 && change.target_state_id == "stress")
        .unwrap();
    assert_eq!(high_stress.before, 0.8);
    assert!((high_stress.event_delta - 0.1).abs() < 1e-12);
    assert_eq!(high_stress.equation_delta, 0.0);
    assert!((high_stress.after - 0.9).abs() < 1e-12);
    let high_stress_events = first_tick
        .event_effects
        .iter()
        .filter(|effect| effect.agent_index == 1 && effect.target_state_id == "stress")
        .collect::<Vec<_>>();
    assert_eq!(high_stress_events.len(), 2);
    assert_eq!(high_stress_events[1].event, "exercise");
    assert_eq!(high_stress_events[1].operation, "subtract");
    assert_eq!(high_stress_events[1].configured_value, 0.1);
    assert_eq!(high_stress_events[1].delta, -0.1);
    assert_eq!(
        high_stress_events[1].evidence.source,
        "Shipped activity default"
    );
    let high_health = first_tick
        .agent_state_changes
        .iter()
        .find(|change| change.agent_index == 1 && change.target_state_id == "health")
        .unwrap();
    assert_eq!(high_health.before, 1.0);
    assert_eq!(high_health.event_delta, 0.0);
    assert!((high_health.equation_delta + 0.04).abs() < 1e-12);
    assert_eq!(high_health.after, 0.96);

    assert_eq!(first_tick.finance_changes.len(), 2);
    let low_finance = &first_tick.finance_changes[0];
    assert_eq!(low_finance.agent_index, 0);
    assert_eq!(low_finance.currency, "CAD");
    assert_eq!(low_finance.provenance.status, "default_estimated");
    assert_eq!(low_finance.provenance.source, "Shipped finance default");
    assert_eq!(low_finance.flows.wages, 10.0);
    assert_eq!(low_finance.flows.other_expenses, 0.0);
    let low_money = low_finance
        .ledger_changes
        .iter()
        .find(|change| change.ledger == "money")
        .unwrap();
    assert_eq!(low_money.before, Some(100.0));
    assert_eq!(low_money.flow_delta, 10.0);
    assert_eq!(low_money.after, Some(110.0));
    let low_income = low_finance
        .ledger_changes
        .iter()
        .find(|change| change.ledger == "income")
        .unwrap();
    assert_eq!(low_income.before, Some(0.0));
    assert_eq!(low_income.flow_delta, 10.0);
    assert_eq!(low_income.after, Some(10.0));
    let high_finance = &first_tick.finance_changes[1];
    assert_eq!(high_finance.agent_index, 1);
    assert_eq!(high_finance.flows.wages, 10.0);
    assert_eq!(high_finance.flows.other_expenses, 2.0);
    assert_eq!(
        high_finance
            .ledger_changes
            .iter()
            .find(|change| change.ledger == "money")
            .unwrap()
            .flow_delta,
        8.0
    );
    assert_eq!(
        high_finance
            .ledger_changes
            .iter()
            .find(|change| change.ledger == "expenses")
            .unwrap()
            .flow_delta,
        2.0
    );
    assert!(
        first_tick
            .finance_formula
            .as_deref()
            .unwrap()
            .contains("money[t+1]")
    );

    let event_json = serde_json::to_value(first_bad_work).unwrap();
    assert_eq!(event_json["rule_index"], 0);
    assert_eq!(event_json["probability"], 1.0);
    assert!(event_json["draw"].is_number());
    assert_eq!(event_json["provenance"]["status"], "default_estimated");
    let state_json = serde_json::to_value(first_tick).unwrap();
    assert_eq!(state_json["agent_state_changes"][0]["agent_index"], 0);
    assert!(state_json["event_effects"][0]["event"].is_string());
    assert_eq!(state_json["finance_changes"][0]["agent_index"], 0);
    assert!(
        state_json["finance_changes"][0]["ledger_changes"]
            .as_array()
            .unwrap()
            .iter()
            .any(|change| change["ledger"] == "money")
    );
    assert_eq!(state_json["finance_changes"][0]["flows"]["wages"], 10.0);

    let repeated = run(request(1)).unwrap();
    assert_eq!(result, repeated);
}
