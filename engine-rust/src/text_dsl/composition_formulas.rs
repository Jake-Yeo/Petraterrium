use super::expression::evaluate;
use super::model::*;
use std::collections::BTreeMap;

pub(super) fn apply_formula_outputs(
    composition: &CompositionDefinition,
    inputs: &BTreeMap<String, f64>,
    children: &[(String, f64, BTreeMap<String, LearnedMetricSummary>)],
    outputs: &mut BTreeMap<String, LearnedMetricSummary>,
) -> DslResult<()> {
    let mut values = composition
        .parameters
        .iter()
        .chain(inputs)
        .map(|(id, value)| (id.clone(), DslValue::Number(*value)))
        .chain(
            outputs
                .iter()
                .map(|(id, summary)| (id.clone(), DslValue::Number(summary.mean))),
        )
        .collect::<BTreeMap<_, _>>();
    add_child_values(children, &mut values);
    for output in &composition.outputs {
        let ReportMetric::Formula { expression } = &output.metric else {
            continue;
        };
        let value = evaluate(expression, &values)?.as_f64().ok_or_else(|| {
            DslError::new(
                "INVALID_COMPOSITION_FORMULA",
                output.line,
                format!("Composition formula {} must resolve to a number", output.id),
            )
        })?;
        if !value.is_finite() {
            return Err(DslError::new(
                "INVALID_COMPOSITION_FORMULA",
                output.line,
                format!("Composition formula {} must be finite", output.id),
            ));
        }
        values.insert(output.id.clone(), DslValue::Number(value));
        outputs.insert(
            output.id.clone(),
            LearnedMetricSummary {
                mean: value,
                standard_deviation: 0.0,
            },
        );
    }
    Ok(())
}

pub(super) fn static_formula_children(
    program: &Program,
    composition: &CompositionDefinition,
) -> DslResult<Vec<(String, f64, BTreeMap<String, LearnedMetricSummary>)>> {
    composition
        .entries
        .iter()
        .map(|entry| {
            let mut outputs = BTreeMap::new();
            if let Some(child) = program
                .compositions
                .iter()
                .find(|child| child.id == entry.child)
            {
                let children = static_formula_children(program, child)?;
                apply_formula_outputs(child, &BTreeMap::new(), &children, &mut outputs)?;
            }
            Ok((entry.child.clone(), entry.weight.unwrap_or(1.0), outputs))
        })
        .collect()
}

fn add_child_values(
    children: &[(String, f64, BTreeMap<String, LearnedMetricSummary>)],
    values: &mut BTreeMap<String, DslValue>,
) {
    let total_weight = children.iter().map(|(_, weight, _)| weight).sum::<f64>();
    let mut sums = BTreeMap::<String, f64>::new();
    let mut weighted = BTreeMap::<String, f64>::new();
    for (child, weight, outputs) in children {
        for (output, summary) in outputs {
            values.insert(format!("{child}.{output}"), DslValue::Number(summary.mean));
            *sums.entry(output.clone()).or_default() += summary.mean;
            *weighted.entry(output.clone()).or_default() += weight * summary.mean;
        }
    }
    for (output, value) in sums {
        values.insert(format!("sum.{output}"), DslValue::Number(value));
    }
    if total_weight > 0.0 {
        for (output, value) in weighted {
            values.insert(
                format!("weighted.{output}"),
                DslValue::Number(value / total_weight),
            );
        }
    }
}
