use petraterrium_engine::agent_types::*;
use petraterrium_engine::agents::run;
use petraterrium_engine::csr::CsrMatrix;
use serde_json::json;
use std::collections::BTreeMap;

fn provenance() -> ProbabilityProvenance {
    ProbabilityProvenance {
        source: "Weighted time-use panel".to_owned(),
        version: "2026-v1".to_owned(),
        status: "present".to_owned(),
        uncertainty: 0.05,
        ..ProbabilityProvenance::default()
    }
}

fn rule(probability: f64) -> ProbabilityRule {
    ProbabilityRule {
        conditions: vec![],
        probability: Some(probability),
        provenance: provenance(),
    }
}

fn request(seed: u64) -> AgentProgramRequest {
    AgentProgramRequest {
        seed,
        ticks: 2,
        tick_hours: 12.0,
        start_hour: 18.0,
        start_weekday: 4,
        places: vec![
            PlaceInput {
                id: "A".to_owned(),
                state: BTreeMap::from([("contamination".to_owned(), 0.4)]),
            },
            PlaceInput {
                id: "B".to_owned(),
                state: BTreeMap::from([("contamination".to_owned(), 0.1)]),
            },
        ],
        agents: AgentColumnsInput {
            module: vec!["choice".to_owned(); 4],
            state: vec!["decide".to_owned(); 4],
            place: vec![0, 0, 1, 1],
            traits: BTreeMap::from([("age".to_owned(), vec![20.0, 40.0, 30.0, 60.0])]),
            trait_dictionaries: BTreeMap::new(),
            memory: BTreeMap::new(),
        },
        modules: vec![
            ModuleDefinition {
                id: "choice".to_owned(),
                entry_state: "decide".to_owned(),
                exit_states: vec!["home".to_owned(), "out".to_owned()],
                inputs: vec![],
                outputs: vec!["memory.social".to_owned()],
                states: vec!["decide".to_owned(), "home".to_owned(), "out".to_owned()],
                transitions: vec![
                    ModuleTransition {
                        id: "stay".to_owned(),
                        from_state: "decide".to_owned(),
                        to_state: "home".to_owned(),
                        rules: vec![rule(0.5)],
                        effects: vec![],
                    },
                    ModuleTransition {
                        id: "leave".to_owned(),
                        from_state: "decide".to_owned(),
                        to_state: "out".to_owned(),
                        rules: vec![rule(0.5)],
                        effects: vec![TransitionEffect {
                            target: "memory.social".to_owned(),
                            operation: "add".to_owned(),
                            value: 1.0,
                        }],
                    },
                ],
            },
            ModuleDefinition {
                id: "venue".to_owned(),
                entry_state: "choose".to_owned(),
                exit_states: vec!["bar".to_owned()],
                inputs: vec![],
                outputs: vec![],
                states: vec!["choose".to_owned(), "bar".to_owned()],
                transitions: vec![ModuleTransition {
                    id: "bar".to_owned(),
                    from_state: "choose".to_owned(),
                    to_state: "bar".to_owned(),
                    rules: vec![rule(1.0)],
                    effects: vec![],
                }],
            },
        ],
        routes: vec![ModuleRoute {
            from_module: "choice".to_owned(),
            exit_state: "out".to_owned(),
            to_module: "venue".to_owned(),
        }],
        network: Some(CsrMatrix {
            rows: 4,
            cols: 4,
            row_offsets: vec![0, 1, 2, 3, 4],
            column_indices: vec![1, 0, 3, 2],
            weights: vec![1.0; 4],
        }),
        schedules: vec![ScheduleRow {
            id: "evening".to_owned(),
            action: "routine-evening".to_owned(),
            weekdays: vec![4],
            start_hour: 17.0,
            end_hour: 23.0,
            modules: vec![],
            states: vec![],
        }],
        meaningful_actions: vec![MeaningfulAction {
            id: "call-friend".to_owned(),
            rules: vec![rule(0.25)],
        }],
        synchronization: SynchronizationConfig {
            border_every_ticks: Some(2),
            media_every_ticks: Some(1),
            weekly_leader_every_ticks: Some(2),
            border_payloads: vec![json!({"from": 0, "to": 1})],
            media_payloads: vec![json!({"topic": "sports"})],
            weekly_leader_payloads: vec![json!({"decision_log_id": "outside-core"})],
        },
    }
}

#[test]
fn agent_program_is_deterministic_and_modular() {
    let first = run(request(99)).unwrap();
    let second = run(request(99)).unwrap();
    assert_eq!(first, second);
    assert_eq!(first.agents.state.len(), 4);
    assert_eq!(
        first
            .shard_populations
            .iter()
            .map(|item| item.agents)
            .sum::<usize>(),
        4
    );
    assert!(
        first
            .synchronization
            .iter()
            .any(|item| item.kind == "weekly_leader" && item.tick == 2)
    );
    assert_eq!(first.routine_actions[0].agent_indices, vec![0, 1, 2, 3]);

    let mut single_tick = request(99);
    single_tick.ticks = 1;
    let single_tick_result = run(single_tick).unwrap();
    assert!(
        single_tick_result
            .agents
            .state
            .iter()
            .all(|state| state != "bar")
    );
}

#[test]
fn null_and_label_only_probabilities_fail_before_execution() {
    let mut null_request = request(1);
    null_request.modules[0].transitions[0].rules[0].probability = None;
    assert_eq!(run(null_request).unwrap_err().code, "UNKNOWN_PROBABILITY");

    for status in ["label_only", "inherited", "imputed", "literature_estimate"] {
        let mut non_predictive = request(1);
        non_predictive.modules[0].transitions[0].rules[0]
            .provenance
            .status = status.to_owned();
        assert_eq!(
            run(non_predictive).unwrap_err().code,
            "NON_PREDICTIVE_EVIDENCE"
        );
    }
}

#[test]
fn cross_shard_neighbor_edges_are_rejected() {
    let mut invalid = request(1);
    invalid.agents.place = vec![0, 1, 1, 1];
    let error = run(invalid).unwrap_err();
    assert_eq!(error.code, "CROSS_SHARD_NETWORK_EDGE");
}

#[test]
fn unmatched_conditional_probability_is_unknown() {
    let mut invalid = request(1);
    invalid.modules[0].inputs = vec!["trait.age".to_owned()];
    invalid.modules[0].transitions[0].rules[0].conditions = vec![NumericCondition {
        input: "trait.age".to_owned(),
        operator: "gt".to_owned(),
        value: 100.0,
    }];
    let error = run(invalid).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_PROBABILITY");
}
