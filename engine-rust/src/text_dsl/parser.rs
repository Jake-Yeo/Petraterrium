use super::aggregate_parser::{parse_aggregate_function, validate_aggregate_functions};
use super::expression::{evaluate, parse_expression, references};
use super::model::*;
use super::neighbourhood_parser::{
    parse_neighbourhood, parse_neighbourhood_population, validate_neighbourhoods,
};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone)]
pub(super) struct Line {
    pub(super) number: usize,
    pub(super) indent: usize,
    pub(super) text: String,
}

pub fn parse_program(source: &str) -> DslResult<Program> {
    let lines = source_lines(source)?;
    let Some(first) = lines.first() else {
        return Err(DslError::new("EMPTY_PROGRAM", 1, "DSL program is empty"));
    };
    let (id, version) = parse_program_header(first)?;
    let mut tick_hours = None;
    let mut placeholder_label = None;
    let mut uncertainty = None;
    let mut record_actions = true;
    let mut results_title = None;
    let mut results_subtitle = None;
    let mut places = Vec::new();
    let mut agents = Vec::new();
    let mut population = None;
    let mut decisions = Vec::new();
    let mut actions = Vec::new();
    let mut reports = Vec::new();
    let mut archetypes = Vec::new();
    let mut weighted_populations = Vec::new();
    let mut aggregate_functions = Vec::new();
    let mut neighbourhoods = Vec::new();
    let mut neighbourhood_populations = Vec::new();
    let mut index = 1;
    while index < lines.len() {
        let line = &lines[index];
        if line.indent == 2 {
            if let Some(value) = line.text.strip_prefix("tick_hours = ") {
                tick_hours = Some(number_with_placeholder(value, line.number)?);
            } else if let Some(value) = line.text.strip_prefix("placeholder = ") {
                placeholder_label = Some(quoted(value, line.number)?);
            } else if let Some(value) = line.text.strip_prefix("uncertainty = ") {
                uncertainty = Some(value.trim().to_owned());
            } else if let Some(value) = line.text.strip_prefix("record_actions = ") {
                record_actions = match value {
                    "true" => true,
                    "false" => false,
                    _ => {
                        return Err(DslError::new(
                            "INVALID_BOOLEAN",
                            line.number,
                            "record_actions must be true or false",
                        ));
                    }
                };
            } else if let Some(value) = line.text.strip_prefix("results_title = ") {
                results_title = Some(quoted(value, line.number)?);
            } else if let Some(value) = line.text.strip_prefix("results_subtitle = ") {
                results_subtitle = Some(quoted(value, line.number)?);
            } else {
                return Err(DslError::new(
                    "UNKNOWN_PROGRAM_SETTING",
                    line.number,
                    format!("Unknown program setting {}", line.text),
                ));
            }
            index += 1;
            continue;
        }
        if line.indent != 0 {
            return Err(DslError::new(
                "INVALID_INDENTATION",
                line.number,
                "Top-level declarations cannot be indented",
            ));
        }
        if let Some(name) = block_name(&line.text, "place") {
            let (value, next) = parse_place(&lines, index, name)?;
            places.push(value);
            index = next;
        } else if let Some((name, parent)) = agent_header(&line.text) {
            let (value, next) = parse_agent(&lines, index, name, parent)?;
            agents.push(value);
            index = next;
        } else if line.text == "population:" {
            let (value, next) = parse_population(&lines, index)?;
            population = Some(value);
            index = next;
        } else if let Some(name) = block_name(&line.text, "archetype") {
            let (value, next) = parse_archetype(&lines, index, name)?;
            archetypes.push(value);
            index = next;
        } else if let Some(name) = block_name(&line.text, "population") {
            let (value, next) = parse_weighted_population(&lines, index, name)?;
            weighted_populations.push(value);
            index = next;
        } else if let Some(name) = block_name(&line.text, "aggregate_function") {
            let (value, next) = parse_aggregate_function(&lines, index, name)?;
            aggregate_functions.push(value);
            index = next;
        } else if let Some(name) = block_name(&line.text, "neighbourhood") {
            let (value, next) = parse_neighbourhood(&lines, index, name)?;
            neighbourhoods.push(value);
            index = next;
        } else if let Some(name) = block_name(&line.text, "neighbourhood_population") {
            let (value, next) = parse_neighbourhood_population(&lines, index, name)?;
            neighbourhood_populations.push(value);
            index = next;
        } else if let Some(name) = block_name(&line.text, "decision") {
            let (value, next) = parse_decision(&lines, index, name)?;
            decisions.push(value);
            index = next;
        } else if let Some(name) = block_name(&line.text, "action") {
            let (value, next) = parse_action(&lines, index, name)?;
            actions.push(value);
            index = next;
        } else if let Some(name) = block_name(&line.text, "output") {
            let (value, next) = parse_report(&lines, index, name)?;
            reports.push(value);
            index = next;
        } else {
            return Err(DslError::new(
                "UNKNOWN_DECLARATION",
                line.number,
                format!("Unknown declaration {}", line.text),
            ));
        }
    }
    let program = Program {
        id,
        version,
        tick_hours: tick_hours.ok_or_else(|| {
            DslError::new(
                "MISSING_TICK_HOURS",
                first.number,
                "Program needs tick_hours",
            )
        })?,
        placeholder_label: placeholder_label.ok_or_else(|| {
            DslError::new(
                "MISSING_PLACEHOLDER_LABEL",
                first.number,
                "Program needs the placeholder label",
            )
        })?,
        uncertainty: uncertainty.ok_or_else(|| {
            DslError::new(
                "MISSING_UNCERTAINTY",
                first.number,
                "Program needs uncertainty",
            )
        })?,
        record_actions,
        results_title: results_title.ok_or_else(|| {
            DslError::new(
                "MISSING_RESULTS_TITLE",
                first.number,
                "Program needs results_title",
            )
        })?,
        results_subtitle: results_subtitle.ok_or_else(|| {
            DslError::new(
                "MISSING_RESULTS_SUBTITLE",
                first.number,
                "Program needs results_subtitle",
            )
        })?,
        places,
        agents,
        population: population.ok_or_else(|| {
            DslError::new(
                "MISSING_POPULATION",
                first.number,
                "Program needs population",
            )
        })?,
        decisions,
        actions,
        reports,
        archetypes,
        weighted_populations,
        aggregate_functions,
        neighbourhoods,
        neighbourhood_populations,
    };
    validate_program(&program)?;
    Ok(program)
}

fn source_lines(source: &str) -> DslResult<Vec<Line>> {
    let mut result = Vec::new();
    for (index, raw) in source.lines().enumerate() {
        let number = index + 1;
        let value = strip_comment(raw);
        if value.trim().is_empty() {
            continue;
        }
        if value.contains('\t') {
            return Err(DslError::new(
                "INVALID_INDENTATION",
                number,
                "DSL indentation uses spaces",
            ));
        }
        let indent = value.len() - value.trim_start_matches(' ').len();
        if indent % 2 != 0 {
            return Err(DslError::new(
                "INVALID_INDENTATION",
                number,
                "DSL indentation uses multiples of two spaces",
            ));
        }
        result.push(Line {
            number,
            indent,
            text: value.trim().to_owned(),
        });
    }
    Ok(result)
}

fn strip_comment(value: &str) -> String {
    let mut quoted = false;
    let mut escaped = false;
    for (index, character) in value.char_indices() {
        if escaped {
            escaped = false;
            continue;
        }
        if character == '\\' {
            escaped = true;
            continue;
        }
        if character == '"' {
            quoted = !quoted;
        }
        if character == '#' && !quoted {
            return value[..index].trim_end().to_owned();
        }
    }
    value.trim_end().to_owned()
}

fn parse_program_header(line: &Line) -> DslResult<(String, String)> {
    if line.indent != 0 || !line.text.starts_with("program ") || !line.text.ends_with(':') {
        return Err(DslError::new(
            "INVALID_PROGRAM_HEADER",
            line.number,
            "Program header is: program Name version \"1.0\":",
        ));
    }
    let body = line
        .text
        .trim_end_matches(':')
        .strip_prefix("program ")
        .unwrap();
    let Some((id, version)) = body.split_once(" version ") else {
        return Err(DslError::new(
            "INVALID_PROGRAM_HEADER",
            line.number,
            "Program header needs a version",
        ));
    };
    identifier(id, line.number)?;
    Ok((id.to_owned(), quoted(version, line.number)?))
}

fn parse_place(lines: &[Line], start: usize, name: &str) -> DslResult<(PlaceDefinition, usize)> {
    identifier(name, lines[start].number)?;
    let mut states = BTreeMap::new();
    let mut state_bounds = BTreeMap::new();
    let mut index = start + 1;
    while index < lines.len() && lines[index].indent > 0 {
        let line = &lines[index];
        require_indent(line, 2)?;
        let Some(value) = line.text.strip_prefix("state ") else {
            return Err(DslError::new(
                "UNKNOWN_PLACE_STATEMENT",
                line.number,
                format!("Unknown place statement {}", line.text),
            ));
        };
        let Some((field, value)) = value.split_once(" = ") else {
            return Err(DslError::new(
                "INVALID_PLACE_STATE",
                line.number,
                "Place state needs =",
            ));
        };
        identifier(field, line.number)?;
        let (value, bounds) = split_range(value, line.number)?;
        states.insert(
            field.to_owned(),
            literal_with_placeholder(&value, line.number)?,
        );
        if let Some(bounds) = bounds {
            state_bounds.insert(field.to_owned(), bounds);
        }
        index += 1;
    }
    Ok((
        PlaceDefinition {
            id: name.to_owned(),
            states,
            state_bounds,
            line: lines[start].number,
        },
        index,
    ))
}

fn parse_agent(
    lines: &[Line],
    start: usize,
    name: &str,
    parent: Option<String>,
) -> DslResult<(AgentDefinition, usize)> {
    identifier(name, lines[start].number)?;
    let mut roles = BTreeSet::new();
    let mut traits = BTreeSet::new();
    let mut states = BTreeSet::new();
    let mut state_bounds = BTreeMap::new();
    let mut initial = Vec::new();
    let mut routine = None;
    let mut index = start + 1;
    while index < lines.len() && lines[index].indent > 0 {
        let line = &lines[index];
        require_indent(line, 2)?;
        if let Some(value) = line.text.strip_prefix("role ") {
            identifier(value, line.number)?;
            roles.insert(value.to_owned());
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("trait ") {
            identifier(value, line.number)?;
            traits.insert(value.to_owned());
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("state ") {
            let (name, bounds) = if let Some((name, bounds)) = value.split_once(" range ") {
                (
                    name,
                    Some(parse_bounds(
                        remove_placeholder(bounds, line.number)?,
                        line.number,
                    )?),
                )
            } else {
                (value, None)
            };
            identifier(name, line.number)?;
            states.insert(name.to_owned());
            if let Some(bounds) = bounds {
                state_bounds.insert(name.to_owned(), bounds);
            }
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("routine = ") {
            identifier(value, line.number)?;
            routine = Some(value.to_owned());
            index += 1;
        } else if line.text == "initial:" {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let assignment = &lines[index];
                require_indent(assignment, 4)?;
                initial.push(parse_initial_assignment(assignment)?);
                index += 1;
            }
        } else {
            return Err(DslError::new(
                "UNKNOWN_AGENT_STATEMENT",
                line.number,
                format!("Unknown agent statement {}", line.text),
            ));
        }
    }
    Ok((
        AgentDefinition {
            id: name.to_owned(),
            parent,
            roles,
            traits,
            states,
            state_bounds,
            initial,
            routine: routine.unwrap_or_default(),
            line: lines[start].number,
        },
        index,
    ))
}

fn parse_initial_assignment(line: &Line) -> DslResult<InitialAssignment> {
    let value = remove_placeholder(&line.text, line.number)?;
    let Some((field, distribution)) = value.split_once(" ~ ") else {
        return Err(DslError::new(
            "INVALID_INITIAL_ASSIGNMENT",
            line.number,
            "Initial assignment needs ~",
        ));
    };
    identifier(field, line.number)?;
    Ok(InitialAssignment {
        field: field.to_owned(),
        distribution: parse_distribution(distribution, line.number)?,
        line: line.number,
    })
}

fn parse_distribution(value: &str, line: usize) -> DslResult<DistributionSpec> {
    let Some(open) = value.find('(') else {
        return Err(DslError::new(
            "INVALID_DISTRIBUTION",
            line,
            "Distribution needs parentheses",
        ));
    };
    if !value.ends_with(')') {
        return Err(DslError::new(
            "INVALID_DISTRIBUTION",
            line,
            "Distribution is missing a closing parenthesis",
        ));
    }
    let kind = &value[..open];
    if !matches!(
        kind,
        "Bernoulli"
            | "Categorical"
            | "Normal"
            | "LogNormal"
            | "Uniform"
            | "Beta"
            | "Poisson"
            | "Triangular"
    ) {
        return Err(DslError::new(
            "UNKNOWN_DISTRIBUTION",
            line,
            format!("Unknown distribution {kind}"),
        ));
    }
    let arguments = split_top_level(&value[open + 1..value.len() - 1], ',');
    let mut parameters = BTreeMap::new();
    let mut categories = Vec::new();
    for argument in arguments {
        if kind == "Categorical" {
            let Some((category, expression)) = argument.split_once(':') else {
                return Err(DslError::new(
                    "INVALID_DISTRIBUTION",
                    line,
                    "Categorical entries use value: probability",
                ));
            };
            categories.push((
                category.trim().to_owned(),
                parse_expression(expression.trim(), line)?,
            ));
        } else {
            let Some((name, expression)) = argument.split_once('=') else {
                return Err(DslError::new(
                    "INVALID_DISTRIBUTION",
                    line,
                    "Distribution parameters use name=value",
                ));
            };
            parameters.insert(
                name.trim().to_owned(),
                parse_expression(expression.trim(), line)?,
            );
        }
    }
    if kind == "Categorical" {
        let empty = BTreeMap::new();
        let values = categories
            .iter()
            .map(|(_, expression)| {
                evaluate(expression, &empty).and_then(|value| {
                    value.as_f64().ok_or_else(|| {
                        DslError::new(
                            "INVALID_DISTRIBUTION",
                            line,
                            "Categorical probabilities must be numeric",
                        )
                    })
                })
            })
            .collect::<DslResult<Vec<_>>>()?;
        if values.iter().any(|value| *value < 0.0)
            || (values.iter().sum::<f64>() - 1.0).abs() > 1e-9
        {
            return Err(DslError::new(
                "PROBABILITIES_NOT_ONE",
                line,
                "Categorical probabilities must sum to 1",
            ));
        }
    }
    Ok(DistributionSpec {
        kind: kind.to_owned(),
        parameters,
        categories,
        line,
    })
}

fn parse_population(lines: &[Line], start: usize) -> DslResult<(PopulationDefinition, usize)> {
    let mut size = None;
    let mut mix = Vec::new();
    let mut child_generation = None;
    let mut index = start + 1;
    while index < lines.len() && lines[index].indent > 0 {
        let line = &lines[index];
        require_indent(line, 2)?;
        if let Some(value) = line.text.strip_prefix("size = ") {
            size = Some(number_with_placeholder(value, line.number)? as usize);
            index += 1;
        } else if line.text == "mix:" {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let entry = &lines[index];
                require_indent(entry, 4)?;
                let value = remove_placeholder(&entry.text, entry.number)?;
                let Some((agent_type, probability)) = value.split_once(" = ") else {
                    return Err(DslError::new(
                        "INVALID_POPULATION_MIX",
                        entry.number,
                        "Population mix entries need =",
                    ));
                };
                mix.push(PopulationMix {
                    agent_type: agent_type.to_owned(),
                    probability: probability.parse().map_err(|_| {
                        DslError::new(
                            "INVALID_POPULATION_MIX",
                            entry.number,
                            "Population mix probability must be numeric",
                        )
                    })?,
                    line: entry.number,
                });
                index += 1;
            }
        } else if line.text == "households:" {
            index += 1;
            if index >= lines.len() || lines[index].indent != 4 {
                return Err(DslError::new(
                    "INVALID_HOUSEHOLDS",
                    line.number,
                    "Households need a child generation rule",
                ));
            }
            let generate = &lines[index];
            let condition_source = generate
                .text
                .strip_prefix("generate children where ")
                .and_then(|value| value.strip_suffix(':'))
                .ok_or_else(|| {
                    DslError::new(
                        "INVALID_HOUSEHOLDS",
                        generate.number,
                        "Child generation is: generate children where condition:",
                    )
                })?;
            let condition = parse_expression(condition_source, generate.number)?;
            index += 1;
            let mut count = None;
            let mut age = None;
            let mut agent_type = None;
            let mut links = Vec::new();
            while index < lines.len() && lines[index].indent > 4 {
                let detail = &lines[index];
                require_indent(detail, 6)?;
                if let Some(value) = detail.text.strip_prefix("count = ") {
                    count = Some(parse_expression(value, detail.number)?);
                } else if let Some(value) = detail.text.strip_prefix("age ~ ") {
                    age = Some(parse_distribution(
                        remove_placeholder(value, detail.number)?,
                        detail.number,
                    )?);
                } else if let Some(value) = detail.text.strip_prefix("type = ") {
                    agent_type = Some(parse_expression(value, detail.number)?);
                } else if let Some(value) = detail.text.strip_prefix("link = ") {
                    links = value
                        .split(',')
                        .map(|item| item.trim().to_owned())
                        .collect();
                } else {
                    return Err(DslError::new(
                        "UNKNOWN_HOUSEHOLD_STATEMENT",
                        detail.number,
                        format!("Unknown household statement {}", detail.text),
                    ));
                }
                index += 1;
            }
            child_generation = Some(ChildGeneration {
                condition,
                count: count.ok_or_else(|| {
                    DslError::new("INVALID_HOUSEHOLDS", generate.number, "Children need count")
                })?,
                age: age.ok_or_else(|| {
                    DslError::new("INVALID_HOUSEHOLDS", generate.number, "Children need age")
                })?,
                agent_type: agent_type.ok_or_else(|| {
                    DslError::new("INVALID_HOUSEHOLDS", generate.number, "Children need type")
                })?,
                links,
                line: generate.number,
            });
        } else {
            return Err(DslError::new(
                "UNKNOWN_POPULATION_STATEMENT",
                line.number,
                format!("Unknown population statement {}", line.text),
            ));
        }
    }
    let total = mix.iter().map(|entry| entry.probability).sum::<f64>();
    if (total - 1.0).abs() > 1e-9 {
        return Err(DslError::new(
            "PROBABILITIES_NOT_ONE",
            lines[start].number,
            format!("Population mix probabilities total {total}"),
        ));
    }
    Ok((
        PopulationDefinition {
            size: size.ok_or_else(|| {
                DslError::new(
                    "MISSING_POPULATION_SIZE",
                    lines[start].number,
                    "Population needs size",
                )
            })?,
            mix,
            child_generation,
        },
        index,
    ))
}

fn parse_archetype(
    lines: &[Line],
    start: usize,
    name: &str,
) -> DslResult<(ArchetypeDefinition, usize)> {
    identifier(name, lines[start].number)?;
    let mut sample_households = None;
    let mut composition = Vec::new();
    let mut initial = Vec::new();
    let mut decision_multipliers = Vec::new();
    let mut outputs = Vec::new();
    let mut index = start + 1;
    while index < lines.len() && lines[index].indent > 0 {
        let line = &lines[index];
        require_indent(line, 2)?;
        if let Some(value) = line.text.strip_prefix("sample_households = ") {
            sample_households = Some(value.parse::<usize>().map_err(|_| {
                DslError::new(
                    "INVALID_ARCHETYPE_SAMPLE",
                    line.number,
                    "sample_households must be a positive integer",
                )
            })?);
            index += 1;
        } else if line.text == "composition:" {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let entry = &lines[index];
                require_indent(entry, 4)?;
                composition.push(parse_archetype_composition(entry)?);
                index += 1;
            }
        } else if line.text == "initial:" {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let entry = &lines[index];
                require_indent(entry, 4)?;
                let estimated = Line {
                    number: entry.number,
                    indent: entry.indent,
                    text: format!("{} placeholder", entry.text),
                };
                initial.push(parse_initial_assignment(&estimated)?);
                index += 1;
            }
        } else if let Some(value) = line.text.strip_prefix("decision ") {
            let Some((action, multiplier)) = value.split_once(" multiplier = ") else {
                return Err(DslError::new(
                    "INVALID_ARCHETYPE_DECISION",
                    line.number,
                    "Archetype decision uses: decision action multiplier = number",
                ));
            };
            decision_multipliers.push(ArchetypeDecisionMultiplier {
                action: action.to_owned(),
                multiplier: multiplier.parse::<f64>().map_err(|_| {
                    DslError::new(
                        "INVALID_ARCHETYPE_DECISION",
                        line.number,
                        "Decision multiplier must be numeric",
                    )
                })?,
                line: line.number,
            });
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("output ") {
            outputs.push(parse_archetype_output(value, line.number)?);
            index += 1;
        } else {
            return Err(DslError::new(
                "UNKNOWN_ARCHETYPE_STATEMENT",
                line.number,
                format!("Unknown archetype statement {}", line.text),
            ));
        }
    }
    Ok((
        ArchetypeDefinition {
            id: name.to_owned(),
            sample_households: sample_households.ok_or_else(|| {
                DslError::new(
                    "MISSING_ARCHETYPE_SAMPLE",
                    lines[start].number,
                    format!("Archetype {name} needs sample_households"),
                )
            })?,
            composition,
            initial,
            decision_multipliers,
            outputs,
            line: lines[start].number,
        },
        index,
    ))
}

fn parse_archetype_composition(line: &Line) -> DslResult<ArchetypeCompositionGroup> {
    let Some((id, value)) = line.text.split_once(" count = ") else {
        return Err(DslError::new(
            "INVALID_ARCHETYPE_COMPOSITION",
            line.number,
            "Composition uses: group count = number mix Type:probability",
        ));
    };
    identifier(id, line.number)?;
    let Some((count, mix_source)) = value.split_once(" mix ") else {
        return Err(DslError::new(
            "INVALID_ARCHETYPE_COMPOSITION",
            line.number,
            "Composition needs an agent mix",
        ));
    };
    let count = count.parse::<usize>().map_err(|_| {
        DslError::new(
            "INVALID_ARCHETYPE_COMPOSITION",
            line.number,
            "Composition count must be a positive integer",
        )
    })?;
    let mut mix = Vec::new();
    for entry in mix_source.split(',') {
        let Some((agent_type, probability)) = entry.trim().split_once(':') else {
            return Err(DslError::new(
                "INVALID_ARCHETYPE_COMPOSITION",
                line.number,
                "Composition mix entries use Agent:probability",
            ));
        };
        mix.push(PopulationMix {
            agent_type: agent_type.trim().to_owned(),
            probability: probability.trim().parse::<f64>().map_err(|_| {
                DslError::new(
                    "INVALID_ARCHETYPE_COMPOSITION",
                    line.number,
                    "Composition probability must be numeric",
                )
            })?,
            line: line.number,
        });
    }
    let total = mix.iter().map(|entry| entry.probability).sum::<f64>();
    if (total - 1.0).abs() > 1e-9 {
        return Err(DslError::new(
            "PROBABILITIES_NOT_ONE",
            line.number,
            format!("Composition mix probabilities total {total}"),
        ));
    }
    Ok(ArchetypeCompositionGroup {
        id: id.to_owned(),
        count,
        mix,
        line: line.number,
    })
}

pub(super) fn parse_archetype_output(
    value: &str,
    line: usize,
) -> DslResult<ArchetypeOutputDefinition> {
    let Some((id, metric)) = value.split_once(" = ") else {
        return Err(DslError::new(
            "INVALID_ARCHETYPE_OUTPUT",
            line,
            "Archetype output needs =",
        ));
    };
    identifier(id, line)?;
    let (metric, spread) = metric
        .strip_suffix(" with sd")
        .map_or((metric, false), |value| (value, true));
    let (metric, filter) = split_where(metric);
    Ok(ArchetypeOutputDefinition {
        id: id.to_owned(),
        metric: parse_report_metric(metric, line)?,
        filter: filter
            .map(|value| parse_expression(value, line))
            .transpose()?,
        spread,
        line,
    })
}

fn parse_weighted_population(
    lines: &[Line],
    start: usize,
    name: &str,
) -> DslResult<(WeightedPopulationDefinition, usize)> {
    identifier(name, lines[start].number)?;
    let mut entries = Vec::new();
    let mut index = start + 1;
    while index < lines.len() && lines[index].indent > 0 {
        let line = &lines[index];
        require_indent(line, 2)?;
        let Some((archetype, weight)) = line.text.split_once(": weight = ") else {
            return Err(DslError::new(
                "INVALID_POPULATION_WEIGHT",
                line.number,
                "Population entries use: Archetype: weight = count",
            ));
        };
        entries.push(WeightedPopulationEntry {
            archetype: archetype.to_owned(),
            weight: weight.parse::<u64>().map_err(|_| {
                DslError::new(
                    "INVALID_POPULATION_WEIGHT",
                    line.number,
                    "Population weight must be a positive integer",
                )
            })?,
            line: line.number,
        });
        index += 1;
    }
    Ok((
        WeightedPopulationDefinition {
            id: name.to_owned(),
            entries,
            line: lines[start].number,
        },
        index,
    ))
}

fn parse_decision(
    lines: &[Line],
    start: usize,
    name: &str,
) -> DslResult<(DecisionDefinition, usize)> {
    let mut branches = Vec::new();
    let mut index = start + 1;
    while index < lines.len() && lines[index].indent > 0 {
        let line = &lines[index];
        require_indent(line, 2)?;
        let value = remove_placeholder(&line.text, line.number)?;
        let value = value.strip_prefix("branch ").ok_or_else(|| {
            DslError::new(
                "UNKNOWN_DECISION_STATEMENT",
                line.number,
                "Decision statements are branches",
            )
        })?;
        let Some((action, probability_and_condition)) = value.split_once(" p = ") else {
            return Err(DslError::new(
                "INVALID_DECISION_BRANCH",
                line.number,
                "Decision branch needs p = formula",
            ));
        };
        let (probability, condition) = split_if(probability_and_condition);
        branches.push(DecisionBranch {
            action: action.to_owned(),
            probability: parse_expression(probability, line.number)?,
            condition: condition
                .map(|value| parse_expression(value, line.number))
                .transpose()?,
            line: line.number,
        });
        index += 1;
    }
    Ok((
        DecisionDefinition {
            id: name.to_owned(),
            branches,
            line: lines[start].number,
        },
        index,
    ))
}

fn parse_action(lines: &[Line], start: usize, name: &str) -> DslResult<(ActionDefinition, usize)> {
    let mut duration = None;
    let mut long = false;
    let mut aggregate = None;
    let mut target = None;
    let mut outcomes = Vec::new();
    let mut index = start + 1;
    while index < lines.len() && lines[index].indent > 0 {
        let line = &lines[index];
        require_indent(line, 2)?;
        if let Some(value) = line.text.strip_prefix("aggregate = ") {
            identifier(value, line.number)?;
            aggregate = Some(value.to_owned());
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("duration = ") {
            duration = Some(parse_duration(
                remove_placeholder(value, line.number)?,
                line.number,
            )?);
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("long = ") {
            long = bool_with_placeholder(value, line.number)?;
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("target = ") {
            target = Some(parse_target(value, line.number)?);
            index += 1;
        } else if line.text.starts_with("outcome ") {
            let (outcome, next) = parse_outcome(lines, index)?;
            outcomes.push(outcome);
            index = next;
        } else {
            return Err(DslError::new(
                "UNKNOWN_ACTION_STATEMENT",
                line.number,
                format!("Unknown action statement {}", line.text),
            ));
        }
    }
    let duration = duration.ok_or_else(|| {
        DslError::new(
            "MISSING_DURATION",
            lines[start].number,
            format!("Action {name} needs duration"),
        )
    })?;
    if duration.maximum > 24.0 {
        return Err(DslError::new(
            "DURATION_OUT_OF_RANGE",
            duration.line,
            "Action duration cannot exceed 24 hours",
        ));
    }
    Ok((
        ActionDefinition {
            id: name.to_owned(),
            aggregate: aggregate.ok_or_else(|| {
                DslError::new(
                    "MISSING_AGGREGATE",
                    lines[start].number,
                    format!("Action {name} needs aggregate"),
                )
            })?,
            duration,
            long,
            target,
            outcomes,
            line: lines[start].number,
        },
        index,
    ))
}

fn parse_report(lines: &[Line], start: usize, name: &str) -> DslResult<(ReportDefinition, usize)> {
    identifier(name, lines[start].number)?;
    let mut title = None;
    let mut group_by = None;
    let mut display = None;
    let mut record = None;
    let mut columns = Vec::new();
    let mut index = start + 1;
    while index < lines.len() && lines[index].indent > 0 {
        let line = &lines[index];
        require_indent(line, 2)?;
        if let Some(value) = line.text.strip_prefix("title = ") {
            title = Some(quoted(value, line.number)?);
        } else if let Some(value) = line.text.strip_prefix("group_by = ") {
            group_by = Some(value.to_owned());
        } else if let Some(value) = line.text.strip_prefix("display = ") {
            display = Some(value.to_owned());
        } else if let Some(value) = line.text.strip_prefix("record = ") {
            record = Some(value.to_owned());
        } else if line.text.starts_with("column ") {
            columns.push(parse_report_column(line)?);
        } else {
            return Err(DslError::new(
                "UNKNOWN_OUTPUT_STATEMENT",
                line.number,
                format!("Unknown output statement {}", line.text),
            ));
        }
        index += 1;
    }
    Ok((
        ReportDefinition {
            id: name.to_owned(),
            title: title.ok_or_else(|| {
                DslError::new(
                    "MISSING_OUTPUT_TITLE",
                    lines[start].number,
                    format!("Output {name} needs a title"),
                )
            })?,
            group_by: group_by.ok_or_else(|| {
                DslError::new(
                    "MISSING_OUTPUT_GROUP",
                    lines[start].number,
                    format!("Output {name} needs group_by"),
                )
            })?,
            display: display.ok_or_else(|| {
                DslError::new(
                    "MISSING_OUTPUT_DISPLAY",
                    lines[start].number,
                    format!("Output {name} needs display"),
                )
            })?,
            record: record.ok_or_else(|| {
                DslError::new(
                    "MISSING_OUTPUT_CADENCE",
                    lines[start].number,
                    format!("Output {name} needs record"),
                )
            })?,
            columns,
            line: lines[start].number,
        },
        index,
    ))
}

fn parse_report_column(line: &Line) -> DslResult<ReportColumnDefinition> {
    let value = line.text.strip_prefix("column ").unwrap();
    let Some((id, value)) = value.split_once(" = ") else {
        return Err(DslError::new(
            "INVALID_OUTPUT_COLUMN",
            line.number,
            "Output column needs =",
        ));
    };
    identifier(id, line.number)?;
    let Some((value, format)) = value.rsplit_once(" format ") else {
        return Err(DslError::new(
            "INVALID_OUTPUT_COLUMN",
            line.number,
            "Output column needs format",
        ));
    };
    let Some((metric, label)) = value.rsplit_once(" label ") else {
        return Err(DslError::new(
            "INVALID_OUTPUT_COLUMN",
            line.number,
            "Output column needs a label",
        ));
    };
    Ok(ReportColumnDefinition {
        id: id.to_owned(),
        label: quoted(label, line.number)?,
        format: format.to_owned(),
        metric: parse_report_metric(metric, line.number)?,
        line: line.number,
    })
}

pub(super) fn parse_report_metric(value: &str, line: usize) -> DslResult<ReportMetric> {
    let Some((name, arguments)) = value.split_once('(') else {
        return Err(DslError::new(
            "INVALID_OUTPUT_METRIC",
            line,
            "Output metric must be a function call",
        ));
    };
    let arguments = arguments.strip_suffix(')').ok_or_else(|| {
        DslError::new(
            "INVALID_OUTPUT_METRIC",
            line,
            "Output metric call needs a closing parenthesis",
        )
    })?;
    let parts = if arguments.trim().is_empty() {
        Vec::new()
    } else {
        split_top_level(arguments, ',')
    };
    let positional = parts
        .iter()
        .filter(|value| !value.contains('='))
        .copied()
        .collect::<Vec<_>>();
    let named = parts
        .iter()
        .filter_map(|value| value.split_once('='))
        .map(|(key, value)| (key.trim(), value.trim()))
        .collect::<BTreeMap<_, _>>();
    if positional.len() + named.len() != parts.len() {
        return Err(DslError::new(
            "INVALID_OUTPUT_METRIC",
            line,
            "Output metric arguments must be unique",
        ));
    }
    let window = || named.get("window").copied().unwrap_or("day").to_owned();
    match name {
        "count" if parts.is_empty() => Ok(ReportMetric::Count),
        "mean" if positional.len() == 1 && named.is_empty() => Ok(ReportMetric::Mean {
            field: positional[0].to_owned(),
        }),
        "sum" if positional.len() == 1 && named.is_empty() => Ok(ReportMetric::Sum {
            field: positional[0].to_owned(),
        }),
        "action_count" if positional.len() == 1 && named.keys().all(|key| *key == "window") => {
            Ok(ReportMetric::ActionCount {
                aggregate: positional[0].to_owned(),
                window: window(),
            })
        }
        "outcome_count" if positional.len() == 1 && named.keys().all(|key| *key == "window") => {
            let Some((action, outcome)) = positional[0].split_once('.') else {
                return Err(DslError::new(
                    "INVALID_OUTPUT_METRIC",
                    line,
                    "outcome_count uses action.outcome",
                ));
            };
            Ok(ReportMetric::OutcomeCount {
                action: action.to_owned(),
                outcome: outcome.to_owned(),
                window: window(),
            })
        }
        "action_rates"
            if positional.is_empty()
                && named.keys().all(|key| matches!(*key, "per" | "window")) =>
        {
            let per = named
                .get("per")
                .ok_or_else(|| {
                    DslError::new("INVALID_OUTPUT_METRIC", line, "action_rates needs per")
                })?
                .parse::<f64>()
                .map_err(|_| {
                    DslError::new(
                        "INVALID_OUTPUT_METRIC",
                        line,
                        "action_rates per must be numeric",
                    )
                })?;
            Ok(ReportMetric::ActionRates {
                per,
                window: window(),
            })
        }
        "family_size" if parts.is_empty() => Ok(ReportMetric::FamilySize),
        "kids_per_family" if parts.is_empty() => Ok(ReportMetric::KidsPerFamily),
        _ => Err(DslError::new(
            "INVALID_OUTPUT_METRIC",
            line,
            format!("Unknown or malformed output metric {value}"),
        )),
    }
}

fn parse_duration(value: &str, line: usize) -> DslResult<DurationSpec> {
    let distribution = parse_distribution(value, line)?;
    if !matches!(
        distribution.kind.as_str(),
        "Triangular" | "Uniform" | "LogNormal"
    ) {
        return Err(DslError::new(
            "INVALID_DURATION",
            line,
            "Duration uses Triangular, Uniform, or LogNormal",
        ));
    }
    let empty = BTreeMap::new();
    let parameter = |name: &str| -> DslResult<f64> {
        distribution
            .parameters
            .get(name)
            .ok_or_else(|| {
                DslError::new(
                    "INVALID_DURATION",
                    line,
                    format!("Duration is missing {name}"),
                )
            })
            .and_then(|value| {
                evaluate(value, &empty)?.as_f64().ok_or_else(|| {
                    DslError::new("INVALID_DURATION", line, "Duration values must be numeric")
                })
            })
    };
    let minimum = parameter("min")?;
    let maximum = parameter("max")?;
    let median = if distribution.kind == "Uniform" {
        (minimum + maximum) / 2.0
    } else {
        parameter("median")?
    };
    if minimum < 0.0 || minimum > median || median > maximum || maximum <= minimum {
        return Err(DslError::new(
            "UNORDERED_DURATION",
            line,
            "Duration must be ordered min, median, max",
        ));
    }
    Ok(DurationSpec {
        shape: distribution.kind.to_lowercase(),
        minimum,
        median,
        maximum,
        sigma: distribution
            .parameters
            .get("sigma")
            .map(|value| {
                evaluate(value, &empty).and_then(|value| {
                    value.as_f64().ok_or_else(|| {
                        DslError::new("INVALID_DURATION", line, "Duration sigma must be numeric")
                    })
                })
            })
            .transpose()?,
        truncatable: false,
        line,
    })
}

fn parse_target(value: &str, line: usize) -> DslResult<TargetSelector> {
    if let Some(value) = value.strip_prefix("random at ") {
        let (place, filter) = split_where(value);
        return Ok(TargetSelector::Random {
            place: place.to_owned(),
            filter: filter
                .map(|value| parse_expression(value, line))
                .transpose()?,
        });
    }
    for (prefix, constructor) in [("friend at ", 0), ("enemy at ", 1)] {
        if let Some(place) = value.strip_prefix(prefix) {
            return Ok(if constructor == 0 {
                TargetSelector::Friend {
                    place: place.to_owned(),
                }
            } else {
                TargetSelector::Enemy {
                    place: place.to_owned(),
                }
            });
        }
    }
    if let Some(value) = value.strip_prefix("strongest at ") {
        let Some((place, field)) = value.split_once(" by ") else {
            return Err(DslError::new(
                "INVALID_TARGET",
                line,
                "Strongest target needs by field",
            ));
        };
        return Ok(TargetSelector::Strongest {
            place: place.to_owned(),
            field: field.to_owned(),
        });
    }
    Err(DslError::new(
        "INVALID_TARGET",
        line,
        format!("Unknown target selector {value}"),
    ))
}

fn parse_outcome(lines: &[Line], start: usize) -> DslResult<(OutcomeDefinition, usize)> {
    let line = &lines[start];
    let header = line
        .text
        .strip_prefix("outcome ")
        .and_then(|value| value.strip_suffix(':'))
        .ok_or_else(|| {
            DslError::new(
                "INVALID_OUTCOME",
                line.number,
                "Outcome header needs a colon",
            )
        })?;
    let header = remove_placeholder(header, line.number)?;
    let Some((id, probability_and_condition)) = header.split_once(" p = ") else {
        return Err(DslError::new(
            "INVALID_OUTCOME",
            line.number,
            "Outcome needs p = formula",
        ));
    };
    let (probability, condition) = split_if(probability_and_condition);
    let mut effects = Vec::new();
    let mut next_decision = None;
    let mut target_next_decision = None;
    let mut index = start + 1;
    while index < lines.len() && lines[index].indent > 2 {
        let detail = &lines[index];
        require_indent(detail, 4)?;
        if let Some(value) = detail.text.strip_prefix("effect ") {
            effects.push(parse_effect(
                remove_placeholder(value, detail.number)?,
                detail.number,
            )?);
        } else if let Some(value) = detail.text.strip_prefix("next = ") {
            next_decision = Some(value.to_owned());
        } else if let Some(value) = detail.text.strip_prefix("target_next = ") {
            target_next_decision = Some(value.to_owned());
        } else {
            return Err(DslError::new(
                "UNKNOWN_OUTCOME_STATEMENT",
                detail.number,
                format!("Unknown outcome statement {}", detail.text),
            ));
        }
        index += 1;
    }
    Ok((
        OutcomeDefinition {
            id: id.to_owned(),
            probability: parse_expression(probability, line.number)?,
            condition: condition
                .map(|value| parse_expression(value, line.number))
                .transpose()?,
            effects,
            next_decision,
            target_next_decision,
            line: line.number,
        },
        index,
    ))
}

fn parse_effect(value: &str, line: usize) -> DslResult<EffectDefinition> {
    let operations = [" += ", " -= ", " *= ", " = "];
    let (left, operation, right) = operations
        .iter()
        .find_map(|operation| {
            value
                .split_once(operation)
                .map(|(left, right)| (left, operation.trim(), right))
        })
        .ok_or_else(|| DslError::new("INVALID_EFFECT", line, "Effect needs =, +=, -=, or *="))?;
    let (scope, field) = if let Some(field) = left.strip_prefix("self.") {
        (EffectScope::SelfAgent, field.to_owned())
    } else if let Some(field) = left.strip_prefix("target.") {
        (EffectScope::Target, field.to_owned())
    } else if let Some(value) = left.strip_prefix("place ") {
        let Some((place, field)) = value.split_once(' ') else {
            return Err(DslError::new(
                "INVALID_EFFECT",
                line,
                "Place effect needs place and field",
            ));
        };
        (
            EffectScope::Place {
                place: place.to_owned(),
            },
            field.to_owned(),
        )
    } else if let Some(value) = left.strip_prefix("all at ") {
        let (place_and_field, filter) = split_where(value);
        let Some((place, field)) = place_and_field.split_once(' ') else {
            return Err(DslError::new(
                "INVALID_EFFECT",
                line,
                "All-at effect needs place and field",
            ));
        };
        (
            EffectScope::AllAt {
                place: place.to_owned(),
                filter: filter
                    .map(|value| parse_expression(value, line))
                    .transpose()?,
            },
            field.to_owned(),
        )
    } else if let Some(field) = left.strip_prefix("relationship with target ") {
        (EffectScope::RelationshipWithTarget, field.to_owned())
    } else {
        return Err(DslError::new(
            "INVALID_EFFECT_SCOPE",
            line,
            format!("Unknown effect scope {left}"),
        ));
    };
    Ok(EffectDefinition {
        scope,
        field,
        operation: operation.to_owned(),
        value: parse_expression(right, line)?,
        line,
    })
}

fn validate_program(program: &Program) -> DslResult<()> {
    if program.placeholder_label
        != "placeholder — agent knowledge, for demo only, to be replaced by research"
    {
        return Err(DslError::new(
            "INVALID_PLACEHOLDER_LABEL",
            1,
            "Program must use the required placeholder label",
        ));
    }
    if program.uncertainty != "wide" {
        return Err(DslError::new(
            "INVALID_UNCERTAINTY",
            1,
            "Demo placeholder uncertainty must be wide",
        ));
    }
    if program.tick_hours <= 0.0 || program.tick_hours > 24.0 {
        return Err(DslError::new(
            "INVALID_TICK_HOURS",
            1,
            "tick_hours must be between zero and 24",
        ));
    }
    unique_ids(
        "place",
        program.places.iter().map(|item| (&item.id, item.line)),
    )?;
    unique_ids(
        "agent",
        program.agents.iter().map(|item| (&item.id, item.line)),
    )?;
    unique_ids(
        "decision",
        program.decisions.iter().map(|item| (&item.id, item.line)),
    )?;
    unique_ids(
        "action",
        program.actions.iter().map(|item| (&item.id, item.line)),
    )?;
    unique_ids(
        "output",
        program.reports.iter().map(|item| (&item.id, item.line)),
    )?;
    unique_ids(
        "archetype",
        program.archetypes.iter().map(|item| (&item.id, item.line)),
    )?;
    unique_ids(
        "weighted population",
        program
            .weighted_populations
            .iter()
            .map(|item| (&item.id, item.line)),
    )?;
    if program.reports.is_empty() {
        return Err(DslError::new(
            "MISSING_OUTPUT",
            1,
            "Program needs at least one output definition",
        ));
    }
    let agents = program
        .agents
        .iter()
        .map(|item| (item.id.as_str(), item))
        .collect::<BTreeMap<_, _>>();
    let decisions = program
        .decisions
        .iter()
        .map(|item| item.id.as_str())
        .collect::<BTreeSet<_>>();
    let actions = program
        .actions
        .iter()
        .map(|item| item.id.as_str())
        .collect::<BTreeSet<_>>();
    let aggregates = program
        .actions
        .iter()
        .map(|item| item.aggregate.as_str())
        .collect::<BTreeSet<_>>();
    let places = program
        .places
        .iter()
        .map(|item| item.id.as_str())
        .collect::<BTreeSet<_>>();
    let all_agent_fields = program
        .agents
        .iter()
        .map(|agent| merged_fields(agent, &agents))
        .collect::<DslResult<Vec<_>>>()?
        .into_iter()
        .flatten()
        .collect::<BTreeSet<_>>();
    for agent in &program.agents {
        if let Some(parent) = &agent.parent
            && !agents.contains_key(parent.as_str())
        {
            return Err(DslError::new(
                "UNKNOWN_AGENT",
                agent.line,
                format!("Agent {} inherits unknown agent {parent}", agent.id),
            ));
        }
        let routine = resolved_routine(agent, &agents)?;
        if !decisions.contains(routine) {
            return Err(DslError::new(
                "UNKNOWN_DECISION",
                agent.line,
                format!("Agent {} uses unknown routine {routine}", agent.id),
            ));
        }
        validate_initial_order(agent, &agents)?;
    }
    for entry in &program.population.mix {
        if !agents.contains_key(entry.agent_type.as_str()) {
            return Err(DslError::new(
                "UNKNOWN_AGENT",
                entry.line,
                format!(
                    "Population mix references unknown agent {}",
                    entry.agent_type
                ),
            ));
        }
    }
    for decision in &program.decisions {
        if decision.branches.is_empty() {
            return Err(DslError::new(
                "EMPTY_DECISION",
                decision.line,
                format!("Decision {} needs branches", decision.id),
            ));
        }
        for branch in &decision.branches {
            if !actions.contains(branch.action.as_str()) {
                return Err(DslError::new(
                    "UNKNOWN_ACTION",
                    branch.line,
                    format!(
                        "Decision {} references unknown action {}",
                        decision.id, branch.action
                    ),
                ));
            }
        }
    }
    for action in &program.actions {
        if !action.long && action.duration.maximum > program.tick_hours + 1e-9 {
            return Err(DslError::new(
                "DURATION_OUTSIDE_TICK_BUDGET",
                action.duration.line,
                format!(
                    "Action {} duration exceeds the tick; add long = true placeholder",
                    action.id
                ),
            ));
        }
        if action.outcomes.is_empty() {
            return Err(DslError::new(
                "EMPTY_ACTION",
                action.line,
                format!("Action {} needs outcomes", action.id),
            ));
        }
        if let Some(target) = &action.target {
            let target_place = match target {
                TargetSelector::Random { place, .. }
                | TargetSelector::Friend { place }
                | TargetSelector::Enemy { place }
                | TargetSelector::Strongest { place, .. } => place,
            };
            if !places.contains(target_place.as_str()) {
                return Err(DslError::new(
                    "UNKNOWN_PLACE",
                    action.line,
                    format!("Action {} targets unknown place {target_place}", action.id),
                ));
            }
        }
        for outcome in &action.outcomes {
            if let Some(next) = &outcome.next_decision
                && !decisions.contains(next.as_str())
            {
                return Err(DslError::new(
                    "UNKNOWN_DECISION",
                    outcome.line,
                    format!("Outcome {} references unknown decision {next}", outcome.id),
                ));
            }
            if let Some(next) = &outcome.target_next_decision
                && !decisions.contains(next.as_str())
            {
                return Err(DslError::new(
                    "UNKNOWN_DECISION",
                    outcome.line,
                    format!(
                        "Outcome {} references unknown target decision {next}",
                        outcome.id
                    ),
                ));
            }
            for effect in &outcome.effects {
                match &effect.scope {
                    EffectScope::SelfAgent | EffectScope::Target | EffectScope::AllAt { .. }
                        if !all_agent_fields.contains(&effect.field) =>
                    {
                        return Err(DslError::new(
                            "UNKNOWN_STATE",
                            effect.line,
                            format!("Effect references undeclared agent field {}", effect.field),
                        ));
                    }
                    EffectScope::Place { place } | EffectScope::AllAt { place, .. }
                        if !places.contains(place.as_str()) =>
                    {
                        return Err(DslError::new(
                            "UNKNOWN_PLACE",
                            effect.line,
                            format!("Effect references unknown place {place}"),
                        ));
                    }
                    EffectScope::Place { place }
                        if !program
                            .places
                            .iter()
                            .find(|item| item.id == *place)
                            .is_some_and(|item| item.states.contains_key(&effect.field)) =>
                    {
                        return Err(DslError::new(
                            "UNKNOWN_STATE",
                            effect.line,
                            format!("Place {place} has no state {}", effect.field),
                        ));
                    }
                    _ => {}
                }
            }
        }
    }
    for report in &program.reports {
        if !matches!(report.group_by.as_str(), "all" | "place" | "agent_type") {
            return Err(DslError::new(
                "INVALID_OUTPUT_GROUP",
                report.line,
                format!(
                    "Output {} has unsupported group {}",
                    report.id, report.group_by
                ),
            ));
        }
        if !matches!(report.display.as_str(), "table" | "cards") {
            return Err(DslError::new(
                "INVALID_OUTPUT_DISPLAY",
                report.line,
                format!("Output {} display must be table or cards", report.id),
            ));
        }
        if !matches!(report.record.as_str(), "tick" | "daily" | "final") {
            return Err(DslError::new(
                "INVALID_OUTPUT_CADENCE",
                report.line,
                format!("Output {} record must be tick, daily, or final", report.id),
            ));
        }
        if report.columns.is_empty() {
            return Err(DslError::new(
                "EMPTY_OUTPUT",
                report.line,
                format!("Output {} needs at least one column", report.id),
            ));
        }
        unique_ids(
            "output column",
            report.columns.iter().map(|item| (&item.id, item.line)),
        )?;
        for column in &report.columns {
            if !matches!(
                column.format.as_str(),
                "integer" | "number" | "decimal" | "currency" | "percent" | "action_rates"
            ) {
                return Err(DslError::new(
                    "INVALID_OUTPUT_FORMAT",
                    column.line,
                    format!("Unknown output format {}", column.format),
                ));
            }
            match &column.metric {
                ReportMetric::Mean { field } | ReportMetric::Sum { field }
                    if !all_agent_fields.contains(field) =>
                {
                    return Err(DslError::new(
                        "UNKNOWN_OUTPUT_FIELD",
                        column.line,
                        format!("Output column references undeclared field {field}"),
                    ));
                }
                ReportMetric::ActionCount { aggregate, window } => {
                    if !aggregates.contains(aggregate.as_str()) {
                        return Err(DslError::new(
                            "UNKNOWN_OUTPUT_ACTION",
                            column.line,
                            format!("Output column references unknown aggregate {aggregate}"),
                        ));
                    }
                    validate_report_window(window, column.line)?;
                }
                ReportMetric::OutcomeCount {
                    action,
                    outcome,
                    window,
                } => {
                    let definition = program.actions.iter().find(|item| item.id == *action);
                    if !definition
                        .is_some_and(|item| item.outcomes.iter().any(|item| item.id == *outcome))
                    {
                        return Err(DslError::new(
                            "UNKNOWN_OUTPUT_OUTCOME",
                            column.line,
                            format!("Output column references unknown outcome {action}.{outcome}"),
                        ));
                    }
                    validate_report_window(window, column.line)?;
                }
                ReportMetric::ActionRates { per, window } => {
                    if !per.is_finite() || *per <= 0.0 {
                        return Err(DslError::new(
                            "INVALID_OUTPUT_RATE",
                            column.line,
                            "Action rate denominator must be positive",
                        ));
                    }
                    validate_report_window(window, column.line)?;
                }
                _ => {}
            }
        }
    }
    let archetypes = program
        .archetypes
        .iter()
        .map(|item| (item.id.as_str(), item))
        .collect::<BTreeMap<_, _>>();
    for archetype in &program.archetypes {
        if archetype.sample_households == 0 {
            return Err(DslError::new(
                "INVALID_ARCHETYPE_SAMPLE",
                archetype.line,
                format!(
                    "Archetype {} sample_households must be positive",
                    archetype.id
                ),
            ));
        }
        if archetype.composition.is_empty() {
            return Err(DslError::new(
                "EMPTY_ARCHETYPE_COMPOSITION",
                archetype.line,
                format!("Archetype {} needs a composition", archetype.id),
            ));
        }
        if archetype.outputs.is_empty() {
            return Err(DslError::new(
                "EMPTY_ARCHETYPE_OUTPUT",
                archetype.line,
                format!("Archetype {} needs outputs", archetype.id),
            ));
        }
        for group in &archetype.composition {
            if group.count == 0 {
                return Err(DslError::new(
                    "INVALID_ARCHETYPE_COMPOSITION",
                    group.line,
                    format!("Composition group {} count must be positive", group.id),
                ));
            }
            for entry in &group.mix {
                if !agents.contains_key(entry.agent_type.as_str()) {
                    return Err(DslError::new(
                        "UNKNOWN_ARCHETYPE_AGENT",
                        entry.line,
                        format!(
                            "Archetype {} references unknown agent {}",
                            archetype.id, entry.agent_type
                        ),
                    ));
                }
            }
        }
        let archetype_fields = all_agent_fields
            .iter()
            .cloned()
            .chain(archetype.initial.iter().map(|item| item.field.clone()))
            .collect::<BTreeSet<_>>();
        for multiplier in &archetype.decision_multipliers {
            if !actions.contains(multiplier.action.as_str()) {
                return Err(DslError::new(
                    "UNKNOWN_ARCHETYPE_ACTION",
                    multiplier.line,
                    format!(
                        "Archetype {} references unknown action {}",
                        archetype.id, multiplier.action
                    ),
                ));
            }
            if !multiplier.multiplier.is_finite() || multiplier.multiplier < 0.0 {
                return Err(DslError::new(
                    "INVALID_ARCHETYPE_DECISION",
                    multiplier.line,
                    "Decision multiplier must be finite and non-negative",
                ));
            }
        }
        for output in &archetype.outputs {
            match &output.metric {
                ReportMetric::Mean { field } if archetype_fields.contains(field) => {}
                ReportMetric::KidsPerFamily => {}
                ReportMetric::ActionCount { aggregate, window }
                    if aggregates.contains(aggregate.as_str()) =>
                {
                    validate_report_window(window, output.line)?;
                }
                ReportMetric::Mean { field } => {
                    return Err(DslError::new(
                        "UNKNOWN_ARCHETYPE_FIELD",
                        output.line,
                        format!("Archetype output references unknown field {field}"),
                    ));
                }
                _ => {
                    return Err(DslError::new(
                        "INVALID_ARCHETYPE_OUTPUT",
                        output.line,
                        "Archetype output metric is invalid for this program",
                    ));
                }
            }
        }
    }
    for population in &program.weighted_populations {
        if population.entries.is_empty() {
            return Err(DslError::new(
                "EMPTY_WEIGHTED_POPULATION",
                population.line,
                format!("Population {} needs archetype weights", population.id),
            ));
        }
        let mut population_archetypes = BTreeSet::new();
        let mut output_ids: Option<BTreeSet<&str>> = None;
        for entry in &population.entries {
            if !population_archetypes.insert(entry.archetype.as_str()) {
                return Err(DslError::new(
                    "DUPLICATE_POPULATION_ARCHETYPE",
                    entry.line,
                    format!(
                        "Population {} repeats archetype {}",
                        population.id, entry.archetype
                    ),
                ));
            }
            if !archetypes.contains_key(entry.archetype.as_str()) {
                return Err(DslError::new(
                    "UNKNOWN_ARCHETYPE",
                    entry.line,
                    format!(
                        "Population {} references unknown archetype {}",
                        population.id, entry.archetype
                    ),
                ));
            }
            if entry.weight == 0 {
                return Err(DslError::new(
                    "INVALID_POPULATION_WEIGHT",
                    entry.line,
                    "Population weight must be positive",
                ));
            }
            let current_outputs = archetypes[entry.archetype.as_str()]
                .outputs
                .iter()
                .map(|output| output.id.as_str())
                .collect::<BTreeSet<_>>();
            if output_ids
                .as_ref()
                .is_some_and(|expected| *expected != current_outputs)
            {
                return Err(DslError::new(
                    "ARCHETYPE_OUTPUT_MISMATCH",
                    entry.line,
                    format!(
                        "Population {} archetypes must expose the same output IDs",
                        population.id
                    ),
                ));
            }
            output_ids = Some(current_outputs);
        }
    }
    validate_neighbourhoods(program)?;
    validate_aggregate_functions(program)?;
    validate_inheritance_cycles(&agents)?;
    Ok(())
}

fn validate_report_window(window: &str, line: usize) -> DslResult<()> {
    if matches!(window, "tick" | "day" | "run") {
        Ok(())
    } else {
        Err(DslError::new(
            "INVALID_OUTPUT_WINDOW",
            line,
            format!("Output window {window} must be tick, day, or run"),
        ))
    }
}

fn validate_initial_order(
    agent: &AgentDefinition,
    agents: &BTreeMap<&str, &AgentDefinition>,
) -> DslResult<()> {
    let assignments = merged_initial(agent, agents)?;
    let declared = merged_fields(agent, agents)?;
    let mut sampled = BTreeSet::new();
    for assignment in assignments {
        if !declared.contains(assignment.field.as_str()) {
            return Err(DslError::new(
                "UNKNOWN_TRAIT_OR_STATE",
                assignment.line,
                format!(
                    "Initial block assigns undeclared field {}",
                    assignment.field
                ),
            ));
        }
        let mut needed = BTreeSet::new();
        for expression in assignment.distribution.parameters.values().chain(
            assignment
                .distribution
                .categories
                .iter()
                .map(|item| &item.1),
        ) {
            needed.extend(references(expression));
        }
        let unknown = needed
            .into_iter()
            .filter(|name| !sampled.contains(name))
            .collect::<Vec<_>>();
        if !unknown.is_empty() {
            return Err(DslError::new(
                "FORWARD_INITIAL_REFERENCE",
                assignment.line,
                format!(
                    "Initial {} references values not sampled above it: {}",
                    assignment.field,
                    unknown.join(", ")
                ),
            ));
        }
        sampled.insert(assignment.field.clone());
    }
    Ok(())
}

pub(crate) fn merged_initial<'a>(
    agent: &'a AgentDefinition,
    agents: &BTreeMap<&str, &'a AgentDefinition>,
) -> DslResult<Vec<&'a InitialAssignment>> {
    let mut result = if let Some(parent) = &agent.parent {
        merged_initial(agents[parent.as_str()], agents)?
    } else {
        Vec::new()
    };
    for assignment in &agent.initial {
        if let Some(index) = result
            .iter()
            .position(|existing| existing.field == assignment.field)
        {
            result[index] = assignment;
        } else {
            result.push(assignment);
        }
    }
    Ok(result)
}

pub(crate) fn merged_fields(
    agent: &AgentDefinition,
    agents: &BTreeMap<&str, &AgentDefinition>,
) -> DslResult<BTreeSet<String>> {
    let mut result = if let Some(parent) = &agent.parent {
        merged_fields(agents[parent.as_str()], agents)?
    } else {
        BTreeSet::new()
    };
    result.extend(agent.traits.iter().cloned());
    result.extend(agent.states.iter().cloned());
    Ok(result)
}

pub(crate) fn merged_roles(
    agent: &AgentDefinition,
    agents: &BTreeMap<&str, &AgentDefinition>,
) -> DslResult<BTreeSet<String>> {
    let mut result = if let Some(parent) = &agent.parent {
        merged_roles(agents[parent.as_str()], agents)?
    } else {
        BTreeSet::new()
    };
    result.extend(agent.roles.iter().cloned());
    Ok(result)
}

pub(crate) fn resolved_routine<'a>(
    agent: &'a AgentDefinition,
    agents: &BTreeMap<&str, &'a AgentDefinition>,
) -> DslResult<&'a str> {
    if !agent.routine.is_empty() {
        return Ok(&agent.routine);
    }
    if let Some(parent) = &agent.parent {
        return resolved_routine(agents[parent.as_str()], agents);
    }
    Err(DslError::new(
        "MISSING_ROUTINE",
        agent.line,
        format!("Agent {} needs a routine decision", agent.id),
    ))
}

fn validate_inheritance_cycles(agents: &BTreeMap<&str, &AgentDefinition>) -> DslResult<()> {
    for agent in agents.values() {
        let mut current = Some(*agent);
        let mut visited = BTreeSet::new();
        while let Some(value) = current {
            if !visited.insert(value.id.as_str()) {
                return Err(DslError::new(
                    "INHERITANCE_CYCLE",
                    agent.line,
                    format!("Agent inheritance cycle includes {}", value.id),
                ));
            }
            current = value
                .parent
                .as_ref()
                .and_then(|parent| agents.get(parent.as_str()).copied());
        }
    }
    Ok(())
}

fn unique_ids<'a>(label: &str, values: impl Iterator<Item = (&'a String, usize)>) -> DslResult<()> {
    let mut seen = BTreeSet::new();
    for (value, line) in values {
        if !seen.insert(value.as_str()) {
            return Err(DslError::new(
                "DUPLICATE_DEFINITION",
                line,
                format!("Duplicate {label} {value}"),
            ));
        }
    }
    Ok(())
}

fn block_name<'a>(value: &'a str, kind: &str) -> Option<&'a str> {
    value
        .strip_prefix(&format!("{kind} "))
        .and_then(|value| value.strip_suffix(':'))
}

fn agent_header(value: &str) -> Option<(&str, Option<String>)> {
    let body = value.strip_prefix("agent ")?.strip_suffix(':')?;
    if let Some((name, parent)) = body.split_once(" inherits ") {
        Some((name, Some(parent.to_owned())))
    } else {
        Some((body, None))
    }
}

pub(super) fn identifier(value: &str, line: usize) -> DslResult<()> {
    if value.is_empty()
        || !value
            .chars()
            .next()
            .is_some_and(|character| character.is_ascii_alphabetic())
        || value
            .chars()
            .any(|character| !character.is_ascii_alphanumeric() && character != '_')
    {
        return Err(DslError::new(
            "INVALID_IDENTIFIER",
            line,
            format!("Invalid identifier {value}"),
        ));
    }
    Ok(())
}

pub(super) fn require_indent(line: &Line, expected: usize) -> DslResult<()> {
    if line.indent != expected {
        return Err(DslError::new(
            "INVALID_INDENTATION",
            line.number,
            format!("Expected {expected} spaces"),
        ));
    }
    Ok(())
}

fn remove_placeholder<'a>(value: &'a str, line: usize) -> DslResult<&'a str> {
    value.strip_suffix(" placeholder").ok_or_else(|| {
        DslError::new(
            "MISSING_PLACEHOLDER_LABEL",
            line,
            "Every demo value must end with placeholder",
        )
    })
}

fn number_with_placeholder(value: &str, line: usize) -> DslResult<f64> {
    remove_placeholder(value, line)?
        .parse()
        .map_err(|_| DslError::new("INVALID_NUMBER", line, "Expected a numeric value"))
}

fn bool_with_placeholder(value: &str, line: usize) -> DslResult<bool> {
    match remove_placeholder(value, line)? {
        "true" => Ok(true),
        "false" => Ok(false),
        _ => Err(DslError::new(
            "INVALID_BOOLEAN",
            line,
            "Expected true or false",
        )),
    }
}

fn literal_with_placeholder(value: &str, line: usize) -> DslResult<DslValue> {
    let value = remove_placeholder(value, line)?;
    if value == "true" {
        return Ok(DslValue::Bool(true));
    }
    if value == "false" {
        return Ok(DslValue::Bool(false));
    }
    if let Ok(value) = value.parse() {
        return Ok(DslValue::Number(value));
    }
    Ok(DslValue::Text(value.trim_matches('"').to_owned()))
}

fn split_range(value: &str, line: usize) -> DslResult<(String, Option<ValueBounds>)> {
    let core = remove_placeholder(value, line)?;
    if let Some((literal, bounds)) = core.split_once(" range ") {
        return Ok((
            format!("{literal} placeholder"),
            Some(parse_bounds(bounds, line)?),
        ));
    }
    Ok((value.to_owned(), None))
}

fn parse_bounds(value: &str, line: usize) -> DslResult<ValueBounds> {
    let Some((minimum, maximum)) = value.split_once("..") else {
        return Err(DslError::new(
            "INVALID_STATE_RANGE",
            line,
            "State range uses minimum..maximum",
        ));
    };
    let minimum = minimum
        .parse::<f64>()
        .map_err(|_| DslError::new("INVALID_STATE_RANGE", line, "State minimum must be numeric"))?;
    let maximum = maximum
        .parse::<f64>()
        .map_err(|_| DslError::new("INVALID_STATE_RANGE", line, "State maximum must be numeric"))?;
    if !minimum.is_finite() || !maximum.is_finite() || maximum <= minimum {
        return Err(DslError::new(
            "INVALID_STATE_RANGE",
            line,
            "State range maximum must exceed minimum",
        ));
    }
    Ok(ValueBounds { minimum, maximum })
}

fn quoted(value: &str, line: usize) -> DslResult<String> {
    value
        .strip_prefix('"')
        .and_then(|value| value.strip_suffix('"'))
        .map(str::to_owned)
        .ok_or_else(|| DslError::new("INVALID_STRING", line, "Expected a quoted string"))
}

fn split_top_level(value: &str, delimiter: char) -> Vec<&str> {
    let mut result = Vec::new();
    let mut depth = 0;
    let mut start = 0;
    for (index, character) in value.char_indices() {
        match character {
            '(' => depth += 1,
            ')' => depth -= 1,
            _ if character == delimiter && depth == 0 => {
                result.push(value[start..index].trim());
                start = index + character.len_utf8();
            }
            _ => {}
        }
    }
    result.push(value[start..].trim());
    result
}

fn split_if(value: &str) -> (&str, Option<&str>) {
    value
        .split_once(" if ")
        .map_or((value, None), |(left, right)| (left, Some(right)))
}

fn split_where(value: &str) -> (&str, Option<&str>) {
    value
        .split_once(" where ")
        .map_or((value, None), |(left, right)| (left, Some(right)))
}
