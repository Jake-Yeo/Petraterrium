import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from petraterrium.atlas.database import AtlasStore
from petraterrium.atlas.feature_catalog import (
    DescriptionUpdate,
    FeatureCatalogStore,
    FeatureCreate,
    create_feature_catalog_router,
)
from petraterrium.atlas.features import canonical_feature_registry
from petraterrium.dsl import FeatureDistribution, FeatureRange


def endurance_request(description=""):
    return FeatureCreate(
        id="endurance",
        name="Endurance",
        type="continuous",
        value_range=FeatureRange(minimum=0, maximum=100, unit="score"),
        description=description,
        provenance_placeholder="Validated endurance instrument to be selected",
        status="pending",
    )


def endurance_distribution():
    return FeatureDistribution(
        feature_id="endurance",
        level="country",
        place="CAN",
        population="Canadian adults",
        coverage_percent=82,
        mean=54,
        standard_deviation=13,
        provenance={
            "source": "Canadian fitness survey",
            "version": "2025-v1",
            "status": "present",
            "uncertainty": 0.12,
            "source_date": "2025-06-01",
        },
    )


def test_pending_feature_exists_before_data_and_blocks_predictor_use(tmp_path):
    registry = canonical_feature_registry()
    catalog = FeatureCatalogStore(AtlasStore(tmp_path / "atlas.sqlite3"))

    created = catalog.create(registry, endurance_request())

    assert created.status == "pending"
    assert created.distributions == []
    assert created.predictor_blocked is True
    assert created.usages[0].mode == "label_only"
    assert created.description == ""


def test_description_is_editable_and_distribution_advances_status(tmp_path):
    registry = canonical_feature_registry()
    catalog = FeatureCatalogStore(AtlasStore(tmp_path / "atlas.sqlite3"))
    catalog.create(registry, endurance_request("Initial description"))

    updated = catalog.update_description(
        registry,
        "endurance",
        DescriptionUpdate(description="Sustained effort on a validated 0–100 instrument."),
    )
    ready = catalog.attach_distribution(registry, "endurance", endurance_distribution())

    assert updated.description.startswith("Sustained effort")
    assert ready.status == "ready"
    assert ready.distributions[0].provenance.source == "Canadian fitness survey"
    assert ready.distributions[0].coverage_percent == 82
    assert ready.predictor_blocked is True
    assert ready.usages[0].mode == "label_only"


def test_catalog_api_creates_and_reopens_feature_detail(tmp_path):
    store = AtlasStore(tmp_path / "atlas.sqlite3")
    registry = canonical_feature_registry()
    application = FastAPI()
    application.include_router(create_feature_catalog_router(store, lambda: registry))
    client = TestClient(application)

    created = client.post(
        "/atlas/feature-catalog",
        json=endurance_request("Initial description").model_dump(mode="json"),
    )
    edited = client.patch(
        "/atlas/feature-catalog/endurance/description",
        json={"description": "Edited description"},
    )
    detail = client.get("/atlas/feature-catalog/endurance")

    assert created.status_code == 201
    assert created.json()["status"] == "pending"
    assert edited.status_code == 200
    assert detail.json()["description"] == "Edited description"
    assert detail.json()["predictor_blocked"] is True


def test_feature_schema_rejects_incomplete_or_ambiguous_values():
    invalid = [
        {
            "id": "segment",
            "name": "Segment",
            "type": "categorical",
            "canonical_values": ["a"],
            "provenance_placeholder": "Survey to be selected",
        },
        {
            "id": "score",
            "name": "Score",
            "type": "continuous",
            "canonical_values": ["high", "low"],
            "provenance_placeholder": "Instrument to be selected",
        },
    ]

    for payload in invalid:
        try:
            FeatureCreate.model_validate(payload)
        except ValueError:
            continue
        raise AssertionError("Invalid feature schema was accepted")


def test_continuous_histogram_rejects_invalid_probabilities(tmp_path):
    catalog = FeatureCatalogStore(AtlasStore(tmp_path / "atlas.sqlite3"))
    registry = canonical_feature_registry()
    distribution = FeatureDistribution(
        feature_id="age",
        level="country",
        place="CN",
        population="China population",
        population_count=100,
        coverage_percent=100,
        values={"0": 0.7, "1": 0.4},
        mean=0.4,
        standard_deviation=0.49,
        provenance={
            "source": "Test source",
            "version": "test-v1",
            "status": "present",
            "uncertainty": 0,
            "source_date": "2023-07-01",
        },
    )
    with pytest.raises(ValueError, match="sum to 1"):
        catalog.attach_distribution(registry, "age", distribution)


def test_feature_detail_uses_latest_distribution_version_per_place(tmp_path):
    store = AtlasStore(tmp_path / "atlas.sqlite3")
    catalog = FeatureCatalogStore(store)
    registry = canonical_feature_registry()
    catalog.create(registry, endurance_request())
    first = endurance_distribution()
    second = FeatureDistribution.model_validate(
        {
            **first.model_dump(),
            "mean": 61,
            "provenance": {
                **first.provenance.model_dump(),
                "version": "2026-v2",
                "source_date": "2026-06-01",
            },
        }
    )

    catalog.attach_distribution(registry, "endurance", first)
    catalog.attach_distribution(registry, "endurance", second)

    detail = catalog.detail(registry, "endurance")
    assert len(detail.distributions) == 1
    assert detail.distributions[0].mean == 61
    assert detail.distributions[0].provenance.version == "2026-v2"
    with store.connection() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM feature_catalog_distributions "
                "WHERE feature_id='endurance'"
            ).fetchone()[0]
            == 2
        )
