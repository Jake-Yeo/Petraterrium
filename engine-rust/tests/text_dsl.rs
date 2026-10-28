use petraterrium_engine::text_dsl::{
    DecisionBranch, DslAgentTimeState, DslPlaceState, DslReportValue, DslRunRequest, DslRunState,
    DslValue, EffectDefinition, EffectScope, Expr, TargetSelector, parse_program, run_program,
    sample_population,
};
use std::collections::BTreeMap;

const SYNTHETIC: &str = r#"program Synthetic version "1.0":
  tick_hours = 1 placeholder
  placeholder = "placeholder — agent knowledge, for demo only, to be replaced by research"
  uncertainty = wide
  results_title = "Synthetic results"
  results_subtitle = "Defined by this test DSL"

output places:
  title = "Places"
  group_by = place
  display = table
  record = tick
  column population = count() label "Population" format integer
  column money = mean(money) label "Money" format number
  column travel = action_count(travel, window=tick) label "Travel" format integer
  column success = outcome_count(experiment.success, window=run) label "Success" format integer
  column actions = action_rates(per=1000, window=tick) label "Actions" format action_rates

output agent_types:
  title = "Agent types"
  group_by = agent_type
  display = cards
  record = final
  column population = count() label "Population" format integer

place Home:
  state calm = 0.8 placeholder

place Lab:
  state noise = 0.2 placeholder

agent Person:
  trait age
  trait aggression
  trait has_family
  trait has_spouse
  trait kids
  state stress
  state money
  state location
  initial:
    age ~ Normal(mean=40, sd=8, min=18, max=75) placeholder
    aggression ~ Beta(alpha=2, beta=5) placeholder
    stress ~ Normal(mean=0.4, sd=0.1, min=0, max=1) placeholder
    money ~ LogNormal(mean=7, sd=0.2, min=0, max=10000) placeholder
    has_family ~ Bernoulli(p=clamp((age - 20) / 40, 0, 0.8)) placeholder
    has_spouse ~ Bernoulli(p=0.7 if has_family else 0.0) placeholder
    kids ~ Poisson(lambda=clamp((age - 24) / 18, 0, 3) if has_family else 0, cap=5) placeholder
    location ~ Categorical(Home: 1.0) placeholder
  routine = choose

agent Student inherits Person:
  role learner
  initial:
    age ~ Normal(mean=20, sd=2, min=18, max=26) placeholder

agent Child inherits Person:
  initial:
    age ~ Uniform(min=0, max=17) placeholder

population:
  size = 20 placeholder
  mix:
    Person = 0.5 placeholder
    Student = 0.5 placeholder
  households:
    generate children where kids > 0:
      count = kids
      age ~ Uniform(min=0, max=max(0, age - 18)) placeholder
      type = Student if age > 5 else Child
      link = parent, household

decision choose:
  branch visit_lab p = 0.7 - stress * 0.2 placeholder
  branch stay_home p = 0.3 + stress * 0.2 placeholder

decision at_lab:
  branch experiment p = 0.8 placeholder
  branch return_home p = 0.2 placeholder

action visit_lab:
  aggregate = travel
  duration = Triangular(min=0.25, median=0.5, max=0.75) placeholder
  outcome arrive p = 1.0 placeholder:
    effect self.location = Lab placeholder
    next = at_lab

action stay_home:
  aggregate = home
  duration = Triangular(min=0.1, median=0.2, max=0.4) placeholder
  outcome rest p = 1.0 placeholder:
    effect self.stress -= 0.1 placeholder
    next = choose

action experiment:
  aggregate = experiment
  duration = Triangular(min=0.25, median=0.5, max=0.75) placeholder
  outcome success p = 0.75 placeholder:
    effect self.money += 10 placeholder
    effect place Lab noise += 0.1 placeholder
    next = at_lab
  outcome failure p = 0.25 placeholder:
    effect self.stress += 0.2 placeholder
    next = at_lab

action return_home:
  aggregate = travel
  duration = Triangular(min=0.25, median=0.5, max=0.75) placeholder
  outcome arrive p = 1.0 placeholder:
    effect self.location = Home placeholder
    next = choose
"#;

#[test]
fn python_like_dsl_parses_without_json_or_python_execution() {
    let program = parse_program(SYNTHETIC).unwrap();

    assert_eq!(program.id, "Synthetic");
    assert_eq!(program.agents.len(), 3);
    assert_eq!(program.places.len(), 2);
    assert_eq!(program.decisions.len(), 2);
    assert_eq!(program.actions.len(), 4);
}

#[test]
fn parser_reports_named_line_errors() {
    let forward = SYNTHETIC.replace(
        "age ~ Normal(mean=40, sd=8, min=18, max=75)",
        "age ~ Normal(mean=stress, sd=8, min=18, max=75)",
    );
    let error = parse_program(&forward).unwrap_err();
    assert_eq!(error.code, "FORWARD_INITIAL_REFERENCE");
    assert!(error.line > 0);

    let categorical = SYNTHETIC.replace(
        "location ~ Categorical(Home: 1.0)",
        "location ~ Categorical(Home: 0.6, Lab: 0.2)",
    );
    let error = parse_program(&categorical).unwrap_err();
    assert_eq!(error.code, "PROBABILITIES_NOT_ONE");

    let duration = SYNTHETIC.replace(
        "Triangular(min=0.25, median=0.5, max=0.75)",
        "Triangular(min=0.75, median=0.5, max=0.25)",
    );
    let error = parse_program(&duration).unwrap_err();
    assert_eq!(error.code, "UNORDERED_DURATION");

    let agent = SYNTHETIC.replace("Person = 0.5 placeholder", "Missing = 0.5 placeholder");
    assert_eq!(parse_program(&agent).unwrap_err().code, "UNKNOWN_AGENT");

    let action = SYNTHETIC.replace("branch visit_lab p =", "branch missing_action p =");
    assert_eq!(parse_program(&action).unwrap_err().code, "UNKNOWN_ACTION");

    let place = SYNTHETIC.replace(
        "action experiment:\n",
        "action experiment:\n  target = random at Missing\n",
    );
    assert_eq!(parse_program(&place).unwrap_err().code, "UNKNOWN_PLACE");

    let state = SYNTHETIC.replace("effect self.stress -=", "effect self.missing -=");
    assert_eq!(parse_program(&state).unwrap_err().code, "UNKNOWN_STATE");
}

#[test]
fn ordered_initial_sampling_is_seeded_and_conditional() {
    let program = parse_program(SYNTHETIC).unwrap();
    let first = sample_population(&program, 41).unwrap();
    let repeated = sample_population(&program, 41).unwrap();

    assert_eq!(first, repeated);
    let adults = first
        .agents
        .iter()
        .filter(|agent| agent.parent_id.is_none());
    for agent in adults {
        let family = agent.value("has_family").unwrap().as_bool().unwrap();
        let kids = agent.value("kids").unwrap().as_f64().unwrap();
        if !family {
            assert_eq!(kids, 0.0);
        }
        if agent.agent_type == "Student" {
            assert!((18.0..=26.0).contains(&agent.value("age").unwrap().as_f64().unwrap()));
        }
    }
    assert!(first.agents.iter().any(|agent| agent.parent_id.is_some()));
}

#[test]
fn initial_sampling_matches_placeholder_distributions_across_many_seeds() {
    let program = parse_program(SYNTHETIC).unwrap();
    let mut aggression = Vec::new();
    let mut younger_kids = Vec::new();
    let mut older_kids = Vec::new();
    let mut family_count = 0;
    let mut adult_count = 0;
    for seed in 0..100 {
        let population = sample_population(&program, seed).unwrap();
        for agent in population
            .agents
            .iter()
            .filter(|agent| agent.parent_id.is_none())
        {
            adult_count += 1;
            aggression.push(agent.value("aggression").unwrap().as_f64().unwrap());
            let family = agent.value("has_family").unwrap().as_bool().unwrap();
            let age = agent.value("age").unwrap().as_f64().unwrap();
            let kids = agent.value("kids").unwrap().as_f64().unwrap();
            if family {
                family_count += 1;
                if age < 30.0 {
                    younger_kids.push(kids);
                }
                if age > 45.0 {
                    older_kids.push(kids);
                }
            } else {
                assert_eq!(kids, 0.0);
            }
        }
    }
    let mean = |values: &[f64]| values.iter().sum::<f64>() / values.len() as f64;
    assert!((mean(&aggression) - 2.0 / 7.0).abs() < 0.04);
    assert!((0.2..0.8).contains(&(family_count as f64 / adult_count as f64)));
    assert!(mean(&older_kids) > mean(&younger_kids));
}

#[test]
fn normalized_decision_and_outcome_frequencies_match_known_weights() {
    let mut decision_program = parse_program(SYNTHETIC).unwrap();
    decision_program.decisions[0].branches = vec![
        DecisionBranch {
            action: "visit_lab".to_owned(),
            probability: Expr::Value(DslValue::Number(0.75)),
            condition: None,
            line: 1,
        },
        DecisionBranch {
            action: "stay_home".to_owned(),
            probability: Expr::Value(DslValue::Number(0.25)),
            condition: None,
            line: 1,
        },
    ];
    let mut travel = 0;
    let mut home = 0;
    for seed in 0..100 {
        let result = run_program(DslRunRequest::new(decision_program.clone(), seed, 1)).unwrap();
        travel += result
            .actions
            .iter()
            .filter(|record| matches!(record.action.as_str(), "visit_lab" | "return_home"))
            .count();
        home += result
            .actions
            .iter()
            .filter(|record| record.action == "stay_home")
            .count();
    }
    let observed = travel as f64 / (travel + home) as f64;
    assert!((observed - 0.75).abs() < 0.04);

    let mut outcome_program = parse_program(SYNTHETIC).unwrap();
    outcome_program.decisions[0].branches = vec![DecisionBranch {
        action: "experiment".to_owned(),
        probability: Expr::Value(DslValue::Number(1.0)),
        condition: None,
        line: 1,
    }];
    let mut success = 0;
    let mut failure = 0;
    for seed in 0..100 {
        let result = run_program(DslRunRequest::new(outcome_program.clone(), seed, 1)).unwrap();
        success += result
            .actions
            .iter()
            .filter(|record| record.action == "experiment" && record.outcome == "success")
            .count();
        failure += result
            .actions
            .iter()
            .filter(|record| record.action == "experiment" && record.outcome == "failure")
            .count();
    }
    let observed = success as f64 / (success + failure) as f64;
    assert!((observed - 0.75).abs() < 0.04);
}

#[test]
fn long_dsl_action_continues_across_ticks_without_truncation() {
    let mut program = parse_program(SYNTHETIC).unwrap();
    program.decisions[0].branches = vec![DecisionBranch {
        action: "visit_lab".to_owned(),
        probability: Expr::Value(DslValue::Number(1.0)),
        condition: None,
        line: 1,
    }];
    let action = program
        .actions
        .iter_mut()
        .find(|action| action.id == "visit_lab")
        .unwrap();
    action.long = true;
    action.duration.minimum = 1.5;
    action.duration.median = 2.0;
    action.duration.maximum = 2.5;

    let first = run_program(DslRunRequest::new(program.clone(), 3, 1)).unwrap();
    assert!(first.actions.is_empty());
    assert!(
        first
            .state
            .time
            .iter()
            .any(|time| time.active_primary.is_some())
    );
    let completed = run_program(DslRunRequest::resume(program, 3, 2, first.state)).unwrap();
    assert!(completed.actions.iter().any(|record| record.action == "visit_lab"));
}

#[test]
fn generic_effect_scopes_update_self_target_all_place_and_relationship() {
    let mut program = parse_program(SYNTHETIC).unwrap();
    program.decisions[0].branches = vec![DecisionBranch {
        action: "experiment".to_owned(),
        probability: Expr::Value(DslValue::Number(1.0)),
        condition: None,
        line: 1,
    }];
    let action = program
        .actions
        .iter_mut()
        .find(|action| action.id == "experiment")
        .unwrap();
    action.target = Some(TargetSelector::Random {
        place: "Lab".to_owned(),
        filter: None,
    });
    action.outcomes.truncate(1);
    action.outcomes[0].probability = Expr::Value(DslValue::Number(1.0));
    action.outcomes[0].target_next_decision = Some("choose".to_owned());
    action.outcomes[0].effects = vec![
        EffectDefinition {
            scope: EffectScope::SelfAgent,
            field: "stress".to_owned(),
            operation: "+=".to_owned(),
            value: Expr::Value(DslValue::Number(0.2)),
            line: 1,
        },
        EffectDefinition {
            scope: EffectScope::Target,
            field: "stress".to_owned(),
            operation: "+=".to_owned(),
            value: Expr::Value(DslValue::Number(0.3)),
            line: 2,
        },
        EffectDefinition {
            scope: EffectScope::AllAt {
                place: "Lab".to_owned(),
                filter: None,
            },
            field: "stress".to_owned(),
            operation: "+=".to_owned(),
            value: Expr::Value(DslValue::Number(0.1)),
            line: 3,
        },
        EffectDefinition {
            scope: EffectScope::Place {
                place: "Lab".to_owned(),
            },
            field: "noise".to_owned(),
            operation: "+=".to_owned(),
            value: Expr::Value(DslValue::Number(0.4)),
            line: 4,
        },
        EffectDefinition {
            scope: EffectScope::RelationshipWithTarget,
            field: "trust".to_owned(),
            operation: "-=".to_owned(),
            value: Expr::Value(DslValue::Number(0.5)),
            line: 5,
        },
    ];
    let mut population = sample_population(&program, 5).unwrap();
    population.agents.truncate(4);
    let before = population
        .agents
        .iter()
        .map(|agent| agent.value("stress").unwrap().as_f64().unwrap())
        .collect::<Vec<_>>();
    for agent in &mut population.agents {
        agent
            .states
            .insert("location".to_owned(), DslValue::Text("Lab".to_owned()));
        agent.current_decision = "choose".to_owned();
    }
    let state = DslRunState {
        completed_ticks: 0,
        time: population
            .agents
            .iter()
            .map(|_| DslAgentTimeState {
                active_primary: None,
                deferred: Vec::new(),
                occurrence_counts: BTreeMap::new(),
            })
            .collect(),
        agents: population.agents,
        places: program
            .places
            .iter()
            .map(|place| DslPlaceState {
                id: place.id.clone(),
                states: place.states.clone(),
            })
            .collect(),
        relationships: population.relationships,
    };
    let result = run_program(DslRunRequest::resume(program, 5, 1, state)).unwrap();

    assert!(
        result
            .state
            .agents
            .iter()
            .zip(before)
            .all(
                |(agent, before)| agent.value("stress").unwrap().as_f64().unwrap() >= before + 0.1
            )
    );
    assert!(result.state.places[1].states["noise"].as_f64().unwrap() > 0.2);
    assert!(result.state.relationships.iter().any(|relationship| {
        relationship
            .values
            .get("trust")
            .is_some_and(|value| *value < 0.0)
    }));
    for target_id in result
        .state
        .relationships
        .iter()
        .filter(|relationship| relationship.kind == "interaction")
        .map(|relationship| relationship.target_id.as_str())
    {
        assert_eq!(
            result
                .state
                .agents
                .iter()
                .find(|agent| agent.id == target_id)
                .unwrap()
                .current_decision,
            "choose"
        );
    }
}

#[test]
fn decision_and_outcome_sampling_are_order_independent() {
    let program = parse_program(SYNTHETIC).unwrap();
    let reordered = parse_program(
        &SYNTHETIC
            .replace(
                "  branch visit_lab p = 0.7 - stress * 0.2 placeholder\n  branch stay_home p = 0.3 + stress * 0.2 placeholder",
                "  branch stay_home p = 0.3 + stress * 0.2 placeholder\n  branch visit_lab p = 0.7 - stress * 0.2 placeholder",
            )
            .replace(
                "  outcome success p = 0.75 placeholder:\n    effect self.money += 10 placeholder\n    effect place Lab noise += 0.1 placeholder\n    next = at_lab\n  outcome failure p = 0.25 placeholder:\n    effect self.stress += 0.2 placeholder\n    next = at_lab",
                "  outcome failure p = 0.25 placeholder:\n    effect self.stress += 0.2 placeholder\n    next = at_lab\n  outcome success p = 0.75 placeholder:\n    effect self.money += 10 placeholder\n    effect place Lab noise += 0.1 placeholder\n    next = at_lab",
            ),
    )
    .unwrap();
    let first = run_program(DslRunRequest::new(program, 7, 3)).unwrap();
    let second = run_program(DslRunRequest::new(reordered, 7, 3)).unwrap();

    assert_eq!(first.actions, second.actions);
    assert_eq!(first.reports, second.reports);
    assert_eq!(first.state, second.state);
}

#[test]
fn interpreter_runs_small_ticks_and_round_trips_checkpoint() {
    let program = parse_program(SYNTHETIC).unwrap();
    let first = run_program(DslRunRequest::new(program.clone(), 9, 2)).unwrap();
    let encoded = serde_json::to_string(&first.state).unwrap();
    let restored: DslRunState = serde_json::from_str(&encoded).unwrap();
    let second = run_program(DslRunRequest::resume(program, 9, 1, restored)).unwrap();

    assert_eq!(first.completed_ticks, 2);
    assert_eq!(second.completed_ticks, 3);
    assert!(second.reports.iter().any(|report| !report.snapshots.is_empty()));
    assert!(
        second
            .state
            .agents
            .iter()
            .all(|agent| agent.value("stress").unwrap().as_f64().unwrap() >= 0.0)
    );
}

#[test]
fn dsl_reports_match_population_by_place_and_type() {
    let program = parse_program(SYNTHETIC).unwrap();
    let result = run_program(DslRunRequest::new(program, 11, 1)).unwrap();
    let place_population = result.reports[0].snapshots[0]
        .rows
        .iter()
        .map(|row| match row.values["population"] {
            DslReportValue::Number(value) => value as usize,
            _ => 0,
        })
        .sum::<usize>();
    let type_population = result.reports[1].snapshots[0]
        .rows
        .iter()
        .map(|row| match row.values["population"] {
            DslReportValue::Number(value) => value as usize,
            _ => 0,
        })
        .sum::<usize>();

    assert_eq!(place_population, result.state.agents.len());
    assert_eq!(type_population, result.state.agents.len());
}

#[test]
fn place_action_rates_use_the_recorded_action_place() {
    let mut program = parse_program(SYNTHETIC).unwrap();
    program.decisions[0].branches = vec![DecisionBranch {
        action: "visit_lab".to_owned(),
        probability: Expr::Value(DslValue::Number(1.0)),
        condition: None,
        line: 1,
    }];
    let result = run_program(DslRunRequest::new(program, 17, 1)).unwrap();
    let rows = &result.reports[0].snapshots[0].rows;
    let home = rows.iter().find(|row| row.group_id == "Home").unwrap();
    let lab = rows.iter().find(|row| row.group_id == "Lab").unwrap();

    assert!(matches!(home.values["travel"], DslReportValue::Number(value) if value > 0.0));
    assert_eq!(lab.values["travel"], DslReportValue::Number(0.0));
}
