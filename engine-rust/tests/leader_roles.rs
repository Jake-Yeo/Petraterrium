use petraterrium_engine::text_dsl::{DslReportValue, DslRunResult, parse_program, run_composition};

const SOURCE: &str = include_str!("../dsl/financial_coupling_test.dsl");

fn run(composition: &str, ticks: u64) -> DslRunResult {
    run_composition(parse_program(SOURCE).unwrap(), composition, 1, ticks).unwrap()
}

fn value(result: &DslRunResult, id: &str) -> f64 {
    let value = &result
        .reports
        .iter()
        .find(|report| report.id == "compositions")
        .unwrap()
        .snapshots[0]
        .rows[0]
        .values[id];
    match value {
        DslReportValue::Number(value) => *value,
        value => panic!("expected number, got {value:?}"),
    }
}

#[test]
fn every_declared_leader_instance_has_exactly_one_agent_and_sync_actions() {
    for (composition, role, action, expected_actions) in [
        ("CanadaLeadership", "president", "enact_policy", 1),
        ("TexasLeadership", "governor", "enact_state_policy", 1),
        ("DallasLeadership", "mayor", "set_city_budget", 1),
        ("FirmAlpha", "ceo", "allocate_capital", 1),
        ("BrandLeadership", "brand_manager", "set_brand_policy", 1),
        (
            "FranchiseLeadership",
            "franchise_manager",
            "set_franchise_policy",
            1,
        ),
        ("StoreLeadership", "manager", "set_store_schedule", 2),
        ("CommunityLeadership", "influencer", "post_spotlight", 1),
    ] {
        let result = run(composition, 48);
        assert_eq!(
            result
                .state
                .agents
                .iter()
                .filter(|agent| agent.roles.contains(role))
                .count(),
            1,
            "{composition}:{role}"
        );
        assert_eq!(
            result
                .actions
                .iter()
                .filter(|record| record.action.ends_with(action))
                .count(),
            expected_actions,
            "{composition}:{action}"
        );
    }
}

#[test]
fn duplicate_leader_count_is_rejected_with_a_line_number() {
    let invalid = SOURCE.replacen("    president: count = 1", "    president: count = 2", 1);
    let error = parse_program(&invalid).unwrap_err();
    assert_eq!(error.code, "LEADER_COUNT_MISMATCH");
    assert!(error.line > 0);
}

#[test]
fn leader_parameters_are_isolated_to_their_declared_subtree() {
    let texas_before = run("TexasLeadership", 0);
    let california_before = run("CaliforniaLeadership", 0);
    let changed_source = SOURCE.replacen("policy_effect = 0.20", "policy_effect = 0.80", 1);
    let texas_after = run_composition(
        parse_program(&changed_source).unwrap(),
        "TexasLeadership",
        1,
        0,
    )
    .unwrap();
    let california_after = run_composition(
        parse_program(&changed_source).unwrap(),
        "CaliforniaLeadership",
        1,
        0,
    )
    .unwrap();
    assert_ne!(
        value(&texas_before, "policy_effect"),
        value(&texas_after, "policy_effect")
    );
    assert_eq!(
        value(&california_before, "policy_effect"),
        value(&california_after, "policy_effect")
    );
}
