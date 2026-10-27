import json
from pathlib import Path

import numpy as np
import pytest

from petraterrium.contracts import Parameters, RunConfig
from petraterrium.engine import initial_state, simulate, step
from petraterrium.versions import config_hash

GOLDEN_CONFIG = RunConfig(countries=["ITA", "FRA", "DEU", "ESP"], start_day=7, end_day=14, seed=42)
GOLDEN_VERSION = "golden-placeholder-seir-v1"


def golden_bytes() -> bytes:
    identity = config_hash(GOLDEN_CONFIG, engine_version=GOLDEN_VERSION)
    snapshots = list(simulate(GOLDEN_CONFIG, identity, GOLDEN_VERSION))
    return ("\n".join(snapshot.model_dump_json() for snapshot in snapshots) + "\n").encode()


def test_zero_transmission_produces_no_new_infections():
    state = np.array([[990, 0, 10, 0], [1000, 0, 0, 0]], dtype=np.int64)
    result = step(state, Parameters(transmission=0), np.random.default_rng(42))
    np.testing.assert_array_equal(result[:, 0], state[:, 0])
    np.testing.assert_array_equal(result[:, 1], [0, 0])
    assert result[:, 2].sum() <= 10


def test_all_zero_rates_produce_identical_state():
    state = np.array([[950, 20, 10, 20]], dtype=np.int64)
    result = step(
        state, Parameters(transmission=0, progression=0, recovery=0), np.random.default_rng(0)
    )
    np.testing.assert_array_equal(result, state)


@pytest.mark.parametrize("seed", range(10))
def test_population_conservation_nonnegative_compartments_and_monotonicity(seed):
    config = RunConfig(
        countries=["ITA", "FRA", "DEU", "ESP"], start_day=0, end_day=250, seed=seed
    )
    identity = config_hash(config)
    snapshots = list(simulate(config, identity, "rust-property-test"))
    populations = [sum(place.states["health"].values()) for place in snapshots[0].places]
    for current, following in zip(snapshots, snapshots[1:], strict=False):
        assert [sum(place.states["health"].values()) for place in following.places] == populations
        assert all(
            value >= 0
            for place in following.places
            for value in place.states["health"].values()
        )
        assert all(
            following_place.susceptible <= current_place.susceptible
            for current_place, following_place in zip(current.places, following.places, strict=True)
        )
        assert all(
            following_place.recovered >= current_place.recovered
            for current_place, following_place in zip(current.places, following.places, strict=True)
        )


def test_golden_determinism_writes_identical_snapshot_files(tmp_path):
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    first.write_bytes(golden_bytes())
    second.write_bytes(golden_bytes())
    frozen = Path(__file__).parent / "fixtures" / "seed42.jsonl"
    assert first.read_bytes() == second.read_bytes() == frozen.read_bytes()
    records = [json.loads(line) for line in first.read_text().splitlines()]
    assert [record["day"] for record in records] == list(range(7, 15))


def test_initial_infections_start_in_italy_only():
    config = RunConfig(countries=["FRA", "ITA", "DEU"])
    state = initial_state(config)
    assert state[config.countries.index("ITA"), 2] == config.parameters.initial_infected
    assert state[:, 2].sum() == config.parameters.initial_infected


def test_canonical_cache_identity_and_version_invalidation():
    config = RunConfig(countries=["ITA", "FRA"])
    reordered = RunConfig(countries=["FRA", "ITA"])
    assert config_hash(config) == config_hash(reordered)
    assert config_hash(config) != config_hash(config.model_copy(update={"seed": 43}))
    assert config_hash(config) != config_hash(config, engine_version="different-source")
    assert config_hash(config) != config_hash(config, data_version="different-atlas")
