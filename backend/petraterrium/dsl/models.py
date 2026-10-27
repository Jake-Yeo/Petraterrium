from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DSLModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


EvidenceStatus = Literal[
    "present",
    "inherited",
    "imputed",
    "missing",
    "unknown",
    "label_only",
    "literature_estimate",
    "hint_only",
]


class Evidence(DSLModel):
    source: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: EvidenceStatus
    uncertainty: float = Field(ge=0, le=1, allow_inf_nan=False)
    source_date: str | None = None


class Distribution(DSLModel):
    values: dict[str, float] = Field(min_length=1)
    provenance: Evidence

    @model_validator(mode="after")
    def valid_distribution(self):
        if any(value < 0 or value > 1 for value in self.values.values()):
            raise ValueError("Distribution probabilities must be between 0 and 1")
        if abs(sum(self.values.values()) - 1) > 1e-9:
            raise ValueError("Distribution probabilities must sum to 1")
        return self


class StateDefinition(DSLModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    values: list[str] = Field(min_length=2)
    initial: Distribution


class AttributeDefinition(DSLModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    kind: Literal["categorical", "continuous", "boolean"]
    values: list[str] = Field(default_factory=list)
    distribution: Distribution | None = None
    provenance: Evidence


class FeatureRange(DSLModel):
    minimum: float = Field(allow_inf_nan=False)
    maximum: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_range(self):
        if self.maximum <= self.minimum:
            raise ValueError("Feature range maximum must exceed minimum")
        return self


class FeatureDefinition(DSLModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    kind: Literal["categorical", "continuous", "binary"]
    canonical_values: list[str] = Field(default_factory=list)
    value_range: FeatureRange | None = None
    provenance: Evidence
    predictive: bool = True
    ancestry_linked: bool = False


class FeatureDistribution(DSLModel):
    feature_id: str
    level: Literal["global", "region", "subregion", "country", "city"]
    place: str = Field(min_length=1)
    population: str = Field(min_length=1)
    coverage_percent: float = Field(ge=0, le=100, allow_inf_nan=False)
    values: dict[str, float] = Field(default_factory=dict)
    mean: float | None = Field(default=None, allow_inf_nan=False)
    standard_deviation: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    provenance: Evidence
    method: Literal["measured", "compositional", "fallback"] = "measured"
    fallback_for: list[str] = Field(default_factory=list)
    explicit_fallback: bool = False


class JointDataProof(DSLModel):
    feature_id: str
    outcomes: list[str] = Field(min_length=1)
    population: str = Field(min_length=1)
    provenance: Evidence


class FeatureRegistry(DSLModel):
    version: str = Field(min_length=1)
    definitions: list[FeatureDefinition] = Field(min_length=1)
    distributions: list[FeatureDistribution] = Field(default_factory=list)
    joint_data: list[JointDataProof] = Field(default_factory=list)


class ChoiceCondition(DSLModel):
    traits: dict[str, str] = Field(default_factory=dict)
    state: dict[str, str] = Field(default_factory=dict)
    context: dict[str, str] = Field(default_factory=dict)
    place: str | None = None
    segment: str | None = None
    role: str | None = None


class ChoiceEvidence(DSLModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
    action_id: str
    conditioning_id: str = Field(min_length=1)
    conditioning: ChoiceCondition = Field(default_factory=ChoiceCondition)
    definition: str = Field(min_length=1)
    value: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    ci_low: float = Field(ge=0, le=1, allow_inf_nan=False)
    ci_high: float = Field(ge=0, le=1, allow_inf_nan=False)
    source_type: Literal[
        "administrative",
        "mobility",
        "transaction",
        "time_use_diary",
        "representative_survey",
        "small_study",
        "poll",
        "news",
        "ethnography",
        "social_media",
        "unknown",
    ]
    tier: int = Field(ge=1, le=5)
    sample_size: int | None = Field(default=None, gt=0)
    source_date: str | None = None
    population: str = Field(min_length=1)
    denominator: str = Field(min_length=1)
    time_unit: Literal["event", "hour", "day", "friday", "week", "year"]
    source_time_unit: Literal["event", "hour", "day", "friday", "week", "year"]
    explicit_time_adjustment: bool = False
    tier_flag: Literal["measured", "imputed", "hint_only", "unknown"]
    provenance: Evidence
    missing_requirement: str = ""

    @model_validator(mode="after")
    def valid_evidence(self):
        if self.ci_low > self.ci_high:
            raise ValueError("Choice confidence interval is reversed")
        if self.value is not None and not self.ci_low <= self.value <= self.ci_high:
            raise ValueError("Choice value must be inside its confidence interval")
        hint_sources = {"news", "ethnography", "social_media"}
        if self.source_type in hint_sources or self.tier == 5 and self.tier_flag == "hint_only":
            if self.tier != 5 or self.tier_flag != "hint_only" or self.value is not None:
                raise ValueError("Tier 5 evidence must remain hint-only without a coefficient")
        if self.source_type == "unknown" and self.tier_flag != "unknown":
            raise ValueError("Unknown choice evidence must remain unknown")
        if self.tier_flag == "unknown" and (
            self.value is not None or self.ci_low != 0 or self.ci_high != 1
        ):
            raise ValueError("Unknown choice evidence needs a 0 to 1 interval and no coefficient")
        if self.tier_flag == "measured" and (self.value is None or self.sample_size is None):
            raise ValueError("Measured choice evidence needs a value and sample size")
        if (
            self.time_unit == "friday"
            and self.source_time_unit != "friday"
            and not self.explicit_time_adjustment
        ):
            raise ValueError("A Friday rate needs Friday-specific data or an explicit adjustment")
        return self


class RuleCondition(DSLModel):
    attribute: str
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "in"]
    value: str | float | bool | list[str]


class GraphTraversal(DSLModel):
    primitive: Literal["neighbors"] = "neighbors"
    network: str
    depth: int = Field(ge=1, le=5)


class RuleDefinition(DSLModel):
    id: str
    conditions: list[RuleCondition] = Field(default_factory=list)
    traversal: GraphTraversal | None = None
    action: str | None = None
    effects: dict[str, float] = Field(default_factory=dict)
    max_applications: int = Field(default=1, ge=1, le=100)


class ScenarioDefinition(DSLModel):
    id: str
    systems: list[str] = Field(min_length=1)
    actions: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)


class ParameterDefinition(DSLModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    value: float | None = Field(default=None, allow_inf_nan=False)
    unit: str = Field(min_length=1)
    provenance: Evidence


class ProbabilitySpec(DSLModel):
    base: float = Field(ge=0, allow_inf_nan=False)
    mode: Literal["probability", "hazard"] = "probability"
    time_unit: Literal["event", "hour", "day", "week", "year"]
    parameter: str | None = None
    source_state: str | None = None
    mixing_parameter: str | None = None
    opportunity: str | None = None
    modifiers: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_probability(self):
        if self.mode == "probability" and self.base > 1:
            raise ValueError("Probability must be between 0 and 1")
        return self


class TransitionDefinition(DSLModel):
    id: str
    from_state: str
    to_state: str
    probability: ProbabilitySpec


class SystemDefinition(DSLModel):
    id: str
    state: str
    transitions: list[TransitionDefinition] = Field(min_length=1)


class ActionDefinition(DSLModel):
    id: str
    system: str | None = None
    probability: ProbabilitySpec
    duration_minutes: float = Field(ge=0, le=1440, allow_inf_nan=False)
    priority: int = Field(ge=0, le=10)
    meaningful: bool = True
    interruptible: bool = True
    protected: bool = False
    reschedulable: bool = True
    compatible_with: list[str] = Field(default_factory=list)
    priority_modifiers: dict[str, int] = Field(default_factory=dict)
    requires_role: str | None = None
    target_requires_role: str | None = None
    loser_outcome: Literal["paused", "deferred", "cancelled", "relationship_cost", "continues"]
    effects: dict[str, float] = Field(default_factory=dict)


class ChainBranch(DSLModel):
    action: str
    probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    delay_ticks: int = Field(default=0, ge=0)
    formula: str | None = None
    conditions: dict[str, str] = Field(default_factory=dict)
    cross_agent: bool = False
    terminates: bool = False


class ChainDefinition(DSLModel):
    id: str
    trigger: str
    branches: list[ChainBranch] = Field(min_length=1)
    max_length: int | None = Field(default=None, ge=1, le=100)
    continue_probability: float = Field(default=1, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_branches(self):
        totals = {}
        for branch in self.branches:
            key = tuple(sorted(branch.conditions.items()))
            totals[key] = totals.get(key, 0) + branch.probability
        if any(abs(total - 1) > 1e-9 for total in totals.values()):
            raise ValueError("Chain branch probabilities must sum to 1 for each conditioning")
        return self


class RoleDefinition(DSLModel):
    id: str
    actions: list[str] = Field(default_factory=list)


class DefaultDefinition(DSLModel):
    id: str
    distribution: Distribution
    depends_on: list[str] = Field(default_factory=list)
    when: dict[str, str] = Field(default_factory=dict)
    place: str | None = None
    age_min: int | None = None
    age_max: int | None = None


class BehaviourBundle(DSLModel):
    id: str
    layer: int = Field(ge=0)
    inherits: list[str] = Field(default_factory=list)
    values: dict[str, float] = Field(default_factory=dict)
    issue_values: dict[str, dict[str, float]] = Field(default_factory=dict)
    blends: dict[str, dict[str, float]] = Field(default_factory=dict)
    provenance: Evidence


class NetworkDefinition(DSLModel):
    id: str
    max_depth: int = Field(ge=1, le=5)
    friend_weight: float = Field(default=0.6, ge=0, le=1)
    stranger_weight: float = Field(default=0.15, ge=0, le=1)
    enemy_weight: float = Field(default=-0.4, ge=-1, le=0)


class MediaRule(DSLModel):
    id: str
    interest_weight: float = Field(ge=0, le=1)
    social_weight: float = Field(ge=0, le=1)
    recency_weight: float = Field(ge=0, le=1)
    trust_weight: float = Field(ge=0, le=1)


class LeaderActionDefinition(DSLModel):
    id: str
    parameter_effects: dict[str, float]
    evidence: Evidence


class EventDefinition(DSLModel):
    id: str
    metric: str
    threshold: float = Field(allow_inf_nan=False)
    direction: Literal["above", "below", "increase", "decrease"]


class CouplingDefinition(DSLModel):
    id: str
    source_system: str
    target_system: str
    source_metric: str
    target_parameter: str
    scale: float = Field(allow_inf_nan=False)


class TickConfig(DSLModel):
    tick_hours: float = Field(default=24, gt=0, le=168, allow_inf_nan=False)
    total_ticks: int = Field(default=30, ge=1, le=175_200)
    snapshot_every_hours: int = Field(default=24, ge=1, le=8760)
    story_every_days: int = Field(default=7, ge=1, le=365)
    update_order: Literal["double_buffered", "seeded_random"] = "double_buffered"


class OutputSpec(DSLModel):
    snapshots: bool = True
    metrics: bool = True
    stories: bool = True
    agent_logs: Literal["none", "tiered", "all"] = "tiered"
    backtest_comparisons: bool = False
    ensemble_updates: bool = True


class PlaceHierarchy(DSLModel):
    city: str | None = None
    country: str = Field(min_length=1)
    subregion: str | None = None
    region: str = Field(min_length=1)


class PopulationReference(DSLModel):
    id: str
    version: str
    size: int = Field(ge=1, le=10_000_000)
    places: list[str] = Field(min_length=1)
    place_populations: dict[str, int] = Field(default_factory=dict)
    place_coordinates: dict[str, tuple[float, float]] = Field(default_factory=dict)
    place_hierarchy: dict[str, PlaceHierarchy] = Field(default_factory=dict)
    initial_state_overrides: dict[str, dict[str, dict[str, int]]] = Field(default_factory=dict)


class AggregateBenchmark(DSLModel):
    action_id: str
    population: int = Field(gt=0)
    observed_annual_count: float = Field(gt=0, allow_inf_nan=False)
    tolerance_factor: float = Field(default=10, ge=1, allow_inf_nan=False)


class DSLConfig(DSLModel):
    schema_version: Literal["1"] = "1"
    id: str
    version: str
    states: list[StateDefinition] = Field(min_length=1)
    attributes: list[AttributeDefinition] = Field(default_factory=list)
    feature_registry: FeatureRegistry | None = None
    choice_evidence: list[ChoiceEvidence] = Field(default_factory=list)
    place_states: list[str] = Field(default_factory=list)
    parameters: list[ParameterDefinition] = Field(default_factory=list)
    systems: list[SystemDefinition] = Field(min_length=1)
    scenarios: list[ScenarioDefinition] = Field(default_factory=list)
    rules: list[RuleDefinition] = Field(default_factory=list)
    actions: list[ActionDefinition] = Field(default_factory=list)
    chains: list[ChainDefinition] = Field(default_factory=list)
    roles: list[RoleDefinition] = Field(default_factory=list)
    default_states: list[DefaultDefinition] = Field(default_factory=list)
    behaviour_bundles: list[BehaviourBundle] = Field(default_factory=list)
    networks: list[NetworkDefinition] = Field(default_factory=list)
    media_rules: list[MediaRule] = Field(default_factory=list)
    leader_actions: list[LeaderActionDefinition] = Field(default_factory=list)
    events: list[EventDefinition] = Field(default_factory=list)
    couplings: list[CouplingDefinition] = Field(default_factory=list)
    tick: TickConfig
    outputs: OutputSpec
    population: PopulationReference
    benchmarks: list[AggregateBenchmark] = Field(default_factory=list)


class ValidationIssue(DSLModel):
    path: str
    message: str


class ImpliedAggregate(DSLModel):
    action_id: str
    implied_annual_count: float
    observed_annual_count: float
    ratio: float


class DSLValidationResult(DSLModel):
    valid: bool
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]
    implied_aggregates: list[ImpliedAggregate]

    @property
    def error_messages(self) -> list[str]:
        return [issue.message for issue in self.errors]


class SliderSpec(DSLModel):
    parameter: str
    value: float
    unit: str
    evidence_status: EvidenceStatus


class BundleResolution(DSLModel):
    values: dict[str, float]
    provenance: dict[str, Evidence]
