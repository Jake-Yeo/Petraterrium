use super::archetypes::{
    MetricSummary, build_archetype_state, calculate_aggregate_metric, calculate_output_definitions,
    calculate_outputs,
};
use super::expression::evaluate;
use super::model::*;
use super::neighbourhoods::{build_neighbourhood_state, decorate_neighbourhood_result};
use super::runtime::run_program;
use std::collections::{BTreeMap, BTreeSet};

pub fn evaluate_aggregate_function(
    program: Program,
    request: AggregateEvaluationProtocolRequest,
) -> DslResult<AggregateEvaluationResult> {
    let function = program
        .aggregate_functions
        .iter()
        .find(|item| item.id == request.function_id)
        .cloned()
        .ok_or_else(|| {
            DslError::new(
                "UNKNOWN_AGGREGATE_FUNCTION",
                1,
                format!("Unknown aggregate function {}", request.function_id),
            )
        })?;
    let inputs = resolved_inputs(&function, &request.inputs)?;
    let reason = invalidation_reason(&function, &request, &inputs);
    let (artifact, cache_hit, agent_ticks) = if reason.is_none() {
        (request.artifact.clone().unwrap(), true, 0)
    } else {
        let version = request
            .artifact
            .as_ref()
            .map_or(1, |artifact| artifact.version + 1);
        let artifact = learn_aggregate_function(
            &program,
            &function,
            &request.dsl_source_hash,
            request.seed,
            request.evaluated_at_day,
            version,
            &inputs,
        )?;
        let agent_ticks = artifact.learning_agent_ticks;
        (artifact, false, agent_ticks)
    };
    let time_series = evaluation_time_points(&function, &artifact, &inputs, request.days)?;
    let endpoint = time_series.last().cloned().ok_or_else(|| {
        DslError::new(
            "EMPTY_AGGREGATE_EVALUATION",
            function.line,
            "Aggregate evaluation produced no time points",
        )
    })?;
    let mut reports = interpolate_reports(
        &function,
        &artifact,
        &inputs,
        request.days,
        program.tick_hours,
    )?;
    reports.insert(
        0,
        aggregate_output_report(&function, &endpoint, request.days),
    );
    reports.push(cache_metadata_report(
        &artifact,
        &inputs_hash(&inputs),
        cache_hit,
        reason.as_deref(),
        agent_ticks,
        request.days,
    ));
    Ok(AggregateEvaluationResult {
        function_id: function.id,
        cache_hit,
        invalidation_reason: reason,
        agent_ticks,
        inputs_hash: inputs_hash(&inputs),
        valid_from: artifact.valid_from,
        valid_until: artifact.valid_until,
        dsl_source_hash: artifact.dsl_source_hash.clone(),
        artifact,
        time_series,
        reports,
    })
}

fn learn_aggregate_function(
    program: &Program,
    function: &AggregateFunctionDefinition,
    dsl_source_hash: &str,
    seed: u64,
    evaluated_at_day: u32,
    version: u32,
    anchor_inputs: &BTreeMap<String, f64>,
) -> DslResult<LearnedAggregateArtifact> {
    let archetype = program
        .archetypes
        .iter()
        .find(|item| item.id == function.id);
    let neighbourhood = program
        .neighbourhoods
        .iter()
        .find(|item| item.id == function.id);
    let mut points = Vec::new();
    let mut learning_agent_ticks = 0_u64;
    for inputs in input_grid(&function.inputs) {
        let (mut prepared, mut state, output_definitions, agent_archetypes) =
            if let Some(archetype) = archetype {
                let (prepared, state, _) = build_archetype_state(program, archetype, seed)?;
                (prepared, state, &archetype.outputs, None)
            } else if let Some(neighbourhood) = neighbourhood {
                let build = build_neighbourhood_state(program, neighbourhood, seed)?;
                (
                    build.program,
                    build.state,
                    &neighbourhood.outputs,
                    Some(build.agent_archetypes),
                )
            } else {
                return Err(DslError::new(
                    "UNKNOWN_AGGREGATE_BRANCH",
                    function.line,
                    format!(
                        "Aggregate function {} has no simulation branch",
                        function.id
                    ),
                ));
            };
        let action_aggregates = prepared
            .actions
            .iter()
            .map(|action| (action.id.clone(), action.aggregate.clone()))
            .collect::<BTreeMap<_, _>>();
        apply_effects(&mut prepared, &mut state, function, &inputs)?;
        let mut completed_ticks = 0_u64;
        for day in &function.time_points {
            let target_ticks = u64::from(*day) * ticks_per_day(program.tick_hours);
            let delta_ticks = target_ticks - completed_ticks;
            learning_agent_ticks += state.agents.len() as u64 * delta_ticks;
            let mut result = run_program(DslRunRequest::resume(
                prepared.clone(),
                grid_seed(seed, &inputs),
                delta_ticks,
                state,
            ))?;
            if let (Some(neighbourhood), Some(agent_archetypes)) =
                (neighbourhood, agent_archetypes.as_ref())
            {
                decorate_neighbourhood_result(
                    neighbourhood,
                    &mut result,
                    agent_archetypes,
                    &action_aggregates,
                    target_ticks,
                    true,
                )?;
            }
            let mut detailed_outputs = if let Some(archetype) = archetype {
                calculate_outputs(archetype, &result)?
            } else {
                calculate_output_definitions(output_definitions, &result)?
            };
            let outputs = function
                .outputs
                .iter()
                .map(|output| {
                    let summary = if let Some(metric) = &output.metric {
                        calculate_aggregate_metric(&result, metric, output.line)?
                    } else {
                        detailed_outputs.remove(&output.id).ok_or_else(|| {
                            DslError::new(
                                "UNKNOWN_AGGREGATE_OUTPUT",
                                output.line,
                                format!("Missing learned output {}", output.id),
                            )
                        })?
                    };
                    Ok((output.id.clone(), learned_summary(summary)))
                })
                .collect::<DslResult<_>>()?;
            points.push(LearnedAggregatePoint {
                inputs: inputs.clone(),
                day: *day,
                outputs,
                reports: final_reports(&result.reports),
            });
            completed_ticks = target_ticks;
            state = result.state;
        }
    }
    Ok(LearnedAggregateArtifact {
        function_id: function.id.clone(),
        version,
        dsl_source_hash: dsl_source_hash.to_owned(),
        seed,
        anchor_inputs: anchor_inputs.clone(),
        valid_from: evaluated_at_day,
        valid_until: evaluated_at_day + function.cache.valid_for_days,
        inputs_hash: inputs_hash(anchor_inputs),
        learning_agent_ticks,
        points,
    })
}

fn apply_effects(
    program: &mut Program,
    state: &mut DslRunState,
    function: &AggregateFunctionDefinition,
    inputs: &BTreeMap<String, f64>,
) -> DslResult<()> {
    let values = inputs
        .iter()
        .map(|(id, value)| (id.clone(), DslValue::Number(*value)))
        .collect::<BTreeMap<_, _>>();
    for effect in &function.effects {
        let value = evaluate(&effect.value, &values)?.as_f64().ok_or_else(|| {
            DslError::new(
                "INVALID_AGGREGATE_EFFECT",
                effect.line,
                "Aggregate effect must resolve to a number",
            )
        })?;
        match &effect.target {
            AggregateEffectTarget::Field(field) => {
                for agent in &mut state.agents {
                    let current = agent
                        .traits
                        .get_mut(field)
                        .or_else(|| agent.states.get_mut(field));
                    if let Some(current) = current {
                        let next = apply_number(
                            current.as_f64().unwrap_or(0.0),
                            &effect.operation,
                            value,
                        )?;
                        *current = DslValue::Number(next);
                    }
                }
            }
            AggregateEffectTarget::Decision(action) => {
                for branch in program
                    .decisions
                    .iter_mut()
                    .flat_map(|decision| &mut decision.branches)
                    .filter(|branch| {
                        branch.action == *action
                            || branch
                                .action
                                .rsplit_once("__")
                                .is_some_and(|(_, id)| id == action)
                    })
                {
                    branch.probability = match effect.operation.as_str() {
                        "=" => Expr::Value(DslValue::Number(value)),
                        operation => Expr::Binary {
                            operation: operation.trim_end_matches('=').to_owned(),
                            left: Box::new(branch.probability.clone()),
                            right: Box::new(Expr::Value(DslValue::Number(value))),
                        },
                    };
                }
            }
        }
    }
    Ok(())
}

fn invalidation_reason(
    function: &AggregateFunctionDefinition,
    request: &AggregateEvaluationProtocolRequest,
    inputs: &BTreeMap<String, f64>,
) -> Option<String> {
    if request.force_relearn {
        return Some("forced_relearn".to_owned());
    }
    let Some(artifact) = request.artifact.as_ref() else {
        return Some("cache_miss".to_owned());
    };
    if artifact.function_id != function.id {
        return Some("function_changed".to_owned());
    }
    if artifact.dsl_source_hash != request.dsl_source_hash {
        return Some("dsl_source_hash_changed".to_owned());
    }
    if request.evaluated_at_day > artifact.valid_until {
        return Some("valid_for_expired".to_owned());
    }
    if let Some(event) = request
        .events
        .intersection(&function.cache.invalidate_events)
        .next()
    {
        return Some(format!("event:{event}"));
    }
    for input in &function.inputs {
        let previous = artifact.anchor_inputs.get(&input.id)?;
        let current = inputs[&input.id];
        if (current - previous).abs() > input.invalidate_threshold {
            return Some(format!("input:{}", input.id));
        }
    }
    None
}

fn resolved_inputs(
    function: &AggregateFunctionDefinition,
    requested: &BTreeMap<String, f64>,
) -> DslResult<BTreeMap<String, f64>> {
    let known = function
        .inputs
        .iter()
        .map(|input| input.id.as_str())
        .collect::<BTreeSet<_>>();
    if let Some(unknown) = requested
        .keys()
        .find(|input| !known.contains(input.as_str()))
    {
        return Err(DslError::new(
            "UNKNOWN_AGGREGATE_INPUT",
            function.line,
            format!("Unknown aggregate input {unknown}"),
        ));
    }
    function
        .inputs
        .iter()
        .map(|input| {
            let value = requested.get(&input.id).copied().unwrap_or(input.default);
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

fn input_grid(inputs: &[AggregateInputDefinition]) -> Vec<BTreeMap<String, f64>> {
    let combinations = 1_usize << inputs.len();
    (0..combinations)
        .map(|combination| {
            inputs
                .iter()
                .enumerate()
                .map(|(index, input)| {
                    let value = if combination & (1 << index) == 0 {
                        input.minimum
                    } else {
                        input.maximum
                    };
                    (input.id.clone(), value)
                })
                .collect()
        })
        .collect()
}

fn evaluation_time_points(
    function: &AggregateFunctionDefinition,
    artifact: &LearnedAggregateArtifact,
    inputs: &BTreeMap<String, f64>,
    days: u32,
) -> DslResult<Vec<AggregateTimePoint>> {
    let mut requested_days = function
        .time_points
        .iter()
        .copied()
        .filter(|day| *day <= days)
        .collect::<BTreeSet<_>>();
    let mut day = function.time_days;
    while day <= days {
        requested_days.insert(day);
        day += function.time_days;
    }
    requested_days.insert(days);
    requested_days
        .into_iter()
        .map(|day| {
            let learned_day = day.min(function.time_days);
            Ok(AggregateTimePoint {
                day,
                outputs: interpolate_outputs(function, artifact, inputs, learned_day)?,
            })
        })
        .collect()
}

fn interpolate_outputs(
    function: &AggregateFunctionDefinition,
    artifact: &LearnedAggregateArtifact,
    inputs: &BTreeMap<String, f64>,
    day: u32,
) -> DslResult<BTreeMap<String, LearnedMetricSummary>> {
    function
        .outputs
        .iter()
        .map(|output| {
            let mean = interpolate_number(function, artifact, inputs, day, |point| {
                point.outputs.get(&output.id).map(|summary| summary.mean)
            })?;
            let second_moment = interpolate_number(function, artifact, inputs, day, |point| {
                point
                    .outputs
                    .get(&output.id)
                    .map(|summary| summary.standard_deviation.powi(2) + summary.mean.powi(2))
            })?;
            Ok((
                output.id.clone(),
                LearnedMetricSummary {
                    mean,
                    standard_deviation: stable_number(
                        (second_moment - mean.powi(2)).max(0.0).sqrt(),
                    ),
                },
            ))
        })
        .collect()
}

fn interpolate_number(
    function: &AggregateFunctionDefinition,
    artifact: &LearnedAggregateArtifact,
    inputs: &BTreeMap<String, f64>,
    day: u32,
    value: impl Fn(&LearnedAggregatePoint) -> Option<f64>,
) -> DslResult<f64> {
    let mut numerator = 0.0;
    let mut denominator = 0.0;
    for point in artifact.points.iter().filter(|point| point.day == day) {
        let weight = interpolation_weight(&function.inputs, inputs, &point.inputs);
        if let Some(value) = value(point) {
            numerator += value * weight;
            denominator += weight;
        }
    }
    if denominator <= 0.0 {
        Err(DslError::new(
            "MISSING_LEARNED_POINT",
            function.line,
            format!("Learned aggregate has no data for day {day}"),
        ))
    } else {
        Ok(stable_number(numerator / denominator))
    }
}

fn interpolation_weight(
    definitions: &[AggregateInputDefinition],
    inputs: &BTreeMap<String, f64>,
    point: &BTreeMap<String, f64>,
) -> f64 {
    definitions.iter().fold(1.0, |weight, definition| {
        let fraction = (inputs[&definition.id] - definition.minimum)
            / (definition.maximum - definition.minimum);
        if point[&definition.id] == definition.minimum {
            weight * (1.0 - fraction)
        } else {
            weight * fraction
        }
    })
}

fn interpolate_reports(
    function: &AggregateFunctionDefinition,
    artifact: &LearnedAggregateArtifact,
    inputs: &BTreeMap<String, f64>,
    days: u32,
    tick_hours: f64,
) -> DslResult<Vec<DslReport>> {
    let learned_day = days.min(function.time_days);
    let template = artifact
        .points
        .iter()
        .find(|point| point.day == learned_day)
        .ok_or_else(|| {
            DslError::new(
                "MISSING_LEARNED_POINT",
                function.line,
                format!("Learned aggregate has no report for day {learned_day}"),
            )
        })?;
    let tick = (f64::from(days) * 24.0 / tick_hours).round() as u64;
    template
        .reports
        .iter()
        .map(|report| {
            let mut report = report.clone();
            let rows = report
                .snapshots
                .last()
                .map(|snapshot| &snapshot.rows)
                .cloned()
                .unwrap_or_default();
            let rows = rows
                .into_iter()
                .map(|mut row| {
                    for (id, value) in &mut row.values {
                        *value = interpolate_report_value(
                            function,
                            artifact,
                            inputs,
                            learned_day,
                            &report.id,
                            &row.group_id,
                            id,
                            value,
                        )?;
                    }
                    Ok(row)
                })
                .collect::<DslResult<Vec<_>>>()?;
            report.record = "cached".to_owned();
            report.snapshots = vec![DslReportSnapshot { tick, rows }];
            Ok(report)
        })
        .collect()
}

#[allow(clippy::too_many_arguments)]
fn interpolate_report_value(
    function: &AggregateFunctionDefinition,
    artifact: &LearnedAggregateArtifact,
    inputs: &BTreeMap<String, f64>,
    day: u32,
    report_id: &str,
    group_id: &str,
    value_id: &str,
    template: &DslReportValue,
) -> DslResult<DslReportValue> {
    match template {
        DslReportValue::Number(_) => Ok(DslReportValue::Number(interpolate_number(
            function,
            artifact,
            inputs,
            day,
            |point| report_number(point, report_id, group_id, value_id),
        )?)),
        DslReportValue::Rates(template) => Ok(DslReportValue::Rates(
            template
                .keys()
                .map(|key| {
                    Ok((
                        key.clone(),
                        interpolate_number(function, artifact, inputs, day, |point| {
                            report_rate(point, report_id, group_id, value_id, key)
                        })?,
                    ))
                })
                .collect::<DslResult<_>>()?,
        )),
        DslReportValue::Text(value) => Ok(DslReportValue::Text(value.clone())),
    }
}

fn report_number(
    point: &LearnedAggregatePoint,
    report_id: &str,
    group_id: &str,
    value_id: &str,
) -> Option<f64> {
    let value = point
        .reports
        .iter()
        .find(|report| report.id == report_id)?
        .snapshots
        .last()?
        .rows
        .iter()
        .find(|row| row.group_id == group_id)?
        .values
        .get(value_id)?;
    match value {
        DslReportValue::Number(value) => Some(*value),
        _ => None,
    }
}

fn report_rate(
    point: &LearnedAggregatePoint,
    report_id: &str,
    group_id: &str,
    value_id: &str,
    key: &str,
) -> Option<f64> {
    let value = point
        .reports
        .iter()
        .find(|report| report.id == report_id)?
        .snapshots
        .last()?
        .rows
        .iter()
        .find(|row| row.group_id == group_id)?
        .values
        .get(value_id)?;
    match value {
        DslReportValue::Rates(values) => values.get(key).copied(),
        _ => None,
    }
}

fn aggregate_output_report(
    function: &AggregateFunctionDefinition,
    endpoint: &AggregateTimePoint,
    days: u32,
) -> DslReport {
    let mut columns = Vec::new();
    let mut values = BTreeMap::new();
    for output in &function.outputs {
        let summary = &endpoint.outputs[&output.id];
        columns.push(report_column(&output.id, &output.id));
        values.insert(output.id.clone(), DslReportValue::Number(summary.mean));
        let sd_id = format!("{}_sd", output.id);
        columns.push(report_column(&sd_id, &sd_id));
        values.insert(sd_id, DslReportValue::Number(summary.standard_deviation));
    }
    DslReport {
        id: "aggregate_outputs".to_owned(),
        title: format!("{} aggregate outputs", function.id),
        group_by: "archetype".to_owned(),
        display: "table".to_owned(),
        record: "cached".to_owned(),
        columns,
        snapshots: vec![DslReportSnapshot {
            tick: u64::from(days),
            rows: vec![DslReportRow {
                group_id: function.id.clone(),
                values,
            }],
        }],
    }
}

fn cache_metadata_report(
    artifact: &LearnedAggregateArtifact,
    requested_inputs_hash: &str,
    cache_hit: bool,
    reason: Option<&str>,
    agent_ticks: u64,
    days: u32,
) -> DslReport {
    let columns = [
        ("status", "Cache status", "number"),
        ("inputs_hash", "Inputs hash", "number"),
        ("valid_from", "Valid from", "integer"),
        ("valid_until", "Valid until", "integer"),
        ("dsl_source_hash", "DSL source hash", "number"),
        ("agent_ticks", "Agent ticks", "integer"),
        ("invalidation", "Invalidation", "number"),
    ]
    .into_iter()
    .map(|(id, label, format)| ReportColumnDefinition {
        id: id.to_owned(),
        label: label.to_owned(),
        format: format.to_owned(),
        metric: ReportMetric::Count,
        line: 1,
    })
    .collect();
    let values = BTreeMap::from([
        (
            "status".to_owned(),
            DslReportValue::Text(if cache_hit { "cached" } else { "relearned" }.to_owned()),
        ),
        (
            "inputs_hash".to_owned(),
            DslReportValue::Text(requested_inputs_hash.to_owned()),
        ),
        (
            "valid_from".to_owned(),
            DslReportValue::Number(f64::from(artifact.valid_from)),
        ),
        (
            "valid_until".to_owned(),
            DslReportValue::Number(f64::from(artifact.valid_until)),
        ),
        (
            "dsl_source_hash".to_owned(),
            DslReportValue::Text(artifact.dsl_source_hash.clone()),
        ),
        (
            "agent_ticks".to_owned(),
            DslReportValue::Number(agent_ticks as f64),
        ),
        (
            "invalidation".to_owned(),
            DslReportValue::Text(reason.unwrap_or("none").to_owned()),
        ),
    ]);
    DslReport {
        id: "cache_metadata".to_owned(),
        title: "Cache metadata".to_owned(),
        group_by: "cache".to_owned(),
        display: "cards".to_owned(),
        record: "cached".to_owned(),
        columns,
        snapshots: vec![DslReportSnapshot {
            tick: u64::from(days),
            rows: vec![DslReportRow {
                group_id: artifact.function_id.clone(),
                values,
            }],
        }],
    }
}

fn report_column(id: &str, label: &str) -> ReportColumnDefinition {
    ReportColumnDefinition {
        id: id.to_owned(),
        label: label.replace('_', " "),
        format: "decimal".to_owned(),
        metric: ReportMetric::Count,
        line: 1,
    }
}

fn final_reports(reports: &[DslReport]) -> Vec<DslReport> {
    reports
        .iter()
        .cloned()
        .map(|mut report| {
            report.snapshots = report.snapshots.last().cloned().into_iter().collect();
            report
        })
        .collect()
}

fn learned_summary(summary: MetricSummary) -> LearnedMetricSummary {
    LearnedMetricSummary {
        mean: summary.mean,
        standard_deviation: summary.standard_deviation,
    }
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

fn inputs_hash(inputs: &BTreeMap<String, f64>) -> String {
    let hash = inputs
        .iter()
        .fold(0xcbf29ce484222325_u64, |hash, (id, value)| {
            id.as_bytes()
                .iter()
                .chain(value.to_bits().to_be_bytes().iter())
                .fold(hash, |hash, byte| {
                    (hash ^ u64::from(*byte)).wrapping_mul(0x100000001b3)
                })
        });
    format!("fnv1a64:{hash:016x}")
}

fn grid_seed(seed: u64, inputs: &BTreeMap<String, f64>) -> u64 {
    inputs_hash(inputs)
        .as_bytes()
        .iter()
        .fold(seed, |hash, byte| {
            (hash ^ u64::from(*byte)).wrapping_mul(0x100000001b3)
        })
}

fn ticks_per_day(tick_hours: f64) -> u64 {
    (24.0 / tick_hours).round().max(1.0) as u64
}

fn stable_number(value: f64) -> f64 {
    (value * 1_000_000_000_000.0).round() / 1_000_000_000_000.0
}
