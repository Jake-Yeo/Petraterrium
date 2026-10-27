from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from threading import RLock
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..atlas.evidence_receipts import AtlasEvidenceReceiptRegistry

EvidenceStatus = Literal["measured_joint", "fitted_model", "approved_estimate"]
Participant = Literal["actor", "target"]
NumericOperation = Literal["set", "add"]
ContextValue = float | str | bool
MAX_INTERACTION_TREE_DEPTH = 5


def _supported_context_input(value: str) -> bool:
    exact = {
        "actor.id",
        "target.id",
        "actor.place_id",
        "target.place_id",
        "relationship.kind",
        "place.id",
        "place.kind",
        "time.weekday",
        "time.hour",
        "channel",
        "co_located",
    }
    prefixes = (
        "actor.trait.",
        "target.trait.",
        "actor.state.",
        "target.state.",
        "actor.routine.",
        "target.routine.",
        "relationship.state.",
        "place.state.",
        "context.",
    )
    return value in exact or any(
        value.startswith(prefix) and len(value) > len(prefix) for prefix in prefixes
    )


class InteractionTreeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class InteractionTransitionEvidence(InteractionTreeModel):
    source: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: EvidenceStatus
    uncertainty: float = Field(ge=0, allow_inf_nan=False)
    source_date: str | None = None
    evidence_id: str | None = None


class InteractionTreeCondition(InteractionTreeModel):
    input: str = Field(min_length=1)
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte"]
    value: ContextValue

    @model_validator(mode="after")
    def valid_input(self):
        if not _supported_context_input(self.input):
            raise ValueError(f"Unsupported interaction condition input {self.input}")
        return self


class AgentStateEffect(InteractionTreeModel):
    kind: Literal["agent_state"] = "agent_state"
    participant: Participant
    field: str = Field(min_length=1)
    operation: NumericOperation
    value: float = Field(allow_inf_nan=False)
    minimum: float | None = Field(default=None, allow_inf_nan=False)
    maximum: float | None = Field(default=None, allow_inf_nan=False)
    scale_by: tuple[str, ...] = ()

    @model_validator(mode="after")
    def ordered_bounds(self):
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("Agent state effect bounds must be ordered")
        if len(set(self.scale_by)) != len(self.scale_by) or any(
            not _supported_context_input(value) for value in self.scale_by
        ):
            raise ValueError("Agent state effect scales must name unique runtime inputs")
        return self


class AgentRoutineEffect(InteractionTreeModel):
    kind: Literal["agent_routine"] = "agent_routine"
    participant: Participant
    operation: Literal["add", "remove"]
    routine_id: str = Field(min_length=1)


class RelationshipStateEffect(InteractionTreeModel):
    kind: Literal["relationship_state"] = "relationship_state"
    field: str = Field(min_length=1)
    operation: NumericOperation
    value: float = Field(allow_inf_nan=False)
    minimum: float | None = Field(default=None, allow_inf_nan=False)
    maximum: float | None = Field(default=None, allow_inf_nan=False)
    scale_by: tuple[str, ...] = ()

    @model_validator(mode="after")
    def ordered_bounds(self):
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("Relationship state effect bounds must be ordered")
        if len(set(self.scale_by)) != len(self.scale_by) or any(
            not _supported_context_input(value) for value in self.scale_by
        ):
            raise ValueError("Relationship state effect scales must name unique runtime inputs")
        return self


class RelationshipKindEffect(InteractionTreeModel):
    kind: Literal["relationship_kind"] = "relationship_kind"
    relationship_type: str = Field(min_length=1)


InteractionTreeEffect = Annotated[
    AgentStateEffect | AgentRoutineEffect | RelationshipStateEffect | RelationshipKindEffect,
    Field(discriminator="kind"),
]


class InteractionTreeNode(InteractionTreeModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    terminal: bool
    target_tree_id: str | None = Field(default=None, min_length=1)


class InteractionProbabilityFactorCase(InteractionTreeModel):
    id: str = Field(min_length=1)
    conditions: tuple[InteractionTreeCondition, ...] = Field(min_length=1)
    multiplier: float = Field(ge=0, allow_inf_nan=False)


class InteractionProbabilityFactor(InteractionTreeModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    cases: tuple[InteractionProbabilityFactorCase, ...] = Field(min_length=1)
    evidence: InteractionTransitionEvidence

    @model_validator(mode="after")
    def unique_cases(self):
        case_ids = [case.id for case in self.cases]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("Interaction probability factor case IDs must be unique")
        return self


class InteractionTreeTransition(InteractionTreeModel):
    id: str = Field(min_length=1)
    from_node: str = Field(min_length=1)
    to_node: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    probability_factors: tuple[InteractionProbabilityFactor, ...] = ()
    evidence: InteractionTransitionEvidence
    conditions: tuple[InteractionTreeCondition, ...] = ()
    effects: tuple[InteractionTreeEffect, ...] = ()

    @model_validator(mode="after")
    def unique_probability_factors(self):
        factor_ids = [factor.id for factor in self.probability_factors]
        if len(set(factor_ids)) != len(factor_ids):
            raise ValueError("Interaction transition probability factor IDs must be unique")
        return self


class InteractionTreeDefinition(InteractionTreeModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    entry_node: str = Field(min_length=1)
    allowed_channels: tuple[str, ...] = Field(min_length=1)
    co_location_policy: Literal["required", "remote_allowed"]
    nodes: tuple[InteractionTreeNode, ...] = Field(min_length=1)
    transitions: tuple[InteractionTreeTransition, ...]

    @model_validator(mode="after")
    def valid_graph(self):
        node_ids = [node.id for node in self.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("Interaction tree node IDs must be unique")
        if self.entry_node not in node_ids:
            raise ValueError("Interaction tree entry node is not declared")
        transition_ids = [transition.id for transition in self.transitions]
        if len(set(transition_ids)) != len(transition_ids):
            raise ValueError("Interaction tree transition IDs must be unique")
        terminal = {node.id for node in self.nodes if node.terminal}
        outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
        for transition in self.transitions:
            if transition.from_node not in outgoing or transition.to_node not in outgoing:
                raise ValueError("Interaction tree transition references an unknown node")
            if transition.from_node in terminal:
                raise ValueError("Terminal interaction tree nodes cannot have outgoing transitions")
            outgoing[transition.from_node].append(transition.to_node)
        dead_ends = sorted(
            node.id for node in self.nodes if not node.terminal and not outgoing[node.id]
        )
        if dead_ends:
            raise ValueError(
                f"Non-terminal interaction tree nodes have no transitions: {', '.join(dead_ends)}"
            )
        self._require_acyclic(outgoing)
        reachable = self._reachable(outgoing)
        unreachable = sorted(set(node_ids) - reachable)
        if unreachable:
            raise ValueError(f"Unreachable interaction tree nodes: {', '.join(unreachable)}")
        if len(set(self.allowed_channels)) != len(self.allowed_channels):
            raise ValueError("Interaction tree allowed channels must be unique")
        return self

    def _require_acyclic(self, outgoing: Mapping[str, Sequence[str]]) -> None:
        active: list[str] = []
        complete: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in active:
                cycle = [*active[active.index(node_id) :], node_id]
                raise ValueError(f"Interaction tree cycle: {' -> '.join(cycle)}")
            if node_id in complete:
                return
            active.append(node_id)
            for target in outgoing[node_id]:
                visit(target)
            active.pop()
            complete.add(node_id)

        visit(self.entry_node)

    def _reachable(self, outgoing: Mapping[str, Sequence[str]]) -> set[str]:
        found: set[str] = set()
        pending = [self.entry_node]
        while pending:
            node_id = pending.pop()
            if node_id in found:
                continue
            found.add(node_id)
            pending.extend(outgoing[node_id])
        return found


class InteractionParticipant(InteractionTreeModel):
    agent_id: str = Field(min_length=1)
    place_id: str = Field(min_length=1)
    traits: dict[str, ContextValue] = Field(default_factory=dict)
    states: dict[str, float] = Field(default_factory=dict)
    routines: tuple[str, ...] = ()

    @model_validator(mode="after")
    def unique_routines(self):
        if len(set(self.routines)) != len(self.routines):
            raise ValueError("Interaction participant routines must be unique")
        return self


class DirectedRelationship(InteractionTreeModel):
    source_agent_id: str = Field(min_length=1)
    target_agent_id: str = Field(min_length=1)
    eligible: bool
    relationship_type: str = Field(min_length=1)
    states: dict[str, float] = Field(default_factory=dict)


class InteractionPlaceContext(InteractionTreeModel):
    id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    states: dict[str, float] = Field(default_factory=dict)


class InteractionTimeContext(InteractionTreeModel):
    weekday: int = Field(ge=0, le=6)
    hour: float = Field(ge=0, lt=24, allow_inf_nan=False)


class InteractionTreeContext(InteractionTreeModel):
    actor: InteractionParticipant
    target: InteractionParticipant
    relationship: DirectedRelationship
    place: InteractionPlaceContext
    time: InteractionTimeContext
    channel: str = Field(min_length=1)
    attributes: dict[str, ContextValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_participants(self):
        if self.actor.agent_id == self.target.agent_id:
            raise ValueError("Interaction tree actor and target must be different agents")
        if (
            self.relationship.source_agent_id != self.actor.agent_id
            or self.relationship.target_agent_id != self.target.agent_id
            or not self.relationship.eligible
        ):
            raise ValueError(
                "Interaction tree requires an eligible relationship directed from actor to target"
            )
        return self


class InteractionTreeRequest(InteractionTreeModel):
    seed: int = Field(ge=0)
    tick: int = Field(ge=0)
    tree: InteractionTreeDefinition
    trees: dict[str, InteractionTreeDefinition] = Field(default_factory=dict)
    context: InteractionTreeContext

    @model_validator(mode="after")
    def valid_eligibility(self):
        if self.context.channel not in self.tree.allowed_channels:
            raise ValueError("Interaction channel is not allowed by the tree")
        co_located = self.context.actor.place_id == self.context.target.place_id
        if self.context.channel == "in_person" and not co_located:
            raise ValueError("In-person interaction requires specific-place co-location")
        if self.tree.co_location_policy == "required" and not co_located:
            raise ValueError("Interaction tree requires specific-place co-location")
        if co_located and self.context.place.id != self.context.actor.place_id:
            raise ValueError("Interaction place must match the co-located participant place")
        return self

    def rust_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class EvaluatedInteractionProbabilityFactor(InteractionTreeModel):
    factor_id: str
    label: str
    case_id: str
    multiplier: float = Field(ge=0, allow_inf_nan=False)
    inputs: dict[str, ContextValue]
    evidence: InteractionTransitionEvidence


class EvaluatedInteractionTransition(InteractionTreeModel):
    transition_id: str
    outcome: str
    base_probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    unnormalized_weight: float = Field(ge=0, allow_inf_nan=False)
    probability: float = Field(ge=0, le=1, allow_inf_nan=False)
    factors: tuple[EvaluatedInteractionProbabilityFactor, ...] = ()
    evidence: InteractionTransitionEvidence


class InteractionPathStep(InteractionTreeModel):
    tree_id: str | None = None
    node_id: str
    transition_id: str
    outcome: str
    probability: float = Field(ge=0, le=1)
    draw: float = Field(ge=0, lt=1)
    evidence: InteractionTransitionEvidence
    factors: tuple[EvaluatedInteractionProbabilityFactor, ...] = ()
    outgoing_probabilities: tuple[EvaluatedInteractionTransition, ...] = ()


class InteractionTreeReceipt(InteractionTreeModel):
    actor_id: str
    target_id: str
    relationship_direction: str
    place_id: str
    channel: str
    weekday: int = Field(ge=0, le=6)
    hour: float = Field(ge=0, lt=24)


class InteractionTreeChange(InteractionTreeModel):
    recipient: Literal["actor", "target", "relationship"]
    field: str
    before: ContextValue
    after: ContextValue


class InteractionTreeResult(InteractionTreeModel):
    tree_id: str
    tree_version: str
    seed: int
    tick: int
    outcome_node: str
    outcome: str
    path: tuple[InteractionPathStep, ...] = Field(min_length=1)
    receipt: InteractionTreeReceipt
    actor_before: InteractionParticipant
    actor_after: InteractionParticipant
    target_before: InteractionParticipant
    target_after: InteractionParticipant
    relationship_before: DirectedRelationship
    relationship_after: DirectedRelationship
    changes: tuple[InteractionTreeChange, ...]


class InteractionTreeSummary(InteractionTreeModel):
    id: str
    name: str
    version: str
    node_count: int
    transition_count: int
    co_location_policy: Literal["required", "remote_allowed"]
    allowed_channels: tuple[str, ...]


class InteractionTreeRegistry:
    def __init__(
        self,
        definitions: Sequence[InteractionTreeDefinition] = (),
        persist: Callable[[InteractionTreeDefinition], InteractionTreeDefinition] | None = None,
        evidence_receipts: AtlasEvidenceReceiptRegistry | None = None,
    ):
        collected: dict[str, InteractionTreeDefinition] = {}
        for definition in definitions:
            if definition.id in collected:
                raise ValueError(f"Duplicate interaction tree ID {definition.id}")
            collected[definition.id] = definition
        _validate_registry(collected)
        self._definitions = collected
        self._lock = RLock()
        self._persist = persist
        self._evidence_receipts = evidence_receipts

    def save(self, definition: InteractionTreeDefinition) -> InteractionTreeDefinition:
        self._validate_evidence(definition)
        with self._lock:
            current = self._definitions.get(definition.id)
            if current is not None and current.version == definition.version:
                raise ValueError(
                    f"Interaction tree {definition.id} version {definition.version} already exists"
                )
            updated = {**self._definitions, definition.id: definition}
            _validate_registry(updated)
            if self._persist is not None:
                self._persist(definition)
            self._definitions = updated
        return definition

    def get(self, tree_id: str) -> InteractionTreeDefinition:
        with self._lock:
            try:
                return self._definitions[tree_id]
            except KeyError as error:
                raise KeyError(f"Unknown interaction tree {tree_id}") from error

    def list(self) -> tuple[InteractionTreeSummary, ...]:
        with self._lock:
            values = tuple(self._definitions.values())
        return tuple(
            InteractionTreeSummary(
                id=definition.id,
                name=definition.name,
                version=definition.version,
                node_count=len(definition.nodes),
                transition_count=len(definition.transitions),
                co_location_policy=definition.co_location_policy,
                allowed_channels=definition.allowed_channels,
            )
            for definition in sorted(values, key=lambda item: item.name.casefold())
        )

    def execution_trees(self, tree_id: str) -> dict[str, InteractionTreeDefinition]:
        with self._lock:
            root = self.get(tree_id)
            definitions = dict(self._definitions)
        self._validate_evidence(root)
        reachable: dict[str, InteractionTreeDefinition] = {}
        pending = [
            node.target_tree_id for node in root.nodes if node.target_tree_id is not None
        ]
        while pending:
            referenced_id = pending.pop()
            if referenced_id in reachable:
                continue
            referenced = definitions[referenced_id]
            self._validate_evidence(referenced)
            reachable[referenced_id] = referenced
            pending.extend(
                node.target_tree_id
                for node in referenced.nodes
                if node.target_tree_id is not None
            )
        return reachable

    def _validate_evidence(self, definition: InteractionTreeDefinition) -> None:
        if self._evidence_receipts is None:
            return
        for transition in definition.transitions:
            expected = {
                definition.id,
                transition.id,
                transition.outcome,
            }
            if transition.evidence.status in {"measured_joint", "fitted_model"}:
                issue = self._evidence_receipts.interaction_issue(
                    transition.evidence.evidence_id,
                    transition.evidence.source,
                    transition.evidence.version,
                    transition.evidence.source_date,
                    expected,
                )
                if issue is not None:
                    raise ValueError(
                        f"Interaction tree {definition.id} transition {transition.id}: {issue}"
                    )
            for factor in transition.probability_factors:
                if factor.evidence.status not in {"measured_joint", "fitted_model"}:
                    continue
                issue = self._evidence_receipts.interaction_issue(
                    factor.evidence.evidence_id,
                    factor.evidence.source,
                    factor.evidence.version,
                    factor.evidence.source_date,
                    {*expected, factor.id},
                )
                if issue is not None:
                    raise ValueError(
                        f"Interaction tree {definition.id} factor {factor.id}: {issue}"
                    )


def _validate_registry(definitions: Mapping[str, InteractionTreeDefinition]) -> None:
    for key, definition in definitions.items():
        if key != definition.id:
            raise ValueError(
                f"Interaction tree registry key {key} contains tree {definition.id}"
            )
        for node in definition.nodes:
            target = node.target_tree_id
            if target is not None and target not in definitions:
                raise ValueError(
                    f"Interaction tree {definition.id} node {node.id} "
                    f"references missing tree {target}"
                )

    def visit(tree_id: str, active: list[str]) -> None:
        if tree_id in active:
            cycle = [*active[active.index(tree_id) :], tree_id]
            raise ValueError(f"Interaction tree reference cycle: {' -> '.join(cycle)}")
        if len(active) + 1 > MAX_INTERACTION_TREE_DEPTH:
            chain = [*active, tree_id]
            raise ValueError(
                "Interaction tree reference depth exceeds "
                f"{MAX_INTERACTION_TREE_DEPTH}: {' -> '.join(chain)}"
            )
        active.append(tree_id)
        definition = definitions[tree_id]
        for node in definition.nodes:
            if node.target_tree_id is not None:
                visit(node.target_tree_id, active)
        active.pop()

    for tree_id in definitions:
        visit(tree_id, [])


InteractionTreeExecutor = Callable[[dict[str, Any]], Mapping[str, Any]]


def evaluate_interaction_tree(
    request: InteractionTreeRequest,
    executor: InteractionTreeExecutor,
) -> InteractionTreeResult:
    try:
        response = executor({"operation": "run_interaction_tree", **request.rust_payload()})
    except RuntimeError as error:
        raise ValueError(str(error)) from error
    if response.get("ok") is False:
        error = response.get("error")
        if isinstance(error, Mapping):
            code = str(error.get("code", "INTERACTION_TREE_FAILED"))
            message = str(error.get("message", "Interaction tree evaluation failed"))
            path = str(error.get("path", "tree"))
            raise ValueError(f"{code} at {path}: {message}")
        raise ValueError("Interaction tree evaluation failed")
    payload = response.get("result", response)
    if not isinstance(payload, Mapping):
        raise ValueError("Rust interaction tree result must be an object")
    result = dict(payload)
    result.pop("protocol_version", None)
    result.pop("engine_version", None)
    return InteractionTreeResult.model_validate(result)


def create_interaction_tree_router(
    registry: InteractionTreeRegistry,
    executor: InteractionTreeExecutor,
) -> APIRouter:
    router = APIRouter(prefix="/simulation/interaction-trees", tags=["Interaction trees"])

    @router.get("", response_model=tuple[InteractionTreeSummary, ...])
    def list_trees() -> tuple[InteractionTreeSummary, ...]:
        return registry.list()

    @router.post("", response_model=InteractionTreeDefinition, status_code=201)
    def save_tree(definition: InteractionTreeDefinition) -> InteractionTreeDefinition:
        try:
            return registry.save(definition)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/{tree_id}", response_model=InteractionTreeDefinition)
    def get_tree(tree_id: str) -> InteractionTreeDefinition:
        try:
            return registry.get(tree_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.post("/{tree_id}/evaluate", response_model=InteractionTreeResult)
    def evaluate_tree(tree_id: str, request: InteractionTreeRequest) -> InteractionTreeResult:
        if request.tree.id != tree_id:
            raise HTTPException(status_code=422, detail="Path tree ID does not match request tree")
        try:
            definition = registry.get(tree_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if definition != request.tree:
            raise HTTPException(
                status_code=409,
                detail="Request tree is not the registered version",
            )
        execution_request = request.model_copy(
            update={"trees": registry.execution_trees(tree_id)}
        )
        try:
            return evaluate_interaction_tree(execution_request, executor)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return router
