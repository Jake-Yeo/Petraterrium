from pydantic import BaseModel, ConfigDict

from ..dsl import (
    Evidence,
    FeatureDefinition,
    FeatureDistribution,
    FeatureRange,
    FeatureRegistry,
)


class FeatureResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    feature_id: str
    status: str
    distribution: FeatureDistribution | None
    resolved_level: str
    region_override: bool
    missing_requirement: str


def schema_evidence(source: str, status: str = "present") -> Evidence:
    return Evidence(
        source=source,
        version="canonical-features-v1",
        status=status,
        uncertainty=0 if status == "present" else 1,
    )


def continuous(feature_id: str, source: str, minimum=0, maximum=1, unit="score"):
    return FeatureDefinition(
        id=feature_id,
        kind="continuous",
        value_range=FeatureRange(minimum=minimum, maximum=maximum, unit=unit),
        provenance=schema_evidence(source),
    )


def categorical(feature_id: str, values: list[str], source: str, **options):
    return FeatureDefinition(
        id=feature_id,
        kind="categorical",
        canonical_values=values,
        provenance=schema_evidence(source),
        **options,
    )


def canonical_feature_registry() -> FeatureRegistry:
    definitions = [
        continuous("age", "ISO 8601 age in completed years", 0, 120, "years"),
        categorical(
            "sex",
            ["female", "male", "intersex", "unknown"],
            "Canonical demographic sex categories",
        ),
        categorical(
            "education_isced",
            ["0", "1", "2", "3", "4", "5", "6", "7", "8", "unknown"],
            "UNESCO ISCED 2011 levels",
        ),
        categorical(
            "occupation_isco",
            ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "unknown"],
            "ILO ISCO-08 major groups",
        ),
        continuous("openness", "Big Five trait scale"),
        continuous("conscientiousness", "Big Five trait scale"),
        continuous("extraversion", "Big Five trait scale"),
        continuous("agreeableness", "Big Five trait scale"),
        continuous("neuroticism", "Big Five trait scale"),
        categorical(
            "schwartz_values",
            [
                "self_direction",
                "stimulation",
                "hedonism",
                "achievement",
                "power",
                "security",
                "conformity",
                "tradition",
                "benevolence",
                "universalism",
            ],
            "Schwartz basic human values",
        ),
        continuous("risk_aversion", "Portable risk preference scale"),
        continuous("time_preference", "Portable time preference scale"),
        continuous("generalized_trust", "Portable generalized trust scale"),
        continuous("religiosity", "Portable religiosity scale"),
        FeatureDefinition(
            id="mbti",
            kind="categorical",
            canonical_values=[
                f"{first}{second}{third}{fourth}"
                for first in ("I", "E")
                for second in ("N", "S")
                for third in ("T", "F")
                for fourth in ("J", "P")
            ],
            provenance=schema_evidence("MBTI labels without joint outcome evidence", "label_only"),
            predictive=False,
        ),
        categorical(
            "eye_colour",
            ["brown", "blue", "green", "hazel", "amber", "grey", "other", "unknown"],
            "Population-specific biological categories",
            ancestry_linked=True,
        ),
        categorical(
            "blood_type",
            ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "unknown"],
            "Population-specific biological categories",
            ancestry_linked=True,
        ),
        categorical(
            "lactose_intolerance",
            ["present", "absent", "unknown"],
            "Population-specific biological categories",
            ancestry_linked=True,
        ),
        categorical(
            "sickle_cell_trait",
            ["present", "absent", "unknown"],
            "Population-specific biological categories",
            ancestry_linked=True,
        ),
    ]
    return FeatureRegistry(
        version="canonical-features-v1",
        definitions=definitions,
        distributions=[],
        joint_data=[],
    )


def resolve_feature_distribution(
    registry: FeatureRegistry,
    feature_id: str,
    city: str,
    country: str,
    region: str,
    subregion: str | None = None,
) -> FeatureResolution:
    priorities = [
        ("city", city, "present", False),
        ("country", country, "inherited", False),
    ]
    if subregion:
        priorities.append(("subregion", subregion, "imputed", True))
    priorities.append(
        ("region", region, "imputed", True),
    )
    for level, place, status, region_override in priorities:
        match = next(
            (
                item
                for item in registry.distributions
                if item.feature_id == feature_id and item.level == level and item.place == place
            ),
            None,
        )
        if match:
            missing_requirement = ""
            if level == "country":
                missing_requirement = f"City measurement for {city}"
            if level in {"subregion", "region"}:
                missing_requirement = f"Country measurement for {country}"
            return FeatureResolution(
                feature_id=feature_id,
                status=status if match.provenance.status == "present" else match.provenance.status,
                distribution=match,
                resolved_level=level,
                region_override=region_override,
                missing_requirement=missing_requirement,
            )
    global_match = next(
        (
            item
            for item in registry.distributions
            if item.feature_id == feature_id
            and item.level == "global"
            and item.explicit_fallback
            and country in item.fallback_for
        ),
        None,
    )
    if global_match:
        return FeatureResolution(
            feature_id=feature_id,
            status="imputed",
            distribution=global_match,
            resolved_level="global",
            region_override=True,
            missing_requirement=f"Country measurement for {country}",
        )
    return FeatureResolution(
        feature_id=feature_id,
        status="label_only"
        if next(item for item in registry.definitions if item.id == feature_id).predictive is False
        else "unknown",
        distribution=None,
        resolved_level="unknown",
        region_override=False,
        missing_requirement=f"City, country, or regional distribution for {feature_id}",
    )
