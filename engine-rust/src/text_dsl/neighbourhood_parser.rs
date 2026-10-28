use super::model::*;
use super::parser::{Line, identifier, parse_archetype_output, require_indent};
use std::collections::{BTreeMap, BTreeSet};

pub(super) fn parse_neighbourhood(
    lines: &[Line],
    start: usize,
    name: &str,
) -> DslResult<(NeighbourhoodDefinition, usize)> {
    identifier(name, lines[start].number)?;
    let mut households = Vec::new();
    let mut places = Vec::new();
    let mut outputs = Vec::new();
    let mut index = start + 1;
    while index < lines.len() && lines[index].indent > 0 {
        let line = &lines[index];
        require_indent(line, 2)?;
        if line.text == "households:" {
            index += 1;
            while index < lines.len() && lines[index].indent > 2 {
                let entry = &lines[index];
                require_indent(entry, 4)?;
                let Some((archetype, weight)) = entry.text.split_once(": weight = ") else {
                    return Err(DslError::new(
                        "INVALID_NEIGHBOURHOOD_HOUSEHOLD",
                        entry.number,
                        "Household entries use Archetype: weight = count",
                    ));
                };
                households.push(WeightedPopulationEntry {
                    archetype: archetype.to_owned(),
                    weight: weight.parse::<u64>().map_err(|_| {
                        DslError::new(
                            "INVALID_NEIGHBOURHOOD_HOUSEHOLD",
                            entry.number,
                            "Household weight must be a positive integer",
                        )
                    })?,
                    line: entry.number,
                });
                index += 1;
            }
        } else if let Some(value) = line.text.strip_prefix("places = ") {
            places = value
                .split(',')
                .map(|item| item.trim().to_owned())
                .collect();
            index += 1;
        } else if let Some(value) = line.text.strip_prefix("output ") {
            outputs.push(parse_archetype_output(value, line.number)?);
            index += 1;
        } else {
            return Err(DslError::new(
                "UNKNOWN_NEIGHBOURHOOD_STATEMENT",
                line.number,
                format!("Unknown neighbourhood statement {}", line.text),
            ));
        }
    }
    Ok((
        NeighbourhoodDefinition {
            id: name.to_owned(),
            households,
            places,
            outputs,
            line: lines[start].number,
        },
        index,
    ))
}

pub(super) fn parse_neighbourhood_population(
    lines: &[Line],
    start: usize,
    name: &str,
) -> DslResult<(WeightedNeighbourhoodPopulation, usize)> {
    identifier(name, lines[start].number)?;
    let mut entries = Vec::new();
    let mut index = start + 1;
    while index < lines.len() && lines[index].indent > 0 {
        let line = &lines[index];
        require_indent(line, 2)?;
        let Some((neighbourhood, weight)) = line.text.split_once(": weight = ") else {
            return Err(DslError::new(
                "INVALID_NEIGHBOURHOOD_WEIGHT",
                line.number,
                "Neighbourhood population entries use Neighbourhood: weight = count",
            ));
        };
        entries.push(WeightedNeighbourhoodEntry {
            neighbourhood: neighbourhood.to_owned(),
            weight: weight.parse::<u64>().map_err(|_| {
                DslError::new(
                    "INVALID_NEIGHBOURHOOD_WEIGHT",
                    line.number,
                    "Neighbourhood weight must be a positive integer",
                )
            })?,
            line: line.number,
        });
        index += 1;
    }
    Ok((
        WeightedNeighbourhoodPopulation {
            id: name.to_owned(),
            entries,
            line: lines[start].number,
        },
        index,
    ))
}

pub(super) fn validate_neighbourhoods(program: &Program) -> DslResult<()> {
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
    let neighbourhoods = program
        .neighbourhoods
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
    for neighbourhood in &program.neighbourhoods {
        if !ids.insert(neighbourhood.id.as_str()) {
            return Err(DslError::new(
                "DUPLICATE_NEIGHBOURHOOD",
                neighbourhood.line,
                format!("Duplicate neighbourhood {}", neighbourhood.id),
            ));
        }
        if neighbourhood.households.is_empty()
            || neighbourhood.places.is_empty()
            || neighbourhood.outputs.is_empty()
        {
            return Err(DslError::new(
                "EMPTY_NEIGHBOURHOOD",
                neighbourhood.line,
                "Neighbourhood needs households, places, and outputs",
            ));
        }
        let mut household_ids = BTreeSet::new();
        for entry in &neighbourhood.households {
            if !household_ids.insert(entry.archetype.as_str()) {
                return Err(DslError::new(
                    "DUPLICATE_NEIGHBOURHOOD_HOUSEHOLD",
                    entry.line,
                    format!(
                        "Neighbourhood repeats household archetype {}",
                        entry.archetype
                    ),
                ));
            }
            if !archetypes.contains(entry.archetype.as_str()) {
                return Err(DslError::new(
                    "UNKNOWN_NEIGHBOURHOOD_HOUSEHOLD",
                    entry.line,
                    format!("Unknown household archetype {}", entry.archetype),
                ));
            }
            if entry.weight == 0 {
                return Err(DslError::new(
                    "INVALID_NEIGHBOURHOOD_HOUSEHOLD",
                    entry.line,
                    "Household weight must be positive",
                ));
            }
        }
        for place in &neighbourhood.places {
            if !places.contains(place.as_str()) {
                return Err(DslError::new(
                    "UNKNOWN_NEIGHBOURHOOD_PLACE",
                    neighbourhood.line,
                    format!("Unknown neighbourhood place {place}"),
                ));
            }
        }
        for output in &neighbourhood.outputs {
            match &output.metric {
                ReportMetric::Mean { field } if base_fields.contains(field) => {}
                ReportMetric::KidsPerFamily => {}
                ReportMetric::ActionCount { aggregate, window }
                    if aggregates.contains(aggregate.as_str())
                        && matches!(window.as_str(), "tick" | "day" | "run") => {}
                _ => {
                    return Err(DslError::new(
                        "INVALID_NEIGHBOURHOOD_OUTPUT",
                        output.line,
                        format!("Invalid neighbourhood output {}", output.id),
                    ));
                }
            }
        }
    }
    let mut population_ids = BTreeSet::new();
    for population in &program.neighbourhood_populations {
        if !population_ids.insert(population.id.as_str()) {
            return Err(DslError::new(
                "DUPLICATE_NEIGHBOURHOOD_POPULATION",
                population.line,
                format!("Duplicate neighbourhood population {}", population.id),
            ));
        }
        if population.entries.is_empty() {
            return Err(DslError::new(
                "EMPTY_NEIGHBOURHOOD_POPULATION",
                population.line,
                "Neighbourhood population needs entries",
            ));
        }
        for entry in &population.entries {
            if !neighbourhoods.contains_key(entry.neighbourhood.as_str()) {
                return Err(DslError::new(
                    "UNKNOWN_NEIGHBOURHOOD",
                    entry.line,
                    format!("Unknown neighbourhood {}", entry.neighbourhood),
                ));
            }
            if entry.weight == 0 {
                return Err(DslError::new(
                    "INVALID_NEIGHBOURHOOD_WEIGHT",
                    entry.line,
                    "Neighbourhood weight must be positive",
                ));
            }
        }
    }
    Ok(())
}
