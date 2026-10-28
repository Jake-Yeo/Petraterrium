use petraterrium_engine::text_dsl::{
    AggregateEvaluationProtocolRequest, DslReportValue, evaluate_aggregate_function, parse_program,
    run_neighbourhood, run_neighbourhood_monolith, run_weighted_neighbourhood_population,
};
use std::collections::{BTreeMap, BTreeSet};
use std::time::Instant;

const SYNTHETIC: &str = r#"program SyntheticNeighbourhood version "1.0":
  tick_hours = 1 placeholder
  placeholder = "placeholder — agent knowledge, for demo only, to be replaced by research"
  uncertainty = wide
  record_actions = true
  results_title = "Synthetic"
  results_subtitle = "Synthetic neighbourhood"

output overview:
  title = "Overview"
  group_by = all
  display = cards
  record = final
  column population = count() label "Population" format integer
  column money = mean(money) label "Money" format number
  column stress = mean(stress) label "Stress" format decimal
  column health = mean(health) label "Health" format decimal
  column fights = action_count(fights, window=run) label "Fights" format integer

output places:
  title = "Places"
  group_by = place
  display = table
  record = final
  column population = count() label "Population" format integer
  column noise = mean(stress) label "Stress" format decimal

output agent_types:
  title = "Agent types"
  group_by = agent_type
  display = table
  record = final
  column population = count() label "Population" format integer
  column money = mean(money) label "Money" format number

place Hub:
  state noise = 0 range 0..100000 placeholder

agent Person:
  trait vote
  trait kids
  state money range 0..100 placeholder
  state stress range 0..1 placeholder
  state health range 0..1 placeholder
  state energy range 0..100 placeholder
  state location
  initial:
    vote ~ Uniform(min=0.5, max=0.5) placeholder
    kids ~ Uniform(min=1, max=1) placeholder
    money ~ Uniform(min=15, max=15) placeholder
    stress ~ Uniform(min=0.2, max=0.2) placeholder
    health ~ Uniform(min=0.8, max=0.8) placeholder
    energy ~ Uniform(min=10, max=10) placeholder
    location ~ Categorical(Hub: 1.0) placeholder
  routine = meet

population:
  size = 1 placeholder
  mix:
    Person = 1.0 placeholder

decision meet:
  branch interact p = 1 placeholder

action interact:
  aggregate = fights
  target = random at Hub
  duration = Triangular(min=0.1, median=0.2, max=0.3) placeholder
  outcome met p = 1 placeholder:
    effect self.stress += 0.01 placeholder
    effect target.energy -= 1 placeholder
    effect relationship with target trust += 1 placeholder
    effect place Hub noise += 1 placeholder
    target_next = meet
    next = meet

archetype Red:
  sample_households = 5
  composition:
    members count = 1 mix Person:1.0
  initial:
    vote ~ Uniform(min=0.8, max=0.8)
    kids ~ Uniform(min=1, max=1)
    money ~ Uniform(min=10, max=10)
    stress ~ Uniform(min=0.2, max=0.2)
    health ~ Uniform(min=0.9, max=0.9)
    energy ~ Uniform(min=10, max=10)
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_share = mean(vote) with sd
  output mean_kids = mean(kids)

archetype Blue:
  sample_households = 5
  composition:
    members count = 1 mix Person:1.0
  initial:
    vote ~ Uniform(min=0.2, max=0.2)
    kids ~ Uniform(min=2, max=2)
    money ~ Uniform(min=20, max=20)
    stress ~ Uniform(min=0.4, max=0.4)
    health ~ Uniform(min=0.7, max=0.7)
    energy ~ Uniform(min=10, max=10)
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_share = mean(vote) with sd
  output mean_kids = mean(kids)

archetype Green:
  sample_households = 5
  composition:
    members count = 1 mix Person:1.0
  initial:
    vote ~ Uniform(min=0.5, max=0.5)
    kids ~ Uniform(min=3, max=3)
    money ~ Uniform(min=30, max=30)
    stress ~ Uniform(min=0.3, max=0.3)
    health ~ Uniform(min=0.8, max=0.8)
    energy ~ Uniform(min=10, max=10)
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_share = mean(vote) with sd
  output mean_kids = mean(kids)

neighbourhood WeightedPair:
  households:
    Red: weight = 60
    Blue: weight = 40
  places = Hub
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_share = mean(vote) with sd
  output mean_kids = mean(kids)
  output fights_per_day = action_count(fights, window=run)

neighbourhood SharedThree:
  households:
    Red: weight = 34
    Blue: weight = 33
    Green: weight = 33
  places = Hub
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_share = mean(vote) with sd
  output mean_kids = mean(kids)
  output fights_per_day = action_count(fights, window=run)

neighbourhood_population SyntheticDistricts:
  WeightedPair: weight = 2
  SharedThree: weight = 3

aggregate_function SharedThree:
  inputs:
    shock = 0 range 0..1
  time = 30 days
  time_points = 1, 30
  effects:
    field money *= 1 + shock
    field stress += shock * 0.1
  outputs:
    mean_income = formula(shock)
    mean_stress = formula(shock)
    mean_health = formula(shock)
    vote_share = formula(shock)
    mean_kids = formula(shock)
    fights_per_day = formula(shock)
  cache:
    valid_for = 30 days
    inputs_hash = hash(shock)
    invalidate_on:
      shock change > 0.2
      event = disaster, pandemic, election
"#;

fn report<'a>(
    result: &'a petraterrium_engine::text_dsl::DslRunResult,
    id: &str,
) -> &'a petraterrium_engine::text_dsl::DslReport {
    result
        .reports
        .iter()
        .find(|report| report.id == id)
        .unwrap()
}

#[test]
fn parser_validates_neighbourhood_references_with_named_line_errors() {
    let program = parse_program(SYNTHETIC).unwrap();
    assert_eq!(program.neighbourhoods.len(), 2);

    let bad_household = SYNTHETIC.replacen("Red: weight = 60", "Missing: weight = 60", 1);
    let error = parse_program(&bad_household).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_NEIGHBOURHOOD_HOUSEHOLD");
    assert!(error.line > 0);

    let bad_place = SYNTHETIC.replacen("places = Hub", "places = Missing", 1);
    let error = parse_program(&bad_place).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_NEIGHBOURHOOD_PLACE");
    assert!(error.line > 0);

    let bad_neighbourhood = SYNTHETIC.replace("WeightedPair: weight = 2", "Missing: weight = 2");
    let error = parse_program(&bad_neighbourhood).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_NEIGHBOURHOOD");
    assert!(error.line > 0);
}

#[test]
fn shared_places_create_cross_archetype_targets_effects_and_relationships() {
    let source = SYNTHETIC.replace("sample_households = 5", "sample_households = 1");
    let program = parse_program(&source).unwrap();
    let result = run_neighbourhood(program, "SharedThree", 1, 2).unwrap();
    let cross_action = result
        .actions
        .iter()
        .find(|action| {
            action
                .target_id
                .as_ref()
                .is_some_and(|target| action.agent_id.split('-').next() != target.split('-').next())
        })
        .unwrap();
    let target = result
        .state
        .agents
        .iter()
        .find(|agent| Some(&agent.id) == cross_action.target_id.as_ref())
        .unwrap();
    assert!(target.value("energy").unwrap().as_f64().unwrap() < 10.0);
    assert!(result.state.places[0].states["noise"].as_f64().unwrap() > 0.0);
    let relationship = result
        .state
        .relationships
        .iter()
        .find(|relationship| {
            relationship.source_id == cross_action.agent_id
                && Some(&relationship.target_id) == cross_action.target_id.as_ref()
        })
        .unwrap();
    assert!(relationship.values["trust"] >= 1.0);
    assert!(result.state.agents.iter().all(|agent| {
        agent
            .agent_type
            .rsplit_once("__")
            .is_some_and(|(namespace, _)| agent.current_decision.starts_with(namespace))
    }));
    assert!(
        !report(&result, "cross_archetype_interactions").snapshots[0]
            .rows
            .is_empty()
    );
}

#[test]
fn weighted_neighbourhood_composition_matches_hand_calculation_before_ticks() {
    let program = parse_program(SYNTHETIC).unwrap();
    let result = run_neighbourhood(program, "WeightedPair", 1, 0).unwrap();
    let row = &report(&result, "neighbourhoods").snapshots[0].rows[0];
    let DslReportValue::Number(mean_income) = row.values["mean_income"] else {
        panic!("expected numeric mean")
    };
    assert_eq!(result.state.agents.len(), 10);
    assert!((mean_income - 14.0).abs() < 1e-12);
}

#[test]
fn represented_neighbourhood_weights_do_not_expand_simulated_objects() {
    let program = parse_program(SYNTHETIC).unwrap();
    let result =
        run_weighted_neighbourhood_population(program, "SyntheticDistricts", 1, 0).unwrap();
    let summary = &report(&result, "neighbourhood_population_summary").snapshots[0].rows[0];
    assert_eq!(result.state.agents.len(), 25);
    assert_eq!(
        summary.values["total_population"],
        DslReportValue::Number(65.0)
    );
}

#[test]
fn place_index_scales_without_global_target_scan() {
    let small_source = SYNTHETIC.replace("sample_households = 5", "sample_households = 60");
    let large_source = SYNTHETIC.replace("sample_households = 5", "sample_households = 334");
    let started = Instant::now();
    let small =
        run_neighbourhood(parse_program(&small_source).unwrap(), "SharedThree", 3, 1).unwrap();
    let small_seconds = started.elapsed().as_secs_f64();
    let started = Instant::now();
    let large =
        run_neighbourhood(parse_program(&large_source).unwrap(), "SharedThree", 3, 1).unwrap();
    let large_seconds = started.elapsed().as_secs_f64();
    assert_eq!(small.state.agents.len(), 180);
    assert_eq!(large.state.agents.len(), 1002);
    assert!(large_seconds < small_seconds.max(1e-6) * 12.0);
    assert!(
        report(&large, "cross_archetype_interactions").snapshots[0]
            .rows
            .iter()
            .all(|row| row.values["selection_index"]
                == DslReportValue::Text("place_membership".to_owned()))
    );
    eprintln!("place-index timings: 180={small_seconds:.6}s 1002={large_seconds:.6}s");
}

#[test]
fn neighbourhood_cache_hits_without_ticks_and_invalidates_only_selected_branch() {
    let program = parse_program(SYNTHETIC).unwrap();
    let request = AggregateEvaluationProtocolRequest {
        source: SYNTHETIC.to_owned(),
        dsl_source_hash: "sha256:neighbourhood".to_owned(),
        function_id: "SharedThree".to_owned(),
        seed: 1,
        days: 30,
        evaluated_at_day: 0,
        inputs: BTreeMap::from([("shock".to_owned(), 0.0)]),
        events: BTreeSet::new(),
        artifact: None,
        force_relearn: false,
    };
    let learned = evaluate_aggregate_function(program.clone(), request).unwrap();
    let cached = evaluate_aggregate_function(
        program.clone(),
        AggregateEvaluationProtocolRequest {
            artifact: Some(learned.artifact.clone()),
            ..AggregateEvaluationProtocolRequest {
                source: SYNTHETIC.to_owned(),
                dsl_source_hash: "sha256:neighbourhood".to_owned(),
                function_id: "SharedThree".to_owned(),
                seed: 1,
                days: 90,
                evaluated_at_day: 1,
                inputs: BTreeMap::from([("shock".to_owned(), 0.0)]),
                events: BTreeSet::new(),
                artifact: None,
                force_relearn: false,
            }
        },
    )
    .unwrap();
    assert!(cached.cache_hit);
    assert_eq!(cached.agent_ticks, 0);
    assert!(
        BTreeSet::from([1, 30, 60, 90])
            .is_subset(&cached.time_series.iter().map(|point| point.day).collect())
    );
    let invalidated = evaluate_aggregate_function(
        program,
        AggregateEvaluationProtocolRequest {
            inputs: BTreeMap::from([("shock".to_owned(), 0.5)]),
            artifact: Some(learned.artifact),
            ..AggregateEvaluationProtocolRequest {
                source: SYNTHETIC.to_owned(),
                dsl_source_hash: "sha256:neighbourhood".to_owned(),
                function_id: "SharedThree".to_owned(),
                seed: 1,
                days: 30,
                evaluated_at_day: 1,
                inputs: BTreeMap::new(),
                events: BTreeSet::new(),
                artifact: None,
                force_relearn: false,
            }
        },
    )
    .unwrap();
    assert!(!invalidated.cache_hit);
    assert_eq!(
        invalidated.invalidation_reason.as_deref(),
        Some("input:shock")
    );
    assert_eq!(invalidated.agent_ticks, learned.agent_ticks);
}

#[test]
fn composed_neighbourhood_matches_monolith_and_is_deterministic() {
    let source = SYNTHETIC.replace("sample_households = 5", "sample_households = 100");
    let program = parse_program(&source).unwrap();
    let composed = run_neighbourhood(program.clone(), "SharedThree", 1, 30 * 24).unwrap();
    let repeated = run_neighbourhood(program.clone(), "SharedThree", 1, 30 * 24).unwrap();
    let monolith = run_neighbourhood_monolith(program, "SharedThree", 1, 30 * 24).unwrap();
    assert_eq!(composed, repeated);
    assert_eq!(composed.state, monolith.state);
    assert_eq!(composed.state.agents.len(), 300);
    let neighbourhood = &report(&composed, "neighbourhoods").snapshots[0].rows[0];
    let mean = |field: &str| {
        monolith
            .state
            .agents
            .iter()
            .filter_map(|agent| agent.value(field).and_then(|value| value.as_f64()))
            .sum::<f64>()
            / monolith.state.agents.len() as f64
    };
    for (output, field) in [
        ("mean_income", "money"),
        ("mean_stress", "stress"),
        ("vote_share", "vote"),
    ] {
        let DslReportValue::Number(actual) = neighbourhood.values[output] else {
            panic!("expected numeric output")
        };
        let expected = mean(field);
        assert!((actual - expected).abs() / expected.abs().max(1e-12) <= 0.10);
    }
    let DslReportValue::Number(fights) = neighbourhood.values["fights_per_day"] else {
        panic!("expected fight count")
    };
    assert!((fights - monolith.actions.len() as f64).abs() <= 1e-12);
    let composed_cross = report(&composed, "cross_archetype_interactions").snapshots[0]
        .rows
        .iter()
        .map(|row| match row.values["count"] {
            DslReportValue::Number(value) => value,
            _ => 0.0,
        })
        .sum::<f64>();
    let monolith_cross = monolith
        .actions
        .iter()
        .filter(|action| {
            action
                .target_id
                .as_ref()
                .is_some_and(|target| action.agent_id.split('-').next() != target.split('-').next())
        })
        .count() as f64;
    assert!((composed_cross - monolith_cross).abs() / monolith_cross.max(1.0) <= 0.10);
}
