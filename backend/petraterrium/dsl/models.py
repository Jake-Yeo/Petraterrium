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


class ChainDefinition(DSLModel):
    id: str
    trigger: str
    branches: list[ChainBranch] = Field(min_length=1)
    max_length: int | None = Field(default=None, ge=1, le=100)
    continue_probability: float = Field(default=1, ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def valid_branches(self):
        if abs(sum(branch.probability for branch in self.branches) - 1) > 1e-9:
            raise ValueError("Chain branch probabilities must sum to 1")
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


class PopulationReference(DSLModel):
    id: str
    version: str
    size: int = Field(ge=1, le=10_000_000)
    places: list[str] = Field(min_length=1)
    place_populations: dict[str, int] = Field(default_factory=dict)
    place_coordinates: dict[str, tuple[float, float]] = Field(default_factory=dict)
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
