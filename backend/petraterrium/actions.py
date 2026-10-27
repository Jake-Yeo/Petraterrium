from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from .dsl import ActionDefinition, ChainDefinition, ProbabilitySpec


class ActionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentActionContext(ActionModel):
    agent_id: str
    role: str = "citizen"
    target_role: str | None = None
    relationship: str = "stranger"
    traits: dict[str, Any] = Field(default_factory=dict)
    states: dict[str, float] = Field(default_factory=dict)
    opportunities: set[str] = Field(default_factory=set)


class ActionBundle(ActionModel):
    primary: str | None
    secondaries: list[str]
    duration_minutes: float
    logs: list[str]


class ConflictResult(ActionModel):
    winner: str
    loser: str
    loser_outcome: str
    log: str


class ChainResult(ActionModel):
    chain_id: str
    previous_action: str
    next_action: str | None
    log: str


PERIOD_HOURS = {"event": 1, "hour": 1, "day": 24, "week": 168, "year": 8760}


def tick_probability(
    probability: ProbabilitySpec,
    tick_hours: float,
    context: AgentActionContext | None = None,
) -> float:
    if probability.opportunity and (
        context is None or probability.opportunity not in context.opportunities
    ):
        return 0
    exposure = tick_hours / PERIOD_HOURS[probability.time_unit]
    if probability.time_unit == "event":
        exposure = 1
    if probability.mode == "hazard":
        value = -np.expm1(-probability.base * exposure)
    else:
        value = 1 - (1 - probability.base) ** exposure
    if context:
        for feature, multiplier in probability.modifiers.items():
            value *= float(context.states.get(feature, context.traits.get(feature, 1))) * multiplier
    return float(np.clip(value, 0, 1))


def check_eligibility(
    action: ActionDefinition,
    agent: AgentActionContext,
    target: AgentActionContext | None = None,
) -> bool:
    if action.requires_role and agent.role != action.requires_role:
        return False
    if action.target_requires_role and target is not None:
        return target.role == action.target_requires_role
    return True


def eligible_actions(
    actions: list[ActionDefinition],
    agent: AgentActionContext,
    target: AgentActionContext | None = None,
) -> list[ActionDefinition]:
    return [action for action in actions if check_eligibility(action, agent, target)]


def effective_priority(action: ActionDefinition, context: AgentActionContext) -> int:
    return action.priority + action.priority_modifiers.get(context.relationship, 0)


def resolve_conflict(
    current_action: ActionDefinition,
    incoming_action: ActionDefinition,
    agent: AgentActionContext,
) -> ConflictResult:
    current_priority = effective_priority(current_action, agent)
    incoming_priority = effective_priority(incoming_action, agent)
    protected = current_action.protected and agent.relationship not in {"boss", "emergency"}
    incoming_wins = not protected and (
        incoming_priority > current_priority
        or (incoming_priority == current_priority and agent.relationship == "boss")
    )
    if not current_action.interruptible and agent.relationship not in {"boss", "emergency"}:
        incoming_wins = False
    winner = incoming_action if incoming_wins else current_action
    loser = current_action if incoming_wins else incoming_action
    return ConflictResult(
        winner=winner.id,
        loser=loser.id,
        loser_outcome=loser.loser_outcome,
        log=(
            f"{winner.id} won priority {max(current_priority, incoming_priority)}; "
            f"{loser.id} {loser.loser_outcome}"
        ),
    )


def choose_bundle(
    agent: AgentActionContext,
    actions: list[ActionDefinition],
    rng: np.random.Generator,
    tick_hours: float,
) -> ActionBundle:
    candidates = [
        action
        for action in actions
        if check_eligibility(action, agent)
        and rng.random() < tick_probability(action.probability, tick_hours, agent)
        and action.meaningful
        and action.duration_minutes <= tick_hours * 60
    ]
    if not candidates:
        return ActionBundle(primary=None, secondaries=[], duration_minutes=0, logs=["idle"])
    ordered = sorted(candidates, key=lambda action: (-effective_priority(action, agent), action.id))
    primary = ordered[0]
    remaining = max(0, tick_hours * 60 - primary.duration_minutes)
    secondaries = []
    logs = []
    for action in ordered[1:]:
        compatible = action.id in primary.compatible_with or primary.id in action.compatible_with
        if compatible and action.duration_minutes <= remaining:
            secondaries.append(action.id)
            remaining -= action.duration_minutes
        else:
            result = resolve_conflict(primary, action, agent)
            logs.append(result.log)
    return ActionBundle(
        primary=primary.id,
        secondaries=secondaries,
        duration_minutes=primary.duration_minutes
        + sum(
            next(item.duration_minutes for item in ordered if item.id == identity)
            for identity in secondaries
        ),
        logs=logs,
    )


def chain_step(
    chain: ChainDefinition,
    current_action: str,
    rng: np.random.Generator,
) -> str | None:
    if current_action != chain.trigger and current_action not in {
        branch.action for branch in chain.branches
    }:
        return None
    if chain.max_length is None and rng.random() >= chain.continue_probability:
        return None
    labels = [branch.action for branch in chain.branches]
    probabilities = [branch.probability for branch in chain.branches]
    return str(rng.choice(labels, p=probabilities))


def chain_step_with_log(
    chain: ChainDefinition,
    current_action: str,
    rng: np.random.Generator,
) -> ChainResult:
    next_action = chain_step(chain, current_action, rng)
    outcome = next_action or "terminated"
    return ChainResult(
        chain_id=chain.id,
        previous_action=current_action,
        next_action=next_action,
        log=f"Chain {chain.id}: {current_action} -> {outcome}",
    )


def change_role(agent: AgentActionContext, role: str) -> AgentActionContext:
    return agent.model_copy(update={"role": role})


def chain_transition_matrix(chains: list[ChainDefinition], action_ids: list[str]) -> np.ndarray:
    positions = {action_id: index for index, action_id in enumerate(action_ids)}
    matrix = np.eye(len(action_ids), dtype=float)
    for chain in chains:
        if chain.trigger not in positions:
            continue
        row = positions[chain.trigger]
        matrix[row] = 0
        for branch in chain.branches:
            if branch.action in positions:
                matrix[row, positions[branch.action]] += branch.probability
    return matrix
