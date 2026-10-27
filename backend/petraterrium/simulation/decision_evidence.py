from __future__ import annotations

from datetime import date
from math import prod
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

IdentifierPattern = r"^[a-z][a-z0-9_-]*$"
Scalar = str | int | float | bool
DecisionDomain = Literal[
    "work",
    "social",
    "family",
    "health",
    "consumption",
    "political",
    "other",
]
InputKind = Literal["trait", "place", "time", "context"]
PlaceLevel = Literal["city", "country", "region", "global"]
EvidenceBasis = Literal["measured_joint", "fitted_model", "marginal"]
FactorStatus = Literal[
    "measured",
    "independence_estimate",
    "inherited",
    "imputed",
    "unknown",
    "label_only",
    "ambiguous",
]


class DecisionEvidenceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class ResearchCitation(DecisionEvidenceModel):
    kind: Literal["article", "research_paper"]
    imported_source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source: str = Field(min_length=1)
    publication_date: date
    population_studied: str = Field(min_length=1)
    link_or_reference: str = Field(min_length=1)
    supports_decision_ids: tuple[str, ...] = Field(min_length=1)
    supports_factor_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_support_targets(self):
        if len(set(self.supports_decision_ids)) != len(self.supports_decision_ids):
            raise ValueError("Citation decision support ids must be unique")
        if len(set(self.supports_factor_ids)) != len(self.supports_factor_ids):
            raise ValueError("Citation factor support ids must be unique")
        return self


class NoSourceAttachment(DecisionEvidenceModel):
    kind: Literal["none"] = "none"
    label: Literal["no source attached — estimated / unknown"] = (
        "no source attached — estimated / unknown"
    )
    reason: str = Field(min_length=1)


SourceAttachment = ResearchCitation | NoSourceAttachment


class EvidencePlace(DecisionEvidenceModel):
    level: PlaceLevel
    place_id: str = Field(min_length=1)
    region_id: str | None = None
    country_id: str | None = None
    city_id: str | None = None

    @model_validator(mode="after")
    def valid_hierarchy(self):
        if self.level == "global":
            if self.place_id != "global" or any(
                item is not None
                for item in (self.region_id, self.country_id, self.city_id)
            ):
                raise ValueError("Global evidence must use only the global place id")
        if self.level == "region":
            if self.region_id != self.place_id or any(
                item is not None for item in (self.country_id, self.city_id)
            ):
                raise ValueError("Region evidence must identify only its region")
        if self.level == "country":
            if (
                self.region_id is None
                or self.country_id != self.place_id
                or self.city_id is not None
            ):
                raise ValueError("Country evidence requires its region and country id")
        if self.level == "city":
            if (
                self.region_id is None
                or self.country_id is None
                or self.city_id != self.place_id
            ):
                raise ValueError("City evidence requires its region, country, and city id")
        return self


class AgentPlace(DecisionEvidenceModel):
    region_id: str = Field(min_length=1)
    country_id: str | None = Field(default=None, min_length=1)
    city_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def city_requires_country(self):
        if self.city_id is not None and self.country_id is None:
            raise ValueError("City agent places require a country id")
        return self


class AgentDecisionContext(DecisionEvidenceModel):
    agent_id: str = Field(min_length=1)
    place: AgentPlace
    traits: dict[str, Scalar] = Field(default_factory=dict)
    place_attributes: dict[str, Scalar] = Field(default_factory=dict)
    time: dict[str, Scalar] = Field(default_factory=dict)
    context: dict[str, Scalar] = Field(default_factory=dict)


class EvidencePredicate(DecisionEvidenceModel):
    operator: Literal["exact", "one_of", "between", "any"]
    value: Scalar | None = None
    values: tuple[Scalar, ...] = ()
    lower: float | None = None
    upper: float | None = None

    @model_validator(mode="after")
    def valid_operands(self):
        if self.operator == "exact" and self.value is None:
            raise ValueError("Exact evidence predicates require a value")
        if self.operator == "one_of" and not self.values:
            raise ValueError("One-of evidence predicates require values")
        if self.operator == "between":
            if self.lower is None or self.upper is None or self.lower > self.upper:
                raise ValueError("Between evidence predicates require an ordered range")
        if self.operator == "any" and any(
            item is not None for item in (self.value, self.lower, self.upper)
        ):
            raise ValueError("Any evidence predicates cannot constrain a value")
        return self


class ProbabilityFactor(DecisionEvidenceModel):
    id: str = Field(pattern=IdentifierPattern)
    name: str = Field(min_length=1)
    input_kind: InputKind
    input_key: str = Field(pattern=IdentifierPattern)
    feature_id: str | None = Field(default=None, pattern=IdentifierPattern)

    @model_validator(mode="after")
    def trait_has_feature(self):
        if self.input_kind == "trait" and self.feature_id is None:
            raise ValueError("Trait probability factors require a feature id")
        if self.input_kind != "trait" and self.feature_id is not None:
            raise ValueError("Only trait probability factors may name a feature")
        return self


class DecisionProbabilityFormula(DecisionEvidenceModel):
    id: str = Field(pattern=IdentifierPattern)
    name: str = Field(min_length=1)
    combination: Literal["product"]
    factors: tuple[ProbabilityFactor, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def valid_factor_combination(self):
        factor_ids = [factor.id for factor in self.factors]
        if len(set(factor_ids)) != len(factor_ids):
            raise ValueError("Probability formula factor ids must be unique")
        if len({factor.input_kind for factor in self.factors}) < 2:
            raise ValueError("Probability formulas must combine multiple input kinds")
        return self


class DecisionNodeTemplate(DecisionEvidenceModel):
    id: str = Field(pattern=IdentifierPattern)
    label: str = Field(min_length=1)
    kind: Literal["decision", "state", "action", "terminal"]


class DecisionEdgeTemplate(DecisionEvidenceModel):
    id: str = Field(pattern=IdentifierPattern)
    decision_id: str = Field(pattern=IdentifierPattern)
    domain: DecisionDomain
    from_state: str = Field(pattern=IdentifierPattern)
    to_state: str = Field(pattern=IdentifierPattern)
    label: str = Field(min_length=1)
    formula: DecisionProbabilityFormula
    source: SourceAttachment

    @model_validator(mode="after")
    def citation_supports_decision(self):
        if (
            isinstance(self.source, ResearchCitation)
            and self.decision_id not in self.source.supports_decision_ids
        ):
            raise ValueError("Attached citation does not support this decision")
        return self


class DecisionTreeTemplate(DecisionEvidenceModel):
    id: str = Field(pattern=IdentifierPattern)
    name: str = Field(min_length=1)
    domain: DecisionDomain
    status: Literal["awaiting_evidence", "ready"]
    entry_state: str = Field(pattern=IdentifierPattern)
    terminal_states: tuple[str, ...] = Field(min_length=1)
    nodes: tuple[DecisionNodeTemplate, ...] = Field(min_length=2)
    edges: tuple[DecisionEdgeTemplate, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_graph(self):
        node_ids = [node.id for node in self.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("Decision tree node ids must be unique")
        known_nodes = set(node_ids)
        if self.entry_state not in known_nodes:
            raise ValueError("Decision tree entry state must reference a node")
        if not set(self.terminal_states).issubset(known_nodes):
            raise ValueError("Decision tree terminal states must reference nodes")
        for edge in self.edges:
            if edge.decision_id != self.id or edge.domain != self.domain:
                raise ValueError("Decision tree edges must match their tree and domain")
            if edge.from_state not in known_nodes or edge.to_state not in known_nodes:
                raise ValueError("Decision tree edges must reference known nodes")
        return self


class DecisionFactorEvidence(DecisionEvidenceModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
    decision_id: str = Field(pattern=IdentifierPattern)
    edge_id: str = Field(pattern=IdentifierPattern)
    factor_id: str = Field(pattern=IdentifierPattern)
    place: EvidencePlace
    predicate: EvidencePredicate
    basis: EvidenceBasis
    estimate: float = Field(ge=0, le=1, allow_inf_nan=False)
    ci_low: float = Field(ge=0, le=1, allow_inf_nan=False)
    ci_high: float = Field(ge=0, le=1, allow_inf_nan=False)
    sample_size: int = Field(gt=0)
    held_out_sample_size: int | None = Field(default=None, gt=0)
    fittable: bool
    source: ResearchCitation

    @model_validator(mode="after")
    def valid_evidence(self):
        if not self.ci_low <= self.estimate <= self.ci_high:
            raise ValueError("Factor estimate must be inside its confidence interval")
        if self.basis == "marginal" and self.fittable:
            raise ValueError("Marginal evidence cannot be fitted as an outcome link")
        if self.basis != "marginal" and not self.fittable:
            raise ValueError("Joint or fitted evidence must be marked fittable")
        if self.basis == "fitted_model" and self.held_out_sample_size is None:
            raise ValueError("Fitted evidence requires a held-out sample")
        if self.decision_id not in self.source.supports_decision_ids:
            raise ValueError("Evidence citation does not support its decision")
        if self.factor_id not in self.source.supports_factor_ids:
            raise ValueError("Evidence citation does not support its factor")
        return self


class EvaluatedFactorReceipt(DecisionEvidenceModel):
    factor_id: str
    factor_name: str
    input_kind: InputKind
    input_key: str
    evaluated_value: Scalar | None
    status: FactorStatus
    estimate: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    ci_low: float = Field(ge=0, le=1, allow_inf_nan=False)
    ci_high: float = Field(ge=0, le=1, allow_inf_nan=False)
    fittable: bool
    evidence_id: str | None
    evidence_basis: EvidenceBasis | None
    evidence_place: EvidencePlace | None
    resolved_level: PlaceLevel | None
    resolution_status: Literal["direct", "inherited", "imputed"] | None
    source: SourceAttachment
    message: str


class EvaluatedDecisionProbability(DecisionEvidenceModel):
    decision_id: str
    edge_id: str
    formula_id: str
    formula_name: str
    expression: str
    agent_id: str
    status: Literal["measured", "independence_estimate", "unknown"]
    status_label: str
    probability: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    ci_low: float = Field(ge=0, le=1, allow_inf_nan=False)
    ci_high: float = Field(ge=0, le=1, allow_inf_nan=False)
    fittable: bool
    factors: tuple[EvaluatedFactorReceipt, ...]
    source: SourceAttachment


def _input_value(factor: ProbabilityFactor, context: AgentDecisionContext) -> Scalar | None:
    values = {
        "trait": context.traits,
        "place": context.place_attributes,
        "time": context.time,
        "context": context.context,
    }[factor.input_kind]
    return values.get(factor.input_key)


def _predicate_matches(predicate: EvidencePredicate, value: Scalar) -> bool:
    if predicate.operator == "any":
        return True
    if predicate.operator == "exact":
        return value == predicate.value
    if predicate.operator == "one_of":
        return value in predicate.values
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    return predicate.lower <= value <= predicate.upper


def _place_specificity(evidence: EvidencePlace, agent: AgentPlace) -> int | None:
    if evidence.level == "city":
        if (
            agent.city_id == evidence.city_id == evidence.place_id
            and agent.country_id == evidence.country_id
            and agent.region_id == evidence.region_id
        ):
            return 4
        return None
    if evidence.level == "country":
        if (
            agent.country_id == evidence.country_id == evidence.place_id
            and agent.region_id == evidence.region_id
        ):
            return 3
        return None
    if evidence.level == "region":
        return 2 if agent.region_id == evidence.region_id == evidence.place_id else None
    return 1 if evidence.place_id == "global" else None


def _unknown_factor(
    factor: ProbabilityFactor,
    value: Scalar | None,
    status: Literal["unknown", "label_only", "ambiguous"],
    message: str,
) -> EvaluatedFactorReceipt:
    return EvaluatedFactorReceipt(
        factor_id=factor.id,
        factor_name=factor.name,
        input_kind=factor.input_kind,
        input_key=factor.input_key,
        evaluated_value=value,
        status=status,
        estimate=None,
        ci_low=0,
        ci_high=1,
        fittable=False,
        evidence_id=None,
        evidence_basis=None,
        evidence_place=None,
        resolved_level=None,
        resolution_status=None,
        source=NoSourceAttachment(reason=message),
        message=message,
    )


def _resolve_factor(
    edge: DecisionEdgeTemplate,
    factor: ProbabilityFactor,
    context: AgentDecisionContext,
    evidence_rows: list[DecisionFactorEvidence],
) -> EvaluatedFactorReceipt:
    value = _input_value(factor, context)
    if value is None:
        return _unknown_factor(
            factor,
            value,
            "unknown",
            f"Agent input {factor.input_key} is missing",
        )
    matches: list[tuple[int, DecisionFactorEvidence]] = []
    for row in evidence_rows:
        if (
            row.decision_id != edge.decision_id
            or row.edge_id != edge.id
            or row.factor_id != factor.id
            or not _predicate_matches(row.predicate, value)
        ):
            continue
        specificity = _place_specificity(row.place, context.place)
        if specificity is None:
            continue
        if factor.feature_id == "mbti" and (
            row.basis != "measured_joint" or row.place.level not in {"city", "country"}
        ):
            continue
        matches.append((specificity, row))
    if not matches:
        if factor.feature_id == "mbti":
            return _unknown_factor(
                factor,
                value,
                "label_only",
                "MBTI is label-only without population-specific measured joint outcome evidence",
            )
        return _unknown_factor(
            factor,
            value,
            "unknown",
            (
                f"No qualifying {factor.name} evidence for city, country, region, or global "
                f"scope of {context.place.country_id or context.place.region_id}"
            ),
        )
    highest_specificity = max(specificity for specificity, _ in matches)
    selected = [row for specificity, row in matches if specificity == highest_specificity]
    if len(selected) != 1:
        return _unknown_factor(
            factor,
            value,
            "ambiguous",
            f"Multiple equally specific evidence rows match {factor.name}",
        )
    row = selected[0]
    independence = row.basis == "marginal"
    agent_specificity = (
        4
        if context.place.city_id is not None
        else (3 if context.place.country_id is not None else 2)
    )
    selected_specificity = highest_specificity
    resolution_status: Literal["direct", "inherited", "imputed"] = "direct"
    if selected_specificity < agent_specificity:
        resolution_status = (
            "inherited"
            if selected_specificity == agent_specificity - 1
            else "imputed"
        )
    country_inherited_by_city = agent_specificity == 4 and selected_specificity == 3
    blocked_fallback = (
        selected_specificity < agent_specificity and not country_inherited_by_city
    )
    status: FactorStatus = (
        resolution_status
        if blocked_fallback
        else ("independence_estimate" if independence else "measured")
    )
    return EvaluatedFactorReceipt(
        factor_id=factor.id,
        factor_name=factor.name,
        input_kind=factor.input_kind,
        input_key=factor.input_key,
        evaluated_value=value,
        status=status,
        estimate=row.estimate,
        ci_low=0 if independence else row.ci_low,
        ci_high=1 if independence else row.ci_high,
        fittable=row.fittable and not independence and not blocked_fallback,
        evidence_id=row.id,
        evidence_basis=row.basis,
        evidence_place=row.place,
        resolved_level=row.place.level,
        resolution_status=resolution_status,
        source=row.source,
        message=(
            (
                f"{resolution_status} from {row.place.level} evidence for "
                f"{row.place.place_id}; "
                + (
                    "blocked as a predictor for this agent place"
                    if blocked_fallback
                    else "executed with its source place retained"
                )
            )
            if resolution_status != "direct"
            else (
                "independence estimate — not measured"
                if independence
                else f"Resolved from {row.place.level} evidence for {row.place.place_id}"
            )
        ),
    )


def evaluate_decision_edge(
    edge: DecisionEdgeTemplate,
    context: AgentDecisionContext,
    evidence_rows: list[DecisionFactorEvidence],
) -> EvaluatedDecisionProbability:
    factors = tuple(
        _resolve_factor(edge, factor, context, evidence_rows)
        for factor in edge.formula.factors
    )
    expression = f"P({edge.label}) = " + " × ".join(
        factor.name for factor in edge.formula.factors
    )
    unresolved = any(
        factor.status
        in {"unknown", "label_only", "ambiguous", "inherited", "imputed"}
        for factor in factors
    )
    source_missing = isinstance(edge.source, NoSourceAttachment)
    if unresolved or source_missing:
        return EvaluatedDecisionProbability(
            decision_id=edge.decision_id,
            edge_id=edge.id,
            formula_id=edge.formula.id,
            formula_name=edge.formula.name,
            expression=expression,
            agent_id=context.agent_id,
            status="unknown",
            status_label="no source attached — estimated / unknown"
            if source_missing
            else "unknown — qualifying evidence missing",
            probability=None,
            ci_low=0,
            ci_high=1,
            fittable=False,
            factors=factors,
            source=edge.source,
        )
    probability = prod(factor.estimate for factor in factors if factor.estimate is not None)
    independence = any(factor.status == "independence_estimate" for factor in factors)
    inherited = any(factor.resolution_status == "inherited" for factor in factors)
    return EvaluatedDecisionProbability(
        decision_id=edge.decision_id,
        edge_id=edge.id,
        formula_id=edge.formula.id,
        formula_name=edge.formula.name,
        expression=expression,
        agent_id=context.agent_id,
        status="independence_estimate" if independence else "measured",
        status_label=(
            "independence estimate — not measured"
            if independence
            else (
                "measured at source place — inherited by agent place"
                if inherited
                else "measured"
            )
        ),
        probability=probability,
        ci_low=0 if independence else prod(factor.ci_low for factor in factors),
        ci_high=1 if independence else prod(factor.ci_high for factor in factors),
        fittable=not independence and all(factor.fittable for factor in factors),
        factors=factors,
        source=edge.source,
    )


def _template_factors(
    prefix: str,
    trait_key: str,
    place_key: str,
    time_key: str,
    context_key: str,
) -> tuple[ProbabilityFactor, ...]:
    return (
        ProbabilityFactor(
            id=f"{prefix}_trait",
            name=trait_key.replace("_", " ").title(),
            input_kind="trait",
            input_key=trait_key,
            feature_id=trait_key,
        ),
        ProbabilityFactor(
            id=f"{prefix}_place",
            name=place_key.replace("_", " ").title(),
            input_kind="place",
            input_key=place_key,
        ),
        ProbabilityFactor(
            id=f"{prefix}_time",
            name=time_key.replace("_", " ").title(),
            input_kind="time",
            input_key=time_key,
        ),
        ProbabilityFactor(
            id=f"{prefix}_context",
            name=context_key.replace("_", " ").title(),
            input_kind="context",
            input_key=context_key,
        ),
    )


def _domain_template(
    identity: str,
    name: str,
    domain: DecisionDomain,
    action_label: str,
    trait_key: str,
    place_key: str,
    time_key: str,
    context_key: str,
) -> DecisionTreeTemplate:
    entry_state = f"consider_{identity}"
    terminal_state = f"choose_{identity}"
    return DecisionTreeTemplate(
        id=identity,
        name=name,
        domain=domain,
        status="awaiting_evidence",
        entry_state=entry_state,
        terminal_states=(terminal_state,),
        nodes=(
            DecisionNodeTemplate(id=entry_state, label=name, kind="decision"),
            DecisionNodeTemplate(id=terminal_state, label=action_label, kind="terminal"),
        ),
        edges=(
            DecisionEdgeTemplate(
                id=f"{identity}_edge",
                decision_id=identity,
                domain=domain,
                from_state=entry_state,
                to_state=terminal_state,
                label=action_label,
                formula=DecisionProbabilityFormula(
                    id=f"{identity}_formula",
                    name=f"{action_label} probability",
                    combination="product",
                    factors=_template_factors(
                        identity,
                        trait_key,
                        place_key,
                        time_key,
                        context_key,
                    ),
                ),
                source=NoSourceAttachment(
                    reason="Template awaits an imported article or research paper"
                ),
            ),
        ),
    )


def decision_domain_templates() -> tuple[DecisionTreeTemplate, ...]:
    return (
        _domain_template(
            "accept_overtime",
            "Overtime decision",
            "work",
            "Accept overtime",
            "conscientiousness",
            "workplace_open",
            "shift_period",
            "overtime_offered",
        ),
        _domain_template(
            "go_out_friday",
            "Friday social outing",
            "social",
            "Go out",
            "big_five_extraversion",
            "evening_venues_available",
            "weekday",
            "free_evening",
        ),
        _domain_template(
            "attend_family_dinner",
            "Family dinner attendance",
            "family",
            "Attend family dinner",
            "family_orientation",
            "family_dinner_location_open",
            "meal_period",
            "family_invitation",
        ),
        _domain_template(
            "seek_healthcare",
            "Healthcare decision",
            "health",
            "Seek healthcare",
            "risk_tolerance",
            "care_accessible",
            "symptom_duration",
            "symptom_severity",
        ),
        _domain_template(
            "make_purchase",
            "Discretionary purchase",
            "consumption",
            "Make purchase",
            "financial_risk_tolerance",
            "retailer_available",
            "pay_period",
            "disposable_income_available",
        ),
        _domain_template(
            "attend_civic_event",
            "Civic participation",
            "political",
            "Attend civic event",
            "political_interest",
            "civic_event_accessible",
            "event_period",
            "event_invitation",
        ),
        _domain_template(
            "use_public_transit",
            "Transport mode decision",
            "other",
            "Use public transit",
            "environmental_preference",
            "public_transit_available",
            "departure_period",
            "trip_required",
        ),
    )
