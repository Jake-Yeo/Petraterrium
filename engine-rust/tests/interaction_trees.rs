#[path = "../src/interaction_trees.rs"]
mod interaction_trees;

use interaction_trees::*;
use std::collections::{BTreeMap, BTreeSet};

fn evidence() -> InteractionTransitionEvidence {
    InteractionTransitionEvidence {
        source: "Observed relationship panel".to_owned(),
        version: "2026-01".to_owned(),
        status: "measured_joint".to_owned(),
        uncertainty: 0.08,
        source_date: Some("2026-01-15".to_owned()),
        evidence_id: Some("relationship-panel-acceptance".to_owned()),
    }
}

fn participant(agent_id: &str) -> InteractionParticipant {
    InteractionParticipant {
        agent_id: agent_id.to_owned(),
        place_id: "cafe-1".to_owned(),
        traits: BTreeMap::from([("sociability".to_owned(), ContextValue::Number(0.8))]),
        states: BTreeMap::from([("confidence".to_owned(), 0.5)]),
        routines: BTreeSet::from(["weekly_social".to_owned()]),
    }
}

fn factor_case(
    id: &str,
    input: &str,
    operator: &str,
    value: ContextValue,
    multiplier: f64,
) -> InteractionProbabilityFactorCase {
    InteractionProbabilityFactorCase {
        id: id.to_owned(),
        conditions: vec![InteractionTreeCondition {
            input: input.to_owned(),
            operator: operator.to_owned(),
            value,
        }],
        multiplier,
    }
}

fn probability_factor(
    id: &str,
    cases: Vec<InteractionProbabilityFactorCase>,
) -> InteractionProbabilityFactor {
    InteractionProbabilityFactor {
        id: id.to_owned(),
        label: id.replace('_', " "),
        cases,
        evidence: evidence(),
    }
}

fn request(seed: u64) -> InteractionTreeRequest {
    let acceptance_conditions = vec![
        InteractionTreeCondition {
            input: "relationship.state.strength".to_owned(),
            operator: "gte".to_owned(),
            value: ContextValue::Number(0.5),
        },
        InteractionTreeCondition {
            input: "co_located".to_owned(),
            operator: "eq".to_owned(),
            value: ContextValue::Flag(true),
        },
    ];
    InteractionTreeRequest {
        seed,
        tick: 48,
        tree: InteractionTreeDefinition {
            id: "ask_out".to_owned(),
            name: "Ask someone out".to_owned(),
            version: "1".to_owned(),
            entry_node: "asked".to_owned(),
            allowed_channels: vec!["in_person".to_owned(), "phone_message".to_owned()],
            co_location_policy: "remote_allowed".to_owned(),
            nodes: vec![
                InteractionTreeNode {
                    id: "asked".to_owned(),
                    label: "Actor asks target".to_owned(),
                    terminal: false,
                    target_tree_id: None,
                },
                InteractionTreeNode {
                    id: "dating".to_owned(),
                    label: "Target accepts".to_owned(),
                    terminal: true,
                    target_tree_id: None,
                },
                InteractionTreeNode {
                    id: "declined".to_owned(),
                    label: "Target declines".to_owned(),
                    terminal: true,
                    target_tree_id: None,
                },
            ],
            transitions: vec![
                InteractionTreeTransition {
                    id: "accept".to_owned(),
                    from_node: "asked".to_owned(),
                    to_node: "dating".to_owned(),
                    outcome: "accepted".to_owned(),
                    probability: 1.0,
                    probability_factors: vec![],
                    evidence: evidence(),
                    conditions: acceptance_conditions.clone(),
                    effects: vec![
                        InteractionTreeEffect::RelationshipKind {
                            relationship_type: "dating".to_owned(),
                        },
                        InteractionTreeEffect::RelationshipState {
                            field: "strength".to_owned(),
                            operation: "add".to_owned(),
                            value: 0.2,
                            minimum: Some(0.0),
                            maximum: Some(1.0),
                            scale_by: vec![],
                        },
                        InteractionTreeEffect::AgentRoutine {
                            participant: "actor".to_owned(),
                            operation: "add".to_owned(),
                            routine_id: "partner_time".to_owned(),
                        },
                        InteractionTreeEffect::AgentRoutine {
                            participant: "target".to_owned(),
                            operation: "add".to_owned(),
                            routine_id: "partner_time".to_owned(),
                        },
                        InteractionTreeEffect::AgentState {
                            participant: "actor".to_owned(),
                            field: "confidence".to_owned(),
                            operation: "add".to_owned(),
                            value: 0.1,
                            minimum: Some(0.0),
                            maximum: Some(1.0),
                            scale_by: vec![],
                        },
                        InteractionTreeEffect::AgentState {
                            participant: "target".to_owned(),
                            field: "confidence".to_owned(),
                            operation: "add".to_owned(),
                            value: 0.05,
                            minimum: Some(0.0),
                            maximum: Some(1.0),
                            scale_by: vec![],
                        },
                    ],
                },
                InteractionTreeTransition {
                    id: "decline".to_owned(),
                    from_node: "asked".to_owned(),
                    to_node: "declined".to_owned(),
                    outcome: "declined".to_owned(),
                    probability: 0.0,
                    probability_factors: vec![],
                    evidence: evidence(),
                    conditions: acceptance_conditions,
                    effects: vec![],
                },
            ],
        },
        trees: BTreeMap::new(),
        context: InteractionTreeContext {
            actor: participant("agent-a"),
            target: participant("agent-b"),
            relationship: DirectedRelationship {
                source_agent_id: "agent-a".to_owned(),
                target_agent_id: "agent-b".to_owned(),
                eligible: true,
                relationship_type: "acquaintance".to_owned(),
                states: BTreeMap::from([("strength".to_owned(), 0.7)]),
            },
            place: InteractionPlaceContext {
                id: "cafe-1".to_owned(),
                kind: "cafe".to_owned(),
                states: BTreeMap::new(),
            },
            time: InteractionTimeContext {
                weekday: 5,
                hour: 19.0,
            },
            channel: "in_person".to_owned(),
            attributes: BTreeMap::new(),
        },
    }
}

fn nested_request(seed: u64) -> InteractionTreeRequest {
    let mut nested = request(seed);
    let response = InteractionTreeDefinition {
        id: "talk_response".to_owned(),
        name: "Talk response".to_owned(),
        version: "1".to_owned(),
        entry_node: "response".to_owned(),
        allowed_channels: vec!["in_person".to_owned()],
        co_location_policy: "required".to_owned(),
        nodes: vec![
            InteractionTreeNode {
                id: "response".to_owned(),
                label: "Respond".to_owned(),
                terminal: false,
                target_tree_id: None,
            },
            InteractionTreeNode {
                id: "heard".to_owned(),
                label: "Message heard".to_owned(),
                terminal: true,
                target_tree_id: None,
            },
        ],
        transitions: vec![InteractionTreeTransition {
            id: "listen".to_owned(),
            from_node: "response".to_owned(),
            to_node: "heard".to_owned(),
            outcome: "heard".to_owned(),
            probability: 1.0,
            probability_factors: vec![],
            evidence: evidence(),
            conditions: vec![],
            effects: vec![
                InteractionTreeEffect::AgentState {
                    participant: "target".to_owned(),
                    field: "confidence".to_owned(),
                    operation: "add".to_owned(),
                    value: 0.2,
                    minimum: Some(0.0),
                    maximum: Some(1.0),
                    scale_by: vec![],
                },
                InteractionTreeEffect::RelationshipState {
                    field: "strength".to_owned(),
                    operation: "add".to_owned(),
                    value: 0.1,
                    minimum: Some(0.0),
                    maximum: Some(1.0),
                    scale_by: vec![],
                },
            ],
        }],
    };
    nested.tree = InteractionTreeDefinition {
        id: "talk".to_owned(),
        name: "Talk".to_owned(),
        version: "1".to_owned(),
        entry_node: "start".to_owned(),
        allowed_channels: vec!["in_person".to_owned()],
        co_location_policy: "required".to_owned(),
        nodes: vec![
            InteractionTreeNode {
                id: "start".to_owned(),
                label: "Start talking".to_owned(),
                terminal: false,
                target_tree_id: None,
            },
            InteractionTreeNode {
                id: "open_response".to_owned(),
                label: "Open response".to_owned(),
                terminal: true,
                target_tree_id: Some("talk_response".to_owned()),
            },
        ],
        transitions: vec![InteractionTreeTransition {
            id: "speak".to_owned(),
            from_node: "start".to_owned(),
            to_node: "open_response".to_owned(),
            outcome: "spoke".to_owned(),
            probability: 1.0,
            probability_factors: vec![],
            evidence: evidence(),
            conditions: vec![],
            effects: vec![InteractionTreeEffect::AgentState {
                participant: "actor".to_owned(),
                field: "confidence".to_owned(),
                operation: "add".to_owned(),
                value: 0.1,
                minimum: Some(0.0),
                maximum: Some(1.0),
                scale_by: vec![],
            }],
        }],
    };
    nested.trees.insert("talk_response".to_owned(), response);
    nested
}

#[test]
fn applies_both_participant_and_relationship_changes_atomically() {
    let result = run(request(29)).unwrap();

    assert_eq!(result.outcome, "accepted");
    assert_eq!(result.relationship_before.relationship_type, "acquaintance");
    assert_eq!(result.relationship_after.relationship_type, "dating");
    assert!((result.relationship_after.states["strength"] - 0.9).abs() < 1e-12);
    assert!(!result.actor_before.routines.contains("partner_time"));
    assert!(result.actor_after.routines.contains("partner_time"));
    assert!(result.target_after.routines.contains("partner_time"));
    assert_eq!(result.actor_after.states["confidence"], 0.6);
    assert_eq!(result.target_after.states["confidence"], 0.55);
    assert_eq!(result.receipt.relationship_direction, "agent-a→agent-b");
    assert_eq!(
        result.path[0].evidence.source,
        "Observed relationship panel"
    );
    assert_eq!(result.changes.len(), 6);
}

#[test]
fn is_deterministic_for_the_same_request_and_seed() {
    let first = run(request(917)).unwrap();
    let second = run(request(917)).unwrap();
    assert_eq!(first, second);
}

#[test]
fn rejects_non_predictive_evidence_before_selecting_a_path() {
    let mut invalid = request(5);
    invalid.tree.transitions[0].evidence.status = "unknown".to_owned();

    let error = run(invalid).unwrap_err();

    assert_eq!(error.code, "NON_PREDICTIVE_TRANSITION_EVIDENCE");
    assert_eq!(error.path, "tree.transitions.0.evidence.status");
}

#[test]
fn rejects_in_person_interaction_without_specific_place_co_location() {
    let mut invalid = request(5);
    invalid.context.target.place_id = "cafe-2".to_owned();

    let error = run(invalid).unwrap_err();

    assert_eq!(error.code, "IN_PERSON_REQUIRES_CO_LOCATION");
}

#[test]
fn rejects_wrong_relationship_direction() {
    let mut invalid = request(5);
    invalid.context.relationship.source_agent_id = "agent-b".to_owned();
    invalid.context.relationship.target_agent_id = "agent-a".to_owned();

    let error = run(invalid).unwrap_err();

    assert_eq!(error.code, "INELIGIBLE_DIRECTED_RELATIONSHIP");
}

#[test]
fn returns_no_partial_result_when_a_late_effect_is_invalid() {
    let mut invalid = request(5);
    let original_actor = invalid.context.actor.clone();
    let original_target = invalid.context.target.clone();
    invalid.tree.transitions[0]
        .effects
        .push(InteractionTreeEffect::AgentState {
            participant: "target".to_owned(),
            field: "missing_state".to_owned(),
            operation: "add".to_owned(),
            value: 0.1,
            minimum: Some(0.0),
            maximum: Some(1.0),
            scale_by: vec![],
        });

    let error = run(invalid.clone()).unwrap_err();

    assert_eq!(error.code, "UNKNOWN_AGENT_EFFECT_STATE");
    assert_eq!(invalid.context.actor, original_actor);
    assert_eq!(invalid.context.target, original_target);
}

fn dynamic_talk_request(
    seed: u64,
    relationship_kind: &str,
    weight: f64,
    trust: f64,
    crowd_density: Option<f64>,
) -> InteractionTreeRequest {
    let mut dynamic = request(seed);
    dynamic.tree.id = "dynamic-talk".to_owned();
    dynamic.tree.name = "Dynamic talk".to_owned();
    dynamic.tree.entry_node = "talk".to_owned();
    dynamic.tree.nodes = vec![
        InteractionTreeNode {
            id: "talk".to_owned(),
            label: "Talk".to_owned(),
            terminal: false,
            target_tree_id: None,
        },
        InteractionTreeNode {
            id: "connect".to_owned(),
            label: "Connect".to_owned(),
            terminal: true,
            target_tree_id: None,
        },
        InteractionTreeNode {
            id: "disengage".to_owned(),
            label: "Disengage".to_owned(),
            terminal: true,
            target_tree_id: None,
        },
    ];
    let relationship_cases = |family_multiplier, stranger_multiplier| {
        vec![
            factor_case(
                "family",
                "relationship.kind",
                "eq",
                ContextValue::Text("family".to_owned()),
                family_multiplier,
            ),
            factor_case(
                "stranger",
                "relationship.kind",
                "eq",
                ContextValue::Text("stranger".to_owned()),
                stranger_multiplier,
            ),
        ]
    };
    let numeric_cases = |input: &str, low_multiplier, high_multiplier| {
        vec![
            factor_case(
                "low",
                input,
                "lt",
                ContextValue::Number(0.5),
                low_multiplier,
            ),
            factor_case(
                "high",
                input,
                "gte",
                ContextValue::Number(0.5),
                high_multiplier,
            ),
        ]
    };
    let branch_factors = |connect: bool| {
        let favored = if connect { (0.5, 2.0) } else { (2.0, 0.5) };
        vec![
            probability_factor(
                "relationship_kind",
                relationship_cases(
                    if connect { 2.0 } else { 0.5 },
                    if connect { 0.5 } else { 2.0 },
                ),
            ),
            probability_factor(
                "relationship_weight",
                numeric_cases("relationship.state.weight", favored.0, favored.1),
            ),
            probability_factor(
                "relationship_trust",
                numeric_cases("relationship.state.trust", favored.0, favored.1),
            ),
            probability_factor(
                "relationship_similarity",
                numeric_cases("relationship.state.similarity", favored.0, favored.1),
            ),
            probability_factor(
                "actor_trait",
                numeric_cases("actor.trait.sociability", favored.0, favored.1),
            ),
            probability_factor(
                "target_trait",
                numeric_cases("target.trait.sociability", favored.0, favored.1),
            ),
            probability_factor(
                "actor_state",
                numeric_cases("actor.state.confidence", favored.0, favored.1),
            ),
            probability_factor(
                "target_state",
                numeric_cases("target.state.confidence", favored.0, favored.1),
            ),
            probability_factor(
                "crowd_density",
                numeric_cases(
                    "place.state.crowd_density",
                    if connect { 2.0 } else { 0.5 },
                    if connect { 0.5 } else { 2.0 },
                ),
            ),
            probability_factor(
                "contamination",
                numeric_cases("place.state.contamination", favored.1, favored.0),
            ),
            probability_factor(
                "time_hour",
                vec![
                    factor_case(
                        "day",
                        "time.hour",
                        "lt",
                        ContextValue::Number(18.0),
                        favored.0,
                    ),
                    factor_case(
                        "evening",
                        "time.hour",
                        "gte",
                        ContextValue::Number(18.0),
                        favored.1,
                    ),
                ],
            ),
        ]
    };
    dynamic.tree.transitions = vec![
        InteractionTreeTransition {
            id: "connect".to_owned(),
            from_node: "talk".to_owned(),
            to_node: "connect".to_owned(),
            outcome: "connected".to_owned(),
            probability: 0.5,
            probability_factors: branch_factors(true),
            evidence: evidence(),
            conditions: vec![],
            effects: vec![
                InteractionTreeEffect::AgentState {
                    participant: "actor".to_owned(),
                    field: "confidence".to_owned(),
                    operation: "add".to_owned(),
                    value: 0.2,
                    minimum: Some(0.0),
                    maximum: Some(1.0),
                    scale_by: vec!["relationship.state.trust".to_owned()],
                },
                InteractionTreeEffect::AgentState {
                    participant: "target".to_owned(),
                    field: "confidence".to_owned(),
                    operation: "add".to_owned(),
                    value: 0.2,
                    minimum: Some(0.0),
                    maximum: Some(1.0),
                    scale_by: vec!["relationship.state.weight".to_owned()],
                },
            ],
        },
        InteractionTreeTransition {
            id: "disengage".to_owned(),
            from_node: "talk".to_owned(),
            to_node: "disengage".to_owned(),
            outcome: "disengaged".to_owned(),
            probability: 0.5,
            probability_factors: branch_factors(false),
            evidence: evidence(),
            conditions: vec![],
            effects: vec![],
        },
    ];
    dynamic.context.relationship.relationship_type = relationship_kind.to_owned();
    dynamic.context.relationship.states = BTreeMap::from([
        ("weight".to_owned(), weight),
        ("trust".to_owned(), trust),
        ("similarity".to_owned(), 0.4),
    ]);
    if relationship_kind == "stranger" {
        dynamic
            .context
            .actor
            .traits
            .insert("sociability".to_owned(), ContextValue::Number(0.2));
        dynamic
            .context
            .target
            .traits
            .insert("sociability".to_owned(), ContextValue::Number(0.2));
        dynamic
            .context
            .actor
            .states
            .insert("confidence".to_owned(), 0.2);
        dynamic
            .context
            .target
            .states
            .insert("confidence".to_owned(), 0.2);
    }
    dynamic.context.place.states = BTreeMap::from([("contamination".to_owned(), 0.1)]);
    if let Some(value) = crowd_density {
        dynamic
            .context
            .place
            .states
            .insert("crowd_density".to_owned(), value);
    }
    dynamic
}

#[test]
fn dynamic_talk_probabilities_use_actual_pair_place_agent_and_time_inputs() {
    let family_empty = run(dynamic_talk_request(7, "family", 0.8, 0.9, Some(0.1))).unwrap();
    let mut stranger_empty_request = dynamic_talk_request(7, "stranger", 0.8, 0.9, Some(0.1));
    for participant in [
        &mut stranger_empty_request.context.actor,
        &mut stranger_empty_request.context.target,
    ] {
        participant
            .traits
            .insert("sociability".to_owned(), ContextValue::Number(0.8));
        participant.states.insert("confidence".to_owned(), 0.5);
    }
    let stranger_empty = run(stranger_empty_request).unwrap();
    let family_crowded = run(dynamic_talk_request(7, "family", 0.8, 0.9, Some(0.9))).unwrap();
    let family_connect = family_empty.path[0]
        .outgoing_probabilities
        .iter()
        .find(|item| item.transition_id == "connect")
        .unwrap();
    let stranger_connect = stranger_empty.path[0]
        .outgoing_probabilities
        .iter()
        .find(|item| item.transition_id == "connect")
        .unwrap();
    let crowded_connect = family_crowded.path[0]
        .outgoing_probabilities
        .iter()
        .find(|item| item.transition_id == "connect")
        .unwrap();

    assert!(family_connect.probability > stranger_connect.probability);
    assert!(family_connect.probability > crowded_connect.probability);
    let values = family_connect
        .factors
        .iter()
        .flat_map(|factor| {
            factor
                .inputs
                .iter()
                .map(|(key, value)| (key.as_str(), value))
        })
        .collect::<BTreeMap<_, _>>();
    assert_eq!(
        values["relationship.kind"],
        &ContextValue::Text("family".to_owned())
    );
    assert_eq!(
        values["relationship.state.weight"],
        &ContextValue::Number(0.8)
    );
    assert_eq!(
        values["relationship.state.trust"],
        &ContextValue::Number(0.9)
    );
    assert_eq!(
        values["relationship.state.similarity"],
        &ContextValue::Number(0.4)
    );
    assert_eq!(
        values["place.state.crowd_density"],
        &ContextValue::Number(0.1)
    );
    assert_eq!(
        values["place.state.contamination"],
        &ContextValue::Number(0.1)
    );
    assert_eq!(values["time.hour"], &ContextValue::Number(19.0));
    assert_eq!(
        values["actor.trait.sociability"],
        &ContextValue::Number(0.8)
    );
    assert_eq!(
        values["target.state.confidence"],
        &ContextValue::Number(0.5)
    );
    assert_eq!(
        family_connect.factors[0].evidence.source,
        "Observed relationship panel"
    );
}

#[test]
fn missing_dynamic_input_blocks_selection_and_commits_no_effect() {
    let request = dynamic_talk_request(7, "family", 0.8, 0.9, None);
    let actor_before = request.context.actor.clone();
    let target_before = request.context.target.clone();

    let error = run(request).unwrap_err();

    assert_eq!(error.code, "MISSING_PROBABILITY_FACTOR_INPUT");
    assert_eq!(error.path, "place.state.crowd_density");
    assert_eq!(actor_before.states["confidence"], 0.5);
    assert_eq!(target_before.states["confidence"], 0.5);
}

#[test]
fn unmatched_or_non_predictive_factor_never_becomes_a_guessed_probability() {
    let mut unmatched = dynamic_talk_request(7, "family", 0.8, 0.9, Some(0.1));
    unmatched.tree.transitions[0].probability_factors[0].cases = vec![factor_case(
        "unsupported-kind",
        "relationship.kind",
        "eq",
        ContextValue::Text("coworker".to_owned()),
        1.0,
    )];
    let unmatched_error = run(unmatched).unwrap_err();
    assert_eq!(unmatched_error.code, "UNMATCHED_PROBABILITY_FACTOR");

    let mut non_predictive = dynamic_talk_request(7, "family", 0.8, 0.9, Some(0.1));
    non_predictive.tree.transitions[0].probability_factors[0]
        .evidence
        .status = "unknown".to_owned();
    let evidence_error = run(non_predictive).unwrap_err();
    assert_eq!(evidence_error.code, "NON_PREDICTIVE_TRANSITION_EVIDENCE");
    assert_eq!(
        evidence_error.path,
        "tree.transitions.0.probability_factors.0.evidence.status"
    );
}

#[test]
fn declared_pair_influence_scales_both_agent_effects_atomically() {
    let mut request = dynamic_talk_request(0, "family", 0.75, 0.5, Some(0.1));
    for seed in 0..1000 {
        request.seed = seed;
        let result = run(request.clone()).unwrap();
        if result.outcome == "connected" {
            assert!((result.actor_after.states["confidence"] - 0.6).abs() < 1e-12);
            assert!((result.target_after.states["confidence"] - 0.65).abs() < 1e-12);
            assert_eq!(result.changes.len(), 2);
            return;
        }
    }
    panic!("expected at least one sourced connected outcome");
}

#[test]
fn talk_calls_nested_response_with_one_path_and_atomic_effect_set() {
    let nested = nested_request(44);
    let mut registry = nested.trees.clone();
    registry.insert(nested.tree.id.clone(), nested.tree.clone());
    validate_registry(&registry).unwrap();
    let result = run(nested).unwrap();

    assert_eq!(result.tree_id, "talk");
    assert_eq!(result.outcome_node, "open_response");
    assert_eq!(result.outcome, "heard");
    assert_eq!(
        result
            .path
            .iter()
            .map(|step| step.tree_id.as_str())
            .collect::<Vec<_>>(),
        vec!["talk", "talk_response"]
    );
    assert_eq!(result.actor_after.states["confidence"], 0.6);
    assert_eq!(result.target_after.states["confidence"], 0.7);
    assert!((result.relationship_after.states["strength"] - 0.8).abs() < 1e-12);
    assert_eq!(result.changes.len(), 3);
}

#[test]
fn rejects_missing_nested_tree_and_reference_cycles() {
    let mut missing = nested_request(44);
    missing.trees.clear();
    let missing_error = run(missing).unwrap_err();
    assert_eq!(missing_error.code, "MISSING_INTERACTION_TREE_REFERENCE");

    let mut cyclic = nested_request(44);
    cyclic.trees.get_mut("talk_response").unwrap().nodes[1].target_tree_id =
        Some("talk".to_owned());
    let cycle_error = run(cyclic).unwrap_err();
    assert_eq!(cycle_error.code, "INTERACTION_TREE_REFERENCE_CYCLE");
}

#[test]
fn rejects_nested_tree_chains_deeper_than_five() {
    let mut deep = nested_request(44);
    deep.tree.nodes[1].target_tree_id = Some("level-2".to_owned());
    deep.trees.clear();
    for level in 2..=6 {
        let target = (level < 6).then(|| format!("level-{}", level + 1));
        deep.trees.insert(
            format!("level-{level}"),
            InteractionTreeDefinition {
                id: format!("level-{level}"),
                name: format!("Level {level}"),
                version: "1".to_owned(),
                entry_node: "call".to_owned(),
                allowed_channels: vec!["in_person".to_owned()],
                co_location_policy: "required".to_owned(),
                nodes: vec![InteractionTreeNode {
                    id: "call".to_owned(),
                    label: "Call next".to_owned(),
                    terminal: true,
                    target_tree_id: target,
                }],
                transitions: vec![],
            },
        );
    }

    let error = run(deep).unwrap_err();
    assert_eq!(error.code, "INTERACTION_TREE_REFERENCE_DEPTH");
}
