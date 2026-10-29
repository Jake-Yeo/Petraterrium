use super::archetypes::{MetricSummary, calculate_output_definitions};
use super::composition_allocations::allocation_report;
use super::composition_formulas::{apply_formula_outputs, static_formula_children};
use super::model::*;
use std::collections::{BTreeMap, BTreeSet};

pub(super) fn decorate_composition_result(
    program: &Program,
    composition: &CompositionDefinition,
    result: &mut DslRunResult,
    agent_groups: &BTreeMap<String, String>,
    action_aggregates: &BTreeMap<String, String>,
    ticks: u64,
    tick_hours: f64,
    record_actions: bool,
    recorded_actions: &BTreeSet<String>,
    formula_inputs: &BTreeMap<String, f64>,
) -> DslResult<()> {
    let outputs = calculate_composition_outputs(
        program,
        composition,
        result,
        composition.represented_population.unwrap_or(0) as f64,
        formula_inputs,
    )?;
    result
        .reports
        .insert(0, composition_report(composition, &outputs, result, ticks));
    result.reports.push(cross_group_report(
        result,
        agent_groups,
        action_aggregates,
        ticks,
    ));
    result.reports.push(child_composition_report(
        composition,
        result,
        agent_groups,
        action_aggregates,
        ticks,
        tick_hours,
    )?);
    if let Some(report) = allocation_report(program, composition, ticks)? {
        result.reports.push(report);
    }
    if composition.report_descendants {
        result
            .reports
            .push(composition_hierarchy_report(program, composition, ticks)?);
    }
    result.results_subtitle = format!("{} {} aggregates", composition.id, composition.level);
    if !record_actions {
        result
            .actions
            .retain(|record| recorded_actions.contains(&record.action));
    }
    Ok(())
}

fn composition_hierarchy_report(
    program: &Program,
    root: &CompositionDefinition,
    tick: u64,
) -> DslResult<DslReport> {
    let mut rows = Vec::new();
    let mut output_ids = BTreeSet::new();
    collect_hierarchy_rows(program, root, &mut rows, &mut output_ids)?;
    let mut columns = vec![ReportColumnDefinition {
        id: "level".to_owned(),
        label: "Level".to_owned(),
        format: "number".to_owned(),
        metric: ReportMetric::Count,
        line: root.line,
    }];
    columns.extend(output_ids.into_iter().map(|id| ReportColumnDefinition {
        label: id.replace('_', " "),
        id,
        format: "decimal".to_owned(),
        metric: ReportMetric::Count,
        line: root.line,
    }));
    Ok(DslReport {
        id: "composition_hierarchy".to_owned(),
        title: format!("{} hierarchy outputs", root.id),
        group_by: "composition".to_owned(),
        display: "table".to_owned(),
        record: "final".to_owned(),
        columns,
        snapshots: vec![DslReportSnapshot { tick, rows }],
    })
}

fn collect_hierarchy_rows(
    program: &Program,
    parent: &CompositionDefinition,
    rows: &mut Vec<DslReportRow>,
    output_ids: &mut BTreeSet<String>,
) -> DslResult<()> {
    for entry in &parent.entries {
        let Some(child) = program
            .compositions
            .iter()
            .find(|composition| composition.id == entry.child)
        else {
            continue;
        };
        let children = static_formula_children(program, child)?;
        let mut outputs = BTreeMap::new();
        apply_formula_outputs(child, &BTreeMap::new(), &children, &mut outputs)?;
        let mut values = BTreeMap::from([(
            "level".to_owned(),
            DslReportValue::Text(child.level.clone()),
        )]);
        for (id, summary) in outputs {
            output_ids.insert(id.clone());
            values.insert(id, DslReportValue::Number(summary.mean));
        }
        rows.push(DslReportRow {
            group_id: child.id.clone(),
            values,
        });
        collect_hierarchy_rows(program, child, rows, output_ids)?;
    }
    Ok(())
}

fn composition_report(
    composition: &CompositionDefinition,
    outputs: &BTreeMap<String, MetricSummary>,
    result: &DslRunResult,
    ticks: u64,
) -> DslReport {
    let mut columns = vec![ReportColumnDefinition {
        id: "population".to_owned(),
        label: "Population".to_owned(),
        format: "integer".to_owned(),
        metric: ReportMetric::Count,
        line: composition.line,
    }];
    let mut values = BTreeMap::from([(
        "population".to_owned(),
        DslReportValue::Number(result.state.agents.len() as f64),
    )]);
    for output in &composition.outputs {
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
        id: "compositions".to_owned(),
        title: "Compositions".to_owned(),
        group_by: composition.level.clone(),
        display: "table".to_owned(),
        record: "final".to_owned(),
        columns,
        snapshots: vec![DslReportSnapshot {
            tick: ticks,
            rows: vec![DslReportRow {
                group_id: composition.id.clone(),
                values,
            }],
        }],
    }
}

fn child_composition_report(
    composition: &CompositionDefinition,
    result: &DslRunResult,
    agent_groups: &BTreeMap<String, String>,
    action_aggregates: &BTreeMap<String, String>,
    ticks: u64,
    tick_hours: f64,
) -> DslResult<DslReport> {
    let mut columns = vec![ReportColumnDefinition {
        id: "population".to_owned(),
        label: "Population".to_owned(),
        format: "integer".to_owned(),
        metric: ReportMetric::Count,
        line: composition.line,
    }];
    for output in &composition.outputs {
        columns.push(ReportColumnDefinition {
            id: output.id.clone(),
            label: output.id.replace('_', " "),
            format: "decimal".to_owned(),
            metric: output.metric.clone(),
            line: output.line,
        });
        if output.spread {
            let id = format!("{}_sd", output.id);
            columns.push(ReportColumnDefinition {
                id: id.clone(),
                label: id.replace('_', " "),
                format: "decimal".to_owned(),
                metric: output.metric.clone(),
                line: output.line,
            });
        }
    }
    let mut rows = Vec::new();
    for entry in &composition.entries {
        let ids = result
            .state
            .agents
            .iter()
            .filter(|agent| agent_groups.get(&agent.id) == Some(&entry.child))
            .map(|agent| agent.id.as_str())
            .collect::<BTreeSet<_>>();
        let filtered = filtered_result(result, &ids);
        let mut values = BTreeMap::from([(
            "population".to_owned(),
            DslReportValue::Number(filtered.state.agents.len() as f64),
        )]);
        for output in &composition.outputs {
            let summary = if matches!(output.metric, ReportMetric::RepresentedCount) {
                Some(MetricSummary {
                    mean: 0.0,
                    standard_deviation: 0.0,
                })
            } else if let ReportMetric::ActionCount { aggregate, window }
            | ReportMetric::ActionRate { aggregate, window } = &output.metric
            {
                let first_tick = match window.as_str() {
                    "tick" => ticks,
                    "day" => ticks.saturating_sub((24.0 / tick_hours).round() as u64 - 1),
                    _ => 0,
                };
                let count = filtered
                    .actions
                    .iter()
                    .filter(|action| action.tick >= first_tick)
                    .filter(|action| {
                        action_aggregates.get(&action.action).map(String::as_str)
                            == Some(aggregate.as_str())
                    })
                    .count() as f64;
                let value = if matches!(output.metric, ReportMetric::ActionRate { .. }) {
                    count / filtered.state.agents.len().max(1) as f64
                } else {
                    count
                };
                Some(MetricSummary {
                    mean: value,
                    standard_deviation: 0.0,
                })
            } else {
                match calculate_output_definitions(std::slice::from_ref(output), &filtered) {
                    Ok(mut output_values) => output_values.remove(&output.id),
                    Err(error)
                        if matches!(
                            error.code.as_str(),
                            "EMPTY_ARCHETYPE_METRIC" | "EMPTY_AGGREGATE_METRIC"
                        ) =>
                    {
                        None
                    }
                    Err(error) => return Err(error),
                }
            };
            if let Some(summary) = summary {
                values.insert(output.id.clone(), DslReportValue::Number(summary.mean));
                if output.spread {
                    values.insert(
                        format!("{}_sd", output.id),
                        DslReportValue::Number(summary.standard_deviation),
                    );
                }
            } else {
                values.insert(
                    output.id.clone(),
                    DslReportValue::Text("not_applicable".to_owned()),
                );
                if output.spread {
                    values.insert(
                        format!("{}_sd", output.id),
                        DslReportValue::Text("not_applicable".to_owned()),
                    );
                }
            }
        }
        rows.push(DslReportRow {
            group_id: entry.child.clone(),
            values,
        });
    }
    Ok(DslReport {
        id: "composition_children".to_owned(),
        title: format!("{} children", composition.id),
        group_by: "composition_child".to_owned(),
        display: "table".to_owned(),
        record: "final".to_owned(),
        columns,
        snapshots: vec![DslReportSnapshot { tick: ticks, rows }],
    })
}

fn calculate_composition_outputs(
    program: &Program,
    composition: &CompositionDefinition,
    result: &DslRunResult,
    represented_population: f64,
    formula_inputs: &BTreeMap<String, f64>,
) -> DslResult<BTreeMap<String, MetricSummary>> {
    let standard = composition
        .outputs
        .iter()
        .filter(|output| {
            !matches!(
                output.metric,
                ReportMetric::RepresentedCount
                    | ReportMetric::RepresentedTotal
                    | ReportMetric::Formula { .. }
            )
        })
        .cloned()
        .collect::<Vec<_>>();
    let mut outputs = calculate_output_definitions(&standard, result)?;
    for output in &composition.outputs {
        if matches!(output.metric, ReportMetric::RepresentedCount) {
            outputs.insert(
                output.id.clone(),
                MetricSummary {
                    mean: represented_population,
                    standard_deviation: 0.0,
                },
            );
        } else if matches!(output.metric, ReportMetric::RepresentedTotal) {
            outputs.insert(
                output.id.clone(),
                MetricSummary {
                    mean: composition.authoritative_total.unwrap_or(0) as f64,
                    standard_deviation: 0.0,
                },
            );
        }
    }
    let children = static_formula_children(program, composition)?;
    apply_formula_outputs(composition, formula_inputs, &children, &mut outputs)?;
    Ok(outputs)
}

fn filtered_result(result: &DslRunResult, ids: &BTreeSet<&str>) -> DslRunResult {
    let selected_indices = result
        .state
        .agents
        .iter()
        .enumerate()
        .filter(|(_, agent)| ids.contains(agent.id.as_str()))
        .map(|(index, _)| index)
        .collect::<Vec<_>>();
    DslRunResult {
        completed_ticks: result.completed_ticks,
        state: DslRunState {
            completed_ticks: result.state.completed_ticks,
            agents: selected_indices
                .iter()
                .map(|index| result.state.agents[*index].clone())
                .collect(),
            places: result.state.places.clone(),
            relationships: result
                .state
                .relationships
                .iter()
                .filter(|relationship| {
                    ids.contains(relationship.source_id.as_str())
                        && ids.contains(relationship.target_id.as_str())
                })
                .cloned()
                .collect(),
            time: selected_indices
                .iter()
                .map(|index| result.state.time[*index].clone())
                .collect(),
        },
        actions: result
            .actions
            .iter()
            .filter(|action| ids.contains(action.agent_id.as_str()))
            .cloned()
            .collect(),
        results_title: result.results_title.clone(),
        results_subtitle: result.results_subtitle.clone(),
        reports: result.reports.clone(),
    }
}

fn cross_group_report(
    result: &DslRunResult,
    agent_groups: &BTreeMap<String, String>,
    action_aggregates: &BTreeMap<String, String>,
    ticks: u64,
) -> DslReport {
    let mut counts = BTreeMap::<(String, String), BTreeMap<String, u64>>::new();
    for action in &result.actions {
        let Some(target_id) = &action.target_id else {
            continue;
        };
        let Some(source) = agent_groups.get(&action.agent_id) else {
            continue;
        };
        let Some(target) = agent_groups.get(target_id) else {
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
        .collect::<Vec<_>>();
    DslReport {
        id: "cross_composition_interactions".to_owned(),
        title: "Cross-composition interactions".to_owned(),
        group_by: "composition_pair".to_owned(),
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
