use super::aggregate_cache::inputs_hash;
use super::composition_cache::{BranchActivity, HierarchyContext};
use super::model::*;
use std::collections::BTreeMap;

pub(super) fn finalize_parent_artifacts(
    context: &mut HierarchyContext<'_>,
    composition: &CompositionDefinition,
    inherited_inputs: &BTreeMap<String, f64>,
) -> DslResult<()> {
    for entry in &composition.entries {
        if let Some(child) = context
            .program
            .compositions
            .iter()
            .find(|item| item.id == entry.child)
            && child.cached.is_some()
        {
            finalize_parent_artifacts(context, child, inherited_inputs)?;
        }
    }
    let function = aggregate_function(context.program, &composition.id)?;
    let inputs = resolve_inputs(
        function,
        &composition.parameters,
        inherited_inputs,
        context.request.branch_inputs.get(&composition.id),
        &BTreeMap::new(),
    )?;
    let dependencies = composition
        .entries
        .iter()
        .filter_map(|entry| {
            context
                .artifacts
                .get(&entry.child)
                .map(|artifact| (entry.child.clone(), artifact.version))
        })
        .collect::<BTreeMap<_, _>>();
    let existing = context.artifacts.get(&composition.id).cloned();
    let own_reason =
        parent_invalidation_reason(context, function, existing.as_ref(), &inputs, &dependencies);
    let child_ticks = composition
        .entries
        .iter()
        .filter_map(|entry| context.activities.get(&entry.child))
        .map(|activity| activity.agent_ticks)
        .sum::<u64>();
    let version = existing.as_ref().map_or(1, |artifact| {
        artifact.version + u32::from(own_reason.is_some())
    });
    let points = context
        .series
        .get(&composition.id)
        .into_iter()
        .flatten()
        .map(|point| LearnedAggregatePoint {
            inputs: inputs.clone(),
            day: point.day,
            outputs: point.outputs.clone(),
            reports: Vec::new(),
        })
        .collect();
    let artifact = if own_reason.is_none() {
        existing.unwrap()
    } else {
        LearnedAggregateArtifact {
            function_id: composition.id.clone(),
            version,
            dsl_source_hash: context.request.dsl_source_hash.clone(),
            seed: context.request.seed,
            anchor_inputs: inputs.clone(),
            valid_from: context.request.evaluated_at_day,
            valid_until: context.request.evaluated_at_day + function.cache.valid_for_days,
            inputs_hash: inputs_hash(&inputs),
            learning_agent_ticks: child_ticks,
            dependencies,
            points,
        }
    };
    context.artifacts.insert(composition.id.clone(), artifact);
    context.activities.insert(
        composition.id.clone(),
        BranchActivity {
            agent_ticks: child_ticks,
            invalidation_reason: own_reason.clone(),
            cached: own_reason.is_none() && child_ticks == 0,
            detailed: false,
        },
    );
    Ok(())
}

fn parent_invalidation_reason(
    context: &HierarchyContext<'_>,
    function: &AggregateFunctionDefinition,
    artifact: Option<&LearnedAggregateArtifact>,
    inputs: &BTreeMap<String, f64>,
    dependencies: &BTreeMap<String, u32>,
) -> Option<String> {
    if context.request.force_relearn {
        return Some("forced_relearn".to_owned());
    }
    let Some(artifact) = artifact else {
        return Some("cache_miss".to_owned());
    };
    if artifact.dsl_source_hash != context.request.dsl_source_hash {
        return Some("dsl_source_hash_changed".to_owned());
    }
    if context.request.evaluated_at_day > artifact.valid_until {
        return Some("valid_for_expired".to_owned());
    }
    if dependencies.keys().any(|id| {
        context
            .activities
            .get(id)
            .is_some_and(|activity| !activity.cached)
    }) {
        return Some("child_cache_updated".to_owned());
    }
    if artifact.dependencies != *dependencies {
        return Some("child_cache_changed".to_owned());
    }
    if let Some(event) = context
        .request
        .events
        .intersection(&function.cache.invalidate_events)
        .next()
    {
        return Some(format!("event:{event}"));
    }
    for input in &function.inputs {
        let previous = artifact.anchor_inputs.get(&input.id)?;
        if (inputs[&input.id] - previous).abs() > input.invalidate_threshold {
            return Some(format!("input:{}", input.id));
        }
    }
    None
}

pub(super) fn leaf_invalidation_reason(
    context: &HierarchyContext<'_>,
    function: &AggregateFunctionDefinition,
    artifact: Option<&LearnedAggregateArtifact>,
    inputs: &BTreeMap<String, f64>,
) -> Option<String> {
    if context.request.force_relearn {
        return Some("forced_relearn".to_owned());
    }
    let Some(artifact) = artifact else {
        return Some("cache_miss".to_owned());
    };
    if artifact.function_id != function.id {
        return Some("function_changed".to_owned());
    }
    if artifact.dsl_source_hash != context.request.dsl_source_hash {
        return Some("dsl_source_hash_changed".to_owned());
    }
    if context.request.evaluated_at_day > artifact.valid_until {
        return Some("valid_for_expired".to_owned());
    }
    if let Some(event) = context
        .request
        .events
        .intersection(&function.cache.invalidate_events)
        .next()
    {
        return Some(format!("event:{event}"));
    }
    for input in &function.inputs {
        let previous = artifact.anchor_inputs.get(&input.id)?;
        if (inputs[&input.id] - previous).abs() > input.invalidate_threshold {
            return Some(format!("input:{}", input.id));
        }
    }
    None
}

pub(super) fn cache_tree(
    context: &HierarchyContext<'_>,
    composition: &CompositionDefinition,
) -> DslResult<CompositionCacheMetadata> {
    let artifact = context.artifacts.get(&composition.id).ok_or_else(|| {
        DslError::new(
            "MISSING_COMPOSITION_ARTIFACT",
            composition.line,
            format!("Missing cache artifact for {}", composition.id),
        )
    })?;
    let activity = context.activities.get(&composition.id).unwrap();
    let mut children = Vec::new();
    for entry in &composition.entries {
        if let Some(child) = context
            .program
            .compositions
            .iter()
            .find(|item| item.id == entry.child)
            && child.cached.is_some()
        {
            children.push(cache_tree(context, child)?);
        } else if let Some(artifact) = context.artifacts.get(&entry.child) {
            let activity = context.activities.get(&entry.child).unwrap();
            children.push(metadata(artifact, activity, Vec::new()));
        }
    }
    Ok(metadata(artifact, activity, children))
}

fn metadata(
    artifact: &LearnedAggregateArtifact,
    activity: &BranchActivity,
    children: Vec<CompositionCacheMetadata>,
) -> CompositionCacheMetadata {
    CompositionCacheMetadata {
        function_id: artifact.function_id.clone(),
        version: artifact.version,
        dsl_source_hash: artifact.dsl_source_hash.clone(),
        inputs_hash: artifact.inputs_hash.clone(),
        valid_from: artifact.valid_from,
        valid_until: artifact.valid_until,
        seed: artifact.seed,
        original_learning_ticks: artifact.learning_agent_ticks,
        evaluation_agent_ticks: activity.agent_ticks,
        cached: activity.cached,
        detailed: activity.detailed,
        invalidation_reason: activity.invalidation_reason.clone(),
        children,
    }
}

pub(super) fn resolve_inputs(
    function: &AggregateFunctionDefinition,
    parameters: &BTreeMap<String, f64>,
    inherited: &BTreeMap<String, f64>,
    branch: Option<&BTreeMap<String, f64>>,
    feedback: &BTreeMap<String, f64>,
) -> DslResult<BTreeMap<String, f64>> {
    function
        .inputs
        .iter()
        .map(|input| {
            let value = branch
                .and_then(|values| values.get(&input.id))
                .or_else(|| feedback.get(&input.id))
                .or_else(|| inherited.get(&input.id))
                .or_else(|| parameters.get(&input.id))
                .copied()
                .unwrap_or(input.default);
            if !(input.minimum..=input.maximum).contains(&value) {
                return Err(DslError::new(
                    "AGGREGATE_INPUT_OUT_OF_RANGE",
                    input.line,
                    format!(
                        "Input {} must be between {} and {}",
                        input.id, input.minimum, input.maximum
                    ),
                ));
            }
            Ok((input.id.clone(), value))
        })
        .collect()
}

pub(super) fn apply_input_schedule(
    function: &AggregateFunctionDefinition,
    schedule: &[ScheduledAggregateInputs],
    day: u32,
    inputs: &mut BTreeMap<String, f64>,
) -> DslResult<()> {
    for entry in schedule.iter().filter(|entry| entry.day <= day) {
        for (id, value) in &entry.values {
            let definition = function
                .inputs
                .iter()
                .find(|input| input.id == *id)
                .ok_or_else(|| {
                    DslError::new(
                        "UNKNOWN_AGGREGATE_INPUT",
                        function.line,
                        format!("Unknown scheduled input {id}"),
                    )
                })?;
            if !(definition.minimum..=definition.maximum).contains(value) {
                return Err(DslError::new(
                    "AGGREGATE_INPUT_OUT_OF_RANGE",
                    definition.line,
                    format!("Scheduled input {id} is outside its range"),
                ));
            }
            inputs.insert(id.clone(), *value);
        }
    }
    Ok(())
}

pub(super) fn composition<'a>(
    program: &'a Program,
    id: &str,
) -> DslResult<&'a CompositionDefinition> {
    program
        .compositions
        .iter()
        .find(|item| item.id == id)
        .ok_or_else(|| {
            DslError::new(
                "UNKNOWN_COMPOSITION",
                1,
                format!("Unknown cached composition {id}"),
            )
        })
}

pub(super) fn aggregate_function<'a>(
    program: &'a Program,
    id: &str,
) -> DslResult<&'a AggregateFunctionDefinition> {
    program
        .aggregate_functions
        .iter()
        .find(|item| item.id == id)
        .ok_or_else(|| {
            DslError::new(
                "UNKNOWN_AGGREGATE_FUNCTION",
                1,
                format!("Unknown aggregate function {id}"),
            )
        })
}
