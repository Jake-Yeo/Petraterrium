use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

use crate::interaction_trees::{
    ContextValue, DirectedRelationship, InteractionParticipant, InteractionPlaceContext,
    InteractionTimeContext, InteractionTransitionEvidence, InteractionTreeContext,
    InteractionTreeDefinition, InteractionTreeRequest, run as run_interaction_tree,
    validate_registry as validate_tree_registry,
};

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct InteractionRequest {
    pub seed: u64,
    pub tick: u64,
    pub hour: f64,
    pub weekday: u8,
    pub agents: InteractionAgentColumns,
    pub places: Vec<InteractionPlace>,
    #[serde(default)]
    pub relationships: Vec<InteractionRelationship>,
    #[serde(default)]
    pub trees: BTreeMap<String, Value>,
    pub rules: Vec<InteractionRule>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct InteractionAgentColumns {
    pub agent_ids: Vec<String>,
    pub place: Vec<usize>,
    pub actions: Vec<Vec<String>>,
    #[serde(default)]
    pub traits: BTreeMap<String, Vec<f64>>,
    #[serde(default)]
    pub states: BTreeMap<String, Vec<f64>>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct InteractionPlace {
    pub id: String,
    pub kind: String,
    pub allows_in_person: bool,
    #[serde(default)]
    pub states: BTreeMap<String, f64>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct InteractionRelationship {
    pub source_index: usize,
    pub target_index: usize,
    pub kind: String,
    pub weight: f64,
    pub trust: f64,
    pub similarity: f64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct RelationshipProfile {
    pub kind: String,
    pub weight: f64,
    pub trust: f64,
    pub similarity: f64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct FactorProvenance {
    pub source: String,
    pub version: String,
    pub status: String,
    pub uncertainty: f64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct InteractionFactor {
    pub id: String,
    pub label: String,
    pub value: f64,
    pub provenance: FactorProvenance,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct TimeFactorWindow {
    pub weekdays: Vec<u8>,
    pub start_hour: f64,
    pub end_hour: f64,
    pub factor: InteractionFactor,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct AgentStateEffect {
    pub recipient: String,
    pub state: String,
    pub delta: f64,
    pub minimum: f64,
    pub maximum: f64,
    #[serde(default)]
    pub scale_by: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct RelationshipStateEffect {
    pub direction: String,
    pub field: String,
    pub delta: f64,
    pub minimum: f64,
    pub maximum: f64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct InteractionRule {
    pub id: String,
    pub source_action: String,
    pub interaction_type: String,
    pub channel: String,
    pub max_targets_per_initiator: usize,
    #[serde(default)]
    pub allowed_relationships: Vec<String>,
    #[serde(default)]
    pub allowed_place_kinds: Vec<String>,
    pub base_factor: InteractionFactor,
    pub relationship_factors: BTreeMap<String, InteractionFactor>,
    pub colocation_factors: BTreeMap<String, InteractionFactor>,
    pub place_factors: BTreeMap<String, InteractionFactor>,
    pub time_factors: Vec<TimeFactorWindow>,
    #[serde(default)]
    pub context_factors: Vec<InteractionFactor>,
    pub unrelated_relationship: Option<RelationshipProfile>,
    #[serde(default)]
    pub agent_effects: Vec<AgentStateEffect>,
    #[serde(default)]
    pub relationship_effects: Vec<RelationshipStateEffect>,
    #[serde(default)]
    pub interaction_tree_id: Option<String>,
    #[serde(default)]
    pub interaction_tree_context: BTreeMap<String, ContextValue>,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct EvaluatedInteractionFactor {
    pub kind: String,
    pub factor: InteractionFactor,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct AppliedStateDelta {
    pub agent_id: String,
    pub state: String,
    pub before: f64,
    pub delta: f64,
    pub after: f64,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct AppliedRelationshipDelta {
    pub source_agent_id: String,
    pub target_agent_id: String,
    pub field: String,
    pub before: f64,
    pub delta: f64,
    pub after: f64,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct DirectedInteractionEvent {
    pub tick: u64,
    pub hour: f64,
    pub weekday: u8,
    pub rule_id: String,
    pub interaction_type: String,
    pub channel: String,
    pub initiator_index: usize,
    pub initiator_id: String,
    pub target_index: usize,
    pub target_id: String,
    pub place_index: usize,
    pub place_id: String,
    pub relationship_type: String,
    pub relationship_weight: f64,
    pub trust: f64,
    pub similarity: f64,
    pub probability: f64,
    pub factors: Vec<EvaluatedInteractionFactor>,
    pub state_deltas: Vec<AppliedStateDelta>,
    pub relationship_deltas: Vec<AppliedRelationshipDelta>,
    pub interaction_tree: Option<InteractionTreeTrace>,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct InteractionTreeTrace {
    pub tree_id: String,
    pub tree_version: String,
    pub outcome_node: String,
    pub outcome: String,
    pub path: Vec<InteractionTreePathRecord>,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct InteractionTreePathRecord {
    pub tree_id: String,
    pub node_id: String,
    pub transition_id: String,
    pub outcome: String,
    pub probability: f64,
    pub draw: f64,
    pub evidence: InteractionTransitionEvidence,
    pub factors: Vec<crate::interaction_trees::EvaluatedInteractionProbabilityFactor>,
    pub outgoing_probabilities: Vec<crate::interaction_trees::EvaluatedInteractionTransition>,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct BlockedInteraction {
    pub rule_id: String,
    pub initiator_id: String,
    pub target_id: Option<String>,
    pub reason: String,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct InteractionResult {
    pub seed: u64,
    pub tick: u64,
    pub states: BTreeMap<String, Vec<f64>>,
    pub relationships: Vec<InteractionRelationship>,
    pub events: Vec<DirectedInteractionEvent>,
    pub blocked: Vec<BlockedInteraction>,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct InteractionError {
    pub code: String,
    pub message: String,
    pub path: String,
}

impl InteractionError {
    fn at(code: &str, message: impl Into<String>, path: impl Into<String>) -> Self {
        Self {
            code: code.to_owned(),
            message: message.into(),
            path: path.into(),
        }
    }
}

struct CandidateEvaluation {
    target: usize,
    relationship: InteractionRelationship,
    factors: Vec<EvaluatedInteractionFactor>,
    probability: f64,
}

pub fn run_interactions(
    request: InteractionRequest,
) -> Result<InteractionResult, InteractionError> {
    validate_request(&request)?;
    let mut rng = ChaCha8Rng::seed_from_u64(request.seed ^ request.tick.rotate_left(19));
    let mut states = request.agents.states.clone();
    let mut relationships = request.relationships.clone();
    let mut events = Vec::new();
    let mut blocked = Vec::new();
    for rule in &request.rules {
        for initiator in 0..request.agents.agent_ids.len() {
            if !request.agents.actions[initiator]
                .iter()
                .any(|action| action == &rule.source_action)
            {
                continue;
            }
            let mut winners = Vec::new();
            let candidate_targets = interaction_candidate_targets(
                initiator,
                request.agents.agent_ids.len(),
                rule,
                &relationships,
            );
            for target in candidate_targets {
                match evaluate_candidate(&request, rule, initiator, target, &relationships) {
                    Ok(candidate) => {
                        if rng.r#gen::<f64>() < candidate.probability {
                            winners.push((rng.r#gen::<u64>(), candidate));
                        }
                    }
                    Err(reason) => blocked.push(BlockedInteraction {
                        rule_id: rule.id.clone(),
                        initiator_id: request.agents.agent_ids[initiator].clone(),
                        target_id: Some(request.agents.agent_ids[target].clone()),
                        reason,
                    }),
                }
            }
            winners.sort_by_key(|(order, candidate)| (*order, candidate.target));
            for (_, candidate) in winners.into_iter().take(rule.max_targets_per_initiator) {
                let target = candidate.target;
                let event = apply_event(
                    &request,
                    rule,
                    initiator,
                    candidate,
                    &mut states,
                    &mut relationships,
                );
                match event {
                    Ok(event) => events.push(event),
                    Err(error) if blocks_tree_without_guess(&error.code) => {
                        blocked.push(BlockedInteraction {
                            rule_id: rule.id.clone(),
                            initiator_id: request.agents.agent_ids[initiator].clone(),
                            target_id: Some(request.agents.agent_ids[target].clone()),
                            reason: format!("{}: {}", error.code, error.message),
                        });
                    }
                    Err(error) => return Err(error),
                }
            }
        }
    }
    Ok(InteractionResult {
        seed: request.seed,
        tick: request.tick,
        states,
        relationships,
        events,
        blocked,
    })
}

fn interaction_candidate_targets(
    initiator: usize,
    agent_count: usize,
    rule: &InteractionRule,
    relationships: &[InteractionRelationship],
) -> Vec<usize> {
    if rule.unrelated_relationship.is_some() {
        return (0..agent_count)
            .filter(|target| *target != initiator)
            .collect();
    }
    let mut targets = relationships
        .iter()
        .filter(|relationship| relationship.source_index == initiator)
        .filter(|relationship| {
            rule.allowed_relationships.is_empty()
                || rule
                    .allowed_relationships
                    .iter()
                    .any(|kind| kind == &relationship.kind)
        })
        .map(|relationship| relationship.target_index)
        .collect::<Vec<_>>();
    targets.sort_unstable();
    targets.dedup();
    targets
}

fn validate_request(request: &InteractionRequest) -> Result<(), InteractionError> {
    let agent_count = request.agents.agent_ids.len();
    if agent_count == 0 {
        return Err(InteractionError::at(
            "EMPTY_AGENT_BATCH",
            "Interaction evaluation requires at least one agent",
            "agents.agent_ids",
        ));
    }
    let unique_agents: BTreeSet<_> = request.agents.agent_ids.iter().collect();
    if unique_agents.len() != agent_count {
        return Err(InteractionError::at(
            "DUPLICATE_AGENT_ID",
            "Interaction agent IDs must be unique",
            "agents.agent_ids",
        ));
    }
    if request.agents.place.len() != agent_count || request.agents.actions.len() != agent_count {
        return Err(InteractionError::at(
            "AGENT_COLUMN_LENGTH",
            "Interaction agent columns must have equal lengths",
            "agents",
        ));
    }
    if request.hour < 0.0 || request.hour >= 24.0 || !request.hour.is_finite() {
        return Err(InteractionError::at(
            "INVALID_HOUR",
            "Interaction hour must be between 0 inclusive and 24 exclusive",
            "hour",
        ));
    }
    if request.weekday > 6 {
        return Err(InteractionError::at(
            "INVALID_WEEKDAY",
            "Interaction weekday must be between 0 and 6",
            "weekday",
        ));
    }
    for (index, place) in request.agents.place.iter().enumerate() {
        if *place >= request.places.len() {
            return Err(InteractionError::at(
                "UNKNOWN_PLACE",
                format!("Agent {index} references place index {place}"),
                format!("agents.place.{index}"),
            ));
        }
    }
    for (state, values) in &request.agents.states {
        if values.len() != agent_count || values.iter().any(|value| !value.is_finite()) {
            return Err(InteractionError::at(
                "INVALID_STATE_COLUMN",
                format!("State column {state} must contain one finite value per agent"),
                format!("agents.states.{state}"),
            ));
        }
    }
    for (name, values) in &request.agents.traits {
        if values.len() != agent_count || values.iter().any(|value| !value.is_finite()) {
            return Err(InteractionError::at(
                "INVALID_TRAIT_COLUMN",
                format!("Trait column {name} must contain one finite value per agent"),
                format!("agents.traits.{name}"),
            ));
        }
    }
    let mut directed_relationships = BTreeSet::new();
    for (index, relationship) in request.relationships.iter().enumerate() {
        validate_relationship(relationship, agent_count, &format!("relationships.{index}"))?;
        if !directed_relationships.insert((relationship.source_index, relationship.target_index)) {
            return Err(InteractionError::at(
                "DUPLICATE_RELATIONSHIP",
                "Only one directed relationship may exist for an agent pair",
                format!("relationships.{index}"),
            ));
        }
    }
    let trees = parse_tree_registry(&request.trees)?;
    validate_tree_registry(&trees)
        .map_err(|error| InteractionError::at(&error.code, error.message, error.path))?;
    let mut rule_ids = BTreeSet::new();
    for (index, rule) in request.rules.iter().enumerate() {
        validate_rule(rule, &request.trees, &format!("rules.{index}"))?;
        if !rule_ids.insert(&rule.id) {
            return Err(InteractionError::at(
                "DUPLICATE_RULE_ID",
                "Interaction rule IDs must be unique",
                format!("rules.{index}.id"),
            ));
        }
    }
    Ok(())
}

fn validate_relationship(
    relationship: &InteractionRelationship,
    agent_count: usize,
    path: &str,
) -> Result<(), InteractionError> {
    if relationship.source_index >= agent_count
        || relationship.target_index >= agent_count
        || relationship.source_index == relationship.target_index
    {
        return Err(InteractionError::at(
            "INVALID_RELATIONSHIP_ENDPOINT",
            "Relationship endpoints must name two different agents",
            path,
        ));
    }
    for (field, value) in [
        ("weight", relationship.weight),
        ("trust", relationship.trust),
        ("similarity", relationship.similarity),
    ] {
        if !value.is_finite() || !(-1.0..=1.0).contains(&value) {
            return Err(InteractionError::at(
                "INVALID_RELATIONSHIP_VALUE",
                format!("Relationship {field} must be finite and between -1 and 1"),
                format!("{path}.{field}"),
            ));
        }
    }
    Ok(())
}

fn validate_rule(
    rule: &InteractionRule,
    trees: &BTreeMap<String, Value>,
    path: &str,
) -> Result<(), InteractionError> {
    if rule.max_targets_per_initiator == 0 {
        return Err(InteractionError::at(
            "INVALID_TARGET_LIMIT",
            "An interaction rule must allow at least one target",
            format!("{path}.max_targets_per_initiator"),
        ));
    }
    if !matches!(
        rule.channel.as_str(),
        "in_person" | "phone_message" | "online"
    ) {
        return Err(InteractionError::at(
            "INVALID_CHANNEL",
            "Interaction channel must be in_person, phone_message, or online",
            format!("{path}.channel"),
        ));
    }
    validate_factor(&rule.base_factor, &format!("{path}.base_factor"))?;
    for (kind, factor) in &rule.relationship_factors {
        validate_factor(factor, &format!("{path}.relationship_factors.{kind}"))?;
    }
    for (key, factor) in &rule.colocation_factors {
        validate_factor(factor, &format!("{path}.colocation_factors.{key}"))?;
    }
    for (key, factor) in &rule.place_factors {
        validate_factor(factor, &format!("{path}.place_factors.{key}"))?;
    }
    for (index, window) in rule.time_factors.iter().enumerate() {
        validate_factor(
            &window.factor,
            &format!("{path}.time_factors.{index}.factor"),
        )?;
        if window.weekdays.iter().any(|weekday| *weekday > 6)
            || !valid_hour_boundary(window.start_hour)
            || !valid_hour_boundary(window.end_hour)
            || window.start_hour == window.end_hour
        {
            return Err(InteractionError::at(
                "INVALID_TIME_WINDOW",
                "Time windows require weekdays 0 to 6 and distinct hour boundaries from 0 to 24",
                format!("{path}.time_factors.{index}"),
            ));
        }
    }
    for (index, factor) in rule.context_factors.iter().enumerate() {
        validate_factor(factor, &format!("{path}.context_factors.{index}"))?;
    }
    if let Some(profile) = &rule.unrelated_relationship {
        let relationship = InteractionRelationship {
            source_index: 0,
            target_index: 1,
            kind: profile.kind.clone(),
            weight: profile.weight,
            trust: profile.trust,
            similarity: profile.similarity,
        };
        validate_relationship(&relationship, 2, &format!("{path}.unrelated_relationship"))?;
    }
    for (index, effect) in rule.agent_effects.iter().enumerate() {
        if !matches!(effect.recipient.as_str(), "initiator" | "target")
            || !effect.delta.is_finite()
            || !effect.minimum.is_finite()
            || !effect.maximum.is_finite()
            || effect.minimum > effect.maximum
            || effect.scale_by.iter().any(|scale| {
                !matches!(
                    scale.as_str(),
                    "relationship_weight" | "trust" | "similarity"
                )
            })
        {
            return Err(InteractionError::at(
                "INVALID_AGENT_EFFECT",
                "Agent effects require a valid recipient, finite bounds, and known relationship scales",
                format!("{path}.agent_effects.{index}"),
            ));
        }
    }
    for (index, effect) in rule.relationship_effects.iter().enumerate() {
        if !matches!(
            effect.direction.as_str(),
            "initiator_to_target" | "target_to_initiator"
        ) || !matches!(effect.field.as_str(), "weight" | "trust" | "similarity")
            || !effect.delta.is_finite()
            || !effect.minimum.is_finite()
            || !effect.maximum.is_finite()
            || effect.minimum > effect.maximum
        {
            return Err(InteractionError::at(
                "INVALID_RELATIONSHIP_EFFECT",
                "Relationship effects require a directed supported field and finite bounds",
                format!("{path}.relationship_effects.{index}"),
            ));
        }
    }
    if let Some(tree_id) = &rule.interaction_tree_id {
        let tree = parse_tree(trees, tree_id, &format!("{path}.interaction_tree_id"))?;
        if tree.id != *tree_id {
            return Err(InteractionError::at(
                "INTERACTION_TREE_ID_MISMATCH",
                format!(
                    "Interaction tree registry key {tree_id} contains tree {}",
                    tree.id
                ),
                format!("{path}.interaction_tree_id"),
            ));
        }
        if !tree
            .allowed_channels
            .iter()
            .any(|channel| channel == &rule.channel)
        {
            return Err(InteractionError::at(
                "INTERACTION_TREE_CHANNEL_MISMATCH",
                format!(
                    "Interaction tree {tree_id} does not allow channel {}",
                    rule.channel
                ),
                format!("{path}.channel"),
            ));
        }
    }
    Ok(())
}

fn parse_tree(
    trees: &BTreeMap<String, Value>,
    tree_id: &str,
    path: &str,
) -> Result<InteractionTreeDefinition, InteractionError> {
    let value = trees.get(tree_id).ok_or_else(|| {
        InteractionError::at(
            "UNKNOWN_INTERACTION_TREE",
            format!("Interaction rule references unknown tree {tree_id}"),
            path,
        )
    })?;
    serde_json::from_value(value.clone()).map_err(|error| {
        InteractionError::at(
            "INVALID_INTERACTION_TREE",
            format!("Interaction tree {tree_id} cannot be decoded: {error}"),
            path,
        )
    })
}

fn parse_tree_registry(
    trees: &BTreeMap<String, Value>,
) -> Result<BTreeMap<String, InteractionTreeDefinition>, InteractionError> {
    trees
        .keys()
        .map(|tree_id| {
            let tree = parse_tree(trees, tree_id, &format!("trees.{tree_id}"))?;
            if tree.id != *tree_id {
                return Err(InteractionError::at(
                    "INTERACTION_TREE_ID_MISMATCH",
                    format!(
                        "Interaction tree registry key {tree_id} contains tree {}",
                        tree.id
                    ),
                    format!("trees.{tree_id}"),
                ));
            }
            Ok((tree_id.clone(), tree))
        })
        .collect()
}

fn valid_hour_boundary(value: f64) -> bool {
    value.is_finite() && (0.0..=24.0).contains(&value)
}

fn validate_factor(factor: &InteractionFactor, path: &str) -> Result<(), InteractionError> {
    if !factor.value.is_finite() || !(0.0..=1.0).contains(&factor.value) {
        return Err(InteractionError::at(
            "INVALID_FACTOR_VALUE",
            "Interaction factors must be finite probabilities between 0 and 1",
            format!("{path}.value"),
        ));
    }
    if !factor.provenance.uncertainty.is_finite()
        || factor.provenance.uncertainty < 0.0
        || factor.provenance.source.trim().is_empty()
        || factor.provenance.version.trim().is_empty()
    {
        return Err(InteractionError::at(
            "INVALID_FACTOR_PROVENANCE",
            "Interaction factors require source, version, and non-negative uncertainty",
            format!("{path}.provenance"),
        ));
    }
    Ok(())
}

fn evaluate_candidate(
    request: &InteractionRequest,
    rule: &InteractionRule,
    initiator: usize,
    target: usize,
    relationships: &[InteractionRelationship],
) -> Result<CandidateEvaluation, String> {
    let initiator_place_index = request.agents.place[initiator];
    let target_place_index = request.agents.place[target];
    let same_place = initiator_place_index == target_place_index;
    let place = &request.places[initiator_place_index];
    if rule.channel == "in_person" && (!same_place || !place.allows_in_person) {
        return Err(if same_place {
            "specific place does not allow in-person interaction".to_owned()
        } else {
            "agents are not at the same specific place".to_owned()
        });
    }
    if !rule.allowed_place_kinds.is_empty()
        && !rule
            .allowed_place_kinds
            .iter()
            .any(|kind| kind == &place.kind)
    {
        return Err("initiator place is not eligible for this interaction".to_owned());
    }
    if let Some(tree_id) = &rule.interaction_tree_id {
        let tree = parse_tree(&request.trees, tree_id, "interaction_tree_id")
            .map_err(|error| error.message)?;
        if tree.co_location_policy == "required" && !same_place {
            return Err("interaction tree requires agents at the same specific place".to_owned());
        }
    }
    let relationship = resolve_relationship(relationships, rule, initiator, target)
        .ok_or_else(|| "no directed relationship evidence exists for this pair".to_owned())?;
    if !rule.allowed_relationships.is_empty()
        && !rule
            .allowed_relationships
            .iter()
            .any(|kind| kind == &relationship.kind)
    {
        return Err("relationship type is not eligible for this interaction".to_owned());
    }
    let relationship_factor = rule
        .relationship_factors
        .get(&relationship.kind)
        .ok_or_else(|| "relationship probability factor is missing".to_owned())?;
    let colocation_key = if same_place {
        "same_specific_place"
    } else {
        "different_specific_place"
    };
    let colocation_factor = rule
        .colocation_factors
        .get(colocation_key)
        .ok_or_else(|| "co-location probability factor is missing".to_owned())?;
    let place_factor = rule
        .place_factors
        .get(&place.id)
        .or_else(|| rule.place_factors.get(&place.kind))
        .ok_or_else(|| "place probability factor is missing".to_owned())?;
    let matching_times: Vec<_> = rule
        .time_factors
        .iter()
        .filter(|window| time_window_matches(window, request.weekday, request.hour))
        .collect();
    if matching_times.len() != 1 {
        return Err(if matching_times.is_empty() {
            "time probability factor is missing".to_owned()
        } else {
            "time probability factors overlap".to_owned()
        });
    }
    let mut factors = vec![
        evaluated("base", &rule.base_factor),
        evaluated("relationship", relationship_factor),
        evaluated("co_location", colocation_factor),
        evaluated("place", place_factor),
        evaluated("time", &matching_times[0].factor),
    ];
    factors.extend(
        rule.context_factors
            .iter()
            .map(|factor| evaluated("context", factor)),
    );
    if let Some(factor) = factors
        .iter()
        .find(|factor| !factor_is_predictive(&factor.factor))
    {
        return Err(format!(
            "factor {} is {} and cannot drive an interaction",
            factor.factor.id, factor.factor.provenance.status
        ));
    }
    let probability = factors
        .iter()
        .map(|factor| factor.factor.value)
        .product::<f64>();
    Ok(CandidateEvaluation {
        target,
        relationship,
        factors,
        probability,
    })
}

fn resolve_relationship(
    relationships: &[InteractionRelationship],
    rule: &InteractionRule,
    initiator: usize,
    target: usize,
) -> Option<InteractionRelationship> {
    relationships
        .iter()
        .find(|relationship| {
            relationship.source_index == initiator && relationship.target_index == target
        })
        .cloned()
        .or_else(|| {
            rule.unrelated_relationship
                .as_ref()
                .map(|profile| InteractionRelationship {
                    source_index: initiator,
                    target_index: target,
                    kind: profile.kind.clone(),
                    weight: profile.weight,
                    trust: profile.trust,
                    similarity: profile.similarity,
                })
        })
}

fn evaluated(kind: &str, factor: &InteractionFactor) -> EvaluatedInteractionFactor {
    EvaluatedInteractionFactor {
        kind: kind.to_owned(),
        factor: factor.clone(),
    }
}

fn factor_is_predictive(factor: &InteractionFactor) -> bool {
    matches!(
        factor.provenance.status.as_str(),
        "measured_joint" | "fitted_model" | "default_estimated" | "approved_estimate"
    )
}

fn blocks_tree_without_guess(code: &str) -> bool {
    matches!(
        code,
        "MISSING_PROBABILITY_FACTOR_INPUT"
            | "UNMATCHED_PROBABILITY_FACTOR"
            | "MISSING_EFFECT_SCALE_INPUT"
            | "MISSING_CONDITION_INPUT"
    )
}

fn time_window_matches(window: &TimeFactorWindow, weekday: u8, hour: f64) -> bool {
    if !window.weekdays.contains(&weekday) {
        return false;
    }
    if window.start_hour < window.end_hour {
        (window.start_hour..window.end_hour).contains(&hour)
    } else {
        hour >= window.start_hour || hour < window.end_hour
    }
}

fn apply_event(
    request: &InteractionRequest,
    rule: &InteractionRule,
    initiator: usize,
    candidate: CandidateEvaluation,
    states: &mut BTreeMap<String, Vec<f64>>,
    relationships: &mut Vec<InteractionRelationship>,
) -> Result<DirectedInteractionEvent, InteractionError> {
    if rule.interaction_tree_id.is_some() {
        return apply_tree_event(request, rule, initiator, candidate, states, relationships);
    }
    let target = candidate.target;
    let mut state_deltas = Vec::new();
    for (effect_index, effect) in rule.agent_effects.iter().enumerate() {
        let agent = if effect.recipient == "initiator" {
            initiator
        } else {
            target
        };
        let values = states.get_mut(&effect.state).ok_or_else(|| {
            InteractionError::at(
                "UNKNOWN_EFFECT_STATE",
                format!(
                    "Interaction effect references missing state {}",
                    effect.state
                ),
                format!("rules.{}.agent_effects.{effect_index}.state", rule.id),
            )
        })?;
        let scale = effect.scale_by.iter().fold(1.0, |value, scale| {
            value
                * match scale.as_str() {
                    "relationship_weight" => candidate.relationship.weight,
                    "trust" => candidate.relationship.trust,
                    "similarity" => candidate.relationship.similarity,
                    _ => unreachable!(),
                }
        });
        let before = values[agent];
        let delta = effect.delta * scale;
        let after = (before + delta).clamp(effect.minimum, effect.maximum);
        values[agent] = after;
        state_deltas.push(AppliedStateDelta {
            agent_id: request.agents.agent_ids[agent].clone(),
            state: effect.state.clone(),
            before,
            delta: after - before,
            after,
        });
    }
    let mut relationship_deltas = Vec::new();
    for effect in &rule.relationship_effects {
        let (source, destination) = if effect.direction == "initiator_to_target" {
            (initiator, target)
        } else {
            (target, initiator)
        };
        let relationship_index =
            ensure_relationship(relationships, source, destination, &candidate.relationship);
        let relationship = &mut relationships[relationship_index];
        let field = match effect.field.as_str() {
            "weight" => &mut relationship.weight,
            "trust" => &mut relationship.trust,
            "similarity" => &mut relationship.similarity,
            _ => unreachable!(),
        };
        let before = *field;
        let after = (before + effect.delta).clamp(effect.minimum, effect.maximum);
        *field = after;
        relationship_deltas.push(AppliedRelationshipDelta {
            source_agent_id: request.agents.agent_ids[source].clone(),
            target_agent_id: request.agents.agent_ids[destination].clone(),
            field: effect.field.clone(),
            before,
            delta: after - before,
            after,
        });
    }
    let place_index = request.agents.place[initiator];
    Ok(DirectedInteractionEvent {
        tick: request.tick,
        hour: request.hour,
        weekday: request.weekday,
        rule_id: rule.id.clone(),
        interaction_type: rule.interaction_type.clone(),
        channel: rule.channel.clone(),
        initiator_index: initiator,
        initiator_id: request.agents.agent_ids[initiator].clone(),
        target_index: target,
        target_id: request.agents.agent_ids[target].clone(),
        place_index,
        place_id: request.places[place_index].id.clone(),
        relationship_type: candidate.relationship.kind,
        relationship_weight: candidate.relationship.weight,
        trust: candidate.relationship.trust,
        similarity: candidate.relationship.similarity,
        probability: candidate.probability,
        factors: candidate.factors,
        state_deltas,
        relationship_deltas,
        interaction_tree: None,
    })
}

fn apply_tree_event(
    request: &InteractionRequest,
    rule: &InteractionRule,
    initiator: usize,
    candidate: CandidateEvaluation,
    states: &mut BTreeMap<String, Vec<f64>>,
    relationships: &mut Vec<InteractionRelationship>,
) -> Result<DirectedInteractionEvent, InteractionError> {
    let target = candidate.target;
    let tree_id = rule
        .interaction_tree_id
        .as_deref()
        .expect("tree event requires a selected tree");
    let trees = parse_tree_registry(&request.trees)?;
    let tree = trees.get(tree_id).cloned().ok_or_else(|| {
        InteractionError::at(
            "UNKNOWN_INTERACTION_TREE",
            format!("Interaction rule references unknown tree {tree_id}"),
            "interaction_tree_id",
        )
    })?;
    let place_index = request.agents.place[initiator];
    let place = &request.places[place_index];
    let actor = participant(request, states, initiator);
    let target_participant = participant(request, states, target);
    let relationship = directed_relationship(request, &candidate.relationship, initiator, target);
    let result = run_interaction_tree(InteractionTreeRequest {
        seed: interaction_tree_seed(request.seed, request.tick, &rule.id, initiator, target),
        tick: request.tick,
        tree,
        trees,
        context: InteractionTreeContext {
            actor,
            target: target_participant,
            relationship,
            place: InteractionPlaceContext {
                id: place.id.clone(),
                kind: place.kind.clone(),
                states: place.states.clone(),
            },
            time: InteractionTimeContext {
                weekday: request.weekday,
                hour: request.hour,
            },
            channel: rule.channel.clone(),
            attributes: rule.interaction_tree_context.clone(),
        },
    })
    .map_err(|error| InteractionError::at(&error.code, error.message, error.path))?;

    let state_deltas = tree_state_deltas(&result, states)?;
    let relationship_deltas = tree_relationship_deltas(&result)?;
    commit_tree_relationship(
        &result,
        relationships,
        initiator,
        target,
        request.agents.agent_ids.len(),
    )?;
    commit_tree_agents(&result, states, initiator, target);
    let relationship_after = relationships
        .iter()
        .find(|relationship| {
            relationship.source_index == initiator && relationship.target_index == target
        })
        .expect("tree relationship was committed");
    Ok(DirectedInteractionEvent {
        tick: request.tick,
        hour: request.hour,
        weekday: request.weekday,
        rule_id: rule.id.clone(),
        interaction_type: rule.interaction_type.clone(),
        channel: rule.channel.clone(),
        initiator_index: initiator,
        initiator_id: request.agents.agent_ids[initiator].clone(),
        target_index: target,
        target_id: request.agents.agent_ids[target].clone(),
        place_index,
        place_id: place.id.clone(),
        relationship_type: relationship_after.kind.clone(),
        relationship_weight: relationship_after.weight,
        trust: relationship_after.trust,
        similarity: relationship_after.similarity,
        probability: candidate.probability,
        factors: candidate.factors,
        state_deltas,
        relationship_deltas,
        interaction_tree: Some(InteractionTreeTrace {
            tree_id: result.tree_id,
            tree_version: result.tree_version,
            outcome_node: result.outcome_node,
            outcome: result.outcome,
            path: result
                .path
                .into_iter()
                .map(|step| InteractionTreePathRecord {
                    tree_id: step.tree_id,
                    node_id: step.node_id,
                    transition_id: step.transition_id,
                    outcome: step.outcome,
                    probability: step.probability,
                    draw: step.draw,
                    evidence: step.evidence,
                    factors: step.factors,
                    outgoing_probabilities: step.outgoing_probabilities,
                })
                .collect(),
        }),
    })
}

fn participant(
    request: &InteractionRequest,
    states: &BTreeMap<String, Vec<f64>>,
    agent: usize,
) -> InteractionParticipant {
    InteractionParticipant {
        agent_id: request.agents.agent_ids[agent].clone(),
        place_id: request.places[request.agents.place[agent]].id.clone(),
        traits: request
            .agents
            .traits
            .iter()
            .map(|(field, values)| (field.clone(), ContextValue::Number(values[agent])))
            .collect(),
        states: states
            .iter()
            .map(|(field, values)| (field.clone(), values[agent]))
            .collect(),
        routines: request.agents.actions[agent].iter().cloned().collect(),
    }
}

fn directed_relationship(
    request: &InteractionRequest,
    relationship: &InteractionRelationship,
    source: usize,
    target: usize,
) -> DirectedRelationship {
    DirectedRelationship {
        source_agent_id: request.agents.agent_ids[source].clone(),
        target_agent_id: request.agents.agent_ids[target].clone(),
        eligible: true,
        relationship_type: relationship.kind.clone(),
        states: BTreeMap::from([
            ("weight".to_owned(), relationship.weight),
            ("trust".to_owned(), relationship.trust),
            ("similarity".to_owned(), relationship.similarity),
        ]),
    }
}

fn tree_state_deltas(
    result: &crate::interaction_trees::InteractionTreeResult,
    states: &BTreeMap<String, Vec<f64>>,
) -> Result<Vec<AppliedStateDelta>, InteractionError> {
    let mut deltas = Vec::new();
    for (recipient, before, after) in [
        ("actor", &result.actor_before, &result.actor_after),
        ("target", &result.target_before, &result.target_after),
    ] {
        if before.routines != after.routines {
            return Err(InteractionError::at(
                "UNSUPPORTED_TREE_ROUTINE_EFFECT",
                "Agent routine effects cannot be applied inside the numeric interaction tick",
                format!("interaction_tree.{recipient}.routines"),
            ));
        }
        for (field, before_value) in &before.states {
            let after_value = after.states[field];
            if !after_value.is_finite() {
                return Err(InteractionError::at(
                    "NON_FINITE_TREE_AGENT_STATE",
                    format!("Interaction tree produced non-finite {recipient} state {field}"),
                    format!("interaction_tree.{recipient}.states.{field}"),
                ));
            }
            if (after_value - before_value).abs() > 1e-12 {
                if !states.contains_key(field) {
                    return Err(InteractionError::at(
                        "UNKNOWN_TREE_AGENT_STATE",
                        format!("Interaction tree changed unknown agent state {field}"),
                        format!("interaction_tree.{recipient}.states.{field}"),
                    ));
                }
                deltas.push(AppliedStateDelta {
                    agent_id: after.agent_id.clone(),
                    state: field.clone(),
                    before: *before_value,
                    delta: after_value - before_value,
                    after: after_value,
                });
            }
        }
    }
    Ok(deltas)
}

fn tree_relationship_deltas(
    result: &crate::interaction_trees::InteractionTreeResult,
) -> Result<Vec<AppliedRelationshipDelta>, InteractionError> {
    let mut deltas = Vec::new();
    for field in ["weight", "trust", "similarity"] {
        let before = result.relationship_before.states[field];
        let after = result.relationship_after.states[field];
        if !after.is_finite() || !(-1.0..=1.0).contains(&after) {
            return Err(InteractionError::at(
                "INVALID_TREE_RELATIONSHIP_STATE",
                format!("Interaction tree produced {field} outside -1 to 1"),
                format!("interaction_tree.relationship.states.{field}"),
            ));
        }
        if (after - before).abs() > 1e-12 {
            deltas.push(AppliedRelationshipDelta {
                source_agent_id: result.relationship_after.source_agent_id.clone(),
                target_agent_id: result.relationship_after.target_agent_id.clone(),
                field: field.to_owned(),
                before,
                delta: after - before,
                after,
            });
        }
    }
    Ok(deltas)
}

fn commit_tree_agents(
    result: &crate::interaction_trees::InteractionTreeResult,
    states: &mut BTreeMap<String, Vec<f64>>,
    initiator: usize,
    target: usize,
) {
    for (participant, agent_index) in [
        (&result.actor_after, initiator),
        (&result.target_after, target),
    ] {
        for (field, value) in &participant.states {
            let column = states
                .get_mut(field)
                .expect("tree participant state came from an agent state column");
            column[agent_index] = *value;
        }
    }
}

fn commit_tree_relationship(
    result: &crate::interaction_trees::InteractionTreeResult,
    relationships: &mut Vec<InteractionRelationship>,
    source: usize,
    target: usize,
    agent_count: usize,
) -> Result<(), InteractionError> {
    let updated = InteractionRelationship {
        source_index: source,
        target_index: target,
        kind: result.relationship_after.relationship_type.clone(),
        weight: result.relationship_after.states["weight"],
        trust: result.relationship_after.states["trust"],
        similarity: result.relationship_after.states["similarity"],
    };
    validate_relationship(&updated, agent_count, "interaction_tree.relationship")?;
    if let Some(index) = relationships.iter().position(|relationship| {
        relationship.source_index == source && relationship.target_index == target
    }) {
        relationships[index] = updated;
    } else {
        relationships.push(updated);
    }
    Ok(())
}

fn interaction_tree_seed(
    seed: u64,
    tick: u64,
    rule_id: &str,
    initiator: usize,
    target: usize,
) -> u64 {
    let mut hash = 0xcbf29ce484222325_u64 ^ seed ^ tick.rotate_left(17);
    for byte in rule_id.bytes() {
        hash ^= u64::from(byte);
        hash = hash.wrapping_mul(0x100000001b3);
    }
    hash ^ (initiator as u64).rotate_left(29) ^ (target as u64).rotate_left(43)
}

fn ensure_relationship(
    relationships: &mut Vec<InteractionRelationship>,
    source: usize,
    target: usize,
    template: &InteractionRelationship,
) -> usize {
    if let Some(index) = relationships.iter().position(|relationship| {
        relationship.source_index == source && relationship.target_index == target
    }) {
        return index;
    }
    relationships.push(InteractionRelationship {
        source_index: source,
        target_index: target,
        kind: template.kind.clone(),
        weight: template.weight,
        trust: template.trust,
        similarity: template.similarity,
    });
    relationships.len() - 1
}
