import math
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from statistics import fmean
from typing import Any

from .default_dsl import DefaultDslReceipt
from .editable_dsl_contracts import (
    EditableDslAction,
    EditableDslCoefficient,
    EditableDslDocument,
    EditableDslDuration,
    EditableDslEvidence,
    EditableDslRevision,
    EditableDslState,
    EditableDslTree,
    EditableDslTreeEdge,
    EditableDslTreeNode,
)
from .editable_dsl_semantics import probability_value, runtime_conditions
from .registry_store import SimulationRegistryStore


def _default_evidence(
    source: str,
    version: str,
    uncertainty: float,
    source_date: str | None = None,
    reasoning: str | None = None,
) -> EditableDslEvidence:
    return EditableDslEvidence(
        status="default",
        source=source,
        source_version=version,
        source_date=source_date,
        uncertainty=uncertainty,
        reasoning=reasoning,
    )


def _action_evidence(
    action: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    version: str,
) -> EditableDslEvidence:
    native = action.get("evidence", {})
    if native.get("editable_provenance"):
        return EditableDslEvidence.model_validate(native["editable_provenance"])
    selected = [sources[item] for item in native.get("source_ids", []) if item in sources]
    source = "; ".join(
        f"{item.get('publisher', '')}: {item.get('original_title', '')}".strip(": ")
        for item in selected
    )
    reasoning = str(native.get("explicit_default_reason") or "").strip() or None
    if not source:
        source = reasoning or "Installed registry default"
    dates = sorted(
        str(item["publication_date"]) for item in selected if item.get("publication_date")
    )
    low = float(native.get("uncertainty_low", 0))
    high = float(native.get("uncertainty_high", 1))
    return _default_evidence(
        source=source,
        version=version,
        source_date=dates[-1] if dates else None,
        uncertainty=max(high, 1 - low),
        reasoning=reasoning,
    ).model_copy(update={"source_ids": tuple(native.get("source_ids", ()))})


def _runtime_rule_name(rule: dict[str, Any], index: int) -> str:
    conditions = rule.get("conditions", [])
    if not conditions:
        return f"Runtime rule {index + 1}"
    return " and ".join(
        f"{item.get('input', 'input')} {item.get('operator', 'eq')} {item.get('value', '')}"
        for item in conditions
    )


def _duration_hours(duration: dict[str, Any]) -> tuple[float, float, float]:
    if "duration_min_hours" in duration:
        return (
            float(duration["duration_min_hours"]),
            float(duration["duration_median_hours"]),
            float(duration["duration_max_hours"]),
        )
    return (
        float(duration["minimum_minutes"]) / 60,
        float(duration["typical_minutes"]) / 60,
        float(duration["maximum_minutes"]) / 60,
    )


def _initial_state_values(payload: dict[str, Any]) -> dict[str, float]:
    agents = payload.get("initial_population", {}).get("population", {}).get("agents", [])
    values: dict[str, list[float]] = {}
    for agent in agents:
        for state_id, raw_value in agent.get("states", {}).items():
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                values.setdefault(state_id, []).append(value)
    return {state_id: fmean(items) for state_id, items in values.items() if items}


def _state_rates(rule: dict[str, Any], maximum: float) -> tuple[float, float]:
    intercept = float(rule.get("intercept", 0))
    coefficient = float(rule.get("coefficients", {}).get(rule.get("target_state_id"), 0))
    recovery = max(0.0, intercept / maximum) if maximum > 0 else 0.0
    decay = max(0.0, -coefficient - recovery)
    return decay, recovery


def _coefficient_sets(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    defaults = payload.get("coefficient_registry", {}).get("defaults", [])
    selected: dict[str, dict[str, Any]] = {}
    for item in defaults:
        action_id = str(item.get("action_id", ""))
        if action_id and (
            action_id not in selected or item.get("place", {}).get("level") == "global"
        ):
            selected[action_id] = item
    return selected


class InstalledRegistryDslAdapter:
    def __init__(self, store: SimulationRegistryStore, tick_hours: float = 1.0):
        self.store = store
        self.tick_hours = tick_hours

    def document(self) -> EditableDslDocument:
        payload = self.store.payload_snapshot()
        receipt = self.store.default_dsl_receipt()
        version = receipt.version if receipt is not None else "installed-registry"
        return EditableDslDocument(
            schema_version="2",
            version=version,
            tick_hours=float(payload.get("editable_dsl_tick_hours", self.tick_hours)),
            actions=self._actions(payload, version),
            states=self._states(payload),
            trees=self._trees(payload, version),
        )

    def required_root_module_ids(self) -> tuple[str, ...]:
        return tuple(sorted(tree.root_module_id for tree in self.store.decision_trees().trees))

    def _actions(
        self,
        payload: dict[str, Any],
        version: str,
    ) -> tuple[EditableDslAction, ...]:
        sources = {str(item["id"]): item for item in payload.get("default_sources", [])}
        aggregate_ids = {
            str(item["action_id"]): str(item["statistic_id"])
            for item in payload.get("aggregate_statistics", {}).get("action_contributions", [])
        }
        result = []
        for action in payload.get("default_actions", []):
            duration = action["duration"]
            minimum_hours, median_hours, maximum_hours = _duration_hours(duration)
            probability_evidence = _action_evidence(action, sources, version)
            duration_evidence = _action_evidence(
                {"evidence": duration.get("evidence", action.get("evidence", {}))},
                sources,
                version,
            )
            coefficients = tuple(
                EditableDslCoefficient(
                    id=f"runtime_rule_{index + 1}",
                    name=_runtime_rule_name(rule, index),
                    value=float(rule["probability"]),
                    evidence=_action_evidence(
                        {"evidence": rule.get("evidence") or action.get("evidence", {})},
                        sources,
                        version,
                    ),
                )
                for index, rule in enumerate(action.get("runtime_rules", []))
            )
            result.append(
                EditableDslAction(
                    id=str(action["id"]),
                    name=str(action["name"]),
                    description=str(action.get("description", "")),
                    category=str(action.get("category", "other")),
                    mode="passive" if action.get("passive") else "primary",
                    priority=int(action.get("priority", 0)),
                    aggregate_statistic_id=aggregate_ids.get(str(action["id"]), str(action["id"])),
                    interruptibility=str(
                        action.get(
                            "interruptibility",
                            "protected" if action.get("protected") else "interruptible",
                        )
                    ),
                    interruption_outcome=str(action.get("interruption_outcome", "defer")),
                    emergency_interruptions=tuple(
                        str(item) for item in action.get("emergency_interruptions", [])
                    ),
                    duration=EditableDslDuration(
                        min_hours=minimum_hours,
                        median_hours=median_hours,
                        max_hours=maximum_hours,
                        shape=duration["shape"],
                        shape_parameters=dict(duration.get("shape_parameters", {})),
                        evidence=duration_evidence,
                    ),
                    evidence=probability_evidence,
                    formula=str(action["formula"]),
                    coefficients=coefficients,
                    place_requirements=tuple(action.get("place_requirements", [])),
                    time_requirements=tuple(action.get("time_requirements", [])),
                )
            )
        return tuple(result)

    def _states(self, payload: dict[str, Any]) -> tuple[EditableDslState, ...]:
        catalog = payload.get("agent_states", {})
        rules = {str(item["target_state_id"]): item for item in catalog.get("runtime_rules", [])}
        initial_values = _initial_state_values(payload)
        result = []
        for definition in catalog.get("definitions", []):
            state_id = str(definition["id"])
            value_range = definition["value_range"]
            minimum = float(value_range["minimum"])
            maximum = float(value_range["maximum"])
            rule = rules.get(state_id, {})
            decay, recovery = _state_rates(rule, maximum)
            result.append(
                EditableDslState(
                    id=state_id,
                    name=str(definition["name"]),
                    min=minimum,
                    max=maximum,
                    initial=float(initial_values.get(state_id, minimum)),
                    decay_per_hour=decay,
                    recovery_per_hour=recovery,
                    thresholds=(),
                )
            )
        return tuple(result)

    def _trees(
        self,
        payload: dict[str, Any],
        version: str,
    ) -> tuple[EditableDslTree, ...]:
        registry = payload.get("decision_trees", {})
        action_ids = {str(item["id"]) for item in payload.get("default_actions", [])}
        coefficient_sets = _coefficient_sets(payload)
        result = []
        for module in registry.get("modules", []):
            coefficients = coefficient_sets.get(str(module["id"]), {}).get("coefficients", {})
            outgoing_counts: dict[str, int] = {}
            for edge in module.get("edges", []):
                source = str(edge["from_node"])
                outgoing_counts[source] = outgoing_counts.get(source, 0) + 1
            edges = []
            for edge in module.get("edges", []):
                edge_id = str(edge["id"])
                if edge.get("probability") is not None:
                    probability = float(edge["probability"])
                elif edge_id in coefficients:
                    probability = float(coefficients[edge_id])
                elif outgoing_counts[str(edge["from_node"])] == 1:
                    probability = 1.0
                else:
                    raise ValueError(
                        f"Decision module {module['id']} edge {edge_id} has no "
                        "executable coefficient"
                    )
                edges.append(
                    EditableDslTreeEdge(
                        id=edge_id,
                        from_node=str(edge["from_node"]),
                        to_node=str(edge["to_node"]),
                        probability=probability,
                        formula=edge.get("formula") or f"coefficient({edge_id})",
                        condition=str(edge.get("condition") or "always"),
                        place_requirements=tuple(edge.get("place_requirements", ())),
                        time_requirements=tuple(edge.get("time_requirements", ())),
                    )
                )
            nodes = []
            for node in module.get("nodes", []):
                node_id = str(node["id"])
                native_kind = str(node["kind"])
                if node_id == module["entry_node"]:
                    kind = "entry"
                elif native_kind == "module_reference":
                    kind = "module"
                else:
                    kind = native_kind
                action_id = node.get("action_id") or (
                    node_id if kind == "action" and node_id in action_ids else None
                )
                nodes.append(
                    EditableDslTreeNode(
                        id=node_id,
                        label=str(node["label"]),
                        kind=kind,
                        action_id=action_id,
                        target_tree_id=node.get("target_module_id"),
                    )
                )
            result.append(
                EditableDslTree(
                    id=str(module["id"]),
                    name=str(module["name"]),
                    entry_node=str(module["entry_node"]),
                    nodes=tuple(nodes),
                    edges=tuple(edges),
                )
            )
        return tuple(result)


class RefreshingEditableDslRegistry(SimulationRegistryStore):
    def __init__(self, path: str | Path, refresh: Callable[[], None]):
        self._registry_path = Path(path)
        self._refresh_callback = refresh
        self._refreshing = False
        super().__init__(self._registry_path)

    @property
    def path(self) -> Path:
        if not self._refreshing:
            self._refreshing = True
            try:
                self._refresh_callback()
            finally:
                self._refreshing = False
        return self._registry_path

    @path.setter
    def path(self, value: str | Path) -> None:
        self._registry_path = Path(value)


def _native_default_evidence(evidence: EditableDslEvidence) -> dict[str, Any]:
    return {
        "status": "default_estimated",
        "explicit_default_reason": evidence.reasoning or evidence.source,
        "uncertainty_low": 0.0,
        "uncertainty_high": evidence.uncertainty,
        "source_ids": list(evidence.source_ids),
        "editable_provenance": evidence.model_dump(mode="json"),
    }


def _native_state_evidence(revision: EditableDslRevision) -> dict[str, Any]:
    return {
        "status": "default_estimated",
        "source": "Human-confirmed visual DSL edit",
        "source_version": revision.version,
        "source_date": revision.accepted_at[:10] if revision.accepted_at else None,
        "url": None,
        "place": "Global editable DSL",
        "population": "Agents using this confirmed DSL revision",
        "language": "en",
        "original_title": "Petraterrium visual DSL revision",
        "english_title": "Petraterrium visual DSL revision",
        "search_source": "Visual DSL Builder",
        "uncertainty": 1.0,
        "default_reason": "Human-confirmed structural DSL edit",
    }


class EditableDslRegistryOverlay(SimulationRegistryStore):
    def __init__(
        self,
        store: SimulationRegistryStore,
        revision: EditableDslRevision,
        path=None,
    ):
        self.source_store = store
        self.revision = revision
        payload = store.payload_snapshot()
        baseline = InstalledRegistryDslAdapter(store).document()
        payload["editable_dsl"] = self.revision.model_dump(mode="json")
        payload["editable_dsl_tick_hours"] = self.revision.document.tick_hours
        self._apply_actions(payload, baseline)
        self._apply_states(payload, baseline)
        self._apply_trees(payload, baseline)
        self._apply_identity(payload)
        destination = path or store.path.with_name(
            f".{store.path.stem}.editable-{revision.document_hash[-12:]}.json"
        )
        super().__init__(destination)
        with self._lock:
            self._write(payload)

    def editable_dsl_receipt(self) -> DefaultDslReceipt:
        current = self.source_store.default_dsl_receipt()
        sections = (
            current.managed_sections
            if current is not None
            else (
                "default_actions",
                "agent_states",
                "decision_trees",
            )
        )
        return DefaultDslReceipt(
            version=self.revision.version,
            hash=self.revision.document_hash,
            managed_sections=sections,
        )

    def _apply_actions(self, payload: dict[str, Any], baseline: EditableDslDocument) -> None:
        native_by_id = {
            str(item["id"]): deepcopy(item) for item in payload.get("default_actions", [])
        }
        state_ids = {state.id for state in self.revision.document.states}
        baseline_by_id = {action.id: action for action in baseline.actions}
        result = []
        for action in self.revision.document.actions:
            before = baseline_by_id.get(action.id)
            native = native_by_id.get(action.id)
            if native is None:
                runtime_rules = []
                if action.coefficients:
                    runtime_rules.append(
                        {"conditions": [], "probability": action.coefficients[0].value}
                    )
                native = {
                    "id": action.id,
                    "name": action.name,
                    "description": action.description or action.name,
                    "duration": {},
                    "formula": action.formula,
                    "conditions": [],
                    "place_requirements": list(action.place_requirements),
                    "time_requirements": list(action.time_requirements),
                    "state_inputs": [
                        item.id for item in action.coefficients if item.id in state_ids
                    ],
                    "outcomes": [],
                    "evidence": _native_default_evidence(
                        action.evidence
                        or _default_evidence(
                            "Human-confirmed action probability",
                            self.revision.version,
                            1.0,
                            reasoning=(
                                "The user confirmed an explicit action probability formula; "
                                "duration evidence is separate."
                            ),
                        )
                    ),
                    "exclusive_choice_group": None,
                    "runtime_rules": runtime_rules,
                    "cash_flow": {},
                }
            native["name"] = action.name
            native["description"] = action.description or action.name
            native["category"] = action.category
            native["priority"] = action.priority
            native["passive"] = action.mode == "passive"
            native["interruptibility"] = action.interruptibility
            native["interruption_outcome"] = action.interruption_outcome
            native["emergency_interruptions"] = list(action.emergency_interruptions)
            previous_duration_evidence = native.get("duration", {}).get(
                "evidence", native.get("evidence")
            )
            native["duration"] = {
                "duration_min_hours": action.duration.min_hours,
                "duration_median_hours": action.duration.median_hours,
                "duration_max_hours": action.duration.max_hours,
                "shape": action.duration.shape,
                "shape_parameters": action.duration.shape_parameters,
                "evidence": previous_duration_evidence
                if before is not None and before.duration.evidence == action.duration.evidence
                else _native_default_evidence(action.duration.evidence),
            }
            if before is not None and (
                before.duration.min_hours != action.duration.min_hours
                or before.duration.median_hours != action.duration.median_hours
                or before.duration.max_hours != action.duration.max_hours
                or before.duration.shape != action.duration.shape
                or before.duration.shape_parameters != action.duration.shape_parameters
            ):
                native["duration_resolutions"] = []
            if action.evidence is not None and (
                before is None or before.evidence != action.evidence
            ):
                native["evidence"] = _native_default_evidence(action.evidence)
            native["formula"] = action.formula
            native["place_requirements"] = list(action.place_requirements)
            native["time_requirements"] = list(action.time_requirements)
            for index, coefficient in enumerate(action.coefficients):
                if index < len(native.get("runtime_rules", [])):
                    native["runtime_rules"][index]["probability"] = coefficient.value
                    if (
                        before is None
                        or index >= len(before.coefficients)
                        or before.coefficients[index].evidence != coefficient.evidence
                    ):
                        native["runtime_rules"][index]["evidence"] = _native_default_evidence(
                            coefficient.evidence
                        )
            formula_changed = before is None or action.formula != before.formula
            constraints_changed = (
                before is None
                or action.place_requirements != before.place_requirements
                or action.time_requirements != before.time_requirements
            )
            if formula_changed:
                probability = probability_value(
                    action.formula, {item.id: item.value for item in action.coefficients}
                )
                if native.get("runtime_rules"):
                    for rule in native["runtime_rules"]:
                        rule["probability"] = probability
                else:
                    native["runtime_rules"] = [{"conditions": [], "probability": probability}]
            if constraints_changed:
                constraints = [
                    condition
                    for expression in (*action.place_requirements, *action.time_requirements)
                    for condition in runtime_conditions(expression, self.revision.document)
                ]
                for rule in native.get("runtime_rules", []):
                    rule["conditions"].extend(constraints)
            result.append(native)
        payload["default_actions"] = result
        aggregate_program = deepcopy(payload.get("aggregate_statistics", {}))
        existing_contributions = {
            str(item["action_id"]): item
            for item in aggregate_program.get("action_contributions", [])
        }
        aggregate_program["action_contributions"] = [
            {
                **deepcopy(
                    existing_contributions.get(
                        action.id,
                        {
                            "action_id": action.id,
                            "event_source": "events",
                            "label_field": "action",
                            "agent_index_field": "agent_index",
                            "agent_indices_field": None,
                        },
                    )
                ),
                "action_id": action.id,
                "statistic_id": action.aggregate_statistic_id,
            }
            for action in self.revision.document.actions
        ]
        payload["aggregate_statistics"] = aggregate_program

    def _apply_states(
        self,
        payload: dict[str, Any],
        baseline: EditableDslDocument,
    ) -> None:
        catalog = deepcopy(payload.get("agent_states", {}))
        definitions = {str(item["id"]): item for item in catalog.get("definitions", [])}
        rules = {str(item["target_state_id"]): item for item in catalog.get("runtime_rules", [])}
        baseline_states = {state.id: state for state in baseline.states}
        evidence = _native_state_evidence(self.revision)
        updated_definitions = []
        updated_rules = []
        changed_initials: dict[str, float] = {}
        for state in self.revision.document.states:
            definition = definitions.get(state.id)
            if definition is None:
                definition = {
                    "id": state.id,
                    "name": state.name,
                    "group": "slow_trait",
                    "description": f"Editable numeric state {state.name}.",
                    "value_range": {"minimum": state.min, "maximum": state.max, "unit": "index"},
                    "initial_feature_ids": [],
                    "initial_evidence": evidence,
                    "event_effects": [],
                    "recovery": {
                        "mode": "stable",
                        "parameter_id": None,
                        "formula": f"{state.id}[t+1] = {state.id}[t] + event_delta",
                        "evidence": evidence,
                    },
                    "decision_modifiers": [],
                    "propagation": [],
                }
            definition["name"] = state.name
            definition["value_range"]["minimum"] = state.min
            definition["value_range"]["maximum"] = state.max
            updated_definitions.append(definition)
            rule = rules.get(state.id)
            if rule is None:
                rule = {
                    "target_state_id": state.id,
                    "intercept": 0.0,
                    "coefficients": {},
                    "minimum": state.min,
                    "maximum": state.max,
                    "formula": (
                        f"{state.id}[t+1] = clamp({state.id}[t] + event_delta, "
                        f"{state.min}, {state.max})"
                    ),
                    "evidence": evidence,
                }
            rule["minimum"] = state.min
            rule["maximum"] = state.max
            before = baseline_states.get(state.id)
            if before is None or (
                before.decay_per_hour != state.decay_per_hour
                or before.recovery_per_hour != state.recovery_per_hour
            ):
                rule["intercept"] = state.recovery_per_hour * state.max
                rule["coefficients"][state.id] = -(state.decay_per_hour + state.recovery_per_hour)
                rule["formula"] = (
                    f"{state.id}[t+1] = clamp({state.id}[t] + "
                    f"{state.recovery_per_hour} * {state.max} - "
                    f"{state.decay_per_hour + state.recovery_per_hour} * "
                    f"{state.id}[t] + event_delta, {state.min}, {state.max})"
                )
                rule["evidence"] = evidence
            updated_rules.append(rule)
            if before is None or before.initial != state.initial:
                changed_initials[state.id] = state.initial
        catalog["version"] = self.revision.version
        catalog["status"] = "confirmed"
        catalog["definitions"] = updated_definitions
        catalog["runtime_rules"] = updated_rules
        payload["agent_states"] = catalog
        for agent in payload.get("initial_population", {}).get("population", {}).get("agents", []):
            states = agent.setdefault("states", {})
            for state_id, initial in changed_initials.items():
                states[state_id] = str(initial)

    def _apply_trees(self, payload: dict[str, Any], baseline: EditableDslDocument) -> None:
        registry = deepcopy(payload.get("decision_trees", {}))
        baseline_trees = {tree.id: tree for tree in baseline.trees}
        unchanged_tree_ids = {
            tree.id for tree in self.revision.document.trees if baseline_trees.get(tree.id) == tree
        }
        native_modules = {str(item["id"]): item for item in registry.get("modules", [])}
        updated_modules = []
        for tree in self.revision.document.trees:
            native = native_modules.get(tree.id, {})
            if tree.id in unchanged_tree_ids:
                updated_modules.append(native)
                continue
            existing_nodes = {str(item["id"]): item for item in native.get("nodes", [])}
            existing_edges = {str(item["id"]): item for item in native.get("edges", [])}
            nodes = []
            for node in tree.nodes:
                previous = existing_nodes.get(node.id, {})
                native_kind = {
                    "entry": "decision",
                    "decision": "decision",
                    "action": "action",
                    "terminal": "terminal",
                    "module": "module_reference",
                }[node.kind]
                nodes.append(
                    {
                        "id": node.id,
                        "label": node.label,
                        "kind": native_kind,
                        "description": previous.get("description", ""),
                        "target_module_id": (
                            node.target_tree_id if node.kind == "module" else None
                        ),
                        "action_id": node.action_id,
                    }
                )
            edges = []
            for edge in tree.edges:
                previous = existing_edges.get(edge.id, {})
                conditions = [
                    condition
                    for expression in (
                        edge.condition,
                        *edge.place_requirements,
                        *edge.time_requirements,
                    )
                    for condition in runtime_conditions(expression, self.revision.document)
                ]
                probability = probability_value(
                    edge.formula, {item.id: item.probability for item in tree.edges}
                )
                edges.append(
                    {
                        "id": edge.id,
                        "from_node": edge.from_node,
                        "to_node": edge.to_node,
                        "label": previous.get("label", edge.id),
                        "condition": "" if edge.condition == "always" else edge.condition,
                        "decision_id": previous.get("decision_id"),
                        "evidence_edge_id": previous.get("evidence_edge_id"),
                        "formula": edge.formula,
                        "probability": edge.probability,
                        "place_requirements": list(edge.place_requirements),
                        "time_requirements": list(edge.time_requirements),
                        "runtime_rules": [{"conditions": conditions, "probability": probability}],
                    }
                )
            updated_modules.append(
                {
                    "id": tree.id,
                    "version": self.revision.version,
                    "name": tree.name,
                    "description": native.get("description", ""),
                    "entry_node": tree.entry_node,
                    "nodes": nodes,
                    "edges": edges,
                    "source": f"Human-confirmed editable DSL {self.revision.document_hash}",
                    "status": "ready",
                    "proposal_audit": native.get("proposal_audit"),
                }
            )
        registry["version"] = self.revision.version
        registry["modules"] = updated_modules
        payload["decision_trees"] = registry
        coefficients = deepcopy(payload.get("coefficient_registry", {}))
        defaults = {str(item["action_id"]): item for item in coefficients.get("defaults", [])}
        changed_tree_ids = {tree.id for tree in self.revision.document.trees} - unchanged_tree_ids
        updated_defaults = [
            deepcopy(item)
            for item in coefficients.get("defaults", [])
            if item["action_id"] not in changed_tree_ids
        ]
        for tree in self.revision.document.trees:
            if tree.id in unchanged_tree_ids:
                continue
            coefficient_set = defaults.get(tree.id)
            if coefficient_set is None:
                coefficient_set = {
                    "id": f"{tree.id}_global_editable_default",
                    "action_id": tree.id,
                    "place": {
                        "level": "global",
                        "place_id": "global",
                        "region_id": None,
                        "country_id": None,
                        "city_id": None,
                    },
                    "coefficients": {},
                    "intervals": {},
                    "source": {},
                }
            coefficient_set["coefficients"] = {edge.id: edge.probability for edge in tree.edges}
            coefficient_set["outgoing_groups"] = {
                node.id: [edge.id for edge in tree.edges if edge.from_node == node.id]
                for node in tree.nodes
                if any(edge.from_node == node.id for edge in tree.edges)
            }
            coefficient_set["intervals"] = {
                edge.id: coefficient_set.get("intervals", {}).get(
                    edge.id, {"low": 0.0, "high": 1.0}
                )
                for edge in tree.edges
            }
            coefficient_set["source"] = {
                "kind": "shipped_default_reason",
                "default_dsl_version": self.revision.version,
                "default_dsl_hash": self.revision.document_hash,
                "reason": (
                    "Human-confirmed editable DSL transition probability with "
                    "retained uncertainty interval."
                ),
            }
            updated_defaults.append(coefficient_set)
        coefficients["version"] = self.revision.version
        for coefficient_set in updated_defaults:
            source = coefficient_set.get("source", {})
            if source.get("kind") == "shipped_default_reason":
                source["default_dsl_version"] = self.revision.version
                source["default_dsl_hash"] = self.revision.document_hash
        coefficients["defaults"] = updated_defaults
        coefficients["fitted"] = [
            item
            for item in coefficients.get("fitted", [])
            if item["action_id"] not in changed_tree_ids
        ]
        payload["coefficient_registry"] = coefficients

    def _apply_identity(self, payload: dict[str, Any]) -> None:
        receipt = self.editable_dsl_receipt()
        payload["default_dsl"] = receipt.model_dump(mode="json")
