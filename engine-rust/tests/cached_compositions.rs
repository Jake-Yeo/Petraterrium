use petraterrium_engine::text_dsl::{
    AggregateEvaluationProtocolRequest, CachedCompositionEvaluationResult,
    CachedCompositionProtocolRequest, CompositionCacheMetadata, DslReport, DslReportValue,
    evaluate_aggregate_function, evaluate_cached_composition, parse_program, run_composition,
};
use std::collections::{BTreeMap, BTreeSet};

const SOURCE: &str = include_str!("../dsl/cached_composition_test.dsl");

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
    artifacts: BTreeMap<String, petraterrium_engine::text_dsl::LearnedAggregateArtifact>,
) -> CachedCompositionProtocolRequest {
    CachedCompositionProtocolRequest {
        source: source.to_owned(),
        dsl_source_hash: hash(source),
        function_id: "Province".to_owned(),
        seed: 1,
        days,
        evaluated_at_day: 0,
        inputs: BTreeMap::from([("unemployment".to_owned(), 0.10), ("tax".to_owned(), 0.25)]),
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

fn report<'a>(result: &'a CachedCompositionEvaluationResult, id: &str) -> &'a DslReport {
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

fn no_feedback_source() -> String {
    SOURCE
        .replace(
            "mean_stress -> unemployment scale = 0.20",
            "mean_stress -> unemployment scale = 0.00",
        )
        .replace(
            "mean_stress -> unemployment scale = 0.15",
            "mean_stress -> unemployment scale = 0.00",
        )
        .replace("  effects:\n    field money *= 1 - tax * 0.10\n", "")
}

#[test]
fn cached_composition_parser_reports_named_line_errors() {
    let unknown = SOURCE.replacen("unemployment * 0.20", "missing_value * 0.20", 1);
    let error = parse_program(&unknown).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_COMPOSITION_FLOW_VALUE");
    assert!(error.line > 0);

    let iterations = SOURCE.replacen("max_iterations = 5", "max_iterations = 6", 1);
    let error = parse_program(&iterations).unwrap_err();
    assert_eq!(error.code, "INVALID_CACHED_COMPOSITION");
    assert!(error.line > 0);

    let feedback = SOURCE.replacen(
        "mean_stress -> unemployment scale = 0.20",
        "missing_output -> unemployment scale = 0.20",
        1,
    );
    let error = parse_program(&feedback).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_COMPOSITION_FEEDBACK_OUTPUT");
    assert!(error.line > 0);
}

#[test]
fn cached_parent_reuses_children_and_matches_weighted_outputs() {
    let source = no_feedback_source();
    let learned = evaluate(&source, request(&source, 1, BTreeMap::new()));
    assert!(learned.agent_ticks > 0);
    assert!(metadata(&learned.cache_tree, "NorthOne").detailed);
    let artifacts = learned.artifacts;
    let cached = evaluate(&source, request(&source, 1, artifacts.clone()));
    assert!(cached.cache_hit);
    assert_eq!(cached.agent_ticks, 0);
    assert_eq!(cached.cache_tree.children.len(), 2);
    assert!(metadata(&cached.cache_tree, "NorthOne").cached);
    assert!(metadata(&cached.cache_tree, "MetroNorth").cached);
    let endpoint = cached.time_series.last().unwrap();
    assert!((endpoint.outputs["mean_income"].mean - 20.75).abs() < 1e-9);
    assert_eq!(endpoint.outputs["population"].mean, 20.0);
    let repeated = evaluate(&source, request(&source, 1, artifacts));
    assert_eq!(cached.time_series, repeated.time_series);
    assert_eq!(cached.reports, repeated.reports);
    assert_eq!(repeated.agent_ticks, 0);
}

#[test]
fn missing_child_relearns_only_that_branch_without_silent_fallback() {
    let learned = evaluate(SOURCE, request(SOURCE, 1, BTreeMap::new()));
    let expected_ticks = learned.artifacts["NorthOne"].learning_agent_ticks;
    let mut artifacts = learned.artifacts;
    artifacts.remove("NorthOne");
    let result = evaluate(SOURCE, request(SOURCE, 1, artifacts));
    assert_eq!(result.agent_ticks, expected_ticks);
    assert!(!result.cache_hit);
    assert!(metadata(&result.cache_tree, "NorthOne").detailed);
    assert!(metadata(&result.cache_tree, "NorthTwo").cached);
    assert!(metadata(&result.cache_tree, "MetroSouth").cached);
    assert!(!metadata(&result.cache_tree, "Province").detailed);
}

#[test]
fn child_cache_reuse_reduces_parent_learning_ticks() {
    let program = parse_program(SOURCE).unwrap();
    let detailed = evaluate_aggregate_function(
        program,
        AggregateEvaluationProtocolRequest {
            source: SOURCE.to_owned(),
            dsl_source_hash: hash(SOURCE),
            function_id: "MetroNorth".to_owned(),
            seed: 1,
            days: 30,
            evaluated_at_day: 0,
            inputs: BTreeMap::from([("unemployment".to_owned(), 0.10), ("tax".to_owned(), 0.25)]),
            events: BTreeSet::new(),
            artifact: None,
            force_relearn: false,
        },
    )
    .unwrap();
    let first = evaluate(SOURCE, request(SOURCE, 1, BTreeMap::new()));
    let cached = evaluate(SOURCE, request(SOURCE, 1, first.artifacts));
    assert_eq!(cached.agent_ticks, 0);
    assert!(detailed.agent_ticks > cached.agent_ticks);
    eprintln!(
        "parent learning ticks: detailed={} cached_children={}",
        detailed.agent_ticks, cached.agent_ticks
    );
}

#[test]
fn flows_recalculate_daily_and_parameter_changes_invalidate_one_branch() {
    let first = evaluate(SOURCE, request(SOURCE, 30, BTreeMap::new()));
    let mut scheduled = request(SOURCE, 30, first.artifacts.clone());
    scheduled
        .input_schedule
        .push(petraterrium_engine::text_dsl::ScheduledAggregateInputs {
            day: 15,
            values: BTreeMap::from([("unemployment".to_owned(), 0.80)]),
        });
    let changed = evaluate(SOURCE, scheduled);
    let flows = report(&changed, "composition_flows");
    assert_eq!(flows.snapshots.len(), 30);
    let rate = |day: u64| {
        let snapshot = flows
            .snapshots
            .iter()
            .find(|item| item.tick == day)
            .unwrap();
        let row = snapshot
            .rows
            .iter()
            .find(|row| row.group_id == "Province:division_visit")
            .unwrap();
        number(&row.values["rate"])
    };
    assert!(rate(15) > rate(14));

    let baseline_income = first
        .time_series
        .iter()
        .find(|point| point.day == 1)
        .unwrap()
        .outputs["mean_income"]
        .mean;
    let baseline_rate = number(
        &report(&first, "composition_flows").snapshots[0]
            .rows
            .iter()
            .find(|row| row.group_id == "MetroNorth:commute")
            .unwrap()
            .values["rate"],
    );
    let mut parameter_change = request(SOURCE, 1, first.artifacts);
    parameter_change.branch_inputs.insert(
        "MetroNorth".to_owned(),
        BTreeMap::from([("tax".to_owned(), 0.35)]),
    );
    let parameter_result = evaluate(SOURCE, parameter_change);
    assert!(!metadata(&parameter_result.cache_tree, "MetroNorth").cached);
    assert!(metadata(&parameter_result.cache_tree, "MetroSouth").cached);
    assert!(!metadata(&parameter_result.cache_tree, "Province").cached);
    assert_eq!(parameter_result.agent_ticks, 0);
    assert!(
        parameter_result.time_series.last().unwrap().outputs["mean_income"].mean < baseline_income
    );
    let changed_rate = number(
        &report(&parameter_result, "composition_flows").snapshots[0]
            .rows
            .iter()
            .find(|row| row.group_id == "MetroNorth:commute")
            .unwrap()
            .values["rate"],
    );
    assert!(changed_rate > baseline_rate);
}

#[test]
fn branch_invalidation_propagates_only_to_ancestors() {
    let first = evaluate(SOURCE, request(SOURCE, 1, BTreeMap::new()));
    let north_ticks = first.artifacts["NorthOne"].learning_agent_ticks;
    let mut changed_request = request(SOURCE, 1, first.artifacts);
    changed_request.branch_inputs.insert(
        "NorthOne".to_owned(),
        BTreeMap::from([("unemployment".to_owned(), 0.80)]),
    );
    let changed = evaluate(SOURCE, changed_request);
    assert_eq!(changed.agent_ticks, north_ticks);
    assert!(metadata(&changed.cache_tree, "NorthOne").detailed);
    assert!(!metadata(&changed.cache_tree, "MetroNorth").cached);
    assert!(!metadata(&changed.cache_tree, "Province").cached);
    assert!(metadata(&changed.cache_tree, "NorthTwo").cached);
    assert!(metadata(&changed.cache_tree, "MetroSouth").cached);
    assert!(metadata(&changed.cache_tree, "SouthOne").cached);
    assert!(metadata(&changed.cache_tree, "SouthTwo").cached);
}

#[test]
fn feedback_converges_and_ninety_day_fast_forward_evolves() {
    let first = evaluate(SOURCE, request(SOURCE, 1, BTreeMap::new()));
    let mut long_request = request(SOURCE, 90, first.artifacts);
    long_request
        .input_schedule
        .push(petraterrium_engine::text_dsl::ScheduledAggregateInputs {
            day: 30,
            values: BTreeMap::from([("unemployment".to_owned(), 0.80)]),
        });
    let result = evaluate(SOURCE, long_request);
    assert!(result.feedback_iterations <= 5);
    assert!(result.feedback_change_percent < 1.0);
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
    assert!(day_90 < day_30);
}

#[test]
fn division_flows_create_inter_child_interactions_generically() {
    let program = parse_program(SOURCE).unwrap();
    let with_flows = run_composition(program, "Province", 1, 2).unwrap();
    let cross = with_flows
        .reports
        .iter()
        .find(|report| report.id == "cross_composition_interactions")
        .unwrap();
    let with_count = cross.snapshots[0]
        .rows
        .iter()
        .map(|row| number(&row.values["count"]))
        .sum::<f64>();
    assert!(with_count > 0.0);

    let without = SOURCE
        .replacen(
            "composition Province:\n  level = synthetic_division\n  children:\n    MetroNorth: weight = 3\n    MetroSouth: weight = 1\n  places = Shared",
            "composition Province:\n  level = synthetic_division\n  children:\n    MetroNorth: weight = 3\n    MetroSouth: weight = 1",
            1,
        )
        .replace(
            "  flows:\n    division_visit MetroNorth -> MetroSouth rate = formula(clamp(0.10 + unemployment * 0.10 + tax * 0.04, 0, 0.40)) effect = visit via Shared\n    division_transfer MetroSouth -> MetroNorth rate = formula(clamp(0.01 + unemployment * 0.02, 0, 0.10)) effect = transfer\n",
            "",
        )
        .replace("  output commuting_rate = flow_rate(division_visit)\n", "")
        .replace("  output migration_rate = flow_rate(division_transfer)\n", "")
        .replace("    commuting_rate = formula(unemployment, tax)\n", "")
        .replace("    migration_rate = formula(unemployment, tax)\n", "");
    let without_flows =
        run_composition(parse_program(&without).unwrap(), "Province", 1, 2).unwrap();
    let cross = without_flows
        .reports
        .iter()
        .find(|report| report.id == "cross_composition_interactions")
        .unwrap();
    assert!(cross.snapshots[0].rows.is_empty());
}

#[test]
fn cached_composition_matches_detailed_three_hundred_agent_run() {
    let source = no_feedback_source()
        .replace("sample_households = 5", "sample_households = 75")
        .replace(
            "division_visit MetroNorth -> MetroSouth rate = formula(clamp(0.10 + unemployment * 0.10 + tax * 0.04, 0, 0.40))",
            "division_visit MetroNorth -> MetroSouth rate = 0.75",
        )
        .replace(
            "division_transfer MetroSouth -> MetroNorth rate = formula(clamp(0.01 + unemployment * 0.02, 0, 0.10))",
            "division_transfer MetroSouth -> MetroNorth rate = 0.00",
        )
        .replace(
            "migration NorthTwo -> NorthOne rate = formula(clamp(0.01 + unemployment * 0.04, 0, 0.20))",
            "migration NorthTwo -> NorthOne rate = 0.00",
        )
        .replace(
            "migration SouthTwo -> SouthOne rate = formula(clamp(0.01 + unemployment * 0.03, 0, 0.20))",
            "migration SouthTwo -> SouthOne rate = 0.00",
        );
    let program = parse_program(&source).unwrap();
    let detailed = run_composition(program.clone(), "Province", 1, 30).unwrap();
    assert_eq!(detailed.state.agents.len(), 300);
    let mut initial = request(&source, 30, BTreeMap::new());
    initial.inputs.insert("unemployment".to_owned(), 0.0);
    let learned = evaluate(&source, initial);
    let mut cached_request = request(&source, 30, learned.artifacts);
    cached_request.inputs.insert("unemployment".to_owned(), 0.0);
    let cached = evaluate(&source, cached_request);
    assert_eq!(cached.agent_ticks, 0);
    let root = detailed
        .reports
        .iter()
        .find(|report| report.id == "compositions")
        .unwrap()
        .snapshots
        .last()
        .unwrap()
        .rows
        .first()
        .unwrap();
    let endpoint = &cached.time_series.last().unwrap().outputs;
    for (id, detailed_id) in [
        ("population", "population"),
        ("mean_income", "mean_income"),
        ("mean_stress", "mean_stress"),
        ("vote_share", "vote_share"),
        ("fights_per_day", "fights_per_day"),
        ("commuting_rate", "commuting_rate"),
    ] {
        let actual = endpoint[id].mean;
        let expected = number(&root.values[detailed_id]);
        assert!(
            (actual - expected).abs() / expected.abs().max(1.0) <= 0.10,
            "{id}: {actual} vs {expected}"
        );
    }
    let detailed_cross = detailed
        .reports
        .iter()
        .find(|report| report.id == "cross_composition_interactions")
        .unwrap()
        .snapshots[0]
        .rows
        .iter()
        .map(|row| number(&row.values["count"]))
        .sum::<f64>()
        / detailed.actions.len() as f64;
    let cached_cross = report(&cached, "cross_composition_interactions").snapshots[0]
        .rows
        .iter()
        .find(|row| row.group_id == "MetroNorth → MetroSouth")
        .map(|row| number(&row.values["rate"]))
        .unwrap();
    assert!((cached_cross - detailed_cross).abs() / detailed_cross.max(1e-9) <= 0.10);
}
