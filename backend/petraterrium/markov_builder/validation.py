from collections import defaultdict, deque

from .models import (
    ChainDraft,
    ChainValidationIssue,
    ChainValidationResult,
    OutgoingProbabilityTotal,
)


def _issue(code: str, path: str, message: str, severity: str = "error") -> ChainValidationIssue:
    return ChainValidationIssue(code=code, severity=severity, path=path, message=message)


def _strongly_connected_components(graph: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph.get(node, set()):
            if target not in indices:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] != indices[node]:
            return
        component: list[str] = []
        while stack:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        components.append(sorted(component))

    for node in graph:
        if node not in indices:
            visit(node)
    return components


def _reachable(start: str, graph: dict[str, set[str]]) -> set[str]:
    reached: set[str] = set()
    pending = [start]
    while pending:
        node = pending.pop()
        if node in reached:
            continue
        reached.add(node)
        pending.extend(graph.get(node, set()) - reached)
    return reached


def _nodes_reaching_terminals(
    nodes: set[str], graph: dict[str, set[str]], terminals: set[str]
) -> set[str]:
    reverse = {node: set() for node in nodes}
    for source, targets in graph.items():
        for target in targets:
            if target in reverse:
                reverse[target].add(source)
    reached = set(terminals)
    pending = deque(terminals)
    while pending:
        node = pending.popleft()
        for source in reverse.get(node, set()):
            if source not in reached:
                reached.add(source)
                pending.append(source)
    return reached


def validate_chain_draft(draft: ChainDraft) -> ChainValidationResult:
    issues: list[ChainValidationIssue] = []
    node_ids = [node.id for node in draft.nodes]
    transition_ids = [transition.id for transition in draft.transitions]
    node_set = set(node_ids)
    duplicate_nodes = sorted({item for item in node_ids if node_ids.count(item) > 1})
    duplicate_transitions = sorted(
        {item for item in transition_ids if transition_ids.count(item) > 1}
    )
    for identity in duplicate_nodes:
        issues.append(_issue("duplicate_node", "nodes", f"Node id {identity} is duplicated"))
    for identity in duplicate_transitions:
        issues.append(
            _issue("duplicate_transition", "transitions", f"Transition id {identity} is duplicated")
        )
    if not draft.nodes:
        issues.append(_issue("missing_nodes", "nodes", "Add at least one state"))
    if draft.entry_node is None:
        issues.append(_issue("missing_entry", "entry_node", "Choose an entry state"))
    elif draft.entry_node not in node_set:
        issues.append(
            _issue("invalid_entry", "entry_node", f"Entry state {draft.entry_node} does not exist")
        )

    outgoing: dict[str, list] = defaultdict(list)
    graph = {node: set() for node in node_set}
    for index, transition in enumerate(draft.transitions):
        path = f"transitions.{index}"
        if transition.from_node not in node_set:
            issues.append(
                _issue(
                    "missing_source_node",
                    f"{path}.from_node",
                    f"Source state {transition.from_node} does not exist",
                )
            )
        if transition.to_node not in node_set:
            issues.append(
                _issue(
                    "missing_target_node",
                    f"{path}.to_node",
                    f"Target state {transition.to_node} does not exist",
                )
            )
        if transition.from_node in node_set:
            outgoing[transition.from_node].append(transition)
        if transition.from_node in node_set and transition.to_node in node_set:
            graph[transition.from_node].add(transition.to_node)

    terminal_states = sorted(node.id for node in draft.nodes if node.terminal)
    terminal_set = set(terminal_states)
    if not terminal_states:
        issues.append(_issue("missing_terminal", "nodes", "Mark at least one terminal state"))
    for node in draft.nodes:
        if node.terminal and outgoing[node.id]:
            issues.append(
                _issue(
                    "terminal_has_outgoing",
                    f"nodes.{node_ids.index(node.id)}.terminal",
                    f"Terminal state {node.id} has outgoing transitions",
                )
            )

    missing_probabilities = sorted(
        transition.id for transition in draft.transitions if transition.probability is None
    )
    missing_conditions = sorted(
        transition.id
        for transition in draft.transitions
        if not (transition.condition or "").strip()
    )
    for identity in missing_probabilities:
        issues.append(
            _issue(
                "missing_probability",
                "transitions",
                f"Transition {identity} needs an explicit probability",
            )
        )
    for index, transition in enumerate(draft.transitions):
        if transition.probability is not None and not 0 <= transition.probability <= 1:
            issues.append(
                _issue(
                    "probability_range",
                    f"transitions.{index}.probability",
                    f"Transition {transition.id} probability must be between 0 and 1",
                )
            )
    for identity in missing_conditions:
        issues.append(
            _issue(
                "missing_condition",
                "transitions",
                f"Transition {identity} needs a condition; use always when unconditional",
            )
        )

    outgoing_totals: list[OutgoingProbabilityTotal] = []
    for node in draft.nodes:
        if node.terminal:
            continue
        transitions = outgoing[node.id]
        known_total = sum(
            transition.probability or 0
            for transition in transitions
            if transition.probability is not None
        )
        unknown_count = sum(transition.probability is None for transition in transitions)
        complete = bool(transitions) and unknown_count == 0
        sums_to_one = complete and abs(known_total - 1) <= 1e-9
        outgoing_totals.append(
            OutgoingProbabilityTotal(
                node_id=node.id,
                known_total=known_total,
                unknown_count=unknown_count,
                complete=complete,
                sums_to_one=sums_to_one,
            )
        )
        if complete and not sums_to_one:
            issues.append(
                _issue(
                    "outgoing_total",
                    f"nodes.{node_ids.index(node.id)}",
                    f"Outgoing probabilities from {node.id} sum to {known_total:.6g}, not 1",
                )
            )

    dead_ends = sorted(
        node.id for node in draft.nodes if not node.terminal and not outgoing[node.id]
    )
    for identity in dead_ends:
        issues.append(
            _issue(
                "dead_end",
                "nodes",
                f"State {identity} has no outgoing transition and is not terminal",
            )
        )

    reaching_terminals = _nodes_reaching_terminals(node_set, graph, terminal_set)
    non_terminating_loops = []
    for component in _strongly_connected_components(graph):
        cyclic = len(component) > 1 or any(node in graph[node] for node in component)
        if cyclic and not any(node in reaching_terminals for node in component):
            non_terminating_loops.append(component)
            issues.append(
                _issue(
                    "non_terminating_loop",
                    "transitions",
                    f"Loop {' -> '.join(component)} has no path to a terminal state",
                )
            )

    reachable_from_entry = (
        _reachable(draft.entry_node, graph) if draft.entry_node in node_set else set()
    )
    unreachable_nodes = sorted(node_set - reachable_from_entry)
    for identity in unreachable_nodes:
        issues.append(
            _issue(
                "unreachable_node",
                "nodes",
                f"State {identity} cannot be reached from the entry state",
                "warning",
            )
        )
    no_terminal_path = sorted(node_set - reaching_terminals - set(dead_ends))
    for identity in no_terminal_path:
        if any(identity in component for component in non_terminating_loops):
            continue
        issues.append(
            _issue(
                "no_terminal_path",
                "nodes",
                f"State {identity} has no path to a terminal state",
            )
        )
    valid = not any(item.severity == "error" for item in issues)
    return ChainValidationResult(
        valid=valid,
        can_confirm=valid,
        issues=issues,
        outgoing_totals=outgoing_totals,
        terminal_states=terminal_states,
        dead_ends=dead_ends,
        non_terminating_loops=sorted(non_terminating_loops),
        missing_conditions=missing_conditions,
        missing_probabilities=missing_probabilities,
        unreachable_nodes=unreachable_nodes,
    )
