use super::*;
use std::collections::BTreeMap;

pub(super) fn transition_matches(
    transition: &InteractionTreeTransition,
    context: &InteractionTreeContext,
) -> Result<bool, InteractionTreeError> {
    transition
        .conditions
        .iter()
        .try_fold(true, |matches, condition| {
            if !matches {
                return Ok(false);
            }
            let actual = resolve_input(&condition.input, context)?;
            compare_values(actual, &condition.operator, &condition.value)
        })
}

pub(super) fn resolve_input(
    input: &str,
    context: &InteractionTreeContext,
) -> Result<ContextValue, InteractionTreeError> {
    let value = if input == "actor.id" {
        ContextValue::Text(context.actor.agent_id.clone())
    } else if input == "target.id" {
        ContextValue::Text(context.target.agent_id.clone())
    } else if input == "actor.place_id" {
        ContextValue::Text(context.actor.place_id.clone())
    } else if input == "target.place_id" {
        ContextValue::Text(context.target.place_id.clone())
    } else if input == "relationship.kind" {
        ContextValue::Text(context.relationship.relationship_type.clone())
    } else if input == "place.id" {
        ContextValue::Text(context.place.id.clone())
    } else if input == "place.kind" {
        ContextValue::Text(context.place.kind.clone())
    } else if input == "time.weekday" {
        ContextValue::Number(f64::from(context.time.weekday))
    } else if input == "time.hour" {
        ContextValue::Number(context.time.hour)
    } else if input == "channel" {
        ContextValue::Text(context.channel.clone())
    } else if input == "co_located" {
        ContextValue::Flag(context.actor.place_id == context.target.place_id)
    } else if let Some(field) = input.strip_prefix("actor.trait.") {
        trait_value(&context.actor.traits, field, input)?
    } else if let Some(field) = input.strip_prefix("target.trait.") {
        trait_value(&context.target.traits, field, input)?
    } else if let Some(field) = input.strip_prefix("actor.state.") {
        state_value(&context.actor.states, field, input)?
    } else if let Some(field) = input.strip_prefix("target.state.") {
        state_value(&context.target.states, field, input)?
    } else if let Some(routine) = input.strip_prefix("actor.routine.") {
        ContextValue::Flag(context.actor.routines.contains(routine))
    } else if let Some(routine) = input.strip_prefix("target.routine.") {
        ContextValue::Flag(context.target.routines.contains(routine))
    } else if let Some(field) = input.strip_prefix("relationship.state.") {
        state_value(&context.relationship.states, field, input)?
    } else if let Some(field) = input.strip_prefix("place.state.") {
        state_value(&context.place.states, field, input)?
    } else if let Some(field) = input.strip_prefix("context.") {
        context.attributes.get(field).cloned().ok_or_else(|| {
            InteractionTreeError::at(
                "MISSING_CONDITION_INPUT",
                format!("Interaction context does not provide {input}"),
                input,
            )
        })?
    } else {
        return Err(InteractionTreeError::at(
            "UNKNOWN_CONDITION_INPUT",
            format!("Unsupported interaction condition input {input}"),
            input,
        ));
    };
    Ok(value)
}

fn trait_value(
    traits: &BTreeMap<String, ContextValue>,
    field: &str,
    input: &str,
) -> Result<ContextValue, InteractionTreeError> {
    traits.get(field).cloned().ok_or_else(|| {
        InteractionTreeError::at(
            "MISSING_CONDITION_INPUT",
            format!("Interaction context does not provide {input}"),
            input,
        )
    })
}

pub(super) fn evaluate_probability_factor(
    factor: &InteractionProbabilityFactor,
    context: &InteractionTreeContext,
) -> Result<EvaluatedInteractionProbabilityFactor, InteractionTreeError> {
    let mut matches = Vec::new();
    for case in &factor.cases {
        let mut inputs = BTreeMap::new();
        let mut case_matches = true;
        for condition in &case.conditions {
            let actual = resolve_input(&condition.input, context).map_err(|error| {
                if error.code == "MISSING_CONDITION_INPUT" {
                    InteractionTreeError::at(
                        "MISSING_PROBABILITY_FACTOR_INPUT",
                        format!(
                            "Probability factor {} requires unavailable input {}",
                            factor.id, condition.input
                        ),
                        condition.input.clone(),
                    )
                } else {
                    error
                }
            })?;
            inputs.insert(condition.input.clone(), actual.clone());
            case_matches &= compare_values(actual, &condition.operator, &condition.value)?;
        }
        if case_matches {
            matches.push((case, inputs));
        }
    }
    if matches.len() != 1 {
        return Err(InteractionTreeError::at(
            if matches.is_empty() {
                "UNMATCHED_PROBABILITY_FACTOR"
            } else {
                "OVERLAPPING_PROBABILITY_FACTOR"
            },
            if matches.is_empty() {
                format!(
                    "Probability factor {} has no case for the actual interaction context",
                    factor.id
                )
            } else {
                format!(
                    "Probability factor {} has multiple cases for the actual interaction context",
                    factor.id
                )
            },
            format!("probability_factors.{}", factor.id),
        ));
    }
    let (case, inputs) = matches.pop().unwrap();
    Ok(EvaluatedInteractionProbabilityFactor {
        factor_id: factor.id.clone(),
        label: factor.label.clone(),
        case_id: case.id.clone(),
        multiplier: case.multiplier,
        inputs,
        evidence: factor.evidence.clone(),
    })
}

pub(super) fn effect_scale(
    effect: &InteractionTreeEffect,
    context: &InteractionTreeContext,
) -> Result<f64, InteractionTreeError> {
    let scale_by = match effect {
        InteractionTreeEffect::AgentState { scale_by, .. }
        | InteractionTreeEffect::RelationshipState { scale_by, .. } => scale_by,
        _ => return Ok(1.0),
    };
    scale_by.iter().try_fold(1.0, |scale, input| {
        let value = resolve_input(input, context).map_err(|error| {
            if error.code == "MISSING_CONDITION_INPUT" {
                InteractionTreeError::at(
                    "MISSING_EFFECT_SCALE_INPUT",
                    format!("Interaction effect scale requires unavailable input {input}"),
                    input.clone(),
                )
            } else {
                error
            }
        })?;
        let ContextValue::Number(value) = value else {
            return Err(InteractionTreeError::at(
                "NON_NUMERIC_EFFECT_SCALE_INPUT",
                format!("Interaction effect scale input {input} is not numeric"),
                input.clone(),
            ));
        };
        let next = scale * value;
        if !next.is_finite() {
            return Err(InteractionTreeError::at(
                "NON_FINITE_EFFECT_SCALE",
                "Interaction effect scale must remain finite",
                input.clone(),
            ));
        }
        Ok(next)
    })
}

fn state_value(
    states: &BTreeMap<String, f64>,
    field: &str,
    input: &str,
) -> Result<ContextValue, InteractionTreeError> {
    states
        .get(field)
        .copied()
        .map(ContextValue::Number)
        .ok_or_else(|| {
            InteractionTreeError::at(
                "MISSING_CONDITION_INPUT",
                format!("Interaction context does not provide {input}"),
                input,
            )
        })
}

fn compare_values(
    actual: ContextValue,
    operator: &str,
    expected: &ContextValue,
) -> Result<bool, InteractionTreeError> {
    match (actual, expected) {
        (ContextValue::Number(left), ContextValue::Number(right)) => Ok(match operator {
            "eq" => left == *right,
            "ne" => left != *right,
            "gt" => left > *right,
            "gte" => left >= *right,
            "lt" => left < *right,
            "lte" => left <= *right,
            _ => unreachable!(),
        }),
        (ContextValue::Text(left), ContextValue::Text(right)) => match operator {
            "eq" => Ok(left == *right),
            "ne" => Ok(left != *right),
            _ => Err(InteractionTreeError::at(
                "INVALID_CONDITION_COMPARISON",
                "Text interaction conditions support only eq and ne",
                "condition.operator",
            )),
        },
        (ContextValue::Flag(left), ContextValue::Flag(right)) => match operator {
            "eq" => Ok(left == *right),
            "ne" => Ok(left != *right),
            _ => Err(InteractionTreeError::at(
                "INVALID_CONDITION_COMPARISON",
                "Boolean interaction conditions support only eq and ne",
                "condition.operator",
            )),
        },
        _ => Err(InteractionTreeError::at(
            "CONDITION_TYPE_MISMATCH",
            "Interaction condition value type does not match its context input",
            "condition.value",
        )),
    }
}

pub(super) fn apply_effect(
    effect: &InteractionTreeEffect,
    scale: f64,
    actor: &mut InteractionParticipant,
    target: &mut InteractionParticipant,
    relationship: &mut DirectedRelationship,
    changes: &mut Vec<InteractionTreeChange>,
) -> Result<(), InteractionTreeError> {
    match effect {
        InteractionTreeEffect::AgentState {
            participant,
            field,
            operation,
            value,
            minimum,
            maximum,
            scale_by: _,
        } => {
            let agent = if participant == "actor" {
                actor
            } else {
                target
            };
            let before = agent.states.get(field).copied().ok_or_else(|| {
                InteractionTreeError::at(
                    "UNKNOWN_AGENT_EFFECT_STATE",
                    format!("Participant {} has no state {field}", agent.agent_id),
                    format!("effects.{participant}.{field}"),
                )
            })?;
            let after = bounded_numeric(before, operation, *value * scale, *minimum, *maximum);
            agent.states.insert(field.clone(), after);
            changes.push(InteractionTreeChange {
                recipient: participant.clone(),
                field: format!("state.{field}"),
                before: ContextValue::Number(before),
                after: ContextValue::Number(after),
            });
        }
        InteractionTreeEffect::AgentRoutine {
            participant,
            operation,
            routine_id,
        } => {
            let agent = if participant == "actor" {
                actor
            } else {
                target
            };
            let before = agent.routines.contains(routine_id);
            if operation == "add" {
                agent.routines.insert(routine_id.clone());
            } else {
                agent.routines.remove(routine_id);
            }
            let after = agent.routines.contains(routine_id);
            changes.push(InteractionTreeChange {
                recipient: participant.clone(),
                field: format!("routine.{routine_id}"),
                before: ContextValue::Flag(before),
                after: ContextValue::Flag(after),
            });
        }
        InteractionTreeEffect::RelationshipState {
            field,
            operation,
            value,
            minimum,
            maximum,
            scale_by: _,
        } => {
            let before = relationship.states.get(field).copied().ok_or_else(|| {
                InteractionTreeError::at(
                    "UNKNOWN_RELATIONSHIP_EFFECT_STATE",
                    format!("Directed relationship has no state {field}"),
                    format!("effects.relationship.{field}"),
                )
            })?;
            let after = bounded_numeric(before, operation, *value * scale, *minimum, *maximum);
            relationship.states.insert(field.clone(), after);
            changes.push(InteractionTreeChange {
                recipient: "relationship".to_owned(),
                field: format!("state.{field}"),
                before: ContextValue::Number(before),
                after: ContextValue::Number(after),
            });
        }
        InteractionTreeEffect::RelationshipKind { relationship_type } => {
            let before = relationship.relationship_type.clone();
            relationship.relationship_type.clone_from(relationship_type);
            changes.push(InteractionTreeChange {
                recipient: "relationship".to_owned(),
                field: "kind".to_owned(),
                before: ContextValue::Text(before),
                after: ContextValue::Text(relationship_type.clone()),
            });
        }
    }
    Ok(())
}

fn bounded_numeric(
    before: f64,
    operation: &str,
    value: f64,
    minimum: Option<f64>,
    maximum: Option<f64>,
) -> f64 {
    let mut after = if operation == "set" {
        value
    } else {
        before + value
    };
    if let Some(limit) = minimum {
        after = after.max(limit);
    }
    if let Some(limit) = maximum {
        after = after.min(limit);
    }
    after
}
