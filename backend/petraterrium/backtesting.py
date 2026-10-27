from datetime import date

import numpy as np

from .contracts import BacktestComparison


def backtest(
    metric: str,
    simulated: list[float],
    observed: list[float],
    cutoff_date: date,
    evidence_dates: list[date],
    provenance: str,
    tolerance: float,
) -> BacktestComparison:
    if not simulated or len(simulated) != len(observed):
        raise ValueError("Backtest series must be nonempty and have equal length")
    future = [item for item in evidence_dates if item > cutoff_date]
    if future:
        raise ValueError(
            f"Backtest evidence dated {min(future).isoformat()} is after cutoff "
            f"{cutoff_date.isoformat()}"
        )
    error = float(np.mean(np.abs(np.asarray(simulated) - np.asarray(observed))))
    return BacktestComparison(
        metric=metric,
        simulated=simulated,
        observed=observed,
        mean_absolute_error=error,
        outcome="hit" if error <= tolerance else "miss",
        cutoff_date=cutoff_date.isoformat(),
        provenance=provenance,
    )


def counterfactual_difference(baseline: list[float], counterfactual: list[float]) -> list[float]:
    if len(baseline) != len(counterfactual):
        raise ValueError("Counterfactual series must have equal length")
    return [
        alternative - reference
        for reference, alternative in zip(baseline, counterfactual, strict=True)
    ]
