from __future__ import annotations

from collections import defaultdict
from typing import Literal

from pydantic import Field

from .coefficient_evidence import (
    CoefficientEvidenceModel,
    CoefficientInterval,
    CoefficientPlace,
    EvidenceState,
    HeldOutValidationReceipt,
)


class RunCoefficientReceipt(CoefficientEvidenceModel):
    action_id: str = Field(min_length=1)
    edge_id: str = Field(min_length=1)
    place: CoefficientPlace
    source_place: CoefficientPlace | None = None
    resolution_status: Literal["direct", "inherited", "imputed"] = "direct"
    evidence_state: EvidenceState
    value: float = Field(ge=0, le=1, allow_inf_nan=False)
    interval: CoefficientInterval
    coefficient_set_id: str = Field(min_length=1)
    default_coefficient_set_id: str = Field(min_length=1)
    default_value: float = Field(ge=0, le=1, allow_inf_nan=False)
    fitted_delta: float | None = Field(default=None, ge=-1, le=1, allow_inf_nan=False)
    promotion_id: str | None = None
    source_label: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    source_id: str | None = None
    default_reason: str | None = None
    held_out: HeldOutValidationReceipt | None = None
    affected_agents: int = Field(default=1, ge=1)


class ActionPlaceEvidenceSummary(CoefficientEvidenceModel):
    action_id: str
    place: CoefficientPlace
    fitted_count: int = Field(ge=0)
    default_estimated_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    coefficients: tuple[RunCoefficientReceipt, ...]


class RunEvidenceSummary(CoefficientEvidenceModel):
    fitted_count: int = Field(ge=0)
    default_estimated_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    by_action_place: tuple[ActionPlaceEvidenceSummary, ...]


class RunEvidenceWarning(CoefficientEvidenceModel):
    code: Literal["default_estimated_coefficients"] = "default_estimated_coefficients"
    action_id: str
    place: CoefficientPlace
    coefficient_ids: tuple[str, ...] = Field(min_length=1)
    message: str = Field(min_length=1)


def empty_evidence_summary() -> RunEvidenceSummary:
    return RunEvidenceSummary(
        fitted_count=0,
        default_estimated_count=0,
        blocked_count=0,
        by_action_place=(),
    )


def evidence_summary(
    receipts: list[RunCoefficientReceipt],
) -> tuple[RunEvidenceSummary, list[RunEvidenceWarning]]:
    merged = _merge_receipts(receipts)
    grouped: dict[tuple[str, str, str], list[RunCoefficientReceipt]] = defaultdict(list)
    for receipt in merged:
        grouped[(receipt.action_id, receipt.place.level, receipt.place.place_id)].append(receipt)
    action_places = []
    warnings = []
    for key in sorted(grouped):
        items = tuple(sorted(grouped[key], key=lambda item: item.edge_id))
        action_place = ActionPlaceEvidenceSummary(
            action_id=items[0].action_id,
            place=items[0].place,
            fitted_count=sum(item.evidence_state == "fitted" for item in items),
            default_estimated_count=sum(
                item.evidence_state == "default_estimated" for item in items
            ),
            blocked_count=sum(item.evidence_state == "blocked" for item in items),
            coefficients=items,
        )
        action_places.append(action_place)
        defaults = [item for item in items if item.evidence_state == "default_estimated"]
        if defaults:
            warnings.append(
                RunEvidenceWarning(
                    action_id=action_place.action_id,
                    place=action_place.place,
                    coefficient_ids=tuple(item.edge_id for item in defaults),
                    message=(
                        f"{action_place.action_id} at {action_place.place.place_id} uses "
                        f"{len(defaults)} default/estimated coefficient"
                        f"{'s' if len(defaults) != 1 else ''}; inspect provenance and uncertainty."
                    ),
                )
            )
    summary = RunEvidenceSummary(
        fitted_count=sum(item.evidence_state == "fitted" for item in merged),
        default_estimated_count=sum(item.evidence_state == "default_estimated" for item in merged),
        blocked_count=sum(item.evidence_state == "blocked" for item in merged),
        by_action_place=tuple(action_places),
    )
    return summary, warnings


def _merge_receipts(receipts: list[RunCoefficientReceipt]) -> list[RunCoefficientReceipt]:
    merged: dict[tuple, RunCoefficientReceipt] = {}
    for receipt in receipts:
        key = (
            receipt.action_id,
            receipt.edge_id,
            receipt.place.level,
            receipt.place.place_id,
            receipt.evidence_state,
            receipt.value,
            receipt.coefficient_set_id,
        )
        existing = merged.get(key)
        if existing is None:
            merged[key] = receipt
        else:
            merged[key] = existing.model_copy(
                update={"affected_agents": existing.affected_agents + receipt.affected_agents}
            )
    return [merged[key] for key in sorted(merged)]
