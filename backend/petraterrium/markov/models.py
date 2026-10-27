from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..dsl import ChoiceEvidence, Evidence

IdentifierPattern = r"^[a-z][a-z0-9_-]*$"
Scalar = str | float | int | bool
InputKind = Literal[
    "agent_trait",
    "place",
    "time",
    "context",
    "persisted_state",
    "place_state",
    "media_state",
]
ValueType = Literal["categorical", "continuous", "boolean", "identifier"]
EvidenceKind = Literal["measured_choice", "measured_joint", "fitted_choice"]
TimeUnit = Literal["event", "hour", "day", "friday", "week", "year"]


class MarkovModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class ModuleInput(MarkovModel):
    id: str = Field(pattern=IdentifierPattern)
    kind: InputKind
    value_type: ValueType
    feature_id: str | None = Field(default=None, pattern=IdentifierPattern)
    required: bool = True

    @model_validator(mode="after")
    def agent_trait_has_feature(self):
        if self.kind == "agent_trait" and self.feature_id is None:
            raise ValueError("Agent trait inputs require a feature id")
        return self


class ModuleOutput(MarkovModel):
    id: str = Field(pattern=IdentifierPattern)
    kind: Literal[
        "location",
        "health",
        "friends",
        "persisted_state",
        "place_state",
        "media_state",
        "event",
    ]
    value_type: ValueType


class ModuleState(MarkovModel):
    id: str = Field(pattern=IdentifierPattern)
    label: str | None = Field(default=None, min_length=1)
    effects: list[str] = Field(default_factory=list)


class ConditionClause(MarkovModel):
    input_id: str = Field(pattern=IdentifierPattern)
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "in"]
    value: Scalar | list[Scalar]


class TransitionCondition(MarkovModel):
    mode: Literal["always", "all", "any"]
    clauses: list[ConditionClause] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_clause_count(self):
        if self.mode == "always" and self.clauses:
            raise ValueError("An always condition cannot contain clauses")
        if self.mode != "always" and not self.clauses:
            raise ValueError("Conditional transitions require at least one clause")
        return self


class ProbabilityQuery(MarkovModel):
    outcome_id: str = Field(pattern=IdentifierPattern)
    conditioning_id: str = Field(min_length=1)
    place_input: str = Field(pattern=IdentifierPattern)
    time_input: str = Field(pattern=IdentifierPattern)
    predictor_inputs: list[str] = Field(default_factory=list)
    allowed_evidence: list[EvidenceKind] = Field(
        default_factory=lambda: ["measured_choice", "measured_joint", "fitted_choice"],
        min_length=1,
    )

    @model_validator(mode="after")
    def unique_predictors_and_evidence(self):
        if len(set(self.predictor_inputs)) != len(self.predictor_inputs):
            raise ValueError("Probability predictor inputs must be unique")
        if len(set(self.allowed_evidence)) != len(self.allowed_evidence):
            raise ValueError("Allowed evidence kinds must be unique")
        return self


class ModuleTransition(MarkovModel):
    id: str = Field(pattern=IdentifierPattern)
    from_state: str = Field(pattern=IdentifierPattern)
    to_state: str = Field(pattern=IdentifierPattern)
    condition: TransitionCondition | None = None
    probability: ProbabilityQuery


class MarkovModule(MarkovModel):
    id: str = Field(pattern=IdentifierPattern)
    version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    entry_state: str = Field(pattern=IdentifierPattern)
    exit_states: list[str] = Field(min_length=1)
    inputs: list[ModuleInput] = Field(default_factory=list)
    outputs: list[ModuleOutput] = Field(default_factory=list)
    states: list[ModuleState] = Field(min_length=1)
    transitions: list[ModuleTransition] = Field(default_factory=list)


class InputBinding(MarkovModel):
    target_input: str = Field(pattern=IdentifierPattern)
    source_kind: Literal["input", "output", "external"]
    source_id: str = Field(pattern=IdentifierPattern)


class ModuleLink(MarkovModel):
    from_module: str = Field(pattern=IdentifierPattern)
    exit_state: str = Field(pattern=IdentifierPattern)
    to_module: str = Field(pattern=IdentifierPattern)
    bindings: list[InputBinding] = Field(default_factory=list)


class ProgramExit(MarkovModel):
    module_id: str = Field(pattern=IdentifierPattern)
    state_id: str = Field(pattern=IdentifierPattern)


class MarkovProgram(MarkovModel):
    id: str = Field(pattern=IdentifierPattern)
    version: str = Field(min_length=1)
    entry_module: str = Field(pattern=IdentifierPattern)
    modules: list[MarkovModule] = Field(min_length=1)
    links: list[ModuleLink] = Field(default_factory=list)
    terminal_exits: list[ProgramExit] = Field(min_length=1)
    external_inputs: list[ModuleInput] = Field(default_factory=list)


class TransitionEvidence(MarkovModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
    kind: Literal["measured_joint", "fitted_choice"]
    outcome_id: str = Field(pattern=IdentifierPattern)
    conditioning_id: str = Field(min_length=1)
    place: str = Field(min_length=1)
    time_unit: TimeUnit
    predictor_values: dict[str, Scalar] = Field(default_factory=dict)
    condition_values: dict[str, Scalar] = Field(default_factory=dict)
    probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    ci_low: float = Field(ge=0, le=1, allow_inf_nan=False)
    ci_high: float = Field(ge=0, le=1, allow_inf_nan=False)
    sample_size: int = Field(gt=0)
    held_out_sample_size: int | None = Field(default=None, gt=0)
    population: str = Field(min_length=1)
    provenance: Evidence

    @model_validator(mode="after")
    def qualifying_evidence(self):
        if self.ci_low > self.probability or self.probability > self.ci_high:
            raise ValueError("Evidence probability must be inside its confidence interval")
        if self.provenance.status != "present":
            raise ValueError("Transition evidence must be measured or fitted from present data")
        if self.provenance.source_date is None:
            raise ValueError("Transition evidence requires a source date")
        if self.kind == "fitted_choice" and self.held_out_sample_size is None:
            raise ValueError("Fitted choice evidence requires a held-out sample")
        return self


class EvidenceCatalog(MarkovModel):
    choice: list[ChoiceEvidence] = Field(default_factory=list)
    transition: list[TransitionEvidence] = Field(default_factory=list)


class CompilationContext(MarkovModel):
    place: str = Field(min_length=1)
    time_unit: TimeUnit
    strata: dict[str, Scalar] = Field(default_factory=dict)
    conditions: dict[str, Scalar] = Field(default_factory=dict)


class ValidationIssue(MarkovModel):
    code: str
    path: str
    message: str


class ModuleValidationResult(MarkovModel):
    valid: bool
    issues: list[ValidationIssue]
    dead_ends: list[str]
    unreachable_states: list[str]
    unreachable_exits: list[str]
    non_terminating_loops: list[list[str]]


class ProgramValidationResult(MarkovModel):
    valid: bool
    issues: list[ValidationIssue]
    module_results: dict[str, ModuleValidationResult]
    unreachable_modules: list[str]
    unlinked_exits: list[ProgramExit]
    non_terminating_module_loops: list[list[str]]


class MissingEvidenceRequirement(MarkovModel):
    key: str
    module_id: str
    transition_id: str
    requirement: str


class ResolvedProbability(MarkovModel):
    module_id: str
    transition_id: str
    from_state: str
    to_state: str
    status: Literal["resolved", "unknown"]
    probability: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    ci_low: float = Field(ge=0, le=1, allow_inf_nan=False)
    ci_high: float = Field(ge=0, le=1, allow_inf_nan=False)
    evidence_kind: EvidenceKind | Literal["unknown"]
    evidence_id: str | None = None
    provenance: Evidence


class OutgoingProbabilityTotal(MarkovModel):
    module_id: str
    state_id: str
    total: float = Field(ge=0, allow_inf_nan=False)
    complete: bool
    sums_to_one: bool


class DoubleBufferPlan(MarkovModel):
    read_buffer: Literal["current_state"] = "current_state"
    write_buffer: Literal["next_state"] = "next_state"
    swap_after_batch: Literal[True] = True


class CompiledTransition(MarkovModel):
    id: str
    source_index: int = Field(ge=0)
    target_index: int = Field(ge=0)
    probability_index: int = Field(ge=0)
    condition: TransitionCondition


class CompiledModule(MarkovModel):
    id: str
    version: str
    entry_index: int = Field(ge=0)
    state_indices: dict[str, int]
    exit_indices: list[int]
    transitions: list[CompiledTransition]
    partition_inputs: list[str]
    vectorized_batch: Literal[True] = True
    double_buffer: DoubleBufferPlan = Field(default_factory=DoubleBufferPlan)


class CompilationResult(MarkovModel):
    context: CompilationContext
    executable: bool
    issues: list[ValidationIssue]
    modules: list[CompiledModule]
    probabilities: list[ResolvedProbability]
    outgoing_totals: list[OutgoingProbabilityTotal]
    missing_requirements: list[MissingEvidenceRequirement]
