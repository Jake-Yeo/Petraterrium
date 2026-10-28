from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .agent_types import ConfirmedAgentTypeRegistry
from .aggregate_statistics import AggregateStatisticsProgram
from .finance_initialization import FinanceInitializationCatalog
from .interaction_trees import InteractionTreeDefinition
from .interactions import InteractionProgramDefinition
from .population_generation import (
    InitialPopulationMaterialization,
    validate_initial_population,
)
from .registry_store import SimulationRegistryStore
from .routines import RoutineRegistryDefinition, validate_routines
from .specialization import SpecializationCatalog
from .tree_modules import DecisionTreeModuleRegistry, DecisionTreeRegistryDefinition

DEFAULT_DSL_PATH = Path(__file__).with_name("defaults") / "base-v1.json"
SELF_HASH = "$default_dsl_hash"


class DefaultDslModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class DefaultDslReceipt(DefaultDslModel):
    schema_version: Literal["1"] = "1"
    version: str = Field(min_length=1)
    hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    source: Literal["shipped"] = "shipped"
    managed_sections: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_sections(self):
        if len(set(self.managed_sections)) != len(self.managed_sections):
            raise ValueError("Default DSL managed sections must be unique")
        return self


class DefaultSourceRecord(DefaultDslModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    original_title: str = Field(min_length=1)
    english_title: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    publication_date: str = Field(min_length=1)
    population: str = Field(min_length=1)
    place: str = Field(min_length=1)
    language: str = Field(min_length=1)
    discovery_source: str = Field(min_length=1)
    url: str = Field(min_length=1)
    supports: tuple[str, ...] = Field(min_length=1)


class DefaultDurationDistribution(DefaultDslModel):
    duration_min_hours: float = Field(ge=0, le=168, allow_inf_nan=False)
    duration_median_hours: float = Field(gt=0, le=168, allow_inf_nan=False)
    duration_max_hours: float = Field(gt=0, le=168, allow_inf_nan=False)
    shape: Literal["triangular", "uniform", "lognormal"]
    shape_parameters: dict[str, float] = Field(default_factory=dict)
    evidence: DefaultEvidence | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_minute_fields(cls, value):
        if not isinstance(value, dict):
            return value
        migrated = dict(value)
        if "minimum_minutes" in migrated:
            migrated["duration_min_hours"] = migrated.pop("minimum_minutes") / 60
            migrated["duration_median_hours"] = migrated.pop("typical_minutes") / 60
            migrated["duration_max_hours"] = migrated.pop("maximum_minutes") / 60
        evidence = migrated.get("evidence")
        if isinstance(evidence, dict) and isinstance(evidence.get("source_ids"), list):
            migrated["evidence"] = {
                **evidence,
                "source_ids": tuple(evidence["source_ids"]),
            }
        return migrated

    @model_validator(mode="after")
    def ordered_duration(self):
        if not (self.duration_min_hours <= self.duration_median_hours <= self.duration_max_hours):
            raise ValueError("Default action duration bounds must be ordered")
        if self.duration_max_hours <= self.duration_min_hours:
            raise ValueError("Default action duration must be a non-fixed range")
        if (
            self.shape == "uniform"
            and abs(
                self.duration_median_hours - (self.duration_min_hours + self.duration_max_hours) / 2
            )
            > 1e-9
        ):
            raise ValueError("Uniform duration median must be the midpoint")
        if self.shape == "lognormal" and self.shape_parameters.get("sigma", 0) <= 0:
            raise ValueError("Lognormal duration requires a positive sigma")
        return self


class DefaultEvidence(DefaultDslModel):
    status: Literal["default_estimated", "measured"]
    explicit_default_reason: str = Field(min_length=1)
    uncertainty_low: float = Field(ge=0, le=1)
    uncertainty_high: float = Field(ge=0, le=1)
    source_ids: tuple[str, ...] = ()
    editable_provenance: dict | None = None

    @model_validator(mode="after")
    def ordered_uncertainty(self):
        if self.uncertainty_low > self.uncertainty_high:
            raise ValueError("Default evidence uncertainty bounds must be ordered")
        return self


class DefaultDurationResolution(DefaultDslModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    place_level: Literal["city", "country", "region", "global"]
    place_ids: tuple[str, ...] = Field(min_length=1)
    agent_type_ids: tuple[str, ...] = ()
    duration: DefaultDurationDistribution

    @model_validator(mode="after")
    def unique_selectors(self):
        if len(set(self.place_ids)) != len(self.place_ids):
            raise ValueError("Duration resolution place ids must be unique")
        if len(set(self.agent_type_ids)) != len(self.agent_type_ids):
            raise ValueError("Duration resolution agent type ids must be unique")
        return self


class DefaultActionOutcome(DefaultDslModel):
    state_id: str = Field(min_length=1)
    operation: Literal["add", "subtract", "set", "multiply"]
    value: float


class DefaultRuntimeCondition(DefaultDslModel):
    input: str = Field(min_length=1)
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte"]
    value: float
    categorical_value: str | None = None


class DefaultRuntimeRule(DefaultDslModel):
    conditions: tuple[DefaultRuntimeCondition, ...] = ()
    probability: float = Field(ge=0, le=1)
    evidence: DefaultEvidence | None = None
    probability_time_unit_hours: float | None = Field(default=None, gt=0)


class DefaultCashFlowFormula(DefaultDslModel):
    input: str = Field(pattern=r"^traits\.[a-z][a-z0-9_]*$")
    multiplier: float = Field(ge=0)
    minimum: float = Field(default=0, ge=0)
    maximum: float | None = Field(default=None, ge=0)
    formula: str = Field(min_length=1)

    @model_validator(mode="after")
    def ordered_bounds(self):
        if self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("Cash-flow formula bounds must be ordered")
        return self


CashFlowValue = float | DefaultCashFlowFormula


class DefaultCashFlow(DefaultDslModel):
    wages: CashFlowValue = 0
    business_income: CashFlowValue = 0
    transfers: CashFlowValue = 0
    housing: CashFlowValue = 0
    food: CashFlowValue = 0
    transport: CashFlowValue = 0
    other_expenses: CashFlowValue = 0
    taxes: CashFlowValue = 0
    savings_contribution: CashFlowValue = 0
    savings_withdrawal: CashFlowValue = 0
    debt_draw: CashFlowValue = 0
    debt_repayment: CashFlowValue = 0

    @model_validator(mode="after")
    def nonnegative_amounts(self):
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, int | float) and value < 0:
                raise ValueError("Cash-flow amounts must be non-negative")
        return self


class DefaultActionDefinition(DefaultDslModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    duration: DefaultDurationDistribution
    duration_resolutions: tuple[DefaultDurationResolution, ...] = ()
    category: str = Field(default="other", min_length=1)
    priority: int = 0
    passive: bool = False
    interruptibility: Literal["interruptible", "protected", "uninterruptible"] = "interruptible"
    interruption_outcome: Literal["defer", "cancel"] = "defer"
    emergency_interruptions: tuple[str, ...] = ()
    formula: str = Field(min_length=1)
    conditions: tuple[str, ...]
    place_requirements: tuple[str, ...]
    time_requirements: tuple[str, ...]
    state_inputs: tuple[str, ...]
    outcomes: tuple[DefaultActionOutcome, ...]
    evidence: DefaultEvidence
    exclusive_choice_group: str | None = None
    runtime_rules: tuple[DefaultRuntimeRule, ...] = ()
    cash_flow: DefaultCashFlow = Field(default_factory=DefaultCashFlow)

    @model_validator(mode="after")
    def valid_choice_group(self):
        if self.exclusive_choice_group is not None and not self.exclusive_choice_group:
            raise ValueError("Exclusive action choice group cannot be empty")
        return self


class DefaultFinanceLedgerRule(DefaultDslModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    target: str = Field(pattern=r"^finance\.[a-z][a-z0-9_]*$")
    terms: dict[str, float] = Field(min_length=1)
    minimum: float | None = Field(default=None, allow_inf_nan=False)
    maximum: float | None = Field(default=None, allow_inf_nan=False)
    formula: str = Field(min_length=1)
    evidence: DefaultEvidence

    @model_validator(mode="after")
    def valid_rule(self):
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("Finance ledger-rule bounds must be ordered")
        if any(not name.startswith(("finance.", "cash_flow.")) for name in self.terms):
            raise ValueError("Finance ledger-rule terms must name finance or cash-flow inputs")
        return self


class DefaultFinanceLedger(DefaultDslModel):
    version: str = Field(min_length=1)
    status: Literal["confirmed"]
    rules: tuple[DefaultFinanceLedgerRule, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_targets(self):
        identities = [rule.id for rule in self.rules]
        targets = [rule.target for rule in self.rules]
        if len(set(identities)) != len(identities):
            raise ValueError("Finance ledger-rule ids must be unique")
        if len(set(targets)) != len(targets):
            raise ValueError("Finance ledger-rule targets must be unique")
        return self


class DefaultSeedingRule(DefaultDslModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    seed: int = Field(ge=0)
    count: int = Field(ge=1)
    algorithm: Literal["stable_sha256"]
    place: str = Field(min_length=1)
    agent_type_ids: tuple[str, ...] = Field(min_length=1)
    expected_agent_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_agent_ids(self):
        if self.count != len(self.expected_agent_ids):
            raise ValueError("Default seeding rule count must match expected agent ids")
        if len(set(self.expected_agent_ids)) != len(self.expected_agent_ids):
            raise ValueError("Default seeding rule agent ids must be unique")
        return self


class DefaultScenarioOverlay(DefaultDslModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    action_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)
    state_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)


class DefaultDslInventory(DefaultDslModel):
    agent_type_ids: tuple[str, ...]
    state_ids: tuple[str, ...]
    relationship_state_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    routine_ids: tuple[str, ...]
    decision_tree_ids: tuple[str, ...]
    interaction_tree_ids: tuple[str, ...]
    initial_agent_ids: tuple[str, ...]

    @property
    def initial_agent_count(self) -> int:
        return len(self.initial_agent_ids)


class DefaultDslPackage(DefaultDslModel):
    receipt: DefaultDslReceipt
    content: dict[str, Any]
    inventory: DefaultDslInventory


class DefaultDslStatus(DefaultDslModel):
    loaded: bool
    intact: bool
    receipt: DefaultDslReceipt
    installed_receipt: DefaultDslReceipt | None
    inventory: DefaultDslInventory
    drifted_sections: tuple[str, ...]


class DefaultDslSectionPreview(DefaultDslModel):
    name: str
    disposition: Literal["unchanged", "restore", "replace"]
    current_count: int = Field(ge=0)
    default_count: int = Field(ge=0)
    current_ids: tuple[str, ...]
    default_ids: tuple[str, ...]
    restored_ids: tuple[str, ...]
    replaced_ids: tuple[str, ...]


class DefaultDslResetPreview(DefaultDslModel):
    changed: bool
    receipt: DefaultDslReceipt
    sections: tuple[DefaultDslSectionPreview, ...]


class ResetDefaultDslRequest(DefaultDslModel):
    user_confirmed: Literal[True]
    expected_hash: str = Field(min_length=1)


class DefaultDslManifest(DefaultDslModel):
    schema_version: Literal["1"]
    dsl_version: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    managed_sections: tuple[str, ...] = Field(min_length=1)
    content: dict[str, Any]


def _condition_signature(
    rule: DefaultRuntimeRule,
) -> tuple[tuple[str, str, float], ...]:
    return tuple(
        sorted(
            (condition.input, condition.operator, condition.value) for condition in rule.conditions
        )
    )


def _validate_exclusive_action_choices(
    actions: list[DefaultActionDefinition],
) -> None:
    grouped: dict[str, list[DefaultActionDefinition]] = {}
    for action in actions:
        if action.exclusive_choice_group is not None:
            grouped.setdefault(action.exclusive_choice_group, []).append(action)
    for group, branches in sorted(grouped.items()):
        if len(branches) < 2:
            raise ValueError(
                f"Exclusive action choice group {group!r} requires at least two branches"
            )
        probability_by_action: dict[str, dict[tuple[tuple[str, str, float], ...], float]] = {}
        for action in branches:
            if not action.runtime_rules:
                raise ValueError(
                    f"Exclusive action choice branch {action.id!r} requires runtime rules"
                )
            probabilities: dict[tuple[tuple[str, str, float], ...], float] = {}
            for rule in action.runtime_rules:
                signature = _condition_signature(rule)
                if signature in probabilities:
                    raise ValueError(
                        f"Exclusive action choice branch {action.id!r} repeats a "
                        "condition partition"
                    )
                probabilities[signature] = rule.probability
            probability_by_action[action.id] = probabilities
        expected_signatures = set(next(iter(probability_by_action.values())))
        if any(
            set(probabilities) != expected_signatures
            for probabilities in probability_by_action.values()
        ):
            raise ValueError(
                f"Exclusive action choice group {group!r} requires matching condition partitions"
            )
        for signature in expected_signatures:
            total = sum(
                probabilities[signature] for probabilities in probability_by_action.values()
            )
            if abs(total - 1.0) > 1e-9:
                raise ValueError(
                    f"Exclusive action choice group {group!r} probabilities sum to "
                    f"{total:.12g}, expected 1"
                )


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _resolve_self_hash(value: Any, content_hash: str) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_self_hash(item, content_hash) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_self_hash(item, content_hash) for item in value]
    return content_hash if value == SELF_HASH else value


def _restore_self_hash_placeholders(value: Any, version: str) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                SELF_HASH
                if key == "default_dsl_hash"
                else version
                if key == "default_dsl_version"
                else _restore_self_hash_placeholders(item, version)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_restore_self_hash_placeholders(item, version) for item in value]
    return value


def _section_ids(name: str, value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if name == "agent_types":
        items = value.get("types", [])
        return tuple(sorted(str(item["id"]) for item in items))
    if name == "agent_states":
        items = value.get("definitions", [])
        return tuple(sorted(str(item["id"]) for item in items))
    if name == "relationship_states":
        items = value.get("definitions", [])
        return tuple(sorted(str(item["id"]) for item in items))
    if name == "default_actions":
        return tuple(sorted(str(item["id"]) for item in value))
    if name == "default_sources":
        return tuple(sorted(str(item["id"]) for item in value))
    if name == "routines":
        return tuple(sorted(str(item["id"]) for item in value.get("routines", [])))
    if name == "decision_trees":
        tree_ids = (f"tree:{item['id']}" for item in value.get("trees", []))
        module_ids = (f"module:{item['id']}" for item in value.get("modules", []))
        return tuple(sorted((*tree_ids, *module_ids)))
    if name == "interaction_trees":
        return tuple(sorted(str(item["id"]) for item in value))
    if name == "interaction_program":
        relationship_ids = (
            f"relationship:{item['kind']}" for item in value.get("relationship_evidence", [])
        )
        rule_ids = (f"rule:{item['id']}" for item in value.get("rules", []))
        return tuple(sorted((*relationship_ids, *rule_ids)))
    if name == "initial_seeding_rules":
        return tuple(sorted(str(item["id"]) for item in value))
    if name == "initial_population":
        agents = value.get("population", {}).get("agents", [])
        return tuple(sorted(str(item["agent_id"]) for item in agents))
    if name == "scenario_overlays":
        return tuple(sorted(str(item["id"]) for item in value))
    if name == "coefficient_registry":
        defaults = (f"default:{item['id']}" for item in value.get("defaults", []))
        fitted = (f"fitted:{item['id']}" for item in value.get("fitted", []))
        return tuple(sorted((*defaults, *fitted)))
    if name == "finance_rules":
        return tuple(sorted(str(item["id"]) for item in value.get("rules", [])))
    if name == "finance_initialization":
        return tuple(sorted(str(item) for item in value.get("programs", {})))
    if name == "specialization_pipeline":
        return tuple(sorted(str(item["country_code"]) for item in value.get("countries", [])))
    if name == "aggregate_statistics":
        return (str(value.get("version", "")),)
    return ()


def _section_records(name: str, value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if name == "agent_types":
        return {str(item["id"]): item for item in value.get("types", [])}
    if name in {"agent_states", "relationship_states"}:
        return {str(item["id"]): item for item in value.get("definitions", [])}
    if name in {
        "default_actions",
        "default_sources",
        "interaction_trees",
        "initial_seeding_rules",
        "scenario_overlays",
    }:
        return {str(item["id"]): item for item in value}
    if name == "interaction_program":
        relationships = {
            f"relationship:{item['kind']}": item for item in value.get("relationship_evidence", [])
        }
        rules = {f"rule:{item['id']}": item for item in value.get("rules", [])}
        return relationships | rules
    if name == "routines":
        return {str(item["id"]): item for item in value.get("routines", [])}
    if name == "decision_trees":
        trees = {f"tree:{item['id']}": item for item in value.get("trees", [])}
        modules = {f"module:{item['id']}": item for item in value.get("modules", [])}
        return trees | modules
    if name == "initial_population":
        return {
            str(item["agent_id"]): item for item in value.get("population", {}).get("agents", [])
        }
    if name == "coefficient_registry":
        defaults = {f"default:{item['id']}": item for item in value.get("defaults", [])}
        fitted = {f"fitted:{item['id']}": item for item in value.get("fitted", [])}
        return defaults | fitted
    if name == "finance_rules":
        return {str(item["id"]): item for item in value.get("rules", [])}
    if name == "finance_initialization":
        return {
            str(program_id): program for program_id, program in value.get("programs", {}).items()
        }
    if name == "specialization_pipeline":
        return {str(country["country_code"]): country for country in value.get("countries", [])}
    if name == "aggregate_statistics":
        return {str(value.get("version", "")): value}
    return {}


def _validate_content(content: dict[str, Any]) -> None:
    sources = [
        DefaultSourceRecord.model_validate_json(json.dumps(item))
        for item in content["default_sources"]
    ]
    source_ids = {item.id for item in sources}
    actions = [
        DefaultActionDefinition.model_validate_json(json.dumps(item))
        for item in content["default_actions"]
    ]
    _validate_exclusive_action_choices(actions)
    action_ids = {action.id for action in actions}
    for action in actions:
        unknown_sources = sorted(set(action.evidence.source_ids) - source_ids)
        if unknown_sources:
            raise ValueError(
                f"Default action {action.id} references unknown sources: "
                + ", ".join(unknown_sources)
            )
        duration_evidence = action.duration.evidence
        unknown_duration_sources = sorted(
            set(duration_evidence.source_ids if duration_evidence else ()) - source_ids
        )
        if unknown_duration_sources:
            raise ValueError(
                f"Default action {action.id} duration references unknown sources: "
                + ", ".join(unknown_duration_sources)
            )
        unknown_interruptions = sorted(set(action.emergency_interruptions) - action_ids)
        if unknown_interruptions:
            raise ValueError(
                f"Default action {action.id} references unknown emergency actions: "
                + ", ".join(unknown_interruptions)
            )
    agent_types = ConfirmedAgentTypeRegistry.model_validate_json(json.dumps(content["agent_types"]))
    trees = DecisionTreeRegistryDefinition.model_validate_json(
        json.dumps(content["decision_trees"])
    )
    tree_validation = DecisionTreeModuleRegistry(trees).validation
    if not tree_validation.valid:
        raise ValueError("Shipped default decision trees are invalid")
    routines = RoutineRegistryDefinition.model_validate_json(json.dumps(content["routines"]))
    routine_validation = validate_routines(
        routines,
        {module.id for module in trees.modules},
    )
    if not routine_validation.valid:
        raise ValueError("Shipped default routines are invalid")
    population = InitialPopulationMaterialization.model_validate_json(
        json.dumps(content["initial_population"])
    )
    population_validation = validate_initial_population(population.population)
    if not population_validation.valid:
        raise ValueError("Shipped default initial population is invalid")
    rules = [
        DefaultSeedingRule.model_validate_json(json.dumps(item))
        for item in content["initial_seeding_rules"]
    ]
    expected_agent_ids = {agent_id for rule in rules for agent_id in rule.expected_agent_ids}
    actual_agent_ids = {agent.agent_id for agent in population.population.agents}
    if expected_agent_ids != actual_agent_ids:
        raise ValueError("Default seeding rules do not match the initial population")
    [
        DefaultScenarioOverlay.model_validate_json(json.dumps(item))
        for item in content["scenario_overlays"]
    ]
    [
        InteractionTreeDefinition.model_validate_json(json.dumps(item))
        for item in content["interaction_trees"]
    ]
    InteractionProgramDefinition.model_validate_json(json.dumps(content["interaction_program"]))
    try:
        from .agent_state import AgentStateCatalog
    except ImportError:
        AgentStateCatalog = None
    if AgentStateCatalog is not None:
        from .agent_state import RelationshipStateCatalog

        state_catalog = AgentStateCatalog.model_validate_json(json.dumps(content["agent_states"]))
        definition_ids = {definition.id for definition in state_catalog.definitions}
        runtime_targets = {rule.target_state_id for rule in state_catalog.runtime_rules}
        if runtime_targets != definition_ids:
            raise ValueError("Shipped default agent states require one runtime rule per definition")
        RelationshipStateCatalog.model_validate_json(json.dumps(content["relationship_states"]))
    DefaultFinanceLedger.model_validate_json(json.dumps(content["finance_rules"]))
    FinanceInitializationCatalog.model_validate_json(json.dumps(content["finance_initialization"]))
    if "specialization_pipeline" in content:
        SpecializationCatalog.model_validate_json(json.dumps(content["specialization_pipeline"]))
    if "aggregate_statistics" in content:
        aggregates = AggregateStatisticsProgram.model_validate_json(
            json.dumps(content["aggregate_statistics"])
        )
        declared_actions = {
            contribution.action_id for contribution in aggregates.action_contributions
        }
        if declared_actions != {action.id for action in actions}:
            raise ValueError("Default aggregate statistics must declare every default action")
    try:
        from .coefficient_evidence import ActionCoefficientRegistry
    except ImportError:
        ActionCoefficientRegistry = None
    if ActionCoefficientRegistry is not None:
        ActionCoefficientRegistry.model_validate_json(json.dumps(content["coefficient_registry"]))
    if "person" not in {item.id for item in agent_types.types}:
        raise ValueError("Shipped default DSL requires the base Person type")


def _inventory(content: dict[str, Any]) -> DefaultDslInventory:
    return DefaultDslInventory(
        agent_type_ids=_section_ids("agent_types", content["agent_types"]),
        state_ids=_section_ids("agent_states", content["agent_states"]),
        relationship_state_ids=_section_ids("relationship_states", content["relationship_states"]),
        action_ids=_section_ids("default_actions", content["default_actions"]),
        routine_ids=_section_ids("routines", content["routines"]),
        decision_tree_ids=tuple(
            item.removeprefix("tree:")
            for item in _section_ids("decision_trees", content["decision_trees"])
            if item.startswith("tree:")
        ),
        interaction_tree_ids=_section_ids("interaction_trees", content["interaction_trees"]),
        initial_agent_ids=_section_ids("initial_population", content["initial_population"]),
    )


def load_shipped_default_dsl(path: str | Path | None = None) -> DefaultDslPackage:
    selected_path = Path(path or DEFAULT_DSL_PATH)
    manifest = DefaultDslManifest.model_validate_json(selected_path.read_text(encoding="utf-8"))
    calculated_hash = _canonical_hash(manifest.content)
    if calculated_hash != manifest.content_hash:
        raise ValueError(
            f"Shipped default DSL hash mismatch: expected {manifest.content_hash}, "
            f"calculated {calculated_hash}"
        )
    content = _resolve_self_hash(deepcopy(manifest.content), manifest.content_hash)
    missing = sorted(set(manifest.managed_sections) - content.keys())
    extra = sorted(set(content) - set(manifest.managed_sections))
    if missing or extra:
        raise ValueError(
            "Shipped default DSL managed sections differ from its content: "
            f"missing={missing}, extra={extra}"
        )
    _validate_content(content)
    receipt = DefaultDslReceipt(
        version=manifest.dsl_version,
        hash=manifest.content_hash,
        managed_sections=manifest.managed_sections,
    )
    return DefaultDslPackage(
        receipt=receipt,
        content=content,
        inventory=_inventory(content),
    )


class DefaultDslService:
    def __init__(
        self,
        store: SimulationRegistryStore,
        package: DefaultDslPackage | None = None,
    ):
        self.store = store
        self.package = package or load_shipped_default_dsl()
        self._reset_hooks: list[Callable[[], None]] = []

    def add_reset_hook(self, hook: Callable[[], None]) -> None:
        self._reset_hooks.append(hook)

    def adopt_installed(self) -> DefaultDslStatus:
        payload = self.store.payload_snapshot()
        receipt = self.store.default_dsl_receipt()
        if receipt is None:
            raise ValueError("Cannot adopt a default DSL before it is installed")
        missing = [section for section in receipt.managed_sections if section not in payload]
        if missing:
            raise ValueError(
                "Cannot adopt an incomplete default DSL; missing " + ", ".join(missing)
            )
        content = {section: deepcopy(payload[section]) for section in receipt.managed_sections}
        _validate_content(content)
        self.package = DefaultDslPackage(
            receipt=receipt,
            content=content,
            inventory=_inventory(content),
        )
        return self.status()

    def set_cached_pipeline_default(
        self,
        sections: dict[str, Any],
        pipeline_version: int,
    ) -> DefaultDslStatus:
        unexpected = sorted(set(sections) - set(self.package.receipt.managed_sections))
        if unexpected:
            raise ValueError(
                "Cached pipeline default contains unmanaged sections: " + ", ".join(unexpected)
            )
        content = deepcopy(self.package.content)
        content.update(deepcopy(sections))
        base_version = self.package.receipt.version.split("+pipeline-", 1)[0]
        derived_version = f"{base_version}+pipeline-{pipeline_version}"
        content = _restore_self_hash_placeholders(content, derived_version)
        content_hash = _canonical_hash(content)
        content = _resolve_self_hash(content, content_hash)
        _validate_content(content)
        receipt = self.package.receipt.model_copy(
            update={
                "version": derived_version,
                "hash": content_hash,
            }
        )
        self.package = DefaultDslPackage(
            receipt=receipt,
            content=content,
            inventory=_inventory(content),
        )
        return self.status()

    def ensure(self) -> DefaultDslStatus:
        self.store.install_default_dsl_if_fresh(
            self.package.content,
            self.package.receipt.model_dump(mode="json"),
        )
        return self.status()

    def status(self) -> DefaultDslStatus:
        payload = self.store.payload_snapshot()
        installed = self.store.default_dsl_receipt()
        drifted = tuple(
            section
            for section in self.package.receipt.managed_sections
            if payload.get(section) != self.package.content[section]
        )
        loaded = installed is not None
        intact = loaded and installed == self.package.receipt and not drifted
        return DefaultDslStatus(
            loaded=loaded,
            intact=intact,
            receipt=self.package.receipt,
            installed_receipt=installed,
            inventory=self.package.inventory,
            drifted_sections=drifted,
        )

    def preview_reset(self) -> DefaultDslResetPreview:
        payload = self.store.payload_snapshot()
        sections = []
        for name in self.package.receipt.managed_sections:
            current = payload.get(name)
            default = self.package.content[name]
            current_ids = _section_ids(name, current)
            default_ids = _section_ids(name, default)
            current_records = _section_records(name, current)
            default_records = _section_records(name, default)
            changed_shared_ids = {
                item_id
                for item_id in current_records.keys() & default_records.keys()
                if current_records[item_id] != default_records[item_id]
            }
            if current is None:
                disposition = "restore"
            elif current == default:
                disposition = "unchanged"
            else:
                disposition = "replace"
            sections.append(
                DefaultDslSectionPreview(
                    name=name,
                    disposition=disposition,
                    current_count=len(current_ids),
                    default_count=len(default_ids),
                    current_ids=current_ids,
                    default_ids=default_ids,
                    restored_ids=(
                        tuple(sorted((set(default_ids) - set(current_ids)) | changed_shared_ids))
                        if disposition != "unchanged"
                        else ()
                    ),
                    replaced_ids=(
                        tuple(sorted((set(current_ids) - set(default_ids)) | changed_shared_ids))
                        if disposition == "replace"
                        else ()
                    ),
                )
            )
        return DefaultDslResetPreview(
            changed=any(item.disposition != "unchanged" for item in sections),
            receipt=self.package.receipt,
            sections=tuple(sections),
        )

    def reset(self, request: ResetDefaultDslRequest) -> DefaultDslStatus:
        if request.expected_hash != self.package.receipt.hash:
            raise ValueError(
                "Default DSL reset hash is stale; preview the current shipped default first"
            )
        self.store.replace_default_dsl(
            self.package.content,
            self.package.receipt.model_dump(mode="json"),
        )
        for hook in self._reset_hooks:
            hook()
        return self.status()


def create_default_dsl_router(service: DefaultDslService) -> APIRouter:
    router = APIRouter(prefix="/simulation/default-dsl", tags=["Default DSL"])

    @router.get("", response_model=DefaultDslStatus)
    def status() -> DefaultDslStatus:
        return service.ensure()

    @router.post("/reset/preview", response_model=DefaultDslResetPreview)
    def preview_reset() -> DefaultDslResetPreview:
        return service.preview_reset()

    @router.post("/reset", response_model=DefaultDslStatus)
    def reset(request: ResetDefaultDslRequest) -> DefaultDslStatus:
        try:
            return service.reset(request)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    return router
