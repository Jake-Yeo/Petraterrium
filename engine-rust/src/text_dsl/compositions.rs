use super::composition_build::{build_composition_state, derived_seed};
use super::composition_reports::decorate_composition_result;
use super::model::*;
use super::runtime::run_program;
use std::collections::BTreeMap;

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
    let mut result = run_program(DslRunRequest::resume(
        build.program,
        seed,
        ticks,
        build.state,
    ))?;
    decorate_composition_result(
        &composition,
        &mut result,
        &build.agent_groups,
        &action_aggregates,
        &build.flows,
        ticks,
        tick_hours,
        record_actions,
    )?;
    Ok(result)
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
