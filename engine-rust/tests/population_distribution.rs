use petraterrium_engine::text_dsl::{
    build_population_plan, parse_program, run_composition, sample_multinomial_counts,
};

const SOURCE: &str = include_str!("../dsl/default.dsl");

#[test]
fn seeded_multinomial_is_conserved_deterministic_and_seed_sensitive() {
    let probabilities = [0.2, 0.3, 0.5];
    let first = sample_multinomial_counts(10_000, &probabilities, 7, "root").unwrap();
    let repeated = sample_multinomial_counts(10_000, &probabilities, 7, "root").unwrap();
    let other_seed = sample_multinomial_counts(10_000, &probabilities, 8, "root").unwrap();
    assert_eq!(first, repeated);
    assert_ne!(first, other_seed);
    assert_eq!(first.iter().sum::<u64>(), 10_000);
    for (actual, expected) in first.iter().zip([2_000.0_f64, 3_000.0, 5_000.0]) {
        let standard_deviation = (expected * (1.0 - expected / 10_000.0)).sqrt();
        assert!((*actual as f64 - expected).abs() <= 5.0 * standard_deviation);
    }
}

#[test]
fn role_distribution_uses_actual_composition_population_as_denominator() {
    let program = parse_program(SOURCE).unwrap();
    let cashier_counts = [100_u64, 1_000, 10_000].map(|budget| {
        let mut configured = program.clone();
        configured
            .compositions
            .iter_mut()
            .find(|composition| composition.id == "RoleDemandDemo")
            .unwrap()
            .sample_budget = Some(budget);
        let result = run_composition(configured, "RoleDemandDemo", 1, 0).unwrap();
        (
            result.state.agents.len(),
            result
                .state
                .agents
                .iter()
                .filter(|agent| agent.roles.contains("cashier"))
                .count(),
        )
    });
    assert_eq!(cashier_counts, [(100, 100), (1_000, 500), (10_000, 500)]);
}

#[test]
fn multinomial_rejects_probabilities_that_do_not_sum_to_one() {
    let error = sample_multinomial_counts(100, &[0.2, 0.2], 1, "root").unwrap_err();
    assert_eq!(error.code, "INVALID_DISTRIBUTION_SUM");
    assert_eq!(error.line, 1);
}

#[test]
fn world_plan_conserves_represented_total_and_samples_each_dag_path() {
    let program = parse_program(SOURCE).unwrap();
    let plan = build_population_plan(&program, "World", 1, Some(10_000)).unwrap();
    let world = plan.iter().find(|row| row.path == "World").unwrap();
    assert_eq!(world.actual_represented, 6_999_999_999);
    let countries = plan
        .iter()
        .filter(|row| row.parent_path.as_deref() == Some("World"))
        .collect::<Vec<_>>();
    assert_eq!(
        countries
            .iter()
            .map(|row| row.actual_represented)
            .sum::<u64>(),
        world.actual_represented
    );
    assert_eq!(
        countries
            .iter()
            .map(|row| row.actual_simulated)
            .sum::<u64>(),
        world.actual_simulated
    );
    let toronto_paths = plan
        .iter()
        .filter(|row| row.node_id == "Toronto")
        .map(|row| row.path.as_str())
        .collect::<Vec<_>>();
    assert_eq!(toronto_paths.len(), 6);
    assert!(
        toronto_paths
            .iter()
            .any(|path| path.contains("World>Canada>Ontario"))
    );
    assert!(
        toronto_paths
            .iter()
            .any(|path| path.contains("World>USA>California"))
    );
}

#[test]
fn sample_budget_and_seed_change_actual_counts_without_changing_probabilities() {
    let program = parse_program(SOURCE).unwrap();
    let small = build_population_plan(&program, "World", 1, Some(1_000)).unwrap();
    let large = build_population_plan(&program, "World", 1, Some(10_000)).unwrap();
    let other_seed = build_population_plan(&program, "World", 2, Some(10_000)).unwrap();
    let path = "World>USA";
    let small_row = small.iter().find(|row| row.path == path).unwrap();
    let large_row = large.iter().find(|row| row.path == path).unwrap();
    let other_row = other_seed.iter().find(|row| row.path == path).unwrap();
    assert_eq!(small_row.probability, large_row.probability);
    assert_eq!(large_row.probability, other_row.probability);
    assert_ne!(small_row.actual_simulated, large_row.actual_simulated);
    assert_ne!(large_row.actual_simulated, other_row.actual_simulated);
    assert_eq!(
        large_row.expected_represented,
        other_row.expected_represented
    );
}
