from collections import defaultdict, deque

from .models import (
    MarkovModule,
    MarkovProgram,
    ModuleInput,
    ModuleOutput,
    ModuleValidationResult,
    ProgramExit,
    ProgramValidationResult,
    ValidationIssue,
)


def issue(code: str, path: str, message: str) -> ValidationIssue:
    return ValidationIssue(code=code, path=path, message=message)


def duplicates(values: list[str]) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for value in values:
        counts[value] += 1
    return sorted(value for value, count in counts.items() if count > 1)


def reachable(start: str, graph: dict[str, set[str]]) -> set[str]:
    visited: set[str] = set()
    pending = [start]
    while pending:
        node = pending.pop()
        if node in visited:
            continue
        visited.add(node)
        pending.extend(graph.get(node, set()) - visited)
    return visited


def nodes_reaching_targets(graph: dict[str, set[str]], targets: set[str]) -> set[str]:
    reverse = {node: set() for node in graph}
    for source, destinations in graph.items():
        for destination in destinations:
            reverse.setdefault(destination, set()).add(source)
    visited = set(targets)
    pending = deque(targets)
    while pending:
        node = pending.popleft()
        for source in reverse.get(node, set()):
            if source not in visited:
                visited.add(source)
                pending.append(source)
    return visited


def strongly_connected_components(graph: dict[str, set[str]]) -> list[list[str]]:
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


def closed_loops(graph: dict[str, set[str]], targets: set[str]) -> list[list[str]]:
    reaching_targets = nodes_reaching_targets(graph, targets)
    result = []
    for component in strongly_connected_components(graph):
        has_cycle = len(component) > 1 or any(node in graph.get(node, set()) for node in component)
        if has_cycle and not any(node in reaching_targets for node in component):
            result.append(component)
    return sorted(result)


def validate_state_input(
    input_value: ModuleInput,
    path: str,
) -> list[ValidationIssue]:
    identity = f"{input_value.id} {input_value.feature_id or ''}".lower()
    tokens = set(identity.replace("-", " ").replace("_", " ").split())
    issues: list[ValidationIssue] = []
    if "contamination" in tokens and input_value.kind != "place_state":
        issues.append(
            issue(
                "contamination_not_place_state",
                path,
                f"Contamination input {input_value.id} must be declared as place_state",
            )
        )
    history_terms = ("timer", "immune", "aversion", "history", "previous", "duration")
    if any(term in tokens for term in history_terms) and input_value.kind != "persisted_state":
        issues.append(
            issue(
                "history_not_persisted_state",
                path,
                f"History input {input_value.id} must be declared as persisted_state",
            )
        )
    return issues


def validate_module(module: MarkovModule) -> ModuleValidationResult:
    issues: list[ValidationIssue] = []
    state_ids = [state.id for state in module.states]
    input_ids = [item.id for item in module.inputs]
    output_ids = [item.id for item in module.outputs]
    transition_ids = [item.id for item in module.transitions]
    state_set = set(state_ids)
    input_by_id = {item.id: item for item in module.inputs}
    output_set = set(output_ids)
    for name, values in (
        ("state", state_ids),
        ("input", input_ids),
        ("output", output_ids),
        ("transition", transition_ids),
        ("exit state", module.exit_states),
    ):
        for identity in duplicates(values):
            issues.append(
                issue(
                    f"duplicate_{name.replace(' ', '_')}",
                    name,
                    f"Duplicate {name} {identity}",
                )
            )
    if module.entry_state not in state_set:
        issues.append(
            issue(
                "missing_entry_state",
                "entry_state",
                f"Entry state {module.entry_state} is missing",
            )
        )
    for index, exit_state in enumerate(module.exit_states):
        if exit_state not in state_set:
            issues.append(
                issue(
                    "missing_exit_state",
                    f"exit_states.{index}",
                    f"Exit state {exit_state} is missing",
                )
            )
    for index, input_value in enumerate(module.inputs):
        issues.extend(validate_state_input(input_value, f"inputs.{index}"))
    for state_index, state in enumerate(module.states):
        for effect in state.effects:
            if effect not in output_set:
                issues.append(
                    issue(
                        "missing_output",
                        f"states.{state_index}.effects",
                        f"State {state.id} references undeclared output {effect}",
                    )
                )
    graph = {identity: set() for identity in state_set}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for index, transition_value in enumerate(module.transitions):
        path = f"transitions.{index}"
        if transition_value.from_state not in state_set:
            issues.append(
                issue(
                    "missing_source_state",
                    f"{path}.from_state",
                    f"Transition {transition_value.id} references missing source state",
                )
            )
        if transition_value.to_state not in state_set:
            issues.append(
                issue(
                    "missing_target_state",
                    f"{path}.to_state",
                    f"Transition {transition_value.id} references missing target state",
                )
            )
        if transition_value.from_state in state_set and transition_value.to_state in state_set:
            graph[transition_value.from_state].add(transition_value.to_state)
            outgoing[transition_value.from_state].append(transition_value.id)
        if transition_value.condition is None:
            issues.append(
                issue(
                    "missing_condition",
                    f"{path}.condition",
                    f"Transition {transition_value.id} requires an explicit condition",
                )
            )
        else:
            for clause_index, clause in enumerate(transition_value.condition.clauses):
                if clause.input_id not in input_by_id:
                    issues.append(
                        issue(
                            "undeclared_condition_input",
                            f"{path}.condition.clauses.{clause_index}.input_id",
                            f"Condition input {clause.input_id} is not declared",
                        )
                    )
        query = transition_value.probability
        place_input = input_by_id.get(query.place_input)
        time_input = input_by_id.get(query.time_input)
        if place_input is None or place_input.kind != "place":
            issues.append(
                issue(
                    "invalid_place_input",
                    f"{path}.probability.place_input",
                    "Probability evidence requires a declared place input",
                )
            )
        if time_input is None or time_input.kind != "time":
            issues.append(
                issue(
                    "invalid_time_input",
                    f"{path}.probability.time_input",
                    "Probability evidence requires a declared time input",
                )
            )
        for predictor in query.predictor_inputs:
            predictor_input = input_by_id.get(predictor)
            if predictor_input is None or predictor_input.kind != "agent_trait":
                issues.append(
                    issue(
                        "invalid_predictor_input",
                        f"{path}.probability.predictor_inputs",
                        f"Predictor {predictor} must be a declared agent_trait input",
                    )
                )
    for exit_state in set(module.exit_states) & state_set:
        if outgoing[exit_state]:
            issues.append(
                issue(
                    "exit_has_outgoing_transition",
                    "exit_states",
                    f"Exit state {exit_state} cannot have an internal outgoing transition",
                )
            )
    dead_ends = sorted(
        state for state in state_set if state not in module.exit_states and not outgoing[state]
    )
    for state in dead_ends:
        issues.append(issue("dead_end", "states", f"State {state} is a non-exit dead end"))
    reached = reachable(module.entry_state, graph) if module.entry_state in state_set else set()
    unreachable_states = sorted(state_set - reached)
    for state in unreachable_states:
        issues.append(issue("unreachable_state", "states", f"State {state} is unreachable"))
    unreachable_exits = sorted(set(module.exit_states) - reached)
    for state in unreachable_exits:
        issues.append(
            issue("unreachable_exit", "exit_states", f"Exit state {state} is unreachable")
        )
    non_terminating_loops = closed_loops(graph, set(module.exit_states))
    for loop in non_terminating_loops:
        issues.append(
            issue(
                "non_terminating_loop",
                "transitions",
                f"States {', '.join(loop)} form a loop with no path to an exit",
            )
        )
    return ModuleValidationResult(
        valid=not issues,
        issues=issues,
        dead_ends=dead_ends,
        unreachable_states=unreachable_states,
        unreachable_exits=unreachable_exits,
        non_terminating_loops=non_terminating_loops,
    )


def source_interface(
    source_kind: str,
    source_id: str,
    source_inputs: dict[str, ModuleInput],
    source_outputs: dict[str, ModuleOutput],
    external_inputs: dict[str, ModuleInput],
) -> tuple[str, str] | None:
    if source_kind == "input" and source_id in source_inputs:
        value = source_inputs[source_id]
        return value.kind, value.value_type
    if source_kind == "external" and source_id in external_inputs:
        value = external_inputs[source_id]
        return value.kind, value.value_type
    if source_kind == "output" and source_id in source_outputs:
        value = source_outputs[source_id]
        output_domains = {
            "location": "place",
            "health": "persisted_state",
            "friends": "persisted_state",
            "persisted_state": "persisted_state",
            "place_state": "place_state",
            "media_state": "media_state",
            "event": "context",
        }
        return output_domains[value.kind], value.value_type
    return None


def validate_program(program: MarkovProgram) -> ProgramValidationResult:
    issues: list[ValidationIssue] = []
    module_ids = [module.id for module in program.modules]
    module_by_id = {module.id: module for module in program.modules}
    module_results = {module.id: validate_module(module) for module in program.modules}
    for module_id, result in module_results.items():
        for module_issue in result.issues:
            issues.append(
                issue(
                    module_issue.code,
                    f"modules.{module_id}.{module_issue.path}",
                    module_issue.message,
                )
            )
    for identity in duplicates(module_ids):
        issues.append(issue("duplicate_module", "modules", f"Duplicate module {identity}"))
    if program.entry_module not in module_by_id:
        issues.append(
            issue(
                "missing_entry_module",
                "entry_module",
                f"Entry module {program.entry_module} is missing",
            )
        )
    external_ids = [item.id for item in program.external_inputs]
    for identity in duplicates(external_ids):
        issues.append(
            issue(
                "duplicate_external_input",
                "external_inputs",
                f"Duplicate external input {identity}",
            )
        )
    external_by_id = {item.id: item for item in program.external_inputs}
    terminal_pairs = {(item.module_id, item.state_id) for item in program.terminal_exits}
    for index, terminal in enumerate(program.terminal_exits):
        module = module_by_id.get(terminal.module_id)
        if module is None or terminal.state_id not in module.exit_states:
            issues.append(
                issue(
                    "invalid_terminal_exit",
                    f"terminal_exits.{index}",
                    f"Terminal exit {terminal.module_id}.{terminal.state_id} is not a module exit",
                )
            )
    linked_pairs: set[tuple[str, str]] = set()
    module_graph = {module_id: set() for module_id in module_ids}
    for index, link in enumerate(program.links):
        path = f"links.{index}"
        source = module_by_id.get(link.from_module)
        target = module_by_id.get(link.to_module)
        if source is None:
            issues.append(
                issue("missing_link_source", path, f"Module {link.from_module} is missing")
            )
            continue
        if target is None:
            issues.append(issue("missing_link_target", path, f"Module {link.to_module} is missing"))
            continue
        if link.exit_state not in source.exit_states:
            issues.append(
                issue(
                    "invalid_link_exit",
                    f"{path}.exit_state",
                    f"State {link.exit_state} is not an exit of {source.id}",
                )
            )
        pair = (source.id, link.exit_state)
        if pair in linked_pairs:
            issues.append(
                issue(
                    "duplicate_exit_link",
                    path,
                    f"Exit {source.id}.{link.exit_state} has more than one module link",
                )
            )
        linked_pairs.add(pair)
        module_graph[source.id].add(target.id)
        target_inputs = {item.id: item for item in target.inputs}
        source_inputs = {item.id: item for item in source.inputs}
        source_outputs = {item.id: item for item in source.outputs}
        binding_targets = [binding.target_input for binding in link.bindings]
        for identity in duplicates(binding_targets):
            issues.append(
                issue(
                    "duplicate_input_binding",
                    f"{path}.bindings",
                    f"Target input {identity} is bound more than once",
                )
            )
        for binding_index, binding in enumerate(link.bindings):
            binding_path = f"{path}.bindings.{binding_index}"
            target_input = target_inputs.get(binding.target_input)
            if target_input is None:
                issues.append(
                    issue(
                        "missing_target_input",
                        binding_path,
                        f"Target input {binding.target_input} is not declared by {target.id}",
                    )
                )
                continue
            source_value = source_interface(
                binding.source_kind,
                binding.source_id,
                source_inputs,
                source_outputs,
                external_by_id,
            )
            if source_value is None:
                issues.append(
                    issue(
                        "missing_binding_source",
                        binding_path,
                        f"Binding source {binding.source_kind}.{binding.source_id} is missing",
                    )
                )
                continue
            if source_value != (target_input.kind, target_input.value_type):
                issues.append(
                    issue(
                        "incompatible_binding",
                        binding_path,
                        f"Binding for {target_input.id} does not match its domain and value type",
                    )
                )
        missing_bindings = sorted(
            item.id for item in target.inputs if item.required and item.id not in binding_targets
        )
        for identity in missing_bindings:
            issues.append(
                issue(
                    "missing_required_binding",
                    f"{path}.bindings",
                    f"Required input {target.id}.{identity} is not bound",
                )
            )
    all_exits = {
        (module.id, state_id) for module in program.modules for state_id in module.exit_states
    }
    unlinked_pairs = sorted(all_exits - linked_pairs - terminal_pairs)
    unlinked_exits = [
        ProgramExit(module_id=module_id, state_id=state_id)
        for module_id, state_id in unlinked_pairs
    ]
    for value in unlinked_exits:
        issues.append(
            issue(
                "unlinked_exit",
                "links",
                f"Exit {value.module_id}.{value.state_id} is neither linked nor terminal",
            )
        )
    reached = (
        reachable(program.entry_module, module_graph)
        if program.entry_module in module_by_id
        else set()
    )
    unreachable_modules = sorted(set(module_ids) - reached)
    for module_id in unreachable_modules:
        issues.append(issue("unreachable_module", "modules", f"Module {module_id} is unreachable"))
    terminal_modules = {module_id for module_id, _ in terminal_pairs}
    non_terminating_module_loops = closed_loops(module_graph, terminal_modules)
    for loop in non_terminating_module_loops:
        issues.append(
            issue(
                "non_terminating_module_loop",
                "links",
                f"Modules {', '.join(loop)} form a loop with no path to a terminal exit",
            )
        )
    return ProgramValidationResult(
        valid=not issues,
        issues=issues,
        module_results=module_results,
        unreachable_modules=unreachable_modules,
        unlinked_exits=unlinked_exits,
        non_terminating_module_loops=non_terminating_module_loops,
    )
