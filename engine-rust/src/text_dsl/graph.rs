use super::model::*;
use super::population_distribution::{PopulationAllocation, build_population_plan};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct ProgramGraph {
    pub nodes: Vec<GraphNode>,
    pub edges: Vec<GraphEdge>,
    pub slices: Vec<GraphSlice>,
    pub orphan_agents: Vec<String>,
    pub population_paths: Vec<PopulationAllocation>,
    pub default_run_id: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct GraphSlice {
    pub id: String,
    pub group: String,
    pub collapsed: bool,
    pub node_count: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct GraphNode {
    pub id: String,
    pub node_kind: String,
    pub vertical_slice: String,
    pub level: String,
    pub parent_id: Option<String>,
    pub parent_ids: Vec<String>,
    pub also_used_in: Vec<String>,
    pub graph_group: String,
    pub inherits_from: Option<String>,
    pub weight: Option<f64>,
    pub distribution_probability: Option<f64>,
    pub expected_represented: Option<f64>,
    pub actual_represented: Option<u64>,
    pub expected_simulated: Option<f64>,
    pub actual_simulated: Option<u64>,
    pub represented_count: Option<u64>,
    pub simulated_count: Option<usize>,
    pub line: usize,
    pub cached: bool,
    pub sync_interval_days: Option<u32>,
    pub places: Vec<String>,
    pub roles_exposed: Vec<GraphRoleExposure>,
    pub subtree_role_count: usize,
    pub subtree_roles: Vec<String>,
    pub roles_used: Vec<String>,
    pub parameters: BTreeMap<String, f64>,
    pub states: Vec<String>,
    pub traits: Vec<String>,
    pub initial: Vec<String>,
    pub decisions: Vec<GraphDecision>,
    pub actions: Vec<GraphAction>,
    pub outputs: Vec<String>,
    pub couplings: Vec<GraphCoupling>,
    pub aggregate: Option<GraphAggregate>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct GraphRoleExposure {
    pub id: String,
    pub actions: Vec<String>,
    pub decisions: Vec<String>,
    pub conditions: Vec<String>,
    pub leader: bool,
    pub count: Option<usize>,
    pub sources: Vec<GraphRoleSource>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct GraphRoleSource {
    pub kind: String,
    pub owner: String,
    pub line: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct GraphDecision {
    pub id: String,
    pub branches: Vec<GraphBranch>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct GraphBranch {
    pub action: String,
    pub probability: String,
    pub condition: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct GraphAction {
    pub id: String,
    pub aggregate: String,
    pub duration: String,
    pub effects: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct GraphCoupling {
    pub id: String,
    pub source: String,
    pub target: String,
    pub formula: String,
    pub sync_interval_days: Option<u32>,
    pub line: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct GraphAggregate {
    pub id: String,
    pub inputs: Vec<GraphAggregateInput>,
    pub valid_for_days: u32,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct GraphAggregateInput {
    pub id: String,
    pub default: f64,
    pub minimum: f64,
    pub maximum: f64,
    pub invalidate_threshold: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct GraphEdge {
    pub id: String,
    pub from_id: String,
    pub to_id: String,
    pub kind: String,
    pub weight: Option<f64>,
    pub sync_interval_days: Option<u32>,
    pub line: usize,
    pub formula: Option<String>,
}

pub fn build_program_graph(program: &Program) -> DslResult<ProgramGraph> {
    let parents = canonical_parents(program);
    let all_parents = all_parents(program);
    let weights = canonical_weights(program, &parents);
    let mut nodes = Vec::new();
    for composition in &program.compositions {
        nodes.push(composition_node(
            program,
            composition,
            &parents,
            &all_parents,
            &weights,
        )?);
    }
    for archetype in &program.archetypes {
        nodes.push(archetype_node(
            program,
            archetype,
            &parents,
            &all_parents,
            &weights,
        ));
    }
    for agent in &program.agents {
        nodes.push(agent_node(program, agent, &parents, &all_parents, &weights));
    }
    let edges = graph_edges(program);
    apply_subtree_role_counts(program, &mut nodes);
    apply_coupled_role_usage(&edges, &mut nodes);
    nodes.sort_by_key(|node| node.line);
    let slices = graph_slices(&nodes);
    let orphan_agents = orphan_agents(program);
    let default_run_id = program
        .compositions
        .iter()
        .find(|composition| composition.default_run)
        .map(|composition| composition.id.clone());
    let mut population_paths = Vec::new();
    for composition in &program.compositions {
        let same_slice_parent = all_parents
            .get(&composition.id)
            .into_iter()
            .flatten()
            .filter_map(|parent| {
                program
                    .compositions
                    .iter()
                    .find(|candidate| candidate.id == *parent)
            })
            .any(|parent| parent.slice == composition.slice);
        if composition.graph_group.as_deref() == Some("main") && !same_slice_parent {
            population_paths.extend(build_population_plan(program, &composition.id, 1, None)?);
        }
    }
    if let Some(id) = default_run_id.as_deref() {
        population_paths.extend(build_population_plan(program, id, 1, None)?);
    }
    apply_population_defaults(&population_paths, &mut nodes);
    Ok(ProgramGraph {
        nodes,
        edges,
        slices,
        orphan_agents,
        population_paths,
        default_run_id,
    })
}

fn all_parents(program: &Program) -> BTreeMap<String, Vec<String>> {
    let mut parents = BTreeMap::<String, Vec<String>>::new();
    for composition in &program.compositions {
        for entry in &composition.entries {
            parents
                .entry(entry.child.clone())
                .or_default()
                .push(composition.id.clone());
        }
    }
    for archetype in &program.archetypes {
        for agent_type in archetype
            .composition
            .iter()
            .flat_map(|group| &group.mix)
            .map(|entry| root_agent_type(program, &entry.agent_type))
            .collect::<BTreeSet<_>>()
        {
            parents
                .entry(agent_type)
                .or_default()
                .push(archetype.id.clone());
        }
    }
    for agent in &program.agents {
        if let Some(parent) = &agent.parent {
            parents
                .entry(agent.id.clone())
                .or_default()
                .push(parent.clone());
        }
    }
    for values in parents.values_mut() {
        values.sort();
        values.dedup();
    }
    parents
}

fn root_agent_type(program: &Program, id: &str) -> String {
    let mut current = id;
    let mut visited = BTreeSet::new();
    while let Some(parent) = program
        .agents
        .iter()
        .find(|agent| agent.id == current)
        .and_then(|agent| agent.parent.as_deref())
    {
        if !visited.insert(current) {
            break;
        }
        current = parent;
    }
    current.to_owned()
}

fn graph_slices(nodes: &[GraphNode]) -> Vec<GraphSlice> {
    let mut values = BTreeMap::<String, (String, usize)>::new();
    for node in nodes {
        let entry = values
            .entry(node.vertical_slice.clone())
            .or_insert_with(|| (node.graph_group.clone(), 0));
        if graph_group_priority(&node.graph_group) < graph_group_priority(&entry.0) {
            entry.0 = node.graph_group.clone();
        }
        entry.1 += 1;
    }
    values
        .into_iter()
        .map(|(id, (group, node_count))| GraphSlice {
            id,
            collapsed: matches!(group.as_str(), "lab" | "allocation"),
            group,
            node_count,
        })
        .collect()
}

fn graph_group_priority(group: &str) -> usize {
    match group {
        "main" => 0,
        "coupled" => 1,
        "allocation" => 2,
        _ => 3,
    }
}

fn canonical_parents(program: &Program) -> BTreeMap<String, String> {
    let mut parents = BTreeMap::new();
    for composition in &program.compositions {
        if !composition.couplings.is_empty() || !composition.boundaries.is_empty() {
            continue;
        }
        for entry in &composition.entries {
            parents
                .entry(entry.child.clone())
                .or_insert_with(|| composition.id.clone());
        }
    }
    for archetype in &program.archetypes {
        for group in &archetype.composition {
            for entry in &group.mix {
                parents
                    .entry(entry.agent_type.clone())
                    .or_insert_with(|| archetype.id.clone());
            }
        }
    }
    parents
}

fn canonical_weights(
    program: &Program,
    parents: &BTreeMap<String, String>,
) -> BTreeMap<String, f64> {
    let mut weights = BTreeMap::new();
    for composition in &program.compositions {
        for entry in &composition.entries {
            if parents.get(&entry.child) == Some(&composition.id) {
                weights.insert(entry.child.clone(), entry.weight);
            }
        }
    }
    weights
}

fn composition_node(
    program: &Program,
    composition: &CompositionDefinition,
    parents: &BTreeMap<String, String>,
    all_parents: &BTreeMap<String, Vec<String>>,
    weights: &BTreeMap<String, f64>,
) -> DslResult<GraphNode> {
    let roles = composition_roles(program, composition);
    let role_ids = roles
        .iter()
        .map(|role| role.id.clone())
        .collect::<BTreeSet<_>>();
    let decisions = role_decisions(program, &role_ids);
    let actions = role_actions(program, &role_ids);
    let couplings = composition
        .couplings
        .iter()
        .map(|coupling| GraphCoupling {
            id: coupling.id.clone(),
            source: coupling.source.clone(),
            target: coupling.target.clone(),
            formula: expression_text(&coupling.value),
            sync_interval_days: coupling
                .cadence_days
                .or_else(|| composition.cached.as_ref().map(|cached| cached.sync_days)),
            line: coupling.line,
        })
        .chain(composition.boundaries.iter().map(|boundary| GraphCoupling {
            id: boundary.id.clone(),
            source: boundary.source.clone(),
            target: boundary.target.clone(),
            formula: format!("identity({})", boundary.fields.join(", ")),
            sync_interval_days: composition.cached.as_ref().map(|cached| cached.sync_days),
            line: boundary.line,
        }))
        .collect();
    Ok(GraphNode {
        id: composition.id.clone(),
        node_kind: "composition".to_owned(),
        vertical_slice: composition
            .slice
            .clone()
            .unwrap_or_else(|| "Labs".to_owned()),
        level: composition.level.clone(),
        parent_id: parents.get(&composition.id).cloned(),
        parent_ids: all_parents
            .get(&composition.id)
            .cloned()
            .unwrap_or_default(),
        also_used_in: all_parents
            .get(&composition.id)
            .filter(|parents| parents.len() > 1)
            .cloned()
            .unwrap_or_default(),
        graph_group: composition
            .graph_group
            .clone()
            .unwrap_or_else(|| "lab".to_owned()),
        inherits_from: None,
        weight: weights.get(&composition.id).copied(),
        distribution_probability: weights.get(&composition.id).copied(),
        expected_represented: None,
        actual_represented: composition.represented_population,
        expected_simulated: None,
        actual_simulated: None,
        represented_count: composition
            .represented_population
            .or(composition.authoritative_total),
        simulated_count: Some(composition_simulated_count(program, composition)),
        line: composition.line,
        cached: composition.cached.is_some(),
        sync_interval_days: composition.cached.as_ref().map(|cached| cached.sync_days),
        places: composition.places.clone(),
        roles_exposed: roles,
        subtree_role_count: 0,
        subtree_roles: Vec::new(),
        roles_used: Vec::new(),
        parameters: composition.parameters.clone(),
        states: composition_place_states(program, composition),
        traits: Vec::new(),
        initial: Vec::new(),
        decisions,
        actions,
        outputs: composition
            .outputs
            .iter()
            .map(|output| output.id.clone())
            .collect(),
        couplings,
        aggregate: graph_aggregate(program, &composition.id),
    })
}

fn archetype_node(
    program: &Program,
    archetype: &ArchetypeDefinition,
    parents: &BTreeMap<String, String>,
    all_parents: &BTreeMap<String, Vec<String>>,
    weights: &BTreeMap<String, f64>,
) -> GraphNode {
    let role_ids = archetype_role_ids(program, archetype);
    GraphNode {
        id: archetype.id.clone(),
        node_kind: "archetype".to_owned(),
        vertical_slice: inherited_slice(program, &archetype.id, all_parents),
        level: if archetype.spotlight {
            "spotlight"
        } else {
            "archetype"
        }
        .to_owned(),
        parent_id: parents.get(&archetype.id).cloned(),
        parent_ids: all_parents.get(&archetype.id).cloned().unwrap_or_default(),
        also_used_in: all_parents
            .get(&archetype.id)
            .filter(|parents| parents.len() > 1)
            .cloned()
            .unwrap_or_default(),
        graph_group: inherited_graph_group(program, &archetype.id, all_parents),
        inherits_from: None,
        weight: weights.get(&archetype.id).copied(),
        distribution_probability: weights.get(&archetype.id).copied(),
        expected_represented: None,
        actual_represented: None,
        expected_simulated: None,
        actual_simulated: None,
        represented_count: None,
        simulated_count: Some(
            archetype.sample_households
                * archetype
                    .composition
                    .iter()
                    .map(|group| group.count)
                    .sum::<usize>(),
        ),
        line: archetype.line,
        cached: program
            .aggregate_functions
            .iter()
            .any(|function| function.id == archetype.id),
        sync_interval_days: None,
        places: Vec::new(),
        roles_exposed: role_exposures(
            program,
            &role_ids,
            &BTreeMap::new(),
            &archetype.id,
            archetype.line,
            "direct",
        ),
        subtree_role_count: role_ids.len(),
        subtree_roles: role_ids.iter().cloned().collect(),
        roles_used: Vec::new(),
        parameters: BTreeMap::new(),
        states: Vec::new(),
        traits: Vec::new(),
        initial: archetype
            .initial
            .iter()
            .map(|assignment| format!("{} ~ {}", assignment.field, assignment.distribution.kind))
            .collect(),
        decisions: role_decisions(program, &role_ids),
        actions: role_actions(program, &role_ids),
        outputs: archetype
            .outputs
            .iter()
            .map(|output| output.id.clone())
            .collect(),
        couplings: Vec::new(),
        aggregate: graph_aggregate(program, &archetype.id),
    }
}

fn agent_node(
    program: &Program,
    agent: &AgentDefinition,
    parents: &BTreeMap<String, String>,
    all_parents: &BTreeMap<String, Vec<String>>,
    weights: &BTreeMap<String, f64>,
) -> GraphNode {
    let role_ids = agent_role_ids(program, &agent.id);
    let mut decisions = role_decisions(program, &role_ids);
    if let Some(decision) = program
        .decisions
        .iter()
        .find(|item| item.id == agent.routine)
    {
        decisions.insert(0, graph_decision(decision));
    }
    GraphNode {
        id: agent.id.clone(),
        node_kind: "agent".to_owned(),
        vertical_slice: inherited_slice(program, &agent.id, all_parents),
        level: "agent".to_owned(),
        parent_id: parents.get(&agent.id).cloned(),
        parent_ids: all_parents.get(&agent.id).cloned().unwrap_or_default(),
        also_used_in: all_parents
            .get(&agent.id)
            .filter(|parents| parents.len() > 1)
            .cloned()
            .unwrap_or_default(),
        graph_group: inherited_graph_group(program, &agent.id, all_parents),
        inherits_from: agent.parent.clone(),
        weight: weights.get(&agent.id).copied(),
        distribution_probability: weights.get(&agent.id).copied(),
        expected_represented: None,
        actual_represented: None,
        expected_simulated: None,
        actual_simulated: None,
        represented_count: None,
        simulated_count: None,
        line: agent.line,
        cached: false,
        sync_interval_days: None,
        places: agent_initial_places(agent),
        roles_exposed: role_exposures(
            program,
            &role_ids,
            &BTreeMap::new(),
            &agent.id,
            agent.line,
            if agent.parent.is_some() {
                "inherited"
            } else {
                "direct"
            },
        ),
        subtree_role_count: role_ids.len(),
        subtree_roles: role_ids.iter().cloned().collect(),
        roles_used: Vec::new(),
        parameters: BTreeMap::new(),
        states: agent.states.iter().cloned().collect(),
        traits: agent.traits.iter().cloned().collect(),
        initial: agent
            .initial
            .iter()
            .map(|assignment| format!("{} ~ {}", assignment.field, assignment.distribution.kind))
            .collect(),
        decisions,
        actions: role_actions(program, &role_ids),
        outputs: Vec::new(),
        couplings: Vec::new(),
        aggregate: None,
    }
}

fn inherited_slice(program: &Program, id: &str, parents: &BTreeMap<String, Vec<String>>) -> String {
    inherited_metadata(program, id, parents)
        .map(|composition| {
            composition
                .slice
                .clone()
                .unwrap_or_else(|| "Labs".to_owned())
        })
        .unwrap_or_else(|| "Orphan agents (not in any composition)".to_owned())
}

fn inherited_graph_group(
    program: &Program,
    id: &str,
    parents: &BTreeMap<String, Vec<String>>,
) -> String {
    inherited_metadata(program, id, parents)
        .and_then(|composition| composition.graph_group.clone())
        .unwrap_or_else(|| "orphan".to_owned())
}

fn inherited_metadata<'a>(
    program: &'a Program,
    id: &str,
    parents: &BTreeMap<String, Vec<String>>,
) -> Option<&'a CompositionDefinition> {
    let mut pending = parents.get(id).cloned().unwrap_or_default();
    let mut visited = BTreeSet::new();
    let mut candidates = Vec::new();
    while let Some(parent) = pending.pop() {
        if !visited.insert(parent.clone()) {
            continue;
        }
        if let Some(composition) = program
            .compositions
            .iter()
            .find(|composition| composition.id == parent)
        {
            candidates.push(composition);
        } else {
            pending.extend(parents.get(&parent).cloned().unwrap_or_default());
        }
    }
    candidates.into_iter().min_by_key(|composition| {
        graph_group_priority(composition.graph_group.as_deref().unwrap_or("lab"))
    })
}

fn orphan_agents(program: &Program) -> Vec<String> {
    let agents = program
        .agents
        .iter()
        .map(|agent| (agent.id.as_str(), agent))
        .collect::<BTreeMap<_, _>>();
    let mut referenced = program
        .archetypes
        .iter()
        .flat_map(|archetype| &archetype.composition)
        .flat_map(|group| &group.mix)
        .map(|entry| entry.agent_type.clone())
        .collect::<BTreeSet<_>>();
    let mut pending = referenced.iter().cloned().collect::<Vec<_>>();
    while let Some(id) = pending.pop() {
        if let Some(parent) = agents
            .get(id.as_str())
            .and_then(|agent| agent.parent.clone())
            && referenced.insert(parent.clone())
        {
            pending.push(parent);
        }
    }
    let mut changed = true;
    while changed {
        changed = false;
        for agent in &program.agents {
            if agent
                .parent
                .as_ref()
                .is_some_and(|parent| referenced.contains(parent))
                && referenced.insert(agent.id.clone())
            {
                changed = true;
            }
        }
    }
    program
        .agents
        .iter()
        .filter(|agent| !referenced.contains(&agent.id))
        .map(|agent| agent.id.clone())
        .collect()
}

fn apply_population_defaults(paths: &[PopulationAllocation], nodes: &mut [GraphNode]) {
    for node in nodes {
        let matches = paths
            .iter()
            .filter(|allocation| allocation.node_id == node.id)
            .collect::<Vec<_>>();
        let Some(first) = matches.first() else {
            continue;
        };
        node.distribution_probability = Some(first.probability);
        node.expected_represented = Some(first.expected_represented);
        node.actual_represented = Some(first.actual_represented);
        node.expected_simulated = Some(first.expected_simulated);
        node.actual_simulated = Some(first.actual_simulated);
        node.represented_count = Some(first.actual_represented);
        node.simulated_count = Some(first.actual_simulated as usize);
    }
}

fn graph_edges(program: &Program) -> Vec<GraphEdge> {
    let mut edges = Vec::new();
    for composition in &program.compositions {
        for entry in &composition.entries {
            edges.push(GraphEdge {
                id: format!("{}:{}", composition.id, entry.child),
                from_id: composition.id.clone(),
                to_id: entry.child.clone(),
                kind: "parent_child".to_owned(),
                weight: Some(entry.weight),
                sync_interval_days: None,
                line: entry.line,
                formula: None,
            });
        }
        for coupling in &composition.couplings {
            edges.push(GraphEdge {
                id: coupling.id.clone(),
                from_id: coupling.source.clone(),
                to_id: coupling.target.clone(),
                kind: "coupling".to_owned(),
                weight: None,
                sync_interval_days: coupling
                    .cadence_days
                    .or_else(|| composition.cached.as_ref().map(|cached| cached.sync_days)),
                line: coupling.line,
                formula: Some(expression_text(&coupling.value)),
            });
        }
        for boundary in &composition.boundaries {
            edges.push(GraphEdge {
                id: boundary.id.clone(),
                from_id: boundary.source.clone(),
                to_id: boundary.target.clone(),
                kind: "coupling".to_owned(),
                weight: None,
                sync_interval_days: composition.cached.as_ref().map(|cached| cached.sync_days),
                line: boundary.line,
                formula: Some(format!("identity({})", boundary.fields.join(", "))),
            });
        }
    }
    for archetype in &program.archetypes {
        for agent_type in archetype
            .composition
            .iter()
            .flat_map(|group| &group.mix)
            .map(|entry| root_agent_type(program, &entry.agent_type))
            .collect::<BTreeSet<_>>()
        {
            let line = archetype
                .composition
                .iter()
                .flat_map(|group| &group.mix)
                .find(|entry| root_agent_type(program, &entry.agent_type) == agent_type)
                .map_or(archetype.line, |entry| entry.line);
            edges.push(GraphEdge {
                id: format!("{}:{agent_type}", archetype.id),
                from_id: archetype.id.clone(),
                to_id: agent_type,
                kind: "parent_child".to_owned(),
                weight: None,
                sync_interval_days: None,
                line,
                formula: None,
            });
        }
    }
    for agent in &program.agents {
        if let Some(parent) = &agent.parent {
            edges.push(GraphEdge {
                id: format!("{parent}:{}", agent.id),
                from_id: parent.clone(),
                to_id: agent.id.clone(),
                kind: "parent_child".to_owned(),
                weight: None,
                sync_interval_days: None,
                line: agent.line,
                formula: Some("inherits".to_owned()),
            });
        }
    }
    edges
}

fn composition_roles(
    program: &Program,
    composition: &CompositionDefinition,
) -> Vec<GraphRoleExposure> {
    let mut counts = composition
        .leaders
        .iter()
        .map(|leader| (leader.role.clone(), leader.count))
        .collect::<BTreeMap<_, _>>();
    let mut role_ids = counts.keys().cloned().collect::<BTreeSet<_>>();
    for entry in &composition.entries {
        if let Some(archetype) = program
            .archetypes
            .iter()
            .find(|archetype| archetype.id == entry.child)
        {
            role_ids.extend(archetype_role_ids(program, archetype));
        }
    }
    for role in &role_ids {
        counts.entry(role.clone()).or_insert(0);
    }
    role_exposures(
        program,
        &role_ids,
        &counts,
        &composition.id,
        composition.line,
        "inherited",
    )
}

fn archetype_role_ids(program: &Program, archetype: &ArchetypeDefinition) -> BTreeSet<String> {
    let mut roles = archetype.roles.clone();
    for group in &archetype.composition {
        for entry in &group.mix {
            roles.extend(agent_role_ids(program, &entry.agent_type));
        }
    }
    roles
}

fn agent_role_ids(program: &Program, agent_id: &str) -> BTreeSet<String> {
    let Some(agent) = program.agents.iter().find(|agent| agent.id == agent_id) else {
        return BTreeSet::new();
    };
    let mut roles = agent
        .parent
        .as_ref()
        .map_or_else(BTreeSet::new, |parent| agent_role_ids(program, parent));
    roles.extend(agent.roles.iter().cloned());
    roles.extend(
        program
            .role_distributions
            .iter()
            .filter(|distribution| distribution.agent_type == agent.id)
            .map(|distribution| distribution.role.clone()),
    );
    roles
}

fn role_exposures(
    program: &Program,
    role_ids: &BTreeSet<String>,
    leader_counts: &BTreeMap<String, usize>,
    owner: &str,
    owner_line: usize,
    default_kind: &str,
) -> Vec<GraphRoleExposure> {
    role_ids
        .iter()
        .map(|id| {
            let definition = program.roles.iter().find(|role| role.id == *id);
            GraphRoleExposure {
                id: id.clone(),
                actions: definition
                    .into_iter()
                    .flat_map(|role| &role.decisions)
                    .flat_map(|decision| &decision.branches)
                    .map(|branch| branch.action.clone())
                    .collect::<BTreeSet<_>>()
                    .into_iter()
                    .collect(),
                decisions: definition
                    .into_iter()
                    .flat_map(|role| &role.decisions)
                    .map(|decision| decision.id.clone())
                    .collect(),
                conditions: definition
                    .into_iter()
                    .flat_map(|role| &role.decisions)
                    .flat_map(|decision| &decision.branches)
                    .filter_map(|branch| branch.condition.as_ref().map(expression_text))
                    .chain(
                        program
                            .role_distributions
                            .iter()
                            .filter(|distribution| distribution.role == *id)
                            .map(|distribution| expression_text(&distribution.condition)),
                    )
                    .collect::<BTreeSet<_>>()
                    .into_iter()
                    .collect(),
                leader: leader_counts.get(id).is_some_and(|count| *count > 0),
                count: leader_counts.get(id).copied().filter(|count| *count > 0),
                sources: vec![GraphRoleSource {
                    kind: if leader_counts.get(id).is_some_and(|count| *count > 0) {
                        "leader"
                    } else {
                        default_kind
                    }
                    .to_owned(),
                    owner: owner.to_owned(),
                    line: owner_line,
                }],
            }
        })
        .collect()
}

fn role_decisions(program: &Program, role_ids: &BTreeSet<String>) -> Vec<GraphDecision> {
    program
        .roles
        .iter()
        .filter(|role| role_ids.contains(&role.id))
        .flat_map(|role| &role.decisions)
        .map(graph_decision)
        .collect()
}

fn graph_decision(decision: &DecisionDefinition) -> GraphDecision {
    GraphDecision {
        id: decision.id.clone(),
        branches: decision
            .branches
            .iter()
            .map(|branch| GraphBranch {
                action: branch.action.clone(),
                probability: expression_text(&branch.probability),
                condition: branch.condition.as_ref().map(expression_text),
            })
            .collect(),
    }
}

fn role_actions(program: &Program, role_ids: &BTreeSet<String>) -> Vec<GraphAction> {
    let action_ids = program
        .roles
        .iter()
        .filter(|role| role_ids.contains(&role.id))
        .flat_map(|role| &role.decisions)
        .flat_map(|decision| &decision.branches)
        .map(|branch| branch.action.as_str())
        .collect::<BTreeSet<_>>();
    program
        .actions
        .iter()
        .filter(|action| action_ids.contains(action.id.as_str()))
        .map(graph_action)
        .collect()
}

fn graph_action(action: &ActionDefinition) -> GraphAction {
    GraphAction {
        id: action.id.clone(),
        aggregate: action.aggregate.clone(),
        duration: format!(
            "{} {} / {} / {} hours",
            action.duration.shape,
            action.duration.minimum,
            action.duration.median,
            action.duration.maximum
        ),
        effects: action
            .outcomes
            .iter()
            .flat_map(|outcome| &outcome.effects)
            .map(|effect| {
                format!(
                    "{} {} {}",
                    effect_target(effect),
                    effect.operation,
                    expression_text(&effect.value)
                )
            })
            .collect(),
    }
}

fn effect_target(effect: &EffectDefinition) -> String {
    match &effect.scope {
        EffectScope::SelfAgent => format!("self.{}", effect.field),
        EffectScope::Target => format!("target.{}", effect.field),
        EffectScope::CurrentPlace => format!("current place {}", effect.field),
        EffectScope::AllAt { place, .. } => format!("all at {place} {}", effect.field),
        EffectScope::Place { place } => format!("place {place} {}", effect.field),
        EffectScope::RelationshipWithTarget => {
            format!("relationship with target {}", effect.field)
        }
    }
}

fn graph_aggregate(program: &Program, id: &str) -> Option<GraphAggregate> {
    let function = program
        .aggregate_functions
        .iter()
        .find(|function| function.id == id)?;
    Some(GraphAggregate {
        id: function.id.clone(),
        inputs: function
            .inputs
            .iter()
            .map(|input| GraphAggregateInput {
                id: input.id.clone(),
                default: input.default,
                minimum: input.minimum,
                maximum: input.maximum,
                invalidate_threshold: input.invalidate_threshold,
            })
            .collect(),
        valid_for_days: function.cache.valid_for_days,
    })
}

fn composition_place_states(program: &Program, composition: &CompositionDefinition) -> Vec<String> {
    composition
        .places
        .iter()
        .filter_map(|id| program.places.iter().find(|place| place.id == *id))
        .flat_map(|place| {
            place
                .states
                .iter()
                .map(move |(id, value)| format!("{}.{} = {}", place.id, id, value_text(value)))
        })
        .collect()
}

fn agent_initial_places(agent: &AgentDefinition) -> Vec<String> {
    agent
        .initial
        .iter()
        .filter(|assignment| assignment.field == "location")
        .flat_map(|assignment| &assignment.distribution.categories)
        .map(|(place, _)| place.clone())
        .collect()
}

fn composition_simulated_count(program: &Program, root: &CompositionDefinition) -> usize {
    let compositions = program
        .compositions
        .iter()
        .map(|item| (item.id.as_str(), item))
        .collect::<BTreeMap<_, _>>();
    let archetypes = program
        .archetypes
        .iter()
        .map(|item| (item.id.as_str(), item))
        .collect::<BTreeMap<_, _>>();
    let mut ids = BTreeSet::new();
    collect_archetypes(root, &compositions, &archetypes, &mut ids);
    ids.into_iter()
        .map(|id| {
            let archetype = archetypes[id];
            archetype.sample_households
                * archetype
                    .composition
                    .iter()
                    .map(|group| group.count)
                    .sum::<usize>()
        })
        .sum()
}

fn collect_archetypes<'a>(
    composition: &'a CompositionDefinition,
    compositions: &BTreeMap<&'a str, &'a CompositionDefinition>,
    archetypes: &BTreeMap<&'a str, &'a ArchetypeDefinition>,
    ids: &mut BTreeSet<&'a str>,
) {
    for entry in &composition.entries {
        if archetypes.contains_key(entry.child.as_str()) {
            ids.insert(entry.child.as_str());
        } else if let Some(child) = compositions.get(entry.child.as_str()) {
            collect_archetypes(child, compositions, archetypes, ids);
        }
    }
}

fn apply_subtree_role_counts(program: &Program, nodes: &mut [GraphNode]) {
    let roles = nodes
        .iter()
        .map(|node| {
            (
                node.id.clone(),
                node.roles_exposed
                    .iter()
                    .map(|role| role.id.clone())
                    .collect::<BTreeSet<_>>(),
            )
        })
        .collect::<BTreeMap<_, _>>();
    let children = program
        .compositions
        .iter()
        .map(|composition| {
            (
                composition.id.clone(),
                composition
                    .entries
                    .iter()
                    .map(|entry| entry.child.clone())
                    .collect::<Vec<_>>(),
            )
        })
        .collect::<BTreeMap<_, _>>();
    for node in nodes {
        let mut subtree = BTreeSet::new();
        collect_subtree_roles(&node.id, &children, &roles, &mut subtree);
        node.subtree_role_count = subtree.len();
        node.subtree_roles = subtree.into_iter().collect();
    }
}

fn collect_subtree_roles(
    id: &str,
    children: &BTreeMap<String, Vec<String>>,
    roles: &BTreeMap<String, BTreeSet<String>>,
    result: &mut BTreeSet<String>,
) {
    if let Some(values) = roles.get(id) {
        result.extend(values.iter().cloned());
    }
    for child in children.get(id).into_iter().flatten() {
        collect_subtree_roles(child, children, roles, result);
    }
}

fn apply_coupled_role_usage(edges: &[GraphEdge], nodes: &mut [GraphNode]) {
    let leader_roles = nodes
        .iter()
        .flat_map(|node| &node.roles_exposed)
        .filter(|role| role.leader)
        .map(|role| role.id.clone())
        .collect::<BTreeSet<_>>();
    let direct = nodes
        .iter()
        .map(|node| {
            (
                node.id.clone(),
                node.roles_exposed
                    .iter()
                    .map(|role| role.id.clone())
                    .collect::<BTreeSet<_>>(),
            )
        })
        .collect::<BTreeMap<_, _>>();
    let mut used = nodes
        .iter()
        .map(|node| {
            (
                node.id.clone(),
                node.roles_used.iter().cloned().collect::<BTreeSet<_>>(),
            )
        })
        .collect::<BTreeMap<_, _>>();
    for _ in 0..nodes.len().max(1) {
        let mut changed = false;
        for edge in edges {
            let source_roles = direct
                .get(&edge.from_id)
                .into_iter()
                .flatten()
                .chain(used.get(&edge.from_id).into_iter().flatten())
                .filter(|role| !leader_roles.contains(*role))
                .cloned()
                .collect::<BTreeSet<_>>();
            let propagate = edge.kind == "coupling" || !used[&edge.from_id].is_empty();
            if propagate {
                let target = used.get_mut(&edge.to_id).unwrap();
                let before = target.len();
                target.extend(source_roles);
                changed |= before != target.len();
            }
        }
        if !changed {
            break;
        }
    }
    for node in nodes {
        node.roles_used = used
            .remove(&node.id)
            .unwrap_or_default()
            .into_iter()
            .collect();
    }
}

fn expression_text(expression: &Expr) -> String {
    match expression {
        Expr::Value(value) => value_text(value),
        Expr::Variable(value) => value.clone(),
        Expr::Unary { operation, value } => format!("{operation} {}", expression_text(value)),
        Expr::Binary {
            operation,
            left,
            right,
        } => format!(
            "({} {operation} {})",
            expression_text(left),
            expression_text(right)
        ),
        Expr::Conditional {
            condition,
            when_true,
            when_false,
        } => format!(
            "{} if {} else {}",
            expression_text(when_true),
            expression_text(condition),
            expression_text(when_false)
        ),
        Expr::Call {
            function,
            arguments,
        } => format!(
            "{function}({})",
            arguments
                .iter()
                .map(expression_text)
                .collect::<Vec<_>>()
                .join(", ")
        ),
    }
}

fn value_text(value: &DslValue) -> String {
    match value {
        DslValue::Number(value) => value.to_string(),
        DslValue::Bool(value) => value.to_string(),
        DslValue::Text(value) => value.clone(),
    }
}
