use super::composition_cache::{CachedFlowPoint, HierarchyContext, stable_number};
use super::composition_cache_artifacts::aggregate_function;
use super::expression::evaluate;
use super::model::*;
use std::collections::BTreeMap;

pub(super) fn apply_cached_couplings(
    context: &mut HierarchyContext<'_>,
    composition: &CompositionDefinition,
    day: u32,
    inputs: &BTreeMap<String, f64>,
    children: &[(String, f64, BTreeMap<String, LearnedMetricSummary>)],
    outputs: &mut BTreeMap<String, LearnedMetricSummary>,
    flows: &[CachedFlowPoint],
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
    for flow in flows {
        values.insert(flow.id.clone(), DslValue::Number(flow.rate));
    }
    let mut points = Vec::new();
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
        if !value.is_finite() {
            return Err(DslError::new(
                "INVALID_COMPOSITION_COUPLING_VALUE",
                coupling.line,
                "Coupling value must be finite",
            ));
        }
        let target_function = aggregate_function(context.program, &coupling.target)?;
        let target_input = target_function
            .inputs
            .iter()
            .find(|input| input.id == coupling.target_input)
            .unwrap();
        if !(target_input.minimum..=target_input.maximum).contains(&value) {
            return Err(DslError::new(
                "COMPOSITION_COUPLING_VALUE_OUT_OF_RANGE",
                coupling.line,
                format!(
                    "Coupling {} must be between {} and {}",
                    coupling.id, target_input.minimum, target_input.maximum
                ),
            ));
        }
        context
            .states
            .get_mut(&coupling.target)
            .unwrap()
            .coupling_inputs
            .insert(coupling.target_input.clone(), value);
        for output in &composition.outputs {
            match &output.metric {
                ReportMetric::FlowRate { flow } | ReportMetric::FlowCount { flow }
                    if flow == &coupling.id =>
                {
                    outputs.insert(
                        output.id.clone(),
                        LearnedMetricSummary {
                            mean: stable_number(value),
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
            id: coupling.id.clone(),
            source: coupling.source.clone(),
            target: coupling.target.clone(),
            effect: "coupling".to_owned(),
            count: stable_number(value),
            rate: stable_number(value),
        });
        values.insert(coupling.id.clone(), DslValue::Number(value));
    }
    for boundary in &composition.boundaries {
        let population = |id: &str| {
            children
                .iter()
                .find(|(child, _, _)| child == id)
                .and_then(|(_, _, outputs)| outputs.get("population"))
                .map_or(0.0, |summary| summary.mean)
        };
        let count = population(&boundary.source).min(population(&boundary.target));
        points.push(CachedFlowPoint {
            day,
            composition: composition.id.clone(),
            id: boundary.id.clone(),
            source: boundary.source.clone(),
            target: boundary.target.clone(),
            effect: "boundary".to_owned(),
            count: stable_number(count),
            rate: if count > 0.0 { 1.0 } else { 0.0 },
        });
    }
    Ok(points)
}
