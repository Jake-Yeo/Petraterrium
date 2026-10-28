from __future__ import annotations

import json
import math
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..atlas.evidence_receipts import AtlasEvidenceReceiptRegistry
from .registry_store import SimulationRegistryStore

IdentifierPattern = r"^[a-z][a-z0-9_-]*$"
EvidenceState = Literal["fitted", "default_estimated", "blocked"]
PlaceLevel = Literal["city", "country", "region", "global"]


class CoefficientEvidenceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )


class DefaultDslEvidenceIdentity(CoefficientEvidenceModel):
    version: str = Field(min_length=1)
    hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    source: Literal["shipped"] = "shipped"


class CoefficientPlace(CoefficientEvidenceModel):
    level: PlaceLevel
    place_id: str = Field(min_length=1)
    region_id: str | None = Field(default=None, min_length=1)
    country_id: str | None = Field(default=None, min_length=1)
    city_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def valid_hierarchy(self):
        if self.level == "global":
            if self.place_id != "global" or any(
                value is not None for value in (self.region_id, self.country_id, self.city_id)
            ):
                raise ValueError("Global coefficient evidence must use only global")
        if self.level == "region":
            if self.region_id != self.place_id or any(
                value is not None for value in (self.country_id, self.city_id)
            ):
                raise ValueError("Region coefficient evidence must identify only its region")
        if self.level == "country":
            if (
                self.region_id is None
                or self.country_id != self.place_id
                or self.city_id is not None
            ):
                raise ValueError("Country coefficient evidence requires region and country")
        if self.level == "city":
            if self.region_id is None or self.country_id is None or self.city_id != self.place_id:
                raise ValueError("City coefficient evidence requires region, country, and city")
        return self

    def specificity_for(self, target: CoefficientPlace) -> int | None:
        if self.level == "global":
            return 1
        if self.level == "region":
            return 2 if self.region_id == target.region_id else None
        if self.level == "country":
            return (
                3
                if self.country_id == target.country_id and self.region_id == target.region_id
                else None
            )
        return (
            4
            if self.city_id == target.city_id
            and self.country_id == target.country_id
            and self.region_id == target.region_id
            else None
        )

    @property
    def key(self) -> tuple[str, str]:
        return self.level, self.place_id


class CoefficientInterval(CoefficientEvidenceModel):
    low: float = Field(ge=0, le=1, allow_inf_nan=False)
    high: float = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def ordered(self):
        if self.low > self.high:
            raise ValueError("Coefficient interval must be ordered")
        return self


class CoefficientCitation(CoefficientEvidenceModel):
    kind: Literal["citation"] = "citation"
    imported_source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source: str = Field(min_length=1)
    publication_date: date
    population_studied: str = Field(min_length=1)
    link_or_reference: str = Field(min_length=1)
    supports_action_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_support_targets(self):
        if len(set(self.supports_action_ids)) != len(self.supports_action_ids):
            raise ValueError("Coefficient citation action support ids must be unique")
        return self


class ShippedDefaultReason(CoefficientEvidenceModel):
    kind: Literal["shipped_default_reason"] = "shipped_default_reason"
    reason: str = Field(min_length=1)
    default_dsl_version: str = Field(min_length=1)
    default_dsl_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


DefaultCoefficientSource = CoefficientCitation | ShippedDefaultReason


class DefaultActionCoefficients(CoefficientEvidenceModel):
    id: str = Field(pattern=IdentifierPattern)
    action_id: str = Field(pattern=IdentifierPattern)
    place: CoefficientPlace
    coefficients: dict[str, float] = Field(min_length=1)
    intervals: dict[str, CoefficientInterval] = Field(min_length=1)
    source: DefaultCoefficientSource
    evidence_state: Literal["default_estimated"] = "default_estimated"
    outgoing_groups: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("coefficients")
    @classmethod
    def finite_probabilities(cls, values: dict[str, float]):
        for edge_id, value in values.items():
            if not edge_id or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("Default coefficients require finite edge probabilities")
        return values

    @model_validator(mode="after")
    def complete_distribution(self):
        if set(self.coefficients) != set(self.intervals):
            raise ValueError("Every default coefficient requires an interval")
        groups = self.outgoing_groups or {"default": list(self.coefficients)}
        if {key for values in groups.values() for key in values} != set(self.coefficients):
            raise ValueError("Default coefficient outgoing groups must cover every edge")
        for values in groups.values():
            if not math.isclose(
                sum(self.coefficients[key] for key in values), 1, rel_tol=0, abs_tol=1e-9
            ):
                raise ValueError("Default action coefficients must sum to one per decision node")
        for edge_id, value in self.coefficients.items():
            interval = self.intervals[edge_id]
            if not interval.low <= value <= interval.high:
                raise ValueError(f"Default coefficient {edge_id} must be inside its interval")
        if (
            isinstance(self.source, CoefficientCitation)
            and self.action_id not in self.source.supports_action_ids
        ):
            raise ValueError("Attached citation does not support this action")
        return self


class HeldOutValidationReceipt(CoefficientEvidenceModel):
    metric: Literal["log_loss"] = "log_loss"
    held_out_rows: int = Field(gt=0)
    fitted_score: float = Field(ge=0, allow_inf_nan=False)
    default_score: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def fitted_improves_on_default(self):
        if self.fitted_score >= self.default_score:
            raise ValueError("Promoted fitted evidence must improve held-out loss")
        return self


class FittedModelProvenance(CoefficientEvidenceModel):
    imported_source_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    source_date: str = Field(min_length=1)
    published_date: str = Field(min_length=1)
    model_id: int = Field(gt=0)
    model_input_traits: dict[str, str | int | float | bool]
    evidence_kind: str = "linked_trait_context_outcome"

    @field_validator("evidence_kind")
    @classmethod
    def linked_outcome_only(cls, value: str):
        if value != "linked_trait_context_outcome":
            raise ValueError("Fitted evidence requires linked trait/context/outcome data")
        return value


class FittedActionCoefficients(CoefficientEvidenceModel):
    id: str = Field(pattern=IdentifierPattern)
    action_id: str = Field(pattern=IdentifierPattern)
    place: CoefficientPlace
    coefficients: dict[str, float] = Field(min_length=1)
    intervals: dict[str, CoefficientInterval] = Field(min_length=1)
    default_coefficient_set_id: str = Field(pattern=IdentifierPattern)
    provenance: FittedModelProvenance
    held_out: HeldOutValidationReceipt
    promoted_at: datetime
    evidence_state: Literal["fitted"] = "fitted"

    @field_validator("coefficients")
    @classmethod
    def finite_probabilities(cls, values: dict[str, float]):
        for edge_id, value in values.items():
            if not edge_id or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("Fitted coefficients require finite edge probabilities")
        return values

    @model_validator(mode="after")
    def complete_distribution(self):
        if set(self.coefficients) != set(self.intervals):
            raise ValueError("Every fitted coefficient requires an interval")
        if not math.isclose(sum(self.coefficients.values()), 1, rel_tol=0, abs_tol=1e-9):
            raise ValueError("Fitted action coefficients must sum to one")
        for edge_id, value in self.coefficients.items():
            interval = self.intervals[edge_id]
            if not interval.low <= value <= interval.high:
                raise ValueError(f"Fitted coefficient {edge_id} must be inside its interval")
        return self


class CoefficientChange(CoefficientEvidenceModel):
    edge_id: str = Field(min_length=1)
    default_value: float = Field(ge=0, le=1, allow_inf_nan=False)
    fitted_value: float = Field(ge=0, le=1, allow_inf_nan=False)


class CoefficientPromotionDiff(CoefficientEvidenceModel):
    promotion_id: str = Field(pattern=IdentifierPattern)
    action_id: str = Field(pattern=IdentifierPattern)
    place: CoefficientPlace
    default_coefficient_set_id: str = Field(pattern=IdentifierPattern)
    fitted_coefficient_set_id: str = Field(pattern=IdentifierPattern)
    changes: tuple[CoefficientChange, ...] = Field(min_length=1)
    provenance: FittedModelProvenance
    held_out: HeldOutValidationReceipt
    promoted_at: datetime


class ActionCoefficientRegistry(CoefficientEvidenceModel):
    version: str = Field(min_length=1)
    defaults: list[DefaultActionCoefficients] = Field(default_factory=list)
    fitted: list[FittedActionCoefficients] = Field(default_factory=list)
    promotions: list[CoefficientPromotionDiff] = Field(default_factory=list)


class ResolvedActionCoefficients(CoefficientEvidenceModel):
    coefficient_set_id: str
    default_coefficient_set_id: str
    action_id: str
    requested_place: CoefficientPlace
    source_place: CoefficientPlace
    coefficients: dict[str, float]
    intervals: dict[str, CoefficientInterval]
    evidence_state: Literal["fitted", "default_estimated"]
    source_label: str
    source_version: str
    source_id: str | None
    default_reason: str | None
    held_out: HeldOutValidationReceipt | None
    fitted_provenance: FittedModelProvenance | None
    default_coefficients: dict[str, float]
    promotion_id: str | None


class CoefficientEvidenceIssue(CoefficientEvidenceModel):
    code: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    coefficient_set_id: str = Field(min_length=1)
    evidence_state: Literal["blocked"] = "blocked"
    message: str = Field(min_length=1)


class CoefficientEvidenceValidation(CoefficientEvidenceModel):
    executable: bool
    fitted_count: int = Field(ge=0)
    default_estimated_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    issues: tuple[CoefficientEvidenceIssue, ...]


def validate_coefficient_registry(
    registry: ActionCoefficientRegistry,
    default_dsl_identity: DefaultDslEvidenceIdentity | None,
    evidence_receipts: AtlasEvidenceReceiptRegistry | None,
) -> CoefficientEvidenceValidation:
    issues: list[CoefficientEvidenceIssue] = []
    default_keys: set[tuple[str, str, str]] = set()
    defaults_by_id: dict[str, DefaultActionCoefficients] = {}
    for item in registry.defaults:
        if item.id in defaults_by_id:
            issues.append(_issue("duplicate_default_id", item, "Duplicate default coefficient id"))
        defaults_by_id[item.id] = item
        key = (item.action_id, *item.place.key)
        if key in default_keys:
            issues.append(_issue("ambiguous_default", item, "Duplicate default action/place"))
        default_keys.add(key)
        if isinstance(item.source, ShippedDefaultReason):
            if default_dsl_identity is None or (
                item.source.default_dsl_version != default_dsl_identity.version
                or item.source.default_dsl_hash != default_dsl_identity.hash
                or default_dsl_identity.source != "shipped"
            ):
                issues.append(
                    _issue(
                        "untrusted_default_reason",
                        item,
                        "Reason-only defaults must match the verified shipped Default DSL",
                    )
                )
        elif evidence_receipts is None:
            issues.append(
                _issue(
                    "unverified_citation",
                    item,
                    "Cited defaults require Atlas receipt verification before execution",
                )
            )
        else:
            source_issue = evidence_receipts.decision_source_issue(
                item.source.imported_source_id,
                item.source.source,
                item.source.publication_date,
                item.action_id,
            )
            if source_issue is not None:
                issues.append(_issue("unsupported_citation", item, source_issue))
    fitted_keys: set[tuple[str, str, str]] = set()
    for item in registry.fitted:
        key = (item.action_id, *item.place.key)
        if key in fitted_keys:
            issues.append(_issue("ambiguous_fitted", item, "Duplicate fitted action/place"))
        fitted_keys.add(key)
        baseline = defaults_by_id.get(item.default_coefficient_set_id)
        if baseline is None:
            issues.append(
                _issue(
                    "missing_default_baseline",
                    item,
                    "Fitted coefficients must reference an installed default coefficient set",
                )
            )
        elif baseline.action_id != item.action_id or set(baseline.coefficients) != set(
            item.coefficients
        ):
            issues.append(
                _issue(
                    "invalid_default_baseline",
                    item,
                    "Fitted coefficients must preserve the default action outcomes",
                )
            )
        else:
            resolved_defaults = _matching_defaults(registry, item.action_id, item.place)
            if not resolved_defaults or resolved_defaults[0].id != baseline.id:
                issues.append(
                    _issue(
                        "invalid_default_baseline",
                        item,
                        "Fitted coefficients must reference the resolved default for their place",
                    )
                )
        promotion = next(
            (
                record
                for record in registry.promotions
                if record.fitted_coefficient_set_id == item.id
                and record.default_coefficient_set_id == item.default_coefficient_set_id
                and record.action_id == item.action_id
                and record.place.key == item.place.key
            ),
            None,
        )
        if promotion is None:
            issues.append(
                _issue(
                    "missing_promotion_receipt",
                    item,
                    "Fitted coefficients require a matching promotion diff receipt",
                )
            )
        if evidence_receipts is None:
            issues.append(
                _issue(
                    "unverified_fitted_model",
                    item,
                    "Fitted coefficients require Atlas model receipt verification",
                )
            )
            continue
        fitted_issue = _fitted_receipt_issue(item, evidence_receipts)
        if fitted_issue is not None:
            issues.append(_issue("invalid_fitted_model", item, fitted_issue))
    return CoefficientEvidenceValidation(
        executable=not issues,
        fitted_count=len(registry.fitted),
        default_estimated_count=len(registry.defaults),
        blocked_count=len(issues),
        issues=tuple(issues),
    )


def _issue(code: str, item, message: str) -> CoefficientEvidenceIssue:
    return CoefficientEvidenceIssue(
        code=code,
        action_id=item.action_id,
        coefficient_set_id=item.id,
        message=message,
    )


def _fitted_receipt_issue(
    item: FittedActionCoefficients,
    evidence_receipts: AtlasEvidenceReceiptRegistry,
) -> str | None:
    receipt = evidence_receipts.get(item.provenance.imported_source_id)
    if receipt is None or not receipt.committed_shared_behaviour:
        return "Fitted evidence is not an explicitly promoted shared behaviour import"
    if (
        receipt.source != item.provenance.source
        or receipt.version != item.provenance.source_version
        or receipt.source_date != item.provenance.source_date
        or receipt.published_date != item.provenance.published_date
    ):
        return "Fitted provenance does not match its imported Atlas receipt"
    model = next(
        (row for row in receipt.models if int(row.get("id") or 0) == item.provenance.model_id),
        None,
    )
    if model is None:
        return "Fitted promotion references an unknown Atlas model"
    heldout_loss = model.get("heldout_loss")
    baseline_loss = model.get("baseline_loss")
    if heldout_loss is None or baseline_loss is None:
        return "Fitted promotion references an Atlas model without held-out validation"
    if (
        model.get("behaviour") != item.action_id
        or model.get("country_code") != item.place.country_id
        or not bool(model.get("fitted"))
        or not bool(model.get("active"))
        or int(model.get("heldout_rows") or 0) != item.held_out.held_out_rows
        or float(heldout_loss) != item.held_out.fitted_score
        or float(baseline_loss) != item.held_out.default_score
    ):
        return "Fitted promotion does not match an active held-out Atlas model"
    return None


def resolve_action_coefficients(
    registry: ActionCoefficientRegistry,
    action_id: str,
    place: CoefficientPlace,
) -> ResolvedActionCoefficients:
    defaults = _matching_defaults(registry, action_id, place)
    if not defaults:
        raise ValueError(f"Action {action_id!r} has no default coefficient for {place.place_id}")
    default = defaults[0]
    fitted = [
        item
        for item in registry.fitted
        if item.action_id == action_id and item.place.key == place.key
    ]
    if len(fitted) > 1:
        raise ValueError(f"Action {action_id!r} has ambiguous fitted evidence for {place.place_id}")
    if fitted:
        item = fitted[0]
        promotion = next(
            (
                record
                for record in registry.promotions
                if record.fitted_coefficient_set_id == item.id
                and record.default_coefficient_set_id == default.id
                and record.action_id == action_id
                and record.place.key == place.key
            ),
            None,
        )
        return ResolvedActionCoefficients(
            coefficient_set_id=item.id,
            default_coefficient_set_id=default.id,
            action_id=action_id,
            requested_place=place,
            source_place=item.place,
            coefficients=item.coefficients,
            intervals=item.intervals,
            evidence_state="fitted",
            source_label=item.provenance.source,
            source_version=item.provenance.source_version,
            source_id=item.provenance.imported_source_id,
            default_reason=None,
            held_out=item.held_out,
            fitted_provenance=item.provenance,
            default_coefficients=default.coefficients,
            promotion_id=promotion.promotion_id if promotion is not None else None,
        )
    if isinstance(default.source, CoefficientCitation):
        source_label = default.source.source
        source_version = default.source.publication_date.isoformat()
        source_id = default.source.imported_source_id
        reason = None
    else:
        source_label = "Shipped default DSL"
        source_version = default.source.default_dsl_version
        source_id = None
        reason = default.source.reason
    return ResolvedActionCoefficients(
        coefficient_set_id=default.id,
        default_coefficient_set_id=default.id,
        action_id=action_id,
        requested_place=place,
        source_place=default.place,
        coefficients=default.coefficients,
        intervals=default.intervals,
        evidence_state="default_estimated",
        source_label=source_label,
        source_version=source_version,
        source_id=source_id,
        default_reason=reason,
        held_out=None,
        fitted_provenance=None,
        default_coefficients=default.coefficients,
        promotion_id=None,
    )


def _matching_defaults(
    registry: ActionCoefficientRegistry,
    action_id: str,
    place: CoefficientPlace,
) -> list[DefaultActionCoefficients]:
    matches = [
        (specificity, item)
        for item in registry.defaults
        if item.action_id == action_id
        and (specificity := item.place.specificity_for(place)) is not None
    ]
    if not matches:
        return []
    highest = max(specificity for specificity, _ in matches)
    selected = sorted(
        (item for specificity, item in matches if specificity == highest),
        key=lambda item: item.id,
    )
    if len(selected) > 1:
        raise ValueError(f"Action {action_id!r} has ambiguous defaults for {place.place_id}")
    return selected


def load_coefficient_registry(
    store: SimulationRegistryStore,
) -> ActionCoefficientRegistry | None:
    with store._lock:
        if not store.path.exists():
            return None
        payload = json.loads(store.path.read_text(encoding="utf-8"))
        value = payload.get("coefficient_registry")
        return ActionCoefficientRegistry.model_validate(value) if value else None


def save_coefficient_registry(
    store: SimulationRegistryStore,
    registry: ActionCoefficientRegistry,
) -> ActionCoefficientRegistry:
    with store._lock:
        payload = store._payload()
        payload["coefficient_registry"] = registry.model_dump(mode="json")
        store._write(payload)
    return registry


def load_default_dsl_identity(
    store: SimulationRegistryStore,
) -> DefaultDslEvidenceIdentity | None:
    receipt_loader = getattr(store, "default_dsl_receipt", None)
    if callable(receipt_loader):
        receipt = receipt_loader()
        if receipt is not None:
            value = receipt.model_dump(mode="json") if isinstance(receipt, BaseModel) else receipt
            return DefaultDslEvidenceIdentity.model_validate(
                {key: value[key] for key in ("version", "hash", "source") if key in value}
            )
    with store._lock:
        if not store.path.exists():
            return None
        payload = json.loads(store.path.read_text(encoding="utf-8"))
    value = payload.get("default_dsl")
    if not isinstance(value, dict):
        return None
    return DefaultDslEvidenceIdentity.model_validate(
        {key: value[key] for key in ("version", "hash", "source") if key in value}
    )
