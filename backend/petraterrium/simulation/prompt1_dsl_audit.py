from __future__ import annotations

import ast
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST_PATH = Path(__file__).with_name("defaults") / "base-v1.json"
RUNTIME_SOURCE_PATHS = (
    Path("backend/petraterrium/simulation/runtime_decision_compiler.py"),
    Path("backend/petraterrium/simulation/runtime_state_compiler.py"),
    Path("engine-rust/src/agent_types.rs"),
    Path("engine-rust/src/agent_validation.rs"),
    Path("engine-rust/src/agents.rs"),
    Path("engine-rust/src/state_finance.rs"),
)
ACTION_REQUIRED_FIELDS = (
    "category",
    "formula",
    "conditions",
    "duration",
    "priority",
    "passive",
    "interruptibility",
    "interruption_outcome",
    "emergency_interruptions",
    "place_requirements",
    "time_requirements",
    "state_inputs",
    "outcomes",
)
ACTION_DURATION_FIELDS = (
    "duration_min_hours",
    "duration_median_hours",
    "duration_max_hours",
    "shape",
    "shape_parameters",
)
FINANCE_LEDGER_TARGETS = frozenset({"money", "income", "expenses", "savings", "debt"})
FINANCE_RUNTIME_MARKERS = (
    "let income = flows.wages",
    "let expenses = flows.housing",
    "next.money[agent_index] = Some",
    "next.savings[agent_index] = Some",
    "next.debt[agent_index] = Some",
    'formula: "income[t+1] = income[t] + wages',
)
SYNTHESIZED_STATE_FORMULA_MARKERS = ("+ event_delta",)
SYNTHESIZED_BASELINE_MARKERS = (
    "def _baseline_module",
    "remain-active-without-confirmed-decision-program",
    "BASELINE_PROGRAM_VERSION",
)


@dataclass(frozen=True, slots=True)
class Prompt1DslFinding:
    finding_id: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class Prompt1DslAuditReport:
    manifest_path: str
    findings: tuple[Prompt1DslFinding, ...]
    schema_version: str = "prompt1-dsl-audit-v1"

    @property
    def compliant(self) -> bool:
        return not self.findings

    @property
    def finding_ids(self) -> tuple[str, ...]:
        return tuple(finding.finding_id for finding in self.findings)

    def render(self) -> str:
        if self.compliant:
            return "Prompt 1 DSL audit passed"
        return "\n".join(
            f"{finding.finding_id} [{finding.path}]: {finding.message}" for finding in self.findings
        )


def _finding(identity: str, path: str, message: str) -> Prompt1DslFinding:
    return Prompt1DslFinding(finding_id=identity, path=path, message=message)


def _nested_formulas(value: Any) -> tuple[str, ...]:
    formulas = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "formula" and isinstance(item, str) and item.strip():
                formulas.append(item.strip())
            formulas.extend(_nested_formulas(item))
    elif isinstance(value, list | tuple):
        for item in value:
            formulas.extend(_nested_formulas(item))
    return tuple(formulas)


def _population(content: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    population = content.get("initial_population", {})
    if not isinstance(population, Mapping):
        return []
    table = population.get("population", {})
    if not isinstance(table, Mapping):
        return []
    agents = table.get("agents", [])
    if not isinstance(agents, list):
        return []
    return [agent for agent in agents if isinstance(agent, Mapping)]


def _agent_types(agent: Mapping[str, Any]) -> set[str]:
    traits = agent.get("traits", {})
    if not isinstance(traits, Mapping):
        traits = {}
    values = traits.get("agent_types")
    if isinstance(values, list):
        return {str(value).strip() for value in values if str(value).strip()}
    primary = str(traits.get("agent_type", agent.get("role", ""))).strip()
    return {primary} if primary else set()


def _place_candidates(agent: Mapping[str, Any]) -> set[str]:
    traits = agent.get("traits", {})
    if not isinstance(traits, Mapping):
        traits = {}
    return {
        str(value).strip().casefold()
        for value in (
            agent.get("place"),
            traits.get("country_id"),
            traits.get("country"),
            traits.get("region"),
            traits.get("city_id"),
            traits.get("city"),
        )
        if str(value or "").strip()
    }


def _tree_applies(tree: Mapping[str, Any], agent: Mapping[str, Any]) -> bool:
    if tree.get("status") != "ready":
        return False
    selected_types = {
        str(value).strip() for value in tree.get("agent_type_ids", []) if str(value).strip()
    }
    selected_places = {
        str(value).strip().casefold() for value in tree.get("place_ids", []) if str(value).strip()
    }
    type_match = not selected_types or bool(selected_types.intersection(_agent_types(agent)))
    place_match = not selected_places or bool(
        selected_places.intersection(_place_candidates(agent))
    )
    return type_match and place_match


def _decision_coverage_findings(content: Mapping[str, Any]) -> list[Prompt1DslFinding]:
    registry = content.get("decision_trees", {})
    trees = registry.get("trees", []) if isinstance(registry, Mapping) else []
    agents = _population(content)
    if not agents:
        return [
            _finding(
                "initial_population_missing",
                "content.initial_population.population.agents",
                "The shipped DSL contains no population against which decision coverage can "
                "be audited",
            )
        ]
    ready_trees = [tree for tree in trees if isinstance(tree, Mapping)]
    uncovered = [
        agent for agent in agents if not any(_tree_applies(tree, agent) for tree in ready_trees)
    ]
    if not uncovered:
        return []
    countries = Counter(
        str(agent.get("traits", {}).get("country_id", agent.get("place", "unknown")))
        for agent in uncovered
    )
    breakdown = ", ".join(f"{country}={count}" for country, count in sorted(countries.items()))
    return [
        _finding(
            "decision_tree_population_uncovered",
            "content.decision_trees.trees",
            f"{len(uncovered)} of {len(agents)} shipped agents have no applicable ready DSL "
            f"tree: {breakdown}",
        )
    ]


def _action_contract_findings(content: Mapping[str, Any]) -> list[Prompt1DslFinding]:
    actions = content.get("default_actions", [])
    findings = []
    for index, action in enumerate(actions if isinstance(actions, list) else []):
        if not isinstance(action, Mapping):
            findings.append(
                _finding(
                    "action_contract_invalid",
                    f"content.default_actions.{index}",
                    "Action records must be objects",
                )
            )
            continue
        action_id = str(action.get("id", index))
        missing = [field for field in ACTION_REQUIRED_FIELDS if field not in action]
        duration = action.get("duration", {})
        if isinstance(duration, Mapping):
            missing.extend(
                f"duration.{field}" for field in ACTION_DURATION_FIELDS if field not in duration
            )
        else:
            missing.append("duration")
        if missing:
            findings.append(
                _finding(
                    "action_contract_incomplete",
                    f"content.default_actions.{action_id}",
                    "Missing DSL action fields: " + ", ".join(sorted(set(missing))),
                )
            )
    return findings


def _state_formula_findings(content: Mapping[str, Any]) -> list[Prompt1DslFinding]:
    catalog = content.get("agent_states", {})
    definitions = catalog.get("definitions", []) if isinstance(catalog, Mapping) else []
    missing = [
        str(definition.get("id", index))
        for index, definition in enumerate(definitions)
        if isinstance(definition, Mapping) and not _nested_formulas(definition)
    ]
    if not missing:
        return []
    return [
        _finding(
            "state_formula_missing",
            "content.agent_states.definitions",
            "States have no DSL formula: " + ", ".join(sorted(missing)),
        )
    ]


def _global_cash_flow_findings(content: Mapping[str, Any]) -> list[Prompt1DslFinding]:
    countries = {
        str(agent.get("traits", {}).get("country_id", agent.get("place", ""))).strip()
        for agent in _population(content)
    }
    countries.discard("")
    if len(countries) < 2:
        return []
    constants = []
    actions = content.get("default_actions", [])
    for action in actions if isinstance(actions, list) else []:
        if not isinstance(action, Mapping):
            continue
        cash_flow = action.get("cash_flow", {})
        if not isinstance(cash_flow, Mapping):
            continue
        for field, value in cash_flow.items():
            if isinstance(value, int | float) and value > 0:
                constants.append(f"{action.get('id', 'unknown')}.{field}={value:g}")
    if not constants:
        return []
    return [
        _finding(
            "global_cash_flow_constant",
            "content.default_actions.*.cash_flow",
            "A multi-country DSL cannot apply one unscoped monetary constant to every country: "
            + ", ".join(constants),
        )
    ]


def _finance_rule_objects(content: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    sections = []
    for name in ("finance_rules", "state_dynamics"):
        section = content.get(name)
        if section is not None:
            sections.append(section)
    catalog = content.get("agent_states")
    if isinstance(catalog, Mapping):
        sections.extend(
            definition
            for definition in catalog.get("definitions", [])
            if isinstance(definition, Mapping)
            and str(definition.get("id", "")).startswith("finance.")
        )

    def records(value: Any) -> Iterable[Mapping[str, Any]]:
        if isinstance(value, Mapping):
            if isinstance(value.get("formula"), str):
                yield value
            for item in value.values():
                yield from records(item)
        elif isinstance(value, list | tuple):
            for item in value:
                yield from records(item)

    for section in sections:
        yield from records(section)


def _finance_target(rule: Mapping[str, Any]) -> str | None:
    for key in ("target_state_id", "target", "ledger", "output"):
        value = rule.get(key)
        if not isinstance(value, str):
            continue
        normalized = value.removeprefix("memory.").removeprefix("finance.")
        if normalized in FINANCE_LEDGER_TARGETS:
            return normalized
    return None


def _finance_formula_findings(content: Mapping[str, Any]) -> list[Prompt1DslFinding]:
    represented = {
        target
        for rule in _finance_rule_objects(content)
        if (target := _finance_target(rule)) is not None
    }
    missing = sorted(FINANCE_LEDGER_TARGETS - represented)
    if not missing:
        return []
    return [
        _finding(
            "finance_ledger_formula_missing",
            "content.finance_rules",
            "The shipped DSL does not define executable ledger formulas for: "
            + ", ".join(missing)
            + ". Add generic ledger-rule data with target, named input terms and coefficients, "
            "bounds, formula text, and evidence; compile those records unchanged for a generic "
            "Rust ledger-rule interpreter",
        )
    ]


def _interaction_findings(content: Mapping[str, Any]) -> list[Prompt1DslFinding]:
    program = content.get("interaction_program")
    if not isinstance(program, Mapping) or not program.get("rules"):
        return [
            _finding(
                "interaction_program_missing",
                "content.interaction_program",
                "The shipped DSL has no confirmed executable interaction rules",
            )
        ]
    action_ids = {
        str(action.get("id"))
        for action in content.get("default_actions", [])
        if isinstance(action, Mapping) and action.get("id")
    }
    routine_actions = {
        str(step.get("activity"))
        for routine in content.get("routines", {}).get("routines", [])
        if isinstance(routine, Mapping)
        for step in routine.get("steps", [])
        if isinstance(step, Mapping) and step.get("activity")
    }
    known_actions = action_ids | routine_actions
    unknown = sorted(
        {
            str(rule.get("source_action"))
            for rule in program.get("rules", [])
            if isinstance(rule, Mapping)
            and str(rule.get("source_action", "")).strip() not in known_actions
        }
    )
    if not unknown:
        return []
    return [
        _finding(
            "interaction_source_action_unknown",
            "content.interaction_program.rules.*.source_action",
            "Interaction rules reference actions the runtime can never observe: "
            + ", ".join(unknown),
        )
    ]


def _python_string_literals(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _runtime_findings(
    content: Mapping[str, Any],
    runtime_sources: Mapping[str, str],
) -> list[Prompt1DslFinding]:
    findings = []
    action_ids = {
        str(action.get("id"))
        for action in content.get("default_actions", [])
        if isinstance(action, Mapping) and action.get("id")
    }
    for path, source in runtime_sources.items():
        matching_markers = [marker for marker in SYNTHESIZED_BASELINE_MARKERS if marker in source]
        if matching_markers:
            findings.append(
                _finding(
                    "runtime_synthesized_baseline_action",
                    path,
                    "Runtime source contains a non-DSL baseline action: "
                    + ", ".join(matching_markers),
                )
            )
        matching_markers = (
            [marker for marker in SYNTHESIZED_STATE_FORMULA_MARKERS if marker in source]
            if path.endswith("runtime_state_compiler.py")
            else []
        )
        if matching_markers:
            findings.append(
                _finding(
                    "runtime_synthesized_state_formula",
                    path,
                    "Runtime source synthesizes state formula content instead of reading DSL data: "
                    + ", ".join(matching_markers)
                    + ". Put the event-delta update equation, bounds, coefficients, and evidence "
                    "on the state DSL record and make this compiler only validate and translate it",
                )
            )
        matching_markers = [marker for marker in FINANCE_RUNTIME_MARKERS if marker in source]
        if matching_markers:
            findings.append(
                _finding(
                    "runtime_hardcoded_finance_formula",
                    path,
                    "Runtime source hardcodes finance ledger equations instead of "
                    "interpreting DSL rules: "
                    + ", ".join(matching_markers)
                    + ". Replace named income/expense/money/savings/debt arithmetic with a generic "
                    "target-plus-weighted-inputs ledger evaluator driven by shipped finance_rules",
                )
            )
        if path.endswith(".py"):
            literals = _python_string_literals(source)
        else:
            literals = set(re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', source))
        embedded_actions = sorted(action_ids.intersection(literals))
        if embedded_actions:
            findings.append(
                _finding(
                    "runtime_action_identifier_hardcoded",
                    path,
                    "Runtime source embeds shipped action identifiers: "
                    + ", ".join(embedded_actions),
                )
            )
    return findings


def audit_prompt1_dsl_document(
    manifest: Mapping[str, Any],
    runtime_sources: Mapping[str, str],
    manifest_path: str = "<memory>",
) -> Prompt1DslAuditReport:
    content = manifest.get("content", {})
    if not isinstance(content, Mapping):
        return Prompt1DslAuditReport(
            manifest_path=manifest_path,
            findings=(
                _finding(
                    "manifest_content_invalid",
                    "content",
                    "The shipped manifest content must be an object",
                ),
            ),
        )
    findings = [
        *_decision_coverage_findings(content),
        *_action_contract_findings(content),
        *_state_formula_findings(content),
        *_global_cash_flow_findings(content),
        *_finance_formula_findings(content),
        *_interaction_findings(content),
        *_runtime_findings(content, runtime_sources),
    ]
    findings.sort(key=lambda item: (item.finding_id, item.path, item.message))
    return Prompt1DslAuditReport(
        manifest_path=manifest_path,
        findings=tuple(findings),
    )


def audit_prompt1_dsl(
    repository_root: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> Prompt1DslAuditReport:
    root = Path(repository_root or DEFAULT_REPOSITORY_ROOT).resolve()
    selected_manifest = Path(manifest_path or DEFAULT_MANIFEST_PATH).resolve()
    manifest = json.loads(selected_manifest.read_text(encoding="utf-8"))
    runtime_sources = {
        str(path): (root / path).read_text(encoding="utf-8") for path in RUNTIME_SOURCE_PATHS
    }
    return audit_prompt1_dsl_document(
        manifest,
        runtime_sources,
        manifest_path=str(selected_manifest),
    )
