use super::model::*;
use super::parser::{Line, identifier, parse_archetype_output, require_indent};
use std::collections::{BTreeMap, BTreeSet};

pub(super) fn parse_neighbourhood(
    lines: &[Line],
    start: usize,
    name: &str,
) -> DslResult<(CompositionDefinition, usize)> {
    parse_composition_body(lines, start, name, Some("neighbourhood"))
}

pub(super) fn parse_composition(
    lines: &[Line],
    start: usize,
    name: &str,
) -> DslResult<(CompositionDefinition, usize)> {
    parse_composition_body(lines, start, name, None)
}

fn parse_composition_body(
    lines: &[Line],
    start: usize,
    name: &str,
    compatibility_level: Option<&str>,
) -> DslResult<(CompositionDefinition, usize)> {
    identifier(name, lines[start].number)?;
    let mut level = compatibility_level.map(str::to_owned);
    let mut entries = Vec::new();
    let mut places = Vec::new();
    let mut parameters = BTreeMap::new();
    let mut adjacency = Vec::new();
    let mut flows = Vec::new();
    let mut outputs = Vec::new();
    let mut index = start + 1;
    while index < lines.len() && lines[index].indent > 0 {
        let line = &lines[index];
        require_indent(line, 2)?;
        if let Some(value) = line.text.strip_prefix("level = ") {
            identifier(value, line.number)?;
            if compatibility_level.is_some() {
                return Err(DslError::new(
                    "INVALID_NEIGHBOURHOOD_LEVEL",
                    line.number,
                    "Legacy neighbourhood blocks already define their level",
                ));
            }
            level = Some(value.to_owned());
            index += 1;
        } else if line.text == "children:" || line.text == "entries:" || line.text == "households:"
        {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let entry = &lines[index];
                require_indent(entry, 4)?;
                let Some((child, weight)) = entry.text.split_once(": weight = ") else {
                    return Err(DslError::new(
                        compatibility_code(
                            compatibility_level,
                            "INVALID_NEIGHBOURHOOD_HOUSEHOLD",
                            "INVALID_COMPOSITION_CHILD",
                        ),
                        entry.number,
                        "Composition entries use Child: weight = count",
                    ));
                };
                identifier(child, entry.number)?;
                entries.push(CompositionEntry {
                    child: child.to_owned(),
                    weight: weight.parse::<u64>().map_err(|_| {
                        DslError::new(
                            compatibility_code(
                                compatibility_level,
                                "INVALID_NEIGHBOURHOOD_HOUSEHOLD",
                                "INVALID_COMPOSITION_CHILD",
                            ),
                            entry.number,
                            "Composition weight must be a positive integer",
                        )
                    })?,
                    line: entry.number,
                });
                index += 1;
            }
        } else if let Some(value) = line
            .text
            .strip_prefix("places = ")
            .or_else(|| line.text.strip_prefix("institutions = "))
        {
            places.extend(value.split(',').map(|item| item.trim().to_owned()));
            index += 1;
        } else if line.text == "parameters:" {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let entry = &lines[index];
                require_indent(entry, 4)?;
                let Some((id, value)) = entry.text.split_once(" = ") else {
                    return Err(DslError::new(
                        "INVALID_COMPOSITION_PARAMETER",
                        entry.number,
                        "Composition parameters use name = number",
                    ));
                };
                identifier(id, entry.number)?;
                let value = value.parse::<f64>().map_err(|_| {
                    DslError::new(
                        "INVALID_COMPOSITION_PARAMETER",
                        entry.number,
                        "Composition parameter must be numeric",
                    )
                })?;
                if !value.is_finite() {
                    return Err(DslError::new(
                        "INVALID_COMPOSITION_PARAMETER",
                        entry.number,
                        "Composition parameter must be finite",
                    ));
                }
                parameters.insert(id.to_owned(), value);
                index += 1;
            }
        } else if line.text == "adjacency:" {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let entry = &lines[index];
                require_indent(entry, 4)?;
                adjacency.push(parse_adjacency(entry)?);
                index += 1;
            }
        } else if line.text == "flows:" {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let entry = &lines[index];
                require_indent(entry, 4)?;
                flows.push(parse_flow(entry)?);
                index += 1;
            }
        } else if let Some(value) = line.text.strip_prefix("output ") {
            outputs.push(parse_archetype_output(value, line.number)?);
            index += 1;
        } else {
            return Err(DslError::new(
                compatibility_code(
                    compatibility_level,
                    "UNKNOWN_NEIGHBOURHOOD_STATEMENT",
                    "UNKNOWN_COMPOSITION_STATEMENT",
                ),
                line.number,
                format!("Unknown composition statement {}", line.text),
            ));
        }
    }
    let compatibility = compatibility_level.is_some();
    Ok((
        CompositionDefinition {
            id: name.to_owned(),
            level: level.ok_or_else(|| {
                DslError::new(
                    "MISSING_COMPOSITION_LEVEL",
                    lines[start].number,
                    "Composition needs level = identifier",
                )
            })?,
            entries,
            places,
            parameters,
            adjacency,
            flows,
            outputs,
            report_id: if compatibility {
                "neighbourhoods"
            } else {
                "compositions"
            }
            .to_owned(),
            interaction_report_id: if compatibility {
                "cross_archetype_interactions"
            } else {
                "cross_composition_interactions"
            }
            .to_owned(),
            report_title: if compatibility {
                "Neighbourhood archetypes"
            } else {
                "Compositions"
            }
            .to_owned(),
            line: lines[start].number,
        },
        index,
    ))
}

fn parse_adjacency(line: &Line) -> DslResult<CompositionAdjacency> {
    let Some((pair, distance)) = line.text.split_once(" distance = ") else {
        return Err(DslError::new(
            "INVALID_COMPOSITION_ADJACENCY",
            line.number,
            "Adjacency uses Source <-> Target distance = number",
        ));
    };
    let Some((source, target)) = pair.split_once(" <-> ") else {
        return Err(DslError::new(
            "INVALID_COMPOSITION_ADJACENCY",
            line.number,
            "Adjacency uses Source <-> Target distance = number",
        ));
    };
    identifier(source, line.number)?;
    identifier(target, line.number)?;
    Ok(CompositionAdjacency {
        source: source.to_owned(),
        target: target.to_owned(),
        distance: distance.parse::<f64>().map_err(|_| {
            DslError::new(
                "INVALID_COMPOSITION_ADJACENCY",
                line.number,
                "Adjacency distance must be numeric",
            )
        })?,
        line: line.number,
    })
}

fn parse_flow(line: &Line) -> DslResult<CompositionFlowDefinition> {
    let Some((id, rest)) = line.text.split_once(' ') else {
        return Err(invalid_flow(line.number));
    };
    identifier(id, line.number)?;
    let Some((source, rest)) = rest.split_once(" -> ") else {
        return Err(invalid_flow(line.number));
    };
    let Some((target, rest)) = rest.split_once(" rate = ") else {
        return Err(invalid_flow(line.number));
    };
    let Some((rate, rest)) = rest.split_once(" effect = ") else {
        return Err(invalid_flow(line.number));
    };
    let (effect, via) = rest
        .split_once(" via ")
        .map_or((rest, None), |(effect, via)| (effect, Some(via.to_owned())));
    identifier(source, line.number)?;
    identifier(target, line.number)?;
    identifier(effect, line.number)?;
    if let Some(via) = &via {
        identifier(via, line.number)?;
    }
    Ok(CompositionFlowDefinition {
        id: id.to_owned(),
        source: source.to_owned(),
        target: target.to_owned(),
        rate: rate.parse::<f64>().map_err(|_| invalid_flow(line.number))?,
        effect: effect.to_owned(),
        via,
        line: line.number,
    })
}

fn invalid_flow(line: usize) -> DslError {
    DslError::new(
        "INVALID_COMPOSITION_FLOW",
        line,
        "Flow uses id Source -> Target rate = number effect = visit|transfer [via Place]",
    )
}

pub(super) fn parse_neighbourhood_population(
    lines: &[Line],
    start: usize,
    name: &str,
) -> DslResult<(WeightedCompositionPopulation, usize)> {
    parse_composition_population_body(lines, start, name, true)
}

pub(super) fn parse_composition_population(
    lines: &[Line],
    start: usize,
    name: &str,
) -> DslResult<(WeightedCompositionPopulation, usize)> {
    parse_composition_population_body(lines, start, name, false)
}

fn parse_composition_population_body(
    lines: &[Line],
    start: usize,
    name: &str,
    compatibility: bool,
) -> DslResult<(WeightedCompositionPopulation, usize)> {
    identifier(name, lines[start].number)?;
    let mut entries = Vec::new();
    let mut index = start + 1;
    while index < lines.len() && lines[index].indent > 0 {
        let line = &lines[index];
        require_indent(line, 2)?;
        let Some((composition, weight)) = line.text.split_once(": weight = ") else {
            return Err(DslError::new(
                if compatibility {
                    "INVALID_NEIGHBOURHOOD_WEIGHT"
                } else {
                    "INVALID_COMPOSITION_WEIGHT"
                },
                line.number,
                "Composition population entries use Composition: weight = count",
            ));
        };
        entries.push(WeightedCompositionEntry {
            composition: composition.to_owned(),
            weight: weight.parse::<u64>().map_err(|_| {
                DslError::new(
                    if compatibility {
                        "INVALID_NEIGHBOURHOOD_WEIGHT"
                    } else {
                        "INVALID_COMPOSITION_WEIGHT"
                    },
                    line.number,
                    "Composition weight must be a positive integer",
                )
            })?,
            line: line.number,
        });
        index += 1;
    }
    Ok((
        WeightedCompositionPopulation {
            id: name.to_owned(),
            entries,
            legacy_neighbourhood: compatibility,
            line: lines[start].number,
        },
        index,
    ))
}

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
        validate_flows(composition, &child_ids)?;
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
    composition: &CompositionDefinition,
    child_ids: &BTreeSet<&str>,
) -> DslResult<()> {
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
        if !flow.rate.is_finite() || !(0.0..=1.0).contains(&flow.rate) {
            return Err(DslError::new(
                "INVALID_COMPOSITION_FLOW_RATE",
                flow.line,
                "Flow rate must be between zero and one",
            ));
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

fn compatibility_code<'a>(
    compatibility_level: Option<&str>,
    compatibility: &'a str,
    generic: &'a str,
) -> &'a str {
    if compatibility_level.is_some() {
        compatibility
    } else {
        generic
    }
}
