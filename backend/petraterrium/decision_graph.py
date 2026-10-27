from collections import Counter, defaultdict

import numpy as np

from .actions import AgentActionContext, choose_bundle
from .contracts import (
    ActionLogEntry,
    DecisionGraph,
    DecisionGraphDiagnostic,
    DecisionGraphEdge,
    DecisionGraphFilter,
    DecisionGraphFilterOptions,
    DecisionGraphNode,
    DecisionPathStep,
)
from .dsl import ChainBranch, ChainDefinition, DSLConfig
from .population import PopulationTable


def active_filters(filters: DecisionGraphFilter) -> bool:
    return any(
        (
            filters.state,
            filters.segment,
            filters.place,
            filters.role,
            filters.tick_start is not None,
            filters.tick_end is not None,
        )
    )


def branch_matches(branch: ChainBranch, filters: DecisionGraphFilter) -> bool:
    if not active_filters(filters):
        return True
    conditions = branch.conditions
    comparisons = {
        "segment": filters.segment,
        "place": filters.place,
        "role": filters.role,
    }
    for key, selected in comparisons.items():
        if selected and key in conditions and conditions[key] != selected:
            return False
    if filters.state:
        state_conditions = {
            value for key, value in conditions.items() if key == "state" or key.startswith("state.")
        }
        if state_conditions and filters.state not in state_conditions:
            return False
    return True


def delay_label(delay_ticks: int, tick_hours: float) -> str:
    if delay_ticks == 0:
        return "same tick"
    if delay_ticks == 1 and tick_hours < 24:
        return "next tick"
    hours = delay_ticks * tick_hours
    if hours >= 24 and hours % 24 == 0:
        return f"{hours / 24:g} day" if hours == 24 else f"{hours / 24:g} days"
    return f"{hours:g} hours"


def edge_formula(chain: ChainDefinition, branch: ChainBranch) -> str:
    return branch.formula or (
        f"P({branch.action} | {chain.trigger}) = {branch.probability:g}"
    )


def graph_diagnostics(dsl: DSLConfig, edges: list[DecisionGraphEdge]):
    incoming = {edge.target for edge in edges}
    outgoing = {edge.source for edge in edges}
    terminal_targets = {edge.target for edge in edges if edge.terminates}
    role_actions = {role.id: set(role.actions) for role in dsl.roles}
    diagnostics = []
    for action in dsl.actions:
        if action.id not in incoming and action.probability.base == 0:
            diagnostics.append(
                DecisionGraphDiagnostic(
                    kind="orphan",
                    subject=action.id,
                    message=f"{action.id} has no incoming transition or start probability",
                )
            )
        if action.id not in outgoing and action.id not in terminal_targets and action.meaningful:
            diagnostics.append(
                DecisionGraphDiagnostic(
                    kind="dead_end",
                    subject=action.id,
                    message=f"{action.id} has no outgoing transition",
                )
            )
        if action.requires_role and action.id not in role_actions.get(action.requires_role, set()):
            diagnostics.append(
                DecisionGraphDiagnostic(
                    kind="unreachable_role",
                    subject=action.id,
                    message=f"{action.id} is not reachable from role {action.requires_role}",
                )
            )
    for chain in dsl.chains:
        if (
            chain.max_length is None
            and chain.continue_probability >= 1
            and not any(branch.terminates for branch in chain.branches)
        ):
            diagnostics.append(
                DecisionGraphDiagnostic(
                    kind="nonterminating_loop",
                    subject=chain.id,
                    message=f"{chain.id} can continue forever",
                )
            )
    return diagnostics


def static_decision_graph(
    dsl: DSLConfig,
    filters: DecisionGraphFilter | None = None,
) -> DecisionGraph:
    selected = filters or DecisionGraphFilter()
    nodes = [
        DecisionGraphNode(
            action_id=action.id,
            system=action.system or "unassigned",
            base_probability=action.probability.base,
            time_unit=action.probability.time_unit,
            parameter=action.probability.parameter,
            source_state=action.probability.source_state,
            opportunity=action.probability.opportunity,
            requires_role=action.requires_role,
            target_requires_role=action.target_requires_role,
            priority=action.priority,
            interruptible=action.interruptible,
            protected=action.protected,
            reschedulable=action.reschedulable,
            loser_outcome=action.loser_outcome,
            duration_minutes=action.duration_minutes,
            compatible_with=action.compatible_with,
            priority_modifiers=action.priority_modifiers,
        )
        for action in dsl.actions
    ]
    edges = [
        DecisionGraphEdge(
            edge_id=f"{chain.id}:{chain.trigger}:{branch.action}",
            source=chain.trigger,
            target=branch.action,
            chain_id=chain.id,
            intended_probability=branch.probability,
            formula=edge_formula(chain, branch),
            delay_ticks=branch.delay_ticks,
            delay_label=delay_label(branch.delay_ticks, dsl.tick.tick_hours),
            conditions=branch.conditions,
            cross_agent=branch.cross_agent,
            terminates=branch.terminates,
        )
        for chain in dsl.chains
        for branch in chain.branches
        if branch_matches(branch, selected)
    ]
    states = sorted({value for state in dsl.states for value in state.values})
    return DecisionGraph(
        view="static",
        unfiltered=not active_filters(selected),
        filters=selected,
        nodes=nodes,
        edges=edges,
        diagnostics=graph_diagnostics(dsl, edges),
        filter_options=DecisionGraphFilterOptions(
            states=states,
            places=sorted(dsl.population.places),
            roles=sorted(role.id for role in dsl.roles),
        ),
    )


def log_matches(entry: ActionLogEntry, filters: DecisionGraphFilter) -> bool:
    if filters.state and filters.state not in {
        *entry.state_before.values(),
        *entry.state_after.values(),
    }:
        return False
    if filters.segment and entry.segment != filters.segment:
        return False
    if filters.place and entry.place != filters.place:
        return False
    if filters.role and entry.role != filters.role:
        return False
    if filters.tick_start is not None and entry.tick < filters.tick_start:
        return False
    return not (filters.tick_end is not None and entry.tick > filters.tick_end)


def filter_options(logs: list[ActionLogEntry]) -> DecisionGraphFilterOptions:
    return DecisionGraphFilterOptions(
        states=sorted(
            {
                value
                for entry in logs
                for value in (*entry.state_before.values(), *entry.state_after.values())
            }
        ),
        segments=sorted({entry.segment for entry in logs}),
        places=sorted({entry.place for entry in logs}),
        roles=sorted({entry.role for entry in logs}),
        agents=sorted({entry.agent_id for entry in logs}),
        maximum_tick=max((entry.tick for entry in logs), default=0),
    )


def run_decision_graph(
    dsl: DSLConfig,
    action_logs: list[ActionLogEntry],
    run_id: str,
    filters: DecisionGraphFilter | None = None,
    agent_id: str | None = None,
) -> DecisionGraph:
    selected = filters or DecisionGraphFilter()
    static = static_decision_graph(dsl, selected)
    filtered = [entry for entry in action_logs if log_matches(entry, selected)]
    node_counts = Counter(entry.action_id for entry in filtered)
    transition_counts = Counter(
        (entry.chain_id, entry.previous_action_id, entry.action_id)
        for entry in filtered
        if entry.chain_id and entry.previous_action_id
    )
    outgoing_counts = Counter(
        (chain_id, previous)
        for chain_id, previous, _action in transition_counts.elements()
    )
    sample_agents = defaultdict(list)
    for entry in filtered:
        if not entry.chain_id or not entry.previous_action_id:
            continue
        key = (entry.chain_id, entry.previous_action_id, entry.action_id)
        if entry.agent_id not in sample_agents[key] and len(sample_agents[key]) < 5:
            sample_agents[key].append(entry.agent_id)
    nodes = [
        node.model_copy(update={"observed_count": node_counts[node.action_id]})
        for node in static.nodes
    ]
    edges = []
    matrix = defaultdict(dict)
    for edge in static.edges:
        key = (edge.chain_id, edge.source, edge.target)
        count = transition_counts[key]
        total = outgoing_counts[(edge.chain_id, edge.source)]
        matrix[edge.source][edge.target] = count
        edges.append(
            edge.model_copy(
                update={
                    "observed_count": count,
                    "observed_frequency": count / total if total else 0,
                    "sample_agents": sample_agents[key],
                }
            )
        )
    diagnostics = list(static.diagnostics)
    chain_limits = {chain.id: chain.max_length for chain in dsl.chains}
    for entry in filtered:
        limit = chain_limits.get(entry.chain_id or "")
        if limit is not None and entry.chain_step_index >= limit:
            diagnostic = DecisionGraphDiagnostic(
                kind="chain_length",
                subject=entry.chain_id or "",
                message=f"Recorded chain step {entry.chain_step_index} exceeds max length {limit}",
            )
            if diagnostic not in diagnostics:
                diagnostics.append(diagnostic)
    path = [
        DecisionPathStep(
            agent_id=entry.agent_id,
            action_id=entry.action_id,
            previous_action_id=entry.previous_action_id,
            chain_id=entry.chain_id,
            chain_step_index=entry.chain_step_index,
            tick=entry.tick,
            place=entry.place,
            target_agent_id=entry.target_agent_id,
        )
        for entry in sorted(filtered, key=lambda item: (item.tick, item.chain_step_index))
        if agent_id and entry.agent_id == agent_id
    ]
    return DecisionGraph(
        view="run",
        run_id=run_id,
        unfiltered=not active_filters(selected),
        filters=selected,
        nodes=nodes,
        edges=edges,
        diagnostics=diagnostics,
        path=path,
        transition_matrix={source: dict(targets) for source, targets in matrix.items()},
        filter_options=filter_options(action_logs),
    )


def context_for_agent(agent) -> AgentActionContext:
    return AgentActionContext(
        agent_id=agent.agent_id,
        role=agent.role,
        traits=agent.traits,
        states={key: 1 for key in agent.states},
        opportunities={"social_contact"} if agent.relationships else set(),
    )


def branch_applies(branch: ChainBranch, agent) -> bool:
    values = {
        "place": agent.place,
        "role": agent.role,
        "segment": agent.log_tier,
        **{f"state.{key}": value for key, value in agent.states.items()},
    }
    return all(values.get(key) == value for key, value in branch.conditions.items())


def record_action_logs(
    dsl: DSLConfig,
    population: PopulationTable,
    seed: int,
) -> list[ActionLogEntry]:
    rng = np.random.default_rng(seed)
    logs = []
    chains_by_trigger = defaultdict(list)
    for chain in dsl.chains:
        chains_by_trigger[chain.trigger].append(chain)
    agents = [agent for agent in population.agents if agent.log_tier != "mass"]
    for tick in range(dsl.tick.total_ticks):
        for agent in agents:
            bundle = choose_bundle(
                agent=context_for_agent(agent),
                actions=dsl.actions,
                rng=rng,
                tick_hours=dsl.tick.tick_hours,
            )
            actions = [item for item in [bundle.primary, *bundle.secondaries] if item]
            for action_id in actions:
                chains = chains_by_trigger.get(action_id, [])
                if not chains:
                    logs.append(
                        ActionLogEntry(
                            agent_id=agent.agent_id,
                            tick=tick,
                            action_id=action_id,
                            place=agent.place,
                            cause="DSL action probability",
                            state_before=agent.states,
                            state_after=agent.states,
                            segment=agent.log_tier,
                            role=agent.role,
                        )
                    )
                for chain in chains:
                    chain_id = chain.id
                    logs.append(
                        ActionLogEntry(
                            chain_id=chain_id,
                            agent_id=agent.agent_id,
                            tick=tick,
                            action_id=action_id,
                            place=agent.place,
                            cause=f"Chain {chain.id} trigger",
                            state_before=agent.states,
                            state_after=agent.states,
                            chain_step_index=0,
                            segment=agent.log_tier,
                            role=agent.role,
                        )
                    )
                    eligible = [
                        branch for branch in chain.branches if branch_applies(branch, agent)
                    ]
                    if not eligible:
                        continue
                    probabilities = np.array(
                        [branch.probability for branch in eligible], dtype=float
                    )
                    probabilities /= probabilities.sum()
                    maximum = chain.max_length or 100
                    previous = action_id
                    for step in range(1, maximum):
                        if rng.random() > chain.continue_probability:
                            break
                        branch = eligible[int(rng.choice(len(eligible), p=probabilities))]
                        target = None
                        if branch.cross_agent and agent.relationships:
                            target = agent.relationships[0].target_id
                        logs.append(
                            ActionLogEntry(
                                chain_id=chain_id,
                                agent_id=agent.agent_id,
                                tick=tick + branch.delay_ticks,
                                action_id=branch.action,
                                target_agent_id=target,
                                place=agent.place,
                                cause=edge_formula(chain, branch),
                                state_before=agent.states,
                                state_after=agent.states,
                                previous_action_id=previous,
                                chain_step_index=step,
                                segment=agent.log_tier,
                                role=agent.role,
                            )
                        )
                        previous = branch.action
                        if branch.terminates:
                            break
    return logs
