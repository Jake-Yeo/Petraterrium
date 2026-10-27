from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from .database import AtlasStore


@dataclass(frozen=True)
class AtlasEvidenceReceipt:
    source_id: str
    source: str
    source_date: str
    published_date: str
    version: str
    scope: str
    kind: str
    status: str
    rows: tuple[dict[str, Any], ...]
    models: tuple[dict[str, Any], ...]

    @property
    def committed_shared_behaviour(self) -> bool:
        return (
            self.status == "committed"
            and self.scope == "shared"
            and self.kind == "behaviour"
        )


class AtlasEvidenceReceiptRegistry:
    def __init__(self, store: AtlasStore):
        self.store = store

    def get(self, source_id: str) -> AtlasEvidenceReceipt | None:
        with self.store.connection() as connection:
            row = connection.execute(
                "SELECT * FROM imports WHERE import_id=?",
                (source_id,),
            ).fetchone()
            if row is None:
                return None
            models = connection.execute(
                "SELECT * FROM models WHERE import_id=? ORDER BY id",
                (source_id,),
            ).fetchall()
        try:
            rows = json.loads(row["validated_json"] or "[]")
        except json.JSONDecodeError:
            rows = []
        return AtlasEvidenceReceipt(
            source_id=row["import_id"],
            source=row["source"],
            source_date=row["source_date"],
            published_date=row["published_date"],
            version=row["version"],
            scope=row["scope"],
            kind=row["kind"],
            status=row["status"],
            rows=tuple(item for item in rows if isinstance(item, dict)),
            models=tuple(dict(item) for item in models),
        )

    def decision_source_issue(
        self,
        source_id: str,
        source: str,
        publication_date: date,
        decision_id: str,
    ) -> str | None:
        receipt = self.get(source_id)
        if receipt is None or not receipt.committed_shared_behaviour:
            return "Evidence source is not an explicitly promoted shared behaviour import"
        if receipt.source != source:
            return "Evidence source label does not match its imported Atlas receipt"
        if receipt.published_date != publication_date.isoformat():
            return "Evidence publication date does not match its imported Atlas receipt"
        if not any(
            row.get("behaviour") == decision_id and row.get("outcome") is not None
            for row in receipt.rows
        ):
            return "Imported behaviour receipt has no linked outcomes for this decision"
        return None

    def decision_factor_issue(
        self,
        source_id: str,
        decision_id: str,
        factor_key: str,
        basis: str,
        place_level: str,
        country_id: str | None,
        predicate_operator: str,
        predicate_value: Any,
        predicate_values: tuple[Any, ...],
        predicate_lower: float | None,
        predicate_upper: float | None,
        estimate: float,
        sample_size: int,
    ) -> str | None:
        receipt = self.get(source_id)
        if receipt is None or not receipt.committed_shared_behaviour:
            return "Evidence source is not an explicitly promoted shared behaviour import"
        if place_level not in {"country", "city"} or country_id is None:
            return "Executable decision evidence requires a directly imported country receipt"
        candidates = [
            row
            for row in receipt.rows
            if row.get("country_code") == country_id
            and row.get("behaviour") == decision_id
            and row.get("outcome") is not None
            and factor_key in row.get("traits", {})
        ]
        if basis == "fitted_model":
            matching_models = [
                model
                for model in receipt.models
                if model.get("country_code") == country_id
                and model.get("behaviour") == decision_id
                and bool(model.get("fitted"))
                and bool(model.get("active"))
                and int(model.get("heldout_rows") or 0) > 0
                and factor_key in json.loads(model.get("traits_json") or "[]")
            ]
            if not matching_models:
                return "Fitted evidence has no active held-out Atlas model receipt"
            return None
        if basis != "measured_joint":
            return None
        matching = [
            row
            for row in candidates
            if _predicate_matches(
                predicate_operator,
                row["traits"][factor_key],
                predicate_value,
                predicate_values,
                predicate_lower,
                predicate_upper,
            )
        ]
        if not matching:
            return "Imported behaviour receipt has no matching linked trait/outcome rows"
        if sample_size != len(matching):
            return "Evidence sample size does not match the imported behaviour receipt"
        total_weight = sum(float(row.get("weight", 1)) for row in matching)
        measured = sum(
            float(row["outcome"]) * float(row.get("weight", 1)) for row in matching
        ) / total_weight
        if abs(measured - estimate) > 1e-9:
            return "Evidence estimate does not match the imported weighted outcome rate"
        return None

    def interaction_issue(
        self,
        evidence_id: str | None,
        source: str,
        version: str,
        source_date: str | None,
        expected_behaviours: set[str],
    ) -> str | None:
        if evidence_id is None:
            return "Measured interaction evidence requires an Atlas receipt id"
        receipt = self.get(evidence_id)
        if receipt is None or not receipt.committed_shared_behaviour:
            return (
                "Measured interaction evidence requires an explicitly promoted shared "
                "behaviour import"
            )
        if (
            source != receipt.source
            or version != receipt.version
            or source_date != receipt.source_date
        ):
            return "Interaction provenance does not match its imported Atlas receipt"
        observed = {
            str(row.get("behaviour"))
            for row in receipt.rows
            if row.get("outcome") is not None
        }
        if not observed.intersection(expected_behaviours):
            return "Imported behaviour receipt does not measure this interaction"
        return None


def _predicate_matches(
    operator: str,
    observed: Any,
    value: Any,
    values: tuple[Any, ...],
    lower: float | None,
    upper: float | None,
) -> bool:
    if operator == "any":
        return True
    if operator == "exact":
        return observed == value
    if operator == "one_of":
        return observed in values
    if operator != "between" or isinstance(observed, bool):
        return False
    if not isinstance(observed, int | float) or lower is None or upper is None:
        return False
    return lower <= observed <= upper
