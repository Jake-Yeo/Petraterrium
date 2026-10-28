use super::*;
use std::collections::{BTreeMap, BTreeSet};

pub(super) fn validate_request(
    request: &InteractionTreeRequest,
) -> Result<(), InteractionTreeError> {
    for (tree_id, tree) in &request.trees {
        if tree_id != &tree.id {
            return Err(InteractionTreeError::at(
                "INTERACTION_TREE_ID_MISMATCH",
                format!(
                    "Interaction tree registry key {tree_id} contains tree {}",
                    tree.id
                ),
                format!("trees.{tree_id}"),
            ));
        }
    }
    let mut definitions = request.trees.clone();
    definitions.insert(request.tree.id.clone(), request.tree.clone());
    validate_registry(&definitions)?;
    let registry: BTreeMap<_, _> = definitions
        .iter()
        .map(|(tree_id, tree)| (tree_id.as_str(), tree))
        .collect();
    let mut reachable = BTreeSet::new();
    validate_reachable_context(
        request.tree.id.as_str(),
        &registry,
        &request.context,
        &mut reachable,
    )?;
    Ok(())
}

pub(super) fn validate_registry(
    definitions: &BTreeMap<String, InteractionTreeDefinition>,
) -> Result<(), InteractionTreeError> {
    let mut registry = BTreeMap::new();
    for (tree_id, tree) in definitions {
        if tree_id != &tree.id {
            return Err(InteractionTreeError::at(
                "INTERACTION_TREE_ID_MISMATCH",
                format!(
                    "Interaction tree registry key {tree_id} contains tree {}",
                    tree.id
                ),
                format!("trees.{tree_id}"),
            ));
        }
        validate_tree(tree)?;
        registry.insert(tree_id.as_str(), tree);
    }
    validate_reference_registry(&registry)
}

fn validate_tree(tree: &InteractionTreeDefinition) -> Result<(), InteractionTreeError> {
    if tree.id.trim().is_empty() || tree.name.trim().is_empty() || tree.version.trim().is_empty() {
        return Err(InteractionTreeError::at(
            "INVALID_TREE_IDENTITY",
            "Interaction trees require an id, name, and version",
            "tree",
        ));
    }
    if tree.allowed_channels.is_empty()
        || tree
            .allowed_channels
            .iter()
            .any(|channel| channel.trim().is_empty())
    {
        return Err(InteractionTreeError::at(
            "MISSING_ALLOWED_CHANNEL",
            "Interaction trees require at least one allowed channel",
            "tree.allowed_channels",
        ));
    }
    let channels: BTreeSet<_> = tree.allowed_channels.iter().collect();
    if channels.len() != tree.allowed_channels.len() {
        return Err(InteractionTreeError::at(
            "DUPLICATE_ALLOWED_CHANNEL",
            "Interaction tree allowed channels must be unique",
            "tree.allowed_channels",
        ));
    }
    if !matches!(
        tree.co_location_policy.as_str(),
        "required" | "remote_allowed"
    ) {
        return Err(InteractionTreeError::at(
            "INVALID_CO_LOCATION_POLICY",
            "Co-location policy must be required or remote_allowed",
            "tree.co_location_policy",
        ));
    }
    let node_ids: BTreeSet<_> = tree.nodes.iter().map(|node| node.id.as_str()).collect();
    if tree.nodes.is_empty()
        || node_ids.len() != tree.nodes.len()
        || tree.nodes.iter().any(|node| {
            node.id.trim().is_empty()
                || node.label.trim().is_empty()
                || node
                    .target_tree_id
                    .as_ref()
                    .is_some_and(|tree_id| tree_id.trim().is_empty())
        })
    {
        return Err(InteractionTreeError::at(
            "INVALID_TREE_NODES",
            "Interaction tree nodes require unique ids and labels",
            "tree.nodes",
        ));
    }
    if !node_ids.contains(tree.entry_node.as_str()) {
        return Err(InteractionTreeError::at(
            "UNKNOWN_ENTRY_NODE",
            "Interaction tree entry node is not declared",
            "tree.entry_node",
        ));
    }
    let transition_ids: BTreeSet<_> = tree
        .transitions
        .iter()
        .map(|transition| transition.id.as_str())
        .collect();
    if transition_ids.len() != tree.transitions.len() {
        return Err(InteractionTreeError::at(
            "DUPLICATE_TRANSITION",
            "Interaction tree transition ids must be unique",
            "tree.transitions",
        ));
    }
    for (index, transition) in tree.transitions.iter().enumerate() {
        let path = format!("tree.transitions.{index}");
        if !node_ids.contains(transition.from_node.as_str())
            || !node_ids.contains(transition.to_node.as_str())
        {
            return Err(InteractionTreeError::at(
                "UNKNOWN_TRANSITION_NODE",
                "Interaction tree transitions must connect declared nodes",
                path,
            ));
        }
        if nodes_terminal(tree, &transition.from_node) {
            return Err(InteractionTreeError::at(
                "TERMINAL_NODE_HAS_TRANSITION",
                "Terminal interaction tree nodes cannot have outgoing transitions",
                path,
            ));
        }
        if !transition.probability.is_finite()
            || transition.probability < 0.0
            || transition.probability > 1.0
        {
            return Err(InteractionTreeError::at(
                "INVALID_TRANSITION_PROBABILITY",
                "Interaction transition probabilities must be finite and between 0 and 1",
                format!("{path}.probability"),
            ));
        }
        validate_evidence(&transition.evidence, &format!("{path}.evidence"))?;
        let mut factor_ids = BTreeSet::new();
        for (factor_index, factor) in transition.probability_factors.iter().enumerate() {
            validate_probability_factor(
                factor,
                &format!("{path}.probability_factors.{factor_index}"),
            )?;
            if !factor_ids.insert(factor.id.as_str()) {
                return Err(InteractionTreeError::at(
                    "DUPLICATE_PROBABILITY_FACTOR",
                    "Interaction transition probability factor ids must be unique",
                    format!("{path}.probability_factors.{factor_index}.id"),
                ));
            }
        }
        for (condition_index, condition) in transition.conditions.iter().enumerate() {
            validate_condition(condition, &format!("{path}.conditions.{condition_index}"))?;
        }
        for (effect_index, effect) in transition.effects.iter().enumerate() {
            validate_effect(effect, &format!("{path}.effects.{effect_index}"))?;
        }
    }
    for node in &tree.nodes {
        if !node.terminal
            && !tree
                .transitions
                .iter()
                .any(|transition| transition.from_node == node.id)
        {
            return Err(InteractionTreeError::at(
                "NON_TERMINAL_DEAD_END",
                format!("Non-terminal node {} has no outgoing transitions", node.id),
                format!("tree.nodes.{}", node.id),
            ));
        }
    }
    let mut reachable = BTreeSet::new();
    let mut pending = vec![tree.entry_node.as_str()];
    while let Some(node_id) = pending.pop() {
        if !reachable.insert(node_id) {
            continue;
        }
        pending.extend(
            tree.transitions
                .iter()
                .filter(|transition| transition.from_node == node_id)
                .map(|transition| transition.to_node.as_str()),
        );
    }
    if reachable.len() != tree.nodes.len() {
        let unreachable = node_ids
            .difference(&reachable)
            .copied()
            .collect::<Vec<_>>()
            .join(", ");
        return Err(InteractionTreeError::at(
            "UNREACHABLE_TREE_NODE",
            format!("Interaction tree contains unreachable nodes: {unreachable}"),
            "tree.nodes",
        ));
    }
    reject_cycles(
        tree,
        &tree.entry_node,
        &mut Vec::new(),
        &mut BTreeSet::new(),
    )?;
    Ok(())
}

fn validate_reference_registry(
    registry: &BTreeMap<&str, &InteractionTreeDefinition>,
) -> Result<(), InteractionTreeError> {
    for (tree_id, tree) in registry {
        for node in &tree.nodes {
            if let Some(target_tree_id) = &node.target_tree_id
                && !registry.contains_key(target_tree_id.as_str())
            {
                return Err(InteractionTreeError::at(
                    "MISSING_INTERACTION_TREE_REFERENCE",
                    format!(
                        "Interaction tree {tree_id} node {} references missing tree {target_tree_id}",
                        node.id
                    ),
                    format!("trees.{tree_id}.nodes.{}", node.id),
                ));
            }
        }
    }
    for tree_id in registry.keys() {
        validate_reference_path(tree_id, registry, &mut Vec::new())?;
    }
    Ok(())
}

fn validate_reference_path<'a>(
    tree_id: &'a str,
    registry: &BTreeMap<&'a str, &'a InteractionTreeDefinition>,
    active: &mut Vec<&'a str>,
) -> Result<(), InteractionTreeError> {
    if let Some(position) = active.iter().position(|active_id| *active_id == tree_id) {
        let mut cycle = active[position..].to_vec();
        cycle.push(tree_id);
        return Err(InteractionTreeError::at(
            "INTERACTION_TREE_REFERENCE_CYCLE",
            format!("Interaction tree reference cycle: {}", cycle.join(" → ")),
            format!("trees.{tree_id}"),
        ));
    }
    if active.len() + 1 > MAX_INTERACTION_TREE_DEPTH {
        let mut chain = active.clone();
        chain.push(tree_id);
        return Err(InteractionTreeError::at(
            "INTERACTION_TREE_REFERENCE_DEPTH",
            format!(
                "Interaction tree reference depth exceeds {MAX_INTERACTION_TREE_DEPTH}: {}",
                chain.join(" → ")
            ),
            format!("trees.{tree_id}"),
        ));
    }
    active.push(tree_id);
    for target_tree_id in registry[tree_id]
        .nodes
        .iter()
        .filter_map(|node| node.target_tree_id.as_deref())
    {
        validate_reference_path(target_tree_id, registry, active)?;
    }
    active.pop();
    Ok(())
}

fn validate_reachable_context<'a>(
    tree_id: &'a str,
    registry: &BTreeMap<&'a str, &'a InteractionTreeDefinition>,
    context: &InteractionTreeContext,
    reachable: &mut BTreeSet<&'a str>,
) -> Result<(), InteractionTreeError> {
    if !reachable.insert(tree_id) {
        return Ok(());
    }
    let tree = registry[tree_id];
    validate_context(tree, context)?;
    for target_tree_id in tree
        .nodes
        .iter()
        .filter_map(|node| node.target_tree_id.as_deref())
    {
        validate_reachable_context(target_tree_id, registry, context, reachable)?;
    }
    Ok(())
}

fn nodes_terminal(tree: &InteractionTreeDefinition, node_id: &str) -> bool {
    tree.nodes
        .iter()
        .find(|node| node.id == node_id)
        .is_some_and(|node| node.terminal)
}

fn reject_cycles<'a>(
    tree: &'a InteractionTreeDefinition,
    node_id: &'a str,
    active: &mut Vec<&'a str>,
    complete: &mut BTreeSet<&'a str>,
) -> Result<(), InteractionTreeError> {
    if let Some(position) = active.iter().position(|active_id| *active_id == node_id) {
        let mut cycle = active[position..].to_vec();
        cycle.push(node_id);
        return Err(InteractionTreeError::at(
            "INTERACTION_TREE_CYCLE",
            format!("Interaction tree cycle: {}", cycle.join(" → ")),
            format!("tree.nodes.{node_id}"),
        ));
    }
    if complete.contains(node_id) {
        return Ok(());
    }
    active.push(node_id);
    for target in tree
        .transitions
        .iter()
        .filter(|transition| transition.from_node == node_id)
        .map(|transition| transition.to_node.as_str())
    {
        reject_cycles(tree, target, active, complete)?;
    }
    active.pop();
    complete.insert(node_id);
    Ok(())
}

fn validate_evidence(
    evidence: &InteractionTransitionEvidence,
    path: &str,
) -> Result<(), InteractionTreeError> {
    if evidence.source.trim().is_empty()
        || evidence.version.trim().is_empty()
        || !evidence.uncertainty.is_finite()
        || evidence.uncertainty < 0.0
    {
        return Err(InteractionTreeError::at(
            "INVALID_TRANSITION_EVIDENCE",
            "Interaction transition evidence requires source, version, and uncertainty",
            path,
        ));
    }
    if !matches!(
        evidence.status.as_str(),
        "measured_joint" | "fitted_model" | "default_estimated" | "approved_estimate"
    ) {
        return Err(InteractionTreeError::at(
            "NON_PREDICTIVE_TRANSITION_EVIDENCE",
            format!(
                "Evidence status {} cannot select an interaction transition",
                evidence.status
            ),
            format!("{path}.status"),
        ));
    }
    Ok(())
}

fn validate_probability_factor(
    factor: &InteractionProbabilityFactor,
    path: &str,
) -> Result<(), InteractionTreeError> {
    if factor.id.trim().is_empty() || factor.label.trim().is_empty() || factor.cases.is_empty() {
        return Err(InteractionTreeError::at(
            "INVALID_PROBABILITY_FACTOR",
            "Interaction probability factors require an id, label, and at least one case",
            path,
        ));
    }
    validate_evidence(&factor.evidence, &format!("{path}.evidence"))?;
    let mut case_ids = BTreeSet::new();
    for (case_index, case) in factor.cases.iter().enumerate() {
        let case_path = format!("{path}.cases.{case_index}");
        if case.id.trim().is_empty()
            || case.conditions.is_empty()
            || !case.multiplier.is_finite()
            || case.multiplier < 0.0
        {
            return Err(InteractionTreeError::at(
                "INVALID_PROBABILITY_FACTOR_CASE",
                "Probability factor cases require an id, conditions, and a non-negative finite multiplier",
                case_path,
            ));
        }
        if !case_ids.insert(case.id.as_str()) {
            return Err(InteractionTreeError::at(
                "DUPLICATE_PROBABILITY_FACTOR_CASE",
                "Probability factor case ids must be unique within a factor",
                format!("{case_path}.id"),
            ));
        }
        for (condition_index, condition) in case.conditions.iter().enumerate() {
            validate_condition(
                condition,
                &format!("{case_path}.conditions.{condition_index}"),
            )?;
        }
    }
    Ok(())
}

fn validate_condition(
    condition: &InteractionTreeCondition,
    path: &str,
) -> Result<(), InteractionTreeError> {
    if condition.input.trim().is_empty()
        || !supported_context_input(&condition.input)
        || !matches!(
            condition.operator.as_str(),
            "eq" | "ne" | "gt" | "gte" | "lt" | "lte"
        )
    {
        return Err(InteractionTreeError::at(
            "INVALID_INTERACTION_CONDITION",
            "Interaction conditions require an input and supported operator",
            path,
        ));
    }
    Ok(())
}

fn supported_context_input(input: &str) -> bool {
    matches!(
        input,
        "actor.id"
            | "target.id"
            | "actor.place_id"
            | "target.place_id"
            | "relationship.kind"
            | "place.id"
            | "place.kind"
            | "time.weekday"
            | "time.hour"
            | "channel"
            | "co_located"
    ) || [
        "actor.trait.",
        "target.trait.",
        "actor.state.",
        "target.state.",
        "actor.routine.",
        "target.routine.",
        "relationship.state.",
        "place.state.",
        "context.",
    ]
    .iter()
    .any(|prefix| {
        input
            .strip_prefix(prefix)
            .is_some_and(|field| !field.is_empty())
    })
}

fn validate_effect(effect: &InteractionTreeEffect, path: &str) -> Result<(), InteractionTreeError> {
    match effect {
        InteractionTreeEffect::AgentState {
            participant,
            field,
            operation,
            value,
            minimum,
            maximum,
            scale_by,
        } => {
            validate_participant(participant, path)?;
            validate_numeric_effect(field, operation, *value, *minimum, *maximum, path)?;
            validate_effect_scales(scale_by, path)
        }
        InteractionTreeEffect::AgentRoutine {
            participant,
            operation,
            routine_id,
        } => {
            validate_participant(participant, path)?;
            if !matches!(operation.as_str(), "add" | "remove") || routine_id.trim().is_empty() {
                return Err(InteractionTreeError::at(
                    "INVALID_ROUTINE_EFFECT",
                    "Routine effects require add or remove and a routine id",
                    path,
                ));
            }
            Ok(())
        }
        InteractionTreeEffect::RelationshipState {
            field,
            operation,
            value,
            minimum,
            maximum,
            scale_by,
        } => {
            validate_numeric_effect(field, operation, *value, *minimum, *maximum, path)?;
            validate_effect_scales(scale_by, path)
        }
        InteractionTreeEffect::RelationshipKind { relationship_type } => {
            if relationship_type.trim().is_empty() {
                return Err(InteractionTreeError::at(
                    "INVALID_RELATIONSHIP_KIND_EFFECT",
                    "Relationship kind effects require a relationship type",
                    path,
                ));
            }
            Ok(())
        }
    }
}

fn validate_effect_scales(scale_by: &[String], path: &str) -> Result<(), InteractionTreeError> {
    let unique = scale_by.iter().collect::<BTreeSet<_>>();
    if unique.len() != scale_by.len()
        || scale_by.iter().any(|input| !supported_context_input(input))
    {
        return Err(InteractionTreeError::at(
            "INVALID_EFFECT_SCALE_INPUT",
            "Interaction effect scales must name unique supported runtime inputs",
            format!("{path}.scale_by"),
        ));
    }
    Ok(())
}

fn validate_participant(participant: &str, path: &str) -> Result<(), InteractionTreeError> {
    if !matches!(participant, "actor" | "target") {
        return Err(InteractionTreeError::at(
            "INVALID_EFFECT_PARTICIPANT",
            "Interaction effects must target actor or target",
            path,
        ));
    }
    Ok(())
}

fn validate_numeric_effect(
    field: &str,
    operation: &str,
    value: f64,
    minimum: Option<f64>,
    maximum: Option<f64>,
    path: &str,
) -> Result<(), InteractionTreeError> {
    if field.trim().is_empty()
        || !matches!(operation, "set" | "add")
        || !value.is_finite()
        || minimum.is_some_and(|limit| !limit.is_finite())
        || maximum.is_some_and(|limit| !limit.is_finite())
        || matches!((minimum, maximum), (Some(low), Some(high)) if low > high)
    {
        return Err(InteractionTreeError::at(
            "INVALID_NUMERIC_EFFECT",
            "Numeric effects require a field, set or add, finite values, and ordered bounds",
            path,
        ));
    }
    Ok(())
}

fn validate_context(
    tree: &InteractionTreeDefinition,
    context: &InteractionTreeContext,
) -> Result<(), InteractionTreeError> {
    if context.actor.agent_id == context.target.agent_id {
        return Err(InteractionTreeError::at(
            "SELF_INTERACTION",
            "Interaction trees require two distinct agents",
            "context.target.agent_id",
        ));
    }
    if context.relationship.source_agent_id != context.actor.agent_id
        || context.relationship.target_agent_id != context.target.agent_id
        || !context.relationship.eligible
    {
        return Err(InteractionTreeError::at(
            "INELIGIBLE_DIRECTED_RELATIONSHIP",
            "Interaction requires an eligible relationship directed from actor to target",
            "context.relationship",
        ));
    }
    if !tree
        .allowed_channels
        .iter()
        .any(|channel| channel == &context.channel)
    {
        return Err(InteractionTreeError::at(
            "CHANNEL_NOT_ALLOWED",
            format!(
                "Channel {} is not allowed by this interaction tree",
                context.channel
            ),
            "context.channel",
        ));
    }
    let co_located = context.actor.place_id == context.target.place_id;
    if context.channel == "in_person" && !co_located {
        return Err(InteractionTreeError::at(
            "IN_PERSON_REQUIRES_CO_LOCATION",
            "In-person interaction requires both agents at the same specific place",
            "context",
        ));
    }
    if tree.co_location_policy == "required" && !co_located {
        return Err(InteractionTreeError::at(
            "CO_LOCATION_REQUIRED",
            "This interaction tree requires both agents at the same specific place",
            "context",
        ));
    }
    if co_located && context.place.id != context.actor.place_id {
        return Err(InteractionTreeError::at(
            "PLACE_CONTEXT_MISMATCH",
            "Co-located interaction place must match both participant place ids",
            "context.place.id",
        ));
    }
    if context.time.weekday > 6
        || !context.time.hour.is_finite()
        || context.time.hour < 0.0
        || context.time.hour >= 24.0
    {
        return Err(InteractionTreeError::at(
            "INVALID_INTERACTION_TIME",
            "Interaction time requires weekday 0 to 6 and hour from 0 inclusive to 24 exclusive",
            "context.time",
        ));
    }
    if context
        .actor
        .states
        .values()
        .chain(context.target.states.values())
        .chain(context.relationship.states.values())
        .chain(context.place.states.values())
        .any(|value| !value.is_finite())
    {
        return Err(InteractionTreeError::at(
            "NON_FINITE_CONTEXT_STATE",
            "Interaction context states must be finite",
            "context",
        ));
    }
    Ok(())
}
