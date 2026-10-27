from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass

from .compatibility import compatibility_dsl
from .contracts import DailySnapshot, PlaceSnapshot, RunConfig
from .data import DATA_VERSION
from .dsl import DSLConfig, OutputSpec, PopulationReference, TickConfig
from .rust_core import RustCoreClient


@dataclass(frozen=True)
class RuntimeSpec:
    dsl: DSLConfig
    population: PopulationReference
    tick: TickConfig
    outputs: OutputSpec


@dataclass(frozen=True)
class RuntimeState:
    places: list[str]
    values: dict[str, list[list[int]]]


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


def runtime_state(
    runtime: RuntimeSpec,
    places: Sequence[str],
    raw_states: Mapping[str, Sequence[Sequence[int]]],
) -> RuntimeState:
    expected_states = {definition.id for definition in runtime.dsl.states}
    if list(places) != runtime.population.places:
        raise ValueError("Rust engine returned a different place order than the DSL")
    if set(raw_states) != expected_states:
        raise ValueError("Rust engine returned a different state set than the DSL")
    values = {
        state_id: [[int(count) for count in place] for place in counts]
        for state_id, counts in raw_states.items()
    }
    for definition in runtime.dsl.states:
        counts = values[definition.id]
        if len(counts) != len(places) or any(
            len(place) != len(definition.values) for place in counts
        ):
            raise ValueError(f"Rust engine returned an invalid matrix for state {definition.id}")
    return RuntimeState(places=list(places), values=values)


def place_snapshot(runtime: RuntimeSpec, state: RuntimeState, place_index: int) -> PlaceSnapshot:
    nested = {}
    metrics: dict[str, int] = {}
    for definition in runtime.dsl.states:
        values = {
            name: state.values[definition.id][place_index][value_index]
            for value_index, name in enumerate(definition.values)
        }
        nested[definition.id] = values
        for name, count in values.items():
            metrics[name] = metrics.get(name, 0) + count
    names = {
        name: metrics.get(name, 0)
        for name in ("susceptible", "exposed", "infected", "recovered")
    }
    coordinates = runtime.population.place_coordinates.get(
        state.places[place_index], (None, None)
    )
    return PlaceSnapshot(
        country=state.places[place_index],
        latitude=coordinates[0],
        longitude=coordinates[1],
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
    result = RustCoreClient().run_aggregate_dsl(runtime.dsl, seed=config.seed)
    if result.get("seed") != config.seed:
        raise ValueError("Rust engine returned a different seed than the run config")
    if result.get("tick_hours") != runtime.tick.tick_hours:
        raise ValueError("Rust engine returned a different tick duration than the DSL")
    expected_values = {
        definition.id: definition.values for definition in runtime.dsl.states
    }
    if result.get("state_values") != expected_values:
        raise ValueError("Rust engine returned a different state-value order than the DSL")
    for raw_snapshot in result["snapshots"]:
        state = runtime_state(runtime, result["places"], raw_snapshot["states"])
        yield snapshot(
            runtime,
            state,
            config,
            run_id,
            engine_version,
            int(raw_snapshot["tick"]),
        )
