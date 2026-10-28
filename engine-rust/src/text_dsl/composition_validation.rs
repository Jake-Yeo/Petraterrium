use super::expression::{evaluate, references};
use super::model::*;
use std::collections::{BTreeMap, BTreeSet};

pub(super) fn validate_compositions(program: &Program) -> DslResult<()> {
    let archetypes = program
        .archetypes
        .iter()
        .map(|item| item.id.as_str())
        .collect::<BTreeSet<_>>();
    let places = program
        .places
        .iter()
        .map(|item| item.id.as_str())
        .collect::<BTreeSet<_>>();
    let compositions = program
        .compositions
        .iter()
        .map(|item| (item.id.as_str(), item))
        .collect::<BTreeMap<_, _>>();
    let base_fields = program
        .agents
        .iter()
        .flat_map(|agent| agent.traits.iter().chain(&agent.states))
        .cloned()
        .chain(
            program
                .archetypes
                .iter()
                .flat_map(|archetype| archetype.initial.iter().map(|item| item.field.clone())),
        )
        .collect::<BTreeSet<_>>();
    let aggregates = program
        .actions
        .iter()
        .map(|item| item.aggregate.as_str())
        .collect::<BTreeSet<_>>();
    let mut ids = BTreeSet::new();
    for composition in &program.compositions {
        let legacy = composition.report_id == "neighbourhoods";
        if !ids.insert(composition.id.as_str()) {
            return Err(DslError::new(
                if legacy {
                    "DUPLICATE_NEIGHBOURHOOD"
                } else {
                    "DUPLICATE_COMPOSITION"
                },
                composition.line,
                format!("Duplicate composition {}", composition.id),
            ));
        }
        if composition.entries.is_empty() || composition.outputs.is_empty() {
            return Err(DslError::new(
                if legacy {
                    "EMPTY_NEIGHBOURHOOD"
                } else {
                    "EMPTY_COMPOSITION"
                },
                composition.line,
                "Composition needs children and outputs",
            ));
        }
        let child_ids = composition
            .entries
            .iter()
            .map(|entry| entry.child.as_str())
            .collect::<BTreeSet<_>>();
        if child_ids.len() != composition.entries.len() {
            return Err(DslError::new(
                if legacy {
                    "DUPLICATE_NEIGHBOURHOOD_HOUSEHOLD"
                } else {
                    "DUPLICATE_COMPOSITION_CHILD"
                },
                composition.line,
                "Composition children must be unique",
            ));
        }
        for entry in &composition.entries {
            if !archetypes.contains(entry.child.as_str())
                && !compositions.contains_key(entry.child.as_str())
            {
                return Err(DslError::new(
                    if legacy {
                        "UNKNOWN_NEIGHBOURHOOD_HOUSEHOLD"
                    } else {
                        "UNKNOWN_COMPOSITION_CHILD"
                    },
                    entry.line,
                    format!("Unknown composition child {}", entry.child),
                ));
            }
            if entry.weight == 0 {
                return Err(DslError::new(
                    if legacy {
                        "INVALID_NEIGHBOURHOOD_HOUSEHOLD"
                    } else {
                        "INVALID_COMPOSITION_CHILD"
                    },
                    entry.line,
                    "Composition weight must be positive",
                ));
            }
        }
        for place in &composition.places {
            if !places.contains(place.as_str()) {
                return Err(DslError::new(
                    if legacy {
                        "UNKNOWN_NEIGHBOURHOOD_PLACE"
                    } else {
                        "UNKNOWN_COMPOSITION_PLACE"
                    },
                    composition.line,
                    format!("Unknown composition place {place}"),
                ));
            }
        }
        validate_adjacency(composition, &child_ids)?;
        validate_flows(program, composition, &child_ids)?;
        validate_cached_composition(program, composition)?;
        for output in &composition.outputs {
            match &output.metric {
                ReportMetric::Count => {}
                ReportMetric::Mean { field } | ReportMetric::Sum { field }
                    if base_fields.contains(field) => {}
                ReportMetric::KidsPerFamily => {}
                ReportMetric::ActionCount { aggregate, window }
                    if aggregates.contains(aggregate.as_str())
                        && matches!(window.as_str(), "tick" | "day" | "run") => {}
                ReportMetric::PlaceState { place, field }
                    if program
                        .places
                        .iter()
                        .any(|item| item.id == *place && item.states.contains_key(field)) => {}
                ReportMetric::FlowCount { flow } | ReportMetric::FlowRate { flow }
                    if composition.flows.iter().any(|item| item.id == *flow) => {}
                _ => {
                    return Err(DslError::new(
                        if legacy {
                            "INVALID_NEIGHBOURHOOD_OUTPUT"
                        } else {
                            "INVALID_COMPOSITION_OUTPUT"
                        },
                        output.line,
                        format!("Invalid composition output {}", output.id),
                    ));
                }
            }
        }
    }
    validate_composition_cycles(&compositions)?;
    let mut population_ids = BTreeSet::new();
    for population in &program.composition_populations {
        if !population_ids.insert(population.id.as_str()) {
            return Err(DslError::new(
                "DUPLICATE_COMPOSITION_POPULATION",
                population.line,
                format!("Duplicate composition population {}", population.id),
            ));
        }
        if population.entries.is_empty() {
            return Err(DslError::new(
                "EMPTY_COMPOSITION_POPULATION",
                population.line,
                "Composition population needs entries",
            ));
        }
        for entry in &population.entries {
            if !compositions.contains_key(entry.composition.as_str()) {
                return Err(DslError::new(
                    if population.legacy_neighbourhood {
                        "UNKNOWN_NEIGHBOURHOOD"
                    } else {
                        "UNKNOWN_COMPOSITION"
                    },
                    entry.line,
                    format!("Unknown composition {}", entry.composition),
                ));
            }
            if entry.weight == 0 {
                return Err(DslError::new(
                    "INVALID_COMPOSITION_WEIGHT",
                    entry.line,
                    "Composition weight must be positive",
                ));
            }
        }
    }
    Ok(())
}

fn validate_adjacency(
    composition: &CompositionDefinition,
    child_ids: &BTreeSet<&str>,
) -> DslResult<()> {
    let mut pairs = BTreeSet::new();
    for edge in &composition.adjacency {
        if !child_ids.contains(edge.source.as_str()) || !child_ids.contains(edge.target.as_str()) {
            return Err(DslError::new(
                "UNKNOWN_COMPOSITION_ADJACENCY",
                edge.line,
                "Adjacency endpoints must be direct composition children",
            ));
        }
        if edge.source == edge.target || !edge.distance.is_finite() || edge.distance <= 0.0 {
            return Err(DslError::new(
                "INVALID_COMPOSITION_ADJACENCY",
                edge.line,
                "Adjacency endpoints must differ and distance must be positive",
            ));
        }
        let pair = if edge.source < edge.target {
            (edge.source.as_str(), edge.target.as_str())
        } else {
            (edge.target.as_str(), edge.source.as_str())
        };
        if !pairs.insert(pair) {
            return Err(DslError::new(
                "DUPLICATE_COMPOSITION_ADJACENCY",
                edge.line,
                "Composition adjacency pairs must be unique",
            ));
        }
    }
    Ok(())
}

fn validate_flows(
    program: &Program,
    composition: &CompositionDefinition,
    child_ids: &BTreeSet<&str>,
) -> DslResult<()> {
    let function = program
        .aggregate_functions
        .iter()
        .find(|item| item.id == composition.id);
    let mut allowed = composition
        .parameters
        .keys()
        .cloned()
        .chain(
            function
                .into_iter()
                .flat_map(|item| item.inputs.iter().map(|input| input.id.clone())),
        )
        .chain(composition.outputs.iter().map(|output| output.id.clone()))
        .collect::<BTreeSet<_>>();
    for entry in &composition.entries {
        if let Some(child) = program
            .compositions
            .iter()
            .find(|item| item.id == entry.child)
        {
            for output in &child.outputs {
                allowed.insert(format!("{}_{}", entry.child, output.id));
                allowed.insert(format!("{}.{}", entry.child, output.id));
            }
        }
    }
    for edge in &composition.adjacency {
        allowed.insert(format!("distance_{}_{}", edge.source, edge.target));
        allowed.insert(format!("distance_{}_{}", edge.target, edge.source));
    }
    let mut ids = BTreeSet::new();
    for flow in &composition.flows {
        if !ids.insert(flow.id.as_str()) {
            return Err(DslError::new(
                "DUPLICATE_COMPOSITION_FLOW",
                flow.line,
                format!("Duplicate composition flow {}", flow.id),
            ));
        }
        if !child_ids.contains(flow.source.as_str()) || !child_ids.contains(flow.target.as_str()) {
            return Err(DslError::new(
                "UNKNOWN_COMPOSITION_FLOW_CHILD",
                flow.line,
                "Flow endpoints must be direct composition children",
            ));
        }
        let unknown = references(&flow.rate)
            .into_iter()
            .filter(|reference| !allowed.contains(reference))
            .collect::<Vec<_>>();
        if !unknown.is_empty() {
            return Err(DslError::new(
                "UNKNOWN_COMPOSITION_FLOW_VALUE",
                flow.line,
                format!(
                    "Flow rate references unknown values: {}",
                    unknown.join(", ")
                ),
            ));
        }
        if references(&flow.rate).is_empty() {
            let rate = evaluate(&flow.rate, &BTreeMap::new())?
                .as_f64()
                .unwrap_or(f64::NAN);
            if !rate.is_finite() || !(0.0..=1.0).contains(&rate) {
                return Err(DslError::new(
                    "INVALID_COMPOSITION_FLOW_RATE",
                    flow.line,
                    "Constant flow rate must be between zero and one",
                ));
            }
        }
        if !matches!(flow.effect.as_str(), "visit" | "transfer") {
            return Err(DslError::new(
                "INVALID_COMPOSITION_FLOW_EFFECT",
                flow.line,
                "Flow effect must be visit or transfer",
            ));
        }
        if flow.effect == "visit" && flow.via.is_none() {
            return Err(DslError::new(
                "MISSING_COMPOSITION_FLOW_PLACE",
                flow.line,
                "Visit flow needs a shared place",
            ));
        }
        if flow
            .via
            .as_ref()
            .is_some_and(|place| !composition.places.contains(place))
        {
            return Err(DslError::new(
                "UNKNOWN_COMPOSITION_FLOW_PLACE",
                flow.line,
                "Flow place must be shared by the composition",
            ));
        }
        let adjacent = composition.adjacency.is_empty()
            || composition.adjacency.iter().any(|edge| {
                edge.source == flow.source && edge.target == flow.target
                    || edge.source == flow.target && edge.target == flow.source
            });
        if !adjacent && flow.via.is_none() {
            return Err(DslError::new(
                "NON_ADJACENT_COMPOSITION_FLOW",
                flow.line,
                "Non-adjacent children require a shared flow place",
            ));
        }
    }
    Ok(())
}

fn validate_cached_composition(
    program: &Program,
    composition: &CompositionDefinition,
) -> DslResult<()> {
    let Some(cached) = &composition.cached else {
        return Ok(());
    };
    if cached.sync_days == 0
        || !(1..=5).contains(&cached.max_iterations)
        || !cached.tolerance.is_finite()
        || !(0.0..1.0).contains(&cached.tolerance)
    {
        return Err(DslError::new(
            "INVALID_CACHED_COMPOSITION",
            cached.line,
            "Cached sync must be positive, iterations 1..5, and tolerance between zero and one",
        ));
    }
    let output_ids = composition
        .outputs
        .iter()
        .map(|output| output.id.as_str())
        .collect::<BTreeSet<_>>();
    let child_inputs = composition
        .entries
        .iter()
        .filter_map(|entry| {
            program
                .aggregate_functions
                .iter()
                .find(|function| function.id == entry.child)
        })
        .flat_map(|function| function.inputs.iter().map(|input| input.id.as_str()))
        .collect::<BTreeSet<_>>();
    for feedback in &cached.feedback {
        if !output_ids.contains(feedback.output.as_str()) {
            return Err(DslError::new(
                "UNKNOWN_COMPOSITION_FEEDBACK_OUTPUT",
                feedback.line,
                format!("Unknown feedback output {}", feedback.output),
            ));
        }
        if !child_inputs.contains(feedback.input.as_str()) {
            return Err(DslError::new(
                "UNKNOWN_COMPOSITION_FEEDBACK_INPUT",
                feedback.line,
                format!("Unknown child feedback input {}", feedback.input),
            ));
        }
        if !feedback.scale.is_finite() {
            return Err(DslError::new(
                "INVALID_COMPOSITION_FEEDBACK",
                feedback.line,
                "Feedback scale must be finite",
            ));
        }
    }
    Ok(())
}

fn validate_composition_cycles(
    compositions: &BTreeMap<&str, &CompositionDefinition>,
) -> DslResult<()> {
    for root in compositions.values() {
        let mut visiting = BTreeSet::new();
        visit_composition(root, compositions, &mut visiting)?;
    }
    Ok(())
}

fn visit_composition<'a>(
    composition: &'a CompositionDefinition,
    compositions: &BTreeMap<&'a str, &'a CompositionDefinition>,
    visiting: &mut BTreeSet<&'a str>,
) -> DslResult<()> {
    if !visiting.insert(composition.id.as_str()) {
        return Err(DslError::new(
            "COMPOSITION_CYCLE",
            composition.line,
            format!("Composition cycle includes {}", composition.id),
        ));
    }
    for entry in &composition.entries {
        if let Some(child) = compositions.get(entry.child.as_str()) {
            visit_composition(child, compositions, visiting)?;
        }
    }
    visiting.remove(composition.id.as_str());
    Ok(())
}
