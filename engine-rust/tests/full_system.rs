use petraterrium_engine::text_dsl::parse_program;

const SOURCE: &str = include_str!("../dsl/default.dsl");

#[test]
fn default_system_has_no_causal_flows_or_global_sample_controls() {
    parse_program(SOURCE).unwrap();
    for forbidden in [
        "sample_budget",
        "planned_draws",
        "detail =",
        "flows:",
        "couplings:",
        "boundaries:",
    ] {
        assert!(!SOURCE.contains(forbidden), "{forbidden}");
    }
}
