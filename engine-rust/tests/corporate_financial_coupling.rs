use petraterrium_engine::text_dsl::{
    CachedCompositionEvaluationResult, CachedCompositionProtocolRequest, CompositionCacheMetadata,
    DslReportValue, DslRunResult, LearnedAggregateArtifact, ScheduledAggregateInputs,
    evaluate_cached_composition, parse_program, run_composition,
};
use std::collections::{BTreeMap, BTreeSet};

const SOURCE: &str = include_str!("../dsl/financial_coupling_test.dsl");

fn run(source: &str, composition: &str, days: u64) -> DslRunResult {
    run_composition(parse_program(source).unwrap(), composition, 1, days * 24).unwrap()
}

fn root_value(result: &DslRunResult, id: &str) -> f64 {
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
    days: u32,
    artifacts: BTreeMap<String, LearnedAggregateArtifact>,
) -> CachedCompositionProtocolRequest {
    CachedCompositionProtocolRequest {
        source: source.to_owned(),
        dsl_source_hash: hash(source),
        function_id: "CorporateFinancialSystem".to_owned(),
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

fn metadata<'a>(tree: &'a CompositionCacheMetadata, id: &str) -> &'a CompositionCacheMetadata {
    if tree.function_id == id {
        return tree;
    }
    tree.children
        .iter()
        .find_map(|child| find_metadata(child, id))
        .unwrap()
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

fn cached_value(result: &CachedCompositionEvaluationResult, id: &str) -> f64 {
    result.time_series.last().unwrap().outputs[id].mean
}

#[test]
fn price_and_market_cap_drive_allocation_without_changing_cash() {
    let baseline = run(SOURCE, "FirmAlpha", 0);
    assert_eq!(root_value(&baseline, "capital_allocation"), 90.0);
    assert_eq!(root_value(&baseline, "cash"), 200.0);
    let repriced = SOURCE
        .replacen("firm_a_price = 31", "firm_a_price = 41", 1)
        .replacen("firm_a_market_cap = 3100", "firm_a_market_cap = 4100", 1);
    let repriced = run(&repriced, "FirmAlpha", 0);
    assert_eq!(root_value(&repriced, "capital_allocation"), 115.0);
    assert!(root_value(&repriced, "expansion") > root_value(&baseline, "expansion"));
    assert!(root_value(&repriced, "wage_policy") > root_value(&baseline, "wage_policy"));
    assert!(root_value(&repriced, "price_policy") > root_value(&baseline, "price_policy"));
    assert_eq!(root_value(&repriced, "cash"), root_value(&baseline, "cash"));
}

#[test]
fn financial_hierarchy_reports_two_separate_market_and_sector_branches() {
    let economy = run(SOURCE, "FinancialEconomy", 0);
    let children = economy
        .reports
        .iter()
        .find(|report| report.id == "composition_children")
        .unwrap();
    let rows = &children.snapshots[0].rows;
    assert!(rows.iter().any(|row| row.group_id == "SectorAlpha"));
    assert!(rows.iter().any(|row| row.group_id == "SectorBeta"));
    assert_ne!(
        root_value(&economy, "alpha_price"),
        root_value(&economy, "beta_price")
    );
    let corporate = run(SOURCE, "ListedCorporateForest", 0);
    assert_eq!(root_value(&corporate, "family_profit"), 40.0);
    assert!(!corporate.reports.iter().any(|report| {
        report.snapshots.iter().any(|snapshot| {
            snapshot.rows.iter().any(|row| {
                row.group_id.contains("FamilyBusiness")
                    && row.values.keys().any(|key| key.contains("market_cap"))
            })
        })
    }));
    let system = run(SOURCE, "CorporateFinancialSystem", 0);
    let hierarchy = system
        .reports
        .iter()
        .find(|report| report.id == "composition_hierarchy")
        .unwrap();
    let ids = hierarchy.snapshots[0]
        .rows
        .iter()
        .map(|row| row.group_id.as_str())
        .collect::<BTreeSet<_>>();
    for id in [
        "FirmAlpha",
        "FirmBeta",
        "MarketAlpha",
        "MarketBeta",
        "SectorAlpha",
        "SectorBeta",
    ] {
        assert!(ids.contains(id), "{id}");
    }
}

#[test]
fn coupled_cache_is_zero_tick_and_invalidates_only_the_changed_firm_branches() {
    let cold = evaluate(SOURCE, request(SOURCE, 90, BTreeMap::new()));
    assert!(cold.agent_ticks > 0);
    let warm = evaluate(SOURCE, request(SOURCE, 90, cold.artifacts.clone()));
    assert!(warm.cache_hit);
    assert_eq!(warm.agent_ticks, 0);

    let mut changed_request = request(SOURCE, 90, cold.artifacts.clone());
    changed_request.branch_inputs.insert(
        "FirmAlpha".to_owned(),
        BTreeMap::from([("profit".to_owned(), 150.0)]),
    );
    changed_request.branch_inputs.insert(
        "FinancialEconomy".to_owned(),
        BTreeMap::from([("firm_a_profit".to_owned(), 150.0)]),
    );
    let changed = evaluate(SOURCE, changed_request);
    assert_eq!(changed.agent_ticks, 0);
    for id in [
        "CorporateFinancialSystem",
        "ListedCorporateForest",
        "FirmAlpha",
        "FinancialEconomy",
        "SectorAlpha",
        "MarketAlpha",
        "StockAlpha",
    ] {
        assert!(!metadata(&changed.cache_tree, id).cached, "{id}");
    }
    for id in [
        "FirmBeta",
        "FamilyBusiness",
        "SectorBeta",
        "MarketBeta",
        "StockBeta",
    ] {
        assert!(metadata(&changed.cache_tree, id).cached, "{id}");
    }
    assert!(cached_value(&changed, "alpha_price") > cached_value(&warm, "alpha_price"));
    assert_eq!(
        cached_value(&changed, "family_profit"),
        cached_value(&warm, "family_profit")
    );

    let mut long_request = request(SOURCE, 90, cold.artifacts);
    long_request.input_schedule.push(ScheduledAggregateInputs {
        day: 60,
        values: BTreeMap::from([("macro_signal".to_owned(), 0.8)]),
    });
    let long = evaluate(SOURCE, long_request);
    let day_30 = long
        .time_series
        .iter()
        .find(|point| point.day == 30)
        .unwrap();
    let day_90 = long
        .time_series
        .iter()
        .find(|point| point.day == 90)
        .unwrap();
    assert_ne!(day_30.outputs, day_90.outputs);
}

#[test]
fn coupling_is_explicit_quarterly_and_not_applied_per_trade() {
    let detailed_day = run(SOURCE, "CorporateFinancialSystem", 1);
    assert_eq!(root_value(&detailed_day, "firm_a_capital_allocation"), 90.0);

    let coupled = evaluate(SOURCE, request(SOURCE, 180, BTreeMap::new()));
    let coupling_rows = |result: &CachedCompositionEvaluationResult| {
        result
            .reports
            .iter()
            .find(|report| report.id == "composition_flows")
            .unwrap()
            .snapshots
            .iter()
            .flat_map(|snapshot| &snapshot.rows)
            .filter(|row| {
                row.values.get("effect") == Some(&DslReportValue::Text("coupling".to_owned()))
            })
            .count()
    };
    assert_eq!(coupling_rows(&coupled), 14);

    let semiannual = SOURCE.replacen(
        "composition CorporateFinancialSystem:\n  level = coupled_corporate_financial\n  report_descendants = true\n  children:\n    ListedCorporateForest: weight = 1\n    FinancialEconomy: weight = 1\n    UnifiedRolePopulation: weight = 1\n  parameters:\n    macro_signal = 0\n  cached:\n    sync = 90 days",
        "composition CorporateFinancialSystem:\n  level = coupled_corporate_financial\n  report_descendants = true\n  children:\n    ListedCorporateForest: weight = 1\n    FinancialEconomy: weight = 1\n    UnifiedRolePopulation: weight = 1\n  parameters:\n    macro_signal = 0\n  cached:\n    sync = 180 days",
        1,
    );
    let semiannual = evaluate(&semiannual, request(&semiannual, 180, BTreeMap::new()));
    assert_eq!(coupling_rows(&semiannual), 7);

    let uncoupled = SOURCE
        .replace(
            "  couplings:\n    alpha_profit_to_market ListedCorporateForest -> FinancialEconomy input = firm_a_profit value = formula(ListedCorporateForest_firm_a_profit) cadence = sync\n    beta_profit_to_market ListedCorporateForest -> FinancialEconomy input = firm_b_profit value = formula(ListedCorporateForest_firm_b_profit) cadence = sync\n    trader_signal_to_market UnifiedRolePopulation -> FinancialEconomy input = trader_signal value = formula(clamp(UnifiedRolePopulation_trade_count / 100, 0, 1)) cadence = sync\n    alpha_price_to_corporate FinancialEconomy -> ListedCorporateForest input = firm_a_price value = formula(FinancialEconomy_alpha_price) cadence = sync\n    alpha_cap_to_corporate FinancialEconomy -> ListedCorporateForest input = firm_a_market_cap value = formula(FinancialEconomy_alpha_market_cap) cadence = sync\n    beta_price_to_corporate FinancialEconomy -> ListedCorporateForest input = firm_b_price value = formula(FinancialEconomy_beta_price) cadence = sync\n    beta_cap_to_corporate FinancialEconomy -> ListedCorporateForest input = firm_b_market_cap value = formula(FinancialEconomy_beta_market_cap) cadence = sync\n",
            "",
        )
        .replace("  output alpha_profit_to_market = flow_rate(alpha_profit_to_market)\n", "")
        .replace("  output alpha_price_to_corporate = flow_rate(alpha_price_to_corporate)\n", "")
        .replace("    alpha_profit_to_market = formula(macro_signal)\n", "")
        .replace("    alpha_price_to_corporate = formula(macro_signal)\n", "");
    let uncoupled = evaluate(&uncoupled, request(&uncoupled, 180, BTreeMap::new()));
    assert_eq!(coupling_rows(&uncoupled), 0);
    assert_ne!(
        cached_value(&coupled, "firm_a_capital_allocation"),
        cached_value(&uncoupled, "firm_a_capital_allocation")
    );
}

#[test]
fn detailed_and_cached_peer_hierarchies_match_within_ten_percent() {
    let detailed = run(SOURCE, "CorporateFinancialSystem", 30);
    let cold = evaluate(SOURCE, request(SOURCE, 30, BTreeMap::new()));
    let cached = evaluate(SOURCE, request(SOURCE, 30, cold.artifacts));
    assert_eq!(cached.agent_ticks, 0);
    for metric in [
        "alpha_price",
        "alpha_dividend",
        "firm_a_profit",
        "firm_a_capital_allocation",
    ] {
        let detailed_value = root_value(&detailed, metric);
        let cached_value = cached_value(&cached, metric);
        assert!(
            (detailed_value - cached_value).abs() / detailed_value.abs().max(1e-9) <= 0.10,
            "{metric}: detailed={detailed_value}, cached={cached_value}"
        );
    }
}
