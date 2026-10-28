use super::aggregate_cache::{evaluate_aggregate_function, inputs_hash, interpolate_outputs};
use super::composition_cache_artifacts::{
    aggregate_function, apply_input_schedule, cache_tree, composition, finalize_parent_artifacts,
    leaf_invalidation_reason, resolve_inputs,
};
use super::composition_cache_reports::cached_reports;
use super::expression::evaluate;
use super::model::*;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone)]
pub(super) struct CachedNodeState {
    weights: BTreeMap<String, f64>,
    feedback_inputs: BTreeMap<String, f64>,
}

#[derive(Clone)]
pub(super) struct BranchActivity {
    pub(super) agent_ticks: u64,
    pub(super) invalidation_reason: Option<String>,
    pub(super) cached: bool,
    pub(super) detailed: bool,
}

#[derive(Clone)]
pub(super) struct CachedFlowPoint {
    pub(super) day: u32,
    pub(super) composition: String,
    pub(super) id: String,
    pub(super) source: String,
    pub(super) target: String,
    pub(super) effect: String,
    pub(super) count: f64,
    pub(super) rate: f64,
}

#[derive(Clone)]
struct NodeDayResult {
    outputs: BTreeMap<String, LearnedMetricSummary>,
    pub(super) flows: Vec<CachedFlowPoint>,
    pub(super) iterations: u32,
    pub(super) change_percent: f64,
}

pub(super) struct HierarchyContext<'a> {
    pub(super) program: &'a Program,
    pub(super) request: &'a CachedCompositionProtocolRequest,
    pub(super) artifacts: BTreeMap<String, LearnedAggregateArtifact>,
    pub(super) activities: BTreeMap<String, BranchActivity>,
    pub(super) states: BTreeMap<String, CachedNodeState>,
    pub(super) series: BTreeMap<String, Vec<AggregateTimePoint>>,
    pub(super) convergence: BTreeMap<String, (u32, f64)>,
    flows: Vec<CachedFlowPoint>,
    memo: BTreeMap<String, BTreeMap<String, LearnedMetricSummary>>,
    node_memo: BTreeMap<String, NodeDayResult>,
    iterations: u32,
    change_percent: f64,
}

pub fn evaluate_cached_composition(
    program: Program,
    request: CachedCompositionProtocolRequest,
) -> DslResult<CachedCompositionEvaluationResult> {
    let composition = composition(&program, &request.function_id)?;
    if composition.cached.is_none() {
        return Err(DslError::new(
            "MISSING_CACHED_COMPOSITION",
            composition.line,
            format!("Composition {} has no cached block", composition.id),
        ));
    }
    let function = aggregate_function(&program, &request.function_id)?;
    let mut root_inputs = resolve_inputs(
        function,
        &composition.parameters,
        &request.inputs,
        request.branch_inputs.get(&composition.id),
        &BTreeMap::new(),
    )?;
    let mut context = HierarchyContext {
        program: &program,
        request: &request,
        artifacts: request.artifacts.clone(),
        activities: BTreeMap::new(),
        states: BTreeMap::new(),
        series: BTreeMap::new(),
        convergence: BTreeMap::new(),
        flows: Vec::new(),
        memo: BTreeMap::new(),
        node_memo: BTreeMap::new(),
        iterations: 0,
        change_percent: 0.0,
    };
    let sync_days = minimum_sync(&program, composition);
    let mut day = sync_days;
    while day <= request.days {
        apply_input_schedule(function, &request.input_schedule, day, &mut root_inputs)?;
        let result = evaluate_node_day(&mut context, composition, day, &root_inputs, true)?;
        context.flows.extend(result.flows);
        context.iterations = context.iterations.max(result.iterations);
        context.change_percent = context.change_percent.max(result.change_percent);
        day = day.saturating_add(sync_days);
    }
    if request.days % sync_days != 0 {
        apply_input_schedule(
            function,
            &request.input_schedule,
            request.days,
            &mut root_inputs,
        )?;
        let result =
            evaluate_node_day(&mut context, composition, request.days, &root_inputs, true)?;
        context.flows.extend(result.flows);
        context.iterations = context.iterations.max(result.iterations);
        context.change_percent = context.change_percent.max(result.change_percent);
    }
    finalize_parent_artifacts(&mut context, composition, &root_inputs)?;
    let cache_tree = cache_tree(&context, composition)?;
    let artifact = context.artifacts[&composition.id].clone();
    let changed_artifacts = context
        .artifacts
        .iter()
        .filter(|(id, artifact)| {
            request
                .artifacts
                .get(*id)
                .is_none_or(|existing| existing.version != artifact.version)
        })
        .map(|(id, artifact)| (id.clone(), artifact.clone()))
        .collect();
    let time_series = context.series.remove(&composition.id).unwrap_or_default();
    let endpoint = time_series.last().ok_or_else(|| {
        DslError::new(
            "EMPTY_CACHED_COMPOSITION",
            composition.line,
            "Cached composition produced no time points",
        )
    })?;
    let reports = cached_reports(
        composition,
        endpoint,
        &context.flows,
        &cache_tree,
        request.days,
        context.iterations,
        context.change_percent,
    );
    let agent_ticks = context
        .activities
        .values()
        .filter(|activity| activity.detailed)
        .map(|activity| activity.agent_ticks)
        .sum();
    Ok(CachedCompositionEvaluationResult {
        function_id: composition.id.clone(),
        cache_hit: cache_tree.cached,
        invalidation_reason: cache_tree.invalidation_reason.clone(),
        agent_ticks,
        inputs_hash: inputs_hash(&root_inputs),
        valid_from: artifact.valid_from,
        valid_until: artifact.valid_until,
        dsl_source_hash: artifact.dsl_source_hash.clone(),
        artifact,
        artifacts: changed_artifacts,
        time_series,
        reports,
        cache_tree,
        feedback_iterations: context.iterations,
        feedback_change_percent: context.change_percent,
    })
}

fn evaluate_node_day(
    context: &mut HierarchyContext<'_>,
    composition: &CompositionDefinition,
    day: u32,
    inherited_inputs: &BTreeMap<String, f64>,
    record: bool,
) -> DslResult<NodeDayResult> {
    ensure_node_state(context, composition);
    let function = aggregate_function(context.program, &composition.id)?;
    let node_inputs = resolve_inputs(
        function,
        &composition.parameters,
        inherited_inputs,
        context.request.branch_inputs.get(&composition.id),
        &BTreeMap::new(),
    )?;
    let memo_key = format!(
        "{}:{day}:{}:{record}",
        composition.id,
        inputs_hash(&node_inputs)
    );
    if let Some(result) = context.node_memo.get(&memo_key) {
        return Ok(result.clone());
    }
    let cached = composition.cached.as_ref();
    let sync_due =
        cached.is_none_or(|value| day % value.sync_days == 0 || day == context.request.days);
    let max_iterations = if record && sync_due {
        cached.map_or(1, |value| value.max_iterations)
    } else {
        1
    };
    let tolerance = cached.map_or(0.01, |value| value.tolerance);
    let mut feedback_inputs = context.states[&composition.id].feedback_inputs.clone();
    if max_iterations == 1 {
        let result = evaluate_node_once(
            context,
            composition,
            day,
            &node_inputs,
            &feedback_inputs,
            record,
            sync_due,
        )?;
        context.node_memo.insert(memo_key, result.clone());
        return Ok(result);
    }
    let mut previous_outputs = BTreeMap::new();
    let mut iterations = 0;
    let mut change_percent = 0.0;
    for iteration in 1..=max_iterations {
        let mut preview_states = context.states.clone();
        let children = evaluate_children(
            context,
            composition,
            day,
            &node_inputs,
            &feedback_inputs,
            &mut preview_states,
            false,
        )?;
        let outputs = combine_outputs(context.program, composition, &node_inputs, &children)?;
        change_percent = output_change(&previous_outputs, &outputs);
        iterations = iteration;
        let next_feedback = feedback_values(composition, &outputs);
        if cached.is_none() || iteration > 1 && change_percent < tolerance * 100.0 {
            feedback_inputs = next_feedback;
            break;
        }
        previous_outputs = outputs;
        feedback_inputs = next_feedback;
    }
    let mut states = std::mem::take(&mut context.states);
    let children = evaluate_children(
        context,
        composition,
        day,
        &node_inputs,
        &feedback_inputs,
        &mut states,
        record,
    )?;
    context.states = states;
    let mut outputs = combine_outputs(context.program, composition, &node_inputs, &children)?;
    let flows = if sync_due {
        apply_cached_flows(
            context,
            composition,
            day,
            &node_inputs,
            &children,
            &mut outputs,
        )?
    } else {
        Vec::new()
    };
    if record {
        record_convergence(context, composition, iterations, change_percent);
        if sync_due && let Some(state) = context.states.get_mut(&composition.id) {
            state.feedback_inputs = feedback_inputs;
        }
        context
            .series
            .entry(composition.id.clone())
            .or_default()
            .push(AggregateTimePoint {
                day,
                outputs: outputs.clone(),
            });
    }
    let result = NodeDayResult {
        outputs,
        flows,
        iterations,
        change_percent,
    };
    context.node_memo.insert(memo_key, result.clone());
    Ok(result)
}

fn evaluate_node_once(
    context: &mut HierarchyContext<'_>,
    composition: &CompositionDefinition,
    day: u32,
    inputs: &BTreeMap<String, f64>,
    feedback_inputs: &BTreeMap<String, f64>,
    record: bool,
    sync_due: bool,
) -> DslResult<NodeDayResult> {
    let mut states = std::mem::take(&mut context.states);
    let children = evaluate_children(
        context,
        composition,
        day,
        inputs,
        feedback_inputs,
        &mut states,
        record,
    )?;
    context.states = states;
    let mut outputs = combine_outputs(context.program, composition, inputs, &children)?;
    let flows = if sync_due {
        apply_cached_flows(context, composition, day, inputs, &children, &mut outputs)?
    } else {
        Vec::new()
    };
    if record {
        record_convergence(context, composition, 1, 0.0);
        if sync_due && let Some(state) = context.states.get_mut(&composition.id) {
            state.feedback_inputs = feedback_values(composition, &outputs);
        }
        context
            .series
            .entry(composition.id.clone())
            .or_default()
            .push(AggregateTimePoint {
                day,
                outputs: outputs.clone(),
            });
    }
    Ok(NodeDayResult {
        outputs,
        flows,
        iterations: 1,
        change_percent: 0.0,
    })
}

fn record_convergence(
    context: &mut HierarchyContext<'_>,
    composition: &CompositionDefinition,
    iterations: u32,
    change_percent: f64,
) {
    context
        .convergence
        .entry(composition.id.clone())
        .and_modify(|current| {
            current.0 = current.0.max(iterations);
            current.1 = current.1.max(change_percent);
        })
        .or_insert((iterations, change_percent));
}

fn minimum_sync(program: &Program, composition: &CompositionDefinition) -> u32 {
    composition.entries.iter().fold(
        composition
            .cached
            .as_ref()
            .map_or(u32::MAX, |cached| cached.sync_days),
        |minimum, entry| {
            program
                .compositions
                .iter()
                .find(|child| child.id == entry.child)
                .map_or(minimum, |child| minimum.min(minimum_sync(program, child)))
        },
    )
}

fn evaluate_children(
    context: &mut HierarchyContext<'_>,
    parent: &CompositionDefinition,
    day: u32,
    inherited_inputs: &BTreeMap<String, f64>,
    feedback_inputs: &BTreeMap<String, f64>,
    states: &mut BTreeMap<String, CachedNodeState>,
    record: bool,
) -> DslResult<Vec<(String, f64, BTreeMap<String, LearnedMetricSummary>)>> {
    let original_states = std::mem::replace(&mut context.states, states.clone());
    let mut children = Vec::new();
    for entry in &parent.entries {
        let mut propagated = inherited_inputs.clone();
        propagated.extend(feedback_inputs.clone());
        if let Some(branch) = context.request.branch_inputs.get(&entry.child) {
            propagated.extend(branch.clone());
        }
        let outputs = if let Some(child) = context
            .program
            .compositions
            .iter()
            .find(|item| item.id == entry.child)
            && child.cached.is_some()
        {
            let result = evaluate_node_day(context, child, day, &propagated, record)?;
            if record {
                context.flows.extend(result.flows.clone());
            }
            result.outputs
        } else {
            evaluate_leaf(context, &entry.child, day, &propagated)?
        };
        let weight = context.states[&parent.id].weights[&entry.child];
        children.push((entry.child.clone(), weight, outputs));
    }
    *states = std::mem::replace(&mut context.states, original_states);
    Ok(children)
}

fn evaluate_leaf(
    context: &mut HierarchyContext<'_>,
    function_id: &str,
    day: u32,
    inherited_inputs: &BTreeMap<String, f64>,
) -> DslResult<BTreeMap<String, LearnedMetricSummary>> {
    let function = aggregate_function(context.program, function_id)?;
    let parameters = context
        .program
        .compositions
        .iter()
        .find(|item| item.id == function_id)
        .map(|item| &item.parameters)
        .cloned()
        .unwrap_or_default();
    let inputs = resolve_inputs(
        function,
        &parameters,
        inherited_inputs,
        context.request.branch_inputs.get(function_id),
        &BTreeMap::new(),
    )?;
    let artifact = context.artifacts.get(function_id).cloned();
    let reason = leaf_invalidation_reason(context, function, artifact.as_ref(), &inputs);
    if reason.is_some() {
        let result = evaluate_aggregate_function(
            context.program.clone(),
            AggregateEvaluationProtocolRequest {
                source: context.request.source.clone(),
                dsl_source_hash: context.request.dsl_source_hash.clone(),
                function_id: function_id.to_owned(),
                seed: context.request.seed,
                days: function.time_days,
                evaluated_at_day: context.request.evaluated_at_day,
                inputs: inputs.clone(),
                events: context.request.events.clone(),
                artifact,
                force_relearn: context.request.force_relearn,
            },
        )?;
        context
            .artifacts
            .insert(function_id.to_owned(), result.artifact.clone());
        let activity = context
            .activities
            .entry(function_id.to_owned())
            .or_insert(BranchActivity {
                agent_ticks: 0,
                invalidation_reason: None,
                cached: true,
                detailed: false,
            });
        activity.agent_ticks += result.agent_ticks;
        activity.invalidation_reason = result.invalidation_reason;
        activity.cached = false;
        activity.detailed |= result.agent_ticks > 0;
    } else {
        context
            .activities
            .entry(function_id.to_owned())
            .or_insert(BranchActivity {
                agent_ticks: 0,
                invalidation_reason: None,
                cached: true,
                detailed: false,
            });
    }
    let artifact = &context.artifacts[function_id];
    let learned_day = (day.saturating_sub(1) % function.time_days) + 1;
    let memo_key = format!(
        "{}:{}:{}:{}",
        function_id,
        artifact.version,
        learned_day,
        inputs_hash(&inputs)
    );
    if let Some(outputs) = context.memo.get(&memo_key) {
        return Ok(outputs.clone());
    }
    let outputs = interpolate_outputs(function, artifact, &inputs, learned_day)?;
    context.memo.insert(memo_key, outputs.clone());
    Ok(outputs)
}

fn combine_outputs(
    program: &Program,
    composition: &CompositionDefinition,
    inputs: &BTreeMap<String, f64>,
    children: &[(String, f64, BTreeMap<String, LearnedMetricSummary>)],
) -> DslResult<BTreeMap<String, LearnedMetricSummary>> {
    let total_weight = children.iter().map(|(_, weight, _)| *weight).sum::<f64>();
    let mut outputs = BTreeMap::new();
    for output in &composition.outputs {
        if matches!(
            output.metric,
            ReportMetric::FlowCount { .. } | ReportMetric::FlowRate { .. }
        ) {
            continue;
        }
        if matches!(output.metric, ReportMetric::RepresentedCount) {
            outputs.insert(
                output.id.clone(),
                LearnedMetricSummary {
                    mean: composition.represented_population.unwrap_or(0) as f64,
                    standard_deviation: 0.0,
                },
            );
            continue;
        }
        if matches!(output.metric, ReportMetric::Count) {
            outputs.insert(
                output.id.clone(),
                LearnedMetricSummary {
                    mean: composition_sample_population(program, composition) as f64,
                    standard_deviation: 0.0,
                },
            );
            continue;
        }
        let values = children
            .iter()
            .filter_map(|(_, weight, outputs)| {
                outputs.get(&output.id).map(|summary| (*weight, summary))
            })
            .collect::<Vec<_>>();
        if values.is_empty()
            && let ReportMetric::Sum { field } = &output.metric
        {
            let mut weighted_sum = 0.0;
            let mut matched_weight = 0.0;
            for (child_id, weight, child_outputs) in children {
                if let Some(id) = mean_output_for_field(program, child_id, field)
                    && let Some(summary) = child_outputs.get(id)
                {
                    weighted_sum += weight * summary.mean;
                    matched_weight += weight;
                }
            }
            if matched_weight > 0.0 {
                outputs.insert(
                    output.id.clone(),
                    LearnedMetricSummary {
                        mean: stable_number(
                            weighted_sum / matched_weight
                                * composition_sample_population(program, composition) as f64,
                        ),
                        standard_deviation: 0.0,
                    },
                );
            }
            continue;
        }
        if values.is_empty() {
            continue;
        }
        if matches!(
            output.metric,
            ReportMetric::Sum { .. } | ReportMetric::ActionCount { .. }
        ) {
            let parent_population = composition_sample_population(program, composition) as f64;
            let scaled = children
                .iter()
                .filter_map(|(child_id, weight, child_outputs)| {
                    let summary = child_outputs.get(&output.id)?;
                    let child_population = child_sample_population(program, child_id) as f64;
                    (child_population > 0.0).then_some((
                        parent_population * weight / total_weight / child_population,
                        summary,
                    ))
                })
                .collect::<Vec<_>>();
            let mean = scaled
                .iter()
                .map(|(scale, summary)| scale * summary.mean)
                .sum::<f64>();
            let variance = scaled
                .iter()
                .map(|(scale, summary)| scale.powi(2) * summary.standard_deviation.powi(2))
                .sum::<f64>();
            outputs.insert(
                output.id.clone(),
                LearnedMetricSummary {
                    mean: stable_number(mean),
                    standard_deviation: stable_number(variance.sqrt()),
                },
            );
            continue;
        }
        let mean = values
            .iter()
            .map(|(weight, summary)| weight * summary.mean)
            .sum::<f64>()
            / total_weight;
        let variance = values
            .iter()
            .map(|(weight, summary)| {
                weight * (summary.standard_deviation.powi(2) + (summary.mean - mean).powi(2))
            })
            .sum::<f64>()
            / total_weight;
        outputs.insert(
            output.id.clone(),
            LearnedMetricSummary {
                mean: stable_number(mean),
                standard_deviation: stable_number(variance.max(0.0).sqrt()),
            },
        );
    }
    apply_parent_effects(program, composition, inputs, &mut outputs)?;
    Ok(outputs)
}

fn mean_output_for_field<'a>(program: &'a Program, child_id: &str, field: &str) -> Option<&'a str> {
    if let Some(composition) = program.compositions.iter().find(|item| item.id == child_id) {
        return composition.outputs.iter().find_map(|output| {
            matches!(&output.metric, ReportMetric::Mean { field: value } if value == field)
                .then_some(output.id.as_str())
        });
    }
    program
        .archetypes
        .iter()
        .find(|item| item.id == child_id)
        .and_then(|archetype| {
            archetype.outputs.iter().find_map(|output| {
                matches!(&output.metric, ReportMetric::Mean { field: value } if value == field)
                    .then_some(output.id.as_str())
            })
        })
}

fn composition_sample_population(program: &Program, composition: &CompositionDefinition) -> usize {
    let compositions = program
        .compositions
        .iter()
        .map(|item| (item.id.as_str(), item))
        .collect::<BTreeMap<_, _>>();
    let archetypes = program
        .archetypes
        .iter()
        .map(|item| (item.id.as_str(), item))
        .collect::<BTreeMap<_, _>>();
    let mut ids = BTreeSet::new();
    collect_archetypes(composition, &compositions, &archetypes, &mut ids);
    ids.into_iter()
        .map(|id| {
            let archetype = archetypes[id];
            archetype.sample_households
                * archetype
                    .composition
                    .iter()
                    .map(|group| group.count)
                    .sum::<usize>()
        })
        .sum()
}

fn child_sample_population(program: &Program, child_id: &str) -> usize {
    if let Some(composition) = program.compositions.iter().find(|item| item.id == child_id) {
        return composition_sample_population(program, composition);
    }
    program
        .archetypes
        .iter()
        .find(|item| item.id == child_id)
        .map_or(0, |archetype| {
            archetype.sample_households
                * archetype
                    .composition
                    .iter()
                    .map(|group| group.count)
                    .sum::<usize>()
        })
}

fn collect_archetypes<'a>(
    composition: &'a CompositionDefinition,
    compositions: &BTreeMap<&'a str, &'a CompositionDefinition>,
    archetypes: &BTreeMap<&'a str, &'a ArchetypeDefinition>,
    ids: &mut BTreeSet<&'a str>,
) {
    for entry in &composition.entries {
        if archetypes.contains_key(entry.child.as_str()) {
            ids.insert(entry.child.as_str());
        } else if let Some(child) = compositions.get(entry.child.as_str()) {
            collect_archetypes(child, compositions, archetypes, ids);
        }
    }
}

fn apply_parent_effects(
    program: &Program,
    composition: &CompositionDefinition,
    inputs: &BTreeMap<String, f64>,
    outputs: &mut BTreeMap<String, LearnedMetricSummary>,
) -> DslResult<()> {
    let function = aggregate_function(program, &composition.id)?;
    let values = inputs
        .iter()
        .map(|(id, value)| (id.clone(), DslValue::Number(*value)))
        .collect::<BTreeMap<_, _>>();
    for effect in &function.effects {
        let AggregateEffectTarget::Field(field) = &effect.target else {
            continue;
        };
        let value = evaluate(&effect.value, &values)?.as_f64().ok_or_else(|| {
            DslError::new(
                "INVALID_AGGREGATE_EFFECT",
                effect.line,
                "Cached aggregate effect must resolve to a number",
            )
        })?;
        for output in &composition.outputs {
            if !matches!(&output.metric, ReportMetric::Mean { field: output_field } | ReportMetric::Sum { field: output_field } if output_field.as_str() == field.as_str())
            {
                continue;
            }
            if let Some(summary) = outputs.get_mut(&output.id) {
                summary.mean = apply_number(summary.mean, &effect.operation, value)?;
                if effect.operation == "*=" {
                    summary.standard_deviation *= value.abs();
                }
            }
        }
    }
    Ok(())
}

fn apply_cached_flows(
    context: &mut HierarchyContext<'_>,
    composition: &CompositionDefinition,
    day: u32,
    inputs: &BTreeMap<String, f64>,
    children: &[(String, f64, BTreeMap<String, LearnedMetricSummary>)],
    outputs: &mut BTreeMap<String, LearnedMetricSummary>,
) -> DslResult<Vec<CachedFlowPoint>> {
    let mut values = composition
        .parameters
        .iter()
        .map(|(id, value)| (id.clone(), DslValue::Number(*value)))
        .chain(
            inputs
                .iter()
                .map(|(id, value)| (id.clone(), DslValue::Number(*value))),
        )
        .chain(
            outputs
                .iter()
                .map(|(id, value)| (id.clone(), DslValue::Number(value.mean))),
        )
        .collect::<BTreeMap<_, _>>();
    for (child, _, child_outputs) in children {
        if let Some(definition) = context
            .program
            .compositions
            .iter()
            .find(|definition| definition.id == *child)
        {
            for (parameter, value) in &definition.parameters {
                values.insert(format!("{child}_{parameter}"), DslValue::Number(*value));
                values.insert(format!("{child}.{parameter}"), DslValue::Number(*value));
            }
        }
        for (output, summary) in child_outputs {
            values.insert(format!("{child}_{output}"), DslValue::Number(summary.mean));
            values.insert(format!("{child}.{output}"), DslValue::Number(summary.mean));
        }
    }
    let state = context.states.get_mut(&composition.id).unwrap();
    let mut points = Vec::new();
    for flow in &composition.flows {
        let distance = composition
            .adjacency
            .iter()
            .find(|edge| {
                edge.source == flow.source && edge.target == flow.target
                    || edge.source == flow.target && edge.target == flow.source
            })
            .map_or(1.0, |edge| edge.distance)
            .max(1.0);
        values.insert(
            format!("distance_{}_{}", flow.source, flow.target),
            DslValue::Number(distance),
        );
        let rate = evaluate(&flow.rate, &values)?
            .as_f64()
            .ok_or_else(|| {
                DslError::new(
                    "INVALID_COMPOSITION_FLOW_RATE",
                    flow.line,
                    "Cached flow rate must resolve to a number",
                )
            })?
            .clamp(0.0, 1.0)
            / distance;
        let source_weight = state.weights.get(&flow.source).copied().unwrap_or(0.0);
        let count = source_weight * rate;
        if flow.effect == "transfer" {
            if let Some(source) = state.weights.get_mut(&flow.source) {
                *source = (*source - count).max(0.0);
            }
            *state.weights.entry(flow.target.clone()).or_default() += count;
        }
        for output in &composition.outputs {
            match &output.metric {
                ReportMetric::FlowRate { flow: id } if id == &flow.id => {
                    outputs.insert(
                        output.id.clone(),
                        LearnedMetricSummary {
                            mean: stable_number(rate),
                            standard_deviation: 0.0,
                        },
                    );
                }
                ReportMetric::FlowCount { flow: id } if id == &flow.id => {
                    outputs.insert(
                        output.id.clone(),
                        LearnedMetricSummary {
                            mean: stable_number(count),
                            standard_deviation: 0.0,
                        },
                    );
                }
                _ => {}
            }
        }
        points.push(CachedFlowPoint {
            day,
            composition: composition.id.clone(),
            id: flow.id.clone(),
            source: flow.source.clone(),
            target: flow.target.clone(),
            effect: flow.effect.clone(),
            count: stable_number(count),
            rate: stable_number(rate),
        });
        values.insert(flow.id.clone(), DslValue::Number(rate));
    }
    Ok(points)
}

fn feedback_values(
    composition: &CompositionDefinition,
    outputs: &BTreeMap<String, LearnedMetricSummary>,
) -> BTreeMap<String, f64> {
    composition
        .cached
        .iter()
        .flat_map(|cached| &cached.feedback)
        .filter_map(|feedback| {
            outputs
                .get(&feedback.output)
                .map(|output| (feedback.input.clone(), output.mean * feedback.scale))
        })
        .collect()
}

fn output_change(
    previous: &BTreeMap<String, LearnedMetricSummary>,
    current: &BTreeMap<String, LearnedMetricSummary>,
) -> f64 {
    if previous.is_empty() {
        return 100.0;
    }
    current
        .iter()
        .filter_map(|(id, value)| {
            previous
                .get(id)
                .map(|old| (value.mean - old.mean).abs() / old.mean.abs().max(1e-9) * 100.0)
        })
        .fold(0.0, f64::max)
}

fn ensure_node_state(context: &mut HierarchyContext<'_>, composition: &CompositionDefinition) {
    context
        .states
        .entry(composition.id.clone())
        .or_insert_with(|| CachedNodeState {
            weights: composition
                .entries
                .iter()
                .map(|entry| (entry.child.clone(), entry.weight as f64))
                .collect(),
            feedback_inputs: BTreeMap::new(),
        });
}

fn apply_number(current: f64, operation: &str, value: f64) -> DslResult<f64> {
    match operation {
        "+=" => Ok(current + value),
        "-=" => Ok(current - value),
        "*=" => Ok(current * value),
        "=" => Ok(value),
        _ => Err(DslError::new(
            "INVALID_AGGREGATE_EFFECT",
            1,
            format!("Unknown aggregate effect operation {operation}"),
        )),
    }
}

fn stable_number(value: f64) -> f64 {
    (value * 1_000_000_000_000.0).round() / 1_000_000_000_000.0
}
