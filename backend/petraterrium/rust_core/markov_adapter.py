from collections.abc import Mapping, Sequence
from typing import Any

from ..markov import CompilationResult, MarkovProgram, ModuleInput
from .bridge import RustCoreError


def compiled_markov_request(
    program: MarkovProgram,
    compilation: CompilationResult,
    *,
    seed: int,
    ticks: int,
    tick_hours: float,
    agents: Mapping[str, Any],
    places: Sequence[Mapping[str, Any]],
    start_hour: float = 0,
    start_weekday: int = 0,
    input_bindings: Mapping[str, str] | None = None,
    network: Mapping[str, Any] | None = None,
    schedules: Sequence[Mapping[str, Any]] = (),
    meaningful_actions: Sequence[Mapping[str, Any]] = (),
    synchronization: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    unresolved = [
        probability
        for probability in compilation.probabilities
        if probability.status != "resolved" or probability.probability is None
    ]
    if unresolved:
        identities = ", ".join(
            f"{item.module_id}.{item.transition_id}" for item in unresolved
        )
        raise RustCoreError(
            "UNRESOLVED_MARKOV_PROBABILITY",
            f"Rust execution requires resolved evidence for: {identities}",
        )
    if not compilation.executable:
        detail = "; ".join(issue.message for issue in compilation.issues)
        raise RustCoreError(
            "MARKOV_COMPILATION_NOT_EXECUTABLE",
            detail or "Compiled Markov program is not executable",
        )
    module_models = {module.id: module for module in program.modules}
    bindings = dict(input_bindings or {})
    place_rows = [dict(place) for place in places]
    encoded_agents, trait_dictionaries = _encoded_agents(agents)
    modules = [
        _module_request(
            module,
            module_models,
            compilation,
            bindings,
            place_rows,
            trait_dictionaries,
        )
        for module in compilation.modules
    ]
    routes = [
        {
            "from_module": link.from_module,
            "exit_state": link.exit_state,
            "to_module": link.to_module,
        }
        for link in program.links
    ]
    return {
        "seed": seed,
        "ticks": ticks,
        "tick_hours": tick_hours,
        "start_hour": start_hour,
        "start_weekday": start_weekday,
        "places": place_rows,
        "agents": encoded_agents,
        "modules": modules,
        "routes": routes,
        "network": dict(network) if network is not None else None,
        "schedules": [dict(schedule) for schedule in schedules],
        "meaningful_actions": [dict(action) for action in meaningful_actions],
        "synchronization": dict(synchronization or {}),
    }


def _module_request(
    compiled_module,
    module_models,
    compilation: CompilationResult,
    input_bindings: Mapping[str, str],
    places: Sequence[Mapping[str, Any]],
    trait_dictionaries: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    source_module = module_models.get(compiled_module.id)
    if source_module is None:
        raise RustCoreError(
            "MARKOV_ADAPTER_MISMATCH",
            f"Compiled module {compiled_module.id} is absent from the source program",
        )
    state_names = _ordered_state_names(compiled_module.state_indices)
    if any(state.effects for state in source_module.states):
        raise RustCoreError(
            "UNRESOLVED_MARKOV_EFFECT",
            f"Module {compiled_module.id} has state effects without numeric effect values",
        )
    source_inputs = {item.id: item for item in source_module.inputs}
    used_inputs: set[str] = set()
    source_transitions = {transition.id: transition for transition in source_module.transitions}
    transitions = []
    for transition in compiled_module.transitions:
        source_transition = source_transitions.get(transition.id)
        if source_transition is None:
            raise RustCoreError(
                "MARKOV_ADAPTER_MISMATCH",
                (
                    f"Compiled transition {compiled_module.id}.{transition.id} "
                    "is absent from the source program"
                ),
            )
        probability = _compiled_probability(compilation, transition.probability_index)
        conditions = _conditions(
            transition.condition,
            source_inputs,
            input_bindings,
            used_inputs,
            trait_dictionaries,
        )
        conditions.extend(
            _evidence_context_conditions(
                source_transition,
                source_inputs,
                compilation,
                input_bindings,
                places,
                used_inputs,
                trait_dictionaries,
            )
        )
        transitions.append(
            {
                "id": transition.id,
                "from_state": state_names[transition.source_index],
                "to_state": state_names[transition.target_index],
                "rules": [
                    {
                        "conditions": conditions,
                        "probability": probability.probability,
                        "provenance": {
                            "source": probability.provenance.source,
                            "version": probability.provenance.version,
                            "status": _engine_evidence_status(probability),
                            "uncertainty": probability.provenance.uncertainty,
                            "source_date": probability.provenance.source_date,
                            "evidence_id": probability.evidence_id,
                            "evidence_kind": probability.evidence_kind,
                            "ci_low": probability.ci_low,
                            "ci_high": probability.ci_high,
                        },
                    }
                ],
                "effects": [],
            }
        )
    return {
        "id": compiled_module.id,
        "entry_state": state_names[compiled_module.entry_index],
        "exit_states": [state_names[index] for index in compiled_module.exit_indices],
        "inputs": sorted(used_inputs),
        "outputs": [],
        "states": state_names,
        "transitions": transitions,
    }


def _ordered_state_names(state_indices: Mapping[str, int]) -> list[str]:
    ordered = [None] * len(state_indices)
    for state, index in state_indices.items():
        if index >= len(ordered) or ordered[index] is not None:
            raise RustCoreError(
                "MARKOV_ADAPTER_MISMATCH",
                "Compiled state indices must be contiguous and unique",
            )
        ordered[index] = state
    if any(state is None for state in ordered):
        raise RustCoreError(
            "MARKOV_ADAPTER_MISMATCH",
            "Compiled state indices must be contiguous and unique",
        )
    return [state for state in ordered if state is not None]


def _compiled_probability(compilation: CompilationResult, index: int):
    try:
        probability = compilation.probabilities[index]
    except IndexError as error:
        raise RustCoreError(
            "MARKOV_ADAPTER_MISMATCH",
            f"Compiled probability index {index} is out of range",
        ) from error
    if probability.status != "resolved" or probability.probability is None:
        raise RustCoreError(
            "UNRESOLVED_MARKOV_PROBABILITY",
            f"Probability {probability.module_id}.{probability.transition_id} is unresolved",
        )
    return probability


def _engine_evidence_status(probability) -> str:
    if probability.evidence_kind == "pipeline_estimate":
        return "default_estimated"
    return probability.provenance.status


def _conditions(
    condition,
    source_inputs: Mapping[str, ModuleInput],
    input_bindings: Mapping[str, str],
    used_inputs: set[str],
    trait_dictionaries: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if condition.mode == "always":
        return []
    if condition.mode != "all":
        raise RustCoreError(
            "UNSUPPORTED_MARKOV_CONDITION",
            "Rust integration currently requires all-mode numeric conditions",
        )
    result = []
    for clause in condition.clauses:
        if clause.operator == "in" or isinstance(clause.value, list):
            raise RustCoreError(
                "UNSUPPORTED_MARKOV_CONDITION",
                f"Condition {clause.input_id} must use a scalar comparison",
            )
        input_path = _input_path(clause.input_id, source_inputs, input_bindings)
        used_inputs.add(input_path)
        result.append(
            {
                "input": input_path,
                "operator": clause.operator,
                "value": _encoded_condition_value(
                    input_path,
                    clause.value,
                    clause.operator,
                    trait_dictionaries,
                ),
            }
        )
    return result


def _evidence_context_conditions(
    transition,
    source_inputs: Mapping[str, ModuleInput],
    compilation: CompilationResult,
    input_bindings: Mapping[str, str],
    places: Sequence[Mapping[str, Any]],
    used_inputs: set[str],
    trait_dictionaries: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    context = compilation.context
    query = transition.probability
    conditions = []
    place_ids = [str(place.get("id", "")) for place in places]
    try:
        place_index = place_ids.index(context.place)
    except ValueError as error:
        raise RustCoreError(
            "MISSING_MARKOV_PLACE",
            f"Compilation place {context.place} is absent from the Rust place shards",
        ) from error
    place_path = _input_path(query.place_input, source_inputs, input_bindings)
    used_inputs.add(place_path)
    conditions.append({"input": place_path, "operator": "eq", "value": float(place_index)})
    if context.time_unit == "friday":
        time_path = _input_path(query.time_input, source_inputs, input_bindings)
        used_inputs.add(time_path)
        conditions.append({"input": time_path, "operator": "eq", "value": 4.0})
    for input_id in query.predictor_inputs:
        input_value = source_inputs[input_id]
        feature_id = input_value.feature_id or input_id
        value = context.strata.get(feature_id, context.strata.get(input_id))
        conditions.append(
            _context_condition(
                input_id,
                value,
                source_inputs,
                input_bindings,
                used_inputs,
                trait_dictionaries,
            )
        )
    for input_id, value in context.conditions.items():
        conditions.append(
            _context_condition(
                input_id,
                value,
                source_inputs,
                input_bindings,
                used_inputs,
                trait_dictionaries,
            )
        )
    unique = {}
    for condition in conditions:
        key = (condition["input"], condition["operator"], condition["value"])
        unique[key] = condition
    return list(unique.values())


def _context_condition(
    input_id: str,
    value: Any,
    source_inputs: Mapping[str, ModuleInput],
    input_bindings: Mapping[str, str],
    used_inputs: set[str],
    trait_dictionaries: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    input_path = _input_path(input_id, source_inputs, input_bindings)
    used_inputs.add(input_path)
    return {
        "input": input_path,
        "operator": "eq",
        "value": _encoded_condition_value(
            input_path,
            value,
            "eq",
            trait_dictionaries,
        ),
    }


def _encoded_agents(
    agents: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    payload = dict(agents)
    raw_traits = payload.get("traits", {})
    raw_dictionaries = payload.get("trait_dictionaries", {})
    if not isinstance(raw_traits, Mapping):
        raise RustCoreError("INVALID_AGENT_TRAITS", "Agent traits must be an object")
    if not isinstance(raw_dictionaries, Mapping):
        raise RustCoreError(
            "INVALID_CATEGORICAL_DICTIONARY",
            "Trait dictionaries must be an object",
        )
    dictionaries = {
        str(name): _validated_dictionary(str(name), value)
        for name, value in raw_dictionaries.items()
    }
    encoded_traits = {}
    for name, raw_column in raw_traits.items():
        if isinstance(raw_column, (str, bytes)) or not isinstance(raw_column, Sequence):
            raise RustCoreError(
                "INVALID_AGENT_TRAIT_COLUMN",
                f"Trait {name} must contain one value per agent",
            )
        column = list(raw_column)
        if any(isinstance(value, str) for value in column):
            dictionary = dictionaries.get(str(name))
            if dictionary is None:
                raise RustCoreError(
                    "MISSING_CATEGORICAL_DICTIONARY",
                    f"Categorical trait {name} requires a versioned dictionary",
                )
            codes = {value: index for index, value in enumerate(dictionary["values"])}
            encoded_column = []
            for value in column:
                if not isinstance(value, str) or value not in codes:
                    detail = (
                        f"Trait {name} value {value!r} is absent from dictionary "
                        f"{dictionary['version']}"
                    )
                    raise RustCoreError(
                        "UNKNOWN_CATEGORICAL_VALUE",
                        detail,
                    )
                encoded_column.append(float(codes[value]))
            encoded_traits[str(name)] = encoded_column
        else:
            encoded_traits[str(name)] = column
    payload["traits"] = encoded_traits
    payload["trait_dictionaries"] = dictionaries
    return payload, dictionaries


def _validated_dictionary(name: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RustCoreError(
            "INVALID_CATEGORICAL_DICTIONARY",
            f"Trait dictionary {name} must be an object",
        )
    source = value.get("source")
    version = value.get("version")
    values = value.get("values")
    if (
        not isinstance(source, str)
        or not source.strip()
        or not isinstance(version, str)
        or not version.strip()
        or isinstance(values, (str, bytes))
        or not isinstance(values, Sequence)
    ):
        raise RustCoreError(
            "INVALID_CATEGORICAL_DICTIONARY",
            f"Trait dictionary {name} requires source, version, and ordered values",
        )
    labels = list(values)
    if not labels or any(not isinstance(label, str) or not label for label in labels):
        raise RustCoreError(
            "INVALID_CATEGORICAL_DICTIONARY",
            f"Trait dictionary {name} values must be non-empty labels",
        )
    if len(set(labels)) != len(labels):
        raise RustCoreError(
            "INVALID_CATEGORICAL_DICTIONARY",
            f"Trait dictionary {name} contains duplicate labels",
        )
    return {"source": source, "version": version, "values": labels}


def _encoded_condition_value(
    input_path: str,
    value: Any,
    operator: str,
    trait_dictionaries: Mapping[str, Mapping[str, Any]],
) -> float:
    if isinstance(value, (bool, int, float)):
        return float(value)
    if not isinstance(value, str) or not input_path.startswith("trait."):
        raise RustCoreError(
            "UNSUPPORTED_MARKOV_CONTEXT_VALUE",
            f"Rust execution cannot encode {value!r} for {input_path}",
        )
    if operator not in {"eq", "ne"}:
        raise RustCoreError(
            "INVALID_CATEGORICAL_OPERATOR",
            f"Categorical input {input_path} supports only eq and ne",
        )
    trait_name = input_path.removeprefix("trait.")
    dictionary = trait_dictionaries.get(trait_name)
    if dictionary is None:
        raise RustCoreError(
            "MISSING_CATEGORICAL_DICTIONARY",
            f"Categorical trait {trait_name} requires a versioned dictionary",
        )
    try:
        return float(dictionary["values"].index(value))
    except ValueError as error:
        raise RustCoreError(
            "UNKNOWN_CATEGORICAL_VALUE",
            f"Trait {trait_name} value {value!r} is absent from dictionary {dictionary['version']}",
        ) from error


def _input_path(
    identity: str,
    source_inputs: Mapping[str, ModuleInput],
    input_bindings: Mapping[str, str],
) -> str:
    if identity in input_bindings:
        return input_bindings[identity]
    input_value = source_inputs.get(identity)
    if input_value is None:
        raise RustCoreError(
            "MARKOV_ADAPTER_MISMATCH",
            f"Condition references undeclared input {identity}",
        )
    if input_value.kind == "agent_trait":
        return f"trait.{input_value.feature_id or input_value.id}"
    if input_value.kind == "persisted_state":
        return f"memory.{input_value.id}"
    if input_value.kind in {"place_state", "media_state"}:
        return f"place.{input_value.id}"
    if input_value.kind == "place":
        return "place.index"
    if input_value.kind in {"time", "context"}:
        if input_value.id in {"day", "weekday"}:
            return "context.weekday"
        if input_value.id in {"hour", "time", "time-of-day"}:
            return "context.hour"
    raise RustCoreError(
        "MISSING_MARKOV_INPUT_BINDING",
        f"Input {identity} requires an explicit Rust input binding",
    )
