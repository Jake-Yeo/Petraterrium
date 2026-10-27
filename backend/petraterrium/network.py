import numpy as np
from pydantic import BaseModel, ConfigDict


class InfluenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    previous: float
    current: float
    causes: dict[str, float]


DEFAULT_WEIGHTS = {"family": 0.7, "household": 0.65, "friend": 0.5, "stranger": 0.1, "enemy": -0.3}


def influence_update(
    opinion: float,
    neighbours: list[dict],
    place_delta: float = 0,
) -> InfluenceUpdate:
    causes = {}
    for neighbour in neighbours:
        kind = neighbour["kind"]
        weight = DEFAULT_WEIGHTS.get(kind, 0.1) * float(neighbour.get("weight", 1))
        causes[kind] = causes.get(kind, 0) + weight * (float(neighbour["opinion"]) - opinion)
    causes["place"] = place_delta * 0.2
    current = float(np.clip(opinion + sum(causes.values()), -1, 1))
    return InfluenceUpdate(previous=opinion, current=current, causes=causes)


def sparse_influence(
    states: np.ndarray,
    sources: np.ndarray,
    targets: np.ndarray,
    weights: np.ndarray,
) -> np.ndarray:
    changes = np.zeros_like(states, dtype=float)
    totals = np.zeros_like(states, dtype=float)
    np.add.at(changes, targets, weights * (states[sources] - states[targets]))
    np.add.at(totals, targets, np.abs(weights))
    return np.clip(states + np.divide(changes, np.maximum(totals, 1)), -1, 1)
