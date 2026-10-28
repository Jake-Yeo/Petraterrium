use petraterrium_engine::text_dsl::{
    AggregateEvaluationProtocolRequest, DslReportValue, DslRunRequest, evaluate_aggregate_function,
    parse_program, run_program,
};
use std::collections::{BTreeMap, BTreeSet};

const MARKET: &str = include_str!("../dsl/finance_demo.dsl");

#[test]
fn dsl_only_finance_system_runs_through_generic_program_and_cache() {
    let program = parse_program(MARKET).unwrap();
    let first = run_program(DslRunRequest::new(program.clone(), 1, 30 * 24)).unwrap();
    let repeated = run_program(DslRunRequest::new(program.clone(), 1, 30 * 24)).unwrap();
    assert_eq!(first, repeated);
    let report = first
        .reports
        .iter()
        .find(|report| report.id == "market_summary")
        .unwrap();
    let row = &report.snapshots[0].rows[0];
    assert!(matches!(row.values["mean_cash"], DslReportValue::Number(value) if value > 0.0));
    assert!(matches!(row.values["price"], DslReportValue::Number(value) if value > 1.0));
    assert!(matches!(row.values["buys"], DslReportValue::Number(value) if value > 0.0));
    assert!(matches!(row.values["sells"], DslReportValue::Number(value) if value > 0.0));

    let learned = evaluate_aggregate_function(
        program.clone(),
        AggregateEvaluationProtocolRequest {
            source: MARKET.to_owned(),
            dsl_source_hash: "sha256:market".to_owned(),
            function_id: "MarketLab".to_owned(),
            seed: 1,
            days: 2,
            evaluated_at_day: 0,
            inputs: BTreeMap::from([("liquidity_shock".to_owned(), 0.0)]),
            events: BTreeSet::new(),
            artifact: None,
            force_relearn: false,
        },
    )
    .unwrap();
    let cached = evaluate_aggregate_function(
        program,
        AggregateEvaluationProtocolRequest {
            source: MARKET.to_owned(),
            dsl_source_hash: "sha256:market".to_owned(),
            function_id: "MarketLab".to_owned(),
            seed: 1,
            days: 2,
            evaluated_at_day: 1,
            inputs: BTreeMap::from([("liquidity_shock".to_owned(), 0.0)]),
            events: BTreeSet::new(),
            artifact: Some(learned.artifact),
            force_relearn: false,
        },
    )
    .unwrap();
    assert!(cached.cache_hit);
    assert_eq!(cached.agent_ticks, 0);
    assert!(
        cached
            .reports
            .iter()
            .any(|report| report.id == "market_summary")
    );
    assert!(
        cached
            .time_series
            .last()
            .is_some_and(|point| point.outputs["mean_price"].mean > 1.0)
    );
}
