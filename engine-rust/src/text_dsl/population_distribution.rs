use super::model::*;
use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;
use rand_distr::{Binomial, Distribution};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct PopulationAllocation {
    pub path: String,
    pub parent_path: Option<String>,
    pub node_id: String,
    pub node_kind: String,
    pub vertical_slice: String,
    pub graph_group: String,
    pub probability: f64,
    pub expected_represented: f64,
    pub actual_represented: u64,
    pub expected_simulated: f64,
    pub actual_simulated: u64,
    pub seed: u64,
}

pub fn sample_multinomial_counts(
    total: u64,
    probabilities: &[f64],
    seed: u64,
    key: &str,
) -> DslResult<Vec<u64>> {
    if probabilities.is_empty() {
        return Ok(Vec::new());
    }
    let sum = probabilities.iter().sum::<f64>();
    if probabilities
        .iter()
        .any(|value| !value.is_finite() || *value < 0.0)
        || (sum - 1.0).abs() > 1e-9
    {
        return Err(DslError::new(
            "INVALID_DISTRIBUTION_SUM",
            1,
            format!("Distribution probabilities sum to {sum}, expected 1"),
        ));
    }
    let mut rng = ChaCha8Rng::seed_from_u64(derived_seed(seed, key));
    let mut remaining_total = total;
    let mut remaining_probability = 1.0;
    let mut counts = Vec::with_capacity(probabilities.len());
    for probability in probabilities.iter().take(probabilities.len() - 1) {
        let conditional = if remaining_probability <= f64::EPSILON {
            0.0
        } else {
            (probability / remaining_probability).clamp(0.0, 1.0)
        };
        let count = if remaining_total == 0 {
            0
        } else {
            Binomial::new(remaining_total, conditional)
                .map_err(|error| DslError::new("INVALID_DISTRIBUTION", 1, error.to_string()))?
                .sample(&mut rng)
        };
        counts.push(count);
        remaining_total -= count;
        remaining_probability = (remaining_probability - probability).max(0.0);
    }
    counts.push(remaining_total);
    Ok(counts)
}

pub fn build_population_plan(
    program: &Program,
    composition_id: &str,
    seed: u64,
    sample_budget: Option<u64>,
) -> DslResult<Vec<PopulationAllocation>> {
    let compositions = program
        .compositions
        .iter()
        .map(|composition| (composition.id.as_str(), composition))
        .collect::<BTreeMap<_, _>>();
    let archetypes = program
        .archetypes
        .iter()
        .map(|archetype| (archetype.id.as_str(), archetype))
        .collect::<BTreeMap<_, _>>();
    let root = compositions.get(composition_id).ok_or_else(|| {
        DslError::new(
            "UNKNOWN_COMPOSITION",
            1,
            format!("Unknown composition {composition_id}"),
        )
    })?;
    let default_budget = default_sample_budget(root, &compositions, &archetypes);
    let simulated = sample_budget.unwrap_or(default_budget);
    let represented = root.represented_population.unwrap_or(0);
    let mut plan = Vec::new();
    allocate_composition(
        root,
        &compositions,
        &archetypes,
        root.id.clone(),
        None,
        1.0,
        represented as f64,
        represented,
        simulated as f64,
        simulated,
        seed,
        &mut plan,
    )?;
    Ok(plan)
}

pub fn apply_actual_simulated_counts(plan: &mut [PopulationAllocation], state: &DslRunState) {
    for allocation in plan {
        let components = allocation.path.split('>').collect::<Vec<_>>();
        allocation.actual_simulated = if components.len() == 1 {
            state.agents.len() as u64
        } else {
            let prefix = components[1..].join("__");
            state
                .agents
                .iter()
                .filter(|agent| agent.id == prefix || agent.id.starts_with(&format!("{prefix}__")))
                .count() as u64
        };
    }
}

#[allow(clippy::too_many_arguments)]
fn allocate_composition(
    composition: &CompositionDefinition,
    compositions: &BTreeMap<&str, &CompositionDefinition>,
    archetypes: &BTreeMap<&str, &ArchetypeDefinition>,
    path: String,
    parent_path: Option<String>,
    probability: f64,
    expected_represented: f64,
    actual_represented: u64,
    expected_simulated: f64,
    actual_simulated: u64,
    seed: u64,
    plan: &mut Vec<PopulationAllocation>,
) -> DslResult<()> {
    plan.push(PopulationAllocation {
        path: path.clone(),
        parent_path,
        node_id: composition.id.clone(),
        node_kind: "composition".to_owned(),
        vertical_slice: composition
            .slice
            .clone()
            .unwrap_or_else(|| "Unassigned".to_owned()),
        graph_group: composition
            .graph_group
            .clone()
            .unwrap_or_else(|| "lab".to_owned()),
        probability,
        expected_represented,
        actual_represented,
        expected_simulated,
        actual_simulated,
        seed,
    });
    if composition.entries.is_empty() {
        return Ok(());
    }
    let probabilities = composition
        .entries
        .iter()
        .map(|entry| entry.weight)
        .collect::<Vec<_>>();
    let represented_counts = sample_multinomial_counts(
        actual_represented,
        &probabilities,
        seed,
        &format!("{path}:represented"),
    )?;
    let simulated_counts = sample_multinomial_counts(
        actual_simulated,
        &probabilities,
        seed,
        &format!("{path}:simulated"),
    )?;
    for (index, entry) in composition.entries.iter().enumerate() {
        let child_path = format!("{path}>{}", entry.child);
        let child_expected_represented = expected_represented * entry.weight;
        let child_expected_simulated = expected_simulated * entry.weight;
        if let Some(child) = compositions.get(entry.child.as_str()) {
            let represented = if actual_represented == 0 {
                child.represented_population.unwrap_or(0)
            } else {
                represented_counts[index]
            };
            allocate_composition(
                child,
                compositions,
                archetypes,
                child_path,
                Some(path.clone()),
                entry.weight,
                if actual_represented == 0 {
                    represented as f64
                } else {
                    child_expected_represented
                },
                represented,
                child_expected_simulated,
                simulated_counts[index],
                seed,
                plan,
            )?;
        } else if let Some(archetype) = archetypes.get(entry.child.as_str()) {
            allocate_archetype(
                archetype,
                child_path,
                path.clone(),
                composition,
                entry.weight,
                child_expected_represented,
                represented_counts[index],
                child_expected_simulated,
                simulated_counts[index],
                seed,
                plan,
            )?;
        }
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
fn allocate_archetype(
    archetype: &ArchetypeDefinition,
    path: String,
    parent_path: String,
    parent: &CompositionDefinition,
    probability: f64,
    expected_represented: f64,
    actual_represented: u64,
    expected_simulated: f64,
    actual_simulated: u64,
    seed: u64,
    plan: &mut Vec<PopulationAllocation>,
) -> DslResult<()> {
    plan.push(PopulationAllocation {
        path,
        parent_path: Some(parent_path),
        node_id: archetype.id.clone(),
        node_kind: "archetype".to_owned(),
        vertical_slice: parent
            .slice
            .clone()
            .unwrap_or_else(|| "Unassigned".to_owned()),
        graph_group: parent
            .graph_group
            .clone()
            .unwrap_or_else(|| "lab".to_owned()),
        probability,
        expected_represented,
        actual_represented,
        expected_simulated,
        actual_simulated,
        seed,
    });
    Ok(())
}

fn default_sample_budget(
    root: &CompositionDefinition,
    compositions: &BTreeMap<&str, &CompositionDefinition>,
    archetypes: &BTreeMap<&str, &ArchetypeDefinition>,
) -> u64 {
    if let Some(budget) = root.sample_budget {
        return budget;
    }
    let mut ids = BTreeSet::new();
    collect_archetypes(root, compositions, archetypes, &mut ids);
    ids.into_iter()
        .map(|id| {
            let archetype = archetypes[id];
            let per_household = archetype
                .composition
                .iter()
                .map(|group| group.count as u64)
                .sum::<u64>();
            archetype.sample_households as u64 * per_household
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

fn derived_seed(seed: u64, value: &str) -> u64 {
    value
        .as_bytes()
        .iter()
        .fold(seed ^ 0xcbf29ce484222325, |hash, byte| {
            (hash ^ u64::from(*byte)).wrapping_mul(0x100000001b3)
        })
}
