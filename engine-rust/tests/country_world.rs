use petraterrium_engine::text_dsl::{
    CachedCompositionEvaluationResult, CachedCompositionProtocolRequest, CompositionCacheMetadata,
    DslReport, DslReportValue, DslRunResult, LearnedAggregateArtifact, ScheduledAggregateInputs,
    evaluate_cached_composition, parse_program, run_composition,
};
use std::collections::{BTreeMap, BTreeSet};

const SOURCE: &str = include_str!("../dsl/country_world_test.dsl");

fn hash(source: &str) -> String {
    let value = source
        .as_bytes()
        .iter()
        .fold(0xcbf29ce484222325_u64, |hash, byte| {
            (hash ^ u64::from(*byte)).wrapping_mul(0x100000001b3)
        });
    format!("test:{value:016x}")
}

fn request(
    source: &str,
    function_id: &str,
    days: u32,
    artifacts: BTreeMap<String, LearnedAggregateArtifact>,
) -> CachedCompositionProtocolRequest {
    CachedCompositionProtocolRequest {
        source: source.to_owned(),
        dsl_source_hash: hash(source),
        function_id: function_id.to_owned(),
        seed: 1,
        days,
        evaluated_at_day: 0,
        inputs: BTreeMap::new(),
        branch_inputs: BTreeMap::new(),
        input_schedule: Vec::new(),
        events: BTreeSet::new(),
        artifacts,
        force_relearn: false,
    }
}

fn evaluate(
    source: &str,
    request: CachedCompositionProtocolRequest,
) -> CachedCompositionEvaluationResult {
    evaluate_cached_composition(parse_program(source).unwrap(), request).unwrap()
}

fn pure_source() -> String {
    let mut source = SOURCE
        .lines()
        .filter(|line| line.trim() != "effects:" && !line.trim_start().starts_with("field "))
        .map(|line| {
            if let (Some(rate), Some(effect)) =
                (line.find(" rate = "), line.find(" effect = transfer"))
            {
                format!("{} rate = 0.0{}", &line[..rate], &line[effect..])
            } else {
                line.to_owned()
            }
        })
        .collect::<Vec<_>>()
        .join("\n");
    source.push('\n');
    source
        .replace("max_iterations = 5", "max_iterations = 1")
        .replace("max_iterations = 2", "max_iterations = 1")
}

fn metadata<'a>(tree: &'a CompositionCacheMetadata, id: &str) -> &'a CompositionCacheMetadata {
    find_metadata(tree, id).unwrap()
}

fn find_metadata<'a>(
    tree: &'a CompositionCacheMetadata,
    id: &str,
) -> Option<&'a CompositionCacheMetadata> {
    if tree.function_id == id {
        return Some(tree);
    }
    tree.children
        .iter()
        .find_map(|child| find_metadata(child, id))
}

fn report<'a>(result: &'a CachedCompositionEvaluationResult, id: &str) -> &'a DslReport {
    result
        .reports
        .iter()
        .find(|report| report.id == id)
        .unwrap()
}

fn run_report<'a>(result: &'a DslRunResult, id: &str) -> &'a DslReport {
    result
        .reports
        .iter()
        .find(|report| report.id == id)
        .unwrap()
}

fn number(value: &DslReportValue) -> f64 {
    match value {
        DslReportValue::Number(value) => *value,
        _ => panic!("expected number"),
    }
}

fn output(result: &CachedCompositionEvaluationResult, id: &str) -> f64 {
    result.time_series.last().unwrap().outputs[id].mean
}

fn flow_value(result: &CachedCompositionEvaluationResult, id: &str, field: &str) -> f64 {
    let flow = report(result, "composition_flows")
        .snapshots
        .iter()
        .flat_map(|snapshot| &snapshot.rows)
        .find(|row| row.group_id == id)
        .unwrap();
    number(&flow.values[field])
}

fn detailed_value(result: &DslRunResult, id: &str) -> f64 {
    let row = &run_report(result, "compositions").snapshots[0].rows[0];
    number(&row.values[id])
}

#[test]
fn parser_templates_and_fixed_budget_use_the_generic_composition_path() {
    let program = parse_program(SOURCE).unwrap();
    assert_eq!(program.composition_archetypes.len(), 1);
    for id in ["NationA", "NationB", "FictionalNation"] {
        let country = program
            .compositions
            .iter()
            .find(|composition| composition.id == id)
            .unwrap();
        assert_eq!(country.template.as_deref(), Some("GenericFederation"));
        assert_eq!(country.parameters["federal_strength"], 0.70);
    }
    for id in ["Province", "NationA", "FictionalNation", "TestWorld"] {
        let result = run_composition(program.clone(), id, 1, 0).unwrap();
        assert_eq!(result.state.agents.len(), 20, "{id}");
    }

    let unknown_child = SOURCE.replacen(
        "    Province: weight = 60",
        "    MissingDivision: weight = 60",
        1,
    );
    let error = parse_program(&unknown_child).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_COMPOSITION_CHILD");
    assert!(error.line > 0);

    let unknown_flow = SOURCE.replacen(
        "trade_a_b NationA -> NationB",
        "trade_a_b NationA -> MissingNation",
        1,
    );
    let error = parse_program(&unknown_flow).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_COMPOSITION_FLOW_CHILD");
    assert!(error.line > 0);

    let forward_flow = SOURCE.replacen(
        "0.08 + NationA_gdp_proxy / 10000",
        "policy_a_b + NationA_gdp_proxy / 10000",
        1,
    );
    let error = parse_program(&forward_flow).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_COMPOSITION_FLOW_VALUE");
    assert!(error.line > 0);

    let bad_sync = SOURCE.replacen("    sync = 90 days", "    sync = 31 days", 1);
    let error = parse_program(&bad_sync).unwrap_err();
    assert_eq!(error.code, "INCOMPATIBLE_COMPOSITION_SYNC");
    assert!(error.line > 0);
}

#[test]
fn weighted_countries_world_and_template_instances_match_hand_calculation() {
    let source = pure_source();
    let mut province_request = request(&source, "Province", 1, BTreeMap::new());
    province_request.inputs =
        BTreeMap::from([("tax".to_owned(), 0.20), ("unemployment".to_owned(), 0.08)]);
    let province = evaluate(&source, province_request.clone());
    province_request.function_id = "ProvinceAlt".to_owned();
    let province_alt = evaluate(&source, province_request);
    let nation_a = evaluate(&source, request(&source, "NationA", 1, BTreeMap::new()));
    let nation_b = evaluate(&source, request(&source, "NationB", 1, BTreeMap::new()));
    let fictional = evaluate(
        &source,
        request(&source, "FictionalNation", 1, BTreeMap::new()),
    );
    let world = evaluate(&source, request(&source, "TestWorld", 1, BTreeMap::new()));

    assert!((output(&province, "mean_income") - 20.75).abs() < 1e-9);
    assert!((output(&province_alt, "mean_income") - 30.25).abs() < 1e-9);
    assert!(
        (output(&nation_a, "mean_income") - 24.55).abs() < 1e-9,
        "NationA {}",
        output(&nation_a, "mean_income")
    );
    assert!(
        (output(&nation_b, "mean_income") - 28.35).abs() < 1e-9,
        "NationB {}",
        output(&nation_b, "mean_income")
    );
    assert!(
        (output(&fictional, "mean_income") - 25.50).abs() < 1e-9,
        "FictionalNation {}",
        output(&fictional, "mean_income")
    );
    assert!(
        (output(&world, "mean_income") - 26.07).abs() < 1e-9,
        "TestWorld {}",
        output(&world, "mean_income")
    );
    assert_ne!(
        output(&nation_a, "mean_income"),
        output(&nation_b, "mean_income")
    );
    assert_ne!(
        output(&nation_b, "mean_income"),
        output(&fictional, "mean_income")
    );
}

#[test]
fn generic_flows_cover_exchange_transfer_travel_infection_and_sparse_adjacency() {
    let baseline = evaluate(SOURCE, request(SOURCE, "TestWorld", 1, BTreeMap::new()));
    let baseline_trade = flow_value(&baseline, "TestWorld:trade_a_b", "rate");
    assert!(baseline_trade > 0.0);
    assert!(flow_value(&baseline, "TestWorld:migration_a_b", "rate") > 0.0);
    assert!(flow_value(&baseline, "TestWorld:travel_a_b", "rate") > 0.0);
    assert!(flow_value(&baseline, "TestWorld:infection_a_b", "rate") > 0.0);
    assert!(flow_value(&baseline, "TestWorld:policy_a_b", "rate") > 0.0);

    let mut blocked_request = request(SOURCE, "TestWorld", 1, baseline.artifacts.clone());
    blocked_request.inputs.insert("tariff".to_owned(), 1.0);
    let blocked = evaluate(SOURCE, blocked_request);
    assert!(flow_value(&blocked, "TestWorld:trade_a_b", "rate") < baseline_trade);
    assert!(flow_value(&blocked, "TestWorld:trade_a_b", "rate") < 0.01);

    let no_travel_source = SOURCE.replacen(
        "travel_a_b NationA -> NationB rate = formula(clamp(0.04 + global_policy * 0.04, 0, 0.20))",
        "travel_a_b NationA -> NationB rate = 0.0",
        1,
    );
    let no_travel = evaluate(
        &no_travel_source,
        request(&no_travel_source, "TestWorld", 1, BTreeMap::new()),
    );
    assert_eq!(
        flow_value(&no_travel, "TestWorld:infection_a_b", "rate"),
        0.0
    );

    let network = evaluate(SOURCE, request(SOURCE, "NetworkWorld", 1, BTreeMap::new()));
    let rows = report(&network, "composition_flows")
        .snapshots
        .iter()
        .flat_map(|snapshot| &snapshot.rows)
        .collect::<Vec<_>>();
    assert!(
        rows.iter()
            .any(|row| row.group_id == "NetworkWorld:adjacent_trade")
    );
    assert!(rows.iter().all(|row| {
        row.group_id != "NetworkWorld:adjacent_trade" || number(&row.values["rate"]) > 0.0
    }));
    assert!(rows.iter().all(|row| {
        row.group_id != "NetworkWorld:adjacent_trade"
            || row.values["source"] == DslReportValue::Text("NationA".to_owned())
                && row.values["target"] == DslReportValue::Text("NationB".to_owned())
    }));

    let non_adjacent = SOURCE.replacen(
        "    adjacent_trade NationA -> NationB rate = formula(clamp(0.10 - tariff * 0.20, 0, 0.40)) effect = exchange",
        "    adjacent_trade NationA -> NationB rate = formula(clamp(0.10 - tariff * 0.20, 0, 0.40)) effect = exchange\n    forbidden_direct NationA -> FictionalNation rate = 0.1 effect = exchange",
        1,
    );
    let error = parse_program(&non_adjacent).unwrap_err();
    assert_eq!(error.code, "NON_ADJACENT_COMPOSITION_FLOW");
    assert!(error.line > 0);
}

#[test]
fn detailed_boundary_transfer_preserves_agents_traits_and_relationships() {
    let no_migration = SOURCE.replacen(
        "migration_a_b NationA -> NationB rate = formula(clamp(0.01 + NationB_mean_income / 1000 - NationB_unemployment * 0.10 - border_policy * 0.01, 0, 0.20))",
        "migration_a_b NationA -> NationB rate = 0.0",
        1,
    );
    let full_migration = SOURCE.replacen(
        "migration_a_b NationA -> NationB rate = formula(clamp(0.01 + NationB_mean_income / 1000 - NationB_unemployment * 0.10 - border_policy * 0.01, 0, 0.20))",
        "migration_a_b NationA -> NationB rate = 0.5",
        1,
    );
    let before = run_composition(parse_program(&no_migration).unwrap(), "TestWorld", 1, 0).unwrap();
    let after =
        run_composition(parse_program(&full_migration).unwrap(), "TestWorld", 1, 0).unwrap();
    let before_agents = before
        .state
        .agents
        .iter()
        .map(|agent| {
            (
                agent.id.clone(),
                (agent.traits.clone(), agent.household_id.clone()),
            )
        })
        .collect::<BTreeMap<_, _>>();
    let after_agents = after
        .state
        .agents
        .iter()
        .map(|agent| {
            (
                agent.id.clone(),
                (agent.traits.clone(), agent.household_id.clone()),
            )
        })
        .collect::<BTreeMap<_, _>>();
    assert_eq!(before_agents, after_agents);
    assert_eq!(before.state.relationships, after.state.relationships);
    let migration = run_report(&after, "composition_flows").snapshots[0]
        .rows
        .iter()
        .find(|row| row.group_id == "migration_a_b")
        .unwrap();
    assert!(number(&migration.values["count"]) > 0.0);
}

#[test]
fn country_world_cache_reuse_and_invalidation_are_branch_scoped() {
    let cold = evaluate(SOURCE, request(SOURCE, "TestWorld", 1, BTreeMap::new()));
    assert!(cold.agent_ticks > 0);
    let cold_ticks = cold.agent_ticks;
    let warm = evaluate(
        SOURCE,
        request(SOURCE, "TestWorld", 1, cold.artifacts.clone()),
    );
    assert!(
        warm.cache_hit,
        "warm invalidation={:?} root={:?}",
        warm.invalidation_reason, warm.cache_tree
    );
    assert_eq!(warm.agent_ticks, 0);
    for id in [
        "TestWorld",
        "NationA",
        "NationB",
        "Province",
        "ProvinceB",
        "MetroNorth",
        "NorthOne",
    ] {
        assert!(metadata(&warm.cache_tree, id).cached, "{id}");
    }

    let mut country_reuse = cold.artifacts.clone();
    country_reuse.remove("TestWorld");
    let reused = evaluate(SOURCE, request(SOURCE, "TestWorld", 1, country_reuse));
    assert_eq!(reused.agent_ticks, 0);
    assert!(cold_ticks > reused.agent_ticks);

    let mut changed_request = request(SOURCE, "TestWorld", 1, cold.artifacts.clone());
    changed_request.branch_inputs.insert(
        "ProvinceB".to_owned(),
        BTreeMap::from([("division_policy".to_owned(), 0.80)]),
    );
    let changed = evaluate(SOURCE, changed_request);
    assert!(!metadata(&changed.cache_tree, "ProvinceB").cached);
    assert!(!metadata(&changed.cache_tree, "NationB").cached);
    assert!(!metadata(&changed.cache_tree, "TestWorld").cached);
    assert!(metadata(&changed.cache_tree, "NationA").cached);
    assert!(metadata(&changed.cache_tree, "Province").cached);
    assert_eq!(changed.agent_ticks, 0);

    let mut event_request = request(SOURCE, "TestWorld", 1, cold.artifacts);
    event_request.events.insert("pandemic".to_owned());
    let event = evaluate(SOURCE, event_request);
    assert!(!metadata(&event.cache_tree, "NationA").cached);
    assert!(!metadata(&event.cache_tree, "NationB").cached);
    assert_ne!(
        parse_program(SOURCE)
            .unwrap()
            .compositions
            .iter()
            .find(|item| item.id == "NationA")
            .unwrap()
            .parameters["infection_modifier"],
        parse_program(SOURCE)
            .unwrap()
            .compositions
            .iter()
            .find(|item| item.id == "NationB")
            .unwrap()
            .parameters["infection_modifier"]
    );
}

#[test]
fn feedback_syncs_and_ninety_day_fast_forward_are_visible_per_level() {
    let learned = evaluate(SOURCE, request(SOURCE, "TestWorld", 1, BTreeMap::new()));
    let mut long_request = request(SOURCE, "TestWorld", 90, learned.artifacts);
    long_request.input_schedule.push(ScheduledAggregateInputs {
        day: 30,
        values: BTreeMap::from([("tax".to_owned(), 0.80)]),
    });
    let result = evaluate(SOURCE, long_request);
    let world = metadata(&result.cache_tree, "TestWorld");
    let country_a = metadata(&result.cache_tree, "NationA");
    let country_b = metadata(&result.cache_tree, "NationB");
    assert!(world.feedback_iterations <= 5);
    assert!(country_a.feedback_iterations <= 2);
    assert!(country_b.feedback_iterations <= 2);
    assert!(world.feedback_change_percent < 1.0);
    assert!(country_a.feedback_change_percent < 1.0);
    assert!(country_b.feedback_change_percent < 1.0);

    let day_30 = result
        .time_series
        .iter()
        .find(|point| point.day == 30)
        .unwrap()
        .outputs["mean_income"]
        .mean;
    let day_90 = result
        .time_series
        .iter()
        .find(|point| point.day == 90)
        .unwrap()
        .outputs["mean_income"]
        .mean;
    assert_ne!(day_30, day_90);

    let flows = report(&result, "composition_flows");
    assert_eq!(flows.snapshots.len(), 90);
    let occurrences = |id: &str| {
        flows
            .snapshots
            .iter()
            .flat_map(|snapshot| &snapshot.rows)
            .filter(|row| row.group_id == id)
            .count()
    };
    assert_eq!(occurrences("TestWorld:trade_a_b"), 1);
    assert_eq!(occurrences("NationA:country_exchange"), 3);
    assert_eq!(occurrences("ProvinceB:division_exchange"), 0);
    assert_eq!(occurrences("MetroNorth:commute"), 0);
}

#[test]
fn represented_population_and_determinism_do_not_expand_objects() {
    let program = parse_program(SOURCE).unwrap();
    let first = run_composition(program.clone(), "HundredMillionWorld", 1, 0).unwrap();
    let second = run_composition(program, "HundredMillionWorld", 1, 0).unwrap();
    assert_eq!(first, second);
    assert_eq!(first.state.agents.len(), 20);
    let summary = run_report(&first, "composition_population_summary");
    assert_eq!(
        number(&summary.snapshots[0].rows[0].values["represented_population"]),
        100_000_000.0
    );
    assert_eq!(
        number(&summary.snapshots[0].rows[0].values["total_population"]),
        20.0
    );

    let cold = evaluate(SOURCE, request(SOURCE, "TestWorld", 1, BTreeMap::new()));
    let warm = evaluate(
        SOURCE,
        request(SOURCE, "TestWorld", 1, cold.artifacts.clone()),
    );
    let repeated = evaluate(SOURCE, request(SOURCE, "TestWorld", 1, cold.artifacts));
    assert_eq!(warm.agent_ticks, 0);
    assert_eq!(output(&warm, "represented_population"), 100_000_000.0);
    assert_eq!(warm.time_series, repeated.time_series);
    assert_eq!(warm.reports, repeated.reports);
}

#[test]
fn country_and_world_cached_outputs_match_three_hundred_agent_runs() {
    let base = pure_source()
        .replace("sample_households = 5", "sample_households = 75")
        .replace(
            "country_exchange Province -> ProvinceAlt rate = formula(clamp(0.10 + Province_mean_income / 1000 - tariff * 0.20, 0, 0.60))",
            "country_exchange Province -> ProvinceAlt rate = 0.20",
        )
        .replace(
            "trade_a_b NationA -> NationB rate = formula(clamp(0.08 + NationA_gdp_proxy / 10000 + NationB_gdp_proxy / 10000 - tariff * 0.25, 0, 0.70))",
            "trade_a_b NationA -> NationB rate = 0.20",
        );
    let country_source = base
        .replace("    Province: weight = 60", "    Province: weight = 180")
        .replace(
            "    ProvinceAlt: weight = 40",
            "    ProvinceAlt: weight = 120",
        );
    compare_detailed_and_cached(
        &country_source,
        "NationA",
        &[
            "population",
            "mean_income",
            "mean_stress",
            "vote_share",
            "fights_per_day",
            "trade_balance",
            "migration_rate",
        ],
    );

    let world_source = base
        .replace("    NationA: weight = 60", "    NationA: weight = 180")
        .replace("    NationB: weight = 40", "    NationB: weight = 120");
    compare_detailed_and_cached(
        &world_source,
        "TestWorld",
        &[
            "population",
            "mean_income",
            "mean_stress",
            "vote_share",
            "fights_per_day",
            "trade_balance",
            "migration_rate",
        ],
    );
}

fn compare_detailed_and_cached(source: &str, id: &str, metrics: &[&str]) {
    let detailed = run_composition(parse_program(source).unwrap(), id, 1, 30).unwrap();
    assert_eq!(detailed.state.agents.len(), 300);
    let learned = evaluate(source, request(source, id, 30, BTreeMap::new()));
    let cached = evaluate(source, request(source, id, 30, learned.artifacts));
    assert_eq!(cached.agent_ticks, 0);
    for metric in metrics {
        let actual = output(&cached, metric);
        let expected = detailed_value(&detailed, metric);
        assert!(
            (actual - expected).abs() / expected.abs().max(1.0) <= 0.10,
            "{id}.{metric}: cached={actual}, detailed={expected}"
        );
    }
}
