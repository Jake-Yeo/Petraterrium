import json
from datetime import date
from math import isfinite, sqrt

from .contracts import (
    BehaviourEvidenceRow,
    ChoiceEvidenceCatalog,
    FeatureResolutionRecord,
    Provenance,
    UniversalFeatureOverview,
)
from .database import AtlasStore
from .features import canonical_feature_registry, resolve_feature_distribution

SOURCE_CLASSIFICATIONS = {
    "anes": ("representative_survey", 3),
    "dhs": ("representative_survey", 3),
    "ess": ("representative_survey", 3),
    "gallup": ("representative_survey", 3),
    "pew": ("representative_survey", 3),
    "wvs": ("representative_survey", 3),
}


def universal_feature_overview() -> UniversalFeatureOverview:
    registry = canonical_feature_registry()
    resolutions = []
    for feature_id in ("generalized_trust", "mbti"):
        resolved = resolve_feature_distribution(
            registry,
            feature_id,
            city="Vancouver",
            country="CAN",
            region="Northern America",
        )
        evidence = resolved.distribution.provenance if resolved.distribution else None
        resolutions.append(
            FeatureResolutionRecord(
                feature_id=feature_id,
                city="Vancouver",
                country="CAN",
                region="Northern America",
                status=resolved.status,
                resolved_level=resolved.resolved_level,
                source=evidence.source if evidence else None,
                version=evidence.version if evidence else None,
                source_date=evidence.source_date if evidence else None,
                population=resolved.distribution.population if resolved.distribution else None,
                coverage_percent=(
                    resolved.distribution.coverage_percent
                    if resolved.distribution
                    else None
                ),
                region_override=resolved.region_override,
                missing_requirement=resolved.missing_requirement,
            )
        )
    return UniversalFeatureOverview(registry=registry, resolutions=resolutions)


def linked_outcome(rows: list[dict], country: str, behaviour: str):
    matched = []
    for item in rows:
        if (
            item.get("country_code") != country
            or item.get("behaviour") != behaviour
            or item.get("outcome") not in (0, 1)
            or not isinstance(item.get("traits"), dict)
            or not item["traits"]
        ):
            continue
        try:
            weight = float(item.get("weight", 1))
        except (TypeError, ValueError):
            continue
        if weight > 0 and isfinite(weight):
            matched.append((float(item["outcome"]), weight))
    if not matched:
        return None
    total_weight = sum(weight for _, weight in matched)
    probability = sum(outcome * weight for outcome, weight in matched) / total_weight
    effective_sample = total_weight**2 / sum(weight**2 for _, weight in matched)
    return probability, effective_sample, len(matched)


def confidence_interval(probability: float, sample_size: float) -> tuple[float, float]:
    z = 1.96
    denominator = 1 + z**2 / sample_size
    center = (probability + z**2 / (2 * sample_size)) / denominator
    margin = (
        z
        * sqrt(
            probability * (1 - probability) / sample_size
            + z**2 / (4 * sample_size**2)
        )
        / denominator
    )
    return max(0, center - margin), min(1, center + margin)


def parsed_json(value, fallback):
    try:
        parsed = json.loads(value or "null")
    except (json.JSONDecodeError, TypeError):
        return fallback
    return parsed if isinstance(parsed, type(fallback)) else fallback


def model_status(row) -> str:
    if bool(row["fitted"]) and bool(row["active"]):
        return "active_fitted"
    if bool(row["fitted"]):
        return "rejected_fit"
    return "label_only"


def model_evidence_receipt(row) -> BehaviourEvidenceRow:
    observations = parsed_json(row["validated_json"], [])
    metadata = parsed_json(row["metadata_json"], {})
    traits = parsed_json(row["traits_json"], [])
    specification = parsed_json(row["specification_json"], {})
    outcome = linked_outcome(observations, row["country_code"], row["behaviour"])
    source_type, source_tier = SOURCE_CLASSIFICATIONS.get(
        metadata.get("source_id"), ("unclassified_upload", None)
    )
    source_status = "measured" if source_tier is not None else "source_unclassified"
    probability = effective_sample = ci_low = ci_high = uncertainty = None
    sample_size = 0
    ci_method = None
    if outcome is not None:
        probability, effective_sample, sample_size = outcome
        ci_low, ci_high = confidence_interval(probability, effective_sample)
        uncertainty = min(1, ci_high - ci_low)
        ci_method = (
            "Approximate Wilson interval using Kish effective sample size; "
            "survey clustering and strata are unavailable"
        )
    status = model_status(row)
    definition = {
        "active_fitted": "Active weighted-logit model that beat its held-out baseline",
        "rejected_fit": "Fitted candidate retained for audit after failing held-out promotion",
        "label_only": "Imported labels remain excluded from predictors",
    }[status]
    return BehaviourEvidenceRow(
        id=f"atlas-model-{row['model_id']}",
        action_id=row["behaviour"],
        country_code=row["country_code"],
        definition=definition,
        model_status=status,
        source_status=source_status,
        source_type=source_type,
        source_tier=source_tier,
        outcome_rate=probability,
        ci_low=ci_low,
        ci_high=ci_high,
        uncertainty=uncertainty,
        sample_size=sample_size,
        effective_sample_size=effective_sample,
        ci_method=ci_method,
        population=f"{row['country_code']} imported linked respondents",
        denominator="Respondents with nonempty traits and a binary outcome",
        traits=[str(trait) for trait in traits],
        algorithm=specification.get("algorithm"),
        reason=specification.get("reason"),
        training_rows=row["training_rows"],
        heldout_rows=row["heldout_rows"],
        heldout_loss=row["heldout_loss"],
        baseline_loss=row["baseline_loss"],
        provenance=Provenance(
            import_id=row["import_id"],
            source=row["source"],
            source_date=row["source_date"],
            published_date=row["published_date"],
            version=row["version"],
            scope=row["scope"],
            uploader=row["uploader"],
        ),
    )


def choice_evidence_catalog(
    store: AtlasStore,
    scope: str = "shared",
    as_of: str | None = None,
) -> ChoiceEvidenceCatalog:
    cutoff = as_of or date.today().isoformat()
    with store.connection() as connection:
        rows = connection.execute(
            """SELECT m.id AS model_id,m.*,v.* FROM models m
            JOIN imports v USING(import_id)
            WHERE v.status='committed' AND v.scope IN ('shared',?)
            AND v.source_date<=? AND v.published_date<=?
            ORDER BY (v.scope=?) DESC,m.id DESC""",
            (scope, cutoff, cutoff, scope),
        ).fetchall()
    return ChoiceEvidenceCatalog(rows=[model_evidence_receipt(row) for row in rows])
