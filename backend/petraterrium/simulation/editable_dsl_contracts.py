from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EditableDslModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        serialize_by_alias=True,
        str_strip_whitespace=True,
    )


class EditableDslEvidence(EditableDslModel):
    status: Literal["measured", "estimated", "fitted", "default"]
    source: str
    source_version: str = Field(alias="sourceVersion")
    source_date: str | None = Field(default=None, alias="sourceDate")
    uncertainty: float
    reasoning: str | None = None
    source_ids: tuple[str, ...] = ()


class EditableDslDuration(EditableDslModel):
    min_hours: float
    median_hours: float
    max_hours: float
    shape: Literal["uniform", "triangular", "lognormal", "weibull", "empirical"]
    shape_parameters: dict[str, float] = Field(default_factory=dict)
    evidence: EditableDslEvidence


class EditableDslCoefficient(EditableDslModel):
    id: str
    name: str
    value: float
    evidence: EditableDslEvidence


class EditableDslStateThreshold(EditableDslModel):
    id: str
    label: str
    value: float


class EditableDslState(EditableDslModel):
    id: str
    name: str
    min: float
    max: float
    initial: float
    decay_per_hour: float
    recovery_per_hour: float
    thresholds: tuple[EditableDslStateThreshold, ...] = ()


class EditableDslAction(EditableDslModel):
    id: str
    name: str
    description: str
    category: str = Field(min_length=1)
    mode: Literal["primary", "passive"]
    priority: int = Field(ge=-1000, le=1000)
    aggregate_statistic_id: str = Field(min_length=1)
    interruptibility: Literal["interruptible", "protected", "uninterruptible"]
    interruption_outcome: Literal["defer", "cancel"]
    emergency_interruptions: tuple[str, ...] = ()
    duration: EditableDslDuration
    evidence: EditableDslEvidence | None = None
    formula: str
    coefficients: tuple[EditableDslCoefficient, ...] = ()
    place_requirements: tuple[str, ...] = ()
    time_requirements: tuple[str, ...] = ()


class EditableDslTreeNode(EditableDslModel):
    id: str
    label: str
    kind: Literal["entry", "decision", "action", "terminal", "module"]
    action_id: str | None = None
    target_tree_id: str | None = None


class EditableDslTreeEdge(EditableDslModel):
    id: str
    from_node: str
    to_node: str
    probability: float
    formula: str
    condition: str
    place_requirements: tuple[str, ...] = ()
    time_requirements: tuple[str, ...] = ()


class EditableDslTree(EditableDslModel):
    id: str
    name: str
    entry_node: str
    nodes: tuple[EditableDslTreeNode, ...]
    edges: tuple[EditableDslTreeEdge, ...]


class EditableDslDocument(EditableDslModel):
    schema_version: str
    version: str
    tick_hours: float
    actions: tuple[EditableDslAction, ...]
    states: tuple[EditableDslState, ...]
    trees: tuple[EditableDslTree, ...]


class EditableDslIssue(EditableDslModel):
    path: str
    message: str
    severity: Literal["error", "warning"]


class EditableDslValidation(EditableDslModel):
    valid: bool
    issues: tuple[EditableDslIssue, ...]

    @model_validator(mode="after")
    def validity_matches_issues(self):
        expected = not any(item.severity == "error" for item in self.issues)
        if self.valid != expected:
            raise ValueError("Editable DSL validity must match its error issues")
        return self


class EditableDslDiff(EditableDslModel):
    path: str
    before: str
    after: str


class EditableDslRevision(EditableDslModel):
    revision: int = Field(ge=0)
    version: str
    document_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    parent_hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    accepted_at: str | None
    source: Literal["installed_registry", "confirmed_edit"]
    document: EditableDslDocument


class PreviewEditableDslRequest(EditableDslModel):
    expected_active_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    document: EditableDslDocument


class PreviewEditableDslResponse(EditableDslModel):
    expected_active_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    document_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    preview_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    validation: EditableDslValidation
    diff: tuple[EditableDslDiff, ...]


class ConfirmEditableDslRequest(EditableDslModel):
    expected_active_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    preview_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    document: EditableDslDocument
    user_confirmed: Literal[True]
