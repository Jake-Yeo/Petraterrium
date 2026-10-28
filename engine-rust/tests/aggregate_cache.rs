use petraterrium_engine::text_dsl::{
    AggregateEvaluationProtocolRequest, LearnedAggregateArtifact, evaluate_aggregate_function,
    parse_program,
};
use std::collections::{BTreeMap, BTreeSet};
use std::time::Instant;

const SYNTHETIC: &str = r#"program SyntheticCache version "1.0":
  tick_hours = 1 placeholder
  placeholder = "placeholder — agent knowledge, for demo only, to be replaced by research"
  uncertainty = wide
  record_actions = false
  results_title = "Synthetic"
  results_subtitle = "Synthetic cache"

output overview:
  title = "Overview"
  group_by = all
  display = cards
  record = final
  column population = count() label "Population" format integer
  column money = mean(money) label "Money" format number
  column stress = mean(stress) label "Stress" format decimal
  column health = mean(health) label "Health" format decimal

output places:
  title = "Places"
  group_by = place
  display = table
  record = final
  column population = count() label "Population" format integer
  column money = mean(money) label "Money" format number

output agent_types:
  title = "Agent types"
  group_by = agent_type
  display = table
  record = final
  column population = count() label "Population" format integer
  column money = mean(money) label "Money" format number

place Home:
  state calm = 1 range 0..1 placeholder

agent Person:
  trait vote
  state money range 0..100 placeholder
  state stress range 0..1 placeholder
  state health range 0..1 placeholder
  state location
  initial:
    vote ~ Uniform(min=0.4, max=0.4) placeholder
    money ~ Uniform(min=10, max=10) placeholder
    stress ~ Uniform(min=0.2, max=0.2) placeholder
    health ~ Uniform(min=0.8, max=0.8) placeholder
    location ~ Categorical(Home: 1.0) placeholder
  routine = daily

population:
  size = 1 placeholder
  mix:
    Person = 1.0 placeholder

decision daily:
  branch rest p = 1 placeholder

action rest:
  aggregate = rest
  duration = Triangular(min=0.1, median=0.2, max=0.3) placeholder
  outcome stayed p = 1 placeholder:
    effect self.stress += 0 placeholder
    next = daily

archetype SyntheticHousehold:
  sample_households = 4
  composition:
    members count = 1 mix Person:1.0
  initial:
    vote ~ Uniform(min=0.4, max=0.4)
    money ~ Uniform(min=10, max=10)
    stress ~ Uniform(min=0.2, max=0.2)
    health ~ Uniform(min=0.8, max=0.8)
  output mean_money = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output mean_health = mean(health) with sd

aggregate_function SyntheticHousehold:
  inputs:
    shock = 0.0 range 0.0..1.0
  time = 30 days
  time_points = 1, 30
  effects:
    field money *= 1 + shock
    field stress += shock * 0.2
    field vote += shock * 0.1
  outputs:
    mean_money = formula(shock)
    mean_stress = formula(shock)
    vote_share = formula(shock)
    mean_health = formula(shock)
  cache:
    valid_for = 30 days
    inputs_hash = hash(shock)
    invalidate_on:
      shock change > 0.20
      event = disaster, pandemic, election
"#;

fn request(
    artifact: Option<LearnedAggregateArtifact>,
    input: f64,
    day: u32,
    events: &[&str],
    source_hash: &str,
    days: u32,
) -> AggregateEvaluationProtocolRequest {
    AggregateEvaluationProtocolRequest {
        source: SYNTHETIC.to_owned(),
        dsl_source_hash: source_hash.to_owned(),
        function_id: "SyntheticHousehold".to_owned(),
        seed: 1,
        days,
        evaluated_at_day: day,
        inputs: BTreeMap::from([("shock".to_owned(), input)]),
        events: events.iter().map(|event| (*event).to_owned()).collect(),
        artifact,
        force_relearn: false,
    }
}

#[test]
fn parser_accepts_aggregate_function_and_rejects_bad_references() {
    let program = parse_program(SYNTHETIC).unwrap();
    assert_eq!(program.aggregate_functions.len(), 1);

    let bad_input = SYNTHETIC.replace(
        "mean_money = formula(shock)",
        "mean_money = formula(missing)",
    );
    let error = parse_program(&bad_input).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_AGGREGATE_INPUT");
    assert!(error.line > 0);

    let bad_output = SYNTHETIC.replace("mean_money = formula(shock)", "missing = formula(shock)");
    let error = parse_program(&bad_output).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_AGGREGATE_OUTPUT");
    assert!(error.line > 0);

    let bad_field = SYNTHETIC.replace("field money *=", "field missing *=");
    let error = parse_program(&bad_field).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_AGGREGATE_FIELD");
    assert!(error.line > 0);
}

#[test]
fn learning_varies_with_inputs_and_is_deterministic() {
    let program = parse_program(SYNTHETIC).unwrap();
    let first = evaluate_aggregate_function(
        program.clone(),
        request(None, 0.0, 0, &[], "sha256:one", 30),
    )
    .unwrap();
    let repeated =
        evaluate_aggregate_function(program, request(None, 0.0, 0, &[], "sha256:one", 30)).unwrap();
    assert_eq!(first.artifact, repeated.artifact);
    let low = first
        .artifact
        .points
        .iter()
        .find(|point| point.day == 30 && point.inputs["shock"] == 0.0)
        .unwrap();
    let high = first
        .artifact
        .points
        .iter()
        .find(|point| point.day == 30 && point.inputs["shock"] == 1.0)
        .unwrap();
    assert!(high.outputs["mean_money"].mean > low.outputs["mean_money"].mean);
    assert!(high.outputs["mean_stress"].mean > low.outputs["mean_stress"].mean);
}

#[test]
fn cache_hit_is_fast_and_threshold_invalidation_is_selective() {
    let program = parse_program(SYNTHETIC).unwrap();
    let learned = evaluate_aggregate_function(
        program.clone(),
        request(None, 0.0, 0, &[], "sha256:one", 30),
    )
    .unwrap();
    let started = Instant::now();
    let hit = evaluate_aggregate_function(
        program.clone(),
        request(
            Some(learned.artifact.clone()),
            0.0,
            10,
            &[],
            "sha256:one",
            30,
        ),
    )
    .unwrap();
    assert!(hit.cache_hit);
    assert_eq!(hit.agent_ticks, 0);
    assert_eq!(hit.time_series, learned.time_series);
    assert!(started.elapsed().as_secs_f64() < 0.1);

    let below_threshold = evaluate_aggregate_function(
        program.clone(),
        request(
            Some(learned.artifact.clone()),
            0.1,
            10,
            &[],
            "sha256:one",
            30,
        ),
    )
    .unwrap();
    assert!(below_threshold.cache_hit);
    assert_eq!(below_threshold.agent_ticks, 0);

    let invalidated = evaluate_aggregate_function(
        program,
        request(Some(learned.artifact), 0.5, 10, &[], "sha256:one", 30),
    )
    .unwrap();
    assert!(!invalidated.cache_hit);
    assert_eq!(
        invalidated.invalidation_reason.as_deref(),
        Some("input:shock")
    );
    assert!(invalidated.agent_ticks > 0);
    assert_ne!(hit.time_series.last(), invalidated.time_series.last());
}

#[test]
fn time_event_and_dsl_changes_each_invalidate_cache() {
    let program = parse_program(SYNTHETIC).unwrap();
    let learned = evaluate_aggregate_function(
        program.clone(),
        request(None, 0.0, 0, &[], "sha256:one", 30),
    )
    .unwrap();
    for (request, expected) in [
        (
            request(
                Some(learned.artifact.clone()),
                0.0,
                31,
                &[],
                "sha256:one",
                30,
            ),
            "valid_for_expired",
        ),
        (
            request(
                Some(learned.artifact.clone()),
                0.0,
                10,
                &["disaster"],
                "sha256:one",
                30,
            ),
            "event:disaster",
        ),
        (
            request(
                Some(learned.artifact.clone()),
                0.0,
                10,
                &[],
                "sha256:changed",
                30,
            ),
            "dsl_source_hash_changed",
        ),
    ] {
        let result = evaluate_aggregate_function(program.clone(), request).unwrap();
        assert!(!result.cache_hit);
        assert_eq!(result.invalidation_reason.as_deref(), Some(expected));
        assert!(result.agent_ticks > 0);
    }
}

#[test]
fn cached_accuracy_and_ninety_day_fast_forward_match_detailed_points() {
    let program = parse_program(SYNTHETIC).unwrap();
    let learned = evaluate_aggregate_function(
        program.clone(),
        request(None, 0.0, 0, &[], "sha256:one", 30),
    )
    .unwrap();
    let detailed = learned
        .artifact
        .points
        .iter()
        .find(|point| point.day == 30 && point.inputs["shock"] == 0.0)
        .unwrap();
    let cached = evaluate_aggregate_function(
        program,
        request(
            Some(learned.artifact.clone()),
            0.0,
            1,
            &[],
            "sha256:one",
            90,
        ),
    )
    .unwrap();
    assert!(cached.cache_hit);
    assert_eq!(cached.agent_ticks, 0);
    let days = cached
        .time_series
        .iter()
        .map(|point| point.day)
        .collect::<BTreeSet<_>>();
    assert!(BTreeSet::from([1, 30, 60, 90]).is_subset(&days));
    let endpoint = cached.time_series.last().unwrap();
    for id in ["mean_money", "mean_stress", "vote_share", "mean_health"] {
        let learned = &endpoint.outputs[id];
        let full = &detailed.outputs[id];
        let mean_error = (learned.mean - full.mean).abs() / full.mean.abs().max(1e-12);
        let sd_error = (learned.standard_deviation - full.standard_deviation).abs()
            / full.standard_deviation.abs().max(1e-12);
        assert!(mean_error <= 0.10, "{id} mean diverged by {mean_error}");
        assert!(sd_error <= 0.20, "{id} sd diverged by {sd_error}");
    }
    assert_eq!(endpoint.outputs, cached.time_series[1].outputs);
}
