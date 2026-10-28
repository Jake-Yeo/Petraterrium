use petraterrium_engine::text_dsl::{parse_program, run_composition};
use std::collections::BTreeSet;

const SOURCE: &str = include_str!("../dsl/default.dsl");

#[test]
fn full_system_runs_every_slice_and_records_each_declared_coupling() {
    let program = parse_program(SOURCE).unwrap();
    let result = run_composition(program, "Petraterrium", 1, 24).unwrap();
    let children = result
        .reports
        .iter()
        .find(|report| report.id == "composition_children")
        .unwrap();
    let child_ids = children.snapshots[0]
        .rows
        .iter()
        .map(|row| row.group_id.as_str())
        .collect::<BTreeSet<_>>();
    for id in [
        "World",
        "Reddit",
        "CorporateForest",
        "ListedCorporateForest",
        "FinancialEconomy",
        "UnifiedRolePopulation",
    ] {
        assert!(child_ids.contains(id), "{id}");
    }
    let flow_report = result
        .reports
        .iter()
        .find(|report| report.id == "composition_flows")
        .unwrap();
    let ids = flow_report.snapshots[0]
        .rows
        .iter()
        .map(|row| row.group_id.as_str())
        .collect::<BTreeSet<_>>();
    for id in [
        "world_to_media",
        "media_outrage_to_world",
        "world_to_store_corporate",
        "store_profit_to_world",
        "store_profit_to_firms",
        "firm_allocation_to_stores",
        "alpha_profit_to_market",
        "alpha_price_to_corporate",
        "trader_signal_to_market",
    ] {
        assert!(ids.contains(id), "missing {id}");
    }
}

#[test]
fn full_system_is_deterministic_for_seed_and_budget() {
    let mut program = parse_program(SOURCE).unwrap();
    program
        .compositions
        .iter_mut()
        .find(|composition| composition.id == "Petraterrium")
        .unwrap()
        .sample_budget = Some(1_000);
    let first = run_composition(program.clone(), "Petraterrium", 17, 2).unwrap();
    let second = run_composition(program, "Petraterrium", 17, 2).unwrap();
    assert_eq!(first, second);
}
