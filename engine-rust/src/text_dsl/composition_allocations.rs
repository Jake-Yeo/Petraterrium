use super::model::*;
use std::collections::BTreeMap;

#[derive(Clone)]
pub(super) struct CompositionAllocation {
    pub(super) path: String,
    pub(super) weight: f64,
    pub(super) represented_count: u64,
    pub(super) simulated_count: u64,
}

struct AllocationLeaf {
    path: String,
    weight: f64,
    declared_count: Option<u64>,
    line: usize,
}

pub(super) fn validate_authoritative_allocations(program: &Program) -> DslResult<()> {
    let compositions = program
        .compositions
        .iter()
        .map(|composition| (composition.id.as_str(), composition))
        .collect::<BTreeMap<_, _>>();
    for root in program
        .compositions
        .iter()
        .filter(|composition| composition.authoritative_total.is_some())
    {
        let total = root.authoritative_total.unwrap();
        let sample_budget = root.sample_budget.ok_or_else(|| {
            DslError::new(
                "MISSING_SAMPLE_BUDGET",
                root.line,
                "Authoritative allocation needs a sample budget",
            )
        })?;
        if total == 0 {
            return Err(DslError::new(
                "INVALID_AUTHORITATIVE_TOTAL",
                root.line,
                "Authoritative total must be positive",
            ));
        }
        if sample_budget == 0 || sample_budget > total {
            return Err(DslError::new(
                "INVALID_SAMPLE_BUDGET",
                root.line,
                "Sample budget must be positive and no larger than the authoritative total",
            ));
        }
        let leaves = allocation_leaves(root, &compositions)?;
        let represented = largest_remainders(
            total,
            &leaves
                .iter()
                .map(|leaf| (leaf.path.clone(), leaf.weight))
                .collect::<Vec<_>>(),
        );
        let declared = leaves
            .iter()
            .filter_map(|leaf| leaf.declared_count.map(|count| (leaf, count)))
            .collect::<Vec<_>>();
        if !declared.is_empty() {
            if declared.len() != leaves.len()
                || declared.iter().map(|(_, count)| count).sum::<u64>() != total
            {
                return Err(DslError::new(
                    "DECLARED_ALLOCATION_TOTAL_MISMATCH",
                    declared.first().map_or(root.line, |(leaf, _)| leaf.line),
                    "Declared leaf counts must cover every leaf and sum to the authoritative total",
                ));
            }
            for (leaf, count) in declared {
                if represented[&leaf.path] != count {
                    return Err(DslError::new(
                        "DECLARED_ALLOCATION_TOTAL_MISMATCH",
                        leaf.line,
                        format!(
                            "Declared count for {} is {}, derived count is {}",
                            leaf.path, count, represented[&leaf.path]
                        ),
                    ));
                }
            }
        }
    }
    Ok(())
}

pub(super) fn composition_allocations(
    program: &Program,
    root: &CompositionDefinition,
) -> DslResult<Vec<CompositionAllocation>> {
    let Some(total) = root.authoritative_total else {
        return Ok(Vec::new());
    };
    let compositions = program
        .compositions
        .iter()
        .map(|composition| (composition.id.as_str(), composition))
        .collect::<BTreeMap<_, _>>();
    let leaves = allocation_leaves(root, &compositions)?;
    let weights = leaves
        .iter()
        .map(|leaf| (leaf.path.clone(), leaf.weight))
        .collect::<Vec<_>>();
    let represented = largest_remainders(total, &weights);
    let simulated = largest_remainders(root.sample_budget.unwrap_or(0), &weights);
    Ok(leaves
        .into_iter()
        .map(|leaf| CompositionAllocation {
            represented_count: represented[&leaf.path],
            simulated_count: simulated[&leaf.path],
            path: leaf.path,
            weight: leaf.weight,
        })
        .collect())
}

fn allocation_leaves<'a>(
    root: &'a CompositionDefinition,
    compositions: &BTreeMap<&'a str, &'a CompositionDefinition>,
) -> DslResult<Vec<AllocationLeaf>> {
    let mut leaves = Vec::new();
    collect_leaves(root, compositions, &[], 1.0, &mut leaves)?;
    if leaves.is_empty() {
        return Err(DslError::new(
            "EMPTY_AUTHORITATIVE_ALLOCATION",
            root.line,
            "Authoritative allocation has no allocation leaves",
        ));
    }
    Ok(leaves)
}

fn collect_leaves<'a>(
    composition: &'a CompositionDefinition,
    compositions: &BTreeMap<&'a str, &'a CompositionDefinition>,
    path: &[String],
    parent_weight: f64,
    leaves: &mut Vec<AllocationLeaf>,
) -> DslResult<()> {
    let total = composition
        .entries
        .iter()
        .map(|entry| entry.weight.unwrap_or(1.0))
        .sum::<f64>();
    if (total - 1.0).abs() > 0.001 {
        return Err(DslError::new(
            "COMPOSITION_WEIGHTS_NOT_ONE",
            composition
                .entries
                .first()
                .map_or(composition.line, |entry| entry.line),
            format!(
                "Allocation weights for {} sum to {total}, expected 1.0 ± 0.001",
                composition.id
            ),
        ));
    }
    for entry in &composition.entries {
        let weight = parent_weight * entry.weight.unwrap_or(1.0) / total;
        let mut child_path = path.to_vec();
        child_path.push(entry.child.clone());
        match compositions.get(entry.child.as_str()) {
            Some(child) if !child.allocation_leaf => {
                collect_leaves(child, compositions, &child_path, weight, leaves)?;
            }
            _ => leaves.push(AllocationLeaf {
                path: child_path.join("/"),
                weight,
                declared_count: entry.declared_count,
                line: entry.line,
            }),
        }
    }
    Ok(())
}

fn largest_remainders(total: u64, weights: &[(String, f64)]) -> BTreeMap<String, u64> {
    let mut allocations = weights
        .iter()
        .map(|(path, weight)| {
            let exact = total as f64 * weight;
            (path.clone(), exact.floor() as u64, exact.fract())
        })
        .collect::<Vec<_>>();
    let assigned = allocations.iter().map(|(_, count, _)| *count).sum::<u64>();
    allocations.sort_by(|left, right| {
        right
            .2
            .total_cmp(&left.2)
            .then_with(|| left.0.cmp(&right.0))
    });
    for (_, count, _) in allocations.iter_mut().take((total - assigned) as usize) {
        *count += 1;
    }
    allocations
        .into_iter()
        .map(|(path, count, _)| (path, count))
        .collect()
}

pub(super) fn allocation_report(
    program: &Program,
    composition: &CompositionDefinition,
    tick: u64,
) -> DslResult<Option<DslReport>> {
    let allocations = composition_allocations(program, composition)?;
    if allocations.is_empty() {
        return Ok(None);
    }
    let columns = [
        ("weight", "Allocation weight", "percent"),
        ("represented_count", "Represented units", "integer"),
        ("simulated_count", "Simulated units", "integer"),
    ]
    .into_iter()
    .map(|(id, label, format)| ReportColumnDefinition {
        id: id.to_owned(),
        label: label.to_owned(),
        format: format.to_owned(),
        metric: ReportMetric::Count,
        line: composition.line,
    })
    .collect();
    let rows = allocations
        .into_iter()
        .map(|allocation| DslReportRow {
            group_id: allocation.path,
            values: BTreeMap::from([
                (
                    "weight".to_owned(),
                    DslReportValue::Number(allocation.weight),
                ),
                (
                    "represented_count".to_owned(),
                    DslReportValue::Number(allocation.represented_count as f64),
                ),
                (
                    "simulated_count".to_owned(),
                    DslReportValue::Number(allocation.simulated_count as f64),
                ),
            ]),
        })
        .collect();
    Ok(Some(DslReport {
        id: "composition_allocations".to_owned(),
        title: format!("{} authoritative allocation", composition.id),
        group_by: "allocation_leaf".to_owned(),
        display: "table".to_owned(),
        record: "final".to_owned(),
        columns,
        snapshots: vec![DslReportSnapshot { tick, rows }],
    }))
}
