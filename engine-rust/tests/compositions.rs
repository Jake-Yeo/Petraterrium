use petraterrium_engine::text_dsl::{
    AggregateEvaluationProtocolRequest, DslReportValue, evaluate_aggregate_function, parse_program,
    run_composition, run_expanded_archetype_population,
};
use std::collections::{BTreeMap, BTreeSet};

const COMPOSED: &str = r#"program GenericComposition version "1.0":
  tick_hours = 1 placeholder
  placeholder = "placeholder — agent knowledge, for demo only, to be replaced by research"
  uncertainty = wide
  record_actions = true
  results_title = "Generic composition"
  results_subtitle = "Synthetic"

output overview:
  title = "Overview"
  group_by = all
  display = cards
  record = final
  column population = count() label "Population" format integer
  column money = mean(money) label "Money" format number
  column stress = mean(stress) label "Stress" format decimal
  column contacts = action_count(contacts, window=run) label "Contacts" format integer

place Local:
  state contacts = 0 range 0..100000 placeholder

place Shared:
  state contacts = 0 range 0..100000 placeholder

agent Person:
  trait vote
  trait kids
  state money range 0..100 placeholder
  state stress range 0..1 placeholder
  state health range 0..1 placeholder
  state location
  initial:
    vote ~ Uniform(min=0.5, max=0.5) placeholder
    kids ~ Uniform(min=1, max=1) placeholder
    money ~ Uniform(min=10, max=10) placeholder
    stress ~ Uniform(min=0.2, max=0.2) placeholder
    health ~ Uniform(min=0.8, max=0.8) placeholder
    location ~ Categorical(Local: 1.0) placeholder
  routine = choose_contact

population:
  size = 1 placeholder
  mix:
    Person = 1.0 placeholder

decision choose_contact:
  branch meet_shared p = 1 if location == Shared placeholder
  branch meet_local p = 1 placeholder

action meet_shared:
  aggregate = contacts
  target = random at Shared where agent != self
  duration = Triangular(min=0.1, median=0.2, max=0.3) placeholder
  outcome met p = 1 placeholder:
    effect self.stress -= 0.01 placeholder
    effect target.stress -= 0.01 placeholder
    effect relationship with target trust += 1 placeholder
    effect place Shared contacts += 1 placeholder
    next = choose_contact

action meet_local:
  aggregate = contacts
  target = random at Local where agent != self
  duration = Triangular(min=0.1, median=0.2, max=0.3) placeholder
  outcome met p = 1 placeholder:
    effect self.stress -= 0.01 placeholder
    effect target.stress -= 0.01 placeholder
    effect relationship with target trust += 1 placeholder
    effect place Local contacts += 1 placeholder
    next = choose_contact

archetype Alpha:
  sample_households = 50
  composition:
    members count = 1 mix Person:1.0
  initial:
    vote ~ Uniform(min=0.8, max=0.8)
    kids ~ Uniform(min=1, max=1)
    money ~ Uniform(min=10, max=10)
    stress ~ Uniform(min=0.2, max=0.2)
    health ~ Uniform(min=0.9, max=0.9)
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output mean_health = mean(health)
  output mean_kids = mean(kids)

archetype Beta:
  sample_households = 50
  composition:
    members count = 1 mix Person:1.0
  initial:
    vote ~ Uniform(min=0.2, max=0.2)
    kids ~ Uniform(min=2, max=2)
    money ~ Uniform(min=20, max=20)
    stress ~ Uniform(min=0.4, max=0.4)
    health ~ Uniform(min=0.7, max=0.7)
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output mean_health = mean(health)
  output mean_kids = mean(kids)

archetype Gamma:
  sample_households = 50
  composition:
    members count = 1 mix Person:1.0
  initial:
    vote ~ Uniform(min=0.5, max=0.5)
    kids ~ Uniform(min=3, max=3)
    money ~ Uniform(min=30, max=30)
    stress ~ Uniform(min=0.3, max=0.3)
    health ~ Uniform(min=0.8, max=0.8)
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output mean_health = mean(health)
  output mean_kids = mean(kids)

composition LowerA:
  level = invented_lower
  children:
    Alpha: weight = 1
  places = Local
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd

composition LowerB:
  level = invented_lower
  children:
    Beta: weight = 1
  places = Local
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd

composition LowerC:
  level = invented_lower
  children:
    Gamma: weight = 1
  places = Local
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd

composition MiddleOne:
  level = invented_middle
  children:
    LowerA: weight = 60
    LowerB: weight = 30
    LowerC: weight = 10
  institutions = Shared
  adjacency:
    LowerA <-> LowerB distance = 1
    LowerB <-> LowerC distance = 2
  flows:
    visit_a LowerA -> LowerB rate = 0.50 effect = visit via Shared
    visit_b LowerB -> LowerA rate = 0.50 effect = visit via Shared
    move_b LowerB -> LowerA rate = 0.20 effect = transfer
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output contacts = action_count(contacts, window=run)
  output visit_rate = flow_rate(visit_a)
  output migration_rate = flow_rate(move_b)

composition MiddleTwo:
  level = invented_middle
  children:
    LowerA: weight = 20
    LowerB: weight = 50
    LowerC: weight = 30
  institutions = Shared
  adjacency:
    LowerA <-> LowerB distance = 1
    LowerB <-> LowerC distance = 2
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output contacts = action_count(contacts, window=run)

composition Upper:
  level = invented_upper
  children:
    MiddleOne: weight = 60
    MiddleTwo: weight = 40
  institutions = Shared
  adjacency:
    MiddleOne <-> MiddleTwo distance = 1
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output contacts = action_count(contacts, window=run)

population FullIndividuals:
  Alpha: weight = 1
  Beta: weight = 1
  Gamma: weight = 1

composition FlatTown:
  level = synthetic_town
  children:
    Alpha: weight = 1
    Beta: weight = 1
    Gamma: weight = 1
  places = Local
  adjacency:
    Alpha <-> Beta distance = 1
  flows:
    commute Alpha -> Beta rate = 0.00 effect = visit via Local
  output population = count()
  output mean_income = mean(money) with sd
  output mean_stress = mean(stress) with sd
  output vote_share = mean(vote) with sd
  output mean_health = mean(health)
  output mean_kids_per_family = mean(kids)
  output contacts = action_count(contacts, window=run)
  output commuting_rate = flow_rate(commute)

aggregate_function MiddleOne:
  inputs:
    shock = 0 range 0..1
  time = 2 days
  time_points = 1, 2
  effects:
    field money *= 1 + shock
    field stress += shock * 0.1
  outputs:
    population = formula(shock)
    mean_income = formula(shock)
    mean_stress = formula(shock)
    vote_share = formula(shock)
    contacts = formula(shock)
    visit_rate = formula(shock)
    migration_rate = formula(shock)
  cache:
    valid_for = 30 days
    inputs_hash = hash(shock)
    invalidate_on:
      shock change > 0.2
      event = disruption
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

fn number(row: &petraterrium_engine::text_dsl::DslReportRow, id: &str) -> f64 {
    match row.values[id] {
        DslReportValue::Number(value) => value,
        _ => panic!("expected numeric report value"),
    }
}

#[test]
fn parser_uses_one_generic_type_for_arbitrary_levels_and_named_errors() {
    let program = parse_program(COMPOSED).unwrap();
    assert_eq!(program.compositions.len(), 7);
    assert_eq!(program.compositions[3].level, "invented_middle");

    let bad_child = COMPOSED.replacen("LowerA: weight = 60", "Missing: weight = 60", 1);
    let error = parse_program(&bad_child).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_COMPOSITION_CHILD");
    assert!(error.line > 0);

    let bad_place = COMPOSED.replacen("institutions = Shared", "institutions = Missing", 1);
    let error = parse_program(&bad_place).unwrap_err();
    assert_eq!(error.code, "UNKNOWN_COMPOSITION_PLACE");
    assert!(error.line > 0);
}

#[test]
fn nested_weighting_matches_hand_calculated_means_without_expansion() {
    let program = parse_program(COMPOSED).unwrap();
    let middle = run_composition(program.clone(), "MiddleOne", 1, 0).unwrap();
    let upper = run_composition(program, "Upper", 1, 0).unwrap();
    let middle_row = &report(&middle, "compositions").snapshots[0].rows[0];
    let upper_row = &report(&upper, "compositions").snapshots[0].rows[0];
    assert_eq!(middle.state.agents.len(), 150);
    assert_eq!(upper.state.agents.len(), 150);
    assert!((number(middle_row, "mean_income") - 15.0).abs() < 1e-12);
    assert!((number(upper_row, "mean_income") - 17.4).abs() < 1e-12);
}

#[test]
fn shared_place_flows_and_adjacency_preserve_agents_and_relationships() {
    let program = parse_program(COMPOSED).unwrap();
    let baseline_source = COMPOSED.replace(
        "move_b LowerB -> LowerA rate = 0.20",
        "move_b LowerB -> LowerA rate = 0.00",
    );
    let before =
        run_composition(parse_program(&baseline_source).unwrap(), "MiddleOne", 1, 0).unwrap();
    let moved = run_composition(program.clone(), "MiddleOne", 1, 0).unwrap();
    let result = run_composition(program, "MiddleOne", 1, 3).unwrap();
    assert_eq!(before.state, moved.state);
    assert_eq!(moved.state.agents.len(), result.state.agents.len());
    assert_eq!(
        before
            .state
            .agents
            .iter()
            .map(|agent| &agent.id)
            .collect::<BTreeSet<_>>(),
        result
            .state
            .agents
            .iter()
            .map(|agent| &agent.id)
            .collect::<BTreeSet<_>>()
    );
    let cross = &report(&result, "cross_composition_interactions").snapshots[0].rows;
    assert!(
        cross
            .iter()
            .any(|row| row.group_id.contains("LowerA") && row.group_id.contains("LowerB"))
    );
    assert!(cross.iter().all(|row| !row.group_id.contains("LowerC")));
    let flows = &report(&result, "composition_flows").snapshots[0].rows;
    assert!(
        flows
            .iter()
            .any(|row| row.group_id == "visit_a" && number(row, "count") > 0.0)
    );
    assert!(
        flows
            .iter()
            .any(|row| row.group_id == "move_b" && number(row, "count") > 0.0)
    );
    let before_children = &report(&before, "composition_children").snapshots[0].rows;
    let moved_children = &report(&moved, "composition_children").snapshots[0].rows;
    let child_population = |rows: &[petraterrium_engine::text_dsl::DslReportRow], id: &str| {
        number(
            rows.iter().find(|row| row.group_id == id).unwrap(),
            "population",
        )
    };
    assert!(
        child_population(moved_children, "LowerA") > child_population(before_children, "LowerA")
    );
    assert!(
        child_population(moved_children, "LowerB") < child_population(before_children, "LowerB")
    );
    assert!(result.state.relationships.iter().any(|relationship| {
        let source = result
            .state
            .agents
            .iter()
            .find(|agent| agent.id == relationship.source_id)
            .unwrap();
        let target = result
            .state
            .agents
            .iter()
            .find(|agent| agent.id == relationship.target_id)
            .unwrap();
        source.agent_type.split("__").next() != target.agent_type.split("__").next()
    }));
    let root_contacts = number(
        &report(&result, "compositions").snapshots[0].rows[0],
        "contacts",
    );
    let child_contacts = report(&result, "composition_children").snapshots[0]
        .rows
        .iter()
        .map(|row| number(row, "contacts"))
        .sum::<f64>();
    assert_eq!(child_contacts, root_contacts);
}

#[test]
fn composition_cache_hits_with_zero_agent_ticks() {
    let program = parse_program(COMPOSED).unwrap();
    let request = AggregateEvaluationProtocolRequest {
        source: COMPOSED.to_owned(),
        dsl_source_hash: "sha256:composition".to_owned(),
        function_id: "MiddleOne".to_owned(),
        seed: 1,
        days: 2,
        evaluated_at_day: 0,
        inputs: BTreeMap::from([("shock".to_owned(), 0.0)]),
        events: BTreeSet::new(),
        artifact: None,
        force_relearn: false,
    };
    let learned = evaluate_aggregate_function(program.clone(), request).unwrap();
    let cached = evaluate_aggregate_function(
        program,
        AggregateEvaluationProtocolRequest {
            artifact: Some(learned.artifact),
            ..AggregateEvaluationProtocolRequest {
                source: COMPOSED.to_owned(),
                dsl_source_hash: "sha256:composition".to_owned(),
                function_id: "MiddleOne".to_owned(),
                seed: 1,
                days: 2,
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
    assert_eq!(cached.time_series.len(), 2);
}

#[test]
fn composed_town_matches_expanded_individual_run_within_tolerance() {
    let source = COMPOSED.replace("sample_households = 50", "sample_households = 100");
    let program = parse_program(&source).unwrap();
    let expanded =
        run_expanded_archetype_population(program.clone(), "FullIndividuals", 1, 30 * 24).unwrap();
    let composed = run_composition(program, "FlatTown", 1, 30 * 24).unwrap();
    assert_eq!(expanded.state.agents.len(), 300);
    assert_eq!(composed.state.agents.len(), 300);
    let composed_row = &report(&composed, "compositions").snapshots[0].rows[0];
    let expanded_row = &report(&expanded, "overview").snapshots[0].rows[0];
    for (composed_id, expanded_id) in [
        ("population", "population"),
        ("mean_income", "money"),
        ("mean_stress", "stress"),
        ("contacts", "contacts"),
    ] {
        let actual = number(composed_row, composed_id);
        let expected = number(expanded_row, expanded_id);
        assert!((actual - expected).abs() / expected.abs().max(1.0) <= 0.10);
    }
    let composed_vote = number(composed_row, "vote_share");
    let state_mean = |field: &str| {
        expanded
            .state
            .agents
            .iter()
            .filter_map(|agent| agent.value(field).and_then(|value| value.as_f64()))
            .sum::<f64>()
            / expanded.state.agents.len() as f64
    };
    let expanded_vote = state_mean("vote");
    assert!((composed_vote - expanded_vote).abs() / expanded_vote.abs().max(1e-12) <= 0.10);
    for (output, field) in [("mean_health", "health"), ("mean_kids_per_family", "kids")] {
        let actual = number(composed_row, output);
        let expected = state_mean(field);
        assert!((actual - expected).abs() / expected.abs().max(1e-12) <= 0.10);
    }
    assert_eq!(number(composed_row, "commuting_rate"), 0.0);
    let composed_cross = report(&composed, "cross_composition_interactions").snapshots[0]
        .rows
        .iter()
        .map(|row| number(row, "count"))
        .sum::<f64>();
    let expanded_cross = expanded
        .actions
        .iter()
        .filter(|action| {
            action
                .target_id
                .as_ref()
                .is_some_and(|target| action.agent_id.split('-').next() != target.split('-').next())
        })
        .count() as f64;
    assert!((composed_cross - expanded_cross).abs() / expanded_cross.max(1.0) <= 0.10);
}
