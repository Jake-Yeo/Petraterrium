from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BuilderModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


ProposalOrigin = Literal["user_explicit", "model_proposal", "structural", "manual_edit"]


class ProposalAudit(BuilderModel):
    provider: str
    model: str
    prompt_version: str
    generated_at: datetime | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    message: str


class ChainNodeDraft(BuilderModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    label: str = Field(min_length=1)
    terminal: bool = False
    origin: ProposalOrigin
    source_excerpt: str | None = None


class ChainTransitionDraft(BuilderModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    from_node: str
    to_node: str
    probability: float | None = Field(default=None, allow_inf_nan=False)
    condition: str | None = None
    origin: ProposalOrigin
    source_excerpt: str | None = None


class ChainDraft(BuilderModel):
    schema_version: Literal["1"] = "1"
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1)
    source_text: str = Field(min_length=1)
    entry_node: str | None = None
    nodes: list[ChainNodeDraft]
    transitions: list[ChainTransitionDraft]
    revision: int = Field(default=0, ge=0)
    proposal_audit: ProposalAudit | None = None


class ChainProposalRequest(BuilderModel):
    text: str = Field(min_length=1, max_length=12_000)
    chain_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]*$")
    name: str | None = Field(default=None, min_length=1, max_length=160)
    use_llm: bool = True


ValidationSeverity = Literal["error", "warning"]


class ChainValidationIssue(BuilderModel):
    code: str
    severity: ValidationSeverity
    path: str
    message: str


class OutgoingProbabilityTotal(BuilderModel):
    node_id: str
    known_total: float = Field(allow_inf_nan=False)
    unknown_count: int = Field(ge=0)
    complete: bool
    sums_to_one: bool


class ChainValidationResult(BuilderModel):
    valid: bool
    can_confirm: bool
    issues: list[ChainValidationIssue]
    outgoing_totals: list[OutgoingProbabilityTotal]
    terminal_states: list[str]
    dead_ends: list[str]
    non_terminating_loops: list[list[str]]
    missing_conditions: list[str]
    missing_probabilities: list[str]
    unreachable_nodes: list[str]


class ChainProposalResult(BuilderModel):
    draft: ChainDraft
    validation: ChainValidationResult
    audit: ProposalAudit


class ConfirmChainRequest(BuilderModel):
    draft: ChainDraft
    user_confirmed: Literal[True]


class ConfirmedChainGraph(BuilderModel):
    schema_version: Literal["1"] = "1"
    id: str
    name: str
    source_text: str
    entry_node: str
    nodes: list[ChainNodeDraft]
    transitions: list[ChainTransitionDraft]
    revision: int
    proposal_audit: ProposalAudit | None = None

    @model_validator(mode="after")
    def contains_only_resolved_transitions(self):
        if any(item.probability is None for item in self.transitions):
            raise ValueError("Confirmed transitions require probabilities")
        if any(
            item.probability is not None and not 0 <= item.probability <= 1
            for item in self.transitions
        ):
            raise ValueError("Confirmed transition probabilities must be between 0 and 1")
        if any(not (item.condition or "").strip() for item in self.transitions):
            raise ValueError("Confirmed transitions require conditions")
        return self


class ConfirmationResult(BuilderModel):
    chain: ConfirmedChainGraph
    validation: ChainValidationResult
    persisted: bool
    persistence_id: str | None = None


class LLMNodeProposal(BuilderModel):
    label: str = Field(min_length=1)
    terminal: bool = False
    source_excerpt: str = Field(min_length=1)


class LLMTransitionProposal(BuilderModel):
    from_label: str = Field(min_length=1)
    to_label: str = Field(min_length=1)
    probability: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    condition: str | None = None
    source_excerpt: str = Field(min_length=1)


class LLMGraphProposal(BuilderModel):
    name: str = Field(min_length=1)
    entry_label: str | None = None
    nodes: list[LLMNodeProposal]
    transitions: list[LLMTransitionProposal]
