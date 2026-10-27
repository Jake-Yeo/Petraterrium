from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .compatibility import compatibility_dsl
from .contracts import DailySnapshot, PlaceSnapshot, RunConfig
from .data import DATA_VERSION
from .dsl import DSLConfig, OutputSpec, PopulationReference, ProbabilitySpec, TickConfig

PERIOD_HOURS = {"event": 1, "hour": 1, "day": 24, "week": 168, "year": 8760}
StateArray = NDArray[np.int64]


@dataclass(frozen=True)
class RuntimeSpec:
    dsl: DSLConfig
    population: PopulationReference
    tick: TickConfig
    outputs: OutputSpec


@dataclass
class RuntimeState:
    places: list[str]
    values: dict[str, StateArray]


def resolve_runtime(config: RunConfig) -> RuntimeSpec:
    dsl = config.dsl or compatibility_dsl(config)
    population = config.population or dsl.population
    tick = config.tick or dsl.tick
    outputs = config.outputs or dsl.outputs
    replacements = {}
    if population != dsl.population:
        replacements["population"] = population
    if tick != dsl.tick:
        replacements["tick"] = tick
    if outputs != dsl.outputs:
        replacements["outputs"] = outputs
    if replacements:
        dsl = dsl.model_copy(update=replacements)
    return RuntimeSpec(dsl=dsl, population=population, tick=tick, outputs=outputs)


def place_populations(population: PopulationReference) -> dict[str, int]:
    if population.place_populations:
        return {place: population.place_populations[place] for place in population.places}
    base, remainder = divmod(population.size, len(population.places))
    return {place: base + int(index < remainder) for index, place in enumerate(population.places)}


def initial_runtime_state(spec: RuntimeSpec, rng: np.random.Generator) -> RuntimeState:
    populations = place_populations(spec.population)
    values = {}
    for state in spec.dsl.states:
        counts = np.zeros((len(spec.population.places), len(state.values)), dtype=np.int64)
        probabilities = np.array(list(state.initial.values.values()), dtype=float)
        nonzero = np.flatnonzero(probabilities)
        for place_index, place in enumerate(spec.population.places):
            override = spec.population.initial_state_overrides.get(place, {}).get(state.id)
            if override is not None:
                counts[place_index] = [override.get(value, 0) for value in state.values]
            elif len(nonzero) == 1:
                counts[place_index, nonzero[0]] = populations[place]
            else:
                counts[place_index] = rng.multinomial(populations[place], probabilities)
        values[state.id] = counts
    return RuntimeState(places=list(spec.population.places), values=values)


def scaled_probability(base: NDArray[np.float64], spec: ProbabilitySpec, tick_hours: float):
    exposure = 1 if spec.time_unit == "event" else tick_hours / PERIOD_HOURS[spec.time_unit]
    if spec.mode == "hazard":
        return -np.expm1(-base * exposure)
    return 1 - np.power(1 - np.clip(base, 0, 1), exposure)


def transition_probabilities(
    runtime: RuntimeSpec,
    state: RuntimeState,
    state_id: str,
    value_names: list[str],
    probability: ProbabilitySpec,
) -> NDArray[np.float64]:
    parameters = {item.id: item.value for item in runtime.dsl.parameters}
    base_value = (
        parameters.get(probability.parameter) if probability.parameter else probability.base
    )
    if base_value is None:
        raise ValueError(f"Parameter {probability.parameter} has no fitted value")
    base = np.full(len(state.places), float(base_value), dtype=float)
    if probability.source_state:
        source_index = value_names.index(probability.source_state)
        counts = state.values[state_id]
        populations = counts.sum(axis=1)
        local = np.divide(
            counts[:, source_index],
            populations,
            out=np.zeros(len(state.places), dtype=float),
            where=populations > 0,
        )
        global_prevalence = counts[:, source_index].sum() / max(1, populations.sum())
        mixing = 0.0
        if probability.mixing_parameter:
            raw_mixing = parameters.get(probability.mixing_parameter)
            if raw_mixing is None:
                raise ValueError(f"Parameter {probability.mixing_parameter} has no fitted value")
            mixing = float(raw_mixing)
        base *= (1 - mixing) * local + mixing * global_prevalence
    return np.clip(scaled_probability(base, probability, runtime.tick.tick_hours), 0, 1)


def step_runtime(
    runtime: RuntimeSpec,
    state: RuntimeState,
    rng: np.random.Generator,
) -> RuntimeState:
    next_values = {state_id: values.copy() for state_id, values in state.values.items()}
    state_definitions = {definition.id: definition for definition in runtime.dsl.states}
    for system in runtime.dsl.systems:
        definition = state_definitions[system.state]
        current = state.values[system.state]
        target = next_values[system.state]
        grouped = {}
        for transition in system.transitions:
            grouped.setdefault(transition.from_state, []).append(transition)
        for source_name, transitions in grouped.items():
            source_index = definition.values.index(source_name)
            probabilities = [
                transition_probabilities(
                    runtime,
                    state,
                    system.state,
                    definition.values,
                    transition.probability,
                )
                for transition in transitions
            ]
            if len(transitions) == 1:
                moved = rng.binomial(current[:, source_index], probabilities[0])
                target[:, source_index] -= moved
                destination = definition.values.index(transitions[0].to_state)
                target[:, destination] += moved
                continue
            matrix = np.stack(probabilities, axis=1)
            if np.any(matrix.sum(axis=1) > 1 + 1e-12):
                raise ValueError(f"Outgoing transition probabilities from {source_name} exceed 1")
            for place_index, source_count in enumerate(current[:, source_index]):
                options = [*matrix[place_index], 1 - matrix[place_index].sum()]
                moves = rng.multinomial(int(source_count), options)[:-1]
                target[place_index, source_index] -= moves.sum()
                for transition, moved in zip(transitions, moves, strict=True):
                    destination = definition.values.index(transition.to_state)
                    target[place_index, destination] += moved
    return RuntimeState(places=list(state.places), values=next_values)


def place_snapshot(runtime: RuntimeSpec, state: RuntimeState, place_index: int) -> PlaceSnapshot:
    nested = {}
    metrics = {}
    for definition in runtime.dsl.states:
        values = {
            name: int(state.values[definition.id][place_index, value_index])
            for value_index, name in enumerate(definition.values)
        }
        nested[definition.id] = values
        for name, count in values.items():
            metrics[name] = metrics.get(name, 0) + count
    names = {
        name: int(metrics.get(name, 0))
        for name in (
            "susceptible",
            "exposed",
            "infected",
            "recovered",
        )
    }
    return PlaceSnapshot(
        country=state.places[place_index],
        latitude=runtime.population.place_coordinates.get(state.places[place_index], (None, None))[
            0
        ],
        longitude=runtime.population.place_coordinates.get(state.places[place_index], (None, None))[
            1
        ],
        states=nested,
        metrics={name: float(value) for name, value in metrics.items()},
        **names,
    )


def snapshot(
    runtime: RuntimeSpec,
    state: RuntimeState,
    config: RunConfig,
    run_id: str,
    engine_version: str,
    tick_index: int,
) -> DailySnapshot:
    elapsed_hours = tick_index * runtime.tick.tick_hours
    return DailySnapshot(
        run_id=run_id,
        day=config.start_day + int(elapsed_hours // 24),
        places=[place_snapshot(runtime, state, index) for index in range(len(state.places))],
        seed=config.seed,
        engine_version=engine_version,
        data_version=DATA_VERSION,
        config_hash=run_id,
        tick=tick_index,
        elapsed_hours=elapsed_hours,
    )


def simulate_runtime(
    config: RunConfig,
    run_id: str,
    engine_version: str,
) -> Iterator[DailySnapshot]:
    runtime = resolve_runtime(config)
    rng = np.random.default_rng(config.seed)
    state = initial_runtime_state(runtime, rng)
    yield snapshot(runtime, state, config, run_id, engine_version, 0)
    for tick_index in range(1, runtime.tick.total_ticks + 1):
        state = step_runtime(runtime, state, rng)
        elapsed_hours = tick_index * runtime.tick.tick_hours
        snapshot_due = elapsed_hours % runtime.tick.snapshot_every_hours == 0
        if snapshot_due or tick_index == runtime.tick.total_ticks:
            yield snapshot(runtime, state, config, run_id, engine_version, tick_index)
