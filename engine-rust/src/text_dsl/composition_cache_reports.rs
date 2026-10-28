use super::composition_cache::CachedFlowPoint;
use super::model::*;
use std::collections::{BTreeMap, BTreeSet};

pub(super) fn cached_reports(
    composition: &CompositionDefinition,
    endpoint: &AggregateTimePoint,
    flows: &[CachedFlowPoint],
    cache_tree: &CompositionCacheMetadata,
    days: u32,
    iterations: u32,
    change_percent: f64,
) -> Vec<DslReport> {
    vec![
        cached_output_report(composition, endpoint, days),
        cached_flow_report(flows, days),
        cached_interaction_report(flows, days),
        cache_hierarchy_report(cache_tree, days),
        feedback_report(iterations, change_percent, days),
    ]
}

fn cached_output_report(
    composition: &CompositionDefinition,
    endpoint: &AggregateTimePoint,
    days: u32,
) -> DslReport {
    let mut columns = Vec::new();
    let mut values = BTreeMap::new();
    for output in &composition.outputs {
        let Some(summary) = endpoint.outputs.get(&output.id) else {
            continue;
        };
        columns.push(report_column(&output.id, "decimal"));
        values.insert(output.id.clone(), DslReportValue::Number(summary.mean));
        if output.spread {
            let id = format!("{}_sd", output.id);
            columns.push(report_column(&id, "decimal"));
            values.insert(id, DslReportValue::Number(summary.standard_deviation));
        }
    }
    DslReport {
        id: "aggregate_outputs".to_owned(),
        title: format!("{} cached composition outputs", composition.id),
        group_by: composition.level.clone(),
        display: "table".to_owned(),
        record: "cached".to_owned(),
        columns,
        snapshots: vec![DslReportSnapshot {
            tick: u64::from(days),
            rows: vec![DslReportRow {
                group_id: composition.id.clone(),
                values,
            }],
        }],
    }
}

fn cached_flow_report(flows: &[CachedFlowPoint], days: u32) -> DslReport {
    let snapshots = flows
        .iter()
        .map(|flow| flow.day)
        .collect::<BTreeSet<_>>()
        .into_iter()
        .map(|day| DslReportSnapshot {
            tick: u64::from(day),
            rows: flows
                .iter()
                .filter(|flow| flow.day == day)
                .map(flow_row)
                .collect(),
        })
        .collect();
    DslReport {
        id: "composition_flows".to_owned(),
        title: "Cached composition boundary flows".to_owned(),
        group_by: "flow".to_owned(),
        display: "table".to_owned(),
        record: "daily".to_owned(),
        columns: vec![
            report_column("composition", "number"),
            report_column("source", "number"),
            report_column("target", "number"),
            report_column("effect", "number"),
            report_column("count", "decimal"),
            report_column("rate", "percent"),
        ],
        snapshots: if flows.is_empty() {
            vec![DslReportSnapshot {
                tick: u64::from(days),
                rows: Vec::new(),
            }]
        } else {
            snapshots
        },
    }
}

fn flow_row(flow: &CachedFlowPoint) -> DslReportRow {
    DslReportRow {
        group_id: format!("{}:{}", flow.composition, flow.id),
        values: BTreeMap::from([
            (
                "composition".to_owned(),
                DslReportValue::Text(flow.composition.clone()),
            ),
            (
                "source".to_owned(),
                DslReportValue::Text(flow.source.clone()),
            ),
            (
                "target".to_owned(),
                DslReportValue::Text(flow.target.clone()),
            ),
            (
                "effect".to_owned(),
                DslReportValue::Text(flow.effect.clone()),
            ),
            ("count".to_owned(), DslReportValue::Number(flow.count)),
            ("rate".to_owned(), DslReportValue::Number(flow.rate)),
        ]),
    }
}

fn cached_interaction_report(flows: &[CachedFlowPoint], days: u32) -> DslReport {
    let rows = flows
        .iter()
        .filter(|flow| flow.effect == "visit")
        .map(|flow| DslReportRow {
            group_id: format!("{} → {}", flow.source, flow.target),
            values: BTreeMap::from([
                ("count".to_owned(), DslReportValue::Number(flow.count)),
                ("rate".to_owned(), DslReportValue::Number(flow.rate)),
            ]),
        })
        .collect();
    DslReport {
        id: "cross_composition_interactions".to_owned(),
        title: "Cached cross-composition interactions".to_owned(),
        group_by: "composition_pair".to_owned(),
        display: "table".to_owned(),
        record: "cached".to_owned(),
        columns: vec![
            report_column("count", "decimal"),
            report_column("rate", "percent"),
        ],
        snapshots: vec![DslReportSnapshot {
            tick: u64::from(days),
            rows,
        }],
    }
}

fn cache_hierarchy_report(tree: &CompositionCacheMetadata, days: u32) -> DslReport {
    let mut rows = Vec::new();
    flatten_cache_tree(tree, &mut rows);
    DslReport {
        id: "cache_hierarchy".to_owned(),
        title: "Composition cache hierarchy".to_owned(),
        group_by: "cache_branch".to_owned(),
        display: "table".to_owned(),
        record: "cached".to_owned(),
        columns: vec![
            report_column("version", "integer"),
            report_column("status", "number"),
            report_column("detailed", "number"),
            report_column("agent_ticks", "integer"),
            report_column("original_learning_ticks", "integer"),
            report_column("dsl_hash", "number"),
            report_column("inputs_hash", "number"),
            report_column("valid_from", "integer"),
            report_column("valid_until", "integer"),
            report_column("seed", "integer"),
            report_column("invalidation", "number"),
        ],
        snapshots: vec![DslReportSnapshot {
            tick: u64::from(days),
            rows,
        }],
    }
}

fn flatten_cache_tree(tree: &CompositionCacheMetadata, rows: &mut Vec<DslReportRow>) {
    rows.push(DslReportRow {
        group_id: tree.function_id.clone(),
        values: BTreeMap::from([
            (
                "version".to_owned(),
                DslReportValue::Number(f64::from(tree.version)),
            ),
            (
                "status".to_owned(),
                DslReportValue::Text(if tree.cached { "cached" } else { "updated" }.to_owned()),
            ),
            (
                "detailed".to_owned(),
                DslReportValue::Text(tree.detailed.to_string()),
            ),
            (
                "agent_ticks".to_owned(),
                DslReportValue::Number(tree.evaluation_agent_ticks as f64),
            ),
            (
                "original_learning_ticks".to_owned(),
                DslReportValue::Number(tree.original_learning_ticks as f64),
            ),
            (
                "dsl_hash".to_owned(),
                DslReportValue::Text(tree.dsl_source_hash.clone()),
            ),
            (
                "inputs_hash".to_owned(),
                DslReportValue::Text(tree.inputs_hash.clone()),
            ),
            (
                "valid_from".to_owned(),
                DslReportValue::Number(f64::from(tree.valid_from)),
            ),
            (
                "valid_until".to_owned(),
                DslReportValue::Number(f64::from(tree.valid_until)),
            ),
            ("seed".to_owned(), DslReportValue::Number(tree.seed as f64)),
            (
                "invalidation".to_owned(),
                DslReportValue::Text(
                    tree.invalidation_reason
                        .clone()
                        .unwrap_or_else(|| "none".to_owned()),
                ),
            ),
        ]),
    });
    for child in &tree.children {
        flatten_cache_tree(child, rows);
    }
}

fn feedback_report(iterations: u32, change_percent: f64, days: u32) -> DslReport {
    DslReport {
        id: "composition_feedback".to_owned(),
        title: "Composition feedback convergence".to_owned(),
        group_by: "feedback".to_owned(),
        display: "cards".to_owned(),
        record: "cached".to_owned(),
        columns: vec![
            report_column("iterations", "integer"),
            report_column("change_percent", "percent"),
        ],
        snapshots: vec![DslReportSnapshot {
            tick: u64::from(days),
            rows: vec![DslReportRow {
                group_id: "final".to_owned(),
                values: BTreeMap::from([
                    (
                        "iterations".to_owned(),
                        DslReportValue::Number(f64::from(iterations)),
                    ),
                    (
                        "change_percent".to_owned(),
                        DslReportValue::Number(change_percent),
                    ),
                ]),
            }],
        }],
    }
}

fn report_column(id: &str, format: &str) -> ReportColumnDefinition {
    ReportColumnDefinition {
        id: id.to_owned(),
        label: id.replace('_', " "),
        format: format.to_owned(),
        metric: ReportMetric::Count,
        line: 1,
    }
}
