use super::model::*;
use crate::agent_types::{DurationDistribution, ProbabilityProvenance, TimedActionDefinition};
use std::collections::BTreeMap;

pub(super) struct CompiledDecision<'a> {
    pub(super) definition: &'a DecisionDefinition,
    pub(super) branches: Vec<&'a DecisionBranch>,
}

pub(super) struct CompiledAction<'a> {
    pub(super) definition: &'a ActionDefinition,
    pub(super) timed: TimedActionDefinition,
    pub(super) outcomes: Vec<&'a OutcomeDefinition>,
}

pub(super) struct CompiledProgram<'a> {
    pub(super) decisions: BTreeMap<&'a str, CompiledDecision<'a>>,
    pub(super) actions: BTreeMap<&'a str, CompiledAction<'a>>,
    pub(super) agent_state_bounds: BTreeMap<String, BTreeMap<String, ValueBounds>>,
    pub(super) place_state_bounds: BTreeMap<String, BTreeMap<String, ValueBounds>>,
}

pub(super) fn compile_program(program: &Program) -> DslResult<CompiledProgram<'_>> {
    let agent_definitions = program
        .agents
        .iter()
        .map(|definition| (definition.id.as_str(), definition))
        .collect::<BTreeMap<_, _>>();
    let decisions = program
        .decisions
        .iter()
        .map(|definition| {
            let mut branches = definition.branches.iter().collect::<Vec<_>>();
            branches.sort_by(|left, right| left.action.cmp(&right.action));
            (
                definition.id.as_str(),
                CompiledDecision {
                    definition,
                    branches,
                },
            )
        })
        .collect();
    let actions = program
        .actions
        .iter()
        .map(|definition| {
            let mut outcomes = definition.outcomes.iter().collect::<Vec<_>>();
            outcomes.sort_by(|left, right| left.id.cmp(&right.id));
            (
                definition.id.as_str(),
                CompiledAction {
                    definition,
                    timed: timed_definition(definition, program),
                    outcomes,
                },
            )
        })
        .collect();
    let agent_state_bounds = program
        .agents
        .iter()
        .map(|definition| {
            Ok((
                definition.id.clone(),
                merged_state_bounds(definition, &agent_definitions)?,
            ))
        })
        .collect::<DslResult<BTreeMap<_, _>>>()?;
    let place_state_bounds = program
        .places
        .iter()
        .map(|place| (place.id.clone(), place.state_bounds.clone()))
        .collect();
    Ok(CompiledProgram {
        decisions,
        actions,
        agent_state_bounds,
        place_state_bounds,
    })
}

fn merged_state_bounds(
    agent: &AgentDefinition,
    agents: &BTreeMap<&str, &AgentDefinition>,
) -> DslResult<BTreeMap<String, ValueBounds>> {
    let mut result = if let Some(parent) = &agent.parent {
        merged_state_bounds(agents[parent.as_str()], agents)?
    } else {
        BTreeMap::new()
    };
    result.extend(agent.state_bounds.clone());
    Ok(result)
}

fn timed_definition(action: &ActionDefinition, program: &Program) -> TimedActionDefinition {
    let mut shape_parameters = BTreeMap::new();
    if let Some(sigma) = action.duration.sigma {
        shape_parameters.insert("sigma".to_owned(), sigma);
    }
    TimedActionDefinition {
        action_id: action.id.clone(),
        category: action.aggregate.clone(),
        duration: DurationDistribution {
            duration_min_hours: action.duration.minimum,
            duration_median_hours: action.duration.median,
            duration_max_hours: action.duration.maximum,
            shape: action.duration.shape.clone(),
            shape_parameters,
            provenance: placeholder_provenance(program),
        },
        duration_overrides: Vec::new(),
        location_place_index_by_agent: Vec::new(),
        priority: 0,
        passive: false,
        interruptibility: "interruptible".to_owned(),
        interruption_outcome: "defer".to_owned(),
        emergency_interruptions: Vec::new(),
    }
}

fn placeholder_provenance(program: &Program) -> ProbabilityProvenance {
    ProbabilityProvenance {
        source: program.placeholder_label.clone(),
        version: program.version.clone(),
        status: "default_estimated".to_owned(),
        resolution_status: None,
        source_places: Vec::new(),
        uncertainty: 1.0,
        source_date: None,
        evidence_id: None,
        evidence_kind: Some("placeholder".to_owned()),
        ci_low: Some(0.0),
        ci_high: Some(1.0),
    }
}
