use petraterrium_engine::text_dsl::{
    DslReportValue, parse_program, run_expanded_archetype_population, run_weighted_population,
};

const SYNTHETIC: &str = r#"program SyntheticArchetypes version "1.0":
  tick_hours = 1 placeholder
  placeholder = "placeholder — agent knowledge, for demo only, to be replaced by research"
  uncertainty = wide
  record_actions = false
  results_title = "Synthetic"
  results_subtitle = "Synthetic archetypes"

output places:
  title = "Places"
  group_by = place
  display = table
  record = final
  column population = count() label "Population" format integer
  column money = mean(money) label "Money" format number
  column stress = mean(stress) label "Stress" format decimal

output agent_types:
  title = "Agent types"
  group_by = agent_type
  display = table
  record = final
  column population = count() label "Population" format integer
  column money = mean(money) label "Money" format number
  column stress = mean(stress) label "Stress" format decimal

place Home:
  state calm = 1 range 0..1 placeholder

agent Person:
  trait age
  trait vote
  trait kids
  trait has_family
  state money range 0..100 placeholder
  state stress range 0..1 placeholder
  state health range 0..1 placeholder
  state location
  initial:
    age ~ Uniform(min=30, max=30) placeholder
    vote ~ Bernoulli(p=0.5) placeholder
    kids ~ Uniform(min=1, max=1) placeholder
    has_family ~ Bernoulli(p=1) placeholder
    money ~ Uniform(min=15, max=15) placeholder
    stress ~ Uniform(min=0.5, max=0.5) placeholder
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

archetype Alpha:
  sample_households = 1
  composition:
    members count = 1 mix Person:1.0
  initial:
    age ~ Uniform(min=30, max=30)
    vote ~ Bernoulli(p=1)
    kids ~ Uniform(min=1, max=1)
    has_family ~ Bernoulli(p=1)
    money ~ Uniform(min=10, max=10)
    stress ~ Uniform(min=0.2, max=0.2)
    health ~ Uniform(min=0.9, max=0.9)
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_share = mean(vote) with sd
  output mean_kids_per_family = mean(kids)

archetype Beta:
  sample_households = 1
  composition:
    members count = 1 mix Person:1.0
  initial:
    age ~ Uniform(min=40, max=40)
    vote ~ Bernoulli(p=0)
    kids ~ Uniform(min=2, max=2)
    has_family ~ Bernoulli(p=1)
    money ~ Uniform(min=20, max=20)
    stress ~ Uniform(min=0.8, max=0.8)
    health ~ Uniform(min=0.7, max=0.7)
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_share = mean(vote) with sd
  output mean_kids_per_family = mean(kids)

archetype Gamma:
  sample_households = 1
  composition:
    members count = 1 mix Person:1.0
  initial:
    age ~ Uniform(min=35, max=35)
    vote ~ Bernoulli(p=0.5)
    kids ~ Uniform(min=3, max=3)
    has_family ~ Bernoulli(p=1)
    money ~ Uniform(min=30, max=30)
    stress ~ Uniform(min=0.5, max=0.5)
    health ~ Uniform(min=0.8, max=0.8)
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output mean_health = mean(health)
  output vote_share = mean(vote) with sd
  output mean_kids_per_family = mean(kids)

population WeightedSmall:
  Alpha: weight = 2
  Beta: weight = 3

population WeightedMillion:
  Alpha: weight = 1000000

population ComparisonTown:
  Alpha: weight = 100
  Beta: weight = 100
  Gamma: weight = 100
"#;

fn summary_value(result: &petraterrium_engine::text_dsl::DslRunResult, id: &str) -> f64 {
    match result.reports[0].snapshots[0].rows[0].values[id] {
        DslReportValue::Number(value) => value,
        _ => panic!("expected numeric summary"),
    }
}

#[test]
fn synthetic_archetype_parses_and_bad_agent_reference_has_named_line_error() {
    let program = parse_program(SYNTHETIC).unwrap();
    assert_eq!(program.archetypes.len(), 3);
    assert_eq!(program.weighted_populations.len(), 3);

    let invalid = SYNTHETIC.replacen("mix Person:1.0", "mix Missing:1.0", 1);
    let error = parse_program(&invalid).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_ARCHETYPE_AGENT");
    assert!(error.line > 0);
}

#[test]
fn weights_two_and_three_match_hand_computed_means() {
    let program = parse_program(SYNTHETIC).unwrap();
    let result = run_weighted_population(program, "WeightedSmall", 1, 1).unwrap();

    assert_eq!(summary_value(&result, "total_population"), 5.0);
    assert_eq!(summary_value(&result, "mean_income"), 16.0);
    assert!((summary_value(&result, "mean_income_sd") - 24.0_f64.sqrt()).abs() < 1e-12);
    assert!((summary_value(&result, "mean_stress") - 0.56).abs() < 1e-12);
    assert!((summary_value(&result, "vote_share") - 0.4).abs() < 1e-12);
    assert_eq!(summary_value(&result, "mean_kids_per_family"), 1.6);
}

#[test]
fn million_household_weight_does_not_expand_simulated_objects() {
    let program = parse_program(SYNTHETIC).unwrap();
    let result = run_weighted_population(program, "WeightedMillion", 1, 1).unwrap();

    assert_eq!(summary_value(&result, "total_population"), 1_000_000.0);
    assert_eq!(result.state.agents.len(), 1);
}

#[test]
fn weighted_and_expanded_three_archetype_towns_match_within_ten_percent() {
    let source = SYNTHETIC
        .replace("sample_households = 1", "sample_households = 100")
        .replace("Alpha: weight = 1000000", "Alpha: weight = 100");
    let program = parse_program(&source).unwrap();
    let weighted = run_weighted_population(program.clone(), "ComparisonTown", 1, 30 * 24).unwrap();
    let expanded =
        run_expanded_archetype_population(program, "ComparisonTown", 1, 30 * 24).unwrap();
    assert_eq!(expanded.state.agents.len(), 300);

    let expanded_mean = |field: &str| {
        expanded
            .state
            .agents
            .iter()
            .filter_map(|agent| agent.value(field).and_then(|value| value.as_f64()))
            .sum::<f64>()
            / expanded.state.agents.len() as f64
    };
    for (summary, field) in [
        ("mean_income", "money"),
        ("mean_stress", "stress"),
        ("vote_share", "vote"),
        ("mean_kids_per_family", "kids"),
    ] {
        let expected = expanded_mean(field);
        let actual = summary_value(&weighted, summary);
        let relative_error = (actual - expected).abs() / expected.abs().max(1e-12);
        assert!(
            relative_error <= 0.10,
            "{summary} diverged: weighted={actual}, expanded={expected}"
        );
    }
    assert_eq!(summary_value(&weighted, "total_population"), 300.0);
    let archetype_rows = &weighted
        .reports
        .iter()
        .find(|report| report.id == "archetypes")
        .unwrap()
        .snapshots[0]
        .rows;
    for row in archetype_rows {
        let agents = expanded
            .state
            .agents
            .iter()
            .filter(|agent| agent.id.starts_with(&format!("{}-", row.group_id)))
            .collect::<Vec<_>>();
        for (summary, field) in [
            ("mean_income", "money"),
            ("mean_stress", "stress"),
            ("vote_share", "vote"),
            ("mean_kids_per_family", "kids"),
        ] {
            let expanded_mean = agents
                .iter()
                .filter_map(|agent| agent.value(field).and_then(|value| value.as_f64()))
                .sum::<f64>()
                / agents.len() as f64;
            let DslReportValue::Number(archetype_mean) = row.values[summary] else {
                panic!("expected numeric archetype summary");
            };
            let relative_error =
                (archetype_mean - expanded_mean).abs() / expanded_mean.abs().max(1e-12);
            assert!(
                relative_error <= 0.10,
                "{} {summary} diverged: archetype={archetype_mean}, expanded={expanded_mean}",
                row.group_id
            );
        }
    }
}

#[test]
fn weighted_execution_is_deterministic() {
    let program = parse_program(SYNTHETIC).unwrap();
    let first = run_weighted_population(program.clone(), "WeightedSmall", 91, 48).unwrap();
    let second = run_weighted_population(program, "WeightedSmall", 91, 48).unwrap();

    assert_eq!(first, second);
}
