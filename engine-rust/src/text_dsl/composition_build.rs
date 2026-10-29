use super::archetypes::{build_archetype_state, ensure_action_metric_report};
use super::compositions::CompositionBuild;
use super::expression::evaluate;
use super::model::*;
use super::runtime::apply_role_distributions;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone)]
struct CompositionLeaf {
    archetype: String,
    namespace: String,
    root_group: String,
    weight: f64,
    scopes: Vec<(String, Vec<String>)>,
    composition_path: Vec<String>,
}

struct CompositionNode<'a> {
    definition: &'a CompositionDefinition,
    path: Vec<String>,
}

pub(super) fn build_composition_state(
    program: &Program,
    composition: &CompositionDefinition,
    seed: u64,
) -> DslResult<CompositionBuild> {
    let archetypes = program
        .archetypes
        .iter()
        .map(|item| (item.id.as_str(), item))
        .collect::<BTreeMap<_, _>>();
    let compositions = program
        .compositions
        .iter()
        .map(|item| (item.id.as_str(), item))
        .collect::<BTreeMap<_, _>>();
    let root_scope = vec![(String::new(), composition.places.clone())];
    let mut leaves = Vec::new();
    flatten_composition(
        composition,
        &compositions,
        &archetypes,
        1.0,
        &[],
        &root_scope,
        None,
        &mut leaves,
    );
    let allocations = leaf_allocations(
        &leaves,
        &archetypes,
        composition.exemplar_households,
        seed,
        &composition.id,
    )?;
    let mut combined = program.clone();
    combined.places.clear();
    combined.agents.clear();
    combined.decisions.clear();
    combined.roles.clear();
    combined.actions.clear();
    combined.archetypes.clear();
    combined.weighted_populations.clear();
    combined.compositions.clear();
    combined.composition_populations.clear();
    combined.aggregate_functions.clear();
    combined.population.child_generation = None;
    combined.record_actions = true;
    let mut agents = Vec::new();
    let mut relationships = Vec::new();
    let mut time = Vec::new();
    let mut agent_groups = BTreeMap::new();
    let mut agent_paths = BTreeMap::new();
    let mut state_places = Vec::new();
    let mut added_places = BTreeSet::new();
    for leaf in &leaves {
        let definition = archetypes[leaf.archetype.as_str()];
        let mut sampled_definition = definition.clone();
        sampled_definition.sample_households = allocations[leaf.namespace.as_str()];
        let leaf_seed = if leaf.namespace == leaf.archetype {
            derived_seed(seed, &leaf.archetype)
        } else {
            derived_seed(seed, &leaf.namespace)
        };
        let mut sampling_program = program.clone();
        sampling_program.role_distributions.clear();
        let (prepared, mut state, _) =
            build_archetype_state(&sampling_program, &sampled_definition, leaf_seed)?;
        let place_map = scoped_place_map(program, &leaf.scopes);
        namespace_program(&mut combined, &prepared, &leaf.namespace, &place_map);
        add_scoped_places(
            program,
            &leaf.scopes,
            &place_map,
            &mut combined.places,
            &mut state_places,
            &mut added_places,
        );
        rename_state_identifiers(&mut state, &leaf.archetype, &leaf.namespace, &place_map);
        for agent in &mut state.agents {
            agent.agent_type = namespaced(&leaf.namespace, &agent.agent_type);
            agent.current_decision = namespaced(&leaf.namespace, &agent.current_decision);
            agent_groups.insert(agent.id.clone(), leaf.root_group.clone());
            agent_paths.insert(agent.id.clone(), leaf.composition_path.clone());
        }
        agents.extend(state.agents);
        relationships.extend(state.relationships);
        time.extend(state.time);
    }
    let metric_outputs = leaves
        .iter()
        .map(|leaf| leaf.archetype.as_str())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .flat_map(|id| archetypes[id].outputs.clone())
        .collect::<Vec<_>>();
    ensure_action_metric_report(&mut combined, &metric_outputs);
    let mut state = DslRunState {
        completed_ticks: 0,
        agents,
        places: state_places,
        relationships,
        time,
    };
    assign_pool_structure_roles(program, &agent_paths, seed, &mut state)?;
    let combined_agents = combined
        .agents
        .iter()
        .map(|agent| (agent.id.as_str(), agent))
        .collect::<BTreeMap<_, _>>();
    apply_role_distributions(program, seed, &combined_agents, &mut state.agents)?;
    let mut nodes = Vec::new();
    collect_composition_nodes(composition, &compositions, &[], &mut nodes);
    apply_policies(program, &nodes, &mut combined, &mut state, &agent_paths)?;
    Ok(CompositionBuild {
        program: combined,
        state,
        agent_groups,
    })
}

fn assign_pool_structure_roles(
    program: &Program,
    agent_paths: &BTreeMap<String, Vec<String>>,
    seed: u64,
    state: &mut DslRunState,
) -> DslResult<()> {
    let levels = program
        .compositions
        .iter()
        .map(|composition| (composition.id.as_str(), composition.level.as_str()))
        .collect::<BTreeMap<_, _>>();
    for agent in &mut state.agents {
        agent.roles.insert("household_member".to_owned());
        let age = agent.value("age").and_then(DslValue::as_f64).unwrap_or(0.0);
        agent.roles.remove("life_child");
        agent.roles.remove("life_student");
        agent.roles.remove("life_worker");
        let life_role = if age < 18.0 {
            "life_child"
        } else if age < 25.0 {
            "life_student"
        } else {
            "life_worker"
        };
        agent.roles.insert(life_role.to_owned());
        if let Some(path) = agent_paths.get(&agent.id) {
            for id in path {
                if let Some(level) = levels.get(id.as_str()) {
                    agent.roles.insert(format!("resident_{level}_{id}"));
                }
            }
        }
    }
    let mut households = BTreeMap::<String, Vec<usize>>::new();
    for (index, agent) in state.agents.iter().enumerate() {
        households
            .entry(agent.household_id.clone())
            .or_default()
            .push(index);
    }
    for indices in households.values() {
        let mut adults = indices
            .iter()
            .copied()
            .filter(|index| {
                state.agents[*index]
                    .value("age")
                    .and_then(DslValue::as_f64)
                    .unwrap_or(0.0)
                    >= 18.0
            })
            .collect::<Vec<_>>();
        adults.sort_by(|left, right| {
            let left_age = state.agents[*left]
                .value("age")
                .and_then(DslValue::as_f64)
                .unwrap_or(0.0);
            let right_age = state.agents[*right]
                .value("age")
                .and_then(DslValue::as_f64)
                .unwrap_or(0.0);
            right_age
                .total_cmp(&left_age)
                .then_with(|| state.agents[*left].id.cmp(&state.agents[*right].id))
        });
        if let Some(head) = adults.first() {
            state.agents[*head].roles.insert("head".to_owned());
        }
        if adults.len() >= 2 {
            let first = adults[0];
            let second = adults[1];
            state.agents[first].roles.insert("spouse".to_owned());
            state.agents[second].roles.insert("spouse".to_owned());
            state.relationships.push(DslRelationshipState {
                kind: "spouse".to_owned(),
                source_id: state.agents[first].id.clone(),
                target_id: state.agents[second].id.clone(),
                values: BTreeMap::new(),
            });
        }
        let has_children = indices.iter().any(|index| {
            state.agents[*index]
                .value("age")
                .and_then(DslValue::as_f64)
                .unwrap_or(0.0)
                < 18.0
        });
        if has_children {
            for index in adults.iter().take(2) {
                state.agents[*index].roles.insert("parent".to_owned());
                match state.agents[*index]
                    .value("sex")
                    .and_then(DslValue::as_text)
                {
                    Some("male") => {
                        state.agents[*index].roles.insert("father".to_owned());
                    }
                    Some("female") => {
                        state.agents[*index].roles.insert("mother".to_owned());
                    }
                    _ => {}
                }
            }
        }
    }
    assign_pool_leaders(program, agent_paths, seed, state)
}

fn assign_pool_leaders(
    program: &Program,
    agent_paths: &BTreeMap<String, Vec<String>>,
    seed: u64,
    state: &mut DslRunState,
) -> DslResult<()> {
    let roles = program
        .roles
        .iter()
        .map(|role| (role.id.as_str(), role))
        .collect::<BTreeMap<_, _>>();
    let mut occupied = BTreeMap::<String, BTreeSet<String>>::new();
    for composition in &program.compositions {
        for leader in &composition.leaders {
            let Some(role) = roles.get(leader.role.as_str()) else {
                continue;
            };
            let conflict = role
                .conflict_group
                .clone()
                .unwrap_or_else(|| format!("leader_{}", role.id));
            let mut candidates = state
                .agents
                .iter()
                .enumerate()
                .filter(|(_, agent)| {
                    agent_paths
                        .get(&agent.id)
                        .is_some_and(|path| path.contains(&composition.id))
                })
                .map(|(index, _)| index)
                .collect::<Vec<_>>();
            if candidates.is_empty() {
                candidates.extend(0..state.agents.len());
            }
            candidates.retain(|index| {
                !occupied
                    .get(&conflict)
                    .is_some_and(|agents| agents.contains(&state.agents[*index].id))
                    && role.eligibility.as_ref().is_none_or(|eligibility| {
                        let values = state.agents[*index]
                            .traits
                            .iter()
                            .chain(&state.agents[*index].states)
                            .map(|(id, value)| (id.clone(), value.clone()))
                            .collect::<BTreeMap<_, _>>();
                        evaluate(eligibility, &values)
                            .ok()
                            .and_then(|value| value.as_bool())
                            .unwrap_or(false)
                    })
            });
            candidates.sort_by_key(|index| {
                derived_seed(
                    seed,
                    &format!("leader:{}:{}", composition.id, state.agents[*index].id),
                )
            });
            for index in candidates.into_iter().take(leader.count) {
                state.agents[index].roles.insert(leader.role.clone());
                occupied
                    .entry(conflict.clone())
                    .or_default()
                    .insert(state.agents[index].id.clone());
                state.relationships.push(DslRelationshipState {
                    kind: "leader".to_owned(),
                    source_id: state.agents[index].id.clone(),
                    target_id: format!("{}:{}", composition.id, leader.role),
                    values: BTreeMap::new(),
                });
            }
        }
    }
    Ok(())
}

fn apply_policies(
    program: &Program,
    nodes: &[CompositionNode<'_>],
    combined: &mut Program,
    state: &mut DslRunState,
    agent_paths: &BTreeMap<String, Vec<String>>,
) -> DslResult<()> {
    let policies = program
        .policies
        .iter()
        .map(|policy| (policy.id.as_str(), policy))
        .collect::<BTreeMap<_, _>>();
    for node in nodes {
        let values = node
            .definition
            .parameters
            .iter()
            .map(|(id, value)| (id.clone(), DslValue::Number(*value)))
            .collect::<BTreeMap<_, _>>();
        let prefix = node.path.join("__");
        for policy_id in &node.definition.policies {
            for effect in &policies[policy_id.as_str()].effects {
                let value = evaluate(&effect.value, &values)?.as_f64().ok_or_else(|| {
                    DslError::new(
                        "INVALID_POLICY_EFFECT",
                        effect.line,
                        "Policy effect must resolve to a number",
                    )
                })?;
                match &effect.target {
                    AggregateEffectTarget::Decision(action) => {
                        for branch in combined
                            .decisions
                            .iter_mut()
                            .flat_map(|decision| &mut decision.branches)
                            .filter(|branch| scoped_identifier(&branch.action, &prefix, action))
                        {
                            branch.probability = policy_expression(
                                branch.probability.clone(),
                                &effect.operation,
                                value,
                            );
                        }
                        for branch in combined
                            .roles
                            .iter_mut()
                            .flat_map(|role| &mut role.decisions)
                            .flat_map(|decision| &mut decision.branches)
                            .filter(|branch| scoped_identifier(&branch.action, &prefix, action))
                        {
                            branch.probability = policy_expression(
                                branch.probability.clone(),
                                &effect.operation,
                                value,
                            );
                        }
                    }
                    AggregateEffectTarget::Field(field) => {
                        for agent in &mut state.agents {
                            let in_scope = node.path.is_empty()
                                || agent_paths
                                    .get(&agent.id)
                                    .is_some_and(|path| path.starts_with(node.path.as_slice()));
                            if !in_scope {
                                continue;
                            }
                            let current = agent
                                .states
                                .get_mut(field)
                                .or_else(|| agent.traits.get_mut(field));
                            if let Some(current) = current
                                && let Some(number) = current.as_f64()
                            {
                                *current = DslValue::Number(apply_policy_number(
                                    number,
                                    &effect.operation,
                                    value,
                                    effect.line,
                                )?);
                            }
                        }
                    }
                }
            }
        }
    }
    Ok(())
}

fn scoped_identifier(value: &str, prefix: &str, id: &str) -> bool {
    (prefix.is_empty() || value.starts_with(&format!("{prefix}__")))
        && (value == id || value.ends_with(&format!("__{id}")))
}

fn policy_expression(current: Expr, operation: &str, value: f64) -> Expr {
    if operation == "=" {
        Expr::Value(DslValue::Number(value))
    } else {
        Expr::Binary {
            operation: operation.trim_end_matches('=').to_owned(),
            left: Box::new(current),
            right: Box::new(Expr::Value(DslValue::Number(value))),
        }
    }
}

fn apply_policy_number(current: f64, operation: &str, value: f64, line: usize) -> DslResult<f64> {
    match operation {
        "=" => Ok(value),
        "+=" => Ok(current + value),
        "-=" => Ok(current - value),
        "*=" => Ok(current * value),
        _ => Err(DslError::new(
            "INVALID_POLICY_EFFECT",
            line,
            format!("Unsupported policy operation {operation}"),
        )),
    }
}

#[allow(clippy::too_many_arguments)]
fn flatten_composition(
    composition: &CompositionDefinition,
    compositions: &BTreeMap<&str, &CompositionDefinition>,
    archetypes: &BTreeMap<&str, &ArchetypeDefinition>,
    parent_weight: f64,
    path: &[String],
    scopes: &[(String, Vec<String>)],
    root_group: Option<&str>,
    leaves: &mut Vec<CompositionLeaf>,
) {
    let total = composition
        .entries
        .iter()
        .map(|entry| entry.weight.unwrap_or(1.0))
        .sum::<f64>();
    for entry in &composition.entries {
        let weight = parent_weight * entry.weight.unwrap_or(1.0) / total;
        let group = root_group.unwrap_or(&entry.child);
        if archetypes.contains_key(entry.child.as_str()) {
            let namespace = if path.is_empty() {
                entry.child.clone()
            } else {
                namespaced(&path.join("__"), &entry.child)
            };
            leaves.push(CompositionLeaf {
                archetype: entry.child.clone(),
                namespace,
                root_group: group.to_owned(),
                weight,
                scopes: scopes.to_vec(),
                composition_path: path.to_vec(),
            });
        } else if let Some(child) = compositions.get(entry.child.as_str()) {
            let mut child_path = path.to_vec();
            child_path.push(entry.child.clone());
            let child_scope = child_path.join("__");
            let mut child_scopes = scopes.to_vec();
            child_scopes.push((child_scope, child.places.clone()));
            flatten_composition(
                child,
                compositions,
                archetypes,
                weight,
                &child_path,
                &child_scopes,
                Some(group),
                leaves,
            );
        }
    }
}

fn collect_composition_nodes<'a>(
    composition: &'a CompositionDefinition,
    compositions: &BTreeMap<&str, &'a CompositionDefinition>,
    path: &[String],
    nodes: &mut Vec<CompositionNode<'a>>,
) {
    nodes.push(CompositionNode {
        definition: composition,
        path: path.to_vec(),
    });
    for entry in &composition.entries {
        if let Some(child) = compositions.get(entry.child.as_str()) {
            let mut child_path = path.to_vec();
            child_path.push(entry.child.clone());
            collect_composition_nodes(child, compositions, &child_path, nodes);
        }
    }
}

fn leaf_allocations(
    leaves: &[CompositionLeaf],
    archetypes: &BTreeMap<&str, &ArchetypeDefinition>,
    exemplar_households: Option<u32>,
    seed: u64,
    key: &str,
) -> DslResult<BTreeMap<String, usize>> {
    let Some(total_households) = exemplar_households else {
        let total_households = leaves
            .iter()
            .map(|leaf| leaf.archetype.as_str())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .map(|id| archetypes[id].sample_households)
            .sum::<usize>();
        return Ok(deterministic_household_allocations(
            leaves,
            total_households,
        ));
    };
    let _ = (archetypes, seed, key);
    Ok(largest_remainder_households(
        leaves,
        total_households as usize,
    ))
}

fn largest_remainder_households(
    leaves: &[CompositionLeaf],
    total: usize,
) -> BTreeMap<String, usize> {
    let weight_sum = leaves.iter().map(|leaf| leaf.weight).sum::<f64>();
    let mut allocations = leaves
        .iter()
        .map(|leaf| {
            let exact = total as f64 * leaf.weight / weight_sum;
            (
                leaf.namespace.clone(),
                exact.floor() as usize,
                exact.fract(),
            )
        })
        .collect::<Vec<_>>();
    let mut remaining = total.saturating_sub(
        allocations
            .iter()
            .map(|(_, count, _)| *count)
            .sum::<usize>(),
    );
    allocations.sort_by(|left, right| {
        right
            .2
            .total_cmp(&left.2)
            .then_with(|| left.0.cmp(&right.0))
    });
    for (_, count, _) in &mut allocations {
        if remaining == 0 {
            break;
        }
        *count += 1;
        remaining -= 1;
    }
    allocations
        .into_iter()
        .map(|(id, count, _)| (id, count))
        .collect()
}

fn deterministic_household_allocations(
    leaves: &[CompositionLeaf],
    total: usize,
) -> BTreeMap<String, usize> {
    let minimum = usize::from(leaves.len() <= total);
    let mut values = leaves
        .iter()
        .map(|leaf| {
            let exact = total as f64 * leaf.weight;
            (
                leaf.namespace.clone(),
                (exact.floor() as usize).max(minimum),
                exact.fract(),
            )
        })
        .collect::<Vec<_>>();
    let assigned = values.iter().map(|(_, count, _)| *count).sum::<usize>();
    if assigned > total {
        values.sort_by(|left, right| {
            left.2
                .total_cmp(&right.2)
                .then_with(|| right.0.cmp(&left.0))
        });
        let mut extra = assigned - total;
        while extra > 0 {
            let mut changed = false;
            for (_, count, _) in &mut values {
                if extra == 0 {
                    break;
                }
                if *count > minimum {
                    *count -= 1;
                    extra -= 1;
                    changed = true;
                }
            }
            if !changed {
                break;
            }
        }
    } else {
        let mut remaining = total - assigned;
        values.sort_by(|left, right| {
            right
                .2
                .total_cmp(&left.2)
                .then_with(|| left.0.cmp(&right.0))
        });
        while remaining > 0 {
            for (_, count, _) in &mut values {
                if remaining == 0 {
                    break;
                }
                *count += 1;
                remaining -= 1;
            }
        }
    }
    values
        .into_iter()
        .map(|(id, count, _)| (id, count))
        .collect()
}

fn scoped_place_map(
    program: &Program,
    scopes: &[(String, Vec<String>)],
) -> BTreeMap<String, String> {
    program
        .places
        .iter()
        .map(|place| {
            let mapped = scopes
                .iter()
                .find(|(_, places)| places.contains(&place.id))
                .map_or_else(
                    || place.id.clone(),
                    |(scope, _)| {
                        if scope.is_empty() {
                            place.id.clone()
                        } else {
                            namespaced(scope, &place.id)
                        }
                    },
                );
            (place.id.clone(), mapped)
        })
        .collect()
}

fn add_scoped_places(
    program: &Program,
    scopes: &[(String, Vec<String>)],
    place_map: &BTreeMap<String, String>,
    definitions: &mut Vec<PlaceDefinition>,
    states: &mut Vec<DslPlaceState>,
    added: &mut BTreeSet<String>,
) {
    for place in &program.places {
        if place.scope != "program" && !scopes.iter().any(|(_, places)| places.contains(&place.id))
        {
            continue;
        }
        let id = place_map[&place.id].clone();
        if !added.insert(id.clone()) {
            continue;
        }
        let mut definition = place.clone();
        definition.id = id.clone();
        definition.scope = "program".to_owned();
        definitions.push(definition);
        states.push(DslPlaceState {
            id,
            states: place.states.clone(),
        });
    }
}

fn rename_state_identifiers(
    state: &mut DslRunState,
    archetype: &str,
    namespace: &str,
    place_map: &BTreeMap<String, String>,
) {
    let id_map = state
        .agents
        .iter()
        .map(|agent| {
            (
                agent.id.clone(),
                replace_namespace(&agent.id, archetype, namespace),
            )
        })
        .collect::<BTreeMap<_, _>>();
    for agent in &mut state.agents {
        agent.id = id_map[&agent.id].clone();
        agent.household_id = replace_namespace(&agent.household_id, archetype, namespace);
        agent.parent_id = agent.parent_id.as_ref().map(|id| id_map[id].clone());
        if let Some(DslValue::Text(place)) = agent.states.get_mut("location") {
            if let Some(mapped) = place_map.get(place) {
                *place = mapped.clone();
            }
        }
    }
    for relationship in &mut state.relationships {
        relationship.source_id = id_map[&relationship.source_id].clone();
        relationship.target_id = id_map[&relationship.target_id].clone();
    }
}

fn replace_namespace(value: &str, archetype: &str, namespace: &str) -> String {
    if archetype == namespace {
        return value.to_owned();
    }
    value.strip_prefix(archetype).map_or_else(
        || namespaced(namespace, value),
        |suffix| format!("{namespace}{suffix}"),
    )
}

fn namespace_program(
    target: &mut Program,
    source: &Program,
    namespace: &str,
    place_map: &BTreeMap<String, String>,
) {
    target
        .agents
        .extend(source.agents.iter().cloned().map(|mut agent| {
            agent.id = namespaced(namespace, &agent.id);
            agent.parent = agent.parent.map(|parent| namespaced(namespace, &parent));
            agent.routine = namespaced(namespace, &agent.routine);
            agent
        }));
    target
        .decisions
        .extend(source.decisions.iter().cloned().map(|mut decision| {
            decision.id = namespaced(namespace, &decision.id);
            for branch in &mut decision.branches {
                branch.action = namespaced(namespace, &branch.action);
                map_place_expression(&mut branch.probability, place_map);
                if let Some(condition) = &mut branch.condition {
                    map_place_expression(condition, place_map);
                }
            }
            decision
        }));
    for source_role in &source.roles {
        let target_role_index = target
            .roles
            .iter()
            .position(|role| role.id == source_role.id);
        if target_role_index.is_none() {
            target.roles.push(RoleDefinition {
                id: source_role.id.clone(),
                kind: source_role.kind.clone(),
                conflict_group: source_role.conflict_group.clone(),
                eligibility: source_role.eligibility.clone(),
                derivation: source_role.derivation.clone(),
                decisions: Vec::new(),
                line: source_role.line,
            });
        }
        let target_role = target
            .roles
            .iter_mut()
            .find(|role| role.id == source_role.id)
            .unwrap();
        target_role
            .decisions
            .extend(source_role.decisions.iter().cloned().map(|mut decision| {
                decision.id = namespaced(namespace, &decision.id);
                for branch in &mut decision.branches {
                    branch.action = namespaced(namespace, &branch.action);
                    map_place_expression(&mut branch.probability, place_map);
                    if let Some(condition) = &mut branch.condition {
                        map_place_expression(condition, place_map);
                    }
                }
                decision
            }));
    }
    target
        .actions
        .extend(source.actions.iter().cloned().map(|mut action| {
            action.id = namespaced(namespace, &action.id);
            if let Some(target) = &mut action.target {
                match target {
                    TargetSelector::Random { place, .. }
                    | TargetSelector::Friend { place }
                    | TargetSelector::Enemy { place }
                    | TargetSelector::Strongest { place, .. } => {
                        *place = place_map
                            .get(place)
                            .cloned()
                            .unwrap_or_else(|| place.clone());
                    }
                    TargetSelector::CurrentRandom { .. } => {}
                }
            }
            for outcome in &mut action.outcomes {
                outcome.next_decision = outcome
                    .next_decision
                    .take()
                    .map(|decision| namespaced(namespace, &decision));
                outcome.target_next_decision = outcome
                    .target_next_decision
                    .take()
                    .map(|decision| namespaced(namespace, &decision));
                for effect in &mut outcome.effects {
                    match &mut effect.scope {
                        EffectScope::AllAt { place, .. } | EffectScope::Place { place } => {
                            *place = place_map
                                .get(place)
                                .cloned()
                                .unwrap_or_else(|| place.clone());
                        }
                        EffectScope::CurrentPlace => {}
                        _ => {}
                    }
                    if effect.field == "location" {
                        map_place_expression(&mut effect.value, place_map);
                    }
                }
            }
            action
        }));
}

fn map_place_expression(expression: &mut Expr, place_map: &BTreeMap<String, String>) {
    match expression {
        Expr::Variable(value) if place_map.contains_key(value) => {
            *expression = Expr::Value(DslValue::Text(place_map[value].clone()));
        }
        Expr::Unary { value, .. } => map_place_expression(value, place_map),
        Expr::Binary { left, right, .. } => {
            map_place_expression(left, place_map);
            map_place_expression(right, place_map);
        }
        Expr::Conditional {
            condition,
            when_true,
            when_false,
        } => {
            map_place_expression(condition, place_map);
            map_place_expression(when_true, place_map);
            map_place_expression(when_false, place_map);
        }
        Expr::Call { arguments, .. } => {
            for argument in arguments {
                map_place_expression(argument, place_map);
            }
        }
        _ => {}
    }
}

fn namespaced(namespace: &str, id: &str) -> String {
    format!("{namespace}__{id}")
}

pub(super) fn derived_seed(seed: u64, value: &str) -> u64 {
    value
        .as_bytes()
        .iter()
        .fold(seed ^ 0xcbf29ce484222325, |hash, byte| {
            (hash ^ u64::from(*byte)).wrapping_mul(0x100000001b3)
        })
}
