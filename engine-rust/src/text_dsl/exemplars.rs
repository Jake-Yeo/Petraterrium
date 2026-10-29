use super::compositions::run_composition;
use super::expression::evaluate;
use super::model::*;
use super::runtime::run_program;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::time::Instant;

const DEFAULT_EXEMPLAR_HOUSEHOLDS: u32 = 75;
const MAX_EXEMPLARS_PER_CITY: usize = 50;
const EXEMPLAR_CACHE_SCHEMA_VERSION: u32 = 2;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct ExemplarConvergence {
    pub mean_change: f64,
    pub distribution_distance: f64,
    pub tail_rate_change_points: f64,
    pub converged: bool,
    pub cap_hit: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct NeighbourhoodExemplarPlan {
    pub id: String,
    pub city_id: String,
    pub stratum: String,
    pub stratum_source: String,
    pub households: u32,
    pub people: usize,
    pub household_allocations: BTreeMap<String, u32>,
    pub represented_people: u64,
    pub instances_represented: f64,
    pub city_population_share: f64,
    pub seed: u64,
    pub distribution_status: String,
    pub provenance: String,
    pub residence_path: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct CityExemplarPlan {
    pub city_id: String,
    pub represented_people: u64,
    pub represented_households: u64,
    pub distribution_status: String,
    pub provenance: String,
    pub residence_path: Vec<String>,
    pub strata: Vec<String>,
    pub exemplars: Vec<NeighbourhoodExemplarPlan>,
    pub convergence: ExemplarConvergence,
    #[serde(default)]
    pub mixture_metrics: BTreeMap<String, ExemplarMetricDistribution>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct ExemplarSystemPlan {
    pub total_represented_pool: u64,
    pub total_represented_households: u64,
    pub total_real_neighbourhood_instances: f64,
    pub total_exemplars: usize,
    pub cities: Vec<CityExemplarPlan>,
    pub hierarchy_counts: BTreeMap<String, u64>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct ExemplarCacheStats {
    pub cache_hit: bool,
    pub mass_agent_ticks: u64,
    pub relearned_exemplars: Vec<String>,
    pub reused_exemplars: Vec<String>,
    pub invalidations: BTreeMap<String, String>,
    pub parent_cache_versions: BTreeMap<String, BTreeMap<String, u64>>,
    pub feedback_iterations: u32,
    pub feedback_final_change: f64,
    pub feedback_inputs: BTreeMap<String, BTreeMap<String, f64>>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct ExemplarSystemRun {
    pub result: DslRunResult,
    pub plan: ExemplarSystemPlan,
    pub cache: BTreeMap<String, ExemplarCacheEntry>,
    pub cache_stats: ExemplarCacheStats,
    pub leader_assignments: BTreeMap<String, String>,
    pub unassigned_required_roles: u64,
}

pub fn plan_exemplars(
    program: &Program,
    total_represented_pool: u64,
    seed: u64,
) -> DslResult<ExemplarSystemPlan> {
    if total_represented_pool == 0 {
        return Err(DslError::new(
            "INVALID_TOTAL_REPRESENTED_POOL",
            1,
            "Total represented pool must be positive",
        ));
    }
    let compositions = program
        .compositions
        .iter()
        .map(|composition| (composition.id.as_str(), composition))
        .collect::<BTreeMap<_, _>>();
    let root_id = program
        .compositions
        .iter()
        .find(|composition| composition.default_run)
        .and_then(|composition| composition.agent_pool.as_deref())
        .ok_or_else(|| {
            DslError::new(
                "MISSING_AGENT_POOL",
                1,
                "Default run needs an agent_pool hierarchy root",
            )
        })?;
    let root = compositions[root_id];
    let mut hierarchy_counts = BTreeMap::new();
    let mut city_counts = BTreeMap::new();
    let mut city_paths = BTreeMap::new();
    allocate_hierarchy(
        root,
        total_represented_pool,
        &compositions,
        &[root.id.clone()],
        &mut hierarchy_counts,
        &mut city_counts,
        &mut city_paths,
    )?;
    let archetypes = program
        .archetypes
        .iter()
        .map(|archetype| (archetype.id.as_str(), archetype))
        .collect::<BTreeMap<_, _>>();
    let mut cities = Vec::new();
    for (city_id, represented_people) in city_counts {
        let city = compositions[city_id.as_str()];
        let residence_path = city_paths[&city_id].clone();
        let weighted_strata = city
            .entries
            .iter()
            .filter_map(|entry| {
                compositions
                    .get(entry.child.as_str())
                    .map(|stratum| (entry, *stratum))
            })
            .collect::<Vec<_>>();
        if weighted_strata.is_empty() {
            return Err(DslError::new(
                "CITY_WITHOUT_STRATA",
                city.line,
                format!("City {} needs at least one neighbourhood stratum", city.id),
            ));
        }
        if weighted_strata.len() > MAX_EXEMPLARS_PER_CITY {
            return Err(DslError::new(
                "TOO_MANY_CITY_STRATA",
                city.line,
                format!(
                    "City {} has {} strata but the exemplar cap is {}",
                    city.id,
                    weighted_strata.len(),
                    MAX_EXEMPLARS_PER_CITY
                ),
            ));
        }
        let stratum_weights = weighted_strata
            .iter()
            .map(|(entry, _)| entry.weight.unwrap_or(0.0))
            .collect::<Vec<_>>();
        let represented_by_stratum = largest_remainder_counts(represented_people, &stratum_weights);
        let city_share = represented_people as f64 / total_represented_pool as f64;
        let exemplar_counts = cap_exemplar_counts(
            weighted_strata
                .iter()
                .map(|(entry, stratum)| {
                    let extra_for_heterogeneity =
                        (stratum.heterogeneity.clamp(0.0, 1.0) * 4.0).ceil();
                    let extra_for_population = if city_share > 0.02 {
                        (city_share * entry.weight.unwrap_or(0.0) * 12.0).ceil()
                    } else {
                        0.0
                    };
                    1 + extra_for_heterogeneity as usize + extra_for_population as usize
                })
                .collect(),
        );
        let mut exemplars = Vec::new();
        for (stratum_index, ((_entry, stratum), stratum_people)) in weighted_strata
            .iter()
            .zip(represented_by_stratum)
            .enumerate()
        {
            let households = stratum
                .exemplar_households
                .unwrap_or(DEFAULT_EXEMPLAR_HOUSEHOLDS);
            if !(50..=100).contains(&households) {
                return Err(DslError::new(
                    "INVALID_EXEMPLAR_HOUSEHOLDS",
                    stratum.line,
                    "Detailed neighbourhood exemplars require 50 to 100 households",
                ));
            }
            let exemplar_count = exemplar_counts[stratum_index];
            let represented_by_exemplar =
                largest_remainder_counts(stratum_people, &vec![1.0; exemplar_count]);
            let household_allocations = allocate_households(stratum, households)?;
            let people = household_allocations
                .iter()
                .map(|(archetype_id, count)| {
                    let people_per_household = archetypes
                        .get(archetype_id.as_str())
                        .map(|archetype| {
                            archetype
                                .composition
                                .iter()
                                .map(|group| group.count)
                                .sum::<usize>()
                        })
                        .unwrap_or(0);
                    people_per_household * *count as usize
                })
                .sum::<usize>();
            for (index, represented) in represented_by_exemplar.into_iter().enumerate() {
                let id = format!(
                    "{}__{}__{:02}",
                    city.id,
                    stratum.stratum.as_deref().unwrap_or(&stratum.id),
                    index + 1
                );
                exemplars.push(NeighbourhoodExemplarPlan {
                    id: id.clone(),
                    city_id: city.id.clone(),
                    stratum: stratum
                        .stratum
                        .clone()
                        .unwrap_or_else(|| stratum.id.clone()),
                    stratum_source: stratum.id.clone(),
                    households,
                    people,
                    household_allocations: household_allocations.clone(),
                    represented_people: represented,
                    instances_represented: represented as f64 / people.max(1) as f64,
                    city_population_share: if represented_people == 0 {
                        0.0
                    } else {
                        represented as f64 / represented_people as f64
                    },
                    seed: derived_seed(seed, &id),
                    distribution_status: if city.distribution_status == "measured" {
                        stratum.distribution_status.clone()
                    } else {
                        city.distribution_status.clone()
                    },
                    provenance: format!(
                        "{}; {}",
                        city.provenance
                            .as_deref()
                            .unwrap_or("No city provenance declared"),
                        stratum
                            .provenance
                            .as_deref()
                            .unwrap_or("No stratum provenance declared")
                    ),
                    residence_path: residence_path.clone(),
                });
            }
        }
        let max_heterogeneity = weighted_strata
            .iter()
            .map(|(_, stratum)| stratum.heterogeneity)
            .fold(0.0, f64::max);
        let count = exemplars.len().max(1) as f64;
        let mean_change = if max_heterogeneity <= 0.05 && count == 1.0 {
            0.0
        } else {
            max_heterogeneity / (count * 50.0)
        };
        let distribution_distance = max_heterogeneity / (count * 20.0);
        let tail_rate_change_points = max_heterogeneity / (count * 2.0);
        let converged =
            mean_change < 0.02 && distribution_distance < 0.05 && tail_rate_change_points < 0.5;
        cities.push(CityExemplarPlan {
            city_id: city.id.clone(),
            represented_people,
            represented_households: exemplars
                .iter()
                .map(|exemplar| exemplar.instances_represented * exemplar.households as f64)
                .sum::<f64>()
                .round() as u64,
            distribution_status: city.distribution_status.clone(),
            provenance: city
                .provenance
                .clone()
                .unwrap_or_else(|| "No provenance declared".to_owned()),
            residence_path,
            strata: weighted_strata
                .iter()
                .map(|(_, stratum)| {
                    stratum
                        .stratum
                        .clone()
                        .unwrap_or_else(|| stratum.id.clone())
                })
                .collect(),
            exemplars,
            convergence: ExemplarConvergence {
                mean_change,
                distribution_distance,
                tail_rate_change_points,
                converged,
                cap_hit: !converged && count as usize == MAX_EXEMPLARS_PER_CITY,
            },
            mixture_metrics: BTreeMap::new(),
        });
    }
    cities.sort_by(|left, right| left.city_id.cmp(&right.city_id));
    let total_represented_households = cities.iter().map(|city| city.represented_households).sum();
    let total_real_neighbourhood_instances = cities
        .iter()
        .flat_map(|city| &city.exemplars)
        .map(|exemplar| exemplar.instances_represented)
        .sum();
    let total_exemplars = cities.iter().map(|city| city.exemplars.len()).sum();
    Ok(ExemplarSystemPlan {
        total_represented_pool,
        total_represented_households,
        total_real_neighbourhood_instances,
        total_exemplars,
        cities,
        hierarchy_counts,
    })
}

fn cap_exemplar_counts(mut counts: Vec<usize>) -> Vec<usize> {
    while counts.iter().sum::<usize>() > MAX_EXEMPLARS_PER_CITY {
        let Some(index) = counts
            .iter()
            .enumerate()
            .filter(|(_, count)| **count > 1)
            .max_by_key(|(index, count)| (**count, std::cmp::Reverse(*index)))
            .map(|(index, _)| index)
        else {
            break;
        };
        counts[index] -= 1;
    }
    counts
}

pub fn restrict_program_to_city(program: &mut Program, city_id: &str) -> DslResult<()> {
    let root_id = program
        .compositions
        .iter()
        .find(|composition| composition.default_run)
        .and_then(|composition| composition.agent_pool.clone())
        .ok_or_else(|| DslError::new("MISSING_AGENT_POOL", 1, "Default run needs agent_pool"))?;
    if !program.compositions.iter().any(|composition| {
        composition.id == city_id && matches!(composition.level.as_str(), "municipality" | "city")
    }) {
        return Err(DslError::new(
            "UNKNOWN_EXEMPLAR_CITY",
            1,
            format!("Unknown exemplar city {city_id}"),
        ));
    }
    let mut child = city_id.to_owned();
    while child != root_id {
        let parent_id = program
            .compositions
            .iter()
            .find(|composition| composition.entries.iter().any(|entry| entry.child == child))
            .map(|composition| composition.id.clone())
            .ok_or_else(|| {
                DslError::new(
                    "CITY_OUTSIDE_AGENT_POOL",
                    1,
                    format!("City {city_id} has no path to {root_id}"),
                )
            })?;
        let parent = program
            .compositions
            .iter_mut()
            .find(|composition| composition.id == parent_id)
            .unwrap();
        parent.entries.retain(|entry| entry.child == child);
        if let Some(entry) = parent.entries.first_mut() {
            entry.weight = Some(1.0);
        }
        child = parent_id;
    }
    Ok(())
}

pub fn run_exemplar_system(
    mut program: Program,
    total_represented_pool: u64,
    seed: u64,
    ticks: u64,
    dsl_source_hash: &str,
    supplied_cache: BTreeMap<String, ExemplarCacheEntry>,
    exemplar_inputs: &BTreeMap<String, BTreeMap<String, f64>>,
    events: &[String],
) -> DslResult<ExemplarSystemRun> {
    let mut plan = plan_exemplars(&program, total_represented_pool, seed)?;
    let record_actions_requested = program.record_actions;
    program.represented_pool = Some(total_represented_pool);
    program.record_actions = true;
    program
        .role_distributions
        .retain(|distribution| distribution.role != "migrant");
    let mut cache = supplied_cache;
    let mut relearned_exemplars = Vec::new();
    let mut reused_exemplars = Vec::new();
    let mut invalidations = BTreeMap::new();
    let mut mass_agent_ticks = 0_u64;
    for city_index in 0..plan.cities.len() {
        let initial = plan.cities[city_index].exemplars.clone();
        for exemplar in &initial {
            mass_agent_ticks = mass_agent_ticks.saturating_add(resolve_exemplar_cache(
                &program,
                exemplar,
                ticks,
                dsl_source_hash,
                exemplar_inputs,
                events,
                &mut cache,
                &mut relearned_exemplars,
                &mut reused_exemplars,
                &mut invalidations,
            )?);
        }
        plan.cities[city_index].convergence =
            measured_convergence(&plan.cities[city_index], &cache);
        while !plan.cities[city_index].convergence.converged
            && plan.cities[city_index].exemplars.len() < MAX_EXEMPLARS_PER_CITY
        {
            let exemplar = append_next_exemplar(&mut plan.cities[city_index], &program, seed)?;
            mass_agent_ticks = mass_agent_ticks.saturating_add(resolve_exemplar_cache(
                &program,
                &exemplar,
                ticks,
                dsl_source_hash,
                exemplar_inputs,
                events,
                &mut cache,
                &mut relearned_exemplars,
                &mut reused_exemplars,
                &mut invalidations,
            )?);
            plan.cities[city_index].convergence =
                measured_convergence(&plan.cities[city_index], &cache);
        }
        if !plan.cities[city_index].convergence.converged
            && plan.cities[city_index].exemplars.len() == MAX_EXEMPLARS_PER_CITY
        {
            plan.cities[city_index].convergence.cap_hit = true;
        }
    }
    plan.total_exemplars = plan.cities.iter().map(|city| city.exemplars.len()).sum();
    plan.total_real_neighbourhood_instances = plan
        .cities
        .iter()
        .flat_map(|city| &city.exemplars)
        .map(|exemplar| exemplar.instances_represented)
        .sum();
    let active_exemplars = plan
        .cities
        .iter()
        .flat_map(|city| &city.exemplars)
        .map(|exemplar| exemplar.id.as_str())
        .collect::<BTreeSet<_>>();
    cache.retain(|id, _| active_exemplars.contains(id.as_str()));
    let leader_assignments = assign_spotlight_leaders(&program, &plan, &cache, seed);
    let boundary = run_boundary_agents(
        program.clone(),
        seed,
        boundary_agent_ticks(&program, ticks),
        &cache,
        &leader_assignments,
    )?;
    let feedback_inputs = boundary_feedback_inputs(&boundary);
    let (feedback_iterations, feedback_final_change) =
        apply_feedback(&plan, &mut cache, &feedback_inputs);
    let parent_cache_versions = parent_cache_versions(&program, &plan, &cache);
    let city_metrics = plan
        .cities
        .iter()
        .map(|city| (city.city_id.clone(), aggregate_city(city, &cache)))
        .collect::<BTreeMap<_, _>>();
    for city in &mut plan.cities {
        city.mixture_metrics = city_metrics.get(&city.city_id).cloned().unwrap_or_default();
        city.convergence = measured_convergence(city, &cache);
    }
    let mut reports = exemplar_reports(&plan, &city_metrics, &cache, ticks);
    let mut unassigned_required_roles = plan
        .cities
        .iter()
        .flat_map(|city| &city.exemplars)
        .filter_map(|exemplar| cache.get(&exemplar.id))
        .flat_map(|entry| &entry.agents)
        .filter(|agent| {
            !agent.roles.iter().any(|role| role == "household_member")
                || !agent.roles.iter().any(|role| role.starts_with("life_"))
                || !agent
                    .roles
                    .iter()
                    .any(|role| role.starts_with("resident_country_"))
                || !agent
                    .roles
                    .iter()
                    .any(|role| role.starts_with("resident_division_"))
                || !agent.roles.iter().any(|role| {
                    role.starts_with("resident_municipality_") || role.starts_with("resident_city_")
                })
                || !agent
                    .roles
                    .iter()
                    .any(|role| role.starts_with("resident_neighbourhood_"))
        })
        .count() as u64;
    unassigned_required_roles = unassigned_required_roles.saturating_add(
        required_leader_count(&program, &plan).saturating_sub(leader_assignments.len()) as u64,
    );
    reports.push(boundary_report(&boundary, ticks));
    let result = DslRunResult {
        completed_ticks: ticks,
        state: boundary.state,
        actions: if record_actions_requested {
            boundary.actions
        } else {
            Vec::new()
        },
        results_title: program.results_title.clone(),
        results_subtitle: "Weighted neighbourhood exemplar composition".to_owned(),
        reports,
    };
    Ok(ExemplarSystemRun {
        result,
        plan,
        cache,
        cache_stats: ExemplarCacheStats {
            cache_hit: relearned_exemplars.is_empty(),
            mass_agent_ticks,
            relearned_exemplars,
            reused_exemplars,
            invalidations,
            parent_cache_versions,
            feedback_iterations,
            feedback_final_change,
            feedback_inputs,
        },
        leader_assignments,
        unassigned_required_roles,
    })
}

#[allow(clippy::too_many_arguments)]
fn resolve_exemplar_cache(
    program: &Program,
    exemplar: &NeighbourhoodExemplarPlan,
    ticks: u64,
    dsl_source_hash: &str,
    exemplar_inputs: &BTreeMap<String, BTreeMap<String, f64>>,
    events: &[String],
    cache: &mut BTreeMap<String, ExemplarCacheEntry>,
    relearned_exemplars: &mut Vec<String>,
    reused_exemplars: &mut Vec<String>,
    invalidations: &mut BTreeMap<String, String>,
) -> DslResult<u64> {
    let inputs = resolved_inputs(exemplar, exemplar_inputs, events);
    let invalidation = cache.get(&exemplar.id).and_then(|entry| {
        cache_invalidation(
            entry,
            dsl_source_hash,
            exemplar.seed,
            ticks,
            &inputs,
            events,
        )
    });
    if cache.contains_key(&exemplar.id) && invalidation.is_none() {
        let entry = cache.get_mut(&exemplar.id).unwrap();
        entry.metrics = interpolate_grid_metrics(&entry.grid_points, &inputs);
        entry.inputs = inputs;
        reused_exemplars.push(exemplar.id.clone());
        return Ok(0);
    }
    let reason = invalidation.unwrap_or_else(|| "cache_miss".to_owned());
    let full_relearn = !reason.starts_with("outside_grid:") && !reason.starts_with("new_input:");
    let previous = cache.get(&exemplar.id);
    let (entry, agent_ticks) = learn_exemplar(
        program,
        exemplar,
        dsl_source_hash,
        ticks,
        inputs,
        previous,
        full_relearn,
    )?;
    invalidations.insert(exemplar.id.clone(), reason);
    cache.insert(exemplar.id.clone(), entry);
    relearned_exemplars.push(exemplar.id.clone());
    Ok(agent_ticks)
}

fn resolved_inputs(
    exemplar: &NeighbourhoodExemplarPlan,
    requested: &BTreeMap<String, BTreeMap<String, f64>>,
    events: &[String],
) -> BTreeMap<String, f64> {
    let mut inputs = default_inputs();
    if let Some(overrides) = requested.get(&exemplar.id) {
        inputs.extend(overrides.clone());
    }
    for event in events {
        let Some((city, value)) = event.split_once(':') else {
            continue;
        };
        if city != exemplar.city_id {
            continue;
        }
        let (input, explicit) = value.split_once('=').map_or(
            (value.trim_end_matches("_change"), None),
            |(input, value)| (input, value.parse::<f64>().ok()),
        );
        if let Some(current) = inputs.get_mut(input) {
            *current = explicit.unwrap_or(*current + input_span(input) * 0.25);
        }
    }
    inputs
}

fn input_span(input: &str) -> f64 {
    input_domain()
        .get(input)
        .map(|(minimum, maximum)| maximum - minimum)
        .unwrap_or(1.0)
}

fn append_next_exemplar(
    city: &mut CityExemplarPlan,
    program: &Program,
    seed: u64,
) -> DslResult<NeighbourhoodExemplarPlan> {
    let compositions = program
        .compositions
        .iter()
        .map(|composition| (composition.id.as_str(), composition))
        .collect::<BTreeMap<_, _>>();
    let mut sources = city
        .exemplars
        .iter()
        .map(|exemplar| exemplar.stratum_source.clone())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    sources.sort_by(|left, right| {
        let score = |source: &str| {
            let count = city
                .exemplars
                .iter()
                .filter(|exemplar| exemplar.stratum_source == source)
                .count() as f64;
            let share = city
                .exemplars
                .iter()
                .filter(|exemplar| exemplar.stratum_source == source)
                .map(|exemplar| exemplar.city_population_share)
                .sum::<f64>();
            let heterogeneity = compositions[source].heterogeneity;
            share * (heterogeneity + 0.05) / (count + 1.0)
        };
        score(right)
            .total_cmp(&score(left))
            .then_with(|| left.cmp(right))
    });
    let source = sources.first().ok_or_else(|| {
        DslError::new(
            "CITY_WITHOUT_STRATA",
            1,
            format!("City {} needs a neighbourhood stratum", city.city_id),
        )
    })?;
    let prototype = city
        .exemplars
        .iter()
        .find(|exemplar| exemplar.stratum_source == *source)
        .cloned()
        .unwrap();
    let ordinal = city
        .exemplars
        .iter()
        .filter(|exemplar| exemplar.stratum_source == *source)
        .count()
        + 1;
    let id = format!("{}__{}__{:02}", city.city_id, prototype.stratum, ordinal);
    let mut exemplar = prototype.clone();
    exemplar.id = id.clone();
    exemplar.seed = derived_seed(seed, &id);
    let represented_total = city
        .exemplars
        .iter()
        .filter(|candidate| candidate.stratum_source == *source)
        .map(|candidate| candidate.represented_people)
        .sum::<u64>();
    city.exemplars.push(exemplar);
    redistribute_stratum(city, source, represented_total);
    Ok(city.exemplars.last().cloned().unwrap())
}

fn redistribute_stratum(city: &mut CityExemplarPlan, source: &str, represented_total: u64) {
    let indices = city
        .exemplars
        .iter()
        .enumerate()
        .filter(|(_, exemplar)| exemplar.stratum_source == source)
        .map(|(index, _)| index)
        .collect::<Vec<_>>();
    let represented = largest_remainder_counts(represented_total, &vec![1.0; indices.len()]);
    for (index, count) in indices.into_iter().zip(represented) {
        let exemplar = &mut city.exemplars[index];
        let represented_per_instance = if exemplar.instances_represented > 0.0 {
            exemplar.represented_people as f64 / exemplar.instances_represented
        } else {
            exemplar.households as f64 * 2.5
        };
        exemplar.represented_people = count;
        exemplar.instances_represented = count as f64 / represented_per_instance;
        exemplar.city_population_share = count as f64 / city.represented_people as f64;
    }
}

fn boundary_agent_ticks(program: &Program, ticks: u64) -> u64 {
    let sync_minutes = program
        .compositions
        .iter()
        .filter(|composition| matches!(composition.level.as_str(), "municipality" | "city"))
        .filter_map(|composition| composition.sync_up_minutes)
        .min()
        .unwrap_or(1_440);
    let elapsed_minutes = ticks as f64 * program.tick_hours * 60.0;
    (elapsed_minutes / sync_minutes as f64).floor() as u64 * 24
}

fn boundary_feedback_inputs(boundary: &DslRunResult) -> BTreeMap<String, BTreeMap<String, f64>> {
    let defaults = default_inputs();
    let mut values = BTreeMap::<(String, String), Vec<f64>>::new();
    for agent in &boundary.state.agents {
        let Some(city) = agent
            .roles
            .iter()
            .find_map(|role| role.strip_prefix("resident_municipality_"))
        else {
            continue;
        };
        for (input, default) in &defaults {
            let Some(value) = agent.value(input).and_then(DslValue::as_f64) else {
                continue;
            };
            if (value - default).abs() > f64::EPSILON {
                values
                    .entry((city.to_owned(), input.clone()))
                    .or_default()
                    .push(value);
            }
        }
    }
    let mut result = BTreeMap::<String, BTreeMap<String, f64>>::new();
    for ((city, input), values) in values {
        result.entry(city).or_default().insert(
            input,
            values.iter().sum::<f64>() / values.len().max(1) as f64,
        );
    }
    result
}

fn apply_feedback(
    plan: &ExemplarSystemPlan,
    cache: &mut BTreeMap<String, ExemplarCacheEntry>,
    feedback_inputs: &BTreeMap<String, BTreeMap<String, f64>>,
) -> (u32, f64) {
    if feedback_inputs.is_empty() {
        return (0, 0.0);
    }
    let mut final_change = 0.0;
    for iteration in 1..=5 {
        let before = plan
            .cities
            .iter()
            .map(|city| (city.city_id.clone(), aggregate_city(city, cache)))
            .collect::<BTreeMap<_, _>>();
        for city in &plan.cities {
            let Some(inputs) = feedback_inputs.get(&city.city_id) else {
                continue;
            };
            for exemplar in &city.exemplars {
                let Some(entry) = cache.get_mut(&exemplar.id) else {
                    continue;
                };
                let mut requested = entry.inputs.clone();
                requested.extend(inputs.clone());
                entry.metrics = interpolate_grid_metrics(&entry.grid_points, &requested);
                entry.inputs = requested;
            }
        }
        let after = plan
            .cities
            .iter()
            .map(|city| (city.city_id.clone(), aggregate_city(city, cache)))
            .collect::<BTreeMap<_, _>>();
        final_change = aggregate_feedback_change(&before, &after);
        if final_change < 0.01 {
            return (iteration, final_change);
        }
    }
    (5, final_change)
}

fn aggregate_feedback_change(
    before: &BTreeMap<String, BTreeMap<String, ExemplarMetricDistribution>>,
    after: &BTreeMap<String, BTreeMap<String, ExemplarMetricDistribution>>,
) -> f64 {
    before
        .iter()
        .flat_map(|(city, metrics)| {
            metrics.iter().filter_map(|(metric, before)| {
                after
                    .get(city)
                    .and_then(|values| values.get(metric))
                    .map(|after| (after.mean - before.mean).abs() / before.mean.abs().max(1.0))
            })
        })
        .fold(0.0, f64::max)
}

fn run_boundary_agents(
    mut program: Program,
    seed: u64,
    ticks: u64,
    cache: &BTreeMap<String, ExemplarCacheEntry>,
    leader_assignments: &BTreeMap<String, String>,
) -> DslResult<DslRunResult> {
    program.record_actions = true;
    let summaries = cache
        .values()
        .flat_map(|entry| &entry.agents)
        .map(|agent| (agent.id.as_str(), agent))
        .collect::<BTreeMap<_, _>>();
    let city_by_agent = cache
        .values()
        .flat_map(|entry| {
            entry
                .agents
                .iter()
                .map(move |agent| (agent.id.as_str(), entry.city_id.as_str()))
        })
        .collect::<BTreeMap<_, _>>();
    let mut used = BTreeSet::new();
    let mut agents = Vec::new();
    for (office, agent_id) in leader_assignments {
        let Some(summary) = summaries.get(agent_id.as_str()) else {
            continue;
        };
        let role = office.split(':').nth(1).unwrap_or("leader");
        used.insert(agent_id.clone());
        agents.push(project_boundary_agent(
            summary,
            &[role],
            boundary_location(&[role]),
        ));
    }
    let specifications = [
        ("migrant", "Toronto", "Home"),
        ("commuter", "Toronto", "TransitHub"),
        ("commuter", "Vancouver", "TransitHub"),
        ("trader", "Toronto", "Exchange"),
        ("trader", "Lytton", "Exchange"),
        ("owner", "Houston", "Store"),
        ("president", "Lytton", "DiplomaticForum"),
    ];
    let mut candidates = summaries.values().copied().collect::<Vec<_>>();
    candidates.sort_by_key(|agent| derived_seed(seed, &agent.id));
    for (role, preferred_city, location) in specifications {
        let selected = candidates
            .iter()
            .find(|agent| {
                !used.contains(&agent.id)
                    && city_by_agent.get(agent.id.as_str()).copied() == Some(preferred_city)
            })
            .or_else(|| candidates.iter().find(|agent| !used.contains(&agent.id)));
        let Some(summary) = selected else {
            continue;
        };
        used.insert(summary.id.clone());
        agents.push(project_boundary_agent(summary, &[role], location));
    }
    let places = program
        .places
        .iter()
        .map(|place| DslPlaceState {
            id: place.id.clone(),
            states: place.states.clone(),
        })
        .collect();
    let time = agents
        .iter()
        .map(|_| DslAgentTimeState {
            active_primary: None,
            deferred: Vec::new(),
            occurrence_counts: BTreeMap::new(),
        })
        .collect();
    run_program(DslRunRequest::resume(
        program,
        seed,
        ticks,
        DslRunState {
            completed_ticks: 0,
            agents,
            places,
            relationships: Vec::new(),
            time,
        },
    ))
}

fn project_boundary_agent(
    summary: &ExemplarAgentSummary,
    roles: &[&str],
    location: &str,
) -> DslAgentState {
    let mut assigned_roles = summary.roles.iter().cloned().collect::<BTreeSet<_>>();
    assigned_roles.extend(roles.iter().map(|role| (*role).to_owned()));
    DslAgentState {
        id: summary.id.clone(),
        agent_type: "Person".to_owned(),
        roles: assigned_roles,
        traits: BTreeMap::from([
            ("age".to_owned(), DslValue::Number(summary.age.max(18.0))),
            ("risk".to_owned(), DslValue::Number(0.8)),
            ("activity".to_owned(), DslValue::Number(0.8)),
            ("interest".to_owned(), DslValue::Number(0.8)),
            ("interest_match".to_owned(), DslValue::Number(0.8)),
            ("agreement".to_owned(), DslValue::Number(0.8)),
            ("aggression".to_owned(), DslValue::Number(0.2)),
            ("has_family".to_owned(), DslValue::Bool(false)),
        ]),
        states: BTreeMap::from([
            ("location".to_owned(), DslValue::Text(location.to_owned())),
            ("money".to_owned(), DslValue::Number(summary.money)),
            ("stress".to_owned(), DslValue::Number(summary.stress)),
            ("health".to_owned(), DslValue::Number(0.9)),
            ("shares".to_owned(), DslValue::Number(10.0)),
            ("outrage".to_owned(), DslValue::Number(0.4)),
            ("residence_change".to_owned(), DslValue::Number(0.0)),
            ("alcohol".to_owned(), DslValue::Number(0.0)),
            ("reputation".to_owned(), DslValue::Number(0.5)),
            ("tax".to_owned(), DslValue::Number(0.25)),
            ("unemployment".to_owned(), DslValue::Number(0.06)),
            ("media_trend".to_owned(), DslValue::Number(0.0)),
            ("price".to_owned(), DslValue::Number(1.0)),
            ("policy".to_owned(), DslValue::Number(0.0)),
        ]),
        current_decision: "where_to_go".to_owned(),
        parent_id: None,
        household_id: summary.household_id.clone(),
    }
}

fn boundary_location(roles: &[&str]) -> &'static str {
    if roles
        .iter()
        .any(|role| matches!(*role, "president" | "prime_minister"))
    {
        "DiplomaticForum"
    } else if roles.iter().any(|role| *role == "influencer") {
        "Feed"
    } else if roles.iter().any(|role| *role == "ceo") {
        "Exchange"
    } else if roles.iter().any(|role| {
        matches!(
            *role,
            "store_manager" | "brand_manager" | "franchise_manager"
        )
    }) {
        "Store"
    } else {
        "Home"
    }
}

fn boundary_report(result: &DslRunResult, ticks: u64) -> DslReport {
    let counts =
        result
            .actions
            .iter()
            .fold(BTreeMap::<String, f64>::new(), |mut values, action| {
                *values
                    .entry(
                        action
                            .action
                            .rsplit("__")
                            .next()
                            .unwrap_or(&action.action)
                            .to_owned(),
                    )
                    .or_default() += 1.0;
                values
            });
    DslReport {
        id: "boundary_agent_actions".to_owned(),
        title: "Boundary and spotlight agent actions".to_owned(),
        group_by: "action".to_owned(),
        display: "table".to_owned(),
        record: "final".to_owned(),
        columns: vec![report_column("count", "Count", "integer")],
        snapshots: vec![DslReportSnapshot {
            tick: ticks,
            rows: counts
                .into_iter()
                .map(|(action, count)| DslReportRow {
                    group_id: action,
                    values: BTreeMap::from([("count".to_owned(), DslReportValue::Number(count))]),
                })
                .collect(),
        }],
    }
}

fn allocate_hierarchy(
    composition: &CompositionDefinition,
    represented: u64,
    compositions: &BTreeMap<&str, &CompositionDefinition>,
    path: &[String],
    hierarchy_counts: &mut BTreeMap<String, u64>,
    city_counts: &mut BTreeMap<String, u64>,
    city_paths: &mut BTreeMap<String, Vec<String>>,
) -> DslResult<()> {
    hierarchy_counts.insert(composition.id.clone(), represented);
    if matches!(composition.level.as_str(), "municipality" | "city") {
        city_counts.insert(composition.id.clone(), represented);
        city_paths.insert(composition.id.clone(), path.to_vec());
        return Ok(());
    }
    let children = composition
        .entries
        .iter()
        .filter_map(|entry| {
            compositions
                .get(entry.child.as_str())
                .map(|child| (entry, *child))
        })
        .collect::<Vec<_>>();
    if children.is_empty() {
        return Ok(());
    }
    let weights = children
        .iter()
        .map(|(entry, _)| entry.weight.unwrap_or(0.0))
        .collect::<Vec<_>>();
    let counts = largest_remainder_counts(represented, &weights);
    for ((_, child), count) in children.into_iter().zip(counts) {
        let mut child_path = path.to_vec();
        child_path.push(child.id.clone());
        allocate_hierarchy(
            child,
            count,
            compositions,
            &child_path,
            hierarchy_counts,
            city_counts,
            city_paths,
        )?;
    }
    Ok(())
}

fn allocate_households(
    stratum: &CompositionDefinition,
    households: u32,
) -> DslResult<BTreeMap<String, u32>> {
    let weights = stratum
        .entries
        .iter()
        .map(|entry| entry.weight.unwrap_or(0.0))
        .collect::<Vec<_>>();
    let counts = largest_remainder_counts(households as u64, &weights);
    let values = stratum
        .entries
        .iter()
        .zip(counts)
        .map(|(entry, count)| (entry.child.clone(), count as u32))
        .collect::<BTreeMap<_, _>>();
    if values.values().sum::<u32>() != households {
        return Err(DslError::new(
            "EXEMPLAR_HOUSEHOLD_MISMATCH",
            stratum.line,
            "Exemplar household allocations do not sum to its declared size",
        ));
    }
    Ok(values)
}

fn largest_remainder_counts(total: u64, weights: &[f64]) -> Vec<u64> {
    let sum = weights.iter().sum::<f64>();
    let mut values = weights
        .iter()
        .enumerate()
        .map(|(index, weight)| {
            let exact = if sum <= 0.0 {
                0.0
            } else {
                total as f64 * weight / sum
            };
            (index, exact.floor() as u64, exact.fract())
        })
        .collect::<Vec<_>>();
    let mut remaining = total.saturating_sub(values.iter().map(|(_, value, _)| *value).sum());
    values.sort_by(|left, right| {
        right
            .2
            .total_cmp(&left.2)
            .then_with(|| left.0.cmp(&right.0))
    });
    for (_, value, _) in &mut values {
        if remaining == 0 {
            break;
        }
        *value += 1;
        remaining -= 1;
    }
    values.sort_by_key(|(index, _, _)| *index);
    values.into_iter().map(|(_, value, _)| value).collect()
}

fn learn_exemplar(
    program: &Program,
    exemplar: &NeighbourhoodExemplarPlan,
    dsl_source_hash: &str,
    ticks: u64,
    inputs: BTreeMap<String, f64>,
    previous: Option<&ExemplarCacheEntry>,
    full_relearn: bool,
) -> DslResult<(ExemplarCacheEntry, u64)> {
    let training_inputs = if full_relearn {
        initial_training_grid(&inputs)
    } else {
        vec![inputs.clone()]
    };
    let mut grid_points = if full_relearn {
        Vec::new()
    } else {
        previous
            .map(|entry| entry.grid_points.clone())
            .unwrap_or_default()
    };
    let mut selected_result = None;
    let mut learning_seconds = 0.0;
    let mut agent_ticks = 0_u64;
    for point_inputs in training_inputs {
        let (result, elapsed) = simulate_exemplar(program, exemplar, ticks, &point_inputs)?;
        learning_seconds += elapsed;
        agent_ticks = agent_ticks.saturating_add(result.state.agents.len() as u64 * ticks);
        let metrics = exemplar_metrics(program, &result);
        if let Some(point) = grid_points
            .iter_mut()
            .find(|point| point.inputs == point_inputs)
        {
            point.metrics = metrics;
        } else {
            grid_points.push(ExemplarGridPoint {
                inputs: point_inputs.clone(),
                metrics,
            });
        }
        if point_inputs == inputs {
            selected_result = Some(result);
        }
    }
    let selected_result = selected_result.ok_or_else(|| {
        DslError::new(
            "MISSING_EXEMPLAR_GRID_POINT",
            1,
            format!(
                "Exemplar {} did not learn its requested input point",
                exemplar.id
            ),
        )
    })?;
    let agents = selected_result
        .state
        .agents
        .iter()
        .map(|agent| ExemplarAgentSummary {
            id: agent.id.clone(),
            agent_type: agent.agent_type.clone(),
            household_id: agent.household_id.clone(),
            roles: agent.roles.iter().cloned().collect(),
            residence_path: exemplar.residence_path.clone(),
            age: agent.value("age").and_then(DslValue::as_f64).unwrap_or(0.0),
            money: agent
                .value("money")
                .and_then(DslValue::as_f64)
                .unwrap_or(0.0),
            stress: agent
                .value("stress")
                .and_then(DslValue::as_f64)
                .unwrap_or(0.0),
        })
        .collect();
    let relationships = selected_result
        .state
        .relationships
        .iter()
        .map(|relationship| ExemplarRelationshipSummary {
            kind: relationship.kind.clone(),
            source_id: relationship.source_id.clone(),
            target_id: relationship.target_id.clone(),
        })
        .collect();
    let input_grid = grid_bounds(&grid_points);
    let metrics = interpolate_grid_metrics(&grid_points, &inputs);
    let previous_version = previous.map(|entry| entry.version).unwrap_or(0);
    let previous_ticks = previous.map(|entry| entry.learning_ticks).unwrap_or(0);
    let previous_seconds = previous.map(|entry| entry.learning_seconds).unwrap_or(0.0);
    Ok((
        ExemplarCacheEntry {
            schema_version: EXEMPLAR_CACHE_SCHEMA_VERSION,
            engine_version: env!("CARGO_PKG_VERSION").to_owned(),
            exemplar_id: exemplar.id.clone(),
            city_id: exemplar.city_id.clone(),
            stratum: exemplar.stratum.clone(),
            dsl_source_hash: dsl_source_hash.to_owned(),
            seed: exemplar.seed,
            version: previous_version + 1,
            learning_ticks: previous_ticks.saturating_add(agent_ticks),
            time_window_ticks: ticks,
            learning_seconds: previous_seconds + learning_seconds,
            valid_for_days: 365,
            input_grid,
            inputs,
            metrics,
            grid_points,
            agents,
            relationships,
            dependencies: exemplar_dependencies(program, exemplar),
            dependency_versions: BTreeMap::new(),
        },
        agent_ticks,
    ))
}

fn simulate_exemplar(
    program: &Program,
    exemplar: &NeighbourhoodExemplarPlan,
    ticks: u64,
    inputs: &BTreeMap<String, f64>,
) -> DslResult<(DslRunResult, f64)> {
    let mut exemplar_program = program.clone();
    for composition in &mut exemplar_program.compositions {
        composition.leaders.clear();
    }
    let definition = exemplar_program
        .compositions
        .iter_mut()
        .find(|composition| composition.id == exemplar.stratum_source)
        .ok_or_else(|| {
            DslError::new(
                "UNKNOWN_EXEMPLAR_STRATUM",
                1,
                format!("Unknown stratum {}", exemplar.stratum_source),
            )
        })?;
    definition.exemplar_households = Some(exemplar.households);
    definition.parameters.extend(inputs.clone());
    let learning_started = Instant::now();
    let mut result = run_composition(
        exemplar_program,
        &exemplar.stratum_source,
        exemplar.seed,
        ticks,
    )
    .map_err(|error| {
        DslError::new(
            &error.code,
            error.line,
            format!(
                "Exemplar {} at inputs {:?}: {}",
                exemplar.id, inputs, error.message
            ),
        )
    })?;
    let learning_seconds = learning_started.elapsed().as_secs_f64();
    namespace_exemplar_result(&mut result, &exemplar.id);
    for agent in &mut result.state.agents {
        agent.roles.retain(|role| !role.starts_with("resident_"));
        for id in &exemplar.residence_path {
            let level = program
                .compositions
                .iter()
                .find(|composition| composition.id == *id)
                .map(|composition| composition.level.as_str())
                .unwrap_or("place");
            agent.roles.insert(format!("resident_{level}_{id}"));
        }
        agent
            .roles
            .insert(format!("resident_neighbourhood_{}", exemplar.id));
    }
    Ok((result, learning_seconds))
}

fn namespace_exemplar_result(result: &mut DslRunResult, exemplar_id: &str) {
    let agent_ids = result
        .state
        .agents
        .iter()
        .map(|agent| (agent.id.clone(), format!("{exemplar_id}__{}", agent.id)))
        .collect::<BTreeMap<_, _>>();
    let household_ids = result
        .state
        .agents
        .iter()
        .map(|agent| {
            (
                agent.household_id.clone(),
                format!("{exemplar_id}__{}", agent.household_id),
            )
        })
        .collect::<BTreeMap<_, _>>();
    for agent in &mut result.state.agents {
        agent.id = agent_ids[&agent.id].clone();
        agent.household_id = household_ids[&agent.household_id].clone();
        if let Some(parent_id) = &mut agent.parent_id
            && let Some(value) = agent_ids.get(parent_id)
        {
            *parent_id = value.clone();
        }
    }
    for relationship in &mut result.state.relationships {
        if let Some(value) = agent_ids.get(&relationship.source_id) {
            relationship.source_id = value.clone();
        }
        if let Some(value) = agent_ids.get(&relationship.target_id) {
            relationship.target_id = value.clone();
        }
    }
    for action in &mut result.actions {
        if let Some(value) = agent_ids.get(&action.agent_id) {
            action.agent_id = value.clone();
        }
        if let Some(target_id) = &mut action.target_id
            && let Some(value) = agent_ids.get(target_id)
        {
            *target_id = value.clone();
        }
    }
}

fn exemplar_dependencies(program: &Program, exemplar: &NeighbourhoodExemplarPlan) -> Vec<String> {
    let mut dependencies = vec![format!("composition:{}", exemplar.stratum_source)];
    if let Some(composition) = program
        .compositions
        .iter()
        .find(|composition| composition.id == exemplar.stratum_source)
    {
        dependencies.extend(
            composition
                .policies
                .iter()
                .map(|policy| format!("policy:{policy}")),
        );
    }
    dependencies.extend(
        program
            .role_distributions
            .iter()
            .map(|distribution| format!("role_distribution:{}", distribution.role)),
    );
    dependencies.sort();
    dependencies.dedup();
    dependencies
}

fn initial_training_grid(inputs: &BTreeMap<String, f64>) -> Vec<BTreeMap<String, f64>> {
    let domain = input_domain();
    let low = inputs
        .keys()
        .map(|id| {
            (
                id.clone(),
                domain.get(id).map(|bounds| bounds.0).unwrap_or(inputs[id]),
            )
        })
        .collect::<BTreeMap<_, _>>();
    let high = inputs
        .keys()
        .map(|id| {
            (
                id.clone(),
                domain.get(id).map(|bounds| bounds.1).unwrap_or(inputs[id]),
            )
        })
        .collect::<BTreeMap<_, _>>();
    let mut points = vec![low, inputs.clone(), high];
    points.dedup();
    points
}

fn input_domain() -> BTreeMap<String, (f64, f64)> {
    BTreeMap::from([
        ("tax".to_owned(), (0.10, 0.40)),
        ("unemployment".to_owned(), (0.02, 0.15)),
        ("media_trend".to_owned(), (-1.0, 1.0)),
        ("price".to_owned(), (0.5, 2.0)),
        ("policy".to_owned(), (-1.0, 1.0)),
    ])
}

fn grid_bounds(points: &[ExemplarGridPoint]) -> BTreeMap<String, (f64, f64)> {
    let mut bounds = BTreeMap::<String, (f64, f64)>::new();
    for point in points {
        for (id, value) in &point.inputs {
            let entry = bounds.entry(id.clone()).or_insert((*value, *value));
            entry.0 = entry.0.min(*value);
            entry.1 = entry.1.max(*value);
        }
    }
    bounds
}

fn interpolate_grid_metrics(
    points: &[ExemplarGridPoint],
    inputs: &BTreeMap<String, f64>,
) -> BTreeMap<String, ExemplarMetricDistribution> {
    if let Some(point) = points.iter().find(|point| point.inputs == *inputs) {
        return point.metrics.clone();
    }
    let bounds = grid_bounds(points);
    let weights = points
        .iter()
        .map(|point| {
            let distance = inputs
                .iter()
                .map(|(id, value)| {
                    let span = bounds
                        .get(id)
                        .map(|(minimum, maximum)| (maximum - minimum).abs())
                        .unwrap_or(1.0)
                        .max(f64::EPSILON);
                    ((value - point.inputs.get(id).copied().unwrap_or(*value)) / span).powi(2)
                })
                .sum::<f64>();
            1.0 / (distance + 1e-9)
        })
        .collect::<Vec<_>>();
    let denominator = weights.iter().sum::<f64>().max(f64::EPSILON);
    let metric_ids = points
        .iter()
        .flat_map(|point| point.metrics.keys())
        .cloned()
        .collect::<BTreeSet<_>>();
    metric_ids
        .into_iter()
        .filter_map(|id| {
            let weighted = points
                .iter()
                .zip(&weights)
                .filter_map(|(point, weight)| {
                    point.metrics.get(&id).map(|metric| (*weight, metric))
                })
                .collect::<Vec<_>>();
            if weighted.is_empty() {
                return None;
            }
            let mean = weighted
                .iter()
                .map(|(weight, metric)| weight * metric.mean)
                .sum::<f64>()
                / denominator;
            let second = weighted
                .iter()
                .map(|(weight, metric)| {
                    weight * (metric.standard_deviation.powi(2) + metric.mean.powi(2))
                })
                .sum::<f64>()
                / denominator;
            let value = |select: fn(&ExemplarMetricDistribution) -> f64| {
                weighted
                    .iter()
                    .map(|(weight, metric)| weight * select(metric))
                    .sum::<f64>()
                    / denominator
            };
            Some((
                id,
                ExemplarMetricDistribution {
                    mean: stable_exemplar_number(mean),
                    standard_deviation: stable_exemplar_number(
                        (second - mean.powi(2)).max(0.0).sqrt(),
                    ),
                    p10: stable_exemplar_number(value(|metric| metric.p10)),
                    p50: stable_exemplar_number(value(|metric| metric.p50)),
                    p90: stable_exemplar_number(value(|metric| metric.p90)),
                    tail_rate: stable_exemplar_number(value(|metric| metric.tail_rate)),
                    quantile_points: interpolate_quantile_points(&weighted, denominator),
                },
            ))
        })
        .collect()
}

fn exemplar_metrics(
    program: &Program,
    result: &DslRunResult,
) -> BTreeMap<String, ExemplarMetricDistribution> {
    let mut metrics = ["money", "stress", "health", "vote_liberal"]
        .into_iter()
        .map(|field| {
            let values = result
                .state
                .agents
                .iter()
                .filter_map(|agent| agent.value(field).and_then(DslValue::as_f64))
                .collect::<Vec<_>>();
            (field.to_owned(), metric_distribution(&values, 0.0))
        })
        .collect::<BTreeMap<_, _>>();
    let aggregates = program
        .actions
        .iter()
        .map(|action| (action.id.as_str(), action.aggregate.as_str()))
        .collect::<BTreeMap<_, _>>();
    let agent_indices = result
        .state
        .agents
        .iter()
        .enumerate()
        .map(|(index, agent)| (agent.id.as_str(), index))
        .collect::<BTreeMap<_, _>>();
    let mut counts = BTreeMap::<String, Vec<f64>>::new();
    for aggregate in aggregates.values().copied().collect::<BTreeSet<_>>() {
        counts.insert(aggregate.to_owned(), vec![0.0; result.state.agents.len()]);
    }
    for action in &result.actions {
        let Some(index) = agent_indices.get(action.agent_id.as_str()) else {
            continue;
        };
        let action_id = action.action.rsplit("__").next().unwrap_or(&action.action);
        let Some(aggregate) = aggregates.get(action_id) else {
            continue;
        };
        if let Some(values) = counts.get_mut(*aggregate) {
            values[*index] += 1.0;
        }
    }
    for (aggregate, values) in counts {
        let tail_rate =
            values.iter().filter(|value| **value > 0.0).count() as f64 / values.len().max(1) as f64;
        metrics.insert(
            format!("action:{aggregate}"),
            metric_distribution(&values, tail_rate),
        );
    }
    metrics
}

fn interpolate_quantile_points(
    weighted: &[(f64, &ExemplarMetricDistribution)],
    denominator: f64,
) -> Vec<f64> {
    let length = weighted
        .iter()
        .map(|(_, metric)| metric.quantile_points.len())
        .max()
        .unwrap_or(0);
    (0..length)
        .map(|index| {
            let value = weighted
                .iter()
                .map(|(weight, metric)| {
                    weight
                        * metric
                            .quantile_points
                            .get(index)
                            .copied()
                            .unwrap_or(metric.p50)
                })
                .sum::<f64>();
            stable_exemplar_number(value / denominator)
        })
        .collect()
}

fn metric_distribution(values: &[f64], tail_rate: f64) -> ExemplarMetricDistribution {
    if values.is_empty() {
        return ExemplarMetricDistribution {
            mean: 0.0,
            standard_deviation: 0.0,
            p10: 0.0,
            p50: 0.0,
            p90: 0.0,
            tail_rate,
            quantile_points: vec![0.0; 21],
        };
    }
    let mean = values.iter().sum::<f64>() / values.len() as f64;
    let standard_deviation = (values
        .iter()
        .map(|value| (value - mean).powi(2))
        .sum::<f64>()
        / values.len() as f64)
        .sqrt();
    let mut sorted = values.to_vec();
    sorted.sort_by(f64::total_cmp);
    let quantile = |probability: f64| {
        let index = ((sorted.len() - 1) as f64 * probability).round() as usize;
        sorted[index]
    };
    ExemplarMetricDistribution {
        mean,
        standard_deviation,
        p10: quantile(0.10),
        p50: quantile(0.50),
        p90: quantile(0.90),
        tail_rate,
        quantile_points: (0..=20)
            .map(|index| quantile(index as f64 / 20.0))
            .collect(),
    }
}

fn aggregate_city(
    city: &CityExemplarPlan,
    cache: &BTreeMap<String, ExemplarCacheEntry>,
) -> BTreeMap<String, ExemplarMetricDistribution> {
    let metric_ids = city
        .exemplars
        .first()
        .and_then(|exemplar| cache.get(&exemplar.id))
        .map(|entry| entry.metrics.keys().cloned().collect::<Vec<_>>())
        .unwrap_or_default();
    metric_ids
        .into_iter()
        .map(|metric_id| {
            let weighted = city
                .exemplars
                .iter()
                .filter_map(|exemplar| {
                    cache
                        .get(&exemplar.id)
                        .and_then(|entry| entry.metrics.get(&metric_id))
                        .map(|metric| (exemplar.city_population_share, metric))
                })
                .collect::<Vec<_>>();
            let mean = weighted
                .iter()
                .map(|(weight, metric)| weight * metric.mean)
                .sum::<f64>();
            let variance = weighted
                .iter()
                .map(|(weight, metric)| {
                    weight * (metric.standard_deviation.powi(2) + (metric.mean - mean).powi(2))
                })
                .sum::<f64>();
            let weighted_value = |value: fn(&ExemplarMetricDistribution) -> f64| {
                weighted
                    .iter()
                    .map(|(weight, metric)| weight * value(metric))
                    .sum::<f64>()
            };
            let quantile_points = mixture_quantile_points(&weighted);
            (
                metric_id,
                ExemplarMetricDistribution {
                    mean: stable_exemplar_number(mean),
                    standard_deviation: stable_exemplar_number(variance.sqrt()),
                    p10: quantile_points.get(2).copied().unwrap_or(0.0),
                    p50: quantile_points.get(10).copied().unwrap_or(0.0),
                    p90: quantile_points.get(18).copied().unwrap_or(0.0),
                    tail_rate: stable_exemplar_number(weighted_value(|metric| metric.tail_rate)),
                    quantile_points,
                },
            )
        })
        .collect()
}

fn mixture_quantile_points(weighted: &[(f64, &ExemplarMetricDistribution)]) -> Vec<f64> {
    let mut values = weighted
        .iter()
        .flat_map(|(weight, metric)| {
            let points = if metric.quantile_points.is_empty() {
                vec![metric.p10, metric.p50, metric.p90]
            } else {
                metric.quantile_points.clone()
            };
            let point_weight = *weight / points.len().max(1) as f64;
            points.into_iter().map(move |value| (value, point_weight))
        })
        .collect::<Vec<_>>();
    values.sort_by(|left, right| left.0.total_cmp(&right.0));
    let total = values.iter().map(|(_, weight)| weight).sum::<f64>();
    (0..=20)
        .map(|index| {
            let target = total * index as f64 / 20.0;
            let mut cumulative = 0.0;
            values
                .iter()
                .find_map(|(value, weight)| {
                    cumulative += weight;
                    (cumulative >= target).then_some(*value)
                })
                .or_else(|| values.last().map(|(value, _)| *value))
                .unwrap_or(0.0)
        })
        .collect()
}

fn stable_exemplar_number(value: f64) -> f64 {
    (value * 1_000_000_000_000.0).round() / 1_000_000_000_000.0
}

fn measured_convergence(
    city: &CityExemplarPlan,
    cache: &BTreeMap<String, ExemplarCacheEntry>,
) -> ExemplarConvergence {
    if city.exemplars.len() <= 1 {
        return ExemplarConvergence {
            mean_change: 0.0,
            distribution_distance: 0.0,
            tail_rate_change_points: 0.0,
            converged: true,
            cap_hit: false,
        };
    }
    let full = aggregate_city(city, cache);
    let mut previous = city.clone();
    previous.exemplars.pop();
    let weight_sum = previous
        .exemplars
        .iter()
        .map(|exemplar| exemplar.city_population_share)
        .sum::<f64>();
    for exemplar in &mut previous.exemplars {
        exemplar.city_population_share /= weight_sum;
    }
    let prior = aggregate_city(&previous, cache);
    let mut mean_change = 0.0_f64;
    let mut distribution_distance = 0.0_f64;
    let mut tail_rate_change_points = 0.0_f64;
    for (id, current) in &full {
        let Some(before) = prior.get(id) else {
            continue;
        };
        mean_change =
            mean_change.max((current.mean - before.mean).abs() / before.mean.abs().max(1.0));
        for (current_value, prior_value) in [
            (current.p10, before.p10),
            (current.p50, before.p50),
            (current.p90, before.p90),
        ] {
            distribution_distance = distribution_distance
                .max((current_value - prior_value).abs() / prior_value.abs().max(1.0));
        }
        tail_rate_change_points =
            tail_rate_change_points.max((current.tail_rate - before.tail_rate).abs() * 100.0);
    }
    let converged =
        mean_change < 0.02 && distribution_distance < 0.05 && tail_rate_change_points < 0.5;
    ExemplarConvergence {
        mean_change,
        distribution_distance,
        tail_rate_change_points,
        converged,
        cap_hit: !converged && city.exemplars.len() == MAX_EXEMPLARS_PER_CITY,
    }
}

fn exemplar_reports(
    plan: &ExemplarSystemPlan,
    city_metrics: &BTreeMap<String, BTreeMap<String, ExemplarMetricDistribution>>,
    cache: &BTreeMap<String, ExemplarCacheEntry>,
    ticks: u64,
) -> Vec<DslReport> {
    let city_columns = vec![
        report_column("represented_people", "Represented people", "integer"),
        report_column(
            "represented_households",
            "Represented households",
            "integer",
        ),
        report_column("exemplars", "Exemplars", "integer"),
        report_column("mean_income", "Mean income", "number"),
        report_column("income_sd", "Income SD", "number"),
        report_column("income_p10", "Income p10", "number"),
        report_column("income_p50", "Income p50", "number"),
        report_column("income_p90", "Income p90", "number"),
        report_column("tail_rate", "Tail rate", "decimal"),
    ];
    let city_rows = plan
        .cities
        .iter()
        .map(|city| {
            let income = city_metrics
                .get(&city.city_id)
                .and_then(|metrics| metrics.get("money"));
            DslReportRow {
                group_id: city.city_id.clone(),
                values: BTreeMap::from([
                    (
                        "represented_people".to_owned(),
                        DslReportValue::Number(city.represented_people as f64),
                    ),
                    (
                        "represented_households".to_owned(),
                        DslReportValue::Number(city.represented_households as f64),
                    ),
                    (
                        "exemplars".to_owned(),
                        DslReportValue::Number(city.exemplars.len() as f64),
                    ),
                    (
                        "mean_income".to_owned(),
                        DslReportValue::Number(income.map(|metric| metric.mean).unwrap_or(0.0)),
                    ),
                    (
                        "income_sd".to_owned(),
                        DslReportValue::Number(
                            income
                                .map(|metric| metric.standard_deviation)
                                .unwrap_or(0.0),
                        ),
                    ),
                    (
                        "income_p10".to_owned(),
                        DslReportValue::Number(income.map(|metric| metric.p10).unwrap_or(0.0)),
                    ),
                    (
                        "income_p50".to_owned(),
                        DslReportValue::Number(income.map(|metric| metric.p50).unwrap_or(0.0)),
                    ),
                    (
                        "income_p90".to_owned(),
                        DslReportValue::Number(income.map(|metric| metric.p90).unwrap_or(0.0)),
                    ),
                    (
                        "tail_rate".to_owned(),
                        DslReportValue::Number(
                            income.map(|metric| metric.tail_rate).unwrap_or(0.0),
                        ),
                    ),
                ]),
            }
        })
        .collect();
    let exemplar_columns = vec![
        report_column("households", "Households", "integer"),
        report_column("people", "People", "integer"),
        report_column("instances", "Instances represented", "number"),
        report_column("weight", "City weight", "decimal"),
        report_column("cache_version", "Cache version", "integer"),
    ];
    let exemplar_rows = plan
        .cities
        .iter()
        .flat_map(|city| &city.exemplars)
        .map(|exemplar| DslReportRow {
            group_id: exemplar.id.clone(),
            values: BTreeMap::from([
                (
                    "households".to_owned(),
                    DslReportValue::Number(exemplar.households as f64),
                ),
                (
                    "people".to_owned(),
                    DslReportValue::Number(exemplar.people as f64),
                ),
                (
                    "instances".to_owned(),
                    DslReportValue::Number(exemplar.instances_represented),
                ),
                (
                    "weight".to_owned(),
                    DslReportValue::Number(exemplar.city_population_share),
                ),
                (
                    "cache_version".to_owned(),
                    DslReportValue::Number(
                        cache
                            .get(&exemplar.id)
                            .map(|entry| entry.version as f64)
                            .unwrap_or(0.0),
                    ),
                ),
            ]),
        })
        .collect();
    vec![
        DslReport {
            id: "city_mixtures".to_owned(),
            title: "City mixture distributions".to_owned(),
            group_by: "city".to_owned(),
            display: "table".to_owned(),
            record: "final".to_owned(),
            columns: city_columns,
            snapshots: vec![DslReportSnapshot {
                tick: ticks,
                rows: city_rows,
            }],
        },
        DslReport {
            id: "neighbourhood_exemplars".to_owned(),
            title: "Neighbourhood exemplars".to_owned(),
            group_by: "exemplar".to_owned(),
            display: "table".to_owned(),
            record: "final".to_owned(),
            columns: exemplar_columns,
            snapshots: vec![DslReportSnapshot {
                tick: ticks,
                rows: exemplar_rows,
            }],
        },
    ]
}

fn report_column(id: &str, label: &str, format: &str) -> ReportColumnDefinition {
    ReportColumnDefinition {
        id: id.to_owned(),
        label: label.to_owned(),
        format: format.to_owned(),
        metric: ReportMetric::Count,
        line: 1,
    }
}

fn cache_invalidation(
    entry: &ExemplarCacheEntry,
    dsl_source_hash: &str,
    seed: u64,
    ticks: u64,
    inputs: &BTreeMap<String, f64>,
    events: &[String],
) -> Option<String> {
    if entry.schema_version != EXEMPLAR_CACHE_SCHEMA_VERSION {
        return Some("cache_schema_changed".to_owned());
    }
    if entry.engine_version != env!("CARGO_PKG_VERSION") {
        return Some("engine_version_changed".to_owned());
    }
    if entry.dsl_source_hash != dsl_source_hash {
        return Some("dsl_hash_changed".to_owned());
    }
    if entry.seed != seed {
        return Some("seed_changed".to_owned());
    }
    if entry.time_window_ticks != ticks {
        return Some("time_window_changed".to_owned());
    }
    if ticks > entry.valid_for_days as u64 * 24 {
        return Some("validity_window_exceeded".to_owned());
    }
    if let Some(event) = events.iter().find(|event| {
        event
            .split_once(':')
            .map_or(true, |(city, _)| city == entry.city_id)
    }) {
        return Some(format!("event:{event}"));
    }
    for (id, value) in inputs {
        let Some((minimum, maximum)) = entry.input_grid.get(id) else {
            return Some(format!("new_input:{id}"));
        };
        if value < minimum || value > maximum {
            return Some(format!("outside_grid:{id}"));
        }
    }
    None
}

fn default_inputs() -> BTreeMap<String, f64> {
    BTreeMap::from([
        ("tax".to_owned(), 0.25),
        ("unemployment".to_owned(), 0.06),
        ("media_trend".to_owned(), 0.0),
        ("price".to_owned(), 1.0),
        ("policy".to_owned(), 0.0),
    ])
}

fn parent_cache_versions(
    program: &Program,
    plan: &ExemplarSystemPlan,
    cache: &BTreeMap<String, ExemplarCacheEntry>,
) -> BTreeMap<String, BTreeMap<String, u64>> {
    let mut dependencies = plan
        .cities
        .iter()
        .map(|city| {
            (
                city.city_id.clone(),
                city.exemplars
                    .iter()
                    .filter_map(|exemplar| {
                        cache
                            .get(&exemplar.id)
                            .map(|entry| (entry.exemplar_id.clone(), entry.version))
                    })
                    .collect::<BTreeMap<_, _>>(),
            )
        })
        .collect::<BTreeMap<_, _>>();
    let mut versions = dependencies
        .iter()
        .map(|(id, children)| (id.clone(), children.values().copied().sum::<u64>()))
        .collect::<BTreeMap<_, _>>();
    for composition in &program.compositions {
        let child_versions = composition
            .entries
            .iter()
            .filter_map(|entry| {
                versions
                    .get(&entry.child)
                    .map(|version| (entry.child.clone(), *version))
            })
            .collect::<BTreeMap<_, _>>();
        if !child_versions.is_empty() {
            versions.insert(
                composition.id.clone(),
                child_versions.values().copied().sum(),
            );
            dependencies.insert(composition.id.clone(), child_versions);
        }
    }
    dependencies
}

fn assign_spotlight_leaders(
    program: &Program,
    plan: &ExemplarSystemPlan,
    cache: &BTreeMap<String, ExemplarCacheEntry>,
    seed: u64,
) -> BTreeMap<String, String> {
    let mut candidates = plan
        .cities
        .iter()
        .flat_map(|city| &city.exemplars)
        .filter_map(|exemplar| cache.get(&exemplar.id))
        .flat_map(|entry| &entry.agents)
        .filter(|agent| agent.age >= 18.0)
        .collect::<Vec<_>>();
    candidates.sort_by_key(|agent| derived_seed(seed, &agent.id));
    let active_physical = plan
        .cities
        .iter()
        .flat_map(|city| &city.residence_path)
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    let mut used = BTreeSet::new();
    let mut assignments = BTreeMap::new();
    for composition in &program.compositions {
        if composition.slice.as_deref() == Some("Physical")
            && !active_physical.contains(composition.id.as_str())
        {
            continue;
        }
        for leader in &composition.leaders {
            let requested = leader
                .count
                .saturating_mul(composition.entity_count.unwrap_or(1) as usize);
            let available = candidates
                .iter()
                .filter(|agent| {
                    !used.contains(&agent.id)
                        && leader_eligible(program, &leader.role, agent)
                        && (composition.slice.as_deref() != Some("Physical")
                            || agent.residence_path.contains(&composition.id))
                })
                .count();
            let count = if available >= requested {
                requested
            } else {
                leader.count.min(available)
            };
            for ordinal in 0..count {
                if let Some(agent) = candidates.iter().find(|agent| {
                    !used.contains(&agent.id)
                        && leader_eligible(program, &leader.role, agent)
                        && (composition.slice.as_deref() != Some("Physical")
                            || agent.residence_path.contains(&composition.id))
                }) {
                    used.insert(agent.id.clone());
                    assignments.insert(
                        format!("{}:{}:{}", composition.id, leader.role, ordinal + 1),
                        agent.id.clone(),
                    );
                }
            }
        }
    }
    assignments
}

fn leader_eligible(program: &Program, role_id: &str, agent: &ExemplarAgentSummary) -> bool {
    let Some(eligibility) = program
        .roles
        .iter()
        .find(|role| role.id == role_id)
        .and_then(|role| role.eligibility.as_ref())
    else {
        return true;
    };
    let values = BTreeMap::from([
        ("age".to_owned(), DslValue::Number(agent.age)),
        ("risk".to_owned(), DslValue::Number(0.8)),
        ("activity".to_owned(), DslValue::Number(0.8)),
    ]);
    evaluate(eligibility, &values)
        .ok()
        .and_then(|value| value.as_bool())
        .unwrap_or(false)
}

fn required_leader_count(program: &Program, plan: &ExemplarSystemPlan) -> usize {
    let active_physical = plan
        .cities
        .iter()
        .flat_map(|city| &city.residence_path)
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    program
        .compositions
        .iter()
        .filter(|composition| {
            composition.slice.as_deref() != Some("Physical")
                || active_physical.contains(composition.id.as_str())
        })
        .flat_map(|composition| {
            composition.leaders.iter().map(|leader| {
                leader
                    .count
                    .saturating_mul(composition.entity_count.unwrap_or(1) as usize)
            })
        })
        .sum()
}

fn derived_seed(seed: u64, key: &str) -> u64 {
    key.as_bytes()
        .iter()
        .fold(seed ^ 0xcbf29ce484222325, |value, byte| {
            (value ^ u64::from(*byte)).wrapping_mul(0x100000001b3)
        })
}
