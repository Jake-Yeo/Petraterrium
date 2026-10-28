use super::composition_build::{build_composition_state, derived_seed};
use super::composition_reports::decorate_composition_result;
use super::expression::evaluate;
use super::model::*;
use super::runtime::run_program;
use std::collections::{BTreeMap, BTreeSet};

pub(super) struct CompositionBuild {
    pub(super) program: Program,
    pub(super) state: DslRunState,
    pub(super) agent_groups: BTreeMap<String, String>,
    pub(super) flows: Vec<ExecutedFlow>,
}

#[derive(Clone)]
pub(super) struct ExecutedFlow {
    pub(super) id: String,
    pub(super) source: String,
    pub(super) target: String,
    pub(super) effect: String,
    pub(super) via: Option<String>,
    pub(super) households: usize,
    pub(super) agents: usize,
    pub(super) rate: f64,
}

pub fn run_composition(
    program: Program,
    composition_id: &str,
    seed: u64,
    ticks: u64,
) -> DslResult<DslRunResult> {
    if let Some(composition) = program
        .compositions
        .iter()
        .find(|item| item.id == composition_id)
        .cloned()
    {
        return execute_composition_definition(program, composition, seed, ticks);
    }
    if let Some(population) = program
        .composition_populations
        .iter()
        .find(|item| item.id == composition_id)
        .cloned()
    {
        return aggregate_composition_population(program, population, seed, ticks);
    }
    Err(DslError::new(
        "UNKNOWN_COMPOSITION",
        1,
        format!("Unknown composition or composition population {composition_id}"),
    ))
}

fn execute_composition_definition(
    program: Program,
    composition: CompositionDefinition,
    seed: u64,
    ticks: u64,
) -> DslResult<DslRunResult> {
    let record_actions = program.record_actions;
    let build = build_composition_state(&program, &composition, seed)?;
    let tick_hours = build.program.tick_hours;
    let action_aggregates = build
        .program
        .actions
        .iter()
        .map(|action| (action.id.clone(), action.aggregate.clone()))
        .collect::<BTreeMap<_, _>>();
    let recorded_actions = build
        .program
        .actions
        .iter()
        .filter(|action| !action.record_fields.is_empty())
        .map(|action| action.id.clone())
        .collect();
    let mut flows = build.flows;
    let mut result = if composition.couplings.is_empty() || ticks == 0 {
        run_program(DslRunRequest::resume(
            build.program,
            seed,
            ticks,
            build.state,
        ))?
    } else {
        execute_coupled_chunks(
            &program,
            &composition,
            build.program,
            build.state,
            &build.agent_groups,
            &action_aggregates,
            &mut flows,
            seed,
            ticks,
        )?
    };
    decorate_composition_result(
        &composition,
        &mut result,
        &build.agent_groups,
        &action_aggregates,
        &flows,
        ticks,
        tick_hours,
        record_actions,
        &recorded_actions,
    )?;
    Ok(result)
}

#[allow(clippy::too_many_arguments)]
fn execute_coupled_chunks(
    source_program: &Program,
    composition: &CompositionDefinition,
    mut program: Program,
    mut state: DslRunState,
    agent_groups: &BTreeMap<String, String>,
    action_aggregates: &BTreeMap<String, String>,
    flows: &mut Vec<ExecutedFlow>,
    seed: u64,
    ticks: u64,
) -> DslResult<DslRunResult> {
    let baseline_decisions = program.decisions.clone();
    let sync_days = composition.cached.as_ref().unwrap().sync_days;
    let sync_ticks = ((f64::from(sync_days) * 24.0 / program.tick_hours).round() as u64).max(1);
    let ticks_per_day = ((24.0 / program.tick_hours).round() as u64).max(1);
    let mut actions = Vec::new();
    let mut latest = None;
    let mut previous_inputs = BTreeMap::new();
    while state.completed_ticks < ticks {
        let remaining = ticks - state.completed_ticks;
        let delta = remaining.min(sync_ticks);
        let mut result = run_program(DslRunRequest::resume(program.clone(), seed, delta, state))?;
        program.decisions = baseline_decisions.clone();
        let coupling_flows = apply_detailed_couplings(
            source_program,
            composition,
            &mut program,
            &mut result.state,
            &result.actions,
            agent_groups,
            action_aggregates,
            ticks_per_day,
            &mut previous_inputs,
        )?;
        flows.extend(coupling_flows);
        actions.extend(result.actions.clone());
        state = result.state.clone();
        latest = Some(result);
    }
    let mut result = latest.unwrap();
    result.state = state;
    result.actions = actions;
    Ok(result)
}

#[allow(clippy::too_many_arguments)]
fn apply_detailed_couplings(
    source_program: &Program,
    composition: &CompositionDefinition,
    program: &mut Program,
    state: &mut DslRunState,
    actions: &[DslActionRecord],
    agent_groups: &BTreeMap<String, String>,
    action_aggregates: &BTreeMap<String, String>,
    ticks_per_day: u64,
    previous_inputs: &mut BTreeMap<String, BTreeMap<String, f64>>,
) -> DslResult<Vec<ExecutedFlow>> {
    let child_definitions = composition
        .entries
        .iter()
        .filter_map(|entry| {
            source_program
                .compositions
                .iter()
                .find(|child| child.id == entry.child)
                .map(|child| (entry.child.as_str(), child))
        })
        .collect::<BTreeMap<_, _>>();
    let child_outputs = child_definitions
        .iter()
        .map(|(id, definition)| {
            (
                (*id).to_owned(),
                detailed_child_outputs(
                    definition,
                    state,
                    actions,
                    agent_groups,
                    action_aggregates,
                    ticks_per_day,
                ),
            )
        })
        .collect::<BTreeMap<_, _>>();
    let mut values = composition
        .parameters
        .iter()
        .map(|(id, value)| (id.clone(), DslValue::Number(*value)))
        .chain(
            source_program
                .aggregate_functions
                .iter()
                .find(|function| function.id == composition.id)
                .into_iter()
                .flat_map(|function| {
                    function
                        .inputs
                        .iter()
                        .map(|input| (input.id.clone(), DslValue::Number(input.default)))
                }),
        )
        .collect::<BTreeMap<_, _>>();
    for (child, outputs) in &child_outputs {
        for (output, value) in outputs {
            values.insert(format!("{child}_{output}"), DslValue::Number(*value));
            values.insert(format!("{child}.{output}"), DslValue::Number(*value));
        }
    }
    let mut target_inputs = BTreeMap::<String, BTreeMap<String, f64>>::new();
    let mut executed = Vec::new();
    for coupling in &composition.couplings {
        let value = evaluate(&coupling.value, &values)?
            .as_f64()
            .ok_or_else(|| {
                DslError::new(
                    "INVALID_COMPOSITION_COUPLING_VALUE",
                    coupling.line,
                    "Coupling value must resolve to a number",
                )
            })?;
        target_inputs
            .entry(coupling.target.clone())
            .or_default()
            .insert(coupling.target_input.clone(), value);
        let source_population = agent_groups
            .values()
            .filter(|group| *group == &coupling.source)
            .count();
        executed.push(ExecutedFlow {
            id: coupling.id.clone(),
            source: coupling.source.clone(),
            target: coupling.target.clone(),
            effect: "coupling".to_owned(),
            via: None,
            households: 0,
            agents: (value.abs() * source_population as f64).round() as usize,
            rate: value,
        });
        values.insert(coupling.id.clone(), DslValue::Number(value));
    }
    for (target, requested) in target_inputs {
        apply_detailed_coupling_effects(
            source_program,
            program,
            state,
            agent_groups,
            &target,
            &requested,
            previous_inputs.get(&target),
        )?;
        previous_inputs.insert(target, requested);
    }
    for boundary in &composition.boundaries {
        let count = apply_boundary_agents(boundary, state, agent_groups);
        executed.push(ExecutedFlow {
            id: boundary.id.clone(),
            source: boundary.source.clone(),
            target: boundary.target.clone(),
            effect: "boundary".to_owned(),
            via: None,
            households: 0,
            agents: count,
            rate: if count == 0 { 0.0 } else { 1.0 },
        });
    }
    Ok(executed)
}

fn apply_boundary_agents(
    boundary: &CompositionBoundaryDefinition,
    state: &mut DslRunState,
    agent_groups: &BTreeMap<String, String>,
) -> usize {
    let mut sources = state
        .agents
        .iter()
        .enumerate()
        .filter(|(_, agent)| agent_groups.get(&agent.id) == Some(&boundary.source))
        .map(|(index, agent)| (index, agent.id.clone()))
        .collect::<Vec<_>>();
    let mut targets = state
        .agents
        .iter()
        .enumerate()
        .filter(|(_, agent)| agent_groups.get(&agent.id) == Some(&boundary.target))
        .map(|(index, agent)| (index, agent.id.clone()))
        .collect::<Vec<_>>();
    sources.sort_by(|left, right| left.1.cmp(&right.1));
    targets.sort_by(|left, right| left.1.cmp(&right.1));
    let count = sources.len().min(targets.len());
    for index in 0..count {
        let values = boundary
            .fields
            .iter()
            .filter_map(|field| {
                state.agents[sources[index].0]
                    .value(field)
                    .cloned()
                    .map(|value| (field.clone(), value))
            })
            .collect::<Vec<_>>();
        let target = &mut state.agents[targets[index].0];
        for (field, value) in values {
            if let Some(current) = target.states.get_mut(&field) {
                *current = value;
            } else if let Some(current) = target.traits.get_mut(&field) {
                *current = value;
            }
        }
    }
    count
}

fn detailed_child_outputs(
    definition: &CompositionDefinition,
    state: &DslRunState,
    actions: &[DslActionRecord],
    agent_groups: &BTreeMap<String, String>,
    action_aggregates: &BTreeMap<String, String>,
    ticks_per_day: u64,
) -> BTreeMap<String, f64> {
    let indices = state
        .agents
        .iter()
        .enumerate()
        .filter(|(_, agent)| agent_groups.get(&agent.id) == Some(&definition.id))
        .map(|(index, _)| index)
        .collect::<Vec<_>>();
    let ids = indices
        .iter()
        .map(|index| state.agents[*index].id.as_str())
        .collect::<BTreeSet<_>>();
    definition
        .outputs
        .iter()
        .filter_map(|output| {
            let value = match &output.metric {
                ReportMetric::Count => indices.len() as f64,
                ReportMetric::Mean { field } => mean_field(state, &indices, field),
                ReportMetric::StandardDeviation { field } => {
                    standard_deviation_field(state, &indices, field)
                }
                ReportMetric::Sum { field } => indices
                    .iter()
                    .filter_map(|index| state.agents[*index].value(field)?.as_f64())
                    .sum(),
                ReportMetric::ActionCount { aggregate, window }
                | ReportMetric::ActionRate { aggregate, window } => {
                    let first_tick = if window == "day" {
                        state.completed_ticks.saturating_sub(ticks_per_day - 1)
                    } else if window == "tick" {
                        state.completed_ticks
                    } else {
                        0
                    };
                    let count = actions
                        .iter()
                        .filter(|action| {
                            action.tick >= first_tick && ids.contains(action.agent_id.as_str())
                        })
                        .filter(|action| action_aggregates.get(&action.action) == Some(aggregate))
                        .count() as f64;
                    if matches!(output.metric, ReportMetric::ActionRate { .. }) {
                        count / indices.len().max(1) as f64
                    } else {
                        count
                    }
                }
                _ => return None,
            };
            Some((output.id.clone(), value))
        })
        .collect()
}

fn mean_field(state: &DslRunState, indices: &[usize], field: &str) -> f64 {
    let values = indices
        .iter()
        .filter_map(|index| state.agents[*index].value(field)?.as_f64())
        .collect::<Vec<_>>();
    if values.is_empty() {
        0.0
    } else {
        values.iter().sum::<f64>() / values.len() as f64
    }
}

fn standard_deviation_field(state: &DslRunState, indices: &[usize], field: &str) -> f64 {
    let values = indices
        .iter()
        .filter_map(|index| state.agents[*index].value(field)?.as_f64())
        .collect::<Vec<_>>();
    if values.is_empty() {
        return 0.0;
    }
    let mean = values.iter().sum::<f64>() / values.len() as f64;
    (values
        .iter()
        .map(|value| (value - mean).powi(2))
        .sum::<f64>()
        / values.len() as f64)
        .sqrt()
}

fn apply_detailed_coupling_effects(
    source_program: &Program,
    program: &mut Program,
    state: &mut DslRunState,
    agent_groups: &BTreeMap<String, String>,
    target: &str,
    requested: &BTreeMap<String, f64>,
    previous: Option<&BTreeMap<String, f64>>,
) -> DslResult<()> {
    let root = source_program
        .compositions
        .iter()
        .find(|composition| composition.id == target)
        .unwrap();
    let mut scopes = Vec::new();
    collect_effect_scopes(source_program, root, target, &mut scopes);
    for (definition, prefix) in scopes {
        let Some(function) = source_program
            .aggregate_functions
            .iter()
            .find(|function| function.id == definition.id)
        else {
            continue;
        };
        let inputs = function
            .inputs
            .iter()
            .map(|input| {
                (
                    input.id.clone(),
                    requested
                        .get(&input.id)
                        .or_else(|| definition.parameters.get(&input.id))
                        .copied()
                        .unwrap_or(input.default),
                )
            })
            .collect::<BTreeMap<_, _>>();
        let values = inputs
            .iter()
            .map(|(id, value)| (id.clone(), DslValue::Number(*value)))
            .collect::<BTreeMap<_, _>>();
        let fields_changed = function.inputs.iter().any(|input| {
            let current = inputs[&input.id];
            previous
                .and_then(|values| values.get(&input.id))
                .is_none_or(|value| (current - value).abs() > input.invalidate_threshold)
        });
        for effect in &function.effects {
            let value = evaluate(&effect.value, &values)?.as_f64().ok_or_else(|| {
                DslError::new(
                    "INVALID_AGGREGATE_EFFECT",
                    effect.line,
                    "Coupled aggregate effect must resolve to a number",
                )
            })?;
            match &effect.target {
                AggregateEffectTarget::Decision(action) => {
                    for branch in program
                        .decisions
                        .iter_mut()
                        .flat_map(|decision| &mut decision.branches)
                        .filter(|branch| {
                            branch.action.starts_with(&format!("{prefix}__"))
                                && (branch.action == *action
                                    || branch.action.ends_with(&format!("__{action}")))
                        })
                    {
                        branch.probability =
                            effect_expression(branch.probability.clone(), &effect.operation, value);
                    }
                }
                AggregateEffectTarget::Field(field) => {
                    if !fields_changed {
                        continue;
                    }
                    for agent in &mut state.agents {
                        if agent_groups.get(&agent.id).map(String::as_str) != Some(target)
                            || !agent.id.starts_with(&format!("{prefix}__"))
                        {
                            continue;
                        }
                        let agent_type = agent.agent_type.clone();
                        let current = agent
                            .states
                            .get_mut(field)
                            .or_else(|| agent.traits.get_mut(field));
                        if let Some(current) = current
                            && let Some(number) = current.as_f64()
                        {
                            let mut next =
                                apply_number(number, &effect.operation, value, effect.line)?;
                            if let Some(bounds) = agent_field_bounds(program, &agent_type, field) {
                                next = next.clamp(bounds.minimum, bounds.maximum);
                            }
                            *current = DslValue::Number(next);
                        }
                    }
                }
            }
        }
    }
    Ok(())
}

fn collect_effect_scopes<'a>(
    program: &'a Program,
    definition: &'a CompositionDefinition,
    prefix: &str,
    result: &mut Vec<(&'a CompositionDefinition, String)>,
) {
    result.push((definition, prefix.to_owned()));
    for entry in &definition.entries {
        if let Some(child) = program
            .compositions
            .iter()
            .find(|child| child.id == entry.child)
        {
            collect_effect_scopes(program, child, &format!("{prefix}__{}", child.id), result);
        }
    }
}

fn agent_field_bounds<'a>(
    program: &'a Program,
    agent_type: &str,
    field: &str,
) -> Option<&'a ValueBounds> {
    let definition = program.agents.iter().find(|agent| agent.id == agent_type)?;
    definition.state_bounds.get(field).or_else(|| {
        definition
            .parent
            .as_ref()
            .and_then(|parent| agent_field_bounds(program, parent, field))
    })
}

fn effect_expression(current: Expr, operation: &str, value: f64) -> Expr {
    if operation == "=" {
        Expr::Value(DslValue::Number(value))
    } else {
        Expr::Binary {
            operation: operation.trim_end_matches('=').to_owned(),
            left: Box::new(current),
            right: Box::new(Expr::Value(DslValue::Number(value))),
        }
    }
}

fn apply_number(current: f64, operation: &str, value: f64, line: usize) -> DslResult<f64> {
    match operation {
        "=" => Ok(value),
        "+=" => Ok(current + value),
        "-=" => Ok(current - value),
        "*=" => Ok(current * value),
        _ => Err(DslError::new(
            "INVALID_AGGREGATE_EFFECT",
            line,
            format!("Unsupported effect operation {operation}"),
        )),
    }
}

fn aggregate_composition_population(
    program: Program,
    population: WeightedCompositionPopulation,
    seed: u64,
    ticks: u64,
) -> DslResult<DslRunResult> {
    let definitions = program
        .compositions
        .iter()
        .map(|item| (item.id.as_str(), item))
        .collect::<BTreeMap<_, _>>();
    let mut runs = Vec::new();
    for entry in &population.entries {
        let definition = definitions[entry.composition.as_str()].clone();
        runs.push((
            entry,
            execute_composition_definition(
                program.clone(),
                definition,
                derived_seed(seed, &entry.composition),
                ticks,
            )?,
        ));
    }
    let first_definition = definitions[population.entries[0].composition.as_str()];
    let report_id = &first_definition.report_id;
    let first_report = runs
        .first()
        .and_then(|(_, result)| result.reports.iter().find(|report| report.id == *report_id))
        .ok_or_else(|| {
            DslError::new(
                "EMPTY_COMPOSITION_POPULATION",
                population.line,
                "Composition population produced no reports",
            )
        })?;
    let output_columns = first_report
        .columns
        .iter()
        .filter(|column| column.id != "population" && !column.id.ends_with("_sd"))
        .cloned()
        .collect::<Vec<_>>();
    let total_weight = runs
        .iter()
        .map(|(entry, _)| entry.weight as f64)
        .sum::<f64>();
    let total_population = runs
        .iter()
        .map(|(entry, result)| entry.weight as f64 * result.state.agents.len() as f64)
        .sum::<f64>();
    let represented_population = population
        .entries
        .iter()
        .map(|entry| {
            entry.represented_population.or_else(|| {
                definitions[entry.composition.as_str()]
                    .represented_population
                    .map(|value| value.saturating_mul(entry.weight))
            })
        })
        .collect::<Option<Vec<_>>>()
        .map(|values| values.into_iter().sum::<u64>());
    let mut summary_values = BTreeMap::from([(
        "total_population".to_owned(),
        DslReportValue::Number(total_population),
    )]);
    let mut summary_columns = vec![ReportColumnDefinition {
        id: "total_population".to_owned(),
        label: "Total population".to_owned(),
        format: "integer".to_owned(),
        metric: ReportMetric::Count,
        line: population.line,
    }];
    if let Some(represented_population) = represented_population {
        summary_values.insert(
            "represented_population".to_owned(),
            DslReportValue::Number(represented_population as f64),
        );
        summary_columns.push(ReportColumnDefinition {
            id: "represented_population".to_owned(),
            label: "Represented population".to_owned(),
            format: "integer".to_owned(),
            metric: ReportMetric::RepresentedCount,
            line: population.line,
        });
    }
    for column in &output_columns {
        let mean = runs
            .iter()
            .map(|(entry, result)| {
                entry.weight as f64 * composition_value(result, report_id, &column.id)
            })
            .sum::<f64>()
            / total_weight;
        summary_values.insert(column.id.clone(), DslReportValue::Number(mean));
        summary_columns.push(column.clone());
        let sd_id = format!("{}_sd", column.id);
        if first_report.columns.iter().any(|item| item.id == sd_id) {
            let variance = runs
                .iter()
                .map(|(entry, result)| {
                    let value = composition_value(result, report_id, &column.id);
                    let sd = composition_value(result, report_id, &sd_id);
                    entry.weight as f64 * (sd.powi(2) + (value - mean).powi(2))
                })
                .sum::<f64>()
                / total_weight;
            summary_values.insert(sd_id.clone(), DslReportValue::Number(variance.sqrt()));
            summary_columns.push(
                first_report
                    .columns
                    .iter()
                    .find(|item| item.id == sd_id)
                    .unwrap()
                    .clone(),
            );
        }
    }
    let legacy = first_definition.report_id == "neighbourhoods";
    let summary = DslReport {
        id: if legacy {
            "neighbourhood_population_summary"
        } else {
            "composition_population_summary"
        }
        .to_owned(),
        title: population.id.clone(),
        group_by: "all".to_owned(),
        display: "cards".to_owned(),
        record: "final".to_owned(),
        columns: summary_columns,
        snapshots: vec![DslReportSnapshot {
            tick: ticks,
            rows: vec![DslReportRow {
                group_id: population.id.clone(),
                values: summary_values,
            }],
        }],
    };
    let mut agents = Vec::new();
    let mut relationships = Vec::new();
    let mut time = Vec::new();
    for (_, result) in runs {
        agents.extend(result.state.agents);
        relationships.extend(result.state.relationships);
        time.extend(result.state.time);
    }
    Ok(DslRunResult {
        completed_ticks: ticks,
        state: DslRunState {
            completed_ticks: ticks,
            agents,
            places: program
                .places
                .iter()
                .filter(|place| place.scope == "program")
                .map(|place| DslPlaceState {
                    id: place.id.clone(),
                    states: place.states.clone(),
                })
                .collect(),
            relationships,
            time,
        },
        actions: Vec::new(),
        results_title: program.results_title,
        results_subtitle: if legacy {
            format!("{} weighted neighbourhood aggregates", population.id)
        } else {
            format!("{} weighted composition aggregates", population.id)
        },
        reports: vec![summary],
    })
}

fn composition_value(result: &DslRunResult, report_id: &str, id: &str) -> f64 {
    result
        .reports
        .iter()
        .find(|report| report.id == report_id)
        .and_then(|report| report.snapshots.last())
        .and_then(|snapshot| snapshot.rows.first())
        .and_then(|row| row.values.get(id))
        .and_then(|value| match value {
            DslReportValue::Number(value) => Some(*value),
            _ => None,
        })
        .unwrap_or(0.0)
}
