use super::model::*;
use super::parser::{Line, identifier, parse_archetype_output, require_indent};
use std::collections::BTreeMap;

pub(super) fn parse_composition(
    lines: &[Line],
    start: usize,
    name: &str,
) -> DslResult<(CompositionDefinition, usize)> {
    parse_composition_body(lines, start, name)
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
) -> DslResult<(CompositionDefinition, usize)> {
    identifier(name, lines[start].number)?;
    let mut level = None;
    let mut slice = None;
    let mut graph_group = None;
    let mut default_run = false;
    let mut template = None;
    let mut agent_pool = None;
    let mut entity_count = None;
    let mut entity_unit = None;
    let mut role_targets = BTreeMap::new();
    let mut exemplar_households = None;
    let mut stratum = None;
    let mut stratifiers = BTreeMap::new();
    let mut heterogeneity = 0.0;
    let mut distribution_status = "estimated".to_owned();
    let mut provenance = None;
    let mut clock_minutes = 1_440;
    let mut sync_up_minutes = None;
    let mut represented_population = None;
    let mut authoritative_total = None;
    let mut allocation_leaf = false;
    let mut report_descendants = false;
    let mut entries = Vec::new();
    let mut places = Vec::new();
    let mut parameters = BTreeMap::new();
    let mut policies = Vec::new();
    let mut adjacency = Vec::new();
    let mut leaders = Vec::new();
    let mut outputs = Vec::new();
    let mut index = start + 1;
    while index < lines.len() && lines[index].indent > 0 {
        let line = &lines[index];
        require_indent(line, 2)?;
        if let Some(value) = line.text.strip_prefix("level = ") {
            identifier(value, line.number)?;
            level = Some(value.to_owned());
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("slice = ") {
            slice = Some(parse_quoted(value, line.number)?);
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("graph_group = ") {
            identifier(value, line.number)?;
            graph_group = Some(value.to_owned());
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("default_run = ") {
            default_run = parse_boolean(value, line.number, "INVALID_DEFAULT_RUN")?;
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("template = ") {
            identifier(value, line.number)?;
            template = Some(value.to_owned());
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("agent_pool = ") {
            identifier(value, line.number)?;
            agent_pool = Some(value.to_owned());
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("entity_count = ") {
            entity_count = Some(value.parse::<u64>().map_err(|_| {
                DslError::new(
                    "INVALID_ENTITY_COUNT",
                    line.number,
                    "Entity count must be a positive integer",
                )
            })?);
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("entity_unit = ") {
            entity_unit = Some(parse_quoted(value, line.number)?);
            index += 1;
        } else if line.text == "role_targets:" {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let target = &lines[index];
                require_indent(target, 4)?;
                let (role, count) = target.text.split_once(" = ").ok_or_else(|| {
                    DslError::new(
                        "INVALID_ROLE_TARGET",
                        target.number,
                        "Role targets use role = count",
                    )
                })?;
                identifier(role, target.number)?;
                role_targets.insert(
                    role.to_owned(),
                    count.parse::<u64>().map_err(|_| {
                        DslError::new(
                            "INVALID_ROLE_TARGET",
                            target.number,
                            "Role target must be a non-negative integer",
                        )
                    })?,
                );
                index += 1;
            }
        } else if let Some(value) = line.text.strip_prefix("households_per_exemplar = ") {
            exemplar_households = Some(value.parse::<u32>().map_err(|_| {
                DslError::new(
                    "INVALID_EXEMPLAR_HOUSEHOLDS",
                    line.number,
                    "households_per_exemplar must be an integer",
                )
            })?);
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("stratum = ") {
            stratum = Some(parse_quoted(value, line.number)?);
            index += 1;
        } else if line.text == "stratifiers:" {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let value = &lines[index];
                require_indent(value, 4)?;
                let (id, number) = value.text.split_once(" = ").ok_or_else(|| {
                    DslError::new(
                        "INVALID_STRATIFIER",
                        value.number,
                        "Stratifiers use name = number",
                    )
                })?;
                identifier(id, value.number)?;
                stratifiers.insert(
                    id.to_owned(),
                    number.parse::<f64>().map_err(|_| {
                        DslError::new(
                            "INVALID_STRATIFIER",
                            value.number,
                            "Stratifier value must be numeric",
                        )
                    })?,
                );
                index += 1;
            }
        } else if let Some(value) = line.text.strip_prefix("heterogeneity = ") {
            heterogeneity = value.parse::<f64>().map_err(|_| {
                DslError::new(
                    "INVALID_HETEROGENEITY",
                    line.number,
                    "Heterogeneity must be numeric",
                )
            })?;
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("distribution_status = ") {
            identifier(value, line.number)?;
            distribution_status = value.to_owned();
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("provenance = ") {
            provenance = Some(parse_quoted(value, line.number)?);
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("clock = ") {
            clock_minutes = parse_duration_minutes(value, line.number)?;
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("sync_up = ") {
            sync_up_minutes = Some(parse_duration_minutes(value, line.number)?);
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
        } else if let Some(value) = line.text.strip_prefix("authoritative_total = ") {
            authoritative_total = Some(value.parse::<u64>().map_err(|_| {
                DslError::new(
                    "INVALID_AUTHORITATIVE_TOTAL",
                    line.number,
                    "Authoritative total must be a positive integer",
                )
            })?);
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("allocation_leaf = ") {
            allocation_leaf = match value {
                "true" => true,
                "false" => false,
                _ => {
                    return Err(DslError::new(
                        "INVALID_ALLOCATION_LEAF",
                        line.number,
                        "Allocation leaf must be true or false",
                    ));
                }
            };
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("report_descendants = ") {
            report_descendants = match value {
                "true" => true,
                "false" => false,
                _ => {
                    return Err(DslError::new(
                        "INVALID_DESCENDANT_REPORT",
                        line.number,
                        "report_descendants must be true or false",
                    ));
                }
            };
            index += 1;
        } else if line.text == "children:" || line.text == "entries:" || line.text == "households:"
        {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let entry = &lines[index];
                require_indent(entry, 4)?;
                let (child, weight) = entry
                    .text
                    .split_once(": weight = ")
                    .map_or((entry.text.as_str(), None), |(child, weight)| {
                        (child, Some(weight))
                    });
                identifier(child, entry.number)?;
                let (weight, declared_count) = weight.map_or((None, None), |weight| {
                    weight
                        .split_once(" count = ")
                        .map_or((Some(weight), None), |(weight, count)| {
                            (Some(weight), Some(count))
                        })
                });
                entries.push(CompositionEntry {
                    child: child.to_owned(),
                    weight: weight
                        .map(|weight| {
                            weight.parse::<f64>().map_err(|_| {
                                DslError::new(
                                    "INVALID_COMPOSITION_CHILD",
                                    entry.number,
                                    "Composition weight must be a positive number",
                                )
                            })
                        })
                        .transpose()?,
                    declared_count: declared_count
                        .map(|count| {
                            count.parse::<u64>().map_err(|_| {
                                DslError::new(
                                    "INVALID_DECLARED_ALLOCATION_COUNT",
                                    entry.number,
                                    "Declared allocation count must be a non-negative integer",
                                )
                            })
                        })
                        .transpose()?,
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
        } else if line.text == "leaders:" {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let entry = &lines[index];
                require_indent(entry, 4)?;
                let (role, detail) = entry.text.split_once(": count = ").ok_or_else(|| {
                    DslError::new(
                        "INVALID_COMPOSITION_LEADER",
                        entry.number,
                        "Composition leaders use role: count = number",
                    )
                })?;
                identifier(role, entry.number)?;
                let (count, archetype, source_composition) =
                    parse_leader_detail(detail, entry.number)?;
                leaders.push(CompositionLeaderDefinition {
                    role: role.to_owned(),
                    count,
                    archetype,
                    source_composition,
                    line: entry.number,
                });
                index += 1;
            }
        } else if let Some(value) = line.text.strip_prefix("output ") {
            outputs.push(parse_archetype_output(value, line.number)?);
            index += 1;
        } else {
            return Err(DslError::new(
                "UNKNOWN_COMPOSITION_STATEMENT",
                line.number,
                format!("Unknown composition statement {}", line.text),
            ));
        }
    }
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
            slice,
            graph_group,
            default_run,
            template,
            agent_pool,
            entity_count,
            entity_unit,
            role_targets,
            exemplar_households,
            stratum,
            stratifiers,
            heterogeneity,
            distribution_status,
            provenance,
            clock_minutes,
            sync_up_minutes,
            represented_population,
            authoritative_total,
            allocation_leaf,
            report_descendants,
            entries,
            places,
            parameters,
            policies,
            adjacency,
            leaders,
            outputs,
            line: lines[start].number,
        },
        index,
    ))
}

fn parse_quoted(value: &str, line: usize) -> DslResult<String> {
    value
        .strip_prefix('"')
        .and_then(|value| value.strip_suffix('"'))
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .ok_or_else(|| DslError::new("INVALID_SLICE", line, "Slice must be a quoted string"))
}

fn parse_duration_minutes(value: &str, line: usize) -> DslResult<u64> {
    let (number, unit) = value.split_once(' ').ok_or_else(|| {
        DslError::new(
            "INVALID_COMPOSITION_CLOCK",
            line,
            "Clock values use number minutes, hours, or days",
        )
    })?;
    let number = number.parse::<u64>().map_err(|_| {
        DslError::new(
            "INVALID_COMPOSITION_CLOCK",
            line,
            "Clock value must be a positive integer",
        )
    })?;
    let multiplier = match unit {
        "minute" | "minutes" => 1,
        "hour" | "hours" => 60,
        "day" | "days" => 1_440,
        _ => {
            return Err(DslError::new(
                "INVALID_COMPOSITION_CLOCK",
                line,
                "Clock unit must be minutes, hours, or days",
            ));
        }
    };
    let minutes = number.saturating_mul(multiplier);
    if minutes == 0 {
        return Err(DslError::new(
            "INVALID_COMPOSITION_CLOCK",
            line,
            "Clock value must be positive",
        ));
    }
    Ok(minutes)
}

fn parse_boolean(value: &str, line: usize, code: &str) -> DslResult<bool> {
    match value {
        "true" => Ok(true),
        "false" => Ok(false),
        _ => Err(DslError::new(code, line, "Expected true or false")),
    }
}

fn parse_leader_detail(
    detail: &str,
    line: usize,
) -> DslResult<(usize, Option<String>, Option<String>)> {
    let mut parts = detail.split_whitespace();
    let count = parts
        .next()
        .and_then(|value| value.parse::<usize>().ok())
        .ok_or_else(|| {
            DslError::new(
                "INVALID_COMPOSITION_LEADER",
                line,
                "Composition leader count must be a positive integer",
            )
        })?;
    let mut archetype = None;
    let mut source_composition = None;
    let remaining = parts.collect::<Vec<_>>();
    let mut index = 0;
    while index < remaining.len() {
        if index + 2 >= remaining.len() || remaining[index + 1] != "=" {
            return Err(DslError::new(
                "INVALID_COMPOSITION_LEADER",
                line,
                "Leader linkage uses archetype = Name and source = Composition",
            ));
        }
        identifier(remaining[index + 2], line)?;
        match remaining[index] {
            "archetype" => archetype = Some(remaining[index + 2].to_owned()),
            "source" => source_composition = Some(remaining[index + 2].to_owned()),
            _ => {
                return Err(DslError::new(
                    "INVALID_COMPOSITION_LEADER",
                    line,
                    "Leader linkage supports archetype and source",
                ));
            }
        }
        index += 3;
    }
    Ok((count, archetype, source_composition))
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

pub(super) fn parse_composition_population(
    lines: &[Line],
    start: usize,
    name: &str,
) -> DslResult<(WeightedCompositionPopulation, usize)> {
    parse_composition_population_body(lines, start, name)
}

fn parse_composition_population_body(
    lines: &[Line],
    start: usize,
    name: &str,
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
                        "INVALID_COMPOSITION_WEIGHT",
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
                "INVALID_COMPOSITION_WEIGHT",
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
            line: lines[start].number,
        },
        index,
    ))
}
