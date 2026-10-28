import math
import re
from collections import Counter

from .editable_dsl_contracts import (
    EditableDslDocument,
    EditableDslEvidence,
    EditableDslIssue,
    EditableDslValidation,
)
from .editable_dsl_semantics import (
    probability_value,
    runtime_conditions,
    validate_transition_profiles,
)

IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]*$")
SUPPORTED_DURATION_SHAPES = {"triangular", "uniform", "lognormal"}


def _issue(path: str, message: str, severity: str = "error") -> EditableDslIssue:
    return EditableDslIssue(path=path, message=message, severity=severity)


def _duplicates(values: list[str], path: str, label: str) -> list[EditableDslIssue]:
    return [
        _issue(path, f"Duplicate {label} id {value}")
        for value, count in Counter(values).items()
        if count > 1
    ]


def _identifier_issues(value: str, path: str, label: str) -> list[EditableDslIssue]:
    if not IDENTIFIER.fullmatch(value):
        return [
            _issue(
                path,
                f"{label} id must use lowercase letters, numbers, underscores, or hyphens",
            )
        ]
    return []


def _evidence_issues(
    evidence: EditableDslEvidence,
    path: str,
) -> list[EditableDslIssue]:
    issues = []
    if not evidence.source or not evidence.source_version:
        issues.append(_issue(path, "Evidence source and source version are required"))
    if not math.isfinite(evidence.uncertainty) or not 0 <= evidence.uncertainty <= 1:
        issues.append(_issue(path, "Evidence uncertainty must be between 0 and 1"))
    if evidence.status in {"estimated", "default"} and not (
        evidence.reasoning and evidence.reasoning.strip()
    ):
        issues.append(_issue(path, "Estimated and default evidence require explicit reasoning"))
    return issues


def _graph_depth_issues(document: EditableDslDocument) -> list[EditableDslIssue]:
    issues = []
    for tree in document.trees:
        adjacency: dict[str, list[str]] = {}
        for edge in tree.edges:
            adjacency.setdefault(edge.from_node, []).append(edge.to_node)

        def visit(
            node_id: str,
            ancestors: tuple[str, ...],
            depth: int,
            tree_id: str = tree.id,
            graph: dict[str, list[str]] = adjacency,
        ) -> None:
            if node_id in ancestors:
                issues.append(
                    _issue(
                        f"trees.{tree_id}.nodes.{node_id}",
                        "Decision tree contains an unbounded cycle",
                    )
                )
                return
            if depth > 5:
                issues.append(
                    _issue(
                        f"trees.{tree_id}",
                        "Decision path exceeds the maximum depth of five",
                    )
                )
                return
            for target in graph.get(node_id, []):
                visit(target, (*ancestors, node_id), depth + 1)

        visit(tree.entry_node, (), 0)
    return issues


def validate_editable_dsl(
    document: EditableDslDocument,
    required_root_module_ids: tuple[str, ...] = (),
    baseline: EditableDslDocument | None = None,
) -> EditableDslValidation:
    issues: list[EditableDslIssue] = []
    if not document.schema_version:
        issues.append(_issue("schema_version", "Schema version is required"))
    if not document.version:
        issues.append(_issue("version", "DSL version is required"))
    if not math.isfinite(document.tick_hours) or not 0 < document.tick_hours <= 24:
        issues.append(_issue("tick_hours", "Tick hours must be greater than 0 and at most 24"))
    elif abs(round(24 / document.tick_hours) - 24 / document.tick_hours) > 1e-9:
        issues.append(
            _issue(
                "tick_hours",
                "Tick hours do not divide a 24-hour accounting day exactly",
                "warning",
            )
        )
    action_ids = [action.id for action in document.actions]
    state_ids = [state.id for state in document.states]
    tree_ids = [tree.id for tree in document.trees]
    issues.extend(_duplicates(action_ids, "actions", "action"))
    issues.extend(_duplicates(state_ids, "states", "state"))
    issues.extend(_duplicates(tree_ids, "trees", "tree"))
    known_actions = set(action_ids)
    baseline_actions = {action.id: action for action in baseline.actions} if baseline else {}
    known_trees = set(tree_ids)
    for root_id in required_root_module_ids:
        if root_id not in known_trees:
            issues.append(
                _issue(
                    "trees",
                    f"Installed decision tree root module {root_id} cannot be removed",
                )
            )

    for action_index, action in enumerate(document.actions):
        path = f"actions.{action.id or action_index}"
        issues.extend(_identifier_issues(action.id, f"{path}.id", "Action"))
        if not action.name or not action.formula:
            issues.append(_issue(path, "Action name and formula are required"))
        previous = baseline_actions.get(action.id)
        if previous is None or previous.formula != action.formula:
            try:
                probability_value(
                    action.formula, {item.id: item.value for item in action.coefficients}
                )
            except ValueError as error:
                issues.append(_issue(f"{path}.formula", str(error)))
        for requirement_name in ("place_requirements", "time_requirements"):
            requirements = getattr(action, requirement_name)
            if previous is not None and requirements == getattr(previous, requirement_name):
                continue
            for index, expression in enumerate(requirements):
                try:
                    runtime_conditions(expression, document)
                except ValueError as error:
                    issues.append(_issue(f"{path}.{requirement_name}.{index}", str(error)))
        if action.evidence is not None:
            issues.extend(_evidence_issues(action.evidence, f"{path}.evidence"))
        if not action.category or not action.aggregate_statistic_id:
            issues.append(
                _issue(
                    path,
                    "Action time category and aggregate statistic are required",
                )
            )
        unknown_interruptions = sorted(set(action.emergency_interruptions) - known_actions)
        if unknown_interruptions:
            issues.append(
                _issue(
                    f"{path}.emergency_interruptions",
                    "Emergency actions do not exist: " + ", ".join(unknown_interruptions),
                )
            )
        duration = action.duration
        values = (duration.min_hours, duration.median_hours, duration.max_hours)
        if any(not math.isfinite(value) for value in values):
            issues.append(_issue(f"{path}.duration", "Action duration values must be finite"))
        elif (
            duration.min_hours < 0
            or duration.median_hours <= 0
            or duration.min_hours > duration.median_hours
            or duration.median_hours > duration.max_hours
        ):
            issues.append(
                _issue(
                    f"{path}.duration",
                    "Duration must satisfy 0 <= minimum <= median <= maximum "
                    "with a positive median",
                )
            )
        elif duration.max_hours <= duration.min_hours:
            issues.append(
                _issue(
                    f"{path}.duration",
                    "A fixed action duration is not executable",
                )
            )
        if duration.shape not in SUPPORTED_DURATION_SHAPES:
            issues.append(
                _issue(
                    f"{path}.duration.shape",
                    f"Duration shape {duration.shape} is not supported by the generic runtime",
                )
            )
        if any(not math.isfinite(value) for value in duration.shape_parameters.values()):
            issues.append(
                _issue(
                    f"{path}.duration.shape_parameters",
                    "Duration shape parameters must be finite",
                )
            )
        if duration.shape == "uniform" and math.isfinite(sum(values)):
            midpoint = (duration.min_hours + duration.max_hours) / 2
            if abs(duration.median_hours - midpoint) > 1e-9:
                issues.append(
                    _issue(
                        f"{path}.duration.median_hours",
                        "Uniform duration median must equal the midpoint of its range",
                    )
                )
        if duration.shape == "lognormal" and duration.shape_parameters.get("sigma", 0) <= 0:
            issues.append(
                _issue(
                    f"{path}.duration.shape_parameters",
                    "Lognormal duration requires a positive sigma parameter",
                )
            )
        issues.extend(_evidence_issues(duration.evidence, f"{path}.duration.evidence"))
        if duration.max_hours > document.tick_hours:
            issues.append(
                _issue(
                    f"{path}.duration.max_hours",
                    "Sampled occurrences may span multiple ticks and must retain remaining time",
                    "warning",
                )
            )
        coefficient_ids = [item.id for item in action.coefficients]
        issues.extend(_duplicates(coefficient_ids, f"{path}.coefficients", "coefficient"))
        for coefficient_index, coefficient in enumerate(action.coefficients):
            coefficient_path = f"{path}.coefficients.{coefficient.id or coefficient_index}"
            issues.extend(
                _identifier_issues(
                    coefficient.id,
                    f"{coefficient_path}.id",
                    "Coefficient",
                )
            )
            if not coefficient.name or not math.isfinite(coefficient.value):
                issues.append(
                    _issue(
                        coefficient_path,
                        "Coefficient name and finite value are required",
                    )
                )
            if coefficient.id.startswith("runtime_rule_") and not 0 <= coefficient.value <= 1:
                issues.append(
                    _issue(
                        f"{coefficient_path}.value",
                        "Runtime-rule probability coefficients must be between 0 and 1",
                    )
                )
            issues.extend(_evidence_issues(coefficient.evidence, f"{coefficient_path}.evidence"))
        if any(not requirement for requirement in action.place_requirements):
            issues.append(
                _issue(
                    f"{path}.place_requirements",
                    "Place requirements cannot be empty",
                )
            )
        if any(not requirement for requirement in action.time_requirements):
            issues.append(_issue(f"{path}.time_requirements", "Time requirements cannot be empty"))

    for state_index, state in enumerate(document.states):
        path = f"states.{state.id or state_index}"
        issues.extend(_identifier_issues(state.id, f"{path}.id", "State"))
        numeric_values = (
            state.min,
            state.max,
            state.initial,
            state.decay_per_hour,
            state.recovery_per_hour,
        )
        if any(not math.isfinite(value) for value in numeric_values):
            issues.append(_issue(path, "State values must be finite"))
        if state.min >= state.max:
            issues.append(_issue(path, "State minimum must be below its maximum"))
        if not state.min <= state.initial <= state.max:
            issues.append(_issue(f"{path}.initial", "Initial state value must be inside its range"))
        if state.decay_per_hour < 0 or state.recovery_per_hour < 0:
            issues.append(_issue(path, "State decay and recovery rates cannot be negative"))
        threshold_ids = [threshold.id for threshold in state.thresholds]
        issues.extend(_duplicates(threshold_ids, f"{path}.thresholds", "threshold"))
        for threshold in state.thresholds:
            issues.extend(
                _identifier_issues(
                    threshold.id,
                    f"{path}.thresholds.{threshold.id}.id",
                    "Threshold",
                )
            )
            if not threshold.label or not state.min <= threshold.value <= state.max:
                issues.append(
                    _issue(
                        f"{path}.thresholds.{threshold.id}",
                        "Threshold label and a value inside the state range are required",
                    )
                )

    for tree_index, tree in enumerate(document.trees):
        path = f"trees.{tree.id or tree_index}"
        try:
            validate_transition_profiles(tree, document)
        except ValueError as error:
            issues.append(_issue(path, str(error)))
        issues.extend(_identifier_issues(tree.id, f"{path}.id", "Tree"))
        node_ids = [node.id for node in tree.nodes]
        edge_ids = [edge.id for edge in tree.edges]
        issues.extend(_duplicates(node_ids, f"{path}.nodes", "node"))
        issues.extend(_duplicates(edge_ids, f"{path}.edges", "edge"))
        known_nodes = set(node_ids)
        if tree.entry_node not in known_nodes:
            issues.append(_issue(f"{path}.entry_node", "Entry node must reference this tree"))
        for node in tree.nodes:
            node_path = f"{path}.nodes.{node.id}"
            issues.extend(_identifier_issues(node.id, f"{node_path}.id", "Node"))
            if not node.label:
                issues.append(_issue(node_path, "Node label is required"))
            if node.kind == "action" and (
                node.action_id is None or node.action_id not in known_actions
            ):
                issues.append(_issue(node_path, "Action node must reference an existing action"))
            if node.kind != "action" and node.action_id is not None:
                issues.append(_issue(node_path, "Only action nodes may reference an action"))
            if node.kind == "module" and (
                node.target_tree_id is None or node.target_tree_id not in known_trees
            ):
                issues.append(_issue(node_path, "Module node must reference an existing tree"))
            if node.kind != "module" and node.target_tree_id is not None:
                issues.append(_issue(node_path, "Only module nodes may reference a target tree"))
            outgoing = [edge for edge in tree.edges if edge.from_node == node.id]
            if node.kind == "terminal" and outgoing:
                issues.append(_issue(node_path, "Terminal nodes cannot have outgoing edges"))
            if node.kind != "terminal" and not outgoing:
                issues.append(_issue(node_path, "Nonterminal node is a dead end"))
            if outgoing:
                total = sum(edge.probability for edge in outgoing)
                if not math.isfinite(total) or abs(total - 1) > 1e-9:
                    issues.append(
                        _issue(
                            f"{node_path}.outgoing",
                            f"Outgoing probabilities total {total:.12g}, expected 1",
                        )
                    )
        for edge in tree.edges:
            edge_path = f"{path}.edges.{edge.id}"
            issues.extend(_identifier_issues(edge.id, f"{edge_path}.id", "Edge"))
            if edge.from_node not in known_nodes or edge.to_node not in known_nodes:
                issues.append(
                    _issue(
                        edge_path,
                        "Edge endpoints must reference nodes in the same tree",
                    )
                )
            if not math.isfinite(edge.probability) or not 0 <= edge.probability <= 1:
                issues.append(_issue(edge_path, "Edge probability must be between 0 and 1"))
            if not edge.formula or not edge.condition:
                issues.append(_issue(edge_path, "Edge formula and condition are required"))
            try:
                probability_value(edge.formula, {item.id: item.probability for item in tree.edges})
                for expression in (
                    edge.condition,
                    *edge.place_requirements,
                    *edge.time_requirements,
                ):
                    runtime_conditions(expression, document)
            except ValueError as error:
                issues.append(_issue(edge_path, str(error)))
            if any(not item for item in edge.place_requirements):
                issues.append(_issue(edge_path, "Edge place requirements cannot be empty"))
            if any(not item for item in edge.time_requirements):
                issues.append(_issue(edge_path, "Edge time requirements cannot be empty"))
    issues.extend(_graph_depth_issues(document))
    return EditableDslValidation(
        valid=not any(item.severity == "error" for item in issues),
        issues=tuple(issues),
    )
