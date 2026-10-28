from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import Field, model_validator

from ..atlas.behaviour import predict
from ..atlas.evidence_receipts import AtlasEvidenceReceiptRegistry
from .coefficient_evidence import (
    ActionCoefficientRegistry,
    CoefficientChange,
    CoefficientEvidenceModel,
    CoefficientInterval,
    CoefficientPlace,
    CoefficientPromotionDiff,
    FittedActionCoefficients,
    FittedModelProvenance,
    HeldOutValidationReceipt,
    load_coefficient_registry,
    resolve_action_coefficients,
    save_coefficient_registry,
)
from .registry_store import SimulationRegistryStore


class VerifiedFittedAction(CoefficientEvidenceModel):
    action_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    place: CoefficientPlace
    coefficients: dict[str, float] = Field(min_length=1)
    intervals: dict[str, CoefficientInterval] = Field(min_length=1)
    provenance: FittedModelProvenance
    held_out: HeldOutValidationReceipt


class AtlasFittedPromotionCandidate(CoefficientEvidenceModel):
    action_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    place: CoefficientPlace
    target_edge_id: str = Field(min_length=1)
    complement_edge_id: str = Field(min_length=1)
    imported_source_id: str = Field(min_length=1)
    model_id: int = Field(gt=0)
    model_input_traits: dict[str, str | int | float | bool]

    @model_validator(mode="after")
    def distinct_binary_outcomes(self):
        if self.target_edge_id == self.complement_edge_id:
            raise ValueError("Fitted binary outcomes must be distinct")
        if self.place.level != "country":
            raise ValueError("Atlas fitted promotion currently requires a country place")
        return self


class ConfirmFittedPromotionRequest(CoefficientEvidenceModel):
    candidate: AtlasFittedPromotionCandidate
    user_confirmed: Literal[True]


class FittedPromotionResponse(CoefficientEvidenceModel):
    registry_version: str
    diff: CoefficientPromotionDiff


def promote_verified_fit(
    registry: ActionCoefficientRegistry,
    fitted: VerifiedFittedAction,
    *,
    user_confirmed: bool,
) -> tuple[ActionCoefficientRegistry, CoefficientPromotionDiff]:
    if not user_confirmed:
        raise ValueError("Fitted coefficient promotion requires explicit confirmation")
    baseline = resolve_action_coefficients(registry, fitted.action_id, fitted.place)
    if set(baseline.coefficients) != set(fitted.coefficients):
        raise ValueError("Fitted action outcomes must match the default action outcomes")
    changes = tuple(
        CoefficientChange(
            edge_id=edge_id,
            default_value=baseline.coefficients[edge_id],
            fitted_value=fitted.coefficients[edge_id],
        )
        for edge_id in sorted(fitted.coefficients)
    )
    identity_payload = {
        "action_id": fitted.action_id,
        "place": fitted.place.model_dump(mode="json"),
        "model": fitted.provenance.model_dump(mode="json"),
        "coefficients": fitted.coefficients,
    }
    digest = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    fitted_id = f"fitted-{digest}"
    promotion_id = f"promotion-{digest}"
    promoted_at = datetime.now(UTC)
    record = FittedActionCoefficients(
        id=fitted_id,
        action_id=fitted.action_id,
        place=fitted.place,
        coefficients=fitted.coefficients,
        intervals=fitted.intervals,
        default_coefficient_set_id=baseline.coefficient_set_id,
        provenance=fitted.provenance,
        held_out=fitted.held_out,
        promoted_at=promoted_at,
    )
    diff = CoefficientPromotionDiff(
        promotion_id=promotion_id,
        action_id=fitted.action_id,
        place=fitted.place,
        default_coefficient_set_id=baseline.coefficient_set_id,
        fitted_coefficient_set_id=fitted_id,
        changes=changes,
        provenance=fitted.provenance,
        held_out=fitted.held_out,
        promoted_at=promoted_at,
    )
    existing_fitted = [
        item
        for item in registry.fitted
        if not (item.action_id == fitted.action_id and item.place.key == fitted.place.key)
    ]
    existing_promotions = [
        item
        for item in registry.promotions
        if not (item.action_id == fitted.action_id and item.place.key == fitted.place.key)
    ]
    updated = ActionCoefficientRegistry(
        version=f"{registry.version}+{promotion_id}",
        defaults=registry.defaults,
        fitted=[*existing_fitted, record],
        promotions=[*existing_promotions, diff],
    )
    return updated, diff


def verify_atlas_fitted_action(
    candidate: AtlasFittedPromotionCandidate,
    evidence_receipts: AtlasEvidenceReceiptRegistry,
) -> VerifiedFittedAction:
    receipt = evidence_receipts.get(candidate.imported_source_id)
    if receipt is None or not receipt.committed_shared_behaviour:
        raise ValueError("Fitted evidence requires a promoted shared behaviour import")
    model = next(
        (row for row in receipt.models if int(row.get("id") or 0) == candidate.model_id),
        None,
    )
    if model is None:
        raise ValueError("Fitted promotion references an unknown Atlas model")
    country_id = candidate.place.country_id
    if (
        model.get("country_code") != country_id
        or model.get("behaviour") != candidate.action_id
        or not bool(model.get("fitted"))
        or not bool(model.get("active"))
    ):
        raise ValueError("Fitted promotion must match an active action/place Atlas model")
    heldout_rows = int(model.get("heldout_rows") or 0)
    heldout_loss = model.get("heldout_loss")
    baseline_loss = model.get("baseline_loss")
    if heldout_rows <= 0 or heldout_loss is None or baseline_loss is None:
        raise ValueError("Fitted promotion requires held-out validation")
    specification = json.loads(str(model.get("specification_json") or "{}"))
    probability = float(
        predict(
            [{"traits": candidate.model_input_traits}],
            specification,
        )[0]
    )
    interval = CoefficientInterval(low=0, high=1)
    return VerifiedFittedAction(
        action_id=candidate.action_id,
        place=candidate.place,
        coefficients={
            candidate.target_edge_id: probability,
            candidate.complement_edge_id: 1 - probability,
        },
        intervals={
            candidate.target_edge_id: interval,
            candidate.complement_edge_id: interval,
        },
        provenance=FittedModelProvenance(
            imported_source_id=receipt.source_id,
            source=receipt.source,
            source_version=receipt.version,
            source_date=receipt.source_date,
            published_date=receipt.published_date,
            model_id=candidate.model_id,
            model_input_traits=candidate.model_input_traits,
        ),
        held_out=HeldOutValidationReceipt(
            held_out_rows=heldout_rows,
            fitted_score=float(heldout_loss),
            default_score=float(baseline_loss),
        ),
    )


def create_coefficient_promotion_router(
    store: SimulationRegistryStore,
    evidence_receipts: AtlasEvidenceReceiptRegistry,
) -> APIRouter:
    router = APIRouter(
        prefix="/simulation/coefficient-evidence",
        tags=["Simulation coefficient evidence"],
    )

    def required_registry() -> ActionCoefficientRegistry:
        registry = load_coefficient_registry(store)
        if registry is None:
            raise HTTPException(409, "No default coefficient registry is installed")
        return registry

    @router.get("")
    def get_registry() -> ActionCoefficientRegistry:
        return required_registry()

    @router.post("/promotions/preview")
    def preview_promotion(
        candidate: AtlasFittedPromotionCandidate,
    ) -> FittedPromotionResponse:
        try:
            verified = verify_atlas_fitted_action(candidate, evidence_receipts)
            updated, diff = promote_verified_fit(
                required_registry(),
                verified,
                user_confirmed=True,
            )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return FittedPromotionResponse(registry_version=updated.version, diff=diff)

    @router.post("/promotions")
    def confirm_promotion(
        request: ConfirmFittedPromotionRequest,
    ) -> FittedPromotionResponse:
        try:
            verified = verify_atlas_fitted_action(request.candidate, evidence_receipts)
            updated, diff = promote_verified_fit(
                required_registry(),
                verified,
                user_confirmed=request.user_confirmed,
            )
            save_coefficient_registry(store, updated)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return FittedPromotionResponse(registry_version=updated.version, diff=diff)

    return router


__all__ = [
    "FittedModelProvenance",
    "HeldOutValidationReceipt",
    "AtlasFittedPromotionCandidate",
    "ConfirmFittedPromotionRequest",
    "FittedPromotionResponse",
    "VerifiedFittedAction",
    "create_coefficient_promotion_router",
    "promote_verified_fit",
    "verify_atlas_fitted_action",
]
