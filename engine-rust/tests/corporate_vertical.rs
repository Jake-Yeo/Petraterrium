use petraterrium_engine::text_dsl::{
    CachedCompositionEvaluationResult, CachedCompositionProtocolRequest, CompositionCacheMetadata,
    DslReportValue, LearnedAggregateArtifact, ScheduledAggregateInputs,
    evaluate_cached_composition, parse_program, run_composition,
};
use std::collections::{BTreeMap, BTreeSet};

const SOURCE: &str = include_str!("../dsl/corporate_test.dsl");
const DEFAULT_SOURCE: &str = include_str!("../dsl/default.dsl");
const GENERIC_SOURCE: &str = r#"program GenericPrimitives version "1.0":
  tick_hours = 1 placeholder
  placeholder = "placeholder — agent knowledge, for demo only, to be replaced by research"
  uncertainty = wide
  record_actions = true
  results_title = "Generic primitives"
  results_subtitle = "Non-domain composition"

output overview:
  title = "Overview"
  group_by = all
  display = cards
  record = final
  column population = count() label "Population" format integer

place Room:
  scope = composition
  state visits = 0 range 0..100 estimated

agent Visitor:
  scope = composition
  role visitor
  state location
  initial:
    location ~ Categorical(Room: 1.0) placeholder
  routine = visitor_day

agent Guide:
  scope = composition
  role guide
  state location
  initial:
    location ~ Categorical(Room: 1.0) placeholder
  routine = guide_day

population:
  size = 1 placeholder
  mix:
    Visitor = 1.0 placeholder

archetype Pair:
  sample_households = 1
  composition:
    visitors count = 1 mix Visitor:1.0
    guides count = 1 mix Guide:1.0
  output population = count()

decision visitor_day:
  branch greet p = 1.0 estimated

decision guide_day:
  branch wait p = 1.0 estimated

action greet:
  aggregate = greetings
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  target = random at current place where target.role.guide
  outcome greeted p = 1.0 estimated:
    effect current place visits += 1 estimated
    next = visitor_day

action wait:
  aggregate = waiting
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  outcome waited p = 1.0 estimated:
    next = guide_day

composition SiteAlpha:
  level = leaf
  allocation_leaf = true
  children:
    Pair: weight = 1
  places = Room
  parameters:
    score = 2
  output population = count()
  output score = formula(score)

composition SiteBeta:
  level = leaf
  allocation_leaf = true
  children:
    Pair: weight = 1
  places = Room
  parameters:
    score = 3
  output population = count()
  output score = formula(score)

composition GenericRegion:
  level = allocation
  authoritative_total = 5
  sample_budget = 2
  children:
    SiteAlpha: weight = 0.4 count = 2
    SiteBeta: weight = 0.6 count = 3
  output population = count()
  output represented_total = represented_total()
  output total_score = formula(sum.score)
"#;

fn report_rows(
    result: &petraterrium_engine::text_dsl::DslRunResult,
    id: &str,
) -> BTreeMap<String, BTreeMap<String, DslReportValue>> {
    result
        .reports
        .iter()
        .find(|report| report.id == id)
        .unwrap()
        .snapshots
        .last()
        .unwrap()
        .rows
        .iter()
        .map(|row| (row.group_id.clone(), row.values.clone()))
        .collect()
}

fn number(value: &DslReportValue) -> f64 {
    match value {
        DslReportValue::Number(value) => *value,
        value => panic!("expected number, got {value:?}"),
    }
}

fn root_value(result: &petraterrium_engine::text_dsl::DslRunResult, id: &str) -> f64 {
    let rows = report_rows(result, "compositions");
    number(&rows.values().next().unwrap()[id])
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
    days: u32,
    artifacts: BTreeMap<String, LearnedAggregateArtifact>,
) -> CachedCompositionProtocolRequest {
    request_for(SOURCE, "CorporateForest", days, artifacts)
}

fn request_for(
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

fn evaluate(request: CachedCompositionProtocolRequest) -> CachedCompositionEvaluationResult {
    let source = request.source.clone();
    evaluate_cached_composition(parse_program(&source).unwrap(), request).unwrap()
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

#[test]
fn same_place_role_targeting_conserves_transaction_money() {
    let result = run_composition(parse_program(SOURCE).unwrap(), "TransactionStore", 1, 1).unwrap();
    let customer = result
        .state
        .agents
        .iter()
        .find(|agent| agent.roles.contains("customer"))
        .unwrap();
    let cashier = result
        .state
        .agents
        .iter()
        .find(|agent| agent.roles.contains("cashier"))
        .unwrap();
    let store = result
        .state
        .places
        .iter()
        .find(|place| place.id == "Store")
        .unwrap();
    assert_eq!(customer.states["money"].as_f64().unwrap(), 90.0);
    assert_eq!(cashier.states["money"].as_f64().unwrap(), 5.0);
    assert_eq!(store.states["cash"].as_f64().unwrap(), 105.0);
    assert_eq!(store.states["revenue"].as_f64().unwrap(), 10.0);
    assert_eq!(
        customer.states["money"].as_f64().unwrap()
            + cashier.states["money"].as_f64().unwrap()
            + store.states["cash"].as_f64().unwrap(),
        200.0
    );
    assert_eq!(result.actions.len(), 2);
    for action in &result.actions {
        let target = result
            .state
            .agents
            .iter()
            .find(|agent| Some(agent.id.as_str()) == action.target_id.as_deref())
            .unwrap();
        assert_eq!(target.place(), Some(action.place.as_str()));
        if action.action.ends_with("buy") {
            assert!(target.roles.contains("cashier"));
        } else {
            assert!(target.roles.contains("customer"));
        }
    }
}

#[test]
fn generic_primitives_work_without_corporate_names_or_levels() {
    let result = run_composition(
        parse_program(GENERIC_SOURCE).unwrap(),
        "GenericRegion",
        1,
        1,
    )
    .unwrap();
    let greetings = result
        .actions
        .iter()
        .filter(|action| action.action.ends_with("greet"))
        .collect::<Vec<_>>();
    assert_eq!(greetings.len(), 2);
    for greeting in greetings {
        let target = result
            .state
            .agents
            .iter()
            .find(|agent| Some(agent.id.as_str()) == greeting.target_id.as_deref())
            .unwrap();
        assert!(target.roles.contains("guide"));
        assert_eq!(target.place(), Some(greeting.place.as_str()));
    }
    assert_eq!(root_value(&result, "total_score"), 5.0);
    let allocations = report_rows(&result, "composition_allocations");
    assert_eq!(number(&allocations["SiteAlpha"]["represented_count"]), 2.0);
    assert_eq!(number(&allocations["SiteBeta"]["represented_count"]), 3.0);
}

#[test]
fn shipped_program_exposes_the_corporate_forest_and_coupled_root() {
    let program = parse_program(DEFAULT_SOURCE).unwrap();
    let levels = program
        .compositions
        .iter()
        .map(|composition| (composition.id.as_str(), composition.level.as_str()))
        .collect::<BTreeMap<_, _>>();
    assert_eq!(levels["CorporateForest"], "forest");
    assert_eq!(levels["ConglomerateRoot"], "parent");
    assert_eq!(levels["BrandOne"], "label");
    assert_eq!(levels["FranchiseOne"], "branch");
    assert_eq!(levels["StoreA"], "site");
    assert_eq!(levels["FamilyStore"], "site");
    assert_eq!(levels["CoupledPhysicalCorporate"], "coupled_modules");
}

#[test]
fn formulas_sum_each_level_once_and_keep_independent_root_isolated() {
    let result = run_composition(parse_program(SOURCE).unwrap(), "CorporateForest", 1, 0).unwrap();
    let store_a = 100.0 - 20.0 - 10.0 - 5.0;
    let store_b = 80.0 - 18.0 - 8.0 - 4.0;
    let store_c = 90.0 - 19.0 - 9.0 - 4.0;
    let store_d = 70.0 - 16.0 - 7.0 - 3.0;
    let franchise_one = store_a + store_b - 7.0;
    let franchise_two = store_c - 6.0;
    let brand_one = franchise_one + franchise_two - 9.0;
    let brand_two = store_d - 3.0;
    let conglomerate = brand_one + brand_two - 11.0;
    let family = 60.0 - 15.0 - 5.0;
    assert_eq!(root_value(&result, "conglomerate_profit"), conglomerate);
    assert_eq!(root_value(&result, "independent_profit"), family);
    assert_eq!(root_value(&result, "total_profit"), conglomerate + family);
    let franchise_result =
        run_composition(parse_program(SOURCE).unwrap(), "FranchiseOne", 1, 0).unwrap();
    let brand_result = run_composition(parse_program(SOURCE).unwrap(), "BrandOne", 1, 0).unwrap();
    let parent_result =
        run_composition(parse_program(SOURCE).unwrap(), "ConglomerateRoot", 1, 0).unwrap();
    let family_result =
        run_composition(parse_program(SOURCE).unwrap(), "FamilyStore", 1, 0).unwrap();
    assert_eq!(root_value(&franchise_result, "cash"), 0.0);
    assert_eq!(root_value(&brand_result, "cash"), 0.0);
    assert_eq!(root_value(&family_result, "cash"), 0.0);
    assert_eq!(
        root_value(&parent_result, "cash"),
        root_value(&parent_result, "profit")
    );
}

#[test]
fn family_owner_payout_moves_existing_cash_without_creating_money() {
    let result = run_composition(parse_program(SOURCE).unwrap(), "FamilyStore", 1, 24).unwrap();
    let owner = result
        .state
        .agents
        .iter()
        .find(|agent| agent.roles.contains("owner"))
        .unwrap();
    assert!(owner.states["money"].as_f64().unwrap() > 0.0);
    assert!(
        result
            .actions
            .iter()
            .any(|action| action.action.ends_with("owner_payout"))
    );
    let agent_money = result
        .state
        .agents
        .iter()
        .map(|agent| agent.states["money"].as_f64().unwrap())
        .sum::<f64>();
    let store_cash = result
        .state
        .places
        .iter()
        .find(|place| place.id == "Store")
        .unwrap()
        .states["cash"]
        .as_f64()
        .unwrap();
    assert!((agent_money + store_cash - 200.0).abs() < 1e-9);
}

#[test]
fn store_actions_are_exposed_by_active_role_subtrees() {
    let program = parse_program(SOURCE).unwrap();
    for (role, decision) in [
        ("customer", "customer_day"),
        ("cashier", "employment_day"),
        ("manager", "manager_day"),
        ("owner", "family_owner_day"),
    ] {
        assert!(
            program
                .roles
                .iter()
                .find(|definition| definition.id == role)
                .unwrap()
                .decisions
                .iter()
                .any(|definition| definition.id == decision),
            "{role}:{decision}"
        );
    }

    let no_cashier = SOURCE.replacen("  role cashier\n", "", 1);
    let no_cashier = run_composition(
        parse_program(&no_cashier).unwrap(),
        "TransactionStore",
        1,
        1,
    )
    .unwrap();
    assert!(no_cashier.actions.is_empty());

    let no_owner = SOURCE.replacen("  role owner\n", "", 1);
    let no_owner =
        run_composition(parse_program(&no_owner).unwrap(), "FamilyStore", 1, 24).unwrap();
    assert!(
        no_owner
            .actions
            .iter()
            .all(|action| !action.action.ends_with("owner_payout"))
    );
}

#[test]
fn moving_membership_in_dsl_redirects_profit_without_engine_changes() {
    let before = run_composition(parse_program(SOURCE).unwrap(), "CorporateForest", 1, 0).unwrap();
    let acquired = SOURCE
        .replace(
            "    StoreB: weight = 1\n  parameters:\n    costs = 7",
            "    StoreB: weight = 1\n    FamilyStore: weight = 1\n  parameters:\n    costs = 7",
        )
        .replace(
            "    ConglomerateRoot: weight = 1\n    FamilyStore: weight = 1\n",
            "    ConglomerateRoot: weight = 1\n",
        )
        .replace(
            "  output independent_profit = formula(FamilyStore.profit)\n",
            "",
        )
        .replace(
            "    independent_profit = formula(price_policy, wage_policy)\n",
            "",
        );
    let after =
        run_composition(parse_program(&acquired).unwrap(), "CorporateForest", 1, 0).unwrap();
    let family = root_value(&before, "independent_profit");
    assert_eq!(
        root_value(&after, "conglomerate_profit"),
        root_value(&before, "conglomerate_profit") + family
    );
    assert_eq!(
        root_value(&after, "total_profit"),
        root_value(&before, "total_profit")
    );
}

#[test]
fn authoritative_allocation_uses_largest_remainders_and_exact_totals() {
    let result = run_composition(parse_program(SOURCE).unwrap(), "RegionalStores", 1, 0).unwrap();
    let rows = report_rows(&result, "composition_allocations");
    assert_eq!(rows.len(), 3);
    assert_eq!(
        rows.values()
            .map(|row| number(&row["represented_count"]))
            .sum::<f64>(),
        7.0
    );
    assert_eq!(
        rows.values()
            .map(|row| number(&row["simulated_count"]))
            .sum::<f64>(),
        3.0
    );
    assert_eq!(
        number(&rows["NorthStores/StoreA"]["represented_count"]),
        2.0
    );
    assert_eq!(
        number(&rows["NorthStores/StoreB"]["represented_count"]),
        2.0
    );
    assert_eq!(
        number(&rows["SouthStores/FamilyStore"]["represented_count"]),
        3.0
    );
    assert_eq!(result.state.agents.len(), 9);
}

#[test]
fn allocation_validation_reports_weight_and_declared_count_errors_with_lines() {
    let bad_weight = SOURCE.replacen(
        "    SouthStores: weight = 0.5",
        "    SouthStores: weight = 0.4",
        1,
    );
    let error = parse_program(&bad_weight).unwrap_err();
    assert_eq!(error.code, "COMPOSITION_WEIGHTS_NOT_ONE");
    assert!(error.line > 0);

    let bad_count = SOURCE.replacen(
        "StoreB: weight = 0.5 count = 2",
        "StoreB: weight = 0.5 count = 1",
        1,
    );
    let error = parse_program(&bad_count).unwrap_err();
    assert_eq!(error.code, "DECLARED_ALLOCATION_TOTAL_MISMATCH");
    assert!(error.line > 0);
}

#[test]
fn changing_the_authoritative_total_reallocates_without_leaf_edits() {
    let baseline = run_composition(
        parse_program(SOURCE).unwrap(),
        "TexasStoreDistribution",
        1,
        0,
    )
    .unwrap();
    let expanded_source = SOURCE.replacen(
        "  authoritative_total = 500",
        "  authoritative_total = 550",
        1,
    );
    let expanded = run_composition(
        parse_program(&expanded_source).unwrap(),
        "TexasStoreDistribution",
        1,
        0,
    )
    .unwrap();
    let total = |result: &petraterrium_engine::text_dsl::DslRunResult| {
        report_rows(result, "composition_allocations")
            .values()
            .map(|row| number(&row["represented_count"]))
            .sum::<f64>()
    };
    assert_eq!(total(&baseline), 500.0);
    assert_eq!(total(&expanded), 550.0);
    assert_eq!(
        number(
            &report_rows(&baseline, "composition_allocations")["DallasStores/StoreA"]["represented_count"]
        ),
        100.0
    );
}

#[test]
fn corporate_cache_reuses_children_and_invalidates_only_the_changed_branch() {
    let cold = evaluate(request(30, BTreeMap::new()));
    assert!(cold.agent_ticks > 0);
    let warm = evaluate(request(30, cold.artifacts.clone()));
    assert!(warm.cache_hit);
    assert_eq!(warm.agent_ticks, 0);
    for id in [
        "CorporateForest",
        "ConglomerateRoot",
        "BrandOne",
        "BrandTwo",
        "FranchiseOne",
        "FranchiseTwo",
        "StoreA",
        "StoreD",
        "FamilyStore",
    ] {
        assert!(metadata(&warm.cache_tree, id).cached, "{id}");
    }

    let mut changed_request = request(30, cold.artifacts.clone());
    changed_request.branch_inputs.insert(
        "BrandOne".to_owned(),
        BTreeMap::from([("price_policy".to_owned(), 1.2)]),
    );
    let changed = evaluate(changed_request);
    assert_eq!(changed.agent_ticks, 0);
    for id in [
        "CorporateForest",
        "ConglomerateRoot",
        "BrandOne",
        "FranchiseOne",
        "FranchiseTwo",
        "StoreA",
    ] {
        assert!(!metadata(&changed.cache_tree, id).cached, "{id}");
    }
    for id in ["BrandTwo", "StoreD", "FamilyStore"] {
        assert!(metadata(&changed.cache_tree, id).cached, "{id}");
    }
    assert_ne!(
        warm.time_series.last().unwrap().outputs["conglomerate_profit"].mean,
        changed.time_series.last().unwrap().outputs["conglomerate_profit"].mean
    );

    let mut long_request = request(90, cold.artifacts);
    long_request.input_schedule.push(ScheduledAggregateInputs {
        day: 60,
        values: BTreeMap::from([("price_policy".to_owned(), 1.1)]),
    });
    let long = evaluate(long_request);
    assert_eq!(long.agent_ticks, 0);
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
fn corporate_couplings_are_explicit_and_sync_cadence_controls_exchange() {
    let detailed = run_composition(
        parse_program(SOURCE).unwrap(),
        "CoupledPhysicalCorporate",
        1,
        1,
    )
    .unwrap();
    assert!(root_value(&detailed, "total_profit") > 0.0);
    let detailed_flows = report_rows(&detailed, "composition_flows");
    assert!(
        detailed_flows
            .keys()
            .any(|id| id.ends_with("demand_to_price"))
    );
    assert!(
        detailed_flows
            .keys()
            .any(|id| id.ends_with("profit_to_demand"))
    );

    let cold = evaluate(request_for(
        SOURCE,
        "CoupledPhysicalCorporate",
        180,
        BTreeMap::new(),
    ));
    let warm = evaluate(request_for(
        SOURCE,
        "CoupledPhysicalCorporate",
        180,
        cold.artifacts.clone(),
    ));
    assert!(warm.cache_hit);
    assert_eq!(warm.agent_ticks, 0);
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
    assert_eq!(coupling_rows(&warm), 4);

    let uncoupled = SOURCE
        .replace(
            "  couplings:\n    demand_to_price PhysicalRetail -> CorporateForest input = price_policy value = formula(clamp(1 + PhysicalRetail_purchase_count * 0, 0.5, 2)) cadence = sync\n    profit_to_demand CorporateForest -> PhysicalRetail input = demand value = formula(clamp(CorporateForest_total_profit / 500, 0, 1)) cadence = sync\n",
            "",
        )
        .replace("  output demand_to_price = flow_rate(demand_to_price)\n", "")
        .replace("  output profit_to_demand = flow_rate(profit_to_demand)\n", "")
        .replace("    demand_to_price = formula(external_demand)\n", "")
        .replace("    profit_to_demand = formula(external_demand)\n", "");
    let uncoupled_result = evaluate(request_for(
        &uncoupled,
        "CoupledPhysicalCorporate",
        180,
        BTreeMap::new(),
    ));
    assert_eq!(coupling_rows(&uncoupled_result), 0);
    assert_ne!(
        warm.time_series.last().unwrap().outputs["purchase_count"].mean,
        uncoupled_result.time_series.last().unwrap().outputs["purchase_count"].mean
    );

    let semiannual = SOURCE.replacen(
        "composition CoupledPhysicalCorporate:\n  level = coupled_modules\n  children:\n    PhysicalRetail: weight = 1\n    CorporateForest: weight = 1\n  cached:\n    sync = 90 days",
        "composition CoupledPhysicalCorporate:\n  level = coupled_modules\n  children:\n    PhysicalRetail: weight = 1\n    CorporateForest: weight = 1\n  cached:\n    sync = 180 days",
        1,
    );
    let semiannual_result = evaluate(request_for(
        &semiannual,
        "CoupledPhysicalCorporate",
        180,
        BTreeMap::new(),
    ));
    assert_eq!(coupling_rows(&semiannual_result), 2);
}

#[test]
fn composed_money_outputs_match_the_detailed_hierarchy() {
    let detailed = run_composition(
        parse_program(SOURCE).unwrap(),
        "CorporateForest",
        1,
        30 * 24,
    )
    .unwrap();
    let cold = evaluate(request(30, BTreeMap::new()));
    let cached = evaluate(request(30, cold.artifacts));
    assert_eq!(cached.agent_ticks, 0);
    for metric in ["total_revenue", "total_profit", "total_wages"] {
        let detailed_value = root_value(&detailed, metric);
        let cached_value = cached.time_series.last().unwrap().outputs[metric].mean;
        assert!(
            (detailed_value - cached_value).abs() / detailed_value.abs().max(1e-9) <= 0.10,
            "{metric}: detailed={detailed_value}, cached={cached_value}"
        );
    }
}
