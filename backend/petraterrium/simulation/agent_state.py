import hashlib
import math
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

StateEvidenceStatus = Literal[
    "measured_joint",
    "measured_marginal",
    "inherited",
    "imputed",
    "literature_support",
    "default_estimated",
    "unknown",
    "simulated",
]
StateGroup = Literal[
    "emotion",
    "slow_trait",
    "health_body",
    "life_social",
    "social_economic",
]
STATE_EVIDENCE_STATUSES = {
    "measured_joint",
    "measured_marginal",
    "inherited",
    "imputed",
    "literature_support",
    "default_estimated",
    "unknown",
    "simulated",
}


class AgentStateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class StateEvidence(AgentStateModel):
    status: StateEvidenceStatus
    source: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    source_date: date | None = None
    url: str | None = None
    place: str = Field(min_length=1)
    population: str = Field(min_length=1)
    language: str | None = Field(default=None, min_length=2)
    original_title: str | None = Field(default=None, min_length=1)
    english_title: str | None = Field(default=None, min_length=1)
    search_source: str | None = Field(default=None, min_length=1)
    uncertainty: float = Field(ge=0, le=1, allow_inf_nan=False)
    default_reason: str | None = Field(default=None, min_length=1)


class StateRange(AgentStateModel):
    minimum: float = Field(allow_inf_nan=False)
    maximum: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1)

    @model_validator(mode="after")
    def ordered(self):
        if self.maximum <= self.minimum:
            raise ValueError("State range maximum must exceed minimum")
        return self


class StateEventEffect(AgentStateModel):
    event_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    direction: Literal["increases", "decreases", "sets", "contextual"]
    parameter_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    formula: str = Field(min_length=1)
    evidence: StateEvidence


class StateRecoveryRule(AgentStateModel):
    mode: Literal["stable", "decay", "recover", "event_driven"]
    parameter_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]*$")
    formula: str = Field(min_length=1)
    evidence: StateEvidence


class StateDecisionModifier(AgentStateModel):
    decision_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    state_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    formula: str = Field(min_length=1)
    coefficient: float | None = Field(default=None, allow_inf_nan=False)
    center: float = Field(default=0.5, allow_inf_nan=False)
    minimum_factor: float = Field(default=0, ge=0, allow_inf_nan=False)
    maximum_factor: float = Field(default=2, ge=0, allow_inf_nan=False)
    direction: Literal["increases", "decreases", "nonlinear", "contextual"]
    evidence: StateEvidence

    @model_validator(mode="after")
    def valid_factor_range(self):
        if self.maximum_factor < self.minimum_factor:
            raise ValueError("Decision modifier factor bounds must be ordered")
        return self


class StatePropagation(AgentStateModel):
    target_state_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    direction: Literal["increases", "decreases", "nonlinear", "contextual"]
    parameter_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    formula: str = Field(min_length=1)
    coefficient: float | None = Field(default=None, allow_inf_nan=False)
    evidence: StateEvidence


class StateRuntimeRule(AgentStateModel):
    target_state_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    intercept: float = Field(allow_inf_nan=False)
    coefficients: dict[str, float]
    minimum: float = Field(allow_inf_nan=False)
    maximum: float = Field(allow_inf_nan=False)
    formula: str = Field(min_length=1)
    evidence: StateEvidence

    @model_validator(mode="after")
    def valid_bounds(self):
        if self.maximum < self.minimum:
            raise ValueError("State runtime-rule bounds must be ordered")
        if any(not math.isfinite(value) for value in self.coefficients.values()):
            raise ValueError("State runtime-rule coefficients must be finite")
        return self


class AgentStateDefinition(AgentStateModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1)
    group: StateGroup
    description: str = Field(min_length=1)
    value_range: StateRange
    initial_feature_ids: tuple[str, ...] = ()
    initial_evidence: StateEvidence
    event_effects: tuple[StateEventEffect, ...] = ()
    recovery: StateRecoveryRule
    decision_modifiers: tuple[StateDecisionModifier, ...] = ()
    propagation: tuple[StatePropagation, ...] = ()


class AgentStateCatalog(AgentStateModel):
    version: str = Field(min_length=1)
    status: Literal["draft", "confirmed"]
    definitions: tuple[AgentStateDefinition, ...] = Field(min_length=1)
    runtime_rules: tuple[StateRuntimeRule, ...] = ()

    @model_validator(mode="after")
    def unique_definitions(self):
        identities = [definition.id for definition in self.definitions]
        if len(set(identities)) != len(identities):
            raise ValueError("Agent state definition ids must be unique")
        rule_targets = [rule.target_state_id for rule in self.runtime_rules]
        if len(set(rule_targets)) != len(rule_targets):
            raise ValueError("Agent state runtime-rule targets must be unique")
        unknown_targets = sorted(set(rule_targets) - set(identities))
        unknown_inputs = sorted(
            {
                state_id
                for rule in self.runtime_rules
                for state_id in rule.coefficients
                if state_id not in identities
            }
        )
        if unknown_targets:
            raise ValueError(
                "Agent state runtime rules target unknown states: "
                + ", ".join(unknown_targets)
            )
        if unknown_inputs:
            raise ValueError(
                "Agent state runtime rules use unknown states: "
                + ", ".join(unknown_inputs)
            )
        return self


class RelationshipStateDefinition(AgentStateModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    value_range: StateRange
    direction: Literal["source_to_target"] = "source_to_target"
    event_effects: tuple[StateEventEffect, ...]
    recovery: StateRecoveryRule


class RelationshipStateCatalog(AgentStateModel):
    version: str
    definitions: tuple[RelationshipStateDefinition, ...] = Field(min_length=1)


class AgentStateSystemView(AgentStateModel):
    agent_states: AgentStateCatalog
    relationship_states: RelationshipStateCatalog


class EducationLabel(AgentStateModel):
    years: int = Field(ge=0, le=40)
    isced_level: int = Field(ge=0, le=8)
    label: str = Field(min_length=1)


class CountryEducationMapping(AgentStateModel):
    country_code: str = Field(min_length=2, max_length=3)
    version: str = Field(min_length=1)
    labels: tuple[EducationLabel, ...] = Field(min_length=1)
    specialization_threshold_years: int = Field(ge=0, le=40)
    provenance: StateEvidence

    @model_validator(mode="after")
    def unique_years(self):
        years = [label.years for label in self.labels]
        if len(set(years)) != len(years):
            raise ValueError("Country education mapping years must be unique")
        if self.provenance.place != self.country_code:
            raise ValueError("Education mapping provenance must describe its country")
        return self


class EducationProfile(AgentStateModel):
    years_of_education: int | None = Field(default=None, ge=0, le=40)
    isced_level: int | None = Field(default=None, ge=0, le=8)
    country_label: str = Field(min_length=1)
    country_code: str = Field(min_length=2)
    specialization: str | None = None
    specialization_threshold_years: int = Field(ge=0, le=40)
    specialization_status: Literal[
        "present", "not_applicable", "awaiting_data"
    ]
    provenance: StateEvidence


class FinanceEvidence(StateEvidence):
    currency: str = Field(min_length=3, max_length=3)


class FinanceAmountRange(AgentStateModel):
    minimum: float = Field(ge=0, allow_inf_nan=False)
    median: float = Field(ge=0, allow_inf_nan=False)
    maximum: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def ordered(self):
        if not self.minimum <= self.median <= self.maximum:
            raise ValueError("Finance amount range must contain its median")
        return self


class FinanceCondition(AgentStateModel):
    age_min: int = Field(default=0, ge=0, le=125)
    age_max: int = Field(default=125, ge=0, le=125)
    education_years_min: int = Field(default=0, ge=0, le=40)
    education_years_max: int = Field(default=40, ge=0, le=40)
    sexes: tuple[str, ...] = ()
    occupations: tuple[str, ...] = ()
    specializations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def ordered(self):
        if self.age_max < self.age_min:
            raise ValueError("Finance age bounds must be ordered")
        if self.education_years_max < self.education_years_min:
            raise ValueError("Finance education bounds must be ordered")
        return self


class FinanceDistributionCell(AgentStateModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    condition: FinanceCondition
    weight: float = Field(gt=0, allow_inf_nan=False)
    money: FinanceAmountRange
    income: FinanceAmountRange
    expenses: FinanceAmountRange
    savings: FinanceAmountRange
    debt: FinanceAmountRange


class FinanceDistribution(AgentStateModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    place: str = Field(min_length=1)
    currency: str = Field(min_length=3, max_length=3)
    evidence: FinanceEvidence
    cells: tuple[FinanceDistributionCell, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def consistent(self):
        if self.evidence.place != self.place:
            raise ValueError("Finance evidence place must match its distribution")
        if self.evidence.currency != self.currency:
            raise ValueError("Finance evidence currency must match its distribution")
        identities = [cell.id for cell in self.cells]
        if len(set(identities)) != len(identities):
            raise ValueError("Finance distribution cell ids must be unique")
        return self


class FinanceProfileInput(AgentStateModel):
    agent_id: str = Field(min_length=1)
    place: str = Field(min_length=1)
    age: int = Field(ge=0, le=125)
    sex: str = Field(min_length=1)
    years_of_education: int = Field(ge=0, le=40)
    specialization: str | None = None
    occupation: str = Field(min_length=1)


class FinanceQuantity(AgentStateModel):
    value: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    evidence: FinanceEvidence


class FinanceState(AgentStateModel):
    currency: str = Field(min_length=3, max_length=3)
    status: StateEvidenceStatus
    source_distribution_id: str | None = None
    source_cell_id: str | None = None
    money: FinanceQuantity
    income: FinanceQuantity
    expenses: FinanceQuantity
    savings: FinanceQuantity
    debt: FinanceQuantity
    evidence: FinanceEvidence
    formula: str = (
        "money[t+1] = money[t] + wages + business_income + transfers + debt_draw + "
        "savings_withdrawal - housing - food - transport - other_expenses - taxes - "
        "savings_contribution - debt_repayment"
    )


class CashFlow(AgentStateModel):
    wages: float = Field(default=0, ge=0, allow_inf_nan=False)
    business_income: float = Field(default=0, ge=0, allow_inf_nan=False)
    transfers: float = Field(default=0, ge=0, allow_inf_nan=False)
    housing: float = Field(default=0, ge=0, allow_inf_nan=False)
    food: float = Field(default=0, ge=0, allow_inf_nan=False)
    transport: float = Field(default=0, ge=0, allow_inf_nan=False)
    other_expenses: float = Field(default=0, ge=0, allow_inf_nan=False)
    taxes: float = Field(default=0, ge=0, allow_inf_nan=False)
    savings_contribution: float = Field(default=0, ge=0, allow_inf_nan=False)
    savings_withdrawal: float = Field(default=0, ge=0, allow_inf_nan=False)
    debt_draw: float = Field(default=0, ge=0, allow_inf_nan=False)
    debt_repayment: float = Field(default=0, ge=0, allow_inf_nan=False)


class StateLinearRule(AgentStateModel):
    target_state_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    intercept: float = Field(default=0, allow_inf_nan=False)
    coefficients: dict[str, float]
    minimum: float = Field(allow_inf_nan=False)
    maximum: float = Field(allow_inf_nan=False)
    formula: str = Field(min_length=1)
    evidence: StateEvidence

    @model_validator(mode="after")
    def valid_bounds(self):
        if self.maximum < self.minimum:
            raise ValueError("State linear rule bounds must be ordered")
        return self


class StateTransitionPlan(AgentStateModel):
    rules: tuple[StateLinearRule, ...] = ()
    decision_modifiers: tuple[StateDecisionModifier, ...] = ()


class StateTickReceipt(AgentStateModel):
    state_id: str
    before: float
    event_delta: float
    equation_delta: float
    after: float
    formula: str
    evidence: StateEvidence


class StateTickResult(AgentStateModel):
    values: dict[str, float]
    receipts: tuple[StateTickReceipt, ...]


class AgentStateValue(AgentStateModel):
    state_id: str
    value: float | None = Field(default=None, allow_inf_nan=False)
    status: Literal["present", "unknown"]
    evidence: StateEvidence


class AgentStateVector(AgentStateModel):
    catalog_version: str
    values: tuple[AgentStateValue, ...]


class AgentFoundationInput(AgentStateModel):
    agent_id: str = Field(min_length=1)
    country_code: str = Field(min_length=2)
    traits: dict[str, Any]
    states: dict[str, str | int | float]


class AgentFoundationProfile(AgentStateModel):
    agent_id: str
    education: EducationProfile
    state_vector: AgentStateVector
    finances: FinanceState


def resolve_education_profile(
    years_of_education: int,
    country_code: str,
    specialization: str | None,
    mapping: CountryEducationMapping,
) -> EducationProfile:
    if mapping.country_code != country_code:
        raise ValueError("Education mapping does not describe the requested country")
    by_year = {label.years: label for label in mapping.labels}
    label = by_year.get(years_of_education)
    country_label = (
        label.label
        if label is not None
        else f"{years_of_education} completed years; local label unavailable"
    )
    threshold_met = years_of_education >= mapping.specialization_threshold_years
    normalized_specialization = specialization.strip() if specialization else None
    if not threshold_met:
        normalized_specialization = None
        specialization_status = "not_applicable"
    elif normalized_specialization:
        specialization_status = "present"
    else:
        specialization_status = "awaiting_data"
    return EducationProfile(
        years_of_education=years_of_education,
        isced_level=label.isced_level if label else None,
        country_label=country_label,
        country_code=country_code,
        specialization=normalized_specialization,
        specialization_threshold_years=mapping.specialization_threshold_years,
        specialization_status=specialization_status,
        provenance=mapping.provenance,
    )


def _numeric_trait(traits: dict[str, Any], key: str) -> float | None:
    value = traits.get(key)
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _trait_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _bounded_uncertainty(value: Any) -> float:
    try:
        uncertainty = float(value)
    except (TypeError, ValueError):
        return 1
    return uncertainty if math.isfinite(uncertainty) and 0 <= uncertainty <= 1 else 1


def _evidence_status(value: Any) -> StateEvidenceStatus:
    normalized = str(value or "unknown")
    return normalized if normalized in STATE_EVIDENCE_STATUSES else "unknown"


def education_profile_from_values(
    country_code: str,
    traits: dict[str, Any],
) -> EducationProfile:
    raw_years = _numeric_trait(traits, "years_of_education")
    years = (
        int(raw_years)
        if raw_years is not None and raw_years.is_integer() and 0 <= raw_years <= 40
        else None
    )
    raw_isced = _numeric_trait(traits, "education_isced")
    isced = (
        int(raw_isced)
        if raw_isced is not None and raw_isced.is_integer() and 0 <= raw_isced <= 8
        else None
    )
    threshold_value = _numeric_trait(traits, "specialization_threshold_years")
    threshold = (
        int(threshold_value)
        if threshold_value is not None
        and threshold_value.is_integer()
        and 0 <= threshold_value <= 40
        else 40
    )
    label_value = traits.get("education_country_label")
    label = str(label_value).strip() if label_value is not None else ""
    if not label:
        label = (
            f"{years} completed years; local label unavailable"
            if years is not None
            else "Years of education unavailable"
        )
    specialization_value = traits.get("specialization")
    specialization = (
        str(specialization_value).strip()
        if specialization_value is not None and str(specialization_value).strip()
        else None
    )
    if years is None:
        specialization_status = "awaiting_data"
        specialization = None
    elif years < threshold:
        specialization_status = "not_applicable"
        specialization = None
    elif specialization:
        specialization_status = "present"
    else:
        specialization_status = "awaiting_data"
    status = _evidence_status(traits.get("education_status"))
    evidence = StateEvidence(
        status=status,
        source=str(
            traits.get("education_source", "No imported country education mapping")
        ),
        source_version=str(traits.get("education_mapping_version", "unavailable")),
        source_date=_trait_date(traits.get("education_source_date")),
        place=country_code,
        population=str(
            traits.get("education_source_population", "No represented population")
        ),
        uncertainty=_bounded_uncertainty(traits.get("education_uncertainty", 1)),
        default_reason=(
            str(traits.get("education_default_reason"))
            if traits.get("education_default_reason")
            else (
                "Years or local labels remain unavailable until a country mapping is imported"
                if status == "unknown"
                else None
            )
        ),
    )
    return EducationProfile(
        years_of_education=years,
        isced_level=isced,
        country_label=label,
        country_code=country_code,
        specialization=specialization,
        specialization_threshold_years=threshold,
        specialization_status=specialization_status,
        provenance=evidence,
    )


def finance_state_from_values(
    place: str,
    traits: dict[str, Any],
    states: dict[str, str | int | float],
) -> FinanceState:
    currency = str(traits.get("finance_currency", "XXX")).upper()
    if len(currency) != 3:
        currency = "XXX"
    values = {
        field: _state_amount(states.get(f"finance.{field}"))
        for field in ("money", "income", "expenses", "savings", "debt")
    }
    status = _evidence_status(traits.get("finance_status"))
    if any(value is None for value in values.values()):
        status = "unknown"
    evidence = FinanceEvidence(
        status=status,
        source=str(traits.get("finance_source", "No matching imported finance distribution")),
        source_version=str(traits.get("finance_source_version", "unavailable")),
        source_date=_trait_date(traits.get("finance_source_date")),
        url=(
            str(traits["finance_source_url"])
            if traits.get("finance_source_url")
            else None
        ),
        place=str(traits.get("finance_source_place", place)),
        population=str(
            traits.get("finance_source_population", "No represented population")
        ),
        uncertainty=_bounded_uncertainty(traits.get("finance_uncertainty", 1)),
        language=(
            str(traits["finance_language"])
            if traits.get("finance_language")
            else None
        ),
        original_title=(
            str(traits["finance_original_title"])
            if traits.get("finance_original_title")
            else None
        ),
        english_title=(
            str(traits["finance_english_title"])
            if traits.get("finance_english_title")
            else None
        ),
        search_source=(
            str(traits["finance_search_source"])
            if traits.get("finance_search_source")
            else None
        ),
        default_reason=(
            str(traits.get("finance_default_reason"))
            if traits.get("finance_default_reason")
            else (
                "Financial quantities remain unknown until a matching distribution is imported"
                if status == "unknown"
                else None
            )
        ),
        currency=currency,
    )
    quantities = {
        field: FinanceQuantity(value=value, evidence=evidence)
        for field, value in values.items()
    }
    return FinanceState(
        currency=currency,
        status=status,
        source_distribution_id=(
            str(traits["finance_distribution_id"])
            if traits.get("finance_distribution_id")
            else None
        ),
        source_cell_id=(
            str(traits["finance_cell_id"]) if traits.get("finance_cell_id") else None
        ),
        evidence=evidence,
        **quantities,
    )


def _state_amount(value: str | int | float | None) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def materialize_foundation_profiles(
    records: tuple[AgentFoundationInput, ...],
    catalog: AgentStateCatalog | None = None,
) -> tuple[AgentFoundationProfile, ...]:
    if len({record.agent_id for record in records}) != len(records):
        raise ValueError("Foundation profile agent ids must be unique")
    selected_catalog = catalog or core_agent_state_catalog()
    return tuple(
        AgentFoundationProfile(
            agent_id=record.agent_id,
            education=education_profile_from_values(record.country_code, record.traits),
            state_vector=state_vector_from_values(
                record.country_code,
                record.traits,
                record.states,
                selected_catalog,
            ),
            finances=finance_state_from_values(
                record.country_code, record.traits, record.states
            ),
        )
        for record in records
    )


def _condition_matches(
    condition: FinanceCondition, profile: FinanceProfileInput
) -> bool:
    specialization = profile.specialization or "none"
    return (
        condition.age_min <= profile.age <= condition.age_max
        and condition.education_years_min
        <= profile.years_of_education
        <= condition.education_years_max
        and (not condition.sexes or profile.sex in condition.sexes)
        and (not condition.occupations or profile.occupation in condition.occupations)
        and (
            not condition.specializations
            or specialization in condition.specializations
        )
    )


def _condition_specificity(condition: FinanceCondition) -> int:
    return (
        int(condition.age_min > 0 or condition.age_max < 125)
        + int(
            condition.education_years_min > 0
            or condition.education_years_max < 40
        )
        + int(bool(condition.sexes))
        + int(bool(condition.occupations))
        + int(bool(condition.specializations))
    )


def _unit_interval(*parts: object) -> float:
    canonical = ":".join(str(part) for part in parts)
    digest = hashlib.sha256(canonical.encode()).digest()
    return int.from_bytes(digest, "big") / (1 << (len(digest) * 8))


def _sample_amount(value: FinanceAmountRange, draw: float) -> float:
    if value.minimum == value.maximum:
        return value.minimum
    ratio = (value.median - value.minimum) / (value.maximum - value.minimum)
    if draw <= ratio:
        sampled = value.minimum + math.sqrt(
            draw * (value.maximum - value.minimum) * (value.median - value.minimum)
        )
    else:
        sampled = value.maximum - math.sqrt(
            (1 - draw)
            * (value.maximum - value.minimum)
            * (value.maximum - value.median)
        )
    return round(sampled, 2)


def _unknown_finance_evidence(place: str) -> FinanceEvidence:
    return FinanceEvidence(
        status="unknown",
        source="No matching imported finance distribution",
        source_version="unavailable",
        place=place,
        population="No represented population",
        uncertainty=1,
        default_reason=(
            "Money, income, expenses, savings, and debt remain unknown until an imported "
            "distribution matches place and agent conditions"
        ),
        currency="XXX",
    )


def initialize_finances(
    profile: FinanceProfileInput,
    distributions: tuple[FinanceDistribution, ...],
    seed: int,
) -> FinanceState:
    candidates = [
        (distribution, cell)
        for distribution in distributions
        if distribution.place == profile.place
        for cell in distribution.cells
        if _condition_matches(cell.condition, profile)
    ]
    if not candidates:
        evidence = _unknown_finance_evidence(profile.place)
        quantity = FinanceQuantity(value=None, evidence=evidence)
        return FinanceState(
            currency="XXX",
            status="unknown",
            money=quantity,
            income=quantity,
            expenses=quantity,
            savings=quantity,
            debt=quantity,
            evidence=evidence,
        )
    maximum_specificity = max(
        _condition_specificity(cell.condition) for _, cell in candidates
    )
    candidates = [
        item
        for item in candidates
        if _condition_specificity(item[1].condition) == maximum_specificity
    ]
    candidates.sort(key=lambda item: (item[0].id, item[1].id))
    total_weight = sum(cell.weight for _, cell in candidates)
    selection = _unit_interval(seed, profile.agent_id, "finance-cell") * total_weight
    cumulative = 0.0
    distribution, cell = candidates[-1]
    for candidate_distribution, candidate_cell in candidates:
        cumulative += candidate_cell.weight
        if selection <= cumulative:
            distribution, cell = candidate_distribution, candidate_cell
            break
    values = {
        field: _sample_amount(
            getattr(cell, field),
            _unit_interval(seed, profile.agent_id, distribution.id, cell.id, field),
        )
        for field in ("money", "income", "expenses", "savings", "debt")
    }
    quantities = {
        field: FinanceQuantity(value=value, evidence=distribution.evidence)
        for field, value in values.items()
    }
    return FinanceState(
        currency=distribution.currency,
        status=distribution.evidence.status,
        source_distribution_id=distribution.id,
        source_cell_id=cell.id,
        evidence=distribution.evidence,
        **quantities,
    )


def advance_finances(finances: FinanceState, flow: CashFlow) -> FinanceState:
    if any(
        quantity.value is None
        for quantity in (
            finances.money,
            finances.savings,
            finances.debt,
        )
    ):
        raise ValueError("Finance ticks require known money, savings, and debt")
    income = flow.wages + flow.business_income + flow.transfers
    expenses = flow.housing + flow.food + flow.transport + flow.other_expenses + flow.taxes
    money = (
        finances.money.value
        + income
        + flow.debt_draw
        + flow.savings_withdrawal
        - expenses
        - flow.savings_contribution
        - flow.debt_repayment
    )
    savings = finances.savings.value + flow.savings_contribution - flow.savings_withdrawal
    debt = finances.debt.value + flow.debt_draw - flow.debt_repayment
    if min(money, savings, debt) < 0:
        money = max(0, money)
        savings = max(0, savings)
        debt = max(0, debt)
    tick_evidence = FinanceEvidence(
        status="simulated",
        source="Rust numeric finance accounting tick",
        source_version="state-finance-v1",
        place=finances.evidence.place,
        population=finances.evidence.population,
        uncertainty=finances.evidence.uncertainty,
        default_reason="Accounting identity applied to recorded DSL cash-flow inputs",
        currency=finances.currency,
    )
    return finances.model_copy(
        update={
            "status": "simulated",
            "money": FinanceQuantity(value=round(money, 2), evidence=tick_evidence),
            "income": FinanceQuantity(value=round(income, 2), evidence=tick_evidence),
            "expenses": FinanceQuantity(value=round(expenses, 2), evidence=tick_evidence),
            "savings": FinanceQuantity(value=round(savings, 2), evidence=tick_evidence),
            "debt": FinanceQuantity(value=round(debt, 2), evidence=tick_evidence),
            "evidence": tick_evidence,
        }
    )


def advance_state_vector(
    values: dict[str, float],
    plan: StateTransitionPlan,
    event_deltas: dict[str, float],
) -> StateTickResult:
    current = {key: float(value) for key, value in values.items()}
    for state_id, delta in event_deltas.items():
        if state_id not in current:
            raise ValueError(f"Event references missing state {state_id!r}")
        if not math.isfinite(delta):
            raise ValueError(f"Event delta for {state_id!r} must be finite")
        current[state_id] += delta
    snapshot = dict(current)
    receipts = []
    for rule in plan.rules:
        if rule.target_state_id not in snapshot:
            raise ValueError(f"State rule target {rule.target_state_id!r} is missing")
        missing_inputs = set(rule.coefficients) - snapshot.keys()
        if missing_inputs:
            raise ValueError(
                f"State rule {rule.target_state_id!r} is missing inputs: "
                + ", ".join(sorted(missing_inputs))
            )
        equation_delta = rule.intercept + sum(
            coefficient * snapshot[state_id]
            for state_id, coefficient in rule.coefficients.items()
        )
        before = values[rule.target_state_id]
        event_delta = event_deltas.get(rule.target_state_id, 0)
        after = min(
            rule.maximum,
            max(rule.minimum, snapshot[rule.target_state_id] + equation_delta),
        )
        current[rule.target_state_id] = after
        receipts.append(
            StateTickReceipt(
                state_id=rule.target_state_id,
                before=before,
                event_delta=event_delta,
                equation_delta=equation_delta,
                after=after,
                formula=rule.formula,
                evidence=rule.evidence,
            )
        )
    return StateTickResult(values=current, receipts=tuple(receipts))


def evaluate_decision_probability(
    base_probability: float,
    values: dict[str, float],
    plan: StateTransitionPlan,
    decision_id: str,
) -> float:
    if not 0 <= base_probability <= 1:
        raise ValueError("Base decision probability must be between zero and one")
    probability = base_probability
    for modifier in plan.decision_modifiers:
        if modifier.decision_id != decision_id:
            continue
        if modifier.coefficient is None:
            raise ValueError(
                f"Decision modifier {decision_id!r} has no fitted or approved coefficient"
            )
        if modifier.state_id not in values:
            raise ValueError(
                f"Decision modifier {decision_id!r} needs state {modifier.state_id!r}"
            )
        factor = 1 + modifier.coefficient * (
            values[modifier.state_id] - modifier.center
        )
        factor = min(modifier.maximum_factor, max(modifier.minimum_factor, factor))
        probability *= factor
    return min(1, max(0, probability))


def state_vector(
    values: dict[str, str | int | float],
    catalog: AgentStateCatalog | None = None,
    value_evidence: dict[str, StateEvidence] | None = None,
) -> AgentStateVector:
    selected = catalog or core_agent_state_catalog()
    resolved = []
    for definition in selected.definitions:
        raw = values.get(definition.id)
        try:
            numeric = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            numeric = None
        if numeric is not None and not (
            definition.value_range.minimum
            <= numeric
            <= definition.value_range.maximum
        ):
            numeric = None
        resolved.append(
            AgentStateValue(
                state_id=definition.id,
                value=numeric,
                status="present" if numeric is not None else "unknown",
                evidence=(value_evidence or {}).get(
                    definition.id, definition.initial_evidence
                ),
            )
        )
    return AgentStateVector(catalog_version=selected.version, values=tuple(resolved))


def state_vector_from_values(
    place: str,
    traits: dict[str, Any],
    values: dict[str, str | int | float],
    catalog: AgentStateCatalog | None = None,
) -> AgentStateVector:
    selected = catalog or core_agent_state_catalog()
    raw_by_state = traits.get("state_provenance")
    by_state = raw_by_state if isinstance(raw_by_state, dict) else {}
    resolved: dict[str, StateEvidence] = {}
    for definition in selected.definitions:
        raw_evidence = by_state.get(definition.id)
        evidence = raw_evidence if isinstance(raw_evidence, dict) else {}
        status = _evidence_status(
            evidence.get("status", traits.get("state_status", "unknown"))
        )
        source = str(
            evidence.get(
                "source",
                traits.get("state_source", "No imported state-specific distribution"),
            )
        )
        source_version = str(
            evidence.get(
                "source_version",
                traits.get("state_source_version", "unavailable"),
            )
        )
        source_place = str(
            evidence.get("place", traits.get("state_source_place", place))
        )
        population = str(
            evidence.get(
                "population",
                traits.get("state_source_population", "No represented population"),
            )
        )
        reason_value = evidence.get(
            "default_reason", traits.get("state_default_reason")
        )
        reason = str(reason_value) if reason_value else None
        if status == "unknown" and reason is None:
            reason = (
                f"{definition.id} remains unknown until a matching distribution is imported"
            )
        resolved[definition.id] = StateEvidence(
            status=status,
            source=source or "No imported state-specific distribution",
            source_version=source_version or "unavailable",
            source_date=_trait_date(
                evidence.get("source_date", traits.get("state_source_date"))
            ),
            url=(
                str(evidence.get("url", traits.get("state_source_url")))
                if evidence.get("url", traits.get("state_source_url"))
                else None
            ),
            place=source_place or place,
            population=population or "No represented population",
            language=(
                str(evidence.get("language", traits.get("state_source_language")))
                if evidence.get("language", traits.get("state_source_language"))
                else None
            ),
            original_title=(
                str(evidence["original_title"])
                if evidence.get("original_title")
                else None
            ),
            english_title=(
                str(evidence["english_title"])
                if evidence.get("english_title")
                else None
            ),
            search_source=(
                str(evidence["search_source"])
                if evidence.get("search_source")
                else None
            ),
            uncertainty=_bounded_uncertainty(
                evidence.get("uncertainty", traits.get("state_uncertainty", 1))
            ),
            default_reason=reason,
        )
    return state_vector(values, selected, resolved)


def _unknown_evidence(reason: str) -> StateEvidence:
    return StateEvidence(
        status="unknown",
        source="No imported state-specific distribution",
        source_version="unavailable",
        place="Unresolved place",
        population="No represented population",
        uncertainty=1,
        default_reason=reason,
    )


def _literature_evidence(
    title: str,
    version: str,
    source_date: date,
    url: str,
    place: str,
    population: str,
) -> StateEvidence:
    return StateEvidence(
        status="literature_support",
        source=title,
        source_version=version,
        source_date=source_date,
        url=url,
        place=place,
        population=population,
        language="en",
        original_title=title,
        english_title=title,
        search_source="PubMed",
        uncertainty=1,
        default_reason=(
            "The source supports direction only; it does not supply a promoted coefficient"
        ),
    )


def _recovery(state_id: str, mode: str = "event_driven") -> StateRecoveryRule:
    parameter = None if mode == "stable" else f"{state_id}_recovery_rate"
    formula = (
        f"{state_id}[t+1] = {state_id}[t]"
        if mode == "stable"
        else (
            f"{state_id}[t+1] = clamp({state_id}[t] + "
            f"{state_id}_recovery_rate × ({state_id}_baseline - {state_id}[t]), 0, 1)"
        )
    )
    return StateRecoveryRule(
        mode=mode,
        parameter_id=parameter,
        formula=formula,
        evidence=_unknown_evidence(
            f"{state_id} recovery requires a place- and population-specific fitted rate"
        ),
    )


def _event(
    state_id: str,
    event_id: str,
    direction: Literal["increases", "decreases", "sets", "contextual"],
    evidence: StateEvidence | None = None,
) -> StateEventEffect:
    sign = "+" if direction == "increases" else "-" if direction == "decreases" else "±"
    parameter_id = f"{event_id}_{state_id}_effect"
    return StateEventEffect(
        event_id=event_id,
        direction=direction,
        parameter_id=parameter_id,
        formula=f"{state_id}[t+1] = clamp({state_id}[t] {sign} {parameter_id}, 0, 1)",
        evidence=evidence
        or _unknown_evidence(
            f"{event_id} to {state_id} needs a confirmed effect-size parameter"
        ),
    )


def _modifier(
    state_id: str,
    decision_id: str,
    direction: Literal["increases", "decreases", "nonlinear", "contextual"],
    evidence: StateEvidence | None = None,
) -> StateDecisionModifier:
    parameter_id = f"beta_{decision_id}_{state_id}"
    sign = "+" if direction == "increases" else "-" if direction == "decreases" else "±"
    return StateDecisionModifier(
        decision_id=decision_id,
        state_id=state_id,
        formula=(
            f"P({decision_id}) = clamp(base({decision_id}) × "
            f"(1 {sign} {parameter_id} × ({state_id} - 0.5)), 0, 1)"
        ),
        direction=direction,
        evidence=evidence
        or _unknown_evidence(
            f"{state_id} to {decision_id} needs linked state and outcome data"
        ),
    )


def _propagation(
    state_id: str,
    target_state_id: str,
    direction: Literal["increases", "decreases", "nonlinear", "contextual"],
    evidence: StateEvidence | None = None,
) -> StatePropagation:
    parameter_id = f"beta_{target_state_id}_{state_id}"
    sign = "+" if direction == "increases" else "-" if direction == "decreases" else "±"
    return StatePropagation(
        target_state_id=target_state_id,
        direction=direction,
        parameter_id=parameter_id,
        formula=(
            f"{target_state_id}[t+1] = clamp({target_state_id}[t] {sign} "
            f"{parameter_id} × {state_id}[t], 0, 1)"
        ),
        evidence=evidence
        or _unknown_evidence(
            f"{state_id} to {target_state_id} needs longitudinal joint data"
        ),
    )


def _definition(
    identity: str,
    name: str,
    group: StateGroup,
    description: str,
    *,
    initial_feature_ids: tuple[str, ...] = (),
    events: tuple[StateEventEffect, ...] = (),
    decisions: tuple[StateDecisionModifier, ...] = (),
    propagation: tuple[StatePropagation, ...] = (),
    recovery_mode: Literal["stable", "decay", "recover", "event_driven"] = "event_driven",
) -> AgentStateDefinition:
    return AgentStateDefinition(
        id=identity,
        name=name,
        group=group,
        description=description,
        value_range=StateRange(minimum=0, maximum=1, unit="normalized index"),
        initial_feature_ids=initial_feature_ids,
        initial_evidence=_unknown_evidence(
            f"Initialize {identity} only from a matching imported distribution; otherwise unknown"
        ),
        event_effects=events,
        recovery=_recovery(identity, recovery_mode),
        decision_modifiers=decisions,
        propagation=propagation,
    )


def core_agent_state_catalog() -> AgentStateCatalog:
    exercise_stress = _literature_evidence(
        (
            "Physical activity, mindfulness meditation, or heart rate variability "
            "biofeedback for stress reduction: a randomized controlled trial"
        ),
        "PMID 26111942",
        date(2015, 12, 1),
        "https://pubmed.ncbi.nlm.nih.gov/26111942/",
        "Netherlands",
        "76 enrolled adult participants in the randomized trial",
    )
    meal_evidence = _literature_evidence(
        "The effects of skipping a meal on daily energy intake and diet quality",
        "PMID 32398192",
        date(2020, 5, 13),
        "https://pubmed.ncbi.nlm.nih.gov/32398192/",
        "United States",
        "23,488 adults in NHANES 2007–2016",
    )
    sleep_evidence = _literature_evidence(
        "Examining the Effects of Sleep Deprivation on Decision-Making: A Scoping Review",
        "PMID 40564605",
        date(2025, 6, 16),
        "https://pubmed.ncbi.nlm.nih.gov/40564605/",
        "Multiple study locations",
        "2,276 participants across 25 included studies",
    )
    definitions = (
        _definition(
            "stress",
            "Stress",
            "emotion",
            "Current psychological strain that can affect health and several decisions.",
            events=(
                _event("stress", "work_outcome", "contextual"),
                _event("stress", "exercise", "decreases", exercise_stress),
                _event("stress", "financial_change", "contextual"),
            ),
            decisions=(
                _modifier("stress", "skip_lunch", "increases"),
                _modifier("stress", "go_to_gym", "contextual", exercise_stress),
                _modifier("stress", "work", "decreases"),
                _modifier("stress", "see_doctor", "increases"),
                _modifier("stress", "quit_job", "increases"),
            ),
            propagation=(
                _propagation("stress", "health", "decreases"),
                _propagation("stress", "fatigue", "increases"),
                _propagation("stress", "depression_level", "increases"),
            ),
            recovery_mode="decay",
        ),
        _definition(
            "outrage",
            "Outrage",
            "emotion",
            "Moral anger linked to a perceived violation.",
            events=(_event("outrage", "perceived_violation", "increases"),),
            decisions=(
                _modifier("outrage", "political_action", "increases"),
                _modifier("outrage", "violent_action", "contextual"),
            ),
            recovery_mode="decay",
        ),
        _definition(
            "fear",
            "Fear",
            "emotion",
            "Current perceived threat response.",
            events=(_event("fear", "threat_exposure", "increases"),),
            decisions=(
                _modifier("fear", "avoid_place", "increases"),
                _modifier("fear", "seek_safety", "increases"),
            ),
            recovery_mode="decay",
        ),
        _definition(
            "happiness",
            "Happiness",
            "emotion",
            "Current positive affect.",
            events=(_event("happiness", "positive_outcome", "increases"),),
            decisions=(_modifier("happiness", "socialize", "increases"),),
            recovery_mode="decay",
        ),
        _definition(
            "sadness",
            "Sadness",
            "emotion",
            "Current negative affect distinct from a depression condition.",
            events=(_event("sadness", "loss", "increases"),),
            decisions=(_modifier("sadness", "socialize", "decreases"),),
            propagation=(_propagation("sadness", "depression_level", "increases"),),
            recovery_mode="decay",
        ),
        _definition(
            "anger",
            "Anger",
            "emotion",
            "Current anger response.",
            events=(_event("anger", "conflict", "increases"),),
            decisions=(_modifier("anger", "confront", "increases"),),
            recovery_mode="decay",
        ),
        _definition(
            "generalized_trust",
            "Generalized trust",
            "emotion",
            "Trust in other people generally; directed trust remains relationship state.",
            initial_feature_ids=("generalized_trust",),
            events=(_event("generalized_trust", "social_outcome", "contextual"),),
            decisions=(_modifier("generalized_trust", "cooperate", "increases"),),
            recovery_mode="event_driven",
        ),
        _definition(
            "grief",
            "Grief",
            "emotion",
            "Loss-related distress with slower recovery than transient sadness.",
            events=(_event("grief", "bereavement", "increases"),),
            decisions=(_modifier("grief", "socialize", "contextual"),),
            propagation=(
                _propagation("grief", "sadness", "increases"),
                _propagation("grief", "depression_level", "increases"),
            ),
            recovery_mode="decay",
        ),
        _definition(
            "depression_level",
            "Depression level",
            "emotion",
            (
                "Current depression symptom burden, not a diagnosis unless linked clinical "
                "data supports it."
            ),
            events=(_event("depression_level", "clinical_change", "contextual"),),
            decisions=(
                _modifier("depression_level", "work", "decreases"),
                _modifier("depression_level", "seek_care", "increases"),
            ),
            propagation=(_propagation("depression_level", "health", "decreases"),),
            recovery_mode="recover",
        ),
        _definition(
            "loneliness",
            "Loneliness",
            "emotion",
            "Perceived social isolation.",
            events=(_event("loneliness", "social_contact", "decreases"),),
            decisions=(_modifier("loneliness", "seek_contact", "increases"),),
            propagation=(_propagation("loneliness", "depression_level", "increases"),),
            recovery_mode="event_driven",
        ),
        _definition(
            "impulsivity",
            "Impulsivity",
            "slow_trait",
            "Tendency to act with limited deliberation.",
            events=(_event("impulsivity", "long_term_change", "contextual"),),
            decisions=(_modifier("impulsivity", "high_consequence_action", "increases"),),
            recovery_mode="stable",
        ),
        _definition(
            "extraversion",
            "Extraversion",
            "slow_trait",
            "Stable tendency toward social engagement.",
            initial_feature_ids=("big_five",),
            events=(_event("extraversion", "long_term_change", "contextual"),),
            decisions=(_modifier("extraversion", "socialize", "increases"),),
            recovery_mode="stable",
        ),
        _definition(
            "conscientiousness",
            "Conscientiousness",
            "slow_trait",
            "Stable tendency toward planning and task persistence.",
            initial_feature_ids=("big_five",),
            events=(_event("conscientiousness", "long_term_change", "contextual"),),
            decisions=(_modifier("conscientiousness", "follow_routine", "increases"),),
            recovery_mode="stable",
        ),
        _definition(
            "risk_aversion",
            "Risk aversion",
            "slow_trait",
            "Preference for lower-risk options under uncertainty.",
            initial_feature_ids=("risk_tolerance",),
            events=(_event("risk_aversion", "long_term_change", "contextual"),),
            decisions=(_modifier("risk_aversion", "take_risk", "decreases"),),
            recovery_mode="stable",
        ),
        _definition(
            "work_ethic",
            "Work ethic",
            "slow_trait",
            "Stable work-effort tendency when work is available.",
            events=(_event("work_ethic", "long_term_change", "contextual"),),
            decisions=(_modifier("work_ethic", "work", "increases"),),
            recovery_mode="stable",
        ),
        _definition(
            "patience",
            "Patience",
            "slow_trait",
            "Willingness to defer an immediate outcome for a later one.",
            initial_feature_ids=("patience",),
            events=(_event("patience", "long_term_change", "contextual"),),
            decisions=(_modifier("patience", "defer_reward", "increases"),),
            recovery_mode="stable",
        ),
        _definition(
            "health",
            "Health",
            "health_body",
            "Current general health capacity.",
            events=(
                _event("health", "illness", "decreases"),
                _event("health", "treatment", "increases"),
                _event("health", "exercise", "increases"),
            ),
            decisions=(
                _modifier("health", "work", "increases"),
                _modifier("health", "go_to_gym", "increases"),
                _modifier("health", "see_doctor", "decreases"),
            ),
            recovery_mode="recover",
        ),
        _definition(
            "sleep_quality",
            "Sleep quality",
            "health_body",
            "Restorative quality of the most recent sleep period.",
            events=(_event("sleep_quality", "sleep", "contextual"),),
            decisions=(
                _modifier("sleep_quality", "take_risk", "contextual", sleep_evidence),
                _modifier("sleep_quality", "work", "increases", sleep_evidence),
            ),
            propagation=(_propagation("sleep_quality", "fatigue", "decreases"),),
            recovery_mode="event_driven",
        ),
        _definition(
            "hunger",
            "Hunger",
            "health_body",
            "Current unmet food need.",
            events=(
                _event("hunger", "meal", "decreases", meal_evidence),
                _event("hunger", "meal_skipped", "increases", meal_evidence),
            ),
            decisions=(
                _modifier("hunger", "eat", "increases", meal_evidence),
                _modifier("hunger", "skip_lunch", "decreases", meal_evidence),
            ),
            propagation=(_propagation("hunger", "fatigue", "increases"),),
            recovery_mode="event_driven",
        ),
        _definition(
            "fatigue",
            "Fatigue",
            "health_body",
            "Current physical and cognitive tiredness.",
            events=(
                _event("fatigue", "exertion", "increases"),
                _event("fatigue", "sleep", "decreases"),
            ),
            decisions=(
                _modifier("fatigue", "work", "decreases"),
                _modifier("fatigue", "rest", "increases"),
            ),
            recovery_mode="recover",
        ),
        _definition(
            "illness_severity",
            "Illness severity",
            "health_body",
            "Current illness burden, with zero meaning no active illness.",
            events=(
                _event("illness_severity", "exposure", "increases"),
                _event("illness_severity", "treatment", "decreases"),
            ),
            decisions=(
                _modifier("illness_severity", "work", "decreases"),
                _modifier("illness_severity", "see_doctor", "increases"),
            ),
            propagation=(_propagation("illness_severity", "health", "decreases"),),
            recovery_mode="recover",
        ),
        *(
            _definition(
                identity,
                name,
                "life_social",
                description,
                events=(_event(identity, event, "sets"),),
                decisions=(_modifier(identity, decision, direction),),
                recovery_mode="stable",
            )
            for identity, name, description, event, decision, direction in (
                (
                    "is_employed",
                    "Employment status",
                    "Whether the agent is employed.",
                    "employment_change",
                    "work",
                    "increases",
                ),
                (
                    "is_married",
                    "Marital status",
                    "Whether the agent is married.",
                    "marital_change",
                    "household_decision",
                    "contextual",
                ),
                (
                    "is_parent",
                    "Parent status",
                    "Whether the agent is a parent.",
                    "parenthood_change",
                    "care_for_child",
                    "increases",
                ),
                (
                    "is_student",
                    "Student status",
                    "Whether the agent is currently a student.",
                    "student_change",
                    "attend_school",
                    "increases",
                ),
                (
                    "is_retired",
                    "Retirement status",
                    "Whether the agent is retired.",
                    "retirement_change",
                    "work",
                    "decreases",
                ),
            )
        ),
        _definition(
            "social_status",
            "Social status",
            "social_economic",
            "Relative status within the agent's social setting.",
            events=(_event("social_status", "status_change", "contextual"),),
            decisions=(_modifier("social_status", "status_seeking", "contextual"),),
            recovery_mode="event_driven",
        ),
        _definition(
            "reputation",
            "Reputation",
            "social_economic",
            "Socially observed standing within a specific context.",
            events=(_event("reputation", "observed_action", "contextual"),),
            decisions=(_modifier("reputation", "cooperate", "contextual"),),
            recovery_mode="event_driven",
        ),
        _definition(
            "financial_stress",
            "Financial stress",
            "social_economic",
            "Strain associated with financial resources and obligations.",
            events=(_event("financial_stress", "financial_change", "contextual"),),
            decisions=(
                _modifier("financial_stress", "find_job", "increases"),
                _modifier("financial_stress", "skip_meal", "increases"),
                _modifier("financial_stress", "move", "contextual"),
            ),
            propagation=(_propagation("financial_stress", "stress", "increases"),),
            recovery_mode="event_driven",
        ),
        _definition(
            "job_satisfaction",
            "Job satisfaction",
            "social_economic",
            "Current satisfaction with employment conditions.",
            events=(_event("job_satisfaction", "work_outcome", "contextual"),),
            decisions=(
                _modifier("job_satisfaction", "work", "increases"),
                _modifier("job_satisfaction", "quit_job", "decreases"),
            ),
            recovery_mode="event_driven",
        ),
        _definition(
            "political_engagement",
            "Political engagement",
            "social_economic",
            "Current willingness to attend to or participate in politics.",
            events=(_event("political_engagement", "political_information", "contextual"),),
            decisions=(_modifier("political_engagement", "political_action", "increases"),),
            recovery_mode="event_driven",
        ),
    )
    return AgentStateCatalog(
        version="core-agent-states-v1",
        status="confirmed",
        definitions=definitions,
    )


def relationship_state_catalog() -> RelationshipStateCatalog:
    return RelationshipStateCatalog(
        version="directed-relationship-states-v1",
        definitions=(
            RelationshipStateDefinition(
                id="love",
                name="Love",
                description=(
                    "Directed attachment from one agent to one specific other agent; it is "
                    "never stored as a general agent state."
                ),
                value_range=StateRange(minimum=0, maximum=1, unit="normalized index"),
                event_effects=(
                    _event("love", "relationship_interaction", "contextual"),
                ),
                recovery=_recovery("love", "event_driven"),
            ),
            RelationshipStateDefinition(
                id="trust",
                name="Directed trust",
                description="Trust from one agent toward one specific other agent.",
                value_range=StateRange(minimum=-1, maximum=1, unit="normalized index"),
                event_effects=(
                    _event("trust", "relationship_interaction", "contextual"),
                ),
                recovery=_recovery("trust", "event_driven"),
            ),
        ),
    )
