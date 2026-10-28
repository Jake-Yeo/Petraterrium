use petraterrium_engine::agent_types::{ProbabilityProvenance, ProbabilityRule};
use petraterrium_engine::agent_validation::validate_probability_rule;

fn rule(status: &str) -> ProbabilityRule {
    ProbabilityRule {
        conditions: vec![],
        probability: Some(0.5),
        time_unit_hours: None,
        provenance: ProbabilityProvenance {
            source: "Shipped default DSL".to_owned(),
            version: "foundation-v1".to_owned(),
            status: status.to_owned(),
            uncertainty: 1.0,
            ..ProbabilityProvenance::default()
        },
    }
}

#[test]
fn default_estimated_and_fitted_are_predictive_evidence_states() {
    validate_probability_rule(&rule("default_estimated"), "rule").unwrap();
    validate_probability_rule(&rule("fitted"), "rule").unwrap();
}

#[test]
fn explicit_global_default_can_execute_for_a_more_specific_place() {
    let mut global_default = rule("default_estimated");
    global_default.provenance.resolution_status = Some("imputed".to_owned());
    global_default.provenance.source_places = vec!["global:global".to_owned()];

    validate_probability_rule(&global_default, "rule").unwrap();
}

#[test]
fn imputed_observed_and_fitted_evidence_remains_non_predictive() {
    for status in ["present", "measured", "fitted"] {
        let mut imputed = rule(status);
        imputed.provenance.resolution_status = Some("imputed".to_owned());
        let error = validate_probability_rule(&imputed, "rule").unwrap_err();
        assert_eq!(error.code, "NON_PREDICTIVE_EVIDENCE");
    }
}

#[test]
fn blocked_is_not_a_predictive_evidence_state() {
    let error = validate_probability_rule(&rule("blocked"), "rule").unwrap_err();
    assert_eq!(error.code, "NON_PREDICTIVE_EVIDENCE");
}
