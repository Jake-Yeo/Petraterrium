import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from itertools import product
from typing import Any

from ..population import AgentRecord
from .coefficient_evidence import (
    ActionCoefficientRegistry,
    CoefficientPlace,
    DefaultDslEvidenceIdentity,
    ResolvedActionCoefficients,
    resolve_action_coefficients,
)
from .decision_evidence import (
    AgentDecisionContext,
    AgentPlace,
    DecisionEdgeTemplate,
    DecisionFactorEvidence,
    DecisionTreeTemplate,
    EvaluatedDecisionProbability,
    EvidencePredicate,
    ProbabilityFactor,
    ResearchCitation,
    Scalar,
    evaluate_decision_edge,
)
from .registry_store import DecisionEvidenceRegistryDefinition
from .run_warnings import RunCoefficientReceipt
from .tree_modules import (
    DecisionTreeDefinition,
    DecisionTreeModule,
    DecisionTreeRegistryDefinition,
)

EXECUTABLE_EVIDENCE_BASES = {"measured_joint", "fitted_model"}
RUNTIME_PROGRAM_VERSION = "generic-dsl-runtime-v1"
WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
MAX_RUNTIME_EVIDENCE_PROFILES = 4096
MAX_UNCOVERED_AGENT_PREVIEW = 5


class RuntimeDecisionCompilationError(ValueError):
    pass


@dataclass(frozen=True)
class RuntimeDecisionCompilation:
    modules: list[dict[str, Any]]
    routes: list[dict[str, str]]
    agent_modules: list[str]
    agent_states: list[str]
    module_ids_by_agent: list[tuple[str, ...]]
    tree_ids_by_agent: list[tuple[str, ...]]
    runtime_module_by_source_module_by_agent: list[dict[str, str]]
    coefficient_receipts: list[RunCoefficientReceipt]


def _text_trait(agent: AgentRecord, name: str) -> str:
    value = agent.traits.get(name)
    return str(value).strip() if value is not None else ""


def _agent_types(agent: AgentRecord) -> set[str]:
    values = agent.traits.get("agent_types")
    if isinstance(values, list):
        return {str(value).strip() for value in values if str(value).strip()}
    value = _text_trait(agent, "agent_type")
    return {value or agent.role}


def _primary_agent_type(agent: AgentRecord) -> str:
    value = _text_trait(agent, "agent_type")
    if value:
        return value
    values = agent.traits.get("agent_types")
    if isinstance(values, list):
        first = next((str(item).strip() for item in values if str(item).strip()), None)
        if first:
            return first
    return agent.role


def _runtime_identifier(prefix: str, value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", value.casefold()).strip("-")
    digest = hashlib.sha256(value.encode()).hexdigest()[:12]
    return f"{prefix}-{normalized or 'unknown'}-{digest}"


def _idle_module(module_id: str) -> dict[str, Any]:
    return {
        "id": module_id,
        "entry_state": "idle",
        "exit_states": ["idle"],
        "inputs": [],
        "outputs": [],
        "states": ["idle"],
        "transitions": [],
    }


def _scalar_mapping(value: Any) -> dict[str, Scalar]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if isinstance(item, str | int | float | bool)
        and not isinstance(item, complex)
        and (not isinstance(item, float) or math.isfinite(item))
    }


def _scalar_traits(agent: AgentRecord) -> dict[str, Scalar]:
    return {
        name: value
        for name, value in agent.traits.items()
        if isinstance(value, str | int | float | bool)
        and not isinstance(value, complex)
        and (not isinstance(value, float) or math.isfinite(value))
    }


def _agent_context(agent: AgentRecord, start_date: date) -> AgentDecisionContext:
    region = _text_trait(agent, "region") or "unknown-region"
    country = (
        _text_trait(agent, "country_id")
        or agent.place.strip()
        or _text_trait(agent, "country")
        or "unknown-country"
    )
    city = _text_trait(agent, "city_id") or _text_trait(agent, "city") or None
    explicit_time = _scalar_mapping(agent.traits.get("time"))
    explicit_context = _scalar_mapping(agent.traits.get("context"))
    context = {
        name: value
        for name, value in agent.states.items()
        if isinstance(value, str | int | float | bool)
    }
    context.update(explicit_context)
    time = {
        "weekday": start_date.strftime("%A").casefold(),
        "hour": 0,
        **explicit_time,
    }
    return AgentDecisionContext(
        agent_id=agent.agent_id,
        place=AgentPlace(region_id=region, country_id=country, city_id=city),
        traits=_scalar_traits(agent),
        place_attributes=_scalar_mapping(agent.traits.get("place_attributes")),
        time=time,
        context=context,
    )


def _agent_coefficient_place(agent: AgentRecord) -> CoefficientPlace:
    region = _text_trait(agent, "region") or "unknown-region"
    country = (
        _text_trait(agent, "country_id")
        or agent.place.strip()
        or _text_trait(agent, "country")
        or "unknown-country"
    )
    city = _text_trait(agent, "city_id") or _text_trait(agent, "city") or None
    if city is not None:
        return CoefficientPlace(
            level="city",
            place_id=city,
            region_id=region,
            country_id=country,
            city_id=city,
        )
    return CoefficientPlace(
        level="country",
        place_id=country,
        region_id=region,
        country_id=country,
    )


def _place_candidates(agent: AgentRecord) -> set[str]:
    return {
        value.casefold()
        for value in (
            agent.place,
            _text_trait(agent, "country_id"),
            _text_trait(agent, "country"),
            _text_trait(agent, "region"),
            _text_trait(agent, "city_id"),
            _text_trait(agent, "city"),
        )
        if value
    }


def _tree_applies(tree: DecisionTreeDefinition, agent: AgentRecord) -> bool:
    type_match = not tree.agent_type_ids or bool(
        _agent_types(agent).intersection(tree.agent_type_ids)
    )
    selected_places = {value.casefold() for value in tree.place_ids}
    place_match = not selected_places or bool(
        selected_places.intersection(_place_candidates(agent))
    )
    return type_match and place_match


def _require_unique[T](items: list[T], identity, label: str) -> dict[str, T]:
    resolved: dict[str, T] = {}
    for item in items:
        item_id = identity(item)
        if item_id in resolved:
            raise RuntimeDecisionCompilationError(
                f"Confirmed decision registry contains duplicate {label} id {item_id!r}"
            )
        resolved[item_id] = item
    return resolved


def _validate_topology(
    tree_id: str,
    module: DecisionTreeModule,
    template: DecisionTreeTemplate,
    evidence_edge_ids: Mapping[str, str],
) -> None:
    if module.status != "ready":
        raise RuntimeDecisionCompilationError(
            f"Confirmed decision tree {tree_id!r} has non-ready module {module.id!r}"
        )
    conditioned_edges = [edge.id for edge in module.edges if edge.condition.strip()]
    if conditioned_edges:
        raise RuntimeDecisionCompilationError(
            f"Confirmed decision module {module.id!r} has non-executable free-text "
            f"conditions on edges: {', '.join(conditioned_edges)}; use typed evidence "
            "predicates"
        )
    outgoing_nodes = {edge.from_node for edge in module.edges}
    routed_nodes = {node.id for node in module.nodes if node.kind == "module_reference"}
    invalid_routes = sorted(routed_nodes.intersection(outgoing_nodes))
    if invalid_routes:
        raise RuntimeDecisionCompilationError(
            f"Confirmed decision module {module.id!r} routes from module reference nodes: "
            f"{', '.join(invalid_routes)}"
        )
    template_nodes = {node.id for node in template.nodes}
    module_nodes = {node.id for node in module.nodes}
    if template.entry_state != module.entry_node or template_nodes != module_nodes:
        raise RuntimeDecisionCompilationError(
            f"Confirmed decision module {module.id!r} does not match its executable evidence "
            "template nodes and entry state"
        )
    template_edges = {edge.id: (edge.from_state, edge.to_state) for edge in template.edges}
    for edge in module.edges:
        evidence_edge_id = evidence_edge_ids[edge.id]
        if template_edges.get(evidence_edge_id) != (edge.from_node, edge.to_node):
            raise RuntimeDecisionCompilationError(
                f"Confirmed decision module {module.id!r} edge {edge.id!r} does not "
                f"match executable evidence edge {evidence_edge_id!r}"
            )
    if set(evidence_edge_ids.values()) != set(template_edges):
        raise RuntimeDecisionCompilationError(
            f"Confirmed decision module {module.id!r} does not map every executable "
            "evidence edge exactly once"
        )
    module_terminals = {
        node.id for node in module.nodes if node.kind in {"terminal", "module_reference"}
    }
    if set(template.terminal_states) != module_terminals:
        raise RuntimeDecisionCompilationError(
            f"Confirmed decision module {module.id!r} does not match its executable "
            "terminal and module-reference states"
        )


def _module_evidence_binding(
    tree_id: str,
    module: DecisionTreeModule,
    root_trees_by_module: Mapping[str, list[DecisionTreeDefinition]],
    templates_by_id: Mapping[str, DecisionTreeTemplate],
) -> tuple[DecisionTreeTemplate, dict[str, str]]:
    explicit_edges = [edge for edge in module.edges if edge.decision_id is not None]
    if explicit_edges and len(explicit_edges) != len(module.edges):
        raise RuntimeDecisionCompilationError(
            f"Confirmed decision module {module.id!r} mixes explicit and implicit evidence mappings"
        )
    if explicit_edges:
        decision_ids = {edge.decision_id for edge in explicit_edges}
        if len(decision_ids) != 1:
            raise RuntimeDecisionCompilationError(
                f"Confirmed decision module {module.id!r} maps to multiple evidence "
                "templates; split it into focused modules"
            )
        template_id = next(iter(decision_ids))
        evidence_edge_ids = {
            edge.id: edge.evidence_edge_id
            for edge in explicit_edges
            if edge.evidence_edge_id is not None
        }
    else:
        root_trees = root_trees_by_module.get(module.id, [])
        matching_template_ids = [
            tree.id
            for tree in root_trees
            if tree.id in templates_by_id and templates_by_id[tree.id].status == "ready"
        ]
        if len(matching_template_ids) != 1:
            raise RuntimeDecisionCompilationError(
                f"Confirmed decision module {module.id!r} has no unique ready executable "
                "evidence template and no explicit edge mappings"
            )
        template_id = matching_template_ids[0]
        evidence_edge_ids = {edge.id: edge.id for edge in module.edges}
    template = templates_by_id.get(template_id)
    if template is None or template.status != "ready":
        raise RuntimeDecisionCompilationError(
            f"Confirmed decision module {module.id!r} maps to evidence template "
            f"{template_id!r}, which is missing or not ready"
        )
    _validate_topology(tree_id, module, template, evidence_edge_ids)
    return template, evidence_edge_ids


def _reachable_modules(
    tree: DecisionTreeDefinition,
    modules_by_id: Mapping[str, DecisionTreeModule],
) -> list[DecisionTreeModule]:
    ordered: list[DecisionTreeModule] = []
    visited: set[str] = set()
    active: list[str] = []

    def visit(module_id: str) -> None:
        if module_id in active:
            cycle = [*active[active.index(module_id) :], module_id]
            raise RuntimeDecisionCompilationError(
                f"Confirmed decision tree {tree.id!r} has a module reference cycle: "
                + " -> ".join(cycle)
            )
        if module_id in visited:
            return
        module = modules_by_id.get(module_id)
        if module is None:
            raise RuntimeDecisionCompilationError(
                f"Confirmed decision tree {tree.id!r} references missing module {module_id!r}"
            )
        if module.status != "ready":
            raise RuntimeDecisionCompilationError(
                f"Confirmed decision tree {tree.id!r} has non-ready module {module.id!r}"
            )
        active.append(module_id)
        ordered.append(module)
        for node in module.nodes:
            if node.kind == "module_reference" and node.target_module_id is not None:
                visit(node.target_module_id)
        active.pop()
        visited.add(module_id)

    visit(tree.root_module_id)
    return ordered


def _citation_label(citation: ResearchCitation) -> str:
    return f"{citation.source}: {citation.title} [{citation.link_or_reference}]"


def _provenance(
    registry_version: str,
    result: EvaluatedDecisionProbability,
) -> dict[str, Any]:
    citations = [result.source]
    citations.extend(factor.source for factor in result.factors)
    research = [citation for citation in citations if isinstance(citation, ResearchCitation)]
    unique = {
        (
            citation.imported_source_id,
            citation.title,
            citation.link_or_reference,
        ): citation
        for citation in research
    }
    ordered = [unique[key] for key in sorted(unique)]
    evidence_ids = sorted(
        factor.evidence_id for factor in result.factors if factor.evidence_id is not None
    )
    evidence_kinds = sorted(
        {factor.evidence_basis for factor in result.factors if factor.evidence_basis is not None}
    )
    resolution_statuses = {
        factor.resolution_status
        for factor in result.factors
        if factor.resolution_status is not None
    }
    inherited = "inherited" in resolution_statuses
    source_places = sorted(
        {
            f"{factor.evidence_place.level}:{factor.evidence_place.place_id}"
            for factor in result.factors
            if factor.evidence_place is not None
        }
    )
    source_dates = sorted({citation.publication_date.isoformat() for citation in ordered})
    probability = result.probability
    if probability is None:
        raise RuntimeDecisionCompilationError(
            f"Decision edge {result.edge_id!r} has no executable probability"
        )
    uncertainty = max(probability - result.ci_low, result.ci_high - probability)
    return {
        "source": "; ".join(_citation_label(citation) for citation in ordered),
        "version": "|".join(
            [registry_version, *sorted(citation.imported_source_id for citation in ordered)]
        ),
        "status": "measured",
        "resolution_status": "inherited" if inherited else "direct",
        "source_places": source_places,
        "uncertainty": uncertainty,
        "source_date": ",".join(source_dates),
        "evidence_id": ",".join(evidence_ids),
        "evidence_kind": ",".join(evidence_kinds),
        "ci_low": result.ci_low,
        "ci_high": result.ci_high,
    }


def _factor_value(
    factor: ProbabilityFactor,
    context: AgentDecisionContext,
) -> Scalar | None:
    values = {
        "trait": context.traits,
        "place": context.place_attributes,
        "time": context.time,
        "context": context.context,
    }[factor.input_kind]
    return values.get(factor.input_key)


def _dynamic_factor(
    factor: ProbabilityFactor,
    runtime_context_keys: set[str],
) -> bool:
    if factor.input_kind == "time":
        if factor.input_key not in {"weekday", "hour"}:
            raise RuntimeDecisionCompilationError(
                f"Time evidence input {factor.input_key!r} has no Rust runtime binding"
            )
        return True
    if factor.input_kind == "place":
        return True
    if factor.input_kind == "context":
        if factor.input_key not in runtime_context_keys:
            raise RuntimeDecisionCompilationError(
                f"Context evidence input {factor.input_key!r} has no live numeric memory "
                "binding and cannot be frozen at compile time"
            )
        return True
    return False


def _evidence_place_matches(
    row: DecisionFactorEvidence,
    context: AgentDecisionContext,
) -> bool:
    place = row.place
    agent = context.place
    if place.level == "global":
        return place.place_id == "global"
    if place.level == "region":
        return place.place_id == agent.region_id
    if place.level == "country":
        return place.place_id == agent.country_id and place.region_id == agent.region_id
    return (
        agent.city_id is not None
        and place.place_id == agent.city_id
        and place.country_id == agent.country_id
        and place.region_id == agent.region_id
    )


def _factor_evidence_rows(
    edge: DecisionEdgeTemplate,
    factor: ProbabilityFactor,
    context: AgentDecisionContext,
    evidence: DecisionEvidenceRegistryDefinition,
) -> list[DecisionFactorEvidence]:
    return [
        row
        for row in evidence.evidence
        if row.decision_id == edge.decision_id
        and row.edge_id == edge.id
        and row.factor_id == factor.id
        and _evidence_place_matches(row, context)
    ]


def _predicate_values(
    predicate: EvidencePredicate,
    fallback: Scalar | None,
) -> list[Scalar]:
    if predicate.operator == "exact":
        return [predicate.value] if predicate.value is not None else []
    if predicate.operator == "one_of":
        return list(predicate.values)
    if predicate.operator == "between":
        if predicate.lower is None or predicate.upper is None:
            return []
        return [(predicate.lower + predicate.upper) / 2]
    if fallback is not None:
        return [fallback]
    return [0]


def _candidate_values(
    factor: ProbabilityFactor,
    rows: list[DecisionFactorEvidence],
    context: AgentDecisionContext,
) -> list[Scalar]:
    if factor.input_kind == "time" and factor.input_key == "weekday":
        predicate_values = [
            value for row in rows for value in _predicate_values(row.predicate, None)
        ]
        if any(isinstance(value, str) for value in predicate_values):
            return list(WEEKDAY_INDEX)
        return list(range(7))
    fallback = _factor_value(factor, context)
    values = {
        (type(value).__name__, json.dumps(value, sort_keys=True)): value
        for row in rows
        for value in _predicate_values(row.predicate, fallback)
    }
    if not values:
        fallback_value: Scalar = fallback if fallback is not None else 0
        values[
            (
                type(fallback_value).__name__,
                json.dumps(fallback_value, sort_keys=True),
            )
        ] = fallback_value
    return [values[key] for key in sorted(values)]


def _profile_context(
    context: AgentDecisionContext,
    profile: Mapping[tuple[str, str], Scalar],
) -> AgentDecisionContext:
    place_attributes = dict(context.place_attributes)
    time = dict(context.time)
    runtime_context = dict(context.context)
    for (input_kind, input_key), value in profile.items():
        if input_kind == "place":
            place_attributes[input_key] = value
        elif input_kind == "time":
            time[input_key] = value
        elif input_kind == "context":
            runtime_context[input_key] = value
    return context.model_copy(
        update={
            "place_attributes": place_attributes,
            "time": time,
            "context": runtime_context,
        }
    )


def _runtime_input(factor: ProbabilityFactor) -> str:
    if factor.input_kind == "time":
        return f"context.{factor.input_key}"
    if factor.input_kind == "context":
        return f"memory.{factor.input_key}"
    if factor.input_key == "kind":
        return "place.kind"
    if factor.input_key == "index":
        return "place.index"
    return f"place.{factor.input_key}"


def _numeric_condition(
    input_name: str,
    operator: str,
    value: Scalar,
) -> dict[str, Any]:
    if input_name == "context.weekday" and isinstance(value, str):
        weekday = WEEKDAY_INDEX.get(value.casefold())
        if weekday is None:
            raise RuntimeDecisionCompilationError(
                f"Weekday evidence predicate uses unknown value {value!r}"
            )
        value = weekday
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, str) and input_name != "place.kind":
        try:
            value = float(value)
        except ValueError as error:
            raise RuntimeDecisionCompilationError(
                f"Runtime input {input_name!r} requires numeric evidence predicates"
            ) from error
    if isinstance(value, int | float):
        numeric = float(value)
        if not math.isfinite(numeric):
            raise RuntimeDecisionCompilationError(
                f"Runtime condition {input_name!r} has a non-finite value"
            )
        return {"input": input_name, "operator": operator, "value": numeric}
    if input_name == "place.kind" and operator in {"eq", "ne"}:
        return {
            "input": input_name,
            "operator": operator,
            "value": 0,
            "categorical_value": str(value).strip().casefold(),
        }
    raise RuntimeDecisionCompilationError(
        f"Runtime input {input_name!r} requires numeric evidence predicates"
    )


def _predicate_conditions(
    factor: ProbabilityFactor,
    predicate: EvidencePredicate,
    evaluated_value: Scalar,
) -> list[dict[str, Any]]:
    input_name = _runtime_input(factor)
    if predicate.operator == "any":
        return []
    if predicate.operator in {"exact", "one_of"}:
        return [_numeric_condition(input_name, "eq", evaluated_value)]
    if predicate.lower is None or predicate.upper is None:
        raise RuntimeDecisionCompilationError(
            f"Evidence predicate for {factor.id!r} has no ordered numeric range"
        )
    return [
        _numeric_condition(input_name, "gte", predicate.lower),
        _numeric_condition(input_name, "lte", predicate.upper),
    ]


def _validated_result(
    template: DecisionTreeTemplate,
    edge: DecisionEdgeTemplate,
    context: AgentDecisionContext,
    evidence: DecisionEvidenceRegistryDefinition,
) -> EvaluatedDecisionProbability:
    result = evaluate_decision_edge(edge, context, evidence.evidence)
    unsupported = [
        factor
        for factor in result.factors
        if factor.status != "measured"
        or not factor.fittable
        or factor.evidence_basis not in EXECUTABLE_EVIDENCE_BASES
    ]
    if result.status != "measured" or not result.fittable or unsupported:
        detail = (
            ", ".join(f"{factor.factor_id}:{factor.status}" for factor in unsupported)
            or result.status
        )
        raise RuntimeDecisionCompilationError(
            f"Confirmed decision tree {template.id!r} cannot compile edge {edge.id!r} "
            f"for agent {context.agent_id!r}: {detail}"
        )
    return result


def _source_profiles(
    edges: list[DecisionEdgeTemplate],
    context: AgentDecisionContext,
    evidence: DecisionEvidenceRegistryDefinition,
    runtime_context_keys: set[str],
) -> list[dict[tuple[str, str], Scalar]]:
    values_by_input: dict[tuple[str, str], dict[tuple[str, str], Scalar]] = {}
    for edge in edges:
        for factor in edge.formula.factors:
            if not _dynamic_factor(factor, runtime_context_keys):
                continue
            identity = (factor.input_kind, factor.input_key)
            rows = _factor_evidence_rows(edge, factor, context, evidence)
            candidates = _candidate_values(factor, rows, context)
            values = values_by_input.setdefault(identity, {})
            for value in candidates:
                values[(type(value).__name__, json.dumps(value, sort_keys=True))] = value
    if not values_by_input:
        return [{}]
    identities = sorted(values_by_input)
    domains = [
        [values_by_input[identity][key] for key in sorted(values_by_input[identity])]
        for identity in identities
    ]
    profile_count = math.prod(len(domain) for domain in domains)
    if profile_count > MAX_RUNTIME_EVIDENCE_PROFILES:
        raise RuntimeDecisionCompilationError(
            f"Runtime evidence expands to {profile_count} profiles; split the decision "
            "into smaller modules"
        )
    return [dict(zip(identities, values, strict=True)) for values in product(*domains)]


def _evaluate_template(
    template: DecisionTreeTemplate,
    context: AgentDecisionContext,
    evidence: DecisionEvidenceRegistryDefinition,
    runtime_context_keys: set[str],
) -> tuple[list[dict[str, Any]], str, list[str]]:
    evidence_by_id = _require_unique(
        evidence.evidence,
        lambda row: row.id,
        "factor evidence",
    )
    edges_by_source: dict[str, list[DecisionEdgeTemplate]] = {}
    for edge in template.edges:
        edges_by_source.setdefault(edge.from_state, []).append(edge)
    terminal_states = set(template.terminal_states)
    rules_by_edge: dict[str, dict[str, dict[str, Any]]] = {edge.id: {} for edge in template.edges}
    for node in template.nodes:
        edges = edges_by_source.get(node.id, [])
        if node.id in terminal_states:
            if edges:
                raise RuntimeDecisionCompilationError(
                    f"Confirmed decision tree {template.id!r} has transitions from terminal "
                    f"state {node.id!r}"
                )
            continue
        if not edges:
            raise RuntimeDecisionCompilationError(
                f"Confirmed decision tree {template.id!r} has no outgoing transition from "
                f"state {node.id!r}"
            )
        for profile in _source_profiles(
            edges,
            context,
            evidence,
            runtime_context_keys,
        ):
            profiled_context = _profile_context(context, profile)
            results = [
                _validated_result(template, edge, profiled_context, evidence) for edge in edges
            ]
            total = sum(result.probability or 0 for result in results)
            if not math.isclose(total, 1, rel_tol=0, abs_tol=1e-9):
                raise RuntimeDecisionCompilationError(
                    f"Confirmed decision tree {template.id!r} outgoing probabilities from "
                    f"{node.id!r} sum to {total:.12g}, expected 1 for agent "
                    f"{context.agent_id!r}"
                )
            for edge, result in zip(edges, results, strict=True):
                conditions = []
                for factor, receipt in zip(
                    edge.formula.factors,
                    result.factors,
                    strict=True,
                ):
                    if not _dynamic_factor(factor, runtime_context_keys):
                        continue
                    if receipt.evidence_id is None:
                        raise RuntimeDecisionCompilationError(
                            f"Dynamic factor {factor.id!r} resolved without evidence"
                        )
                    row = evidence_by_id[receipt.evidence_id]
                    evaluated_value = profile[(factor.input_kind, factor.input_key)]
                    conditions.extend(_predicate_conditions(factor, row.predicate, evaluated_value))
                conditions.sort(key=lambda condition: json.dumps(condition, sort_keys=True))
                rule = {
                    "conditions": conditions,
                    "probability": result.probability,
                    "provenance": _provenance(evidence.version, result),
                }
                condition_key = json.dumps(
                    conditions,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                existing = rules_by_edge[edge.id].get(condition_key)
                if existing is not None and existing != rule:
                    raise RuntimeDecisionCompilationError(
                        f"Dynamic evidence produces conflicting rules for edge {edge.id!r}"
                    )
                rules_by_edge[edge.id][condition_key] = rule
    transitions = [
        {
            "id": edge.id,
            "from_state": edge.from_state,
            "to_state": edge.to_state,
            "rules": [rules_by_edge[edge.id][key] for key in sorted(rules_by_edge[edge.id])],
            "effects": [],
        }
        for edge in template.edges
    ]
    inputs = sorted(
        {
            condition["input"]
            for transition in transitions
            for rule in transition["rules"]
            for condition in rule["conditions"]
        }
    )
    signature = json.dumps(transitions, sort_keys=True, separators=(",", ":"))
    return transitions, hashlib.sha256(signature.encode()).hexdigest()[:12], inputs


def _evaluate_module(
    module: DecisionTreeModule,
    template: DecisionTreeTemplate,
    evidence_edge_ids: Mapping[str, str],
    context: AgentDecisionContext,
    evidence: DecisionEvidenceRegistryDefinition,
    runtime_context_keys: set[str],
) -> tuple[list[dict[str, Any]], str, list[str]]:
    evaluated, _, inputs = _evaluate_template(
        template,
        context,
        evidence,
        runtime_context_keys,
    )
    evaluated_by_id = {transition["id"]: transition for transition in evaluated}
    transitions = []
    for edge in module.edges:
        evidence_edge_id = evidence_edge_ids[edge.id]
        transition = evaluated_by_id[evidence_edge_id]
        transitions.append(
            {
                **transition,
                "id": edge.id,
                "from_state": edge.from_node,
                "to_state": edge.to_node,
            }
        )
    signature = json.dumps(transitions, sort_keys=True, separators=(",", ":"))
    return transitions, hashlib.sha256(signature.encode()).hexdigest()[:12], inputs


def _coefficient_resolution_status(
    requested: CoefficientPlace,
    source: CoefficientPlace,
) -> str:
    specificity = {"global": 1, "region": 2, "country": 3, "city": 4}
    difference = specificity[requested.level] - specificity[source.level]
    if difference <= 0:
        return "direct"
    return "inherited" if difference == 1 else "imputed"


def _coefficient_provenance(
    resolution: ResolvedActionCoefficients,
    edge_id: str,
) -> dict[str, Any]:
    value = resolution.coefficients[edge_id]
    interval = resolution.intervals[edge_id]
    uncertainty = max(value - interval.low, interval.high - value)
    provenance = {
        "source": resolution.source_label,
        "version": resolution.source_version,
        "status": resolution.evidence_state,
        "resolution_status": _coefficient_resolution_status(
            resolution.requested_place,
            resolution.source_place,
        ),
        "source_places": [f"{resolution.source_place.level}:{resolution.source_place.place_id}"],
        "uncertainty": uncertainty,
        "evidence_id": resolution.source_id or resolution.coefficient_set_id,
        "evidence_kind": resolution.evidence_state,
        "ci_low": interval.low,
        "ci_high": interval.high,
    }
    if resolution.fitted_provenance is not None:
        provenance["source_date"] = resolution.fitted_provenance.source_date
    return provenance


def _evaluate_coefficient_module(
    module: DecisionTreeModule,
    agent: AgentRecord,
    registry: ActionCoefficientRegistry,
) -> tuple[list[dict[str, Any]], str, list[RunCoefficientReceipt]]:
    requested_place = _agent_coefficient_place(agent)
    resolution = resolve_action_coefficients(registry, module.id, requested_place)
    edge_ids = {edge.id for edge in module.edges}
    if set(resolution.coefficients) != edge_ids:
        raise RuntimeDecisionCompilationError(
            f"Action coefficient set {resolution.coefficient_set_id!r} outcomes do not match "
            f"decision module {module.id!r} edges"
        )
    outgoing_sources = {edge.from_node for edge in module.edges}
    if len(outgoing_sources) != 1:
        raise RuntimeDecisionCompilationError(
            f"Default/fitted coefficient action {module.id!r} must contain one decision node"
        )
    transitions = [
        {
            "id": edge.id,
            "from_state": edge.from_node,
            "to_state": edge.to_node,
            "rules": [
                {
                    "conditions": [],
                    "probability": resolution.coefficients[edge.id],
                    "provenance": _coefficient_provenance(resolution, edge.id),
                }
            ],
            "effects": [],
        }
        for edge in module.edges
    ]
    resolution_status = _coefficient_resolution_status(
        resolution.requested_place,
        resolution.source_place,
    )
    receipts = [
        RunCoefficientReceipt(
            action_id=module.id,
            edge_id=edge.id,
            place=resolution.requested_place,
            source_place=resolution.source_place,
            resolution_status=resolution_status,
            evidence_state=resolution.evidence_state,
            value=resolution.coefficients[edge.id],
            interval=resolution.intervals[edge.id],
            coefficient_set_id=resolution.coefficient_set_id,
            default_coefficient_set_id=resolution.default_coefficient_set_id,
            default_value=resolution.default_coefficients[edge.id],
            fitted_delta=(
                resolution.coefficients[edge.id] - resolution.default_coefficients[edge.id]
                if resolution.evidence_state == "fitted"
                else None
            ),
            promotion_id=resolution.promotion_id,
            source_label=resolution.source_label,
            source_version=resolution.source_version,
            source_id=resolution.source_id,
            default_reason=resolution.default_reason,
            held_out=resolution.held_out,
        )
        for edge in module.edges
    ]
    signature = json.dumps(transitions, sort_keys=True, separators=(",", ":"))
    return transitions, hashlib.sha256(signature.encode()).hexdigest()[:12], receipts


def _compile_agent_program(
    agent: AgentRecord,
    trees: list[DecisionTreeDefinition],
    modules_by_id: Mapping[str, DecisionTreeModule],
    root_trees_by_module: Mapping[str, list[DecisionTreeDefinition]],
    templates_by_id: Mapping[str, DecisionTreeTemplate],
    evidence: DecisionEvidenceRegistryDefinition,
    coefficient_registry: ActionCoefficientRegistry | None,
    start_date: date,
    runtime_context_keys: set[str],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, str]],
    dict[str, str],
    list[RunCoefficientReceipt],
]:
    context = _agent_context(agent, start_date)
    source_modules: dict[str, tuple[DecisionTreeDefinition, DecisionTreeModule]] = {}
    for tree in sorted(trees, key=lambda item: item.id):
        for module in _reachable_modules(tree, modules_by_id):
            source_modules.setdefault(module.id, (tree, module))
    compiled: list[
        tuple[
            DecisionTreeDefinition,
            DecisionTreeModule,
            list[dict[str, Any]],
            str,
            list[str],
            list[RunCoefficientReceipt],
        ]
    ] = []
    for module_id in sorted(source_modules):
        tree, module = source_modules[module_id]
        coefficient_defaults = (
            [item for item in coefficient_registry.defaults if item.action_id == module.id]
            if coefficient_registry is not None
            else []
        )
        if coefficient_defaults:
            transitions, profile, receipts = _evaluate_coefficient_module(
                module,
                agent,
                coefficient_registry,
            )
            inputs: list[str] = []
        else:
            template, evidence_edge_ids = _module_evidence_binding(
                tree.id,
                module,
                root_trees_by_module,
                templates_by_id,
            )
            transitions, profile, inputs = _evaluate_module(
                module,
                template,
                evidence_edge_ids,
                context,
                evidence,
                runtime_context_keys,
            )
            receipts = []
        compiled.append((tree, module, transitions, profile, inputs, receipts))
    program_signature = json.dumps(
        [
            _primary_agent_type(agent),
            [(tree.id, module.id, profile) for tree, module, _, profile, _, _ in compiled],
        ],
        separators=(",", ":"),
    )
    program_id = hashlib.sha256(program_signature.encode()).hexdigest()[:12]
    runtime_modules = []
    runtime_by_source: dict[str, str] = {}
    for _tree, module, transitions, profile, inputs, _receipts in compiled:
        module_id = _runtime_identifier(
            "decision",
            f"{program_id}:{module.id}:{profile}",
        )
        runtime_by_source[module.id] = module_id
        runtime_modules.append(
            {
                "id": module_id,
                "entry_state": module.entry_node,
                "exit_states": [
                    node.id
                    for node in module.nodes
                    if node.kind in {"terminal", "module_reference"}
                ],
                "inputs": inputs,
                "outputs": [],
                "states": [node.id for node in module.nodes],
                "transitions": transitions,
            }
        )
    routes = []
    for _, module, _, _, _, _ in compiled:
        for node in module.nodes:
            if node.kind != "module_reference" or node.target_module_id is None:
                continue
            target = runtime_by_source.get(node.target_module_id)
            if target is None:
                raise RuntimeDecisionCompilationError(
                    f"Confirmed decision module {module.id!r} references uncompiled "
                    f"module {node.target_module_id!r}"
                )
            routes.append(
                {
                    "from_module": runtime_by_source[module.id],
                    "exit_state": node.id,
                    "to_module": target,
                }
            )
    receipts = [receipt for *_, values in compiled for receipt in values]
    return runtime_modules, routes, runtime_by_source, receipts


def compile_runtime_decisions(
    tree_registry: DecisionTreeRegistryDefinition,
    evidence_registry: DecisionEvidenceRegistryDefinition | None,
    agents: list[AgentRecord],
    start_date: date,
    requested_tree_ids_by_agent: list[set[str]] | None = None,
    requested_module_ids_by_agent: list[set[str]] | None = None,
    runtime_context_keys: set[str] | None = None,
    coefficient_registry: ActionCoefficientRegistry | None = None,
    default_dsl_identity: DefaultDslEvidenceIdentity | None = None,
) -> RuntimeDecisionCompilation:
    ready_trees = sorted(
        (tree for tree in tree_registry.trees if tree.status == "ready"),
        key=lambda tree: tree.id,
    )
    trees_by_id = _require_unique(tree_registry.trees, lambda tree: tree.id, "tree")
    modules_by_id = _require_unique(tree_registry.modules, lambda module: module.id, "module")
    if len(trees_by_id) != len(tree_registry.trees):
        raise RuntimeDecisionCompilationError("Confirmed decision tree ids must be unique")
    templates_by_id: dict[str, DecisionTreeTemplate] = {}
    if evidence_registry is not None:
        templates_by_id = _require_unique(
            evidence_registry.templates, lambda template: template.id, "evidence template"
        )
    root_trees_by_module: dict[str, list[DecisionTreeDefinition]] = {}
    for tree in ready_trees:
        root_trees_by_module.setdefault(tree.root_module_id, []).append(tree)
    reachable_module_ids_by_tree: dict[str, set[str]] = {}
    for tree in ready_trees:
        found: set[str] = set()
        pending = [tree.root_module_id]
        while pending:
            module_id = pending.pop()
            if module_id in found:
                continue
            found.add(module_id)
            module = modules_by_id.get(module_id)
            if module is not None:
                pending.extend(
                    node.target_module_id
                    for node in module.nodes
                    if node.target_module_id is not None
                )
        reachable_module_ids_by_tree[tree.id] = found
    requested_tree_ids = requested_tree_ids_by_agent or [set() for _ in agents]
    requested_module_ids = requested_module_ids_by_agent or [set() for _ in agents]
    if len(requested_tree_ids) != len(agents) or len(requested_module_ids) != len(agents):
        raise RuntimeDecisionCompilationError(
            "Requested decision tree and module bindings must align with selected agents"
        )
    applicable: list[list[DecisionTreeDefinition]] = []
    for agent, tree_ids, module_ids in zip(
        agents, requested_tree_ids, requested_module_ids, strict=True
    ):
        for tree_id in sorted(tree_ids):
            tree = trees_by_id.get(tree_id)
            if tree is None or tree.status != "ready":
                raise RuntimeDecisionCompilationError(
                    f"Agent {agent.agent_id!r} requires decision tree {tree_id!r}, "
                    "but it is missing or not ready"
                )
        for module_id in sorted(module_ids):
            module = modules_by_id.get(module_id)
            matches = [
                tree for tree in ready_trees if module_id in reachable_module_ids_by_tree[tree.id]
            ]
            if module is None or module.status != "ready" or not matches:
                raise RuntimeDecisionCompilationError(
                    f"Agent {agent.agent_id!r} routine calls decision module {module_id!r}, "
                    "but no ready decision tree reaches it"
                )
        applicable.append(
            [
                tree
                for tree in ready_trees
                if _tree_applies(tree, agent)
                or tree.id in tree_ids
                or bool(reachable_module_ids_by_tree[tree.id].intersection(module_ids))
            ]
        )
    uncovered = [
        (agent.agent_id, _primary_agent_type(agent))
        for agent, trees in zip(agents, applicable, strict=True)
        if not trees
    ]
    if uncovered:
        preview = ", ".join(
            f"{agent_id} ({agent_type})"
            for agent_id, agent_type in uncovered[:MAX_UNCOVERED_AGENT_PREVIEW]
        )
        remaining = len(uncovered) - MAX_UNCOVERED_AGENT_PREVIEW
        suffix = f", +{remaining} more" if remaining > 0 else ""
        noun = "agent has" if len(uncovered) == 1 else "agents have"
        raise RuntimeDecisionCompilationError(
            f"Run blocked: {len(uncovered)} selected {noun} no applicable confirmed "
            f"executable decision tree: {preview}{suffix}. Confirm ready decision trees "
            "with default/estimated or fitted evidence for every selected agent type in "
            "Simulation > Decision Trees, then run again."
        )
    coefficient_action_ids = (
        {item.action_id for item in coefficient_registry.defaults}
        if coefficient_registry is not None
        else set()
    )
    modules_without_coefficients = {
        module_id
        for trees in applicable
        for tree in trees
        for module_id in reachable_module_ids_by_tree[tree.id]
        if module_id not in coefficient_action_ids
    }
    if any(applicable) and evidence_registry is None and modules_without_coefficients:
        tree_ids = sorted({tree.id for trees in applicable for tree in trees})
        raise RuntimeDecisionCompilationError(
            "Confirmed decision trees have no confirmed decision evidence registry: "
            + ", ".join(tree_ids)
            + ". Attach executable default/estimated or fitted evidence in Simulation > "
            "Decision Trees, then run again."
        )
    if coefficient_registry is not None:
        for item in coefficient_registry.defaults:
            source = item.source
            if hasattr(source, "default_dsl_version") and (
                default_dsl_identity is None
                or source.default_dsl_version != default_dsl_identity.version
                or source.default_dsl_hash != default_dsl_identity.hash
            ):
                raise RuntimeDecisionCompilationError(
                    f"Default coefficient set {item.id!r} does not match the verified shipped "
                    "Default DSL"
                )
    modules: dict[str, dict[str, Any]] = {}
    routes: dict[tuple[str, str], dict[str, str]] = {}
    agent_modules: list[str] = []
    agent_states: list[str] = []
    module_ids_by_agent: list[tuple[str, ...]] = []
    tree_ids_by_agent: list[tuple[str, ...]] = []
    runtime_module_by_source_module_by_agent: list[dict[str, str]] = []
    coefficient_receipts: list[RunCoefficientReceipt] = []
    live_context_keys = runtime_context_keys or set()
    for agent, trees in zip(agents, applicable, strict=True):
        compilation_evidence = evidence_registry or DecisionEvidenceRegistryDefinition(
            version="coefficient-registry-only",
            templates=[],
            evidence=[],
        )
        compiled_modules, compiled_routes, runtime_by_source, agent_receipts = (
            _compile_agent_program(
                agent,
                trees,
                modules_by_id,
                root_trees_by_module,
                templates_by_id,
                compilation_evidence,
                coefficient_registry,
                start_date,
                live_context_keys,
            )
        )
        coefficient_receipts.extend(agent_receipts)
        for module in compiled_modules:
            existing = modules.get(module["id"])
            if existing is not None and existing != module:
                raise RuntimeDecisionCompilationError(
                    f"Runtime module identity {module['id']!r} has conflicting definitions"
                )
            modules[module["id"]] = module
        for route in compiled_routes:
            key = (route["from_module"], route["exit_state"])
            existing = routes.get(key)
            if existing is not None and existing != route:
                raise RuntimeDecisionCompilationError(
                    f"Runtime route {key!r} has conflicting targets"
                )
            routes[key] = route
        agent_type = _primary_agent_type(agent)
        idle_module_id = _runtime_identifier("idle-agent-type", agent_type)
        modules.setdefault(idle_module_id, _idle_module(idle_module_id))
        agent_modules.append(idle_module_id)
        agent_states.append("idle")
        module_ids_by_agent.append((idle_module_id, *(module["id"] for module in compiled_modules)))
        tree_ids_by_agent.append(tuple(tree.id for tree in trees))
        runtime_module_by_source_module_by_agent.append(runtime_by_source)
    return RuntimeDecisionCompilation(
        modules=sorted(modules.values(), key=lambda module: module["id"]),
        routes=[routes[key] for key in sorted(routes)],
        agent_modules=agent_modules,
        agent_states=agent_states,
        module_ids_by_agent=module_ids_by_agent,
        tree_ids_by_agent=tree_ids_by_agent,
        runtime_module_by_source_module_by_agent=(runtime_module_by_source_module_by_agent),
        coefficient_receipts=coefficient_receipts,
    )
