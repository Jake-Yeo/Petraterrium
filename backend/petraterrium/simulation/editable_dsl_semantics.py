import ast
import math
from itertools import product
from typing import Any

from .editable_dsl_contracts import EditableDslDocument, EditableDslEvidence


def probability_value(expression: str, coefficients: dict[str, float]) -> float:
    def evaluate(node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in coefficients:
            return coefficients[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
            return (-1 if isinstance(node.op, ast.USub) else 1) * evaluate(node.operand)
        if isinstance(node, ast.BinOp):
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "coefficient" and len(node.args) == 1:
                argument = node.args[0]
                key = (
                    argument.id
                    if isinstance(argument, ast.Name)
                    else getattr(argument, "value", None)
                )
                if key in coefficients:
                    return coefficients[key]
            arguments = [evaluate(item) for item in node.args]
            if node.func.id in {"min", "max"} and arguments:
                return min(arguments) if node.func.id == "min" else max(arguments)
            if node.func.id == "clamp" and len(arguments) == 3:
                return min(arguments[2], max(arguments[1], arguments[0]))
        raise ValueError(
            "Unsupported probability expression; use numbers, coefficient(id), "
            "+, -, *, /, min, max, or clamp"
        )

    try:
        value = evaluate(ast.parse(expression, mode="eval").body)
    except (SyntaxError, ZeroDivisionError, OverflowError, TypeError) as error:
        raise ValueError(f"Unsupported probability expression: {error}") from error
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Probability expression must evaluate to a finite value between 0 and 1")
    return value


def runtime_conditions(expression: str, document: EditableDslDocument) -> list[dict[str, Any]]:
    if expression.strip() in {"", "always", "any place", "any time"}:
        return []
    thresholds = {
        (state.id, threshold.id): threshold.value
        for state in document.states
        for threshold in state.thresholds
    }
    operators = {
        ast.Eq: "eq",
        ast.NotEq: "ne",
        ast.Gt: "gt",
        ast.GtE: "gte",
        ast.Lt: "lt",
        ast.LtE: "lte",
    }

    def number(node: ast.AST) -> float | str:
        if isinstance(node, ast.Constant) and type(node.value) in {float, int, str}:
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -float(number(node.operand))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "threshold"
            and len(node.args) == 2
        ):
            keys = tuple(
                item.id if isinstance(item, ast.Name) else getattr(item, "value", None)
                for item in node.args
            )
            if keys in thresholds:
                return thresholds[keys]
        raise ValueError(
            "Condition values must be numeric constants, place-kind strings, "
            "or threshold(state_id, threshold_id)"
        )

    def compare(node: ast.AST) -> list[dict[str, Any]]:
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
            return [condition for child in node.values for condition in compare(child)]
        if not isinstance(node, ast.Compare) or len(node.ops) != 1:
            raise ValueError("Conditions support comparisons joined with and")
        input_name = ast.unparse(node.left)
        if not input_name.startswith(("memory.", "trait.", "context.", "place.")):
            raise ValueError(
                "Condition input must use memory.*, trait.*, context.hour, "
                "context.weekday, or place.*"
            )
        if input_name.startswith("context.") and input_name not in {
            "context.hour",
            "context.weekday",
        }:
            raise ValueError("Context condition input must be context.hour or context.weekday")
        operator = operators.get(type(node.ops[0]))
        if operator is None:
            raise ValueError("Condition comparison must use ==, !=, >, >=, <, or <=")
        value = number(node.comparators[0])
        if isinstance(value, str):
            if input_name != "place.kind" or operator not in {"eq", "ne"}:
                raise ValueError("String conditions support only place.kind == or != a place kind")
            return [
                {
                    "input": input_name,
                    "operator": operator,
                    "value": 0.0,
                    "categorical_value": value,
                }
            ]
        if not math.isfinite(value):
            raise ValueError("Condition value must be finite")
        return [{"input": input_name, "operator": operator, "value": float(value)}]

    try:
        return compare(ast.parse(expression, mode="eval").body)
    except SyntaxError as error:
        raise ValueError(f"Invalid executable condition: {error.msg}") from error


def editable_provenance(evidence: EditableDslEvidence, evidence_id: str) -> dict[str, Any]:
    status = evidence.status if evidence.status in {"measured", "fitted"} else "default_estimated"
    return {
        "source": evidence.source,
        "version": evidence.source_version,
        "status": status,
        "source_date": evidence.source_date,
        "uncertainty": evidence.uncertainty,
        "evidence_id": evidence_id,
        "evidence_kind": evidence.status,
        "ci_low": 0.0,
        "ci_high": 1.0,
    }


def validate_transition_profiles(tree, document: EditableDslDocument) -> None:
    for node in tree.nodes:
        edges = [edge for edge in tree.edges if edge.from_node == node.id]
        if not edges:
            continue
        coefficients = {edge.id: edge.probability for edge in tree.edges}
        rules = [
            (
                probability_value(edge.formula, coefficients),
                [
                    condition
                    for expression in (
                        edge.condition,
                        *edge.place_requirements,
                        *edge.time_requirements,
                    )
                    for condition in runtime_conditions(expression, document)
                ],
            )
            for edge in edges
        ]
        samples: dict[str, set] = {}
        for _probability, conditions in rules:
            for condition in conditions:
                name = condition["input"]
                if "categorical_value" in condition:
                    samples.setdefault(name, {"__other__"}).add(condition["categorical_value"])
                else:
                    value = condition["value"]
                    samples.setdefault(name, set()).update((value - 1e-6, value, value + 1e-6))
        names = sorted(samples)
        if math.prod(len(samples[name]) for name in names) > 4096:
            raise ValueError(
                "Transition conditions exceed 4096 validation profiles; "
                "split this decision into modules"
            )

        def matches(condition, profile):
            actual = profile[condition["input"]]
            expected = condition.get("categorical_value", condition["value"])
            operations = {
                "eq": lambda: actual == expected,
                "ne": lambda: actual != expected,
                "gt": lambda: actual > expected,
                "gte": lambda: actual >= expected,
                "lt": lambda: actual < expected,
                "lte": lambda: actual <= expected,
            }
            return operations[condition["operator"]]()

        for values in product(*(sorted(samples[name], key=str) for name in names)):
            profile = dict(zip(names, values, strict=True))
            total = sum(
                probability
                for probability, conditions in rules
                if all(matches(condition, profile) for condition in conditions)
            )
            if abs(total - 1) > 1e-9:
                raise ValueError(
                    f"Executable outgoing probabilities from {node.id} total {total:.12g}, "
                    f"expected 1 for {profile or 'all agents'}; "
                    "add explicit complementary transitions"
                )
