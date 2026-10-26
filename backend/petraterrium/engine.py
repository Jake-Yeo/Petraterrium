from collections.abc import Iterator

import numpy as np
from numpy.typing import NDArray

from .contracts import DailySnapshot, Parameters, PlaceSnapshot, RunConfig
from .data import COUNTRY_BY_CODE, DATA_VERSION

State = NDArray[np.int64]
ENGINE_MODEL = "placeholder-seir-v1"


def initial_state(config: RunConfig) -> State:
    state = np.zeros((len(config.countries), 4), dtype=np.int64)
    state[:, 0] = [COUNTRY_BY_CODE[c].population for c in config.countries]
    origin = config.countries.index("ITA") if "ITA" in config.countries else 0
    state[origin, 0] -= config.parameters.initial_infected
    state[origin, 2] = config.parameters.initial_infected
    return state


def step(state: State, params: Parameters, rng: np.random.Generator) -> State:
    populations = state.sum(axis=1)
    prevalence = state[:, 2] / populations
    shared_prevalence = state[:, 2].sum() / populations.sum()
    force = params.transmission * (
        (1 - params.mixing) * prevalence + params.mixing * shared_prevalence
    )
    exposed = rng.binomial(state[:, 0], -np.expm1(-force))
    infected = rng.binomial(state[:, 1], -np.expm1(-params.progression))
    recovered = rng.binomial(state[:, 2], -np.expm1(-params.recovery))
    next_state = state.copy()
    next_state[:, 0] -= exposed
    next_state[:, 1] += exposed - infected
    next_state[:, 2] += infected - recovered
    next_state[:, 3] += recovered
    return next_state


def simulate(config: RunConfig, run_id: str, engine_version: str) -> Iterator[DailySnapshot]:
    rng = np.random.default_rng(config.seed)
    state = initial_state(config)
    for day in range(config.start_day, config.end_day + 1):
        yield DailySnapshot(
            run_id=run_id,
            day=day,
            places=[
                PlaceSnapshot(
                    country=country,
                    susceptible=int(values[0]),
                    exposed=int(values[1]),
                    infected=int(values[2]),
                    recovered=int(values[3]),
                )
                for country, values in zip(config.countries, state, strict=True)
            ],
            seed=config.seed,
            engine_version=engine_version,
            data_version=DATA_VERSION,
        )
        if day < config.end_day:
            state = step(state, config.parameters, rng)
