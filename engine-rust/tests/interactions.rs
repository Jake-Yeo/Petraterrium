#[path = "../src/interaction_trees.rs"]
mod interaction_trees;
#[path = "../src/interactions.rs"]
mod interactions;

use interaction_trees::{
    InteractionTransitionEvidence, InteractionTreeDefinition, InteractionTreeEffect,
    InteractionTreeNode, InteractionTreeTransition,
};
use interactions::*;
use std::collections::BTreeMap;

fn provenance() -> FactorProvenance {
    FactorProvenance {
        source: "Imported interaction panel".to_owned(),
        version: "panel-2025".to_owned(),
        status: "measured_joint".to_owned(),
        uncertainty: 0.04,
    }
}

fn factor(id: &str, value: f64) -> InteractionFactor {
    InteractionFactor {
        id: id.to_owned(),
        label: id.replace('_', " "),
        value,
        provenance: provenance(),
    }
}

fn rule() -> InteractionRule {
    InteractionRule {
        id: "talk-after-dinner".to_owned(),
        source_action: "talk".to_owned(),
        interaction_type: "talk".to_owned(),
        channel: "in_person".to_owned(),
        max_targets_per_initiator: 1,
        allowed_relationships: vec!["family".to_owned(), "stranger".to_owned()],
        allowed_place_kinds: vec!["home".to_owned(), "bar".to_owned()],
        base_factor: factor("hourly_contact", 1.0),
        relationship_factors: BTreeMap::from([
            ("family".to_owned(), factor("family_rate", 1.0)),
            ("stranger".to_owned(), factor("stranger_rate", 0.05)),
        ]),
        colocation_factors: BTreeMap::from([(
            "same_specific_place".to_owned(),
            factor("same_place", 1.0),
        )]),
        place_factors: BTreeMap::from([
            ("home".to_owned(), factor("home_contact", 1.0)),
            ("bar".to_owned(), factor("bar_contact", 1.0)),
        ]),
        time_factors: vec![TimeFactorWindow {
            weekdays: (0..=6).collect(),
            start_hour: 17.0,
            end_hour: 23.0,
            factor: factor("evening", 1.0),
        }],
        context_factors: vec![],
        unrelated_relationship: Some(RelationshipProfile {
            kind: "stranger".to_owned(),
            weight: 0.1,
            trust: 0.2,
            similarity: 0.5,
        }),
        agent_effects: vec![AgentStateEffect {
            recipient: "target".to_owned(),
            state: "mood".to_owned(),
            delta: 0.5,
            minimum: -1.0,
            maximum: 1.0,
            scale_by: vec!["relationship_weight".to_owned(), "trust".to_owned()],
        }],
        relationship_effects: vec![RelationshipStateEffect {
            direction: "initiator_to_target".to_owned(),
            field: "trust".to_owned(),
            delta: 0.1,
            minimum: -1.0,
            maximum: 1.0,
        }],
        interaction_tree_id: None,
        interaction_tree_context: BTreeMap::new(),
    }
}

fn request(seed: u64, places: Vec<usize>) -> InteractionRequest {
    InteractionRequest {
        seed,
        tick: 12,
        hour: 19.0,
        weekday: 4,
        agents: InteractionAgentColumns {
            agent_ids: vec![
                "parent".to_owned(),
                "child".to_owned(),
                "stranger".to_owned(),
            ],
            place: places,
            actions: vec![vec!["talk".to_owned()], vec![], vec![]],
            traits: BTreeMap::new(),
            states: BTreeMap::from([("mood".to_owned(), vec![0.0, 0.0, 0.0])]),
        },
        places: vec![
            InteractionPlace {
                id: "home-1".to_owned(),
                kind: "home".to_owned(),
                allows_in_person: true,
                states: BTreeMap::new(),
            },
            InteractionPlace {
                id: "bar-1".to_owned(),
                kind: "bar".to_owned(),
                allows_in_person: true,
                states: BTreeMap::new(),
            },
        ],
        relationships: vec![InteractionRelationship {
            source_index: 0,
            target_index: 1,
            kind: "family".to_owned(),
            weight: 0.8,
            trust: 0.75,
            similarity: 0.5,
        }],
        trees: BTreeMap::new(),
        rules: vec![rule()],
    }
}

fn tree_evidence() -> InteractionTransitionEvidence {
    InteractionTransitionEvidence {
        source: "Imported conversation outcome panel".to_owned(),
        version: "talk-2026".to_owned(),
        status: "measured_joint".to_owned(),
        uncertainty: 0.06,
        source_date: Some("2026-03-01".to_owned()),
        evidence_id: Some("talk-response".to_owned()),
    }
}

fn talk_tree_request() -> InteractionRequest {
    let response = InteractionTreeDefinition {
        id: "talk_response".to_owned(),
        name: "Talk response".to_owned(),
        version: "1".to_owned(),
        entry_node: "listen".to_owned(),
        allowed_channels: vec!["in_person".to_owned()],
        co_location_policy: "required".to_owned(),
        nodes: vec![
            InteractionTreeNode {
                id: "listen".to_owned(),
                label: "Listen".to_owned(),
                terminal: false,
                target_tree_id: None,
            },
            InteractionTreeNode {
                id: "responded".to_owned(),
                label: "Responded".to_owned(),
                terminal: true,
                target_tree_id: None,
            },
        ],
        transitions: vec![InteractionTreeTransition {
            id: "respond".to_owned(),
            from_node: "listen".to_owned(),
            to_node: "responded".to_owned(),
            outcome: "responded".to_owned(),
            probability: 1.0,
            probability_factors: vec![],
            evidence: tree_evidence(),
            conditions: vec![],
            effects: vec![
                InteractionTreeEffect::AgentState {
                    participant: "target".to_owned(),
                    field: "mood".to_owned(),
                    operation: "add".to_owned(),
                    value: 0.3,
                    minimum: Some(-1.0),
                    maximum: Some(1.0),
                    scale_by: vec![],
                },
                InteractionTreeEffect::RelationshipState {
                    field: "trust".to_owned(),
                    operation: "add".to_owned(),
                    value: 0.1,
                    minimum: Some(-1.0),
                    maximum: Some(1.0),
                    scale_by: vec![],
                },
            ],
        }],
    };
    let talk = InteractionTreeDefinition {
        id: "talk".to_owned(),
        name: "Talk".to_owned(),
        version: "1".to_owned(),
        entry_node: "start".to_owned(),
        allowed_channels: vec!["in_person".to_owned()],
        co_location_policy: "required".to_owned(),
        nodes: vec![
            InteractionTreeNode {
                id: "start".to_owned(),
                label: "Start".to_owned(),
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
            evidence: tree_evidence(),
            conditions: vec![],
            effects: vec![InteractionTreeEffect::AgentState {
                participant: "actor".to_owned(),
                field: "mood".to_owned(),
                operation: "add".to_owned(),
                value: 0.2,
                minimum: Some(-1.0),
                maximum: Some(1.0),
                scale_by: vec![],
            }],
        }],
    };
    let mut nested = request(19, vec![0, 0, 1]);
    nested.rules[0].interaction_tree_id = Some("talk".to_owned());
    nested.trees = BTreeMap::from([
        ("talk".to_owned(), serde_json::to_value(talk).unwrap()),
        (
            "talk_response".to_owned(),
            serde_json::to_value(response).unwrap(),
        ),
    ]);
    nested
}

#[test]
fn co_location_and_relationship_evidence_gate_directed_events() {
    let result = run_interactions(request(7, vec![0, 0, 1])).unwrap();
    assert_eq!(result.events.len(), 1);
    let event = &result.events[0];
    assert_eq!(event.initiator_id, "parent");
    assert_eq!(event.target_id, "child");
    assert_eq!(event.relationship_type, "family");
    assert_eq!(event.place_id, "home-1");
    assert_eq!(event.factors.len(), 5);
    assert!((event.state_deltas[0].delta - 0.3).abs() < 1e-12);
    assert!((result.states["mood"][1] - 0.3).abs() < 1e-12);
    assert_eq!(event.relationship_deltas[0].before, 0.75);
    assert_eq!(event.relationship_deltas[0].after, 0.85);
    assert!(result.blocked.iter().any(|blocked| {
        blocked.target_id.as_deref() == Some("stranger")
            && blocked.reason == "agents are not at the same specific place"
    }));
}

#[test]
fn away_family_and_separated_strangers_have_no_in_person_event() {
    let result = run_interactions(request(7, vec![1, 0, 0])).unwrap();
    assert!(result.events.is_empty());
    assert!(result.blocked.iter().any(|blocked| {
        blocked.target_id.as_deref() == Some("child")
            && blocked.reason == "agents are not at the same specific place"
    }));
}

#[test]
fn sourced_low_stranger_rate_is_nonzero_without_becoming_uniform() {
    let mut occurred = 0;
    for seed in 0..400 {
        let result = run_interactions(request(seed, vec![1, 0, 1])).unwrap();
        occurred += result
            .events
            .iter()
            .filter(|event| event.target_id == "stranger")
            .count();
    }
    assert!(occurred > 0);
    assert!(occurred < 60);
}

#[test]
fn sourced_family_rate_exceeds_colocated_stranger_rate() {
    let mut family_events = 0;
    let mut stranger_events = 0;
    for seed in 0..400 {
        let result = run_interactions(request(seed, vec![0, 0, 0])).unwrap();
        family_events += result
            .events
            .iter()
            .filter(|event| event.relationship_type == "family")
            .count();
        stranger_events += result
            .events
            .iter()
            .filter(|event| event.relationship_type == "stranger")
            .count();
    }
    assert!(stranger_events > 0);
    assert!(family_events > stranger_events * 10);
}

#[test]
fn repeated_input_is_deterministic_and_non_executable_evidence_cannot_fire() {
    let first = run_interactions(request(31, vec![0, 0, 1])).unwrap();
    let second = run_interactions(request(31, vec![0, 0, 1])).unwrap();
    assert_eq!(first, second);

    for status in ["unknown", "present", "user_defined", "imputed"] {
        let mut blocked_request = request(31, vec![0, 0, 1]);
        blocked_request.rules[0]
            .relationship_factors
            .get_mut("family")
            .unwrap()
            .provenance
            .status = status.to_owned();
        let result = run_interactions(blocked_request).unwrap();
        assert!(result.events.is_empty());
        assert!(result.blocked.iter().any(|blocked| {
            blocked
                .reason
                .contains(&format!("is {status} and cannot drive an interaction"))
        }));
    }
}

#[test]
fn talk_executes_nested_response_and_commits_both_agents_atomically() {
    let result = run_interactions(talk_tree_request()).unwrap();
    let event = &result.events[0];
    let trace = event.interaction_tree.as_ref().unwrap();

    assert_eq!(
        trace
            .path
            .iter()
            .map(|step| step.tree_id.as_str())
            .collect::<Vec<_>>(),
        vec!["talk", "talk_response"]
    );
    assert_eq!(result.states["mood"][0], 0.2);
    assert_eq!(result.states["mood"][1], 0.3);
    assert_eq!(event.state_deltas.len(), 2);
    assert_eq!(event.relationship_deltas.len(), 1);
    assert!((result.relationships[0].trust - 0.85).abs() < 1e-12);
}

#[test]
fn invalid_nested_effect_returns_no_partial_interaction_result() {
    let mut invalid = talk_tree_request();
    let response = invalid.trees.get_mut("talk_response").unwrap();
    response["transitions"][0]["effects"]
        .as_array_mut()
        .unwrap()
        .push(serde_json::json!({
            "kind": "agent_state",
            "participant": "target",
            "field": "missing",
            "operation": "add",
            "value": 1.0,
            "minimum": 0.0,
            "maximum": 1.0
        }));

    let error = run_interactions(invalid).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_AGENT_EFFECT_STATE");
}

#[test]
fn missing_tree_factor_input_is_blocked_without_committing_any_effect() {
    let mut missing = talk_tree_request();
    missing.trees.get_mut("talk").unwrap()["transitions"][0]["probability_factors"] = serde_json::json!([{
        "id": "crowd-density",
        "label": "Crowd density",
        "cases": [{
            "id": "known",
            "conditions": [{
                "input": "place.state.crowd_density",
                "operator": "gte",
                "value": 0
            }],
            "multiplier": 1
        }],
        "evidence": {
            "source": "Imported conversation outcome panel",
            "version": "talk-2026",
            "status": "measured_joint",
            "uncertainty": 0.06,
            "source_date": "2026-03-01",
            "evidence_id": "talk-response"
        }
    }]);

    let result = run_interactions(missing).unwrap();

    assert!(result.events.is_empty());
    assert_eq!(result.states["mood"], vec![0.0, 0.0, 0.0]);
    assert_eq!(result.relationships[0].trust, 0.75);
    assert!(result.blocked.iter().any(|blocked| {
        blocked.reason.contains("MISSING_PROBABILITY_FACTOR_INPUT")
            && blocked.target_id.as_deref() == Some("child")
    }));
}
