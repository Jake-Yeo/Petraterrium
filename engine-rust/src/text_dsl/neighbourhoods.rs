use super::archetypes::{MetricSummary, build_archetype_state, calculate_output_definitions};
use super::model::*;
use super::runtime::run_program;
use std::collections::BTreeMap;

pub(super) struct NeighbourhoodBuild {
    pub(super) program: Program,
    pub(super) state: DslRunState,
    pub(super) agent_archetypes: BTreeMap<String, String>,
}

pub fn run_neighbourhood(
    program: Program,
    neighbourhood_id: &str,
    seed: u64,
    ticks: u64,
) -> DslResult<DslRunResult> {
    let neighbourhood = program
        .neighbourhoods
        .iter()
        .find(|item| item.id == neighbourhood_id)
        .cloned()
        .ok_or_else(|| {
            DslError::new(
                "UNKNOWN_NEIGHBOURHOOD",
                1,
                format!("Unknown neighbourhood {neighbourhood_id}"),
            )
        })?;
    let record_actions = program.record_actions;
    let build = build_neighbourhood_state(&program, &neighbourhood, seed)?;
    let action_aggregates = build
        .program
        .actions
        .iter()
        .map(|action| (action.id.clone(), action.aggregate.clone()))
        .collect::<BTreeMap<_, _>>();
    let mut result = run_program(DslRunRequest::resume(
        build.program,
        seed,
        ticks,
        build.state,
    ))?;
    decorate_neighbourhood_result(
        &neighbourhood,
        &mut result,
        &build.agent_archetypes,
        &action_aggregates,
        ticks,
        record_actions,
    )?;
    Ok(result)
}

pub fn run_neighbourhood_monolith(
    program: Program,
    neighbourhood_id: &str,
    seed: u64,
    ticks: u64,
) -> DslResult<DslRunResult> {
    let neighbourhood = program
        .neighbourhoods
        .iter()
        .find(|item| item.id == neighbourhood_id)
        .cloned()
        .ok_or_else(|| {
            DslError::new(
                "UNKNOWN_NEIGHBOURHOOD",
                1,
                format!("Unknown neighbourhood {neighbourhood_id}"),
            )
        })?;
    let build = build_neighbourhood_state(&program, &neighbourhood, seed)?;
    run_program(DslRunRequest::resume(
        build.program,
        seed,
        ticks,
        build.state,
    ))
}

pub fn run_weighted_neighbourhood_population(
    program: Program,
    population_id: &str,
    seed: u64,
    ticks: u64,
) -> DslResult<DslRunResult> {
    let population = program
        .neighbourhood_populations
        .iter()
        .find(|item| item.id == population_id)
        .cloned()
        .ok_or_else(|| {
            DslError::new(
                "UNKNOWN_NEIGHBOURHOOD_POPULATION",
                1,
                format!("Unknown neighbourhood population {population_id}"),
            )
        })?;
    let mut runs = Vec::new();
    for entry in &population.entries {
        runs.push((
            entry,
            run_neighbourhood(
                program.clone(),
                &entry.neighbourhood,
                derived_seed(seed, &entry.neighbourhood),
                ticks,
            )?,
        ));
    }
    let first_report = runs
        .first()
        .and_then(|(_, result)| {
            result
                .reports
                .iter()
                .find(|report| report.id == "neighbourhoods")
        })
        .ok_or_else(|| {
            DslError::new(
                "EMPTY_NEIGHBOURHOOD_POPULATION",
                population.line,
                "Neighbourhood population produced no reports",
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
    for column in &output_columns {
        let mean = runs
            .iter()
            .map(|(entry, result)| entry.weight as f64 * neighbourhood_value(result, &column.id))
            .sum::<f64>()
            / total_weight;
        summary_values.insert(column.id.clone(), DslReportValue::Number(mean));
        summary_columns.push(column.clone());
        let sd_id = format!("{}_sd", column.id);
        if first_report.columns.iter().any(|item| item.id == sd_id) {
            let variance = runs
                .iter()
                .map(|(entry, result)| {
                    let value = neighbourhood_value(result, &column.id);
                    let sd = neighbourhood_value(result, &sd_id);
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
    let summary = DslReport {
        id: "neighbourhood_population_summary".to_owned(),
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
        results_subtitle: format!("{} weighted neighbourhood aggregates", population.id),
        reports: vec![summary],
    })
}

fn neighbourhood_value(result: &DslRunResult, id: &str) -> f64 {
    result
        .reports
        .iter()
        .find(|report| report.id == "neighbourhoods")
        .and_then(|report| report.snapshots.last())
        .and_then(|snapshot| snapshot.rows.first())
        .and_then(|row| row.values.get(id))
        .and_then(|value| match value {
            DslReportValue::Number(value) => Some(*value),
            _ => None,
        })
        .unwrap_or(0.0)
}

pub(super) fn decorate_neighbourhood_result(
    neighbourhood: &NeighbourhoodDefinition,
    result: &mut DslRunResult,
    agent_archetypes: &BTreeMap<String, String>,
    action_aggregates: &BTreeMap<String, String>,
    ticks: u64,
    record_actions: bool,
) -> DslResult<()> {
    let outputs = calculate_output_definitions(&neighbourhood.outputs, &result)?;
    result.reports.insert(
        0,
        neighbourhood_report(neighbourhood, &outputs, result, ticks),
    );
    result.reports.push(cross_archetype_report(
        result,
        agent_archetypes,
        action_aggregates,
        ticks,
    ));
    result.results_subtitle = format!("{} neighbourhood aggregates", neighbourhood.id);
    if !record_actions {
        result.actions.clear();
    }
    Ok(())
}

pub(super) fn build_neighbourhood_state(
    program: &Program,
    neighbourhood: &NeighbourhoodDefinition,
    seed: u64,
) -> DslResult<NeighbourhoodBuild> {
    let archetypes = program
        .archetypes
        .iter()
        .map(|item| (item.id.as_str(), item))
        .collect::<BTreeMap<_, _>>();
    let allocations = household_allocations(neighbourhood, &archetypes);
    let mut combined = program.clone();
    combined.agents.clear();
    combined.decisions.clear();
    combined.actions.clear();
    combined.archetypes.clear();
    combined.weighted_populations.clear();
    combined.neighbourhoods.clear();
    combined.neighbourhood_populations.clear();
    combined.aggregate_functions.clear();
    combined.population.child_generation = None;
    combined.record_actions = true;
    let mut agents = Vec::new();
    let mut relationships = Vec::new();
    let mut time = Vec::new();
    let mut agent_archetypes = BTreeMap::new();
    for entry in &neighbourhood.households {
        let definition = archetypes[entry.archetype.as_str()];
        let mut sampled_definition = definition.clone();
        sampled_definition.sample_households = allocations[entry.archetype.as_str()];
        let (prepared, mut state, _) = build_archetype_state(
            program,
            &sampled_definition,
            derived_seed(seed, &entry.archetype),
        )?;
        namespace_program(&mut combined, &prepared, &entry.archetype);
        for agent in &mut state.agents {
            agent.agent_type = namespaced(&entry.archetype, &agent.agent_type);
            agent.current_decision = namespaced(&entry.archetype, &agent.current_decision);
            agent_archetypes.insert(agent.id.clone(), entry.archetype.clone());
        }
        agents.extend(state.agents);
        relationships.extend(state.relationships);
        time.extend(state.time);
    }
    let state = DslRunState {
        completed_ticks: 0,
        agents,
        places: program
            .places
            .iter()
            .filter(|place| neighbourhood.places.contains(&place.id))
            .map(|place| DslPlaceState {
                id: place.id.clone(),
                states: place.states.clone(),
            })
            .collect(),
        relationships,
        time,
    };
    Ok(NeighbourhoodBuild {
        program: combined,
        state,
        agent_archetypes,
    })
}

fn household_allocations(
    neighbourhood: &NeighbourhoodDefinition,
    archetypes: &BTreeMap<&str, &ArchetypeDefinition>,
) -> BTreeMap<String, usize> {
    let total_samples = neighbourhood
        .households
        .iter()
        .map(|entry| archetypes[entry.archetype.as_str()].sample_households)
        .sum::<usize>();
    let total_weight = neighbourhood
        .households
        .iter()
        .map(|entry| entry.weight)
        .sum::<u64>();
    let mut allocations = neighbourhood
        .households
        .iter()
        .map(|entry| {
            let exact = total_samples as f64 * entry.weight as f64 / total_weight as f64;
            (
                entry.archetype.clone(),
                exact.floor().max(1.0) as usize,
                exact.fract(),
            )
        })
        .collect::<Vec<_>>();
    let assigned = allocations
        .iter()
        .map(|(_, count, _)| *count)
        .sum::<usize>();
    let mut remaining = total_samples.saturating_sub(assigned);
    allocations.sort_by(|left, right| {
        right
            .2
            .total_cmp(&left.2)
            .then_with(|| left.0.cmp(&right.0))
    });
    for (_, count, _) in &mut allocations {
        if remaining == 0 {
            break;
        }
        *count += 1;
        remaining -= 1;
    }
    allocations
        .into_iter()
        .map(|(id, count, _)| (id, count))
        .collect()
}

fn namespace_program(target: &mut Program, source: &Program, namespace: &str) {
    target
        .agents
        .extend(source.agents.iter().cloned().map(|mut agent| {
            agent.id = namespaced(namespace, &agent.id);
            agent.parent = agent.parent.map(|parent| namespaced(namespace, &parent));
            agent.routine = namespaced(namespace, &agent.routine);
            agent
        }));
    target
        .decisions
        .extend(source.decisions.iter().cloned().map(|mut decision| {
            decision.id = namespaced(namespace, &decision.id);
            for branch in &mut decision.branches {
                branch.action = namespaced(namespace, &branch.action);
            }
            decision
        }));
    target
        .actions
        .extend(source.actions.iter().cloned().map(|mut action| {
            action.id = namespaced(namespace, &action.id);
            for outcome in &mut action.outcomes {
                outcome.next_decision = outcome
                    .next_decision
                    .take()
                    .map(|decision| namespaced(namespace, &decision));
                outcome.target_next_decision = outcome
                    .target_next_decision
                    .take()
                    .map(|decision| namespaced(namespace, &decision));
            }
            action
        }));
}

fn neighbourhood_report(
    neighbourhood: &NeighbourhoodDefinition,
    outputs: &BTreeMap<String, MetricSummary>,
    result: &DslRunResult,
    ticks: u64,
) -> DslReport {
    let mut columns = vec![ReportColumnDefinition {
        id: "population".to_owned(),
        label: "Population".to_owned(),
        format: "integer".to_owned(),
        metric: ReportMetric::Count,
        line: neighbourhood.line,
    }];
    let mut values = BTreeMap::from([(
        "population".to_owned(),
        DslReportValue::Number(result.state.agents.len() as f64),
    )]);
    for output in &neighbourhood.outputs {
        let summary = &outputs[&output.id];
        columns.push(ReportColumnDefinition {
            id: output.id.clone(),
            label: output.id.replace('_', " "),
            format: "decimal".to_owned(),
            metric: output.metric.clone(),
            line: output.line,
        });
        values.insert(output.id.clone(), DslReportValue::Number(summary.mean));
        if output.spread {
            let id = format!("{}_sd", output.id);
            columns.push(ReportColumnDefinition {
                id: id.clone(),
                label: id.replace('_', " "),
                format: "decimal".to_owned(),
                metric: output.metric.clone(),
                line: output.line,
            });
            values.insert(id, DslReportValue::Number(summary.standard_deviation));
        }
    }
    DslReport {
        id: "neighbourhoods".to_owned(),
        title: "Neighbourhood archetypes".to_owned(),
        group_by: "neighbourhood".to_owned(),
        display: "table".to_owned(),
        record: "final".to_owned(),
        columns,
        snapshots: vec![DslReportSnapshot {
            tick: ticks,
            rows: vec![DslReportRow {
                group_id: neighbourhood.id.clone(),
                values,
            }],
        }],
    }
}

fn cross_archetype_report(
    result: &DslRunResult,
    agent_archetypes: &BTreeMap<String, String>,
    action_aggregates: &BTreeMap<String, String>,
    ticks: u64,
) -> DslReport {
    let mut counts = BTreeMap::<(String, String), BTreeMap<String, u64>>::new();
    for action in &result.actions {
        let Some(target_id) = &action.target_id else {
            continue;
        };
        let Some(source) = agent_archetypes.get(&action.agent_id) else {
            continue;
        };
        let Some(target) = agent_archetypes.get(target_id) else {
            continue;
        };
        if source == target {
            continue;
        }
        let aggregate = action_aggregates
            .get(&action.action)
            .cloned()
            .unwrap_or_else(|| action.action.clone());
        *counts
            .entry((source.clone(), target.clone()))
            .or_default()
            .entry(aggregate)
            .or_default() += 1;
    }
    let population = result.state.agents.len().max(1) as f64;
    let rows = counts
        .into_iter()
        .map(|((source, target), counts)| {
            let total = counts.values().sum::<u64>();
            DslReportRow {
                group_id: format!("{source} → {target}"),
                values: BTreeMap::from([
                    ("count".to_owned(), DslReportValue::Number(total as f64)),
                    (
                        "rates_per_1000".to_owned(),
                        DslReportValue::Rates(
                            counts
                                .into_iter()
                                .map(|(action, count)| (action, count as f64 / population * 1000.0))
                                .collect(),
                        ),
                    ),
                    (
                        "selection_index".to_owned(),
                        DslReportValue::Text("place_membership".to_owned()),
                    ),
                ]),
            }
        })
        .collect();
    DslReport {
        id: "cross_archetype_interactions".to_owned(),
        title: "Cross-archetype interactions".to_owned(),
        group_by: "archetype_pair".to_owned(),
        display: "table".to_owned(),
        record: "final".to_owned(),
        columns: vec![
            ReportColumnDefinition {
                id: "count".to_owned(),
                label: "Interactions".to_owned(),
                format: "integer".to_owned(),
                metric: ReportMetric::Count,
                line: 1,
            },
            ReportColumnDefinition {
                id: "rates_per_1000".to_owned(),
                label: "Rates / 1,000".to_owned(),
                format: "action_rates".to_owned(),
                metric: ReportMetric::ActionRates {
                    per: 1000.0,
                    window: "run".to_owned(),
                },
                line: 1,
            },
            ReportColumnDefinition {
                id: "selection_index".to_owned(),
                label: "Target index".to_owned(),
                format: "number".to_owned(),
                metric: ReportMetric::Count,
                line: 1,
            },
        ],
        snapshots: vec![DslReportSnapshot { tick: ticks, rows }],
    }
}

fn namespaced(namespace: &str, id: &str) -> String {
    format!("{namespace}__{id}")
}

fn derived_seed(seed: u64, value: &str) -> u64 {
    value
        .as_bytes()
        .iter()
        .fold(seed ^ 0xcbf29ce484222325, |hash, byte| {
            (hash ^ u64::from(*byte)).wrapping_mul(0x100000001b3)
        })
}
