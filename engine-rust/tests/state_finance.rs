use std::collections::BTreeMap;

use petraterrium_engine::state_finance::{
    CashFlowColumns, DirectedRelationshipState, EducationColumns, EvidenceReceipt, FinanceColumns,
    FinanceLedgerRule, LinearStateRule, StateColumns, advance_finance_columns,
    advance_state_columns, validate_directed_relationship_states, validate_education_columns,
};

fn values(entries: &[(&str, Vec<f64>)]) -> BTreeMap<String, Vec<f64>> {
    entries
        .iter()
        .map(|(key, value)| ((*key).to_owned(), value.clone()))
        .collect()
}

fn evidence() -> EvidenceReceipt {
    EvidenceReceipt {
        status: "measured_joint".to_owned(),
        source: "Imported linked state and outcome fixture".to_owned(),
        source_version: "fixture-v1".to_owned(),
        uncertainty: 0.04,
    }
}

fn zero_flows(agent_count: usize) -> CashFlowColumns {
    let zeros = vec![0.0; agent_count];
    CashFlowColumns {
        wages: zeros.clone(),
        business_income: zeros.clone(),
        transfers: zeros.clone(),
        housing: zeros.clone(),
        food: zeros.clone(),
        transport: zeros.clone(),
        other_expenses: zeros.clone(),
        taxes: zeros.clone(),
        savings_contribution: zeros.clone(),
        savings_withdrawal: zeros.clone(),
        debt_draw: zeros.clone(),
        debt_repayment: zeros,
    }
}

fn finance_rule(id: &str, target: &str, terms: &[(&str, f64)], formula: &str) -> FinanceLedgerRule {
    FinanceLedgerRule {
        id: id.to_owned(),
        target: target.to_owned(),
        terms: terms
            .iter()
            .map(|(name, coefficient)| ((*name).to_owned(), *coefficient))
            .collect(),
        minimum: Some(0.0),
        maximum: None,
        formula: formula.to_owned(),
        evidence: evidence(),
    }
}

fn finance_rules() -> Vec<FinanceLedgerRule> {
    vec![
        finance_rule(
            "update_income",
            "finance.income",
            &[
                ("finance.income", 1.0),
                ("cash_flow.wages", 1.0),
                ("cash_flow.business_income", 1.0),
                ("cash_flow.transfers", 1.0),
            ],
            "income[t+1] = income[t] + wages + business_income + transfers",
        ),
        finance_rule(
            "update_expenses",
            "finance.expenses",
            &[
                ("finance.expenses", 1.0),
                ("cash_flow.housing", 1.0),
                ("cash_flow.food", 1.0),
                ("cash_flow.transport", 1.0),
                ("cash_flow.other_expenses", 1.0),
                ("cash_flow.taxes", 1.0),
            ],
            "expenses[t+1] = expenses[t] + configured expense flows",
        ),
        finance_rule(
            "update_money",
            "finance.money",
            &[
                ("finance.money", 1.0),
                ("cash_flow.wages", 1.0),
                ("cash_flow.business_income", 1.0),
                ("cash_flow.transfers", 1.0),
                ("cash_flow.debt_draw", 1.0),
                ("cash_flow.savings_withdrawal", 1.0),
                ("cash_flow.housing", -1.0),
                ("cash_flow.food", -1.0),
                ("cash_flow.transport", -1.0),
                ("cash_flow.other_expenses", -1.0),
                ("cash_flow.taxes", -1.0),
                ("cash_flow.savings_contribution", -1.0),
                ("cash_flow.debt_repayment", -1.0),
            ],
            "money[t+1] = configured weighted inputs",
        ),
        finance_rule(
            "update_savings",
            "finance.savings",
            &[
                ("finance.savings", 1.0),
                ("cash_flow.savings_contribution", 1.0),
                ("cash_flow.savings_withdrawal", -1.0),
            ],
            "savings[t+1] = configured weighted inputs",
        ),
        finance_rule(
            "update_debt",
            "finance.debt",
            &[
                ("finance.debt", 1.0),
                ("cash_flow.debt_draw", 1.0),
                ("cash_flow.debt_repayment", -1.0),
            ],
            "debt[t+1] = configured weighted inputs",
        ),
    ]
}

#[test]
fn state_tick_reads_only_current_columns_and_applies_agent_event_deltas() {
    let current = StateColumns {
        values: values(&[("stress", vec![0.5, 0.8]), ("health", vec![0.9, 0.7])]),
    };
    let event_deltas = StateColumns {
        values: values(&[("stress", vec![0.3, -0.25])]),
    };
    let rules = vec![
        LinearStateRule {
            target_state_id: "stress".to_owned(),
            intercept: 0.0,
            coefficients: BTreeMap::new(),
            minimum: 0.0,
            maximum: 1.0,
            formula: "stress[t+1] = clamp(stress[t] + event_delta, 0, 1)".to_owned(),
            evidence: evidence(),
        },
        LinearStateRule {
            target_state_id: "health".to_owned(),
            intercept: 0.0,
            coefficients: values(&[("stress", vec![-0.05])])
                .into_iter()
                .map(|(key, value)| (key, value[0]))
                .collect(),
            minimum: 0.0,
            maximum: 1.0,
            formula: "health[t+1] = clamp(health[t] - 0.05 * stress[t], 0, 1)".to_owned(),
            evidence: evidence(),
        },
    ];

    let result = advance_state_columns(&current, &event_deltas, &rules).unwrap();

    assert_eq!(result.columns.values["stress"], vec![0.8, 0.55]);
    assert_eq!(
        result.columns.values["health"],
        vec![0.875, 0.6599999999999999]
    );
    assert_eq!(result.receipts[1].input_state_ids, vec!["stress"]);
    assert_eq!(result.receipts[1].formula, rules[1].formula);
    assert_eq!(result.agent_state_changes.len(), 4);
    assert_eq!(result.agent_state_changes[0].agent_index, 0);
    assert_eq!(result.agent_state_changes[0].target_state_id, "stress");
    assert_eq!(result.agent_state_changes[0].rule_index, 0);
    assert_eq!(result.agent_state_changes[0].before, 0.5);
    assert_eq!(result.agent_state_changes[0].event_delta, 0.3);
    assert_eq!(result.agent_state_changes[0].equation_delta, 0.0);
    assert_eq!(result.agent_state_changes[0].after, 0.8);
    assert_eq!(result.agent_state_changes[2].agent_index, 0);
    assert_eq!(result.agent_state_changes[2].target_state_id, "health");
    assert_eq!(result.agent_state_changes[2].rule_index, 1);
    assert_eq!(result.agent_state_changes[2].before, 0.9);
    assert_eq!(result.agent_state_changes[2].event_delta, 0.0);
    assert_eq!(result.agent_state_changes[2].equation_delta, -0.025);
    assert_eq!(result.agent_state_changes[2].after, 0.875);
}

#[test]
fn state_tick_omits_unchanged_agent_receipts() {
    let current = StateColumns {
        values: values(&[("stress", vec![0.2, 0.8])]),
    };
    let event_deltas = StateColumns::default();
    let rules = vec![LinearStateRule {
        target_state_id: "stress".to_owned(),
        intercept: 0.0,
        coefficients: BTreeMap::new(),
        minimum: 0.0,
        maximum: 1.0,
        formula: "stress[t+1] = clamp(stress[t] + event_delta, 0, 1)".to_owned(),
        evidence: evidence(),
    }];

    let result = advance_state_columns(&current, &event_deltas, &rules).unwrap();

    assert_eq!(result.columns, current);
    assert!(result.agent_state_changes.is_empty());
    assert_eq!(result.receipts.len(), 1);
}

#[test]
fn finance_tick_applies_the_generic_accounting_identity_for_every_agent() {
    let current = FinanceColumns {
        currency: vec!["CAD".to_owned(), "CAD".to_owned()],
        money: vec![Some(1_000.0), Some(10_000.0)],
        income: vec![Some(48_000.0), Some(90_000.0)],
        expenses: vec![Some(36_000.0), Some(70_000.0)],
        savings: vec![Some(500.0), Some(20_000.0)],
        debt: vec![Some(4_000.0), Some(30_000.0)],
        status: vec!["measured_joint".to_owned(), "measured_joint".to_owned()],
        source: vec!["fixture".to_owned(), "fixture".to_owned()],
    };
    let flows = CashFlowColumns {
        wages: vec![2_000.0, 4_000.0],
        business_income: vec![0.0, 2_000.0],
        transfers: vec![100.0, 0.0],
        housing: vec![900.0, 1_500.0],
        food: vec![250.0, 500.0],
        transport: vec![100.0, 300.0],
        other_expenses: vec![200.0, 400.0],
        taxes: vec![300.0, 1_200.0],
        savings_contribution: vec![200.0, 1_000.0],
        savings_withdrawal: vec![0.0, 0.0],
        debt_draw: vec![0.0, 0.0],
        debt_repayment: vec![150.0, 600.0],
    };

    let rules = finance_rules();
    let result = advance_finance_columns(&current, &flows, &rules).unwrap();

    assert_eq!(result.columns.income, vec![Some(50_100.0), Some(96_000.0)]);
    assert_eq!(
        result.columns.expenses,
        vec![Some(37_750.0), Some(73_900.0)]
    );
    assert_eq!(result.columns.money, vec![Some(1_000.0), Some(10_500.0)]);
    assert_eq!(result.columns.savings, vec![Some(700.0), Some(21_000.0)]);
    assert_eq!(result.columns.debt, vec![Some(3_850.0), Some(29_400.0)]);
    assert_eq!(result.finance_changes.len(), 2);
    let first = &result.finance_changes[0];
    assert_eq!(first.agent_index, 0);
    assert_eq!(first.currency, "CAD");
    assert_eq!(first.provenance.status, "measured_joint");
    assert_eq!(first.provenance.source, "fixture");
    assert_eq!(first.flows.wages, 2_000.0);
    assert_eq!(first.flows.transfers, 100.0);
    assert_eq!(first.flows.housing, 900.0);
    assert_eq!(first.flows.food, 250.0);
    assert_eq!(first.flows.savings_contribution, 200.0);
    assert_eq!(first.flows.debt_repayment, 150.0);
    assert_eq!(
        first
            .ledger_changes
            .iter()
            .map(|change| change.ledger.as_str())
            .collect::<Vec<_>>(),
        vec!["income", "expenses", "savings", "debt"]
    );
    assert_eq!(first.ledger_changes[0].before, Some(48_000.0));
    assert_eq!(first.ledger_changes[0].flow_delta, 2_100.0);
    assert_eq!(first.ledger_changes[0].after, Some(50_100.0));
    let second_agent = &result.finance_changes[1];
    let money_change = second_agent
        .ledger_changes
        .iter()
        .find(|change| change.ledger == "money")
        .unwrap();
    assert_eq!(money_change.before, Some(10_000.0));
    assert_eq!(money_change.flow_delta, 500.0);
    assert_eq!(money_change.after, Some(10_500.0));
    let second = advance_finance_columns(&result.columns, &flows, &rules).unwrap();
    assert_eq!(second.columns.income, vec![Some(52_200.0), Some(102_000.0)]);
    assert_eq!(
        second.columns.expenses,
        vec![Some(39_500.0), Some(77_800.0)]
    );
    assert!(
        result
            .formula
            .contains("wages + business_income + transfers")
    );

    let unchanged = advance_finance_columns(&current, &zero_flows(2), &rules).unwrap();
    assert_eq!(unchanged.columns, current);
    assert!(unchanged.finance_changes.is_empty());
}

#[test]
fn education_and_relationship_contracts_enforce_semantics() {
    let education = EducationColumns {
        years_of_education: vec![12, 16],
        isced_level: vec![Some(3), Some(6)],
        country_label: vec![
            "Secondary completion".to_owned(),
            "Bachelor's degree".to_owned(),
        ],
        specialization: vec![None, Some("engineering".to_owned())],
        specialization_threshold_years: vec![12, 12],
        provenance_status: vec![
            "measured_marginal".to_owned(),
            "measured_marginal".to_owned(),
        ],
        provenance_source: vec!["ISCED mapping".to_owned(), "ISCED mapping".to_owned()],
    };
    validate_education_columns(&education).unwrap();

    let invalid = EducationColumns {
        specialization: vec![Some("engineering".to_owned()), None],
        years_of_education: vec![11, 16],
        ..education.clone()
    };
    assert!(validate_education_columns(&invalid).is_err());

    let relationships = vec![DirectedRelationshipState {
        source_agent_index: 0,
        target_agent_index: 1,
        values: values(&[("love", vec![0.7])])
            .into_iter()
            .map(|(key, value)| (key, value[0]))
            .collect(),
    }];
    validate_directed_relationship_states(&relationships, 2).unwrap();
    assert_eq!(relationships[0].values["love"], 0.7);
}
