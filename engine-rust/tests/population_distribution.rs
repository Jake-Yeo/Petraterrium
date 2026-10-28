use petraterrium_engine::text_dsl::{
    build_population_plan, configure_pool_run, parse_program, sample_multinomial_counts,
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
}

#[test]
fn pool_partition_conserves_default_eight_billion_and_two_billion() {
    for total in [6_999_999_999_u64, 8_000_000_000, 2_000_000_000] {
        let mut program = parse_program(SOURCE).unwrap();
        configure_pool_run(&mut program, "Petraterrium", total, Some("medium")).unwrap();
        let plan = build_population_plan(&program, "World", 1, None).unwrap();
        let world = plan.iter().find(|row| row.path == "World").unwrap();
        assert_eq!(world.actual_represented, total);
        assert_eq!(world.actual_simulated, 291);
        let countries = plan
            .iter()
            .filter(|row| row.parent_path.as_deref() == Some("World"))
            .collect::<Vec<_>>();
        assert_eq!(
            countries
                .iter()
                .map(|row| row.actual_represented)
                .sum::<u64>(),
            total
        );
        assert_eq!(
            countries
                .iter()
                .map(|row| row.actual_simulated)
                .sum::<u64>(),
            291
        );
    }
}

#[test]
fn world_uses_declared_country_weights_and_tree_paths() {
    let mut program = parse_program(SOURCE).unwrap();
    configure_pool_run(&mut program, "Petraterrium", 6_999_999_999, Some("medium")).unwrap();
    let world = program
        .compositions
        .iter()
        .find(|composition| composition.id == "World")
        .unwrap();
    assert_eq!(
        world
            .entries
            .iter()
            .map(|entry| (entry.child.as_str(), entry.weight.unwrap()))
            .collect::<Vec<_>>(),
        vec![
            ("Canada", 0.20833333333333334),
            ("USA", 0.625),
            ("Mexico", 0.16666666666666663),
        ]
    );
    let plan = build_population_plan(&program, "World", 1, None).unwrap();
    assert_eq!(
        plan.iter().filter(|row| row.node_id == "Toronto").count(),
        1
    );
    assert_eq!(
        plan.iter().filter(|row| row.node_id == "Vancouver").count(),
        1
    );
}
