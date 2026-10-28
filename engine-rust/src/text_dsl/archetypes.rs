use super::expression::evaluate;
use super::model::*;
use super::runtime::{run_program, sample_population};
use std::collections::{BTreeMap, BTreeSet};

pub(super) struct MetricSummary {
    pub(super) mean: f64,
    pub(super) standard_deviation: f64,
}

struct ArchetypeRun<'a> {
    definition: &'a ArchetypeDefinition,
    weight: u64,
    population_per_household: usize,
    result: DslRunResult,
    outputs: BTreeMap<String, MetricSummary>,
}

pub fn run_weighted_population(
    program: Program,
    population_id: &str,
    seed: u64,
    ticks: u64,
) -> DslResult<DslRunResult> {
    let population = program
        .weighted_populations
        .iter()
        .find(|item| item.id == population_id)
        .ok_or_else(|| {
            DslError::new(
                "UNKNOWN_WEIGHTED_POPULATION",
                1,
                format!("Unknown weighted population {population_id}"),
            )
        })?;
    let archetypes = program
        .archetypes
        .iter()
        .map(|item| (item.id.as_str(), item))
        .collect::<BTreeMap<_, _>>();
    let mut runs = Vec::new();
    for entry in &population.entries {
        let definition = archetypes[entry.archetype.as_str()];
        let (archetype_program, state, population_per_household) =
            build_archetype_state(&program, definition, seed)?;
        let result = run_program(DslRunRequest::resume(
            archetype_program,
            derived_seed(seed, &definition.id),
            ticks,
            state,
        ))?;
        let outputs = calculate_outputs(definition, &result)?;
        runs.push(ArchetypeRun {
            definition,
            weight: entry.weight,
            population_per_household,
            result,
            outputs,
        });
    }
    weighted_result(&program, population, runs, ticks)
}

pub fn run_expanded_archetype_population(
    program: Program,
    population_id: &str,
    seed: u64,
    ticks: u64,
) -> DslResult<DslRunResult> {
    let population = program
        .weighted_populations
        .iter()
        .find(|item| item.id == population_id)
        .ok_or_else(|| {
            DslError::new(
                "UNKNOWN_WEIGHTED_POPULATION",
                1,
                format!("Unknown weighted population {population_id}"),
            )
        })?;
    let archetypes = program
        .archetypes
        .iter()
        .map(|item| (item.id.as_str(), item))
        .collect::<BTreeMap<_, _>>();
    let mut combined_program = program.clone();
    combined_program.archetypes.clear();
    combined_program.weighted_populations.clear();
    combined_program.population.child_generation = None;
    let mut agents = Vec::new();
    let mut relationships = Vec::new();
    for entry in &population.entries {
        let definition = archetypes[entry.archetype.as_str()];
        if !definition.decision_multipliers.is_empty() {
            return Err(DslError::new(
                "EXPANDED_DECISION_OVERRIDE",
                definition.line,
                "Expanded comparison requires archetypes without decision multipliers",
            ));
        }
        let (prepared, state, _) = build_archetype_state(&program, definition, seed)?;
        merge_declared_fields(&mut combined_program, &prepared);
        agents.extend(state.agents);
        relationships.extend(state.relationships);
    }
    let time = agents
        .iter()
        .map(|_| DslAgentTimeState {
            active_primary: None,
            deferred: Vec::new(),
            occurrence_counts: BTreeMap::new(),
        })
        .collect();
    let places = places_for_agents(&program, &agents);
    let state = DslRunState {
        completed_ticks: 0,
        agents,
        places,
        relationships,
        time,
    };
    run_program(DslRunRequest::resume(combined_program, seed, ticks, state))
}

pub(super) fn build_archetype_state(
    program: &Program,
    archetype: &ArchetypeDefinition,
    seed: u64,
) -> DslResult<(Program, DslRunState, usize)> {
    let prepared = prepare_archetype_program(program, archetype);
    let mut households = (0..archetype.sample_households)
        .map(|_| Vec::new())
        .collect::<Vec<Vec<DslAgentState>>>();
    for group in &archetype.composition {
        let child_group = group
            .mix
            .iter()
            .all(|entry| agent_has_role(program, &entry.agent_type, "child"));
        let mut group_program = if child_group {
            let mut base = program.clone();
            base.archetypes.clear();
            base.weighted_populations.clear();
            base.population.child_generation = None;
            base
        } else {
            prepared.clone()
        };
        group_program.population = PopulationDefinition {
            size: archetype.sample_households * group.count,
            mix: group.mix.clone(),
            child_generation: None,
        };
        let sampled = sample_population(
            &group_program,
            derived_seed(seed, &format!("{}:{}", archetype.id, group.id)),
        )?;
        for (index, mut agent) in sampled.agents.into_iter().enumerate() {
            let household_index = index / group.count;
            let slot = index % group.count;
            agent.id = format!(
                "{}-household-{household_index:04}-{}-{slot}",
                archetype.id, group.id
            );
            agent.household_id = format!("{}-household-{household_index:04}", archetype.id);
            agent.parent_id = None;
            households[household_index].push(agent);
        }
    }
    let mut agents = households.into_iter().flatten().collect::<Vec<_>>();
    let mut relationships = Vec::new();
    let household_ids = agents
        .iter()
        .map(|agent| agent.household_id.clone())
        .collect::<BTreeSet<_>>();
    for household_id in household_ids {
        let parent_id = agents
            .iter()
            .find(|agent| agent.household_id == household_id && !agent.roles.contains("child"))
            .map(|agent| agent.id.clone());
        let Some(parent_id) = parent_id else {
            continue;
        };
        for agent in agents
            .iter_mut()
            .filter(|agent| agent.household_id == household_id && agent.roles.contains("child"))
        {
            agent.parent_id = Some(parent_id.clone());
            relationships.push(DslRelationshipState {
                kind: "parent".to_owned(),
                source_id: parent_id.clone(),
                target_id: agent.id.clone(),
                values: BTreeMap::new(),
            });
        }
    }
    let time = agents
        .iter()
        .map(|_| DslAgentTimeState {
            active_primary: None,
            deferred: Vec::new(),
            occurrence_counts: BTreeMap::new(),
        })
        .collect();
    let places = places_for_agents(program, &agents);
    let state = DslRunState {
        completed_ticks: 0,
        agents,
        places,
        relationships,
        time,
    };
    let population_per_household = archetype.composition.iter().map(|group| group.count).sum();
    Ok((prepared, state, population_per_household))
}

fn places_for_agents(program: &Program, agents: &[DslAgentState]) -> Vec<DslPlaceState> {
    let used = agents
        .iter()
        .filter_map(|agent| agent.place())
        .collect::<BTreeSet<_>>();
    program
        .places
        .iter()
        .filter(|place| place.scope == "program" || used.contains(place.id.as_str()))
        .map(|place| DslPlaceState {
            id: place.id.clone(),
            states: place.states.clone(),
        })
        .collect()
}

fn agent_has_role(program: &Program, agent_type: &str, role: &str) -> bool {
    let Some(agent) = program.agents.iter().find(|agent| agent.id == agent_type) else {
        return false;
    };
    agent.roles.contains(role)
        || agent
            .parent
            .as_ref()
            .is_some_and(|parent| agent_has_role(program, parent, role))
}

fn prepare_archetype_program(program: &Program, archetype: &ArchetypeDefinition) -> Program {
    let mut prepared = program.clone();
    prepared.archetypes.clear();
    prepared.weighted_populations.clear();
    prepared.population.child_generation = None;
    let state_fields = prepared
        .agents
        .iter()
        .flat_map(|agent| agent.states.iter().cloned())
        .collect::<BTreeSet<_>>();
    for agent in &mut prepared.agents {
        for assignment in &archetype.initial {
            if !agent.states.contains(&assignment.field)
                && !agent.traits.contains(&assignment.field)
            {
                if state_fields.contains(&assignment.field) {
                    agent.states.insert(assignment.field.clone());
                } else {
                    agent.traits.insert(assignment.field.clone());
                }
            }
            if let Some(existing) = agent
                .initial
                .iter_mut()
                .find(|item| item.field == assignment.field)
            {
                *existing = assignment.clone();
            } else {
                agent.initial.push(assignment.clone());
            }
        }
    }
    for multiplier in &archetype.decision_multipliers {
        for branch in prepared
            .decisions
            .iter_mut()
            .flat_map(|decision| &mut decision.branches)
            .filter(|branch| branch.action == multiplier.action)
        {
            branch.probability = Expr::Binary {
                operation: "*".to_owned(),
                left: Box::new(branch.probability.clone()),
                right: Box::new(Expr::Value(DslValue::Number(multiplier.multiplier))),
            };
        }
    }
    ensure_action_metric_report(&mut prepared, &archetype.outputs);
    prepared
}

pub(super) fn ensure_action_metric_report(
    program: &mut Program,
    outputs: &[ArchetypeOutputDefinition],
) {
    let existing = program
        .reports
        .iter()
        .flat_map(|report| &report.columns)
        .map(|column| column.metric.clone())
        .collect::<Vec<_>>();
    let mut ids = BTreeSet::new();
    let columns = outputs
        .iter()
        .filter(|output| {
            matches!(
                output.metric,
                ReportMetric::ActionCount { .. } | ReportMetric::ActionRate { .. }
            ) && !existing.iter().any(|metric| metric == &output.metric)
                && ids.insert(output.id.clone())
        })
        .map(|output| ReportColumnDefinition {
            id: output.id.clone(),
            label: output.id.replace('_', " "),
            format: "decimal".to_owned(),
            metric: output.metric.clone(),
            line: output.line,
        })
        .collect::<Vec<_>>();
    if columns.is_empty() {
        return;
    }
    program.reports.push(ReportDefinition {
        id: "__action_metrics".to_owned(),
        title: "Action metrics".to_owned(),
        group_by: "all".to_owned(),
        display: "table".to_owned(),
        record: "final".to_owned(),
        columns,
        line: 1,
    });
}

fn merge_declared_fields(target: &mut Program, source: &Program) {
    for target_agent in &mut target.agents {
        if let Some(source_agent) = source
            .agents
            .iter()
            .find(|agent| agent.id == target_agent.id)
        {
            target_agent.traits.extend(source_agent.traits.clone());
            target_agent.states.extend(source_agent.states.clone());
        }
    }
}

pub(super) fn calculate_outputs(
    archetype: &ArchetypeDefinition,
    result: &DslRunResult,
) -> DslResult<BTreeMap<String, MetricSummary>> {
    calculate_output_definitions(&archetype.outputs, result)
}

pub(super) fn calculate_output_definitions(
    outputs: &[ArchetypeOutputDefinition],
    result: &DslRunResult,
) -> DslResult<BTreeMap<String, MetricSummary>> {
    outputs
        .iter()
        .map(|output| {
            let mut values = match &output.metric {
                ReportMetric::Count => vec![result.state.agents.len() as f64],
                ReportMetric::RepresentedCount => Vec::new(),
                ReportMetric::Mean { field } => result
                    .state
                    .agents
                    .iter()
                    .filter(|agent| output_filter(output, agent).unwrap_or(false))
                    .filter_map(|agent| agent.value(field).and_then(DslValue::as_f64))
                    .collect::<Vec<_>>(),
                ReportMetric::StandardDeviation { field } => {
                    let values = result
                        .state
                        .agents
                        .iter()
                        .filter(|agent| output_filter(output, agent).unwrap_or(false))
                        .filter_map(|agent| agent.value(field).and_then(DslValue::as_f64))
                        .collect::<Vec<_>>();
                    vec![standard_deviation(&values)]
                }
                ReportMetric::Sum { field } => vec![
                    result
                        .state
                        .agents
                        .iter()
                        .filter_map(|agent| agent.value(field).and_then(DslValue::as_f64))
                        .sum(),
                ],
                ReportMetric::KidsPerFamily => kids_per_family_values(&result.state),
                ReportMetric::ActionCount { .. } | ReportMetric::ActionRate { .. } => {
                    report_metric_values(result, &output.metric)
                }
                ReportMetric::PlaceState { place, field } => result
                    .state
                    .places
                    .iter()
                    .find(|item| item.id == *place)
                    .and_then(|item| item.states.get(field))
                    .and_then(DslValue::as_f64)
                    .into_iter()
                    .collect(),
                ReportMetric::FlowCount { flow } => composition_flow_values(result, flow, "count"),
                ReportMetric::FlowRate { flow } => composition_flow_values(result, flow, "rate"),
                _ => Vec::new(),
            };
            if values.is_empty()
                && matches!(
                    output.metric,
                    ReportMetric::ActionCount { .. }
                        | ReportMetric::ActionRate { .. }
                        | ReportMetric::FlowCount { .. }
                        | ReportMetric::FlowRate { .. }
                )
            {
                values.push(0.0);
            }
            if values.is_empty() {
                return Err(DslError::new(
                    "EMPTY_ARCHETYPE_METRIC",
                    output.line,
                    format!("Archetype output {} has no eligible agents", output.id),
                ));
            }
            let mean = values.iter().sum::<f64>() / values.len() as f64;
            let variance = values
                .iter()
                .map(|value| (value - mean).powi(2))
                .sum::<f64>()
                / values.len() as f64;
            Ok((
                output.id.clone(),
                MetricSummary {
                    mean,
                    standard_deviation: variance.sqrt(),
                },
            ))
        })
        .collect()
}

fn report_metric_values(result: &DslRunResult, metric: &ReportMetric) -> Vec<f64> {
    result
        .reports
        .iter()
        .filter(|report| report.group_by == "all")
        .filter_map(|report| {
            let column = report
                .columns
                .iter()
                .find(|column| column.metric == *metric)?;
            let value = report
                .snapshots
                .last()?
                .rows
                .first()?
                .values
                .get(&column.id)?;
            report_number(value)
        })
        .collect()
}

fn composition_flow_values(result: &DslRunResult, flow: &str, value: &str) -> Vec<f64> {
    result
        .reports
        .iter()
        .find(|report| report.id == "composition_flows")
        .and_then(|report| report.snapshots.last())
        .and_then(|snapshot| snapshot.rows.iter().find(|row| row.group_id == flow))
        .and_then(|row| row.values.get(value))
        .and_then(|value| match value {
            DslReportValue::Number(value) => Some(*value),
            _ => None,
        })
        .into_iter()
        .collect()
}

pub(super) fn calculate_aggregate_metric(
    result: &DslRunResult,
    metric: &ReportMetric,
    line: usize,
) -> DslResult<MetricSummary> {
    let mut values = match metric {
        ReportMetric::Count => vec![result.state.agents.len() as f64],
        ReportMetric::RepresentedCount => Vec::new(),
        ReportMetric::Mean { field } => result
            .state
            .agents
            .iter()
            .filter_map(|agent| agent.value(field).and_then(DslValue::as_f64))
            .collect::<Vec<_>>(),
        ReportMetric::StandardDeviation { field } => {
            let values = result
                .state
                .agents
                .iter()
                .filter_map(|agent| agent.value(field).and_then(DslValue::as_f64))
                .collect::<Vec<_>>();
            vec![standard_deviation(&values)]
        }
        ReportMetric::Sum { field } => vec![
            result
                .state
                .agents
                .iter()
                .filter_map(|agent| agent.value(field).and_then(DslValue::as_f64))
                .sum(),
        ],
        ReportMetric::ActionCount { .. } | ReportMetric::ActionRate { .. } => {
            report_metric_values(result, metric)
        }
        ReportMetric::PlaceState { place, field } => result
            .state
            .places
            .iter()
            .find(|item| item.id == *place)
            .and_then(|item| item.states.get(field))
            .and_then(DslValue::as_f64)
            .into_iter()
            .collect(),
        ReportMetric::FlowCount { flow } => composition_flow_values(result, flow, "count"),
        ReportMetric::FlowRate { flow } => composition_flow_values(result, flow, "rate"),
        _ => Vec::new(),
    };
    if values.is_empty()
        && matches!(
            metric,
            ReportMetric::ActionCount { .. }
                | ReportMetric::ActionRate { .. }
                | ReportMetric::FlowCount { .. }
                | ReportMetric::FlowRate { .. }
        )
    {
        values.push(0.0);
    }
    if values.is_empty() {
        return Err(DslError::new(
            "EMPTY_AGGREGATE_METRIC",
            line,
            "Aggregate output source has no values",
        ));
    }
    let mean = values.iter().sum::<f64>() / values.len() as f64;
    let variance = values
        .iter()
        .map(|value| (value - mean).powi(2))
        .sum::<f64>()
        / values.len() as f64;
    Ok(MetricSummary {
        mean,
        standard_deviation: variance.sqrt(),
    })
}

fn standard_deviation(values: &[f64]) -> f64 {
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

fn output_filter(output: &ArchetypeOutputDefinition, agent: &DslAgentState) -> DslResult<bool> {
    let Some(filter) = &output.filter else {
        return Ok(true);
    };
    let values = agent
        .traits
        .iter()
        .chain(&agent.states)
        .map(|(key, value)| (key.clone(), value.clone()))
        .collect::<BTreeMap<_, _>>();
    Ok(evaluate(filter, &values)?.as_bool().unwrap_or(false))
}

fn kids_per_family_values(state: &DslRunState) -> Vec<f64> {
    let mut counts = BTreeMap::<&str, usize>::new();
    for relationship in &state.relationships {
        if relationship.kind == "parent" {
            *counts.entry(&relationship.source_id).or_default() += 1;
        }
    }
    counts.into_values().map(|count| count as f64).collect()
}

fn weighted_result(
    program: &Program,
    population: &WeightedPopulationDefinition,
    runs: Vec<ArchetypeRun<'_>>,
    ticks: u64,
) -> DslResult<DslRunResult> {
    let mut reports = vec![weighted_summary_report(population, &runs, ticks)?];
    reports.extend(merged_base_reports(program, &runs, ticks));
    reports.push(archetype_report(&runs, ticks));
    let mut agents = Vec::new();
    let mut relationships = Vec::new();
    let mut time = Vec::new();
    let mut actions = Vec::new();
    for run in runs {
        agents.extend(run.result.state.agents);
        relationships.extend(run.result.state.relationships);
        time.extend(run.result.state.time);
        actions.extend(run.result.actions);
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
        actions,
        results_title: program.results_title.clone(),
        results_subtitle: format!("{} weighted archetype aggregates", population.id),
        reports,
    })
}

fn weighted_summary_report(
    population: &WeightedPopulationDefinition,
    runs: &[ArchetypeRun<'_>],
    ticks: u64,
) -> DslResult<DslReport> {
    let first = runs.first().ok_or_else(|| {
        DslError::new(
            "EMPTY_WEIGHTED_POPULATION",
            population.line,
            "Weighted population has no archetype runs",
        )
    })?;
    let output_definitions = &first.definition.outputs;
    let total_population = runs
        .iter()
        .map(|run| run.weight as f64 * run.population_per_household as f64)
        .sum::<f64>();
    let mut values = BTreeMap::from([(
        "total_population".to_owned(),
        DslReportValue::Number(total_population),
    )]);
    let mut columns = vec![report_column(
        "total_population",
        "Total population",
        "integer",
        ReportMetric::Count,
    )];
    for output in output_definitions {
        let total_weight = runs.iter().map(|run| run.weight as f64).sum::<f64>();
        let mean = runs
            .iter()
            .map(|run| run.outputs[&output.id].mean * run.weight as f64)
            .sum::<f64>()
            / total_weight;
        values.insert(output.id.clone(), DslReportValue::Number(mean));
        columns.push(report_column(
            &output.id,
            &output.id,
            "decimal",
            output.metric.clone(),
        ));
        if output.spread {
            let variance = runs
                .iter()
                .map(|run| {
                    let summary = &run.outputs[&output.id];
                    run.weight as f64
                        * (summary.standard_deviation.powi(2) + (summary.mean - mean).powi(2))
                })
                .sum::<f64>()
                / total_weight;
            let id = format!("{}_sd", output.id);
            values.insert(id.clone(), DslReportValue::Number(variance.sqrt()));
            columns.push(report_column(&id, &id, "decimal", output.metric.clone()));
        }
    }
    Ok(DslReport {
        id: "weighted_summary".to_owned(),
        title: population.id.clone(),
        group_by: "all".to_owned(),
        display: "cards".to_owned(),
        record: "final".to_owned(),
        columns,
        snapshots: vec![DslReportSnapshot {
            tick: ticks,
            rows: vec![DslReportRow {
                group_id: population.id.clone(),
                values,
            }],
        }],
    })
}

fn archetype_report(runs: &[ArchetypeRun<'_>], ticks: u64) -> DslReport {
    let mut columns = vec![
        report_column("weight", "Household weight", "integer", ReportMetric::Count),
        report_column(
            "simulated_agents",
            "Simulated agents",
            "integer",
            ReportMetric::Count,
        ),
        report_column(
            "represented_population",
            "Represented population",
            "integer",
            ReportMetric::Count,
        ),
    ];
    if let Some(first) = runs.first() {
        for output in &first.definition.outputs {
            columns.push(report_column(
                &output.id,
                &output.id,
                "decimal",
                output.metric.clone(),
            ));
            if output.spread {
                let id = format!("{}_sd", output.id);
                columns.push(report_column(&id, &id, "decimal", output.metric.clone()));
            }
        }
    }
    let rows = runs
        .iter()
        .map(|run| {
            let mut values = BTreeMap::from([
                (
                    "weight".to_owned(),
                    DslReportValue::Number(run.weight as f64),
                ),
                (
                    "simulated_agents".to_owned(),
                    DslReportValue::Number(run.result.state.agents.len() as f64),
                ),
                (
                    "represented_population".to_owned(),
                    DslReportValue::Number(run.weight as f64 * run.population_per_household as f64),
                ),
            ]);
            for output in &run.definition.outputs {
                let summary = &run.outputs[&output.id];
                values.insert(output.id.clone(), DslReportValue::Number(summary.mean));
                if output.spread {
                    values.insert(
                        format!("{}_sd", output.id),
                        DslReportValue::Number(summary.standard_deviation),
                    );
                }
            }
            DslReportRow {
                group_id: run.definition.id.clone(),
                values,
            }
        })
        .collect();
    DslReport {
        id: "archetypes".to_owned(),
        title: "Archetypes".to_owned(),
        group_by: "archetype".to_owned(),
        display: "table".to_owned(),
        record: "final".to_owned(),
        columns,
        snapshots: vec![DslReportSnapshot { tick: ticks, rows }],
    }
}

fn merged_base_reports(program: &Program, runs: &[ArchetypeRun<'_>], ticks: u64) -> Vec<DslReport> {
    program
        .reports
        .iter()
        .filter(|definition| matches!(definition.group_by.as_str(), "place" | "agent_type"))
        .filter_map(|definition| merge_report(definition, runs, ticks))
        .collect()
}

fn merge_report(
    definition: &ReportDefinition,
    runs: &[ArchetypeRun<'_>],
    ticks: u64,
) -> Option<DslReport> {
    let group_ids = runs
        .iter()
        .filter_map(|run| {
            run.result
                .reports
                .iter()
                .find(|report| report.id == definition.id)
        })
        .filter_map(|report| report.snapshots.last())
        .flat_map(|snapshot| snapshot.rows.iter().map(|row| row.group_id.clone()))
        .collect::<BTreeSet<_>>();
    let count_column = definition
        .columns
        .iter()
        .find(|column| matches!(column.metric, ReportMetric::Count))
        .map(|column| column.id.as_str());
    let rows = group_ids
        .into_iter()
        .map(|group_id| {
            let weighted_rows = runs
                .iter()
                .filter_map(|run| {
                    let row = run
                        .result
                        .reports
                        .iter()
                        .find(|report| report.id == definition.id)?
                        .snapshots
                        .last()?
                        .rows
                        .iter()
                        .find(|row| row.group_id == group_id)?;
                    let simulated_count = count_column
                        .and_then(|id| row.values.get(id))
                        .and_then(report_number)
                        .unwrap_or(run.result.state.agents.len() as f64);
                    let represented_count = simulated_count * run.weight as f64
                        / run.definition.sample_households as f64;
                    let scale = run.weight as f64 / run.definition.sample_households as f64;
                    Some((row, represented_count, scale))
                })
                .collect::<Vec<_>>();
            let values = definition
                .columns
                .iter()
                .map(|column| {
                    let value = merge_column(column, &weighted_rows);
                    (column.id.clone(), value)
                })
                .collect();
            DslReportRow { group_id, values }
        })
        .collect::<Vec<_>>();
    (!rows.is_empty()).then(|| DslReport {
        id: definition.id.clone(),
        title: definition.title.clone(),
        group_by: definition.group_by.clone(),
        display: definition.display.clone(),
        record: "final".to_owned(),
        columns: definition.columns.clone(),
        snapshots: vec![DslReportSnapshot { tick: ticks, rows }],
    })
}

fn merge_column(
    column: &ReportColumnDefinition,
    rows: &[(&DslReportRow, f64, f64)],
) -> DslReportValue {
    if matches!(
        column.metric,
        ReportMetric::Count | ReportMetric::Sum { .. } | ReportMetric::ActionCount { .. }
    ) {
        return DslReportValue::Number(
            rows.iter()
                .map(|(row, represented, scale)| {
                    let value = row
                        .values
                        .get(&column.id)
                        .and_then(report_number)
                        .unwrap_or(0.0);
                    if matches!(column.metric, ReportMetric::Count) {
                        *represented
                    } else {
                        value * scale
                    }
                })
                .sum(),
        );
    }
    if matches!(column.metric, ReportMetric::ActionRates { .. }) {
        let keys = rows
            .iter()
            .filter_map(|(row, _, _)| row.values.get(&column.id))
            .filter_map(report_rates)
            .flat_map(|rates| rates.keys().cloned())
            .collect::<BTreeSet<_>>();
        return DslReportValue::Rates(
            keys.into_iter()
                .map(|key| {
                    let numerator = rows
                        .iter()
                        .map(|(row, represented, _)| {
                            row.values
                                .get(&column.id)
                                .and_then(report_rates)
                                .and_then(|rates| rates.get(&key))
                                .copied()
                                .unwrap_or(0.0)
                                * represented
                        })
                        .sum::<f64>();
                    let denominator = rows
                        .iter()
                        .map(|(_, represented, _)| represented)
                        .sum::<f64>();
                    (
                        key,
                        if denominator == 0.0 {
                            0.0
                        } else {
                            numerator / denominator
                        },
                    )
                })
                .collect(),
        );
    }
    let denominator = rows
        .iter()
        .map(|(_, represented, _)| represented)
        .sum::<f64>();
    DslReportValue::Number(if denominator == 0.0 {
        0.0
    } else {
        rows.iter()
            .map(|(row, represented, _)| {
                row.values
                    .get(&column.id)
                    .and_then(report_number)
                    .unwrap_or(0.0)
                    * represented
            })
            .sum::<f64>()
            / denominator
    })
}

fn report_number(value: &DslReportValue) -> Option<f64> {
    match value {
        DslReportValue::Number(value) => Some(*value),
        _ => None,
    }
}

fn report_rates(value: &DslReportValue) -> Option<&BTreeMap<String, f64>> {
    match value {
        DslReportValue::Rates(value) => Some(value),
        _ => None,
    }
}

fn report_column(
    id: &str,
    label: &str,
    format: &str,
    metric: ReportMetric,
) -> ReportColumnDefinition {
    ReportColumnDefinition {
        id: id.to_owned(),
        label: label.replace('_', " "),
        format: format.to_owned(),
        metric,
        line: 1,
    }
}

fn derived_seed(seed: u64, value: &str) -> u64 {
    value
        .as_bytes()
        .iter()
        .fold(seed ^ 0xcbf29ce484222325, |hash, byte| {
            (hash ^ u64::from(*byte)).wrapping_mul(0x100000001b3)
        })
}
