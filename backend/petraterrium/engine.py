from collections.abc import Iterator

from .compatibility import State, initial_state, step
from .contracts import DailySnapshot, RunConfig
from .runtime import simulate_runtime

ENGINE_MODEL = "rust-vector-engine-v1"


def simulate(config: RunConfig, run_id: str, engine_version: str) -> Iterator[DailySnapshot]:
    yield from simulate_runtime(config, run_id, engine_version)


__all__ = ["ENGINE_MODEL", "State", "initial_state", "simulate", "step"]
