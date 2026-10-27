import json
from copy import deepcopy
from pathlib import Path

import numpy as np

from petraterrium.atlas.features import canonical_feature_registry, resolve_feature_distribution
from petraterrium.dsl import FeatureDistribution, load_dsl, validate_dsl
from petraterrium.population import sample_feature_traits

SMOKE_PATH = Path(__file__).resolve().parents[2] / "shared" / "dsl-schema" / "smoke-spread.json"


def smoke_config():
    return json.loads(SMOKE_PATH.read_text())


def registry_payload():
    return {
        "version": "test-v1",
        "definitions": [
            {
                "id": "trust",
                "kind": "continuous",
                "canonical_values": [],
                "value_range": {"minimum": 0, "maximum": 1, "unit": "score"},
                "provenance": {
                    "source": "Test instrument",
                    "version": "test-v1",
                    "status": "present",
                    "uncertainty": 0.1,
                    "source_date": "2026-01-01",
                },
            }
        ],
        "distributions": [],
        "joint_data": [],
    }


def messages(payload):
    return " ".join(issue.message for issue in validate_dsl(payload).errors).lower()


def test_canonical_registry_contains_relevant_population_and_behaviour_features():
    registry = canonical_feature_registry()
    definitions = {feature.id: feature for feature in registry.definitions}
    assert {
        "age",
        "sex",
        "income",
        "household_size",
        "education_isced",
        "occupation_isco",
        "openness",
        "conscientiousness",
        "extraversion",
        "agreeableness",
        "neuroticism",
        "schwartz_values",
        "risk_aversion",
        "time_preference",
        "generalized_trust",
        "religiosity",
        "mbti",
        "ideology_economic",
        "ideology_state",
        "ideology_cultural",
    } <= definitions.keys()
    assert {
        "eye_colour",
        "blood_type",
        "lactose_intolerance",
        "sickle_cell_trait",
    }.isdisjoint(definitions)
    assert "age_band" not in definitions
    assert definitions["mbti"].predictive is False
    assert definitions["mbti"].provenance.status == "label_only"


def test_continuous_age_histogram_samples_single_year_values():
    age = next(
        feature for feature in canonical_feature_registry().definitions if feature.id == "age"
    )
    distribution = FeatureDistribution(
        feature_id="age",
        level="country",
        place="CN",
        population="100 people",
        population_count=100,
        coverage_percent=100,
        values={"0": 0.25, "1": 0.75},
        mean=0.75,
        standard_deviation=0.4330127019,
        provenance={
            "source": "Test single-year ages",
            "version": "test-v1",
            "status": "present",
            "uncertainty": 0,
            "source_date": "2023-07-01",
        },
    )
    rng = np.random.default_rng(44)
    sampled = [sample_feature_traits([(age, distribution)], rng)["age"] for _ in range(200)]
    assert set(sampled) == {0.0, 1.0}
    assert 130 <= sampled.count(1.0) <= 170


def test_registry_rejects_missing_canonical_schema_and_invalid_distribution():
    missing_schema = smoke_config()
    registry = registry_payload()
    registry["definitions"][0] = {
        **registry["definitions"][0],
        "kind": "categorical",
        "value_range": None,
    }
    missing_schema["feature_registry"] = registry
    assert "canonical values" in messages(missing_schema)

    invalid_sum = smoke_config()
    registry = registry_payload()
    registry["definitions"][0] = {
        **registry["definitions"][0],
        "kind": "categorical",
        "canonical_values": ["low", "high"],
        "value_range": None,
    }
    registry["distributions"] = [
        {
            "feature_id": "trust",
            "level": "country",
            "place": "CAN",
            "population": "Canadian adults",
            "coverage_percent": 100,
            "values": {"low": 0.7, "high": 0.4},
            "provenance": registry["definitions"][0]["provenance"],
        }
    ]
    invalid_sum["feature_registry"] = registry
    assert "sum to 1" in messages(invalid_sum)


def test_registry_rejects_invalid_continuous_histogram():
    payload = smoke_config()
    registry = registry_payload()
    registry["distributions"] = [
        {
            "feature_id": "trust",
            "level": "country",
            "place": "CAN",
            "population": "Canadian adults",
            "coverage_percent": 100,
            "values": {"0": 0.7, "1": 0.4},
            "mean": 0.4,
            "standard_deviation": 0.2,
            "provenance": registry["definitions"][0]["provenance"],
        }
    ]
    payload["feature_registry"] = registry
    assert "sum to 1" in messages(payload)

    payload["feature_registry"]["distributions"][0]["values"] = {"0": 0.5, "2": 0.5}
    assert "outside its range" in messages(payload)


def test_global_distribution_requires_explicit_country_fallback():
    payload = smoke_config()
    registry = registry_payload()
    registry["distributions"] = [
        {
            "feature_id": "trust",
            "level": "global",
            "place": "global",
            "population": "Global test population",
            "coverage_percent": 10,
            "mean": 0.5,
            "standard_deviation": 0.2,
            "fallback_for": ["CAN"],
            "explicit_fallback": False,
            "provenance": registry["definitions"][0]["provenance"],
        }
    ]
    payload["feature_registry"] = registry
    assert "explicit fallback" in messages(payload)
    payload["feature_registry"]["distributions"][0]["explicit_fallback"] = True
    assert validate_dsl(payload).valid


def test_mbti_cannot_predict_without_population_specific_joint_data():
    payload = smoke_config()
    registry = registry_payload()
    registry["definitions"] = [
        {
            "id": "mbti",
            "kind": "categorical",
            "canonical_values": ["INTJ", "ENTP"],
            "value_range": None,
            "predictive": True,
            "provenance": {
                "source": "Self-selected test labels",
                "version": "test-v1",
                "status": "label_only",
                "uncertainty": 1,
            },
        }
    ]
    payload["feature_registry"] = registry
    assert "mbti" in messages(payload)
    assert "joint data" in messages(payload)
    payload["feature_registry"]["joint_data"] = [
        {
            "feature_id": "mbti",
            "outcomes": ["repost"],
            "population": "CAN",
            "provenance": {
                "source": "Joint test fixture",
                "version": "test-v1",
                "status": "present",
                "uncertainty": 0.2,
            },
        }
    ]
    assert validate_dsl(payload).valid


def test_feature_resolution_prefers_city_then_country_then_region_and_flags_fallback():
    registry = canonical_feature_registry().model_copy(
        update={
            "distributions": [
                FeatureDistribution(
                    feature_id="generalized_trust",
                    level="region",
                    place="Northern America",
                    population="Northern America covered population",
                    coverage_percent=70,
                    mean=0.4,
                    standard_deviation=0.2,
                    provenance={
                        "source": "FAKE regional fixture",
                        "version": "test-v1",
                        "status": "imputed",
                        "uncertainty": 0.5,
                        "source_date": "2026-01-01",
                    },
                ),
                FeatureDistribution(
                    feature_id="generalized_trust",
                    level="country",
                    place="CAN",
                    population="Canadian adults",
                    coverage_percent=90,
                    mean=0.55,
                    standard_deviation=0.15,
                    provenance={
                        "source": "FAKE country fixture",
                        "version": "test-v1",
                        "status": "present",
                        "uncertainty": 0.1,
                        "source_date": "2026-01-01",
                    },
                ),
            ]
        }
    )
    country = resolve_feature_distribution(
        registry, "generalized_trust", city="Toronto", country="CAN", region="Northern America"
    )
    assert country.distribution.place == "CAN"
    assert country.status == "inherited"
    assert country.region_override is False

    without_country = deepcopy(registry.model_dump())
    without_country["distributions"] = [without_country["distributions"][0]]
    regional = resolve_feature_distribution(
        load_dsl({**smoke_config(), "feature_registry": without_country}).feature_registry,
        "generalized_trust",
        city="Vancouver",
        country="CAN",
        region="Northern America",
    )
    assert regional.distribution.place == "Northern America"
    assert regional.status == "imputed"
    assert regional.region_override is True
    assert "country measurement" in regional.missing_requirement.lower()


def test_feature_resolution_accepts_subregion_between_country_and_region():
    registry = canonical_feature_registry().model_copy(
        update={
            "distributions": [
                FeatureDistribution(
                    feature_id="generalized_trust",
                    level="subregion",
                    place="Western Europe",
                    population="Western Europe covered population",
                    coverage_percent=75,
                    mean=0.48,
                    standard_deviation=0.18,
                    provenance={
                        "source": "FAKE subregion fixture",
                        "version": "test-v1",
                        "status": "imputed",
                        "uncertainty": 0.4,
                        "source_date": "2026-01-01",
                    },
                ),
                FeatureDistribution(
                    feature_id="generalized_trust",
                    level="region",
                    place="Europe",
                    population="Europe covered population",
                    coverage_percent=65,
                    mean=0.42,
                    standard_deviation=0.22,
                    provenance={
                        "source": "FAKE region fixture",
                        "version": "test-v1",
                        "status": "imputed",
                        "uncertainty": 0.5,
                        "source_date": "2026-01-01",
                    },
                ),
            ]
        }
    )
    resolved = resolve_feature_distribution(
        registry,
        "generalized_trust",
        city="Paris",
        country="FRA",
        subregion="Western Europe",
        region="Europe",
    )
    assert resolved.resolved_level == "subregion"
    assert resolved.distribution.place == "Western Europe"
    assert resolved.region_override is True
