import json
from importlib import import_module
from pathlib import Path

import yaml

from .models import (
    ActionDefinition,
    AggregateBenchmark,
    AttributeDefinition,
    BehaviourBundle,
    BundleResolution,
    ChainBranch,
    ChainDefinition,
    ChoiceCondition,
    ChoiceEvidence,
    CouplingDefinition,
    DefaultDefinition,
    Distribution,
    DSLConfig,
    DSLValidationResult,
    EventDefinition,
    Evidence,
    FeatureDefinition,
    FeatureDistribution,
    FeatureRange,
    FeatureRegistry,
    GraphTraversal,
    JointDataProof,
    LeaderActionDefinition,
    MediaRule,
    NetworkDefinition,
    OutputSpec,
    ParameterDefinition,
    PlaceHierarchy,
    PopulationReference,
    ProbabilitySpec,
    RoleDefinition,
    RuleCondition,
    RuleDefinition,
    ScenarioDefinition,
    SliderSpec,
    StateDefinition,
    SystemDefinition,
    TickConfig,
    TransitionDefinition,
)
from .validator import validate_dsl

markov_models = import_module("petraterrium.markov.models")
builder_models = import_module("petraterrium.markov_builder.models")
MarkovProgram = markov_models.MarkovProgram
TransitionEvidence = markov_models.TransitionEvidence
ConfirmedChainGraph = builder_models.ConfirmedChainGraph

DSLConfig.model_rebuild(
    _types_namespace={
        "ConfirmedChainGraph": ConfirmedChainGraph,
        "MarkovProgram": MarkovProgram,
        "TransitionEvidence": TransitionEvidence,
    }
)


def load_dsl(value: DSLConfig | dict | str | Path) -> DSLConfig:
    if isinstance(value, DSLConfig):
        config = value
    elif isinstance(value, Path):
        contents = value.read_text()
        config = (
            DSLConfig.model_validate(yaml.safe_load(contents))
            if value.suffix.casefold() in {".yaml", ".yml"}
            else DSLConfig.model_validate_json(contents)
        )
    elif isinstance(value, str):
        stripped = value.lstrip()
        if stripped.startswith(("{", "[")):
            config = DSLConfig.model_validate(json.loads(value))
        elif "\n" in value or ":" in value:
            config = DSLConfig.model_validate(yaml.safe_load(value))
        else:
            config = load_dsl(Path(value))
    else:
        config = DSLConfig.model_validate(value)
    result = validate_dsl(config)
    if not result.valid:
        raise ValueError("; ".join(result.error_messages))
    return config


def flatten_behaviour_bundles(
    selected: list[str], bundles: dict[str, BehaviourBundle]
) -> BundleResolution:
    values = {}
    provenance = {}
    active = set()

    def apply(identity: str):
        if identity in active:
            raise ValueError(f"Behaviour inheritance cycle at {identity}")
        bundle = bundles.get(identity)
        if bundle is None:
            raise ValueError(f"Unknown behaviour bundle {identity}")
        active.add(identity)
        for parent in bundle.inherits:
            apply(parent)
        active.remove(identity)
        for key, value in bundle.values.items():
            values[key] = value
            provenance[key] = bundle.provenance

    for identity in selected:
        apply(identity)
    return BundleResolution(values=values, provenance=provenance)


def render_plain_language(dsl: DSLConfig) -> str:
    systems = ", ".join(system.id for system in dsl.systems)
    actions = ", ".join(action.id for action in dsl.actions) or "no configured actions"
    return (
        f"{dsl.id} runs {systems} for {dsl.tick.total_ticks} ticks of "
        f"{dsl.tick.tick_hours:g} hours. It exposes {actions}. Population "
        f"{dsl.population.id} contains {dsl.population.size:,} synthetic agents."
    )


def render_sliders(dsl: DSLConfig) -> list[SliderSpec]:
    return [
        SliderSpec(
            parameter=parameter.id,
            value=parameter.value,
            unit=parameter.unit,
            evidence_status=parameter.provenance.status,
        )
        for parameter in dsl.parameters
        if parameter.value is not None
    ]


__all__ = [
    "ActionDefinition",
    "AggregateBenchmark",
    "AttributeDefinition",
    "BehaviourBundle",
    "BundleResolution",
    "ChainBranch",
    "ChainDefinition",
    "ChoiceCondition",
    "ChoiceEvidence",
    "CouplingDefinition",
    "DefaultDefinition",
    "Distribution",
    "DSLConfig",
    "DSLValidationResult",
    "EventDefinition",
    "Evidence",
    "FeatureDefinition",
    "FeatureDistribution",
    "FeatureRange",
    "FeatureRegistry",
    "GraphTraversal",
    "JointDataProof",
    "LeaderActionDefinition",
    "MarkovProgram",
    "MediaRule",
    "NetworkDefinition",
    "OutputSpec",
    "ParameterDefinition",
    "PlaceHierarchy",
    "PopulationReference",
    "ProbabilitySpec",
    "RoleDefinition",
    "RuleCondition",
    "RuleDefinition",
    "ScenarioDefinition",
    "SliderSpec",
    "StateDefinition",
    "SystemDefinition",
    "TickConfig",
    "TransitionDefinition",
    "TransitionEvidence",
    "flatten_behaviour_bundles",
    "load_dsl",
    "render_plain_language",
    "render_sliders",
    "validate_dsl",
]
