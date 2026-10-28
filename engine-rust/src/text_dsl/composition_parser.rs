use super::expression::parse_expression;
use super::model::*;
use super::parser::{Line, identifier, parse_archetype_output, require_indent};
use std::collections::BTreeMap;

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

pub(super) fn parse_composition_archetype(
    lines: &[Line],
    start: usize,
    name: &str,
) -> DslResult<(CompositionArchetypeDefinition, usize)> {
    identifier(name, lines[start].number)?;
    let mut level = None;
    let mut child_level = None;
    let mut parameters = BTreeMap::new();
    let mut outputs = Vec::new();
    let mut index = start + 1;
    while index < lines.len() && lines[index].indent > 0 {
        let line = &lines[index];
        require_indent(line, 2)?;
        if let Some(value) = line.text.strip_prefix("level = ") {
            identifier(value, line.number)?;
            level = Some(value.to_owned());
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("child_level = ") {
            identifier(value, line.number)?;
            child_level = Some(value.to_owned());
            index += 1;
        } else if line.text == "parameters:" {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let entry = &lines[index];
                require_indent(entry, 4)?;
                let Some((id, value)) = entry.text.split_once(" = ") else {
                    return Err(DslError::new(
                        "INVALID_COMPOSITION_ARCHETYPE_PARAMETER",
                        entry.number,
                        "Composition archetype parameters use name = number",
                    ));
                };
                identifier(id, entry.number)?;
                parameters.insert(
                    id.to_owned(),
                    value.parse::<f64>().map_err(|_| {
                        DslError::new(
                            "INVALID_COMPOSITION_ARCHETYPE_PARAMETER",
                            entry.number,
                            "Composition archetype parameter must be numeric",
                        )
                    })?,
                );
                index += 1;
            }
        } else if let Some(value) = line.text.strip_prefix("output ") {
            outputs.push(parse_archetype_output(value, line.number)?);
            index += 1;
        } else {
            return Err(DslError::new(
                "UNKNOWN_COMPOSITION_ARCHETYPE_STATEMENT",
                line.number,
                format!("Unknown composition archetype statement {}", line.text),
            ));
        }
    }
    Ok((
        CompositionArchetypeDefinition {
            id: name.to_owned(),
            level: level.ok_or_else(|| {
                DslError::new(
                    "MISSING_COMPOSITION_ARCHETYPE_LEVEL",
                    lines[start].number,
                    "Composition archetype needs level",
                )
            })?,
            child_level: child_level.ok_or_else(|| {
                DslError::new(
                    "MISSING_COMPOSITION_ARCHETYPE_CHILD_LEVEL",
                    lines[start].number,
                    "Composition archetype needs child_level",
                )
            })?,
            parameters,
            outputs,
            line: lines[start].number,
        },
        index,
    ))
}

fn parse_composition_body(
    lines: &[Line],
    start: usize,
    name: &str,
    compatibility_level: Option<&str>,
) -> DslResult<(CompositionDefinition, usize)> {
    identifier(name, lines[start].number)?;
    let mut level = compatibility_level.map(str::to_owned);
    let mut template = None;
    let mut represented_population = None;
    let mut entries = Vec::new();
    let mut places = Vec::new();
    let mut parameters = BTreeMap::new();
    let mut policies = Vec::new();
    let mut adjacency = Vec::new();
    let mut flows = Vec::new();
    let mut couplings = Vec::new();
    let mut boundaries = Vec::new();
    let mut cached = None;
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
        } else if let Some(value) = line.text.strip_prefix("template = ") {
            identifier(value, line.number)?;
            template = Some(value.to_owned());
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("represented_population = ") {
            represented_population = Some(value.parse::<u64>().map_err(|_| {
                DslError::new(
                    "INVALID_REPRESENTED_POPULATION",
                    line.number,
                    "Represented population must be a positive integer",
                )
            })?);
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
        } else if let Some(value) = line.text.strip_prefix("policies = ") {
            policies.extend(value.split(',').map(|item| item.trim().to_owned()));
            index += 1;
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
        } else if line.text == "couplings:" {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let entry = &lines[index];
                require_indent(entry, 4)?;
                couplings.push(parse_coupling(entry)?);
                index += 1;
            }
        } else if line.text == "boundaries:" {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let entry = &lines[index];
                require_indent(entry, 4)?;
                boundaries.push(parse_boundary(entry)?);
                index += 1;
            }
        } else if line.text == "cached:" {
            let (definition, next) = parse_cached_composition(lines, index)?;
            cached = Some(definition);
            index = next;
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
            template,
            represented_population,
            entries,
            places,
            parameters,
            policies,
            adjacency,
            flows,
            couplings,
            boundaries,
            cached,
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

fn parse_boundary(line: &Line) -> DslResult<CompositionBoundaryDefinition> {
    let Some((id, value)) = line.text.split_once(' ') else {
        return Err(invalid_boundary(line.number));
    };
    identifier(id, line.number)?;
    let Some((source, value)) = value.split_once(" -> ") else {
        return Err(invalid_boundary(line.number));
    };
    let Some((target, fields)) = value.split_once(" fields = ") else {
        return Err(invalid_boundary(line.number));
    };
    identifier(source, line.number)?;
    identifier(target, line.number)?;
    let fields = fields
        .split(',')
        .map(|field| {
            let field = field.trim();
            identifier(field, line.number)?;
            Ok(field.to_owned())
        })
        .collect::<DslResult<Vec<_>>>()?;
    if fields.is_empty() {
        return Err(invalid_boundary(line.number));
    }
    Ok(CompositionBoundaryDefinition {
        id: id.to_owned(),
        source: source.to_owned(),
        target: target.to_owned(),
        fields,
        line: line.number,
    })
}

fn invalid_boundary(line: usize) -> DslError {
    DslError::new(
        "INVALID_COMPOSITION_BOUNDARY",
        line,
        "Boundary uses id Source -> Target fields = field, field",
    )
}

fn parse_coupling(line: &Line) -> DslResult<CompositionCouplingDefinition> {
    let Some((id, value)) = line.text.split_once(' ') else {
        return Err(invalid_coupling(line.number));
    };
    identifier(id, line.number)?;
    let Some((source, value)) = value.split_once(" -> ") else {
        return Err(invalid_coupling(line.number));
    };
    let Some((target, value)) = value.split_once(" input = ") else {
        return Err(invalid_coupling(line.number));
    };
    let Some((target_input, value)) = value.split_once(" value = ") else {
        return Err(invalid_coupling(line.number));
    };
    let Some((expression, cadence)) = value.split_once(" cadence = ") else {
        return Err(invalid_coupling(line.number));
    };
    identifier(source, line.number)?;
    identifier(target, line.number)?;
    identifier(target_input, line.number)?;
    if !matches!(cadence, "sync" | "immediate") {
        return Err(DslError::new(
            "INVALID_COMPOSITION_COUPLING_CADENCE",
            line.number,
            "Coupling cadence must be sync or immediate",
        ));
    }
    Ok(CompositionCouplingDefinition {
        id: id.to_owned(),
        source: source.to_owned(),
        target: target.to_owned(),
        target_input: target_input.to_owned(),
        value: parse_expression(
            expression
                .strip_prefix("formula(")
                .and_then(|value| value.strip_suffix(')'))
                .unwrap_or(expression),
            line.number,
        )?,
        cadence: cadence.to_owned(),
        line: line.number,
    })
}

fn invalid_coupling(line: usize) -> DslError {
    DslError::new(
        "INVALID_COMPOSITION_COUPLING",
        line,
        "Coupling uses id Source -> Target input = name value = formula(expression) cadence = sync|immediate",
    )
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
        rate: parse_expression(
            rate.strip_prefix("formula(")
                .and_then(|value| value.strip_suffix(')'))
                .unwrap_or(rate),
            line.number,
        )?,
        effect: effect.to_owned(),
        via,
        line: line.number,
    })
}

fn invalid_flow(line: usize) -> DslError {
    DslError::new(
        "INVALID_COMPOSITION_FLOW",
        line,
        "Flow uses id Source -> Target rate = number|formula(expression) effect = visit|transfer [via Place]",
    )
}

fn parse_cached_composition(
    lines: &[Line],
    start: usize,
) -> DslResult<(CachedCompositionDefinition, usize)> {
    let mut sync_days = None;
    let mut max_iterations = 5;
    let mut tolerance = 0.01;
    let mut feedback = Vec::new();
    let mut index = start + 1;
    while index < lines.len() && lines[index].indent > 2 {
        let line = &lines[index];
        require_indent(line, 4)?;
        if let Some(value) = line.text.strip_prefix("sync = ") {
            sync_days = Some(parse_days(value, line.number)?);
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("max_iterations = ") {
            max_iterations = value.parse::<u32>().map_err(|_| {
                DslError::new(
                    "INVALID_CACHED_COMPOSITION",
                    line.number,
                    "max_iterations must be an integer",
                )
            })?;
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("tolerance = ") {
            tolerance = value.parse::<f64>().map_err(|_| {
                DslError::new(
                    "INVALID_CACHED_COMPOSITION",
                    line.number,
                    "tolerance must be numeric",
                )
            })?;
            index += 1;
        } else if line.text == "feedback:" {
            index += 1;
            while index < lines.len() && lines[index].indent > 4 {
                let entry = &lines[index];
                require_indent(entry, 6)?;
                let Some((mapping, scale)) = entry.text.split_once(" scale = ") else {
                    return Err(DslError::new(
                        "INVALID_COMPOSITION_FEEDBACK",
                        entry.number,
                        "Feedback uses output -> input scale = number",
                    ));
                };
                let Some((output, input)) = mapping.split_once(" -> ") else {
                    return Err(DslError::new(
                        "INVALID_COMPOSITION_FEEDBACK",
                        entry.number,
                        "Feedback uses output -> input scale = number",
                    ));
                };
                identifier(output, entry.number)?;
                identifier(input, entry.number)?;
                feedback.push(CompositionFeedbackDefinition {
                    output: output.to_owned(),
                    input: input.to_owned(),
                    scale: scale.parse::<f64>().map_err(|_| {
                        DslError::new(
                            "INVALID_COMPOSITION_FEEDBACK",
                            entry.number,
                            "Feedback scale must be numeric",
                        )
                    })?,
                    line: entry.number,
                });
                index += 1;
            }
        } else {
            return Err(DslError::new(
                "UNKNOWN_CACHED_COMPOSITION_STATEMENT",
                line.number,
                format!("Unknown cached composition statement {}", line.text),
            ));
        }
    }
    Ok((
        CachedCompositionDefinition {
            sync_days: sync_days.ok_or_else(|| {
                DslError::new(
                    "MISSING_CACHED_COMPOSITION_SYNC",
                    lines[start].number,
                    "Cached composition needs sync = number days",
                )
            })?,
            max_iterations,
            tolerance,
            feedback,
            line: lines[start].number,
        },
        index,
    ))
}

fn parse_days(value: &str, line: usize) -> DslResult<u32> {
    value
        .strip_suffix(" days")
        .ok_or_else(|| {
            DslError::new(
                "INVALID_CACHED_COMPOSITION_SYNC",
                line,
                "Sync uses number days",
            )
        })?
        .parse::<u32>()
        .map_err(|_| {
            DslError::new(
                "INVALID_CACHED_COMPOSITION_SYNC",
                line,
                "Sync days must be an integer",
            )
        })
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
        let (composition, weight, represented_population) = if let Some((composition, weight)) =
            line.text.split_once(": weight = ")
        {
            (
                composition,
                weight.parse::<u64>().map_err(|_| {
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
                None,
            )
        } else if let Some((composition, represented)) = line.text.split_once(": represented = ") {
            (
                composition,
                1,
                Some(represented.parse::<u64>().map_err(|_| {
                    DslError::new(
                        "INVALID_REPRESENTED_POPULATION",
                        line.number,
                        "Represented population must be a positive integer",
                    )
                })?),
            )
        } else {
            return Err(DslError::new(
                if compatibility {
                    "INVALID_NEIGHBOURHOOD_WEIGHT"
                } else {
                    "INVALID_COMPOSITION_WEIGHT"
                },
                line.number,
                "Composition population entries use Composition: weight = count or represented = count",
            ));
        };
        entries.push(WeightedCompositionEntry {
            composition: composition.to_owned(),
            weight,
            represented_population,
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
