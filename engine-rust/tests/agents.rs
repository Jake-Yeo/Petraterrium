use petraterrium_engine::agent_types::*;
use petraterrium_engine::agents::run;
use petraterrium_engine::csr::CsrMatrix;
use petraterrium_engine::interaction_trees::ContextValue;
use petraterrium_engine::interactions::{
    AgentStateEffect, FactorProvenance, InteractionFactor, InteractionRelationship,
    InteractionRule, RelationshipProfile, RelationshipStateEffect, TimeFactorWindow,
};
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

fn interaction_factor(id: &str) -> InteractionFactor {
    InteractionFactor {
        id: id.to_owned(),
        label: id.to_owned(),
        value: 1.0,
        provenance: FactorProvenance {
            source: "FAKE integrated interaction fixture".to_owned(),
            version: "fixture-v1".to_owned(),
            status: "measured_joint".to_owned(),
            uncertainty: 0.0,
        },
    }
}

fn request(seed: u64) -> AgentProgramRequest {
    AgentProgramRequest {
        seed,
        ticks: 2,
        continuation: None,
        tick_hours: 12.0,
        start_hour: 18.0,
        start_weekday: 4,
        places: vec![
            PlaceInput {
                id: "A".to_owned(),
                kind: "city".to_owned(),
                accepts_arrivals: true,
                allows_in_person: true,
                capacity: None,
                state: BTreeMap::from([("contamination".to_owned(), 0.4)]),
                available_decision_modules: None,
            },
            PlaceInput {
                id: "B".to_owned(),
                kind: "city".to_owned(),
                accepts_arrivals: true,
                allows_in_person: true,
                capacity: None,
                state: BTreeMap::from([("contamination".to_owned(), 0.1)]),
                available_decision_modules: None,
            },
        ],
        agents: AgentColumnsInput {
            agent_ids: (0..4).map(|index| format!("agent-{index}")).collect(),
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
                available_place_kinds: vec![],
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
                available_place_kinds: vec![],
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
            eligible_agent_indices: vec![],
            required_place_indices: vec![],
            destination_place_index: None,
            destination_place_by_agent: vec![],
            activate_module_by_agent: vec![],
            travel_by_agent: vec![],
            unavailable_reason_by_agent: vec![],
            travel_place_index: None,
            travel_ticks: None,
        }],
        meaningful_actions: vec![MeaningfulAction {
            id: "call-friend".to_owned(),
            exclusive_choice_group: None,
            rules: vec![rule(0.25)],
        }],
        interactions: InteractionProgram::default(),
        synchronization: SynchronizationConfig {
            border_every_ticks: Some(2),
            media_every_ticks: Some(1),
            weekly_leader_every_ticks: Some(2),
            border_payloads: vec![json!({"from": 0, "to": 1})],
            media_payloads: vec![json!({"topic": "sports"})],
            weekly_leader_payloads: vec![json!({"decision_log_id": "outside-core"})],
        },
        state_dynamics: StateDynamicsProgram::default(),
    }
}

fn talk_tree() -> serde_json::Value {
    json!({
        "id": "talk-tree",
        "name": "Talk",
        "version": "fixture-v1",
        "entry_node": "talk",
        "allowed_channels": ["in_person"],
        "co_location_policy": "required",
        "nodes": [
            {"id": "talk", "label": "Talk", "terminal": false},
            {"id": "connected", "label": "Connected", "terminal": true}
        ],
        "transitions": [{
            "id": "talk-connects",
            "from_node": "talk",
            "to_node": "connected",
            "outcome": "connected",
            "probability": 1.0,
            "probability_factors": [
                {
                    "id": "actor-age",
                    "label": "Actor age",
                    "cases": [{
                        "id": "observed",
                        "conditions": [{"input": "actor.trait.age", "operator": "gte", "value": 0}],
                        "multiplier": 1
                    }],
                    "evidence": {
                        "source": "FAKE talk outcome panel",
                        "version": "fixture-v1",
                        "status": "measured_joint",
                        "uncertainty": 0.0
                    }
                },
                {
                    "id": "target-age",
                    "label": "Target age",
                    "cases": [{
                        "id": "observed",
                        "conditions": [{"input": "target.trait.age", "operator": "gte", "value": 0}],
                        "multiplier": 1
                    }],
                    "evidence": {
                        "source": "FAKE talk outcome panel",
                        "version": "fixture-v1",
                        "status": "measured_joint",
                        "uncertainty": 0.0
                    }
                },
                {
                    "id": "pair-trust",
                    "label": "Pair trust",
                    "cases": [{
                        "id": "observed",
                        "conditions": [{"input": "relationship.state.trust", "operator": "gte", "value": -1}],
                        "multiplier": 1
                    }],
                    "evidence": {
                        "source": "FAKE talk outcome panel",
                        "version": "fixture-v1",
                        "status": "measured_joint",
                        "uncertainty": 0.0
                    }
                },
                {
                    "id": "live-place",
                    "label": "Live place state",
                    "cases": [{
                        "id": "observed",
                        "conditions": [
                            {"input": "place.state.occupancy", "operator": "gte", "value": 0},
                            {"input": "place.state.crowd_density", "operator": "gte", "value": 0},
                            {"input": "place.state.contamination", "operator": "gte", "value": 0}
                        ],
                        "multiplier": 1
                    }],
                    "evidence": {
                        "source": "FAKE talk outcome panel",
                        "version": "fixture-v1",
                        "status": "measured_joint",
                        "uncertainty": 0.0
                    }
                },
                {
                    "id": "runtime-time",
                    "label": "Runtime time",
                    "cases": [{
                        "id": "observed",
                        "conditions": [{"input": "time.hour", "operator": "gte", "value": 0}],
                        "multiplier": 1
                    }],
                    "evidence": {
                        "source": "FAKE talk outcome panel",
                        "version": "fixture-v1",
                        "status": "measured_joint",
                        "uncertainty": 0.0
                    }
                }
            ],
            "evidence": {
                "source": "FAKE talk outcome panel",
                "version": "fixture-v1",
                "status": "measured_joint",
                "uncertainty": 0.0
            },
            "effects": [
                {
                    "kind": "agent_state",
                    "participant": "actor",
                    "field": "mood",
                    "operation": "add",
                    "value": 0.2,
                    "minimum": -1.0,
                    "maximum": 1.0
                },
                {
                    "kind": "agent_state",
                    "participant": "target",
                    "field": "mood",
                    "operation": "add",
                    "value": 0.4,
                    "minimum": -1.0,
                    "maximum": 1.0
                },
                {
                    "kind": "relationship_state",
                    "field": "trust",
                    "operation": "add",
                    "value": 0.1,
                    "minimum": -1.0,
                    "maximum": 1.0
                }
            ]
        }]
    })
}

fn interaction_tree_request(colocated: bool) -> AgentProgramRequest {
    let mut configured = request(41);
    configured.ticks = 1;
    configured.network = None;
    configured.places[0].capacity = Some(4);
    configured.agents.state = vec![
        "decide".to_owned(),
        "home".to_owned(),
        "home".to_owned(),
        "home".to_owned(),
    ];
    configured.agents.place = if colocated {
        vec![0, 0, 1, 1]
    } else {
        vec![0, 1, 1, 1]
    };
    configured
        .agents
        .memory
        .insert("mood".to_owned(), vec![0.0; 4]);
    configured.schedules[0].states = vec!["decide".to_owned()];
    configured.interactions = InteractionProgram {
        relationships: vec![InteractionRelationship {
            source_index: 0,
            target_index: 1,
            kind: "family".to_owned(),
            weight: 0.5,
            trust: 0.5,
            similarity: 0.5,
        }],
        trees: BTreeMap::from([("talk-tree".to_owned(), talk_tree())]),
        rules: vec![InteractionRule {
            id: "evening-talk-tree".to_owned(),
            source_action: "routine-evening".to_owned(),
            interaction_type: "talk".to_owned(),
            channel: "in_person".to_owned(),
            max_targets_per_initiator: 1,
            allowed_relationships: vec!["family".to_owned()],
            allowed_place_kinds: vec!["city".to_owned()],
            base_factor: interaction_factor("base"),
            relationship_factors: BTreeMap::from([(
                "family".to_owned(),
                interaction_factor("family"),
            )]),
            colocation_factors: BTreeMap::from([(
                "same_specific_place".to_owned(),
                interaction_factor("same-place"),
            )]),
            place_factors: BTreeMap::from([("city".to_owned(), interaction_factor("city"))]),
            time_factors: vec![TimeFactorWindow {
                weekdays: vec![4],
                start_hour: 0.0,
                end_hour: 24.0,
                factor: interaction_factor("friday"),
            }],
            context_factors: vec![],
            unrelated_relationship: None,
            agent_effects: vec![AgentStateEffect {
                recipient: "target".to_owned(),
                state: "mood".to_owned(),
                delta: 0.9,
                minimum: -1.0,
                maximum: 1.0,
                scale_by: vec![],
            }],
            relationship_effects: vec![RelationshipStateEffect {
                direction: "initiator_to_target".to_owned(),
                field: "trust".to_owned(),
                delta: 0.4,
                minimum: -1.0,
                maximum: 1.0,
            }],
            interaction_tree_id: Some("talk-tree".to_owned()),
            interaction_tree_context: BTreeMap::new(),
        }],
    };
    configured
}

fn scheduled_location_request() -> AgentProgramRequest {
    let mut configured = request(73);
    configured.ticks = 15;
    configured.tick_hours = 1.0;
    configured.start_hour = 8.0;
    configured.start_weekday = 4;
    configured.places = vec![
        PlaceInput {
            id: "home".to_owned(),
            kind: "home".to_owned(),
            accepts_arrivals: true,
            allows_in_person: true,
            capacity: None,
            state: BTreeMap::new(),
            available_decision_modules: None,
        },
        PlaceInput {
            id: "travel".to_owned(),
            kind: "transit".to_owned(),
            accepts_arrivals: true,
            allows_in_person: false,
            capacity: None,
            state: BTreeMap::new(),
            available_decision_modules: None,
        },
        PlaceInput {
            id: "work".to_owned(),
            kind: "workplace".to_owned(),
            accepts_arrivals: true,
            allows_in_person: true,
            capacity: None,
            state: BTreeMap::new(),
            available_decision_modules: None,
        },
        PlaceInput {
            id: "bar".to_owned(),
            kind: "bar".to_owned(),
            accepts_arrivals: true,
            allows_in_person: true,
            capacity: None,
            state: BTreeMap::new(),
            available_decision_modules: None,
        },
    ];
    configured.agents = AgentColumnsInput {
        agent_ids: vec!["agent-0".to_owned()],
        module: vec!["choice".to_owned()],
        state: vec!["decide".to_owned()],
        place: vec![0],
        traits: BTreeMap::from([("age".to_owned(), vec![20.0])]),
        trait_dictionaries: BTreeMap::new(),
        memory: BTreeMap::new(),
    };
    configured.network = None;
    configured.meaningful_actions.clear();
    configured.interactions = InteractionProgram::default();
    configured.synchronization = SynchronizationConfig::default();
    configured.schedules = vec![
        ScheduleRow {
            id: "work-shift".to_owned(),
            action: "work".to_owned(),
            weekdays: vec![4],
            start_hour: 8.0,
            end_hour: 17.0,
            modules: vec![],
            states: vec![],
            eligible_agent_indices: vec![],
            required_place_indices: vec![2],
            destination_place_index: Some(2),
            destination_place_by_agent: vec![],
            activate_module_by_agent: vec![],
            travel_by_agent: vec![],
            unavailable_reason_by_agent: vec![],
            travel_place_index: Some(1),
            travel_ticks: Some(1),
        },
        ScheduleRow {
            id: "bar-visit".to_owned(),
            action: "socialize".to_owned(),
            weekdays: vec![4],
            start_hour: 17.0,
            end_hour: 20.0,
            modules: vec![],
            states: vec![],
            eligible_agent_indices: vec![],
            required_place_indices: vec![3],
            destination_place_index: Some(3),
            destination_place_by_agent: vec![],
            activate_module_by_agent: vec![],
            travel_by_agent: vec![],
            unavailable_reason_by_agent: vec![],
            travel_place_index: Some(1),
            travel_ticks: Some(1),
        },
        ScheduleRow {
            id: "return-home".to_owned(),
            action: "at-home".to_owned(),
            weekdays: vec![4],
            start_hour: 20.0,
            end_hour: 24.0,
            modules: vec![],
            states: vec![],
            eligible_agent_indices: vec![],
            required_place_indices: vec![0],
            destination_place_index: Some(0),
            destination_place_by_agent: vec![],
            activate_module_by_agent: vec![],
            travel_by_agent: vec![],
            unavailable_reason_by_agent: vec![],
            travel_place_index: Some(1),
            travel_ticks: Some(1),
        },
    ];
    configured
}

fn household_return_request(destination_place_by_agent: Vec<Option<usize>>) -> AgentProgramRequest {
    let mut configured = request(83);
    configured.ticks = 2;
    configured.tick_hours = 1.0;
    configured.start_hour = 20.0;
    configured.start_weekday = 4;
    configured.places = vec![
        PlaceInput {
            id: "household-a".to_owned(),
            kind: "home".to_owned(),
            accepts_arrivals: true,
            allows_in_person: true,
            capacity: None,
            state: BTreeMap::new(),
            available_decision_modules: None,
        },
        PlaceInput {
            id: "travel".to_owned(),
            kind: "transit".to_owned(),
            accepts_arrivals: true,
            allows_in_person: false,
            capacity: None,
            state: BTreeMap::new(),
            available_decision_modules: None,
        },
        PlaceInput {
            id: "work".to_owned(),
            kind: "workplace".to_owned(),
            accepts_arrivals: true,
            allows_in_person: true,
            capacity: None,
            state: BTreeMap::new(),
            available_decision_modules: None,
        },
        PlaceInput {
            id: "household-b".to_owned(),
            kind: "home".to_owned(),
            accepts_arrivals: true,
            allows_in_person: true,
            capacity: None,
            state: BTreeMap::new(),
            available_decision_modules: None,
        },
    ];
    configured.agents = AgentColumnsInput {
        agent_ids: vec![
            "household-a-adult".to_owned(),
            "household-b-adult".to_owned(),
        ],
        module: vec!["choice".to_owned(); 2],
        state: vec!["decide".to_owned(); 2],
        place: vec![2; 2],
        traits: BTreeMap::from([("age".to_owned(), vec![34.0, 47.0])]),
        trait_dictionaries: BTreeMap::new(),
        memory: BTreeMap::new(),
    };
    configured.network = None;
    configured.meaningful_actions.clear();
    configured.interactions = InteractionProgram::default();
    configured.synchronization = SynchronizationConfig::default();
    configured.schedules = vec![ScheduleRow {
        id: "return-home".to_owned(),
        action: "at-home".to_owned(),
        weekdays: vec![4],
        start_hour: 20.0,
        end_hour: 24.0,
        modules: vec![],
        states: vec![],
        eligible_agent_indices: vec![],
        required_place_indices: vec![0, 3],
        destination_place_index: None,
        destination_place_by_agent,
        activate_module_by_agent: vec![],
        travel_by_agent: vec![],
        unavailable_reason_by_agent: vec![],
        travel_place_index: Some(1),
        travel_ticks: Some(1),
    }];
    configured
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
fn continuation_chunks_match_one_linear_numeric_run() {
    let mut monolithic_request = request(107);
    monolithic_request.ticks = 4;
    let monolithic = run(monolithic_request).unwrap();

    let mut first_request = request(107);
    first_request.ticks = 2;
    let agent_ids = first_request.agents.agent_ids.clone();
    let first = run(first_request).unwrap();

    let mut second_request = request(107);
    second_request.ticks = 2;
    second_request.continuation = Some(first.continuation.clone());
    second_request.agents = AgentColumnsInput {
        agent_ids,
        module: first.agents.module.clone(),
        state: first.agents.state.clone(),
        place: first.agents.place.clone(),
        traits: first.agents.traits.clone(),
        trait_dictionaries: first.agents.trait_dictionaries.clone(),
        memory: first.agents.memory.clone(),
    };
    let second = run(second_request).unwrap();

    assert_eq!(second.ticks, 4);
    assert_eq!(second.agents, monolithic.agents);
    assert_eq!(second.continuation, monolithic.continuation);
    assert_eq!(second.relationships, monolithic.relationships);

    let mut transition_counts = first.transition_counts;
    transition_counts.extend(second.transition_counts);
    assert_eq!(transition_counts, monolithic.transition_counts);

    let mut transition_outcomes = first.transition_outcomes;
    transition_outcomes.extend(second.transition_outcomes);
    assert_eq!(transition_outcomes, monolithic.transition_outcomes);

    let mut events = first.events;
    events.extend(second.events);
    assert_eq!(events, monolithic.events);

    let mut routines = first.routine_actions;
    routines.extend(second.routine_actions);
    assert_eq!(routines, monolithic.routine_actions);

    let mut synchronization = first.synchronization;
    synchronization.extend(second.synchronization);
    assert_eq!(synchronization, monolithic.synchronization);
}

#[test]
fn continuation_preserves_travel_across_chunk_boundaries() {
    let monolithic = run(scheduled_location_request()).unwrap();

    let mut first_request = scheduled_location_request();
    first_request.ticks = 1;
    let agent_ids = first_request.agents.agent_ids.clone();
    let first = run(first_request).unwrap();
    assert!(first.continuation.active_travel[0].is_some());

    let mut second_request = scheduled_location_request();
    second_request.ticks = 14;
    second_request.continuation = Some(first.continuation.clone());
    second_request.agents = AgentColumnsInput {
        agent_ids,
        module: first.agents.module.clone(),
        state: first.agents.state.clone(),
        place: first.agents.place.clone(),
        traits: first.agents.traits.clone(),
        trait_dictionaries: first.agents.trait_dictionaries.clone(),
        memory: first.agents.memory.clone(),
    };
    let second = run(second_request).unwrap();

    assert_eq!(second.agents, monolithic.agents);
    assert_eq!(second.continuation, monolithic.continuation);
    let mut locations = first.location_transitions;
    locations.extend(second.location_transitions);
    assert_eq!(locations, monolithic.location_transitions);
    let mut routines = first.routine_actions;
    routines.extend(second.routine_actions);
    assert_eq!(routines, monolithic.routine_actions);
    let mut unavailable = first.routine_unavailable;
    unavailable.extend(second.routine_unavailable);
    assert_eq!(unavailable, monolithic.routine_unavailable);
}

#[test]
fn transition_outcomes_record_each_selected_agent_path_deterministically() {
    let first = run(request(113)).unwrap();
    let second = run(request(113)).unwrap();

    assert_eq!(first.transition_outcomes, second.transition_outcomes);
    let first_tick = first
        .transition_outcomes
        .iter()
        .filter(|outcome| outcome.tick == 1)
        .collect::<Vec<_>>();
    assert_eq!(first_tick.len(), 4);
    assert_eq!(
        first_tick
            .iter()
            .map(|outcome| outcome.agent_index)
            .collect::<Vec<_>>(),
        vec![0, 1, 2, 3]
    );
    assert!(first_tick.iter().all(|outcome| {
        outcome.module == "choice"
            && outcome.from_state == "decide"
            && outcome.provenance.source == "Weighted time-use panel"
            && outcome.probability == 0.5
    }));
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
fn inherited_measured_evidence_executes_with_resolution_receipts() {
    let mut inherited = request(1);
    for module in &mut inherited.modules {
        for transition in &mut module.transitions {
            for rule in &mut transition.rules {
                rule.provenance.resolution_status = Some("inherited".to_owned());
                rule.provenance.source_places = vec!["country:CA".to_owned()];
            }
        }
    }

    let output = run(inherited).unwrap();
    assert!(output.transition_outcomes.iter().all(|outcome| {
        outcome.provenance.status == "present"
            && outcome.provenance.resolution_status.as_deref() == Some("inherited")
            && outcome.provenance.source_places == ["country:CA"]
    }));

    let mut imputed = request(1);
    imputed.modules[0].transitions[0].rules[0]
        .provenance
        .resolution_status = Some("imputed".to_owned());
    assert_eq!(run(imputed).unwrap_err().code, "NON_PREDICTIVE_EVIDENCE");
}

#[test]
fn scheduled_actions_drive_evidence_backed_colocated_interactions() {
    let mut configured = request(17);
    configured.ticks = 1;
    configured.interactions = InteractionProgram {
        relationships: vec![],
        trees: BTreeMap::new(),
        rules: vec![InteractionRule {
            id: "evening-talk".to_owned(),
            source_action: "routine-evening".to_owned(),
            interaction_type: "talk".to_owned(),
            channel: "in_person".to_owned(),
            max_targets_per_initiator: 1,
            allowed_relationships: vec!["stranger".to_owned()],
            allowed_place_kinds: vec!["city".to_owned()],
            base_factor: interaction_factor("base"),
            relationship_factors: BTreeMap::from([(
                "stranger".to_owned(),
                interaction_factor("stranger"),
            )]),
            colocation_factors: BTreeMap::from([(
                "same_specific_place".to_owned(),
                interaction_factor("same-place"),
            )]),
            place_factors: BTreeMap::from([("city".to_owned(), interaction_factor("city"))]),
            time_factors: vec![TimeFactorWindow {
                weekdays: vec![4],
                start_hour: 0.0,
                end_hour: 24.0,
                factor: interaction_factor("friday"),
            }],
            context_factors: vec![],
            unrelated_relationship: Some(RelationshipProfile {
                kind: "stranger".to_owned(),
                weight: 0.0,
                trust: 0.0,
                similarity: 0.0,
            }),
            agent_effects: vec![],
            relationship_effects: vec![],
            interaction_tree_id: None,
            interaction_tree_context: BTreeMap::new(),
        }],
    };

    let result = run(configured).unwrap();

    assert_eq!(result.interactions.len(), 4);
    assert!(
        result
            .interactions
            .iter()
            .all(|event| event.initiator_id != event.target_id)
    );
    assert!(
        result
            .blocked_interactions
            .iter()
            .any(|blocked| blocked.reason.contains("same specific place"))
    );
}

#[test]
fn schedules_record_home_travel_work_bar_and_home_locations() {
    let first = run(scheduled_location_request()).unwrap();
    let second = run(scheduled_location_request()).unwrap();

    assert_eq!(first, second);
    assert_eq!(first.agents.place, vec![0]);
    assert_eq!(
        first
            .location_transitions
            .iter()
            .map(|record| (
                record.tick,
                record.source.as_str(),
                record.phase.as_str(),
                record.from_place_index,
                record.to_place_index,
                record.destination_place_index,
            ))
            .collect::<Vec<_>>(),
        vec![
            (1, "work-shift", "travel_started", 0, 1, 2),
            (2, "work-shift", "travel_arrived", 1, 2, 2),
            (10, "bar-visit", "travel_started", 2, 1, 3),
            (11, "bar-visit", "travel_arrived", 1, 3, 3),
            (13, "return-home", "travel_started", 3, 1, 0),
            (14, "return-home", "travel_arrived", 1, 0, 0),
        ]
    );
    assert!(first.routine_actions.iter().any(|batch| {
        batch.tick == 2 && batch.schedule == "work-shift" && batch.agent_indices == vec![0]
    }));
    assert!(first.routine_actions.iter().any(|batch| {
        batch.tick == 11 && batch.schedule == "bar-visit" && batch.agent_indices == vec![0]
    }));
    assert!(first.routine_actions.iter().any(|batch| {
        batch.tick == 14 && batch.schedule == "return-home" && batch.agent_indices == vec![0]
    }));
    assert!(
        first
            .routine_actions
            .iter()
            .all(|batch| !matches!(batch.tick, 1 | 10 | 13))
    );
}

#[test]
fn evidenced_travel_delays_place_specific_decision_until_arrival() {
    let mut configured = scheduled_location_request();
    configured.ticks = 2;
    configured.schedules.truncate(1);
    configured.schedules[0].activate_module_by_agent = vec![Some("venue".to_owned())];
    configured.schedules[0].travel_place_index = None;
    configured.schedules[0].travel_ticks = None;
    configured.schedules[0].eligible_agent_indices = vec![0];
    configured.schedules[0].travel_by_agent = vec![Some(ScheduledTravelPlan {
        from_place_index: 0,
        travel_place_index: 1,
        travel_ticks: 1,
        route_id: "home-to-work-2025".to_owned(),
        provenance: json!({
            "source_title": "Vancouver travel survey",
            "source_version": "2025",
            "source_date": "2025-04-01",
            "licence": "Open Government Licence",
            "evidence_id": "vancouver-travel-2025",
            "status": "measured"
        }),
    })];

    let result = run(configured).unwrap();

    assert_eq!(result.agents.place, vec![2]);
    assert!(result.routine_unavailable.is_empty());
    assert!(
        result
            .transition_outcomes
            .iter()
            .all(|item| { item.tick != 1 || item.module != "venue" })
    );
    assert!(
        result
            .transition_outcomes
            .iter()
            .any(|item| { item.tick == 2 && item.module == "venue" && item.transition == "bar" })
    );
    assert_eq!(
        result.location_transitions[0].provenance,
        Some(json!({
            "source_title": "Vancouver travel survey",
            "source_version": "2025",
            "source_date": "2025-04-01",
            "licence": "Open Government Licence",
            "evidence_id": "vancouver-travel-2025",
            "status": "measured"
        }))
    );
}

#[test]
fn schedule_cannot_activate_module_outside_its_available_place_kind() {
    let mut configured = scheduled_location_request();
    configured.ticks = 2;
    configured.schedules.truncate(1);
    configured.schedules[0].activate_module_by_agent = vec![Some("venue".to_owned())];
    configured.modules[1].available_place_kinds = vec!["bar".to_owned()];

    let result = run(configured).unwrap();

    assert_eq!(result.agents.place, vec![2]);
    assert!(
        result
            .transition_outcomes
            .iter()
            .all(|item| item.module != "venue")
    );
    assert_eq!(result.routine_unavailable.len(), 1);
    assert_eq!(
        result.routine_unavailable[0].decision_module.as_deref(),
        Some("venue")
    );
    assert!(
        result.routine_unavailable[0]
            .reason
            .contains("requires place kind bar")
    );
}

#[test]
fn missing_route_evidence_blocks_travel_and_explains_unavailable_decision() {
    let mut configured = scheduled_location_request();
    configured.ticks = 2;
    configured.schedules.truncate(1);
    configured.schedules[0].activate_module_by_agent = vec![Some("venue".to_owned())];
    configured.schedules[0].travel_place_index = None;
    configured.schedules[0].travel_ticks = None;
    configured.schedules[0].eligible_agent_indices = vec![0];
    configured.schedules[0].travel_by_agent = vec![None];
    configured.schedules[0].unavailable_reason_by_agent = vec![Some(
        "Work decision unavailable — no confirmed home to work route evidence".to_owned(),
    )];

    let result = run(configured).unwrap();

    assert_eq!(result.agents.place, vec![0]);
    assert!(result.location_transitions.is_empty());
    assert!(result.routine_actions.is_empty());
    assert_eq!(result.routine_unavailable.len(), 1);
    assert_eq!(result.routine_unavailable[0].tick, 1);
    assert_eq!(
        result.routine_unavailable[0].reason,
        "Work decision unavailable — no confirmed home to work route evidence"
    );
    assert_eq!(
        result.routine_unavailable[0].decision_module.as_deref(),
        Some("venue")
    );
}

#[test]
fn closed_place_blocks_immediate_schedule_move() {
    let mut configured = scheduled_location_request();
    configured.ticks = 1;
    configured.schedules.truncate(1);
    configured.schedules[0].travel_place_index = None;
    configured.schedules[0].travel_ticks = None;
    configured.places[2].accepts_arrivals = false;

    let result = run(configured).unwrap();

    assert_eq!(result.agents.place, vec![0]);
    assert!(result.location_transitions.is_empty());
    assert_eq!(result.routine_unavailable.len(), 1);
    assert!(
        result.routine_unavailable[0]
            .reason
            .contains("does not accept arrivals")
    );
}

#[test]
fn simultaneous_immediate_moves_never_exceed_capacity() {
    let mut configured = scheduled_location_request();
    configured.ticks = 1;
    configured.agents = AgentColumnsInput {
        agent_ids: (0..3).map(|index| format!("agent-{index}")).collect(),
        module: vec!["choice".to_owned(); 3],
        state: vec!["decide".to_owned(); 3],
        place: vec![0; 3],
        traits: BTreeMap::from([("age".to_owned(), vec![20.0, 30.0, 40.0])]),
        trait_dictionaries: BTreeMap::new(),
        memory: BTreeMap::new(),
    };
    configured.schedules.truncate(1);
    configured.schedules[0].travel_place_index = None;
    configured.schedules[0].travel_ticks = None;
    configured.places[2].capacity = Some(1);

    let first = run(configured.clone()).unwrap();
    let second = run(configured).unwrap();

    assert_eq!(first, second);
    assert_eq!(first.agents.place, vec![2, 0, 0]);
    assert_eq!(first.routine_unavailable.len(), 2);
    assert_eq!(
        first
            .routine_unavailable
            .iter()
            .map(|item| item.agent_index)
            .collect::<Vec<_>>(),
        vec![1, 2]
    );
    assert!(
        first
            .routine_unavailable
            .iter()
            .all(|item| item.reason.contains("capacity 1"))
    );
}

#[test]
fn initial_occupancy_cannot_exceed_place_capacity() {
    let mut configured = request(17);
    configured.places[0].capacity = Some(1);

    let error = run(configured).unwrap_err();

    assert_eq!(error.code, "INITIAL_PLACE_CAPACITY_EXCEEDED");
    assert_eq!(error.path.as_deref(), Some("places.0.capacity"));
}

#[test]
fn simultaneous_travel_arrivals_respect_capacity_and_remain_in_flight() {
    let mut configured = scheduled_location_request();
    configured.ticks = 2;
    configured.agents = AgentColumnsInput {
        agent_ids: vec!["agent-0".to_owned(), "agent-1".to_owned()],
        module: vec!["choice".to_owned(); 2],
        state: vec!["decide".to_owned(); 2],
        place: vec![0; 2],
        traits: BTreeMap::from([("age".to_owned(), vec![20.0, 30.0])]),
        trait_dictionaries: BTreeMap::new(),
        memory: BTreeMap::new(),
    };
    configured.schedules.truncate(1);
    configured.places[2].capacity = Some(1);

    let result = run(configured).unwrap();

    assert_eq!(result.agents.place, vec![2, 1]);
    assert!(result.continuation.active_travel[0].is_none());
    assert_eq!(
        result.continuation.active_travel[1]
            .as_ref()
            .map(|travel| travel.arrival_tick),
        Some(3)
    );
    assert_eq!(result.routine_unavailable.len(), 1);
    assert_eq!(result.routine_unavailable[0].agent_index, 1);
    assert!(result.routine_unavailable[0].reason.contains("capacity 1"));
}

#[test]
fn capacity_blocked_travel_is_checkpoint_equivalent() {
    let mut configured = scheduled_location_request();
    configured.ticks = 3;
    configured.agents = AgentColumnsInput {
        agent_ids: vec!["agent-0".to_owned(), "agent-1".to_owned()],
        module: vec!["choice".to_owned(); 2],
        state: vec!["decide".to_owned(); 2],
        place: vec![0; 2],
        traits: BTreeMap::from([("age".to_owned(), vec![20.0, 30.0])]),
        trait_dictionaries: BTreeMap::new(),
        memory: BTreeMap::new(),
    };
    configured.schedules.truncate(1);
    configured.places[2].capacity = Some(1);
    let monolithic = run(configured.clone()).unwrap();

    let mut first_request = configured.clone();
    first_request.ticks = 2;
    let agent_ids = first_request.agents.agent_ids.clone();
    let first = run(first_request).unwrap();
    let mut second_request = configured;
    second_request.ticks = 1;
    second_request.continuation = Some(first.continuation.clone());
    second_request.agents = AgentColumnsInput {
        agent_ids,
        module: first.agents.module.clone(),
        state: first.agents.state.clone(),
        place: first.agents.place.clone(),
        traits: first.agents.traits.clone(),
        trait_dictionaries: first.agents.trait_dictionaries.clone(),
        memory: first.agents.memory.clone(),
    };
    let second = run(second_request).unwrap();

    assert_eq!(second.agents, monolithic.agents);
    assert_eq!(second.continuation, monolithic.continuation);
    let mut unavailable = first.routine_unavailable;
    unavailable.extend(second.routine_unavailable);
    assert_eq!(unavailable, monolithic.routine_unavailable);
    let mut locations = first.location_transitions;
    locations.extend(second.location_transitions);
    assert_eq!(locations, monolithic.location_transitions);
}

#[test]
fn place_closure_blocks_an_in_flight_arrival() {
    let mut first_request = scheduled_location_request();
    first_request.ticks = 1;
    first_request.schedules.truncate(1);
    let agent_ids = first_request.agents.agent_ids.clone();
    let first = run(first_request).unwrap();

    let mut second_request = scheduled_location_request();
    second_request.ticks = 1;
    second_request.schedules.truncate(1);
    second_request.places[2].accepts_arrivals = false;
    second_request.continuation = Some(first.continuation.clone());
    second_request.agents = AgentColumnsInput {
        agent_ids,
        module: first.agents.module,
        state: first.agents.state,
        place: first.agents.place,
        traits: first.agents.traits,
        trait_dictionaries: first.agents.trait_dictionaries,
        memory: first.agents.memory,
    };

    let second = run(second_request).unwrap();

    assert_eq!(second.agents.place, vec![1]);
    assert_eq!(
        second.continuation.active_travel[0]
            .as_ref()
            .map(|travel| travel.arrival_tick),
        Some(3)
    );
    assert_eq!(second.routine_unavailable.len(), 1);
    assert!(
        second.routine_unavailable[0]
            .reason
            .contains("does not accept arrivals")
    );
}

#[test]
fn place_restricted_module_is_unavailable_outside_its_place_kind() {
    let mut configured = request(211);
    configured.ticks = 1;
    configured.network = None;
    configured.modules[0].available_place_kinds = vec!["bar".to_owned()];

    let blocked = run(configured.clone()).unwrap();

    assert_eq!(blocked.agents.state, vec!["decide"; 4]);
    assert!(blocked.transition_outcomes.is_empty());
    assert_eq!(blocked.routine_unavailable.len(), 4);
    assert!(
        blocked
            .routine_unavailable
            .iter()
            .all(|item| item.reason.contains("requires place kind bar"))
    );

    configured.places[0].kind = "bar".to_owned();
    configured.places[1].kind = "bar".to_owned();
    let available = run(configured).unwrap();
    assert_eq!(available.transition_outcomes.len(), 4);
    assert!(available.routine_unavailable.is_empty());
}

#[test]
fn one_schedule_returns_two_households_to_distinct_homes() {
    let result = run(household_return_request(vec![Some(0), Some(3)])).unwrap();

    assert_eq!(result.agents.place, vec![0, 3]);
    assert_eq!(
        result
            .location_transitions
            .iter()
            .map(|record| (
                record.tick,
                record.agent_index,
                record.phase.as_str(),
                record.from_place_index,
                record.to_place_index,
                record.destination_place_index,
            ))
            .collect::<Vec<_>>(),
        vec![
            (1, 0, "travel_started", 2, 1, 0),
            (1, 1, "travel_started", 2, 1, 3),
            (2, 0, "travel_arrived", 1, 0, 0),
            (2, 1, "travel_arrived", 1, 3, 3),
        ]
    );
    assert_eq!(result.routine_actions.len(), 1);
    assert_eq!(result.routine_actions[0].tick, 2);
    assert_eq!(result.routine_actions[0].agent_indices, vec![0, 1]);
}

#[test]
fn per_agent_schedule_destination_requires_one_entry_per_agent() {
    let error = run(household_return_request(vec![Some(0)])).unwrap_err();

    assert_eq!(error.code, "INVALID_SCHEDULE_DESTINATION_COLUMN");
    assert_eq!(
        error.path.as_deref(),
        Some("schedules.0.destination_place_by_agent")
    );
}

#[test]
fn required_places_gate_schedule_actions() {
    let mut configured = request(29);
    configured.ticks = 1;
    configured.network = None;
    configured.agents.place = vec![0; 4];
    configured.schedules[0].required_place_indices = vec![1];

    let result = run(configured).unwrap();

    assert!(result.routine_actions.is_empty());
}

#[test]
fn scheduled_relocation_prevents_in_person_interaction_across_places() {
    let mut configured = interaction_tree_request(true);
    configured.schedules[0].destination_place_index = Some(1);
    configured.schedules[0].required_place_indices = vec![1];

    let result = run(configured).unwrap();

    assert_eq!(result.agents.place[0], 1);
    assert!(result.interactions.is_empty());
    assert!(result.blocked_interactions.iter().any(|blocked| {
        blocked.initiator_id == "agent-0"
            && blocked.target_id.as_deref() == Some("agent-1")
            && blocked.reason == "agents are not at the same specific place"
    }));
    assert_eq!(
        result.location_transitions,
        vec![LocationTransitionRecord {
            tick: 1,
            agent_index: 0,
            source: "evening".to_owned(),
            phase: "schedule_move".to_owned(),
            from_place_index: 0,
            to_place_index: 1,
            destination_place_index: 1,
            provenance: None,
        }]
    );
}

#[test]
fn colocated_talk_tree_updates_both_agents_and_relationship_atomically() {
    let result = run(interaction_tree_request(true)).unwrap();

    assert!((result.agents.memory["mood"][0] - 0.2).abs() < 1e-12);
    assert!((result.agents.memory["mood"][1] - 0.4).abs() < 1e-12);
    assert!((result.relationships[0].trust - 0.6).abs() < 1e-12);
    assert_eq!(result.interactions.len(), 1);
    let trace = result.interactions[0].interaction_tree.as_ref().unwrap();
    assert_eq!(trace.tree_id, "talk-tree");
    assert_eq!(trace.outcome, "connected");
    assert_eq!(trace.path.len(), 1);
    assert_eq!(trace.path[0].transition_id, "talk-connects");
    assert_eq!(trace.path[0].evidence.source, "FAKE talk outcome panel");
    let factor_inputs = trace.path[0].outgoing_probabilities[0]
        .factors
        .iter()
        .flat_map(|factor| factor.inputs.clone())
        .collect::<BTreeMap<_, _>>();
    assert_eq!(factor_inputs["actor.trait.age"], ContextValue::Number(20.0));
    assert_eq!(
        factor_inputs["target.trait.age"],
        ContextValue::Number(40.0)
    );
    assert_eq!(
        factor_inputs["relationship.state.trust"],
        ContextValue::Number(0.5)
    );
    assert_eq!(
        factor_inputs["place.state.occupancy"],
        ContextValue::Number(2.0)
    );
    assert_eq!(
        factor_inputs["place.state.crowd_density"],
        ContextValue::Number(0.5)
    );
    assert_eq!(
        factor_inputs["place.state.contamination"],
        ContextValue::Number(0.4)
    );
    assert_eq!(factor_inputs["time.hour"], ContextValue::Number(18.0));
    assert_eq!(result.interactions[0].state_deltas.len(), 2);
    assert_eq!(result.interactions[0].relationship_deltas.len(), 1);

    let separated = run(interaction_tree_request(false)).unwrap();
    assert!(separated.interactions.is_empty());
    assert_eq!(separated.agents.memory["mood"], vec![0.0; 4]);
    assert!((separated.relationships[0].trust - 0.5).abs() < 1e-12);
    assert!(separated.blocked_interactions.iter().any(|blocked| {
        blocked.target_id.as_deref() == Some("agent-1")
            && blocked.reason == "agents are not at the same specific place"
    }));
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
        categorical_value: None,
    }];
    let error = run(invalid).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_PROBABILITY");
}

#[test]
fn current_place_kind_selects_a_live_probability_rule() {
    let mut configured = request(1);
    configured.ticks = 1;
    configured.network = None;
    configured.agents.state = vec!["decide".to_owned(); 4];
    configured.places[0].kind = "home".to_owned();
    configured.places[1].kind = "bar".to_owned();
    configured.modules[0].inputs = vec!["place.kind".to_owned()];
    for (transition_index, home_probability, bar_probability) in [(0, 1.0, 0.0), (1, 0.0, 1.0)] {
        configured.modules[0].transitions[transition_index].rules = vec![
            ProbabilityRule {
                conditions: vec![NumericCondition {
                    input: "place.kind".to_owned(),
                    operator: "eq".to_owned(),
                    value: 0.0,
                    categorical_value: Some("home".to_owned()),
                }],
                probability: Some(home_probability),
                provenance: provenance(),
            },
            ProbabilityRule {
                conditions: vec![NumericCondition {
                    input: "place.kind".to_owned(),
                    operator: "eq".to_owned(),
                    value: 0.0,
                    categorical_value: Some("bar".to_owned()),
                }],
                probability: Some(bar_probability),
                provenance: provenance(),
            },
        ];
    }

    let result = run(configured).unwrap();

    let selected = result
        .transition_outcomes
        .iter()
        .map(|outcome| (outcome.agent_index, outcome.transition.as_str()))
        .collect::<Vec<_>>();
    assert_eq!(
        selected,
        vec![(0, "stay"), (1, "stay"), (2, "leave"), (3, "leave")]
    );
}
