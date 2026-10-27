use rand::Rng;
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(untagged)]
pub enum ContextValue {
    Number(f64),
    Text(String),
    Flag(bool),
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InteractionTreeRequest {
    pub seed: u64,
    pub tick: u64,
    pub tree: InteractionTreeDefinition,
    #[serde(default)]
    pub trees: BTreeMap<String, InteractionTreeDefinition>,
    pub context: InteractionTreeContext,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct InteractionTreeDefinition {
    pub id: String,
    pub name: String,
    pub version: String,
    pub entry_node: String,
    pub allowed_channels: Vec<String>,
    pub co_location_policy: String,
    pub nodes: Vec<InteractionTreeNode>,
    pub transitions: Vec<InteractionTreeTransition>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct InteractionTreeNode {
    pub id: String,
    pub label: String,
    pub terminal: bool,
    #[serde(default)]
    pub target_tree_id: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct InteractionTreeTransition {
    pub id: String,
    pub from_node: String,
    pub to_node: String,
    pub outcome: String,
    pub probability: f64,
    #[serde(default)]
    pub probability_factors: Vec<InteractionProbabilityFactor>,
    pub evidence: InteractionTransitionEvidence,
    #[serde(default)]
    pub conditions: Vec<InteractionTreeCondition>,
    #[serde(default)]
    pub effects: Vec<InteractionTreeEffect>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct InteractionProbabilityFactor {
    pub id: String,
    pub label: String,
    pub cases: Vec<InteractionProbabilityFactorCase>,
    pub evidence: InteractionTransitionEvidence,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct InteractionProbabilityFactorCase {
    pub id: String,
    pub conditions: Vec<InteractionTreeCondition>,
    pub multiplier: f64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct InteractionTransitionEvidence {
    pub source: String,
    pub version: String,
    pub status: String,
    pub uncertainty: f64,
    #[serde(default)]
    pub source_date: Option<String>,
    #[serde(default)]
    pub evidence_id: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct InteractionTreeCondition {
    pub input: String,
    pub operator: String,
    pub value: ContextValue,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum InteractionTreeEffect {
    AgentState {
        participant: String,
        field: String,
        operation: String,
        value: f64,
        minimum: Option<f64>,
        maximum: Option<f64>,
        #[serde(default)]
        scale_by: Vec<String>,
    },
    AgentRoutine {
        participant: String,
        operation: String,
        routine_id: String,
    },
    RelationshipState {
        field: String,
        operation: String,
        value: f64,
        minimum: Option<f64>,
        maximum: Option<f64>,
        #[serde(default)]
        scale_by: Vec<String>,
    },
    RelationshipKind {
        relationship_type: String,
    },
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct InteractionParticipant {
    pub agent_id: String,
    pub place_id: String,
    #[serde(default)]
    pub traits: BTreeMap<String, ContextValue>,
    #[serde(default)]
    pub states: BTreeMap<String, f64>,
    #[serde(default)]
    pub routines: BTreeSet<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct DirectedRelationship {
    pub source_agent_id: String,
    pub target_agent_id: String,
    pub eligible: bool,
    pub relationship_type: String,
    #[serde(default)]
    pub states: BTreeMap<String, f64>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InteractionPlaceContext {
    pub id: String,
    pub kind: String,
    #[serde(default)]
    pub states: BTreeMap<String, f64>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InteractionTimeContext {
    pub weekday: u8,
    pub hour: f64,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InteractionTreeContext {
    pub actor: InteractionParticipant,
    pub target: InteractionParticipant,
    pub relationship: DirectedRelationship,
    pub place: InteractionPlaceContext,
    pub time: InteractionTimeContext,
    pub channel: String,
    #[serde(default)]
    pub attributes: BTreeMap<String, ContextValue>,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct InteractionTreeResult {
    pub tree_id: String,
    pub tree_version: String,
    pub seed: u64,
    pub tick: u64,
    pub outcome_node: String,
    pub outcome: String,
    pub path: Vec<InteractionPathStep>,
    pub receipt: InteractionTreeReceipt,
    pub actor_before: InteractionParticipant,
    pub actor_after: InteractionParticipant,
    pub target_before: InteractionParticipant,
    pub target_after: InteractionParticipant,
    pub relationship_before: DirectedRelationship,
    pub relationship_after: DirectedRelationship,
    pub changes: Vec<InteractionTreeChange>,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct InteractionPathStep {
    pub tree_id: String,
    pub node_id: String,
    pub transition_id: String,
    pub outcome: String,
    pub probability: f64,
    pub draw: f64,
    pub evidence: InteractionTransitionEvidence,
    pub factors: Vec<EvaluatedInteractionProbabilityFactor>,
    pub outgoing_probabilities: Vec<EvaluatedInteractionTransition>,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct EvaluatedInteractionProbabilityFactor {
    pub factor_id: String,
    pub label: String,
    pub case_id: String,
    pub multiplier: f64,
    pub inputs: BTreeMap<String, ContextValue>,
    pub evidence: InteractionTransitionEvidence,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct EvaluatedInteractionTransition {
    pub transition_id: String,
    pub outcome: String,
    pub base_probability: f64,
    pub unnormalized_weight: f64,
    pub probability: f64,
    pub factors: Vec<EvaluatedInteractionProbabilityFactor>,
    pub evidence: InteractionTransitionEvidence,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct InteractionTreeReceipt {
    pub actor_id: String,
    pub target_id: String,
    pub relationship_direction: String,
    pub place_id: String,
    pub channel: String,
    pub weekday: u8,
    pub hour: f64,
}

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct InteractionTreeChange {
    pub recipient: String,
    pub field: String,
    pub before: ContextValue,
    pub after: ContextValue,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct InteractionTreeError {
    pub code: String,
    pub message: String,
    pub path: String,
}

impl InteractionTreeError {
    fn at(code: &str, message: impl Into<String>, path: impl Into<String>) -> Self {
        Self {
            code: code.to_owned(),
            message: message.into(),
            path: path.into(),
        }
    }
}

#[path = "interaction_tree_runtime.rs"]
mod interaction_tree_runtime;
#[path = "interaction_tree_validation.rs"]
mod interaction_tree_validation;

use interaction_tree_runtime::{
    apply_effect, effect_scale, evaluate_probability_factor, transition_matches,
};

const MAX_INTERACTION_TREE_DEPTH: usize = 5;

#[derive(Clone)]
struct PendingInteractionTreeEffect {
    effect: InteractionTreeEffect,
    scale: f64,
}

pub fn run(request: InteractionTreeRequest) -> Result<InteractionTreeResult, InteractionTreeError> {
    validate_request(&request)?;
    let mut rng = ChaCha8Rng::seed_from_u64(request.seed);
    let mut path = Vec::new();
    let mut effects = Vec::new();
    let (outcome_node, outcome) = traverse_tree(
        &request.tree,
        &request.trees,
        &request.context,
        &mut rng,
        1,
        &mut path,
        &mut effects,
    )?;
    let actor_before = request.context.actor.clone();
    let target_before = request.context.target.clone();
    let relationship_before = request.context.relationship.clone();
    let mut actor_after = actor_before.clone();
    let mut target_after = target_before.clone();
    let mut relationship_after = relationship_before.clone();
    let mut changes = Vec::new();
    for pending in &effects {
        apply_effect(
            &pending.effect,
            pending.scale,
            &mut actor_after,
            &mut target_after,
            &mut relationship_after,
            &mut changes,
        )?;
    }
    Ok(InteractionTreeResult {
        tree_id: request.tree.id.clone(),
        tree_version: request.tree.version.clone(),
        seed: request.seed,
        tick: request.tick,
        outcome_node,
        outcome,
        path,
        receipt: InteractionTreeReceipt {
            actor_id: actor_before.agent_id.clone(),
            target_id: target_before.agent_id.clone(),
            relationship_direction: format!(
                "{}→{}",
                relationship_before.source_agent_id, relationship_before.target_agent_id
            ),
            place_id: request.context.place.id.clone(),
            channel: request.context.channel.clone(),
            weekday: request.context.time.weekday,
            hour: request.context.time.hour,
        },
        actor_before,
        actor_after,
        target_before,
        target_after,
        relationship_before,
        relationship_after,
        changes,
    })
}

fn traverse_tree(
    tree: &InteractionTreeDefinition,
    trees: &BTreeMap<String, InteractionTreeDefinition>,
    context: &InteractionTreeContext,
    rng: &mut ChaCha8Rng,
    depth: usize,
    path: &mut Vec<InteractionPathStep>,
    effects: &mut Vec<PendingInteractionTreeEffect>,
) -> Result<(String, String), InteractionTreeError> {
    if depth > MAX_INTERACTION_TREE_DEPTH {
        return Err(InteractionTreeError::at(
            "INTERACTION_TREE_REFERENCE_DEPTH",
            format!("Interaction tree reference depth exceeds {MAX_INTERACTION_TREE_DEPTH}"),
            format!("trees.{}", tree.id),
        ));
    }
    let nodes: BTreeMap<_, _> = tree
        .nodes
        .iter()
        .map(|node| (node.id.as_str(), node))
        .collect();
    let mut current_node = tree.entry_node.as_str();
    let mut outcome = String::new();
    let mut steps = 0;
    loop {
        let node = nodes[current_node];
        if let Some(target_tree_id) = &node.target_tree_id {
            let target_tree = trees.get(target_tree_id).ok_or_else(|| {
                InteractionTreeError::at(
                    "MISSING_INTERACTION_TREE_REFERENCE",
                    format!(
                        "Interaction tree {} node {} references missing tree {target_tree_id}",
                        tree.id, node.id
                    ),
                    format!("trees.{}.nodes.{}", tree.id, node.id),
                )
            })?;
            let (_, nested_outcome) =
                traverse_tree(target_tree, trees, context, rng, depth + 1, path, effects)?;
            outcome = nested_outcome;
        }
        if node.terminal {
            return Ok((current_node.to_owned(), outcome));
        }
        let eligible: Vec<_> = tree
            .transitions
            .iter()
            .filter(|transition| transition.from_node == current_node)
            .filter_map(|transition| match transition_matches(transition, context) {
                Ok(true) => Some(Ok(transition)),
                Ok(false) => None,
                Err(error) => Some(Err(error)),
            })
            .collect::<Result<_, _>>()?;
        if eligible.is_empty() {
            return Err(InteractionTreeError::at(
                "NO_ELIGIBLE_TRANSITION",
                format!("Node {current_node} has no transition for this actor and target context"),
                format!("trees.{}.nodes.{current_node}", tree.id),
            ));
        }
        let mut evaluated = eligible
            .iter()
            .map(|transition| {
                let factors = transition
                    .probability_factors
                    .iter()
                    .map(|factor| evaluate_probability_factor(factor, context))
                    .collect::<Result<Vec<_>, _>>()?;
                let unnormalized_weight = transition.probability
                    * factors
                        .iter()
                        .map(|factor| factor.multiplier)
                        .product::<f64>();
                Ok((transition, factors, unnormalized_weight))
            })
            .collect::<Result<Vec<_>, InteractionTreeError>>()?;
        let total = evaluated
            .iter()
            .map(|(_, _, unnormalized_weight)| unnormalized_weight)
            .sum::<f64>();
        let has_dynamic_factors = evaluated
            .iter()
            .any(|(transition, _, _)| !transition.probability_factors.is_empty());
        if !total.is_finite() || total <= 0.0 {
            return Err(InteractionTreeError::at(
                "INVALID_CONTEXT_PROBABILITY_TOTAL",
                format!("Eligible transitions from {current_node} have no positive total weight"),
                format!("trees.{}.nodes.{current_node}", tree.id),
            ));
        }
        if !has_dynamic_factors && (total - 1.0).abs() > 1e-9 {
            return Err(InteractionTreeError::at(
                "INVALID_CONTEXT_PROBABILITY_TOTAL",
                format!("Eligible transitions from {current_node} sum to {total}, expected 1"),
                format!("trees.{}.nodes.{current_node}", tree.id),
            ));
        }
        let outgoing_probabilities = evaluated
            .iter()
            .map(
                |(transition, factors, unnormalized_weight)| EvaluatedInteractionTransition {
                    transition_id: transition.id.clone(),
                    outcome: transition.outcome.clone(),
                    base_probability: transition.probability,
                    unnormalized_weight: *unnormalized_weight,
                    probability: if has_dynamic_factors {
                        *unnormalized_weight / total
                    } else {
                        *unnormalized_weight
                    },
                    factors: factors.clone(),
                    evidence: transition.evidence.clone(),
                },
            )
            .collect::<Vec<_>>();
        let draw = rng.r#gen::<f64>();
        let mut boundary = 0.0;
        let selected_index = outgoing_probabilities
            .iter()
            .position(|transition| {
                boundary += transition.probability;
                draw < boundary
            })
            .unwrap_or(outgoing_probabilities.len() - 1);
        let selected = evaluated.swap_remove(selected_index);
        let selected_transition = selected.0;
        let selected_evaluation = &outgoing_probabilities[selected_index];
        path.push(InteractionPathStep {
            tree_id: tree.id.clone(),
            node_id: current_node.to_owned(),
            transition_id: selected_transition.id.clone(),
            outcome: selected_transition.outcome.clone(),
            probability: selected_evaluation.probability,
            draw,
            evidence: selected_transition.evidence.clone(),
            factors: selected_evaluation.factors.clone(),
            outgoing_probabilities,
        });
        for effect in &selected_transition.effects {
            effects.push(PendingInteractionTreeEffect {
                effect: effect.clone(),
                scale: effect_scale(effect, context)?,
            });
        }
        outcome.clone_from(&selected_transition.outcome);
        current_node = selected_transition.to_node.as_str();
        steps += 1;
        if steps > tree.nodes.len() {
            return Err(InteractionTreeError::at(
                "TREE_TRAVERSAL_LIMIT",
                "Interaction tree traversal exceeded its node count",
                format!("trees.{}", tree.id),
            ));
        }
    }
}

pub fn validate_request(request: &InteractionTreeRequest) -> Result<(), InteractionTreeError> {
    interaction_tree_validation::validate_request(request)
}

pub fn validate_registry(
    definitions: &BTreeMap<String, InteractionTreeDefinition>,
) -> Result<(), InteractionTreeError> {
    interaction_tree_validation::validate_registry(definitions)
}
