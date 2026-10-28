use petraterrium_engine::text_dsl::{
    configure_pool_run, parse_program, pool_run_summary, run_composition,
};
use std::collections::{BTreeMap, BTreeSet};

const SOURCE: &str = include_str!("../dsl/default.dsl");

fn configured(total: u64, detail: &str) -> petraterrium_engine::text_dsl::Program {
    let mut program = parse_program(SOURCE).unwrap();
    configure_pool_run(&mut program, "Petraterrium", total, Some(detail)).unwrap();
    program
}

#[test]
fn one_pool_has_complete_household_residence_life_stage_and_leader_roles() {
    let program = configured(6_999_999_999, "medium");
    let initial = run_composition(program.clone(), "Petraterrium", 1, 0).unwrap();
    let result = run_composition(program.clone(), "Petraterrium", 1, 2).unwrap();
    assert_eq!(initial.state.agents.len(), result.state.agents.len());
    assert_eq!(result.state.agents.len(), 291);
    let summary = pool_run_summary(&program, &result.state);
    assert_eq!(summary.total_represented_pool, 6_999_999_999);
    assert_eq!(summary.unique_represented_agents, 6_999_999_999);
    assert_eq!(summary.simulated_pool_sample, 291);
    assert_eq!(summary.unassigned_required_roles, 0);
    assert!(summary.role_shortfalls.values().all(|count| *count == 0));
    assert!(summary.explicit_neither.values().all(|count| *count > 0));
    assert!(summary.role_membership["redditor"] > 0);
    assert!(summary.role_membership["cashier"] > 0);
    assert!(summary.role_membership["trader"] > 0);
    let groups = program.role_distributions.iter().fold(
        BTreeMap::<&str, (BTreeSet<&str>, &str)>::new(),
        |mut values, distribution| {
            let entry = values
                .entry(distribution.group.as_str())
                .or_insert_with(|| (BTreeSet::new(), distribution.otherwise.as_str()));
            entry.0.insert(distribution.role.as_str());
            values
        },
    );
    for agent in &result.state.agents {
        for (roles, otherwise) in groups.values() {
            assert!(
                roles.iter().any(|role| agent.roles.contains(*role))
                    || agent.roles.contains(*otherwise)
            );
        }
    }
    let mut heads = BTreeMap::<&str, usize>::new();
    for agent in &result.state.agents {
        if agent.roles.contains("head") {
            *heads.entry(&agent.household_id).or_default() += 1;
        }
        assert!(agent.roles.contains("household_member"));
        assert!(
            agent
                .roles
                .iter()
                .any(|role| role.starts_with("resident_country_"))
        );
        assert!(agent.roles.iter().any(|role| role.starts_with("life_")));
        let age = agent.value("age").unwrap().as_f64().unwrap();
        if agent.roles.contains("cashier") {
            assert!(age >= 18.0);
        }
        if agent.roles.contains("trader") {
            assert!(age >= 18.0);
            assert!(agent.value("risk").unwrap().as_f64().unwrap() >= 0.4);
        }
        if agent.roles.contains("redditor") {
            assert!(age >= 13.0);
            assert!(agent.value("interest").unwrap().as_f64().unwrap() >= 0.3);
        }
    }
    let households = result
        .state
        .agents
        .iter()
        .map(|agent| agent.household_id.as_str())
        .collect::<BTreeSet<_>>();
    assert_eq!(heads.len(), households.len());
    assert!(heads.values().all(|count| *count == 1));
    let agents = result
        .state
        .agents
        .iter()
        .map(|agent| (agent.id.as_str(), agent))
        .collect::<BTreeMap<_, _>>();
    for relationship in &result.state.relationships {
        if relationship.kind == "parent" {
            let parent = agents[relationship.source_id.as_str()];
            let child = agents[relationship.target_id.as_str()];
            assert!(parent.value("age").unwrap().as_f64().unwrap() >= 18.0);
            assert!(child.value("age").unwrap().as_f64().unwrap() < 18.0);
            assert_eq!(parent.household_id, child.household_id);
        }
        if relationship.kind == "spouse" {
            assert_eq!(
                agents[relationship.source_id.as_str()].household_id,
                agents[relationship.target_id.as_str()].household_id
            );
        }
        if relationship.kind == "leader" {
            assert!(
                !agents[relationship.source_id.as_str()]
                    .roles
                    .contains("life_child")
            );
        }
    }
    let expected_leaders = program
        .compositions
        .iter()
        .flat_map(|composition| &composition.leaders)
        .map(|leader| leader.count)
        .sum::<usize>();
    assert_eq!(summary.leader_assignments.len(), expected_leaders);
    let conflict_by_role = program
        .roles
        .iter()
        .filter_map(|role| {
            role.conflict_group
                .as_deref()
                .map(|group| (role.id.as_str(), group))
        })
        .collect::<BTreeMap<_, _>>();
    let mut occupied = BTreeSet::new();
    for relationship in result
        .state
        .relationships
        .iter()
        .filter(|relationship| relationship.kind == "leader")
    {
        let role = relationship.target_id.rsplit(':').next().unwrap();
        let group = conflict_by_role[role];
        assert!(occupied.insert((relationship.source_id.as_str(), group)));
    }
}

#[test]
fn role_groups_require_an_explicit_otherwise_outcome() {
    let invalid = SOURCE.replacen("  otherwise = media_neither\n", "", 1);
    let error = parse_program(&invalid).unwrap_err();
    assert_eq!(error.code, "MISSING_ROLE_GROUP_OTHERWISE");
}

#[test]
fn role_group_explicit_outcomes_cannot_exceed_one() {
    let invalid = SOURCE
        .replacen(
            "represented_users = 8000000",
            "represented_users = 6000000000",
            1,
        )
        .replacen(
            "represented_users = 4000000",
            "represented_users = 4000000000",
            1,
        );
    let error = parse_program(&invalid).unwrap_err();
    assert_eq!(error.code, "ROLE_GROUP_PROBABILITIES_NOT_ONE");
}

#[test]
fn pool_run_is_deterministic_for_seed_total_and_detail() {
    let program = configured(8_000_000_000, "low");
    let first = run_composition(program.clone(), "Petraterrium", 17, 2).unwrap();
    let second = run_composition(program, "Petraterrium", 17, 2).unwrap();
    assert_eq!(first, second);
}

#[test]
fn default_program_has_no_causal_composition_flows_or_couplings() {
    let program = parse_program(SOURCE).unwrap();
    assert!(program.compositions.iter().all(|composition| {
        composition.flows.is_empty()
            && composition.couplings.is_empty()
            && composition.boundaries.is_empty()
    }));
}

#[test]
fn agent_actions_drive_leadership_trade_migration_and_payout_statistics() {
    let source = SOURCE.replace("record_actions = false", "record_actions = true");
    let mut program = parse_program(&source).unwrap();
    configure_pool_run(&mut program, "Petraterrium", 6_999_999_999, Some("medium")).unwrap();
    let result = run_composition(program, "Petraterrium", 1, 30 * 24).unwrap();
    let actions = result
        .actions
        .iter()
        .map(|record| record.action.rsplit("__").next().unwrap())
        .collect::<BTreeSet<_>>();
    assert!(actions.contains("diplomatic_summit"), "{actions:?}");
    assert!(actions.contains("secondary_buy") || actions.contains("secondary_sell"));
    assert!(actions.contains("migrate_household"));
    assert!(actions.contains("owner_payout"));
    for agent in result.state.agents.iter().filter(|agent| {
        agent
            .value("residence_change")
            .and_then(|value| value.as_f64())
            .is_some_and(|value| value > 0.0)
    }) {
        for prefix in [
            "resident_country_",
            "resident_division_",
            "resident_municipality_",
            "resident_neighbourhood_",
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
        assert!(agent.household_id.starts_with("relocated_household-"));
    }
    assert!(SOURCE.contains("effect self.money += 10"));
    assert!(SOURCE.contains("effect place Store cash -= 10"));
}
