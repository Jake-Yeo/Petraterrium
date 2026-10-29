use petraterrium_engine::text_dsl::{
    ExemplarCacheEntry, Program, parse_program, plan_exemplars, restrict_program_to_city,
    run_exemplar_system,
};
use std::collections::{BTreeMap, BTreeSet};

const SOURCE: &str = include_str!("../dsl/default.dsl");

fn lytton_program() -> Program {
    let mut program = parse_program(SOURCE).unwrap();
    retain_children(&mut program, "World", &["Canada"]);
    retain_children(&mut program, "Canada", &["BritishColumbia"]);
    retain_children(&mut program, "BritishColumbia", &["Lytton"]);
    let store = program
        .compositions
        .iter_mut()
        .find(|composition| composition.id == "BerkshireRetailStore")
        .unwrap();
    store.entity_count = Some(1);
    store.role_targets.insert("store_manager".to_owned(), 1);
    program
}

fn toronto_and_lytton_program() -> Program {
    let mut program = parse_program(SOURCE).unwrap();
    retain_children(&mut program, "World", &["Canada"]);
    retain_children(&mut program, "Canada", &["Ontario", "BritishColumbia"]);
    retain_children(&mut program, "Ontario", &["Toronto"]);
    retain_children(&mut program, "BritishColumbia", &["Lytton"]);
    program
}

fn retain_children(program: &mut Program, parent: &str, children: &[&str]) {
    let composition = program
        .compositions
        .iter_mut()
        .find(|composition| composition.id == parent)
        .unwrap();
    composition
        .entries
        .retain(|entry| children.contains(&entry.child.as_str()));
    for entry in &mut composition.entries {
        entry.weight = Some(1.0);
    }
}

#[test]
fn every_exemplar_has_complete_fifty_to_one_hundred_households() {
    let program = parse_program(SOURCE).unwrap();
    let plan = plan_exemplars(&program, 6_999_999_999, 1).unwrap();
    assert!(plan.total_exemplars > plan.cities.len());
    for exemplar in plan.cities.iter().flat_map(|city| &city.exemplars) {
        assert!((50..=100).contains(&exemplar.households));
        assert_eq!(
            exemplar.household_allocations.values().sum::<u32>(),
            exemplar.households
        );
        assert!(exemplar.people >= exemplar.households as usize * 2);
        assert!(
            (exemplar.instances_represented * exemplar.people as f64
                - exemplar.represented_people as f64)
                .abs()
                < 1.0
        );
    }
}

#[test]
fn exemplar_weights_conserve_every_city_and_world_at_all_totals() {
    let program = parse_program(SOURCE).unwrap();
    let plans = [6_999_999_999_u64, 8_000_000_000, 2_000_000_000]
        .map(|total| plan_exemplars(&program, total, 1).unwrap());
    let identities = plans[0]
        .cities
        .iter()
        .flat_map(|city| &city.exemplars)
        .map(|exemplar| (exemplar.id.clone(), exemplar.households))
        .collect::<Vec<_>>();
    for plan in &plans {
        assert_eq!(
            plan.cities
                .iter()
                .map(|city| city.represented_people)
                .sum::<u64>(),
            plan.total_represented_pool
        );
        for (parent, children) in [
            ("Canada", vec!["Ontario", "BritishColumbia"]),
            ("USA", vec!["California", "Texas"]),
            ("Mexico", vec!["CentralMexico", "NorthernMexico"]),
            ("World", vec!["Canada", "USA", "Mexico"]),
        ] {
            assert_eq!(
                plan.hierarchy_counts[parent],
                children
                    .iter()
                    .map(|child| plan.hierarchy_counts[*child])
                    .sum::<u64>()
            );
        }
        for city in &plan.cities {
            assert_eq!(
                city.exemplars
                    .iter()
                    .map(|exemplar| exemplar.represented_people)
                    .sum::<u64>(),
                city.represented_people
            );
            assert!(
                (city
                    .exemplars
                    .iter()
                    .map(|value| value.city_population_share)
                    .sum::<f64>()
                    - 1.0)
                    .abs()
                    < 1e-9
            );
        }
        assert_eq!(
            identities,
            plan.cities
                .iter()
                .flat_map(|city| &city.exemplars)
                .map(|exemplar| (exemplar.id.clone(), exemplar.households))
                .collect::<Vec<_>>()
        );
    }
    assert_ne!(
        plans[0].cities[0].exemplars[0].instances_represented,
        plans[1].cities[0].exemplars[0].instances_represented
    );
}

#[test]
fn cities_have_path_specific_stratified_exemplars_and_convergence_reports() {
    let program = parse_program(SOURCE).unwrap();
    let plan = plan_exemplars(&program, 6_999_999_999, 1).unwrap();
    let city_ids = plan
        .cities
        .iter()
        .map(|city| city.city_id.as_str())
        .collect::<BTreeSet<_>>();
    for city in [
        "Toronto",
        "Vancouver",
        "Lytton",
        "LosAngeles",
        "Houston",
        "MexicoCity",
        "Monterrey",
    ] {
        assert!(city_ids.contains(city), "{city}");
    }
    let all_ids = plan
        .cities
        .iter()
        .flat_map(|city| &city.exemplars)
        .map(|exemplar| exemplar.id.as_str())
        .collect::<Vec<_>>();
    assert_eq!(
        all_ids.iter().copied().collect::<BTreeSet<_>>().len(),
        all_ids.len()
    );
    let lytton = plan
        .cities
        .iter()
        .find(|city| city.city_id == "Lytton")
        .unwrap();
    assert_eq!(lytton.exemplars.len(), 1);
    assert_eq!(lytton.distribution_status, "fallback");
    assert!(
        lytton
            .exemplars
            .iter()
            .all(|exemplar| exemplar.distribution_status == "fallback")
    );
    let los_angeles = plan
        .cities
        .iter()
        .find(|city| city.city_id == "LosAngeles")
        .unwrap();
    assert!(
        los_angeles
            .exemplars
            .iter()
            .all(|exemplar| exemplar.distribution_status == "inherited")
    );
    let toronto = plan
        .cities
        .iter()
        .find(|city| city.city_id == "Toronto")
        .unwrap();
    assert!(toronto.exemplars.len() > lytton.exemplars.len());
    assert!(plan.cities.iter().all(|city| {
        city.convergence.converged || (city.convergence.cap_hit && city.exemplars.len() == 50)
    }));
}

#[test]
fn city_debug_run_keeps_only_the_requested_city_path() {
    let mut program = parse_program(SOURCE).unwrap();
    restrict_program_to_city(&mut program, "Vancouver").unwrap();
    let plan = plan_exemplars(&program, 2_000_000_000, 1).unwrap();
    assert_eq!(plan.cities.len(), 1);
    assert_eq!(plan.cities[0].city_id, "Vancouver");
    assert_eq!(plan.cities[0].represented_people, 2_000_000_000);
}

#[test]
fn detailed_learning_assigns_each_person_to_one_exemplar_and_household() {
    let program = lytton_program();
    let run = run_exemplar_system(
        program.clone(),
        6_999_999_999,
        1,
        0,
        "sha256:test",
        BTreeMap::new(),
        &BTreeMap::new(),
        &[],
    )
    .unwrap();
    assert!(run.cache_stats.mass_agent_ticks == 0);
    assert!(
        run.plan
            .cities
            .iter()
            .all(|city| city.convergence.converged || city.convergence.cap_hit)
    );
    for city in &run.plan.cities {
        for exemplar in &city.exemplars {
            let cache = &run.cache[&exemplar.id];
            assert_eq!(cache.agents.len(), exemplar.people);
            let households = cache
                .agents
                .iter()
                .map(|agent| agent.household_id.as_str())
                .collect::<BTreeSet<_>>();
            assert_eq!(households.len(), exemplar.households as usize);
            let mut heads = BTreeMap::<&str, usize>::new();
            for agent in &cache.agents {
                assert!(!agent.roles.is_empty());
                assert_eq!(
                    agent
                        .roles
                        .iter()
                        .filter(|role| role.starts_with("resident_neighbourhood_"))
                        .count(),
                    1
                );
                for prefix in [
                    "resident_country_",
                    "resident_division_",
                    "resident_municipality_",
                ] {
                    assert_eq!(
                        agent
                            .roles
                            .iter()
                            .filter(|role| role.starts_with(prefix))
                            .count(),
                        1
                    );
                }
                if agent.roles.iter().any(|role| role == "head") {
                    *heads.entry(&agent.household_id).or_default() += 1;
                }
            }
            assert_eq!(heads.len(), households.len());
            assert!(heads.values().all(|count| *count == 1));
        }
    }
    assert_eq!(run.unassigned_required_roles, 0);
}

#[test]
fn exemplar_cache_hits_and_selective_relearn_are_branch_local() {
    let program = toronto_and_lytton_program();
    let learned = run_exemplar_system(
        program.clone(),
        6_999_999_999,
        1,
        1,
        "sha256:test",
        BTreeMap::new(),
        &BTreeMap::new(),
        &[],
    )
    .unwrap();
    assert!(!learned.cache_stats.cache_hit);
    assert!(learned.cache_stats.mass_agent_ticks > 0);
    let agent_ids = learned
        .cache
        .values()
        .flat_map(|entry| entry.agents.iter().map(|agent| agent.id.as_str()))
        .collect::<Vec<_>>();
    assert_eq!(
        agent_ids.iter().copied().collect::<BTreeSet<_>>().len(),
        agent_ids.len()
    );
    let cached = run_exemplar_system(
        program.clone(),
        6_999_999_999,
        1,
        1,
        "sha256:test",
        learned.cache.clone(),
        &BTreeMap::new(),
        &[],
    )
    .unwrap();
    assert!(cached.cache_stats.cache_hit);
    assert_eq!(cached.cache_stats.mass_agent_ticks, 0);
    assert_eq!(learned.plan, cached.plan);
    assert_eq!(
        learned
            .cache
            .iter()
            .map(|(id, entry)| (id, &entry.metrics))
            .collect::<BTreeMap<_, _>>(),
        cached
            .cache
            .iter()
            .map(|(id, entry)| (id, &entry.metrics))
            .collect::<BTreeMap<_, _>>()
    );
    let exemplar_id = cached.plan.cities[0].exemplars[0].id.clone();
    assert_eq!(cached.cache[&exemplar_id].grid_points.len(), 3);
    let interpolated_inputs = BTreeMap::from([(
        exemplar_id.clone(),
        BTreeMap::from([("price".to_owned(), 1.5)]),
    )]);
    let interpolated = run_exemplar_system(
        program.clone(),
        6_999_999_999,
        1,
        1,
        "sha256:test",
        cached.cache.clone(),
        &interpolated_inputs,
        &[],
    )
    .unwrap();
    assert!(interpolated.cache_stats.cache_hit);
    assert_eq!(interpolated.cache_stats.mass_agent_ticks, 0);
    assert_eq!(interpolated.cache[&exemplar_id].inputs["price"], 1.5);
    let changed_inputs = BTreeMap::from([(
        exemplar_id.clone(),
        BTreeMap::from([("price".to_owned(), 3.0)]),
    )]);
    let relearned = run_exemplar_system(
        program,
        6_999_999_999,
        1,
        1,
        "sha256:test",
        interpolated.cache.clone(),
        &changed_inputs,
        &[],
    )
    .unwrap();
    assert_eq!(relearned.cache_stats.relearned_exemplars, vec![exemplar_id]);
    assert_eq!(relearned.cache_stats.mass_agent_ticks > 0, true);
    assert_ne!(
        cached.cache[&relearned.cache_stats.relearned_exemplars[0]].metrics["money"].mean,
        relearned.cache[&relearned.cache_stats.relearned_exemplars[0]].metrics["money"].mean
    );
    let changed_city = &relearned.plan.cities[0].city_id;
    assert_ne!(
        cached.cache_stats.parent_cache_versions[changed_city],
        relearned.cache_stats.parent_cache_versions[changed_city]
    );
    for city in relearned.plan.cities.iter().skip(1) {
        assert_eq!(
            cached.cache_stats.parent_cache_versions[&city.city_id],
            relearned.cache_stats.parent_cache_versions[&city.city_id]
        );
    }
    assert!(relearned.cache_stats.feedback_iterations <= 5);
    assert!(relearned.cache_stats.feedback_final_change < 0.01);
    let event_relearn = run_exemplar_system(
        toronto_and_lytton_program(),
        6_999_999_999,
        1,
        1,
        "sha256:test",
        relearned.cache.clone(),
        &BTreeMap::new(),
        &["Toronto:policy_change".to_owned()],
    )
    .unwrap();
    assert!(
        event_relearn
            .cache_stats
            .relearned_exemplars
            .iter()
            .all(|id| id.starts_with("Toronto__"))
    );
    assert_eq!(
        event_relearn.cache_stats.relearned_exemplars.len(),
        event_relearn
            .plan
            .cities
            .iter()
            .find(|city| city.city_id == "Toronto")
            .unwrap()
            .exemplars
            .len()
    );
    let hash_changed = run_exemplar_system(
        toronto_and_lytton_program(),
        6_999_999_999,
        1,
        1,
        "sha256:changed",
        event_relearn.cache,
        &BTreeMap::new(),
        &[],
    )
    .unwrap();
    assert_eq!(
        hash_changed.cache_stats.relearned_exemplars.len(),
        hash_changed.plan.total_exemplars
    );
    assert!(
        hash_changed
            .cache_stats
            .invalidations
            .values()
            .all(|reason| reason == "dsl_hash_changed")
    );
}

#[test]
fn child_clock_must_divide_parent_sync() {
    let invalid = SOURCE.replacen("sync_up = 7 days", "sync_up = 25 minutes", 1);
    let error = parse_program(&invalid).unwrap_err();
    assert_eq!(error.code, "CLOCK_SYNC_MISMATCH");
    assert!(error.line > 0);
}

#[test]
fn cache_entry_type_is_stable_for_persistence() {
    let value = serde_json::from_str::<BTreeMap<String, ExemplarCacheEntry>>("{}").unwrap();
    assert!(value.is_empty());
}

#[test]
fn stale_exemplar_cache_schema_relearns_only_the_stale_entry() {
    let program = lytton_program();
    let learned = run_exemplar_system(
        program.clone(),
        6_999_999_999,
        1,
        0,
        "sha256:test",
        BTreeMap::new(),
        &BTreeMap::new(),
        &[],
    )
    .unwrap();
    let stale_id = learned.plan.cities[0].exemplars[0].id.clone();
    let mut stale_cache = learned.cache;
    stale_cache.get_mut(&stale_id).unwrap().schema_version = 0;
    let relearned = run_exemplar_system(
        program,
        6_999_999_999,
        1,
        0,
        "sha256:test",
        stale_cache,
        &BTreeMap::new(),
        &[],
    )
    .unwrap();
    assert_eq!(
        relearned.cache_stats.relearned_exemplars,
        vec![stale_id.clone()]
    );
    assert_eq!(
        relearned.cache_stats.invalidations[&stale_id],
        "cache_schema_changed"
    );
    assert_eq!(relearned.unassigned_required_roles, 0);
}

#[test]
fn composed_run_ticks_boundary_and_spotlight_agents_only() {
    let mut program = lytton_program();
    program
        .compositions
        .iter_mut()
        .find(|composition| composition.id == "Lytton")
        .unwrap()
        .sync_up_minutes = Some(60);
    let run = run_exemplar_system(
        program.clone(),
        6_999_999_999,
        1,
        24,
        "sha256:test",
        BTreeMap::new(),
        &BTreeMap::new(),
        &[],
    )
    .unwrap();
    let actions = run
        .result
        .reports
        .iter()
        .find(|report| report.id == "boundary_agent_actions")
        .unwrap()
        .snapshots[0]
        .rows
        .iter()
        .map(|row| row.group_id.as_str())
        .collect::<BTreeSet<_>>();
    for expected in [
        "migrate_household",
        "commute_boundary",
        "secondary_buy",
        "media_post",
        "diplomatic_summit",
        "owner_payout",
    ] {
        assert!(actions.contains(expected), "{expected}: {actions:?}");
    }
    assert!(run.result.actions.is_empty());
    let logical_agents = run
        .cache
        .values()
        .flat_map(|entry| entry.agents.iter().map(|agent| agent.id.as_str()))
        .collect::<BTreeSet<_>>();
    assert!(
        run.result
            .state
            .agents
            .iter()
            .all(|agent| logical_agents.contains(agent.id.as_str()))
    );
    assert_eq!(
        run.result
            .state
            .agents
            .iter()
            .map(|agent| agent.id.as_str())
            .collect::<BTreeSet<_>>()
            .len(),
        run.result.state.agents.len()
    );
    let migrant = run
        .result
        .state
        .agents
        .iter()
        .find(|agent| agent.roles.contains("migrant"))
        .unwrap();
    assert!(migrant.household_id.starts_with("relocated_household-"));
    assert_eq!(
        migrant
            .value("residence_change")
            .and_then(|value| value.as_f64()),
        Some(1.0)
    );
    assert!(run.cache_stats.feedback_iterations > 0);
    assert!(run.cache_stats.feedback_final_change < 0.01);
    assert!(run.cache_stats.feedback_inputs.contains_key("Lytton"));
    let cached = run_exemplar_system(
        program,
        6_999_999_999,
        1,
        24,
        "sha256:test",
        run.cache.clone(),
        &BTreeMap::new(),
        &[],
    )
    .unwrap();
    assert!(cached.cache_stats.cache_hit);
    assert_eq!(run.plan, cached.plan);
    assert_eq!(run.result.reports, cached.result.reports);
}
