from typing import Literal

from pydantic import Field, model_validator

from .agent_types import (
    AgentTypeDefinition,
    AgentTypeModel,
    AgentTypeProposalAudit,
    AgentTypeProposalDraft,
    ConfirmedAgentTypeRegistry,
)
from .routines import RoutineEvidence, RoutineRegistryDefinition, RoutineSchedule
from .tree_modules import DecisionTreeRegistryDefinition

EvidenceRequirementBasis = Literal[
    "measured",
    "user_defined",
    "measured_joint",
    "fitted_model",
]
EvidenceRequirementKind = Literal["routine_schedule", "decision_probability"]
EvidenceRequirementStatus = Literal["matched", "missing"]
PlaceScope = Literal["global", "region", "country", "city"]


class RoutineStepIntent(AgentTypeModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=160)
    activity: str = Field(min_length=1)
    decision_tree_module_id: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_-]*$",
    )


class RoutineIntent(AgentTypeModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=160)
    agent_type_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    description: str | None = Field(default=None, min_length=1)
    source_feature_ids: list[str] = Field(default_factory=list)
    steps: list[RoutineStepIntent] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_references(self):
        if len(set(self.source_feature_ids)) != len(self.source_feature_ids):
            raise ValueError("Routine source feature ids must be unique")
        step_ids = [step.id for step in self.steps]
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("Routine intent step ids must be unique")
        return self


class RoutineStepProposal(AgentTypeModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=160)
    activity: str = Field(min_length=1)
    decision_tree_module_id: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_-]*$",
    )
    schedule: RoutineSchedule | None = None


class RoutineProposalDraft(AgentTypeModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=160)
    agent_type_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    description: str | None = Field(default=None, min_length=1)
    source_feature_ids: list[str] = Field(default_factory=list)
    evidence: RoutineEvidence
    steps: list[RoutineStepProposal] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_references(self):
        if len(set(self.source_feature_ids)) != len(self.source_feature_ids):
            raise ValueError("Routine source feature ids must be unique")
        step_ids = [step.id for step in self.steps]
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("Routine proposal step ids must be unique")
        return self


class DecisionTreeNodeIntent(AgentTypeModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    label: str = Field(min_length=1)
    kind: Literal["decision", "action", "terminal", "module_reference"]
    description: str = ""
    target_module_id: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_-]*$",
    )

    @model_validator(mode="after")
    def valid_reference(self):
        if self.kind == "module_reference" and self.target_module_id is None:
            raise ValueError("Module reference nodes require a target module")
        if self.kind != "module_reference" and self.target_module_id is not None:
            raise ValueError("Only module reference nodes can target a module")
        return self


class DecisionTreeEdgeIntent(AgentTypeModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    from_node: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    to_node: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    label: str = ""
    condition: str = ""


class DecisionTreeModuleIntent(AgentTypeModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    entry_node: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    nodes: list[DecisionTreeNodeIntent] = Field(min_length=1)
    edges: list[DecisionTreeEdgeIntent] = Field(default_factory=list)


class DecisionTreeIntent(AgentTypeModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    version: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    root_module_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    agent_type_ids: list[str] = Field(default_factory=list)
    place_ids: list[str] = Field(default_factory=list)


class DecisionTreeTopologyIntent(AgentTypeModel):
    version: str = Field(min_length=1)
    trees: list[DecisionTreeIntent] = Field(default_factory=list)
    modules: list[DecisionTreeModuleIntent] = Field(default_factory=list)


class DecisionEdgeInputPlan(AgentTypeModel):
    tree_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    module_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    edge_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    source_feature_ids: list[str] = Field(default_factory=list)
    outcome: str = Field(min_length=1)
    population_scope: str = Field(min_length=1)
    place_scope: PlaceScope
    time_scope: str = Field(min_length=1)
    decision_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_-]*$")
    evidence_edge_id: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_-]*$",
    )

    @model_validator(mode="after")
    def complete_evidence_reference(self):
        if (self.decision_id is None) != (self.evidence_edge_id is None):
            raise ValueError(
                "Decision input plans must provide both decision_id and evidence_edge_id"
            )
        if len(set(self.source_feature_ids)) != len(self.source_feature_ids):
            raise ValueError("Decision input source feature ids must be unique")
        return self


class AgentBehaviorProposalShape(AgentTypeModel):
    types: list[AgentTypeDefinition] = Field(min_length=1)
    routines: list[RoutineIntent] = Field(default_factory=list)
    decision_trees: DecisionTreeTopologyIntent
    decision_inputs: list[DecisionEdgeInputPlan] = Field(default_factory=list)


class BehaviorEvidenceRequirement(AgentTypeModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    kind: EvidenceRequirementKind
    status: EvidenceRequirementStatus
    target_id: str = Field(min_length=1)
    source_feature_ids: list[str] = Field(default_factory=list)
    outcome: str = Field(min_length=1)
    population_scope: str = Field(min_length=1)
    place_scope: PlaceScope
    time_scope: str = Field(min_length=1)
    accepted_bases: list[EvidenceRequirementBasis]
    required_fields: list[str] = Field(min_length=1)
    matched_evidence_ids: list[str] = Field(default_factory=list)
    message: str = Field(min_length=1)


class AgentBehaviorProposalDraft(AgentTypeProposalDraft):
    schema_version: Literal["2"] = "2"
    routine_drafts: list[RoutineProposalDraft] = Field(default_factory=list)
    decision_tree_drafts: DecisionTreeRegistryDefinition
    decision_inputs: list[DecisionEdgeInputPlan] = Field(default_factory=list)
    evidence_requirements: list[BehaviorEvidenceRequirement] = Field(default_factory=list)


class ConfirmAgentBehaviorProposalRequest(AgentTypeModel):
    draft: AgentBehaviorProposalDraft
    user_confirmed: Literal[True]


class ConfirmedAgentBehaviorBundle(AgentTypeModel):
    schema_version: Literal["2"] = "2"
    agent_types: ConfirmedAgentTypeRegistry
    routines: RoutineRegistryDefinition
    decision_trees: DecisionTreeRegistryDefinition
    evidence_requirements: list[BehaviorEvidenceRequirement]
    audit: AgentTypeProposalAudit
    confirmed: Literal[True] = True
    revision: int
