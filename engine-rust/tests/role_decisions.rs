use petraterrium_engine::text_dsl::{
    DslRunResult, parse_program, run_expanded_archetype_population, sample_population,
};

const SOURCE: &str = include_str!("../dsl/role_test.dsl");

fn run(archetype: &str, ticks: u64) -> DslRunResult {
    let source = format!("{SOURCE}\npopulation Selected:\n  {archetype}: weight = 1\n");
    run_expanded_archetype_population(parse_program(&source).unwrap(), "Selected", 1, ticks)
        .unwrap()
}

fn count(result: &DslRunResult, suffix: &str) -> usize {
    result
        .actions
        .iter()
        .filter(|action| action.action.ends_with(suffix))
        .count()
}

#[test]
fn role_subtrees_are_included_only_for_active_roles_and_sample_once() {
    let neither = run("NeitherUsers", 200);
    let reddit = run("RedditUsers", 200);
    let tiktok = run("TikTokUsers", 200);
    let both = run("BothUsers", 200);
    assert_eq!(count(&neither, "post_reddit"), 0);
    assert_eq!(count(&neither, "post_tiktok"), 0);
    assert!(count(&reddit, "post_reddit") > 0);
    assert_eq!(count(&reddit, "post_tiktok"), 0);
    assert_eq!(count(&tiktok, "post_reddit"), 0);
    assert!(count(&tiktok, "post_tiktok") > 0);
    assert!(count(&both, "post_reddit") > 0);
    assert!(count(&both, "post_tiktok") > 0);
    assert_eq!(both.actions.len(), 200);
    assert_eq!(both.state.agents.len(), 1);
    assert_eq!(both.state.agents[0].agent_type, "Person");
    assert!(
        both.state.agents[0]
            .value("money")
            .unwrap()
            .as_f64()
            .unwrap()
            > 100.0
    );
    assert!(
        both.state.agents[0]
            .value("stress")
            .unwrap()
            .as_f64()
            .unwrap()
            > 0.2
    );
}

#[test]
fn role_order_does_not_change_the_deterministic_result() {
    let reordered = SOURCE.replace(
        "  roles = redditor, tiktoker",
        "  roles = tiktoker, redditor",
    );
    let source = format!("{SOURCE}\npopulation Selected:\n  BothUsers: weight = 1\n");
    let reordered = format!("{reordered}\npopulation Selected:\n  BothUsers: weight = 1\n");
    let first =
        run_expanded_archetype_population(parse_program(&source).unwrap(), "Selected", 7, 100)
            .unwrap();
    let second =
        run_expanded_archetype_population(parse_program(&reordered).unwrap(), "Selected", 7, 100)
            .unwrap();
    assert_eq!(first, second);
}

#[test]
fn join_and_quit_change_role_subtrees_on_the_next_tick_without_new_agents() {
    let joined = run("Joiner", 30);
    assert_eq!(joined.state.agents.len(), 1);
    assert!(joined.state.agents[0].roles.contains("redditor"));
    assert_eq!(count(&joined, "join_reddit"), 1);
    let joined_tick = joined
        .actions
        .iter()
        .find(|action| action.action.ends_with("join_reddit"))
        .unwrap()
        .tick;
    assert!(
        joined
            .actions
            .iter()
            .any(|action| action.action.ends_with("post_reddit") && action.tick > joined_tick)
    );

    let quitter_source = SOURCE.replace(
        "archetype Quitter:\n  sample_households = 1",
        "archetype Quitter:\n  sample_households = 1\n  initial:\n    activity ~ Uniform(min=0, max=0)",
    );
    let quitter_source = format!("{quitter_source}\npopulation Selected:\n  Quitter: weight = 1\n");
    let quit = run_expanded_archetype_population(
        parse_program(&quitter_source).unwrap(),
        "Selected",
        1,
        30,
    )
    .unwrap();
    assert_eq!(quit.state.agents.len(), 1);
    assert!(!quit.state.agents[0].roles.contains("redditor"));
    assert_eq!(count(&quit, "quit_reddit"), 1);
    let quit_tick = quit
        .actions
        .iter()
        .find(|action| action.action.ends_with("quit_reddit"))
        .unwrap()
        .tick;
    assert!(
        quit.actions
            .iter()
            .all(|action| !action.action.ends_with("post_reddit") || action.tick < quit_tick)
    );
}

#[test]
fn a_new_role_adds_a_subtree_without_editing_the_base_decision() {
    let addition = r#"
role volunteer:
  decision at_rest:
    branch volunteer_help p = 1.0 estimated

action volunteer_help:
  aggregate = volunteer_actions
  duration = Triangular(min=0.1, median=0.2, max=0.5) estimated
  outcome helped p = 1.0 estimated:
    next = at_rest
"#;
    let extended = SOURCE.replace(
        "  roles = redditor\n  composition:",
        "  roles = volunteer\n  composition:",
    ) + addition;
    let extended = format!("{extended}\npopulation Selected:\n  RedditUsers: weight = 1\n");
    let base_tree = SOURCE
        .split("decision at_rest:")
        .nth(1)
        .unwrap()
        .split("decision at_feed:")
        .next()
        .unwrap();
    let extended_tree = extended
        .split("decision at_rest:")
        .nth(1)
        .unwrap()
        .split("decision at_feed:")
        .next()
        .unwrap();
    assert_eq!(base_tree, extended_tree);
    let result =
        run_expanded_archetype_population(parse_program(&extended).unwrap(), "Selected", 1, 10)
            .unwrap();
    assert!(count(&result, "volunteer_help") > 0);
}

#[test]
fn duplicate_role_subtrees_return_a_named_line_error() {
    let invalid = SOURCE.replace(
        "  decision at_feed:\n    branch post_reddit",
        "  decision at_rest:\n    branch post_reddit",
    );
    let error = parse_program(&invalid).unwrap_err();
    assert_eq!(error.code, "DUPLICATE_ROLE_DECISION");
    assert!(error.line > 0);
}

#[test]
fn role_distribution_uses_a_slice_formula_and_trait_condition_without_new_agents() {
    let source = SOURCE.replace("size = 1 placeholder", "size = 100 placeholder");
    let source = format!(
        "{source}\nrole_distribution redditor:\n  agent = Person\n  parameters:\n    represented_users = 25\n    population = 100\n  share = formula(represented_users / population)\n  when = activity >= 0.5\n\nrole_distribution tiktoker:\n  agent = Person\n  parameters:\n    represented_users = 80\n    population = 100\n  share = formula(represented_users / population)\n  when = activity > 0.9\n"
    );
    let program = parse_program(&source).unwrap();
    let population = sample_population(&program, 1).unwrap();
    assert_eq!(population.agents.len(), 100);
    assert_eq!(
        population
            .agents
            .iter()
            .filter(|agent| agent.roles.contains("redditor"))
            .count(),
        25
    );
    assert_eq!(
        population
            .agents
            .iter()
            .filter(|agent| agent.roles.contains("tiktoker"))
            .count(),
        0
    );
    assert!(
        population
            .agents
            .iter()
            .all(|agent| agent.agent_type == "Person")
    );
}

#[test]
fn media_role_posting_is_live_at_rest_and_lower_than_at_feed() {
    let rest = run("RedditUsers", 500);
    let feed_source = SOURCE.replacen("routine = at_rest", "routine = at_feed", 1);
    let feed_source = format!("{feed_source}\npopulation Selected:\n  RedditUsers: weight = 1\n");
    let feed =
        run_expanded_archetype_population(parse_program(&feed_source).unwrap(), "Selected", 1, 500)
            .unwrap();
    let rest_posts = count(&rest, "post_reddit");
    let feed_posts = count(&feed, "post_reddit");
    assert!(rest_posts > 0);
    assert!(
        feed_posts > rest_posts,
        "rest={rest_posts}, feed={feed_posts}"
    );
}
