use crate::error::{CoreError, CoreResult};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Default, Deserialize, PartialEq, Serialize)]
pub struct StateColumns {
    pub values: BTreeMap<String, Vec<f64>>,
}

impl StateColumns {
    pub fn len(&self) -> CoreResult<usize> {
        let length = self.values.values().next().map_or(0, Vec::len);
        if self.values.values().any(|values| values.len() != length) {
            return Err(CoreError::new(
                "STATE_COLUMN_LENGTH_MISMATCH",
                "Every state column must contain the same number of agents",
            ));
        }
        if self
            .values
            .values()
            .flatten()
            .any(|value| !value.is_finite())
        {
            return Err(CoreError::new(
                "INVALID_STATE_VALUE",
                "State columns must contain finite values",
            ));
        }
        Ok(length)
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct EvidenceReceipt {
    pub status: String,
    pub source: String,
    pub source_version: String,
    pub uncertainty: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct LinearStateRule {
    pub target_state_id: String,
    pub intercept: f64,
    pub coefficients: BTreeMap<String, f64>,
    pub minimum: f64,
    pub maximum: f64,
    pub formula: String,
    pub evidence: EvidenceReceipt,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct StateTickReceipt {
    pub target_state_id: String,
    pub input_state_ids: Vec<String>,
    pub formula: String,
    pub evidence: EvidenceReceipt,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct AgentStateChangeReceipt {
    pub agent_index: usize,
    pub target_state_id: String,
    pub rule_index: usize,
    pub before: f64,
    pub event_delta: f64,
    pub equation_delta: f64,
    pub after: f64,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct StateTickResult {
    pub columns: StateColumns,
    pub receipts: Vec<StateTickReceipt>,
    pub agent_state_changes: Vec<AgentStateChangeReceipt>,
}

fn validate_state_tick(
    current: &StateColumns,
    event_deltas: &StateColumns,
    rules: &[LinearStateRule],
) -> CoreResult<usize> {
    let agent_count = current.len()?;
    let event_count = event_deltas.len()?;
    if !event_deltas.values.is_empty() && event_count != agent_count {
        return Err(CoreError::new(
            "STATE_EVENT_LENGTH_MISMATCH",
            "Event delta columns must contain one value per agent",
        ));
    }
    let mut targets = BTreeSet::new();
    for (index, rule) in rules.iter().enumerate() {
        if !targets.insert(rule.target_state_id.clone()) {
            return Err(CoreError::at(
                "DUPLICATE_STATE_TARGET",
                "A state tick may define only one rule per target state",
                format!("rules.{index}.target_state_id"),
            ));
        }
        if !current.values.contains_key(&rule.target_state_id) {
            return Err(CoreError::at(
                "UNKNOWN_STATE_TARGET",
                "State rule target is absent from the current state columns",
                format!("rules.{index}.target_state_id"),
            ));
        }
        if rule.maximum < rule.minimum
            || !rule.intercept.is_finite()
            || !rule.minimum.is_finite()
            || !rule.maximum.is_finite()
            || !rule.evidence.uncertainty.is_finite()
        {
            return Err(CoreError::at(
                "INVALID_STATE_RULE",
                "State rule bounds and numeric metadata must be finite and ordered",
                format!("rules.{index}"),
            ));
        }
        for (state_id, coefficient) in &rule.coefficients {
            if !current.values.contains_key(state_id) {
                return Err(CoreError::at(
                    "UNKNOWN_STATE_INPUT",
                    "State rule input is absent from the current state columns",
                    format!("rules.{index}.coefficients.{state_id}"),
                ));
            }
            if !coefficient.is_finite() {
                return Err(CoreError::at(
                    "INVALID_STATE_COEFFICIENT",
                    "State coefficients must be finite",
                    format!("rules.{index}.coefficients.{state_id}"),
                ));
            }
        }
    }
    if let Some(state_id) = event_deltas
        .values
        .keys()
        .find(|state_id| !targets.contains(state_id.as_str()))
    {
        return Err(CoreError::at(
            "MISSING_STATE_EVENT_RULE",
            "Every event delta requires a state rule that defines its range and evidence",
            format!("event_deltas.{state_id}"),
        ));
    }
    Ok(agent_count)
}

pub fn advance_state_columns(
    current: &StateColumns,
    event_deltas: &StateColumns,
    rules: &[LinearStateRule],
) -> CoreResult<StateTickResult> {
    let agent_count = validate_state_tick(current, event_deltas, rules)?;
    let mut next = current.clone();
    let mut receipts = Vec::with_capacity(rules.len());
    let mut agent_state_changes = Vec::with_capacity(rules.len() * agent_count);
    for (rule_index, rule) in rules.iter().enumerate() {
        let mut target = vec![0.0; agent_count];
        for agent_index in 0..agent_count {
            let equation_value =
                rule.coefficients
                    .iter()
                    .fold(rule.intercept, |value, (state_id, coefficient)| {
                        value + current.values[state_id][agent_index] * coefficient
                    });
            let event_delta = event_deltas
                .values
                .get(&rule.target_state_id)
                .map_or(0.0, |values| values[agent_index]);
            let before = current.values[&rule.target_state_id][agent_index];
            let after = (before + equation_value + event_delta).clamp(rule.minimum, rule.maximum);
            target[agent_index] = after;
            if event_delta != 0.0 || equation_value != 0.0 || after != before {
                agent_state_changes.push(AgentStateChangeReceipt {
                    agent_index,
                    target_state_id: rule.target_state_id.clone(),
                    rule_index,
                    before,
                    event_delta,
                    equation_delta: equation_value,
                    after,
                });
            }
        }
        next.values.insert(rule.target_state_id.clone(), target);
        receipts.push(StateTickReceipt {
            target_state_id: rule.target_state_id.clone(),
            input_state_ids: rule.coefficients.keys().cloned().collect(),
            formula: rule.formula.clone(),
            evidence: rule.evidence.clone(),
        });
    }
    Ok(StateTickResult {
        columns: next,
        receipts,
        agent_state_changes,
    })
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct FinanceColumns {
    pub currency: Vec<String>,
    pub money: Vec<Option<f64>>,
    pub income: Vec<Option<f64>>,
    pub expenses: Vec<Option<f64>>,
    pub savings: Vec<Option<f64>>,
    pub debt: Vec<Option<f64>>,
    pub status: Vec<String>,
    pub source: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct CashFlowColumns {
    pub wages: Vec<f64>,
    pub business_income: Vec<f64>,
    pub transfers: Vec<f64>,
    pub housing: Vec<f64>,
    pub food: Vec<f64>,
    pub transport: Vec<f64>,
    pub other_expenses: Vec<f64>,
    pub taxes: Vec<f64>,
    pub savings_contribution: Vec<f64>,
    pub savings_withdrawal: Vec<f64>,
    pub debt_draw: Vec<f64>,
    pub debt_repayment: Vec<f64>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct FinanceTickResult {
    pub columns: FinanceColumns,
    pub formula: String,
    pub finance_changes: Vec<AgentFinanceChangeReceipt>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct FinanceLedgerRule {
    pub id: String,
    pub target: String,
    pub terms: BTreeMap<String, f64>,
    pub minimum: Option<f64>,
    pub maximum: Option<f64>,
    pub formula: String,
    pub evidence: EvidenceReceipt,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct AgentCashFlowReceipt {
    pub wages: f64,
    pub business_income: f64,
    pub transfers: f64,
    pub housing: f64,
    pub food: f64,
    pub transport: f64,
    pub other_expenses: f64,
    pub taxes: f64,
    pub savings_contribution: f64,
    pub savings_withdrawal: f64,
    pub debt_draw: f64,
    pub debt_repayment: f64,
}

impl AgentCashFlowReceipt {
    fn has_flows(&self) -> bool {
        self.values().into_iter().any(|value| value != 0.0)
    }

    fn values(&self) -> [f64; 12] {
        [
            self.wages,
            self.business_income,
            self.transfers,
            self.housing,
            self.food,
            self.transport,
            self.other_expenses,
            self.taxes,
            self.savings_contribution,
            self.savings_withdrawal,
            self.debt_draw,
            self.debt_repayment,
        ]
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct FinanceLedgerChangeReceipt {
    pub ledger: String,
    pub before: Option<f64>,
    pub flow_delta: f64,
    pub after: Option<f64>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct FinanceProvenanceReceipt {
    pub status: String,
    pub source: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct AgentFinanceChangeReceipt {
    pub agent_index: usize,
    pub currency: String,
    pub provenance: FinanceProvenanceReceipt,
    pub flows: AgentCashFlowReceipt,
    pub ledger_changes: Vec<FinanceLedgerChangeReceipt>,
}

fn finance_column_lengths(finances: &FinanceColumns, flows: &CashFlowColumns) -> Vec<usize> {
    vec![
        finances.currency.len(),
        finances.money.len(),
        finances.income.len(),
        finances.expenses.len(),
        finances.savings.len(),
        finances.debt.len(),
        finances.status.len(),
        finances.source.len(),
        flows.wages.len(),
        flows.business_income.len(),
        flows.transfers.len(),
        flows.housing.len(),
        flows.food.len(),
        flows.transport.len(),
        flows.other_expenses.len(),
        flows.taxes.len(),
        flows.savings_contribution.len(),
        flows.savings_withdrawal.len(),
        flows.debt_draw.len(),
        flows.debt_repayment.len(),
    ]
}

pub fn advance_finance_columns(
    current: &FinanceColumns,
    flows: &CashFlowColumns,
    rules: &[FinanceLedgerRule],
) -> CoreResult<FinanceTickResult> {
    let lengths = finance_column_lengths(current, flows);
    let agent_count = lengths.first().copied().unwrap_or(0);
    if lengths.iter().any(|length| *length != agent_count) {
        return Err(CoreError::new(
            "FINANCE_COLUMN_LENGTH_MISMATCH",
            "Every finance and cash-flow column must contain the same number of agents",
        ));
    }
    let finite_flows = [
        &flows.wages,
        &flows.business_income,
        &flows.transfers,
        &flows.housing,
        &flows.food,
        &flows.transport,
        &flows.other_expenses,
        &flows.taxes,
        &flows.savings_contribution,
        &flows.savings_withdrawal,
        &flows.debt_draw,
        &flows.debt_repayment,
    ];
    if finite_flows
        .into_iter()
        .flatten()
        .any(|value| !value.is_finite() || *value < 0.0)
    {
        return Err(CoreError::new(
            "INVALID_CASH_FLOW",
            "Cash-flow columns must contain finite non-negative values",
        ));
    }
    validate_finance_rules(rules)?;
    let mut next = current.clone();
    let mut finance_changes = Vec::new();
    for agent_index in 0..agent_count {
        let agent_flows = AgentCashFlowReceipt {
            wages: flows.wages[agent_index],
            business_income: flows.business_income[agent_index],
            transfers: flows.transfers[agent_index],
            housing: flows.housing[agent_index],
            food: flows.food[agent_index],
            transport: flows.transport[agent_index],
            other_expenses: flows.other_expenses[agent_index],
            taxes: flows.taxes[agent_index],
            savings_contribution: flows.savings_contribution[agent_index],
            savings_withdrawal: flows.savings_withdrawal[agent_index],
            debt_draw: flows.debt_draw[agent_index],
            debt_repayment: flows.debt_repayment[agent_index],
        };
        let mut ledger_changes = Vec::new();
        for rule in rules {
            let before = finance_ledger_value(current, &rule.target, agent_index)?;
            let mut after = 0.0;
            for (input, coefficient) in &rule.terms {
                after += coefficient * finance_input(current, flows, input, agent_index)?;
            }
            if let Some(minimum) = rule.minimum {
                after = after.max(minimum);
            }
            if let Some(maximum) = rule.maximum {
                after = after.min(maximum);
            }
            set_finance_ledger_value(&mut next, &rule.target, agent_index, after)?;
            append_finance_ledger_change(
                &mut ledger_changes,
                rule.target.strip_prefix("finance.").unwrap_or(&rule.target),
                before,
                Some(after),
            );
        }
        if agent_flows.has_flows() || !ledger_changes.is_empty() {
            finance_changes.push(AgentFinanceChangeReceipt {
                agent_index,
                currency: current.currency[agent_index].clone(),
                provenance: FinanceProvenanceReceipt {
                    status: current.status[agent_index].clone(),
                    source: current.source[agent_index].clone(),
                },
                flows: agent_flows,
                ledger_changes,
            });
        }
    }
    Ok(FinanceTickResult {
        columns: next,
        formula: rules
            .iter()
            .map(|rule| rule.formula.as_str())
            .collect::<Vec<_>>()
            .join("; "),
        finance_changes,
    })
}

fn validate_finance_rules(rules: &[FinanceLedgerRule]) -> CoreResult<()> {
    if rules.is_empty() {
        return Err(CoreError::new(
            "MISSING_FINANCE_RULES",
            "Finance execution requires at least one DSL ledger rule",
        ));
    }
    let mut ids = BTreeSet::new();
    let mut targets = BTreeSet::new();
    for (index, rule) in rules.iter().enumerate() {
        if !ids.insert(rule.id.as_str()) || !targets.insert(rule.target.as_str()) {
            return Err(CoreError::at(
                "DUPLICATE_FINANCE_RULE",
                "Finance ledger-rule ids and targets must be unique",
                format!("finance_rules.{index}"),
            ));
        }
        if !is_finance_ledger(&rule.target)
            || rule.terms.is_empty()
            || rule.formula.trim().is_empty()
            || rule.evidence.status.trim().is_empty()
            || rule.evidence.source.trim().is_empty()
            || rule.evidence.source_version.trim().is_empty()
            || !rule.evidence.uncertainty.is_finite()
            || !(0.0..=1.0).contains(&rule.evidence.uncertainty)
            || rule.minimum.is_some_and(|value| !value.is_finite())
            || rule.maximum.is_some_and(|value| !value.is_finite())
            || matches!((rule.minimum, rule.maximum), (Some(minimum), Some(maximum)) if minimum > maximum)
        {
            return Err(CoreError::at(
                "INVALID_FINANCE_RULE",
                "Finance ledger rules require a supported target, terms, ordered bounds, formula, and evidence",
                format!("finance_rules.{index}"),
            ));
        }
        for (input, coefficient) in &rule.terms {
            if !is_finance_input(input) || !coefficient.is_finite() {
                return Err(CoreError::at(
                    "INVALID_FINANCE_RULE_INPUT",
                    "Finance ledger-rule inputs and coefficients must be supported and finite",
                    format!("finance_rules.{index}.terms.{input}"),
                ));
            }
        }
    }
    Ok(())
}

fn is_finance_ledger(name: &str) -> bool {
    matches!(
        name,
        "finance.money"
            | "finance.income"
            | "finance.expenses"
            | "finance.savings"
            | "finance.debt"
    )
}

fn is_finance_input(name: &str) -> bool {
    is_finance_ledger(name)
        || matches!(
            name,
            "cash_flow.wages"
                | "cash_flow.business_income"
                | "cash_flow.transfers"
                | "cash_flow.housing"
                | "cash_flow.food"
                | "cash_flow.transport"
                | "cash_flow.other_expenses"
                | "cash_flow.taxes"
                | "cash_flow.savings_contribution"
                | "cash_flow.savings_withdrawal"
                | "cash_flow.debt_draw"
                | "cash_flow.debt_repayment"
        )
}

fn finance_ledger_value(
    finances: &FinanceColumns,
    name: &str,
    agent_index: usize,
) -> CoreResult<Option<f64>> {
    let value = match name {
        "finance.money" => finances.money[agent_index],
        "finance.income" => finances.income[agent_index],
        "finance.expenses" => finances.expenses[agent_index],
        "finance.savings" => finances.savings[agent_index],
        "finance.debt" => finances.debt[agent_index],
        _ => {
            return Err(CoreError::at(
                "UNKNOWN_FINANCE_LEDGER",
                format!("Unknown finance ledger {name}"),
                name,
            ));
        }
    };
    Ok(value)
}

fn finance_input(
    finances: &FinanceColumns,
    flows: &CashFlowColumns,
    name: &str,
    agent_index: usize,
) -> CoreResult<f64> {
    if name.starts_with("finance.") {
        return finance_ledger_value(finances, name, agent_index)?.ok_or_else(|| {
            CoreError::at(
                "UNKNOWN_FINANCE_STATE",
                format!("Finance ledger input {name} is unknown"),
                format!("{name}.{agent_index}"),
            )
        });
    }
    let value = match name {
        "cash_flow.wages" => flows.wages[agent_index],
        "cash_flow.business_income" => flows.business_income[agent_index],
        "cash_flow.transfers" => flows.transfers[agent_index],
        "cash_flow.housing" => flows.housing[agent_index],
        "cash_flow.food" => flows.food[agent_index],
        "cash_flow.transport" => flows.transport[agent_index],
        "cash_flow.other_expenses" => flows.other_expenses[agent_index],
        "cash_flow.taxes" => flows.taxes[agent_index],
        "cash_flow.savings_contribution" => flows.savings_contribution[agent_index],
        "cash_flow.savings_withdrawal" => flows.savings_withdrawal[agent_index],
        "cash_flow.debt_draw" => flows.debt_draw[agent_index],
        "cash_flow.debt_repayment" => flows.debt_repayment[agent_index],
        _ => {
            return Err(CoreError::at(
                "UNKNOWN_CASH_FLOW",
                format!("Unknown cash-flow input {name}"),
                name,
            ));
        }
    };
    Ok(value)
}

fn set_finance_ledger_value(
    finances: &mut FinanceColumns,
    name: &str,
    agent_index: usize,
    value: f64,
) -> CoreResult<()> {
    let target = match name {
        "finance.money" => &mut finances.money,
        "finance.income" => &mut finances.income,
        "finance.expenses" => &mut finances.expenses,
        "finance.savings" => &mut finances.savings,
        "finance.debt" => &mut finances.debt,
        _ => {
            return Err(CoreError::at(
                "UNKNOWN_FINANCE_LEDGER",
                format!("Unknown finance ledger {name}"),
                name,
            ));
        }
    };
    target[agent_index] = Some(value);
    Ok(())
}

fn append_finance_ledger_change(
    changes: &mut Vec<FinanceLedgerChangeReceipt>,
    ledger: &str,
    before: Option<f64>,
    after: Option<f64>,
) {
    if before == after {
        return;
    }
    changes.push(FinanceLedgerChangeReceipt {
        ledger: ledger.to_owned(),
        before,
        flow_delta: after.unwrap_or(0.0) - before.unwrap_or(0.0),
        after,
    });
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct EducationColumns {
    pub years_of_education: Vec<u8>,
    pub isced_level: Vec<Option<u8>>,
    pub country_label: Vec<String>,
    pub specialization: Vec<Option<String>>,
    pub specialization_threshold_years: Vec<u8>,
    pub provenance_status: Vec<String>,
    pub provenance_source: Vec<String>,
}

pub fn validate_education_columns(columns: &EducationColumns) -> CoreResult<()> {
    let lengths = [
        columns.years_of_education.len(),
        columns.isced_level.len(),
        columns.country_label.len(),
        columns.specialization.len(),
        columns.specialization_threshold_years.len(),
        columns.provenance_status.len(),
        columns.provenance_source.len(),
    ];
    let agent_count = lengths[0];
    if lengths.iter().any(|length| *length != agent_count) {
        return Err(CoreError::new(
            "EDUCATION_COLUMN_LENGTH_MISMATCH",
            "Every education column must contain the same number of agents",
        ));
    }
    for agent_index in 0..agent_count {
        if columns.years_of_education[agent_index] > 40
            || columns.isced_level[agent_index].is_some_and(|level| level > 8)
        {
            return Err(CoreError::at(
                "INVALID_EDUCATION_VALUE",
                "Education years must be at most 40 and ISCED levels at most 8",
                format!("education.{agent_index}"),
            ));
        }
        if columns.specialization[agent_index].is_some()
            && columns.years_of_education[agent_index]
                < columns.specialization_threshold_years[agent_index]
        {
            return Err(CoreError::at(
                "SPECIALIZATION_BELOW_THRESHOLD",
                "Specialization is unavailable before the country threshold",
                format!("specialization.{agent_index}"),
            ));
        }
        if columns.country_label[agent_index].trim().is_empty()
            || columns.provenance_status[agent_index].trim().is_empty()
            || columns.provenance_source[agent_index].trim().is_empty()
        {
            return Err(CoreError::at(
                "MISSING_EDUCATION_PROVENANCE",
                "Education labels require country mapping provenance",
                format!("education.{agent_index}"),
            ));
        }
    }
    Ok(())
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
pub struct DirectedRelationshipState {
    pub source_agent_index: usize,
    pub target_agent_index: usize,
    pub values: BTreeMap<String, f64>,
}

pub fn validate_directed_relationship_states(
    relationships: &[DirectedRelationshipState],
    agent_count: usize,
) -> CoreResult<()> {
    for (index, relationship) in relationships.iter().enumerate() {
        if relationship.source_agent_index >= agent_count
            || relationship.target_agent_index >= agent_count
            || relationship.source_agent_index == relationship.target_agent_index
        {
            return Err(CoreError::at(
                "INVALID_RELATIONSHIP_ENDPOINT",
                "Directed relationship states require two distinct existing agents",
                format!("relationships.{index}"),
            ));
        }
        if relationship.values.is_empty()
            || relationship
                .values
                .iter()
                .any(|(state_id, value)| state_id.trim().is_empty() || !value.is_finite())
        {
            return Err(CoreError::at(
                "INVALID_RELATIONSHIP_STATE",
                "Directed relationship state ids must be non-empty and values finite",
                format!("relationships.{index}.values"),
            ));
        }
    }
    Ok(())
}
