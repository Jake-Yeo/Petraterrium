use super::expression::{parse_expression, references};
use super::model::*;
use super::parser::{Line, identifier, parse_report_metric, require_indent};
use std::collections::{BTreeMap, BTreeSet};

pub(super) fn parse_aggregate_function(
    lines: &[Line],
    start: usize,
    name: &str,
) -> DslResult<(AggregateFunctionDefinition, usize)> {
    identifier(name, lines[start].number)?;
    let mut inputs = Vec::new();
    let mut time_days = None;
    let mut time_points = Vec::new();
    let mut effects = Vec::new();
    let mut outputs = Vec::new();
    let mut valid_for_days = None;
    let mut hash_inputs = Vec::new();
    let mut thresholds = BTreeMap::new();
    let mut invalidate_events = BTreeSet::new();
    let mut index = start + 1;
    while index < lines.len() && lines[index].indent > 0 {
        let line = &lines[index];
        require_indent(line, 2)?;
        if line.text == "inputs:" {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let entry = &lines[index];
                require_indent(entry, 4)?;
                inputs.push(parse_input(entry)?);
                index += 1;
            }
        } else if let Some(value) = line.text.strip_prefix("time = ") {
            time_days = Some(parse_days(value, line.number)?);
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("time_points = ") {
            time_points = parse_u32_list(value, line.number)?;
            index += 1;
        } else if line.text == "effects:" {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let entry = &lines[index];
                require_indent(entry, 4)?;
                effects.push(parse_effect(entry)?);
                index += 1;
            }
        } else if line.text == "outputs:" {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let entry = &lines[index];
                require_indent(entry, 4)?;
                outputs.push(parse_output(entry)?);
                index += 1;
            }
        } else if line.text == "cache:" {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let entry = &lines[index];
                require_indent(entry, 4)?;
                if let Some(value) = entry.text.strip_prefix("valid_for = ") {
                    valid_for_days = Some(parse_days(value, entry.number)?);
                    index += 1;
                } else if let Some(value) = entry.text.strip_prefix("inputs_hash = hash(") {
                    let value = value.strip_suffix(')').ok_or_else(|| {
                        DslError::new(
                            "INVALID_CACHE_HASH",
                            entry.number,
                            "inputs_hash requires hash(input, ...)",
                        )
                    })?;
                    hash_inputs = parse_identifiers(value, entry.number)?;
                    index += 1;
                } else if entry.text == "invalidate_on:" {
                    index += 1;
                    while index < lines.len() && lines[index].indent > 4 {
                        let invalidation = &lines[index];
                        require_indent(invalidation, 6)?;
                        if let Some(value) = invalidation.text.strip_prefix("event = ") {
                            invalidate_events
                                .extend(value.split(',').map(|item| item.trim().to_owned()));
                        } else {
                            let Some((input, threshold)) =
                                invalidation.text.split_once(" change > ")
                            else {
                                return Err(DslError::new(
                                    "INVALID_CACHE_INVALIDATION",
                                    invalidation.number,
                                    "Invalidation uses input change > threshold or event = names",
                                ));
                            };
                            identifier(input, invalidation.number)?;
                            thresholds.insert(
                                input.to_owned(),
                                threshold.parse::<f64>().map_err(|_| {
                                    DslError::new(
                                        "INVALID_CACHE_INVALIDATION",
                                        invalidation.number,
                                        "Invalidation threshold must be numeric",
                                    )
                                })?,
                            );
                        }
                        index += 1;
                    }
                } else {
                    return Err(DslError::new(
                        "UNKNOWN_CACHE_STATEMENT",
                        entry.number,
                        format!("Unknown cache statement {}", entry.text),
                    ));
                }
            }
        } else {
            return Err(DslError::new(
                "UNKNOWN_AGGREGATE_FUNCTION_STATEMENT",
                line.number,
                format!("Unknown aggregate function statement {}", line.text),
            ));
        }
    }
    for input in &mut inputs {
        input.invalidate_threshold = thresholds.get(&input.id).copied().ok_or_else(|| {
            DslError::new(
                "MISSING_CACHE_THRESHOLD",
                input.line,
                format!("Input {} needs an invalidate_on threshold", input.id),
            )
        })?;
    }
    Ok((
        AggregateFunctionDefinition {
            id: name.to_owned(),
            inputs,
            time_days: time_days.ok_or_else(|| {
                DslError::new(
                    "MISSING_AGGREGATE_TIME",
                    lines[start].number,
                    "Aggregate function needs time",
                )
            })?,
            time_points,
            effects,
            outputs,
            cache: AggregateCacheDefinition {
                valid_for_days: valid_for_days.ok_or_else(|| {
                    DslError::new(
                        "MISSING_CACHE_VALIDITY",
                        lines[start].number,
                        "Aggregate function cache needs valid_for",
                    )
                })?,
                hash_inputs,
                invalidate_events,
            },
            line: lines[start].number,
        },
        index,
    ))
}

fn parse_input(line: &Line) -> DslResult<AggregateInputDefinition> {
    let Some((id, value)) = line.text.split_once(" = ") else {
        return Err(DslError::new(
            "INVALID_AGGREGATE_INPUT",
            line.number,
            "Input uses name = default range minimum..maximum",
        ));
    };
    identifier(id, line.number)?;
    let Some((default, range)) = value.split_once(" range ") else {
        return Err(DslError::new(
            "INVALID_AGGREGATE_INPUT",
            line.number,
            "Input needs a range",
        ));
    };
    let Some((minimum, maximum)) = range.split_once("..") else {
        return Err(DslError::new(
            "INVALID_AGGREGATE_INPUT",
            line.number,
            "Input range uses minimum..maximum",
        ));
    };
    Ok(AggregateInputDefinition {
        id: id.to_owned(),
        default: parse_number(default, line.number)?,
        minimum: parse_number(minimum, line.number)?,
        maximum: parse_number(maximum, line.number)?,
        invalidate_threshold: 0.0,
        line: line.number,
    })
}

fn parse_effect(line: &Line) -> DslResult<AggregateInputEffect> {
    let (target, value) = if let Some(value) = line.text.strip_prefix("field ") {
        let Some((field, value)) = value.split_once(' ') else {
            return Err(DslError::new(
                "INVALID_AGGREGATE_EFFECT",
                line.number,
                "Field effect needs a field and operation",
            ));
        };
        (AggregateEffectTarget::Field(field.to_owned()), value)
    } else if let Some(value) = line.text.strip_prefix("decision ") {
        let Some((action, value)) = value.split_once(' ') else {
            return Err(DslError::new(
                "INVALID_AGGREGATE_EFFECT",
                line.number,
                "Decision effect needs an action and operation",
            ));
        };
        (AggregateEffectTarget::Decision(action.to_owned()), value)
    } else {
        return Err(DslError::new(
            "INVALID_AGGREGATE_EFFECT",
            line.number,
            "Effect starts with field or decision",
        ));
    };
    let operations = ["*=", "+=", "-=", "="];
    let Some((operation, expression)) = operations.iter().find_map(|operation| {
        value
            .strip_prefix(&format!("{operation} "))
            .map(|expression| ((*operation).to_owned(), expression))
    }) else {
        return Err(DslError::new(
            "INVALID_AGGREGATE_EFFECT",
            line.number,
            "Effect needs =, +=, -=, or *=",
        ));
    };
    Ok(AggregateInputEffect {
        target,
        operation,
        value: parse_expression(expression, line.number)?,
        line: line.number,
    })
}

fn parse_output(line: &Line) -> DslResult<AggregateFunctionOutput> {
    let Some((id, value)) = line.text.split_once(" = formula(") else {
        return Err(DslError::new(
            "INVALID_AGGREGATE_OUTPUT",
            line.number,
            "Output uses name = formula(input, ...)",
        ));
    };
    identifier(id, line.number)?;
    let (value, metric) = value
        .rsplit_once(" from ")
        .map_or((value, None), |(formula, metric)| (formula, Some(metric)));
    let value = value.strip_suffix(')').ok_or_else(|| {
        DslError::new(
            "INVALID_AGGREGATE_OUTPUT",
            line.number,
            "Output formula needs a closing parenthesis",
        )
    })?;
    Ok(AggregateFunctionOutput {
        id: id.to_owned(),
        inputs: parse_identifiers(value, line.number)?,
        metric: metric
            .map(|metric| parse_report_metric(metric, line.number))
            .transpose()?,
        line: line.number,
    })
}

fn parse_days(value: &str, line: usize) -> DslResult<u32> {
    value
        .strip_suffix(" days")
        .ok_or_else(|| DslError::new("INVALID_DAYS", line, "Duration uses number days"))?
        .parse::<u32>()
        .map_err(|_| DslError::new("INVALID_DAYS", line, "Duration days must be an integer"))
}

fn parse_u32_list(value: &str, line: usize) -> DslResult<Vec<u32>> {
    value
        .split(',')
        .map(|item| {
            item.trim().parse::<u32>().map_err(|_| {
                DslError::new("INVALID_TIME_POINTS", line, "Time points must be integers")
            })
        })
        .collect()
}

fn parse_identifiers(value: &str, line: usize) -> DslResult<Vec<String>> {
    value
        .split(',')
        .map(|item| {
            let item = item.trim();
            identifier(item, line)?;
            Ok(item.to_owned())
        })
        .collect()
}

fn parse_number(value: &str, line: usize) -> DslResult<f64> {
    value
        .trim()
        .parse::<f64>()
        .map_err(|_| DslError::new("INVALID_NUMBER", line, "Expected a numeric value"))
}

pub(super) fn validate_aggregate_functions(program: &Program) -> DslResult<()> {
    let archetypes = program
        .archetypes
        .iter()
        .map(|item| (item.id.as_str(), item))
        .collect::<BTreeMap<_, _>>();
    let neighbourhoods = program
        .neighbourhoods
        .iter()
        .map(|item| (item.id.as_str(), item))
        .collect::<BTreeMap<_, _>>();
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
    let base_fields = program
        .agents
        .iter()
        .flat_map(|agent| agent.traits.iter().chain(&agent.states))
        .cloned()
        .collect::<BTreeSet<_>>();
    let mut ids = BTreeSet::new();
    for function in &program.aggregate_functions {
        if !ids.insert(function.id.as_str()) {
            return Err(DslError::new(
                "DUPLICATE_AGGREGATE_FUNCTION",
                function.line,
                format!("Duplicate aggregate function {}", function.id),
            ));
        }
        let archetype = archetypes.get(function.id.as_str()).copied();
        let neighbourhood = neighbourhoods.get(function.id.as_str()).copied();
        if archetype.is_none() && neighbourhood.is_none() {
            return Err(DslError::new(
                "UNKNOWN_AGGREGATE_BRANCH",
                function.line,
                format!(
                    "Aggregate function references unknown archetype or neighbourhood {}",
                    function.id
                ),
            ));
        }
        if function.inputs.is_empty() || function.outputs.is_empty() {
            return Err(DslError::new(
                "EMPTY_AGGREGATE_FUNCTION",
                function.line,
                "Aggregate function needs inputs and outputs",
            ));
        }
        let mut input_ids = BTreeSet::new();
        for input in &function.inputs {
            if !input_ids.insert(input.id.as_str()) {
                return Err(DslError::new(
                    "DUPLICATE_AGGREGATE_INPUT",
                    input.line,
                    format!("Duplicate aggregate input {}", input.id),
                ));
            }
            if !input.minimum.is_finite()
                || !input.maximum.is_finite()
                || input.minimum >= input.maximum
                || !(input.minimum..=input.maximum).contains(&input.default)
                || !input.invalidate_threshold.is_finite()
                || input.invalidate_threshold < 0.0
            {
                return Err(DslError::new(
                    "INVALID_AGGREGATE_INPUT",
                    input.line,
                    format!(
                        "Aggregate input {} has invalid bounds or threshold",
                        input.id
                    ),
                ));
            }
        }
        let mut time_points = function.time_points.clone();
        time_points.sort_unstable();
        time_points.dedup();
        if time_points.is_empty()
            || time_points
                .iter()
                .any(|day| *day == 0 || *day > function.time_days)
            || time_points.last() != Some(&function.time_days)
        {
            return Err(DslError::new(
                "INVALID_AGGREGATE_TIME_POINTS",
                function.line,
                "Time points must be unique positive days ending at the function time",
            ));
        }
        let fields = base_fields
            .iter()
            .cloned()
            .chain(
                archetype
                    .into_iter()
                    .flat_map(|item| item.initial.iter().map(|item| item.field.clone())),
            )
            .chain(neighbourhood.into_iter().flat_map(|neighbourhood| {
                neighbourhood.households.iter().flat_map(|entry| {
                    archetypes[entry.archetype.as_str()]
                        .initial
                        .iter()
                        .map(|item| item.field.clone())
                })
            }))
            .collect::<BTreeSet<_>>();
        for effect in &function.effects {
            match &effect.target {
                AggregateEffectTarget::Field(field) if !fields.contains(field) => {
                    return Err(DslError::new(
                        "UNKNOWN_AGGREGATE_FIELD",
                        effect.line,
                        format!("Aggregate effect references unknown field {field}"),
                    ));
                }
                AggregateEffectTarget::Decision(action) if !actions.contains(action.as_str()) => {
                    return Err(DslError::new(
                        "UNKNOWN_AGGREGATE_ACTION",
                        effect.line,
                        format!("Aggregate effect references unknown action {action}"),
                    ));
                }
                _ => {}
            }
            validate_references(&effect.value, &input_ids, effect.line)?;
        }
        let branch_outputs = archetype
            .map(|item| &item.outputs)
            .or_else(|| neighbourhood.map(|item| &item.outputs))
            .unwrap();
        let archetype_outputs = branch_outputs
            .iter()
            .map(|output| output.id.as_str())
            .collect::<BTreeSet<_>>();
        let mut output_ids = BTreeSet::new();
        for output in &function.outputs {
            if !output_ids.insert(output.id.as_str()) {
                return Err(DslError::new(
                    "DUPLICATE_AGGREGATE_OUTPUT",
                    output.line,
                    format!("Duplicate aggregate output {}", output.id),
                ));
            }
            if !archetype_outputs.contains(output.id.as_str()) && output.metric.is_none() {
                return Err(DslError::new(
                    "UNKNOWN_AGGREGATE_OUTPUT",
                    output.line,
                    format!("Aggregate function references unknown output {}", output.id),
                ));
            }
            if let Some(metric) = &output.metric {
                match metric {
                    ReportMetric::Mean { field } if fields.contains(field) => {}
                    ReportMetric::ActionCount { aggregate, window }
                        if aggregates.contains(aggregate.as_str())
                            && matches!(window.as_str(), "tick" | "day" | "run") => {}
                    _ => {
                        return Err(DslError::new(
                            "INVALID_AGGREGATE_OUTPUT_SOURCE",
                            output.line,
                            format!("Output {} has an invalid source metric", output.id),
                        ));
                    }
                }
            }
            for input in &output.inputs {
                if !input_ids.contains(input.as_str()) {
                    return Err(DslError::new(
                        "UNKNOWN_AGGREGATE_INPUT",
                        output.line,
                        format!("Output {} references unknown input {input}", output.id),
                    ));
                }
            }
        }
        if function
            .cache
            .hash_inputs
            .iter()
            .any(|input| !input_ids.contains(input.as_str()))
            || function.cache.hash_inputs.len() != input_ids.len()
        {
            return Err(DslError::new(
                "INVALID_CACHE_HASH",
                function.line,
                "inputs_hash must include every aggregate input exactly once",
            ));
        }
        if function.cache.valid_for_days == 0 {
            return Err(DslError::new(
                "INVALID_CACHE_VALIDITY",
                function.line,
                "Cache valid_for must be positive",
            ));
        }
    }
    Ok(())
}

fn validate_references(expression: &Expr, inputs: &BTreeSet<&str>, line: usize) -> DslResult<()> {
    for reference in references(expression) {
        if !inputs.contains(reference.as_str()) {
            return Err(DslError::new(
                "UNKNOWN_AGGREGATE_INPUT",
                line,
                format!("Aggregate expression references unknown input {reference}"),
            ));
        }
    }
    Ok(())
}
