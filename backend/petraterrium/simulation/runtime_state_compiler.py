from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..population import AgentRecord
from .agent_state import AgentStateCatalog, StateEvidence
from .coefficient_evidence import CoefficientInterval, CoefficientPlace
from .default_dsl import (
    DefaultActionDefinition,
    DefaultCashFlowFormula,
    DefaultFinanceLedger,
    DefaultSourceRecord,
    _validate_exclusive_action_choices,
)
from .registry_store import SimulationRegistryStore
from .run_warnings import RunCoefficientReceipt


@dataclass(frozen=True)
class RuntimeStateCompilation:
    meaningful_actions: list[dict[str, Any]]
    state_dynamics: dict[str, Any]
    coefficient_receipts: list[RunCoefficientReceipt]


def _probability_provenance(
    action: DefaultActionDefinition,
    sources: dict[str, DefaultSourceRecord],
    version: str,
) -> dict[str, Any]:
    selected = [sources[source_id] for source_id in action.evidence.source_ids]
    source = "; ".join(
        f"{item.publisher}: {item.original_title} ({item.url})" for item in selected
    ) or action.evidence.explicit_default_reason
    dates = sorted(item.publication_date for item in selected)
    return {
        "source": source,
        "version": version,
        "status": action.evidence.status,
        "uncertainty": max(
            action.evidence.uncertainty_high,
            1 - action.evidence.uncertainty_low,
        ),
        "source_date": dates[-1] if dates else None,
        "evidence_id": action.id,
        "evidence_kind": action.evidence.status,
        "ci_low": action.evidence.uncertainty_low,
        "ci_high": action.evidence.uncertainty_high,
    }


def _state_evidence(evidence: StateEvidence) -> dict[str, Any]:
    return {
        "status": (
            evidence.status
            if evidence.status in {"measured_joint", "measured_marginal"}
            else "default_estimated"
        ),
        "source": evidence.source,
        "source_version": evidence.source_version,
        "uncertainty": evidence.uncertainty,
    }


def _meaningful_actions(
    actions: list[DefaultActionDefinition],
    sources: dict[str, DefaultSourceRecord],
    version: str,
) -> list[dict[str, Any]]:
    result = []
    for action in actions:
        if not action.runtime_rules:
            continue
        provenance = _probability_provenance(action, sources, version)
        result.append(
            {
                "id": action.id,
                "exclusive_choice_group": action.exclusive_choice_group,
                "rules": [
                    {
                        "conditions": [
                            {
                                "input": condition.input,
                                "operator": condition.operator,
                                "value": condition.value,
                            }
                            for condition in rule.conditions
                        ],
                        "probability": rule.probability,
                        "provenance": provenance,
                    }
                    for rule in action.runtime_rules
                ],
            }
        )
    return result


def _state_rules(
    actions: list[DefaultActionDefinition],
    catalog: AgentStateCatalog,
    available_memory: set[str],
) -> list[dict[str, Any]]:
    definitions = {definition.id: definition for definition in catalog.definitions}
    required_targets = {
        outcome.state_id
        for action in actions
        for outcome in action.outcomes
    }
    rules_by_target = {rule.target_state_id: rule for rule in catalog.runtime_rules}
    required_targets.update(
        rule.target_state_id for rule in catalog.runtime_rules if rule.coefficients
    )
    missing_targets = sorted(required_targets - definitions.keys())
    missing_rules = sorted(required_targets - rules_by_target.keys())
    missing_memory = sorted(required_targets - available_memory)
    missing_inputs = sorted(
        {
            input_state
            for target in required_targets
            for input_state in (
                rules_by_target[target].coefficients if target in rules_by_target else {}
            )
            if input_state not in available_memory
        }
    )
    if missing_targets:
        raise ValueError(
            "Default action outcomes reference unknown agent states: "
            + ", ".join(missing_targets)
        )
    if missing_rules:
        raise ValueError(
            "Default action outcomes require missing DSL state runtime rules: "
            + ", ".join(missing_rules)
        )
    if missing_memory:
        raise ValueError(
            "Default action outcomes require unavailable numeric state columns: "
            + ", ".join(missing_memory)
        )
    if missing_inputs:
        raise ValueError(
            "State propagation requires unavailable numeric state columns: "
            + ", ".join(missing_inputs)
        )
    return [
        {
            "target_state_id": rule.target_state_id,
            "intercept": rule.intercept,
            "coefficients": rule.coefficients,
            "minimum": rule.minimum,
            "maximum": rule.maximum,
            "formula": rule.formula,
            "evidence": _state_evidence(rule.evidence),
        }
        for target in sorted(required_targets)
        for rule in (rules_by_target[target],)
    ]


def _finance_rules(
    ledger: DefaultFinanceLedger,
    version: str,
) -> list[dict[str, Any]]:
    return [
        {
            "id": rule.id,
            "target": rule.target,
            "terms": rule.terms,
            "minimum": rule.minimum,
            "maximum": rule.maximum,
            "formula": rule.formula,
            "evidence": {
                "status": rule.evidence.status,
                "source": rule.evidence.explicit_default_reason,
                "source_version": version,
                "uncertainty": max(
                    rule.evidence.uncertainty_high,
                    1 - rule.evidence.uncertainty_low,
                ),
            },
        }
        for rule in ledger.rules
    ]


def _event_payload(
    action: DefaultActionDefinition,
    sources: dict[str, DefaultSourceRecord],
    version: str,
    agents: list[AgentRecord],
) -> dict[str, Any]:
    probability_provenance = _probability_provenance(action, sources, version)
    amount_fields = tuple(type(action.cash_flow).model_fields)
    absolute_cash_flow = {}
    cash_flow_by_agent = (
        {field: [] for field in amount_fields}
        if any(
            isinstance(getattr(action.cash_flow, field), DefaultCashFlowFormula)
            for field in amount_fields
        )
        else None
    )
    for field in amount_fields:
        configured = getattr(action.cash_flow, field)
        absolute_cash_flow[field] = (
            0.0 if isinstance(configured, DefaultCashFlowFormula) else configured
        )
        if cash_flow_by_agent is None:
            continue
        for agent in agents:
            if not isinstance(configured, DefaultCashFlowFormula):
                cash_flow_by_agent[field].append(float(configured))
                continue
            trait_id = configured.input.removeprefix("traits.")
            try:
                value = float(agent.traits[trait_id]) * configured.multiplier
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(
                    f"Agent {agent.agent_id!r} lacks {configured.input!r} required "
                    f"by action {action.id!r} cash flow {field!r}"
                ) from error
            bounded = max(configured.minimum, value)
            if configured.maximum is not None:
                bounded = min(configured.maximum, bounded)
            cash_flow_by_agent[field].append(round(bounded, 6))
    return {
        "id": action.id,
        "effects": [
            {
                "target": f"memory.{outcome.state_id}",
                "operation": outcome.operation,
                "value": outcome.value,
            }
            for outcome in action.outcomes
        ],
        "cash_flow": absolute_cash_flow,
        "cash_flow_by_agent": cash_flow_by_agent,
        "evidence": {
            "status": probability_provenance["status"],
            "source": probability_provenance["source"],
            "source_version": version,
            "uncertainty": probability_provenance["uncertainty"],
        },
    }


def _finance_metadata(agents: list[AgentRecord]) -> dict[str, list[str]]:
    def required(agent: AgentRecord, field: str) -> str:
        value = str(agent.traits.get(field, "")).strip()
        if not value:
            raise ValueError(
                f"Agent {agent.agent_id!r} has no {field} for the finance runtime"
            )
        return value

    return {
        "currency": [required(agent, "finance_currency") for agent in agents],
        "status": [required(agent, "finance_status") for agent in agents],
        "source": [required(agent, "finance_source") for agent in agents],
    }


def _agent_place(agent: AgentRecord) -> CoefficientPlace:
    region = str(agent.traits.get("region", "unknown-region")).strip()
    country = str(
        agent.traits.get("country_id", agent.place or "unknown-country")
    ).strip()
    city_value = agent.traits.get("city_id")
    city = str(city_value).strip() if city_value is not None else ""
    if city:
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


def _coefficient_receipts(
    actions: list[DefaultActionDefinition],
    sources: dict[str, DefaultSourceRecord],
    version: str,
    agents: list[AgentRecord],
) -> list[RunCoefficientReceipt]:
    place_counts: dict[CoefficientPlace, int] = {}
    for agent in agents:
        place = _agent_place(agent)
        place_counts[place] = place_counts.get(place, 0) + 1
    result = []
    source_place = CoefficientPlace(level="global", place_id="global")
    for action in actions:
        if not action.runtime_rules:
            continue
        provenance = _probability_provenance(action, sources, version)
        for place, affected_agents in sorted(
            place_counts.items(), key=lambda item: item[0].key
        ):
            for index, rule in enumerate(action.runtime_rules):
                result.append(
                    RunCoefficientReceipt(
                        action_id=action.id,
                        edge_id=f"runtime_rule_{index}",
                        place=place,
                        source_place=source_place,
                        resolution_status="imputed",
                        evidence_state="default_estimated",
                        value=rule.probability,
                        interval=CoefficientInterval(
                            low=action.evidence.uncertainty_low,
                            high=action.evidence.uncertainty_high,
                        ),
                        coefficient_set_id=f"{action.id}_{version}_runtime",
                        default_coefficient_set_id=f"{action.id}_{version}_runtime",
                        default_value=rule.probability,
                        source_label=provenance["source"],
                        source_version=version,
                        source_id=(
                            ",".join(action.evidence.source_ids) or action.id
                        ),
                        default_reason=action.evidence.explicit_default_reason,
                        affected_agents=affected_agents,
                    )
                )
    return result


def compile_runtime_state(
    store: SimulationRegistryStore,
    agents: list[AgentRecord],
    available_memory: set[str],
) -> RuntimeStateCompilation:
    payload = store.payload_snapshot()
    raw_actions = payload.get("default_actions", [])
    raw_sources = payload.get("default_sources", [])
    raw_catalog = payload.get("agent_states")
    raw_finance_rules = payload.get("finance_rules")
    if not raw_actions or raw_catalog is None or raw_finance_rules is None:
        return RuntimeStateCompilation(
            meaningful_actions=[],
            state_dynamics={},
            coefficient_receipts=[],
        )
    actions = [
        DefaultActionDefinition.model_validate_json(json.dumps(item))
        for item in raw_actions
    ]
    _validate_exclusive_action_choices(actions)
    sources = {
        source.id: source
        for source in (
            DefaultSourceRecord.model_validate_json(json.dumps(item))
            for item in raw_sources
        )
    }
    catalog = AgentStateCatalog.model_validate_json(json.dumps(raw_catalog))
    finance_ledger = DefaultFinanceLedger.model_validate_json(
        json.dumps(raw_finance_rules)
    )
    receipt = store.default_dsl_receipt()
    version = receipt.version if receipt is not None else "user-registry"
    return RuntimeStateCompilation(
        meaningful_actions=_meaningful_actions(actions, sources, version),
        state_dynamics={
            "events": [
                _event_payload(action, sources, version, agents) for action in actions
            ],
            "state_rules": _state_rules(actions, catalog, available_memory),
            "finance": _finance_metadata(agents),
            "finance_rules": _finance_rules(finance_ledger, version),
        },
        coefficient_receipts=_coefficient_receipts(
            actions,
            sources,
            version,
            agents,
        ),
    )
