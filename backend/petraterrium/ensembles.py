import numpy as np
from pydantic import BaseModel, ConfigDict

from .leaders import AnchorTimeline, LeaderDecision


class EnsembleModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EnsembleSample(EnsembleModel):
    seed: int
    timeline: list[LeaderDecision]
    parameters: dict[str, float]


class EnsembleResults(EnsembleModel):
    anchor_config_id: str
    evidence_version: str
    population_version: str
    samples: list[EnsembleSample]


def ensemble_replay(
    anchor_timeline: AnchorTimeline,
    seeds: list[int],
    distributions: dict[str, tuple[float, float]],
) -> EnsembleResults:
    samples = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        parameters = {
            name: float(rng.uniform(bounds[0], bounds[1]))
            for name, bounds in sorted(distributions.items())
        }
        samples.append(
            EnsembleSample(
                seed=seed,
                timeline=list(anchor_timeline.timeline),
                parameters=parameters,
            )
        )
    return EnsembleResults(
        anchor_config_id=anchor_timeline.config_id,
        evidence_version=anchor_timeline.evidence_version,
        population_version=anchor_timeline.population_version,
        samples=samples,
    )
