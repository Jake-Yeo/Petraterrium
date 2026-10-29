use super::composition_allocations::validate_authoritative_allocations;
use super::expression::references;
use super::model::*;
use std::collections::{BTreeMap, BTreeSet};

pub(super) fn apply_composition_archetypes(program: &mut Program) -> DslResult<()> {
    let archetypes = program
        .composition_archetypes
        .iter()
        .map(|item| (item.id.as_str(), item))
        .collect::<BTreeMap<_, _>>();
    for composition in &mut program.compositions {
        let Some(template_id) = &composition.template else {
            continue;
        };
        let template = archetypes.get(template_id.as_str()).ok_or_else(|| {
            DslError::new(
                "UNKNOWN_COMPOSITION_ARCHETYPE",
                composition.line,
                format!("Unknown composition archetype {template_id}"),
            )
        })?;
        if composition.level != template.level {
            return Err(DslError::new(
                "COMPOSITION_ARCHETYPE_LEVEL_MISMATCH",
                composition.line,
                format!(
                    "Composition {} level {} does not match template level {}",
                    composition.id, composition.level, template.level
                ),
            ));
        }
        let mut parameters = template.parameters.clone();
        parameters.extend(composition.parameters.clone());
        composition.parameters = parameters;
        if composition.outputs.is_empty() {
            composition.outputs = template.outputs.clone();
        }
    }
    Ok(())
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
    let policies = program
        .policies
        .iter()
        .map(|policy| (policy.id.as_str(), policy))
        .collect::<BTreeMap<_, _>>();
    let known_roles = program
        .roles
        .iter()
        .map(|role| role.id.as_str())
        .collect::<BTreeSet<_>>();
    let mut ids = BTreeSet::new();
    let mut archetype_ids = BTreeSet::new();
    for archetype in &program.composition_archetypes {
        if !archetype_ids.insert(archetype.id.as_str()) {
            return Err(DslError::new(
                "DUPLICATE_COMPOSITION_ARCHETYPE",
                archetype.line,
                format!("Duplicate composition archetype {}", archetype.id),
            ));
        }
        if archetype.outputs.is_empty() {
            return Err(DslError::new(
                "EMPTY_COMPOSITION_ARCHETYPE",
                archetype.line,
                "Composition archetype needs outputs",
            ));
        }
    }
    for composition in &program.compositions {
        if !ids.insert(composition.id.as_str()) {
            return Err(DslError::new(
                "DUPLICATE_COMPOSITION",
                composition.line,
                format!("Duplicate composition {}", composition.id),
            ));
        }
        validate_graph_metadata(composition)?;
        if composition.entries.is_empty() || composition.outputs.is_empty() {
            return Err(DslError::new(
                "EMPTY_COMPOSITION",
                composition.line,
                "Composition needs children and outputs",
            ));
        }
        let child_ids = composition
            .entries
            .iter()
            .map(|entry| entry.child.as_str())
            .collect::<BTreeSet<_>>();
        if composition.represented_population == Some(0) {
            return Err(DslError::new(
                "INVALID_REPRESENTED_POPULATION",
                composition.line,
                "Represented population must be positive",
            ));
        }
        if composition.level == "neighbourhood"
            && !composition
                .exemplar_households
                .is_some_and(|households| (50..=100).contains(&households))
        {
            return Err(DslError::new(
                "INVALID_EXEMPLAR_HOUSEHOLDS",
                composition.line,
                "Neighbourhood compositions need 50 to 100 households_per_exemplar",
            ));
        }
        if !composition.heterogeneity.is_finite()
            || !(0.0..=1.0).contains(&composition.heterogeneity)
            || composition
                .stratifiers
                .values()
                .any(|value| !value.is_finite())
        {
            return Err(DslError::new(
                "INVALID_STRATIFICATION",
                composition.line,
                "Heterogeneity must be 0..1 and stratifiers must be finite",
            ));
        }
        if !matches!(
            composition.distribution_status.as_str(),
            "measured" | "inherited" | "fallback" | "estimated"
        ) {
            return Err(DslError::new(
                "INVALID_DISTRIBUTION_STATUS",
                composition.line,
                "distribution_status must be measured, inherited, estimated, or fallback",
            ));
        }
        if let Some(role) = composition
            .role_targets
            .keys()
            .find(|role| !known_roles.contains(role.as_str()))
        {
            return Err(DslError::new(
                "UNKNOWN_ROLE_TARGET",
                composition.line,
                format!("Unknown role target {role}"),
            ));
        }
        let unweighted = composition
            .entries
            .iter()
            .filter(|entry| entry.weight.is_none())
            .count();
        if unweighted > 0
            && (unweighted != composition.entries.len() || composition.agent_pool.is_none())
        {
            return Err(DslError::new(
                "INVALID_UNWEIGHTED_CHILDREN",
                composition.line,
                "Only an agent-pool root may omit every child weight",
            ));
        }
        if let Some(pool) = &composition.agent_pool
            && !composition.entries.iter().any(|entry| entry.child == *pool)
        {
            return Err(DslError::new(
                "UNKNOWN_AGENT_POOL",
                composition.line,
                "agent_pool must name a direct child",
            ));
        }
        if let Some(template_id) = &composition.template {
            let template = program
                .composition_archetypes
                .iter()
                .find(|item| item.id == *template_id)
                .ok_or_else(|| {
                    DslError::new(
                        "UNKNOWN_COMPOSITION_ARCHETYPE",
                        composition.line,
                        format!("Unknown composition archetype {template_id}"),
                    )
                })?;
            for entry in &composition.entries {
                if let Some(child) = compositions.get(entry.child.as_str())
                    && child.level != template.child_level
                {
                    return Err(DslError::new(
                        "COMPOSITION_ARCHETYPE_CHILD_LEVEL_MISMATCH",
                        entry.line,
                        format!(
                            "Template {} expects {} children, got {}",
                            template.id, template.child_level, child.level
                        ),
                    ));
                }
            }
        }
        if child_ids.len() != composition.entries.len() {
            return Err(DslError::new(
                "DUPLICATE_COMPOSITION_CHILD",
                composition.line,
                "Composition children must be unique",
            ));
        }
        let mut policy_ids = BTreeSet::new();
        for policy_id in &composition.policies {
            if !policy_ids.insert(policy_id.as_str()) {
                return Err(DslError::new(
                    "DUPLICATE_COMPOSITION_POLICY",
                    composition.line,
                    format!("Composition {} repeats policy {policy_id}", composition.id),
                ));
            }
            let policy = policies.get(policy_id.as_str()).ok_or_else(|| {
                DslError::new(
                    "UNKNOWN_COMPOSITION_POLICY",
                    composition.line,
                    format!(
                        "Composition {} uses unknown policy {policy_id}",
                        composition.id
                    ),
                )
            })?;
            let unknown = policy
                .effects
                .iter()
                .flat_map(|effect| references(&effect.value))
                .filter(|reference| !composition.parameters.contains_key(reference))
                .collect::<BTreeSet<_>>();
            if !unknown.is_empty() {
                return Err(DslError::new(
                    "UNKNOWN_COMPOSITION_POLICY_VALUE",
                    policy.line,
                    format!(
                        "Policy references unknown values: {}",
                        unknown.into_iter().collect::<Vec<_>>().join(", ")
                    ),
                ));
            }
        }
        for entry in &composition.entries {
            if !archetypes.contains(entry.child.as_str())
                && !compositions.contains_key(entry.child.as_str())
            {
                return Err(DslError::new(
                    "UNKNOWN_COMPOSITION_CHILD",
                    entry.line,
                    format!("Unknown composition child {}", entry.child),
                ));
            }
            if entry
                .weight
                .is_some_and(|weight| !weight.is_finite() || weight <= 0.0)
            {
                return Err(DslError::new(
                    "INVALID_COMPOSITION_CHILD",
                    entry.line,
                    "Composition weight must be positive",
                ));
            }
            if let Some(child) = compositions.get(entry.child.as_str())
                && let Some(sync_up) = composition.sync_up_minutes
                && sync_up % child.clock_minutes != 0
            {
                return Err(DslError::new(
                    "CLOCK_SYNC_MISMATCH",
                    entry.line,
                    format!(
                        "Child clock {} minutes does not divide parent sync {} minutes",
                        child.clock_minutes, sync_up
                    ),
                ));
            }
        }
        for place in &composition.places {
            if !places.contains(place.as_str()) {
                return Err(DslError::new(
                    "UNKNOWN_COMPOSITION_PLACE",
                    composition.line,
                    format!("Unknown composition place {place}"),
                ));
            }
        }
        validate_adjacency(composition, &child_ids)?;
        for output in &composition.outputs {
            match &output.metric {
                ReportMetric::Count => {}
                ReportMetric::RepresentedCount
                    if composition.represented_population.is_some()
                        || composition.slice.is_some() => {}
                ReportMetric::RepresentedTotal
                    if composition.authoritative_total.is_some() || composition.slice.is_some() => {
                }
                ReportMetric::Formula { expression }
                    if valid_formula_references(program, composition, output, expression) => {}
                ReportMetric::Mean { field } | ReportMetric::Sum { field }
                    if base_fields.contains(field) => {}
                ReportMetric::StandardDeviation { field } if base_fields.contains(field) => {}
                ReportMetric::KidsPerFamily => {}
                ReportMetric::ActionCount { aggregate, window }
                | ReportMetric::ActionRate { aggregate, window }
                    if aggregates.contains(aggregate.as_str())
                        && matches!(window.as_str(), "tick" | "day" | "run") => {}
                ReportMetric::PlaceState { place, field }
                    if program
                        .places
                        .iter()
                        .any(|item| item.id == *place && item.states.contains_key(field)) => {}
                _ => {
                    return Err(DslError::new(
                        "INVALID_COMPOSITION_OUTPUT",
                        output.line,
                        format!("Invalid composition output {}", output.id),
                    ));
                }
            }
        }
    }
    validate_composition_cycles(&compositions)?;
    for composition in &program.compositions {
        validate_composition_leaders(program, composition, &compositions)?;
    }
    let default_runs = program
        .compositions
        .iter()
        .filter(|composition| composition.default_run)
        .collect::<Vec<_>>();
    if default_runs.len() > 1 {
        return Err(DslError::new(
            "MULTIPLE_DEFAULT_RUNS",
            default_runs[1].line,
            "Only one composition may declare default_run = true",
        ));
    }
    validate_authoritative_allocations(program)?;
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
                    "UNKNOWN_COMPOSITION",
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
            if entry.represented_population == Some(0) {
                return Err(DslError::new(
                    "INVALID_REPRESENTED_POPULATION",
                    entry.line,
                    "Represented population must be positive",
                ));
            }
        }
    }
    Ok(())
}

fn validate_graph_metadata(composition: &CompositionDefinition) -> DslResult<()> {
    if composition.graph_group.as_deref() != Some("root")
        && composition.graph_group.is_some()
        && composition.slice.is_none()
    {
        return Err(DslError::new(
            "MISSING_COMPOSITION_SLICE",
            composition.line,
            "A graph-grouped composition needs slice = \"name\"",
        ));
    }
    if let Some(group) = &composition.graph_group
        && !matches!(
            group.as_str(),
            "main" | "root" | "coupled" | "lab" | "allocation"
        )
    {
        return Err(DslError::new(
            "INVALID_GRAPH_GROUP",
            composition.line,
            "graph_group must be main, root, coupled, lab, or allocation",
        ));
    }
    if composition.slice.is_some() && !composition.entries.is_empty() {
        let weights = composition
            .entries
            .iter()
            .filter_map(|entry| entry.weight)
            .collect::<Vec<_>>();
        let sum = weights.iter().sum::<f64>();
        if !weights.is_empty() && (sum - 1.0).abs() > 1e-9 {
            return Err(DslError::new(
                "INVALID_DISTRIBUTION_SUM",
                composition.entries[0].line,
                format!("Child probabilities sum to {sum}, expected 1"),
            ));
        }
    }
    Ok(())
}

fn validate_composition_leaders(
    program: &Program,
    composition: &CompositionDefinition,
    compositions: &BTreeMap<&str, &CompositionDefinition>,
) -> DslResult<()> {
    let known_roles = program
        .roles
        .iter()
        .map(|role| role.id.as_str())
        .collect::<BTreeSet<_>>();
    let mut declared = BTreeSet::new();
    for leader in &composition.leaders {
        if leader.count == 0 {
            return Err(DslError::new(
                "INVALID_COMPOSITION_LEADER",
                leader.line,
                "Leader count must be positive",
            ));
        }
        if !declared.insert(leader.role.as_str()) {
            return Err(DslError::new(
                "DUPLICATE_COMPOSITION_LEADER",
                leader.line,
                format!(
                    "Composition {} repeats leader role {}",
                    composition.id, leader.role
                ),
            ));
        }
        if !known_roles.contains(leader.role.as_str()) {
            return Err(DslError::new(
                "UNKNOWN_COMPOSITION_LEADER_ROLE",
                leader.line,
                format!("Unknown leader role {}", leader.role),
            ));
        }
        if program
            .roles
            .iter()
            .find(|role| role.id == leader.role)
            .is_some_and(|role| role.kind == "leader")
        {
            continue;
        }
        let actual = if let Some(archetype_id) = &leader.archetype {
            let archetype = program
                .archetypes
                .iter()
                .find(|archetype| archetype.id == *archetype_id)
                .ok_or_else(|| {
                    DslError::new(
                        "UNKNOWN_LEADER_ARCHETYPE",
                        leader.line,
                        format!("Unknown leader archetype {archetype_id}"),
                    )
                })?;
            if let Some(source_id) = &leader.source_composition {
                let source = compositions.get(source_id.as_str()).ok_or_else(|| {
                    DslError::new(
                        "UNKNOWN_LEADER_SOURCE",
                        leader.line,
                        format!("Unknown leader source composition {source_id}"),
                    )
                })?;
                if !composition_contains_archetype(source, archetype_id, compositions) {
                    return Err(DslError::new(
                        "LEADER_SOURCE_MISMATCH",
                        leader.line,
                        format!("Composition {source_id} does not contain {archetype_id}"),
                    ));
                }
            }
            archetype_role_count(program, archetype, &leader.role)
        } else {
            composition_role_count(program, composition, &leader.role, compositions)
        };
        if actual != leader.count {
            return Err(DslError::new(
                "LEADER_COUNT_MISMATCH",
                leader.line,
                format!(
                    "Composition {} declares {} {} leader(s), but its subtree defines {}",
                    composition.id, leader.count, leader.role, actual
                ),
            ));
        }
    }
    Ok(())
}

fn composition_contains_archetype(
    composition: &CompositionDefinition,
    archetype_id: &str,
    compositions: &BTreeMap<&str, &CompositionDefinition>,
) -> bool {
    composition.entries.iter().any(|entry| {
        entry.child == archetype_id
            || compositions.get(entry.child.as_str()).is_some_and(|child| {
                composition_contains_archetype(child, archetype_id, compositions)
            })
    })
}

fn composition_role_count(
    program: &Program,
    composition: &CompositionDefinition,
    role: &str,
    compositions: &BTreeMap<&str, &CompositionDefinition>,
) -> usize {
    composition
        .entries
        .iter()
        .map(|entry| {
            if let Some(child) = compositions.get(entry.child.as_str()) {
                composition_role_count(program, child, role, compositions)
            } else {
                program
                    .archetypes
                    .iter()
                    .find(|archetype| archetype.id == entry.child)
                    .map_or(0, |archetype| {
                        archetype_role_count(program, archetype, role)
                    })
            }
        })
        .sum()
}

fn archetype_role_count(program: &Program, archetype: &ArchetypeDefinition, role: &str) -> usize {
    let total = archetype
        .composition
        .iter()
        .map(|group| {
            let probability = if archetype.roles.contains(role) {
                1.0
            } else {
                group
                    .mix
                    .iter()
                    .filter(|entry| agent_definition_has_role(program, &entry.agent_type, role))
                    .map(|entry| entry.probability)
                    .sum::<f64>()
            };
            archetype.sample_households as f64 * group.count as f64 * probability
        })
        .sum::<f64>();
    total.round() as usize
}

fn agent_definition_has_role(program: &Program, agent_id: &str, role: &str) -> bool {
    let Some(agent) = program.agents.iter().find(|agent| agent.id == agent_id) else {
        return false;
    };
    agent.roles.contains(role)
        || agent
            .parent
            .as_ref()
            .is_some_and(|parent| agent_definition_has_role(program, parent, role))
}

fn valid_formula_references(
    program: &Program,
    composition: &CompositionDefinition,
    output: &ArchetypeOutputDefinition,
    expression: &Expr,
) -> bool {
    let prior_outputs = composition
        .outputs
        .iter()
        .take_while(|candidate| candidate.id != output.id)
        .map(|candidate| candidate.id.clone());
    let mut allowed = composition
        .parameters
        .keys()
        .cloned()
        .chain(prior_outputs)
        .collect::<BTreeSet<_>>();
    if let Some(function) = program
        .aggregate_functions
        .iter()
        .find(|function| function.id == composition.id)
    {
        allowed.extend(function.inputs.iter().map(|input| input.id.clone()));
    }
    for entry in &composition.entries {
        let outputs = program
            .compositions
            .iter()
            .find(|child| child.id == entry.child)
            .map(|child| child.outputs.as_slice())
            .or_else(|| {
                program
                    .archetypes
                    .iter()
                    .find(|child| child.id == entry.child)
                    .map(|child| child.outputs.as_slice())
            })
            .unwrap_or_default();
        for child_output in outputs {
            allowed.insert(format!("{}.{}", entry.child, child_output.id));
            allowed.insert(format!("sum.{}", child_output.id));
            allowed.insert(format!("weighted.{}", child_output.id));
        }
    }
    references(expression)
        .into_iter()
        .all(|reference| allowed.contains(&reference))
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
