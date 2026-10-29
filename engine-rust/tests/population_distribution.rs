use petraterrium_engine::text_dsl::sample_multinomial_counts;

#[test]
fn seeded_multinomial_primitive_is_conserved_deterministic_and_seed_sensitive() {
    let probabilities = [0.2, 0.3, 0.5];
    let first = sample_multinomial_counts(10_000, &probabilities, 7, "root").unwrap();
    let repeated = sample_multinomial_counts(10_000, &probabilities, 7, "root").unwrap();
    let other_seed = sample_multinomial_counts(10_000, &probabilities, 8, "root").unwrap();
    assert_eq!(first, repeated);
    assert_ne!(first, other_seed);
    assert_eq!(first.iter().sum::<u64>(), 10_000);
}
