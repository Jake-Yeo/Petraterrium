use super::aggregate_parser::parse_aggregate_effect;
use super::model::*;
use super::parser::{Line, identifier, parse_bounds, require_indent};
use std::collections::BTreeMap;

pub(super) fn parse_entity(
    lines: &[Line],
    start: usize,
    name: &str,
) -> DslResult<(EntityDefinition, usize)> {
    identifier(name, lines[start].number)?;
    let mut fields = Vec::new();
    let mut owner_field = None;
    let mut links = BTreeMap::new();
    let mut index = start + 1;
    while index < lines.len() && lines[index].indent > 0 {
        let line = &lines[index];
        require_indent(line, 2)?;
        if let Some(id) = line.text.strip_prefix("field ") {
            identifier(id, line.number)?;
            fields.push(EntityFieldDefinition {
                id: id.to_owned(),
                bounds: None,
                line: line.number,
            });
        } else if let Some(value) = line.text.strip_prefix("state ") {
            let (id, bounds) = value.split_once(" range ").ok_or_else(|| {
                DslError::new(
                    "INVALID_ENTITY_STATE",
                    line.number,
                    "Entity state uses state name range minimum..maximum",
                )
            })?;
            identifier(id, line.number)?;
            fields.push(EntityFieldDefinition {
                id: id.to_owned(),
                bounds: Some(parse_bounds(
                    bounds.strip_suffix(" estimated").unwrap_or(bounds),
                    line.number,
                )?),
                line: line.number,
            });
        } else if let Some(value) = line.text.strip_prefix("owner = ") {
            identifier(value, line.number)?;
            owner_field = Some(value.to_owned());
        } else if let Some(value) = line.text.strip_prefix("link ") {
            let (kind, target) = value.split_once(" = ").ok_or_else(|| {
                DslError::new(
                    "INVALID_ENTITY_LINK",
                    line.number,
                    "Entity links use link kind = target",
                )
            })?;
            identifier(kind, line.number)?;
            identifier(target, line.number)?;
            if links.insert(kind.to_owned(), target.to_owned()).is_some() {
                return Err(DslError::new(
                    "DUPLICATE_ENTITY_LINK",
                    line.number,
                    format!("Entity {name} repeats link {kind}"),
                ));
            }
        } else {
            return Err(DslError::new(
                "UNKNOWN_ENTITY_STATEMENT",
                line.number,
                format!("Unknown entity statement {}", line.text),
            ));
        }
        index += 1;
    }
    Ok((
        EntityDefinition {
            id: name.to_owned(),
            fields,
            owner_field,
            links,
            line: lines[start].number,
        },
        index,
    ))
}

pub(super) fn parse_policy(
    lines: &[Line],
    start: usize,
    name: &str,
) -> DslResult<(PolicyDefinition, usize)> {
    identifier(name, lines[start].number)?;
    let mut effects = Vec::new();
    let mut index = start + 1;
    while index < lines.len() && lines[index].indent > 0 {
        let line = &lines[index];
        require_indent(line, 2)?;
        let value = line.text.strip_prefix("effect ").ok_or_else(|| {
            DslError::new(
                "UNKNOWN_POLICY_STATEMENT",
                line.number,
                format!("Unknown policy statement {}", line.text),
            )
        })?;
        effects.push(parse_aggregate_effect(&Line {
            number: line.number,
            indent: line.indent,
            text: value.to_owned(),
        })?);
        index += 1;
    }
    Ok((
        PolicyDefinition {
            id: name.to_owned(),
            effects,
            line: lines[start].number,
        },
        index,
    ))
}
