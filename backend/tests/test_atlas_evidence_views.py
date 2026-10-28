import json

import pytest

from petraterrium.atlas.database import AtlasStore
from petraterrium.atlas.evidence_views import (
    choice_evidence_catalog,
    universal_feature_overview,
)


def seed_model(
    store,
    import_id="promoted-behaviour",
    scope="shared",
    source_id="wvs",
    source_date="2024-01-01",
    published_date="2024-02-01",
    fitted=True,
    label_only=False,
    active=True,
    observations=None,
):
    rows = observations or [
        {
            "country_code": "CA",
            "behaviour": "go_out",
            "traits": {"extraversion": 0.8},
            "outcome": 1,
            "weight": 2,
        },
        {
            "country_code": "CA",
            "behaviour": "go_out",
            "traits": {"extraversion": 0.2},
            "outcome": 0,
            "weight": 1,
        },
    ]
    metadata = {"source_id": source_id} if source_id else {}
    training_rows = 1 if fitted else 0
    heldout_rows = 1 if fitted else 0
    with store.connection() as connection:
        connection.execute(
            """INSERT INTO imports(
            import_id,source,source_date,published_date,version,scope,uploader,kind,filename,
            row_count,status,metadata_json,rows_json,mapping_json,audit_json,validation_json,
            validated_json,promoted_from,redistribution_allowed,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                import_id,
                "World Values Survey" if source_id == "wvs" else "Uploaded linked rows",
                source_date,
                published_date,
                "2024-v1",
                scope,
                "tester",
                "behaviour",
                "behaviour.csv",
                len(rows),
                "committed",
                json.dumps(metadata),
                "[]",
                "[]",
                "{}",
                "{}",
                json.dumps(rows),
                "run-version" if scope == "shared" else None,
                1,
                "2024-02-01T00:00:00Z",
            ),
        )
        connection.execute(
            """INSERT INTO models(
            import_id,country_code,behaviour,fitted,label_only,active,specification_json,
            heldout_loss,baseline_loss,training_rows,heldout_rows,traits_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                import_id,
                "CA",
                "go_out",
                fitted,
                label_only,
                active,
                json.dumps(
                    {
                        "algorithm": "weighted-logit-irls-v1" if fitted else None,
                        "reason": None if fitted else "Linked sample is too small",
                    }
                ),
                0.4 if fitted else None,
                0.6 if fitted else None,
                training_rows,
                heldout_rows,
                json.dumps(["extraversion"]),
            ),
        )


def test_choice_evidence_catalog_does_not_expose_smoke_fixtures(tmp_path):
    store = AtlasStore(tmp_path / "atlas.sqlite3")

    catalog = choice_evidence_catalog(store)

    assert catalog.rows == []


def test_choice_evidence_catalog_projects_promoted_fitted_imports(tmp_path):
    store = AtlasStore(tmp_path / "atlas.sqlite3")
    seed_model(store)

    row = choice_evidence_catalog(store).rows[0]

    assert row.action_id == "go_out"
    assert row.country_code == "CA"
    assert row.model_status == "active_fitted"
    assert row.source_status == "measured"
    assert row.source_type == "representative_survey"
    assert row.source_tier == 3
    assert row.outcome_rate == pytest.approx(2 / 3)
    assert row.sample_size == 2
    assert row.effective_sample_size == pytest.approx(1.8)
    assert "Kish effective sample size" in row.ci_method
    assert row.provenance.import_id == "promoted-behaviour"
    assert row.provenance.source == "World Values Survey"
    assert row.provenance.version == "2024-v1"
    assert row.provenance.published_date == "2024-02-01"


def test_choice_evidence_catalog_respects_scope_and_no_hindsight_date(tmp_path):
    store = AtlasStore(tmp_path / "atlas.sqlite3")
    seed_model(store, import_id="run-behaviour", scope="run-a")

    assert choice_evidence_catalog(store, "shared", "2026-01-01").rows == []
    assert choice_evidence_catalog(store, "run-a", "2023-12-31").rows == []
    assert len(choice_evidence_catalog(store, "run-a", "2024-12-31").rows) == 1


def test_choice_evidence_catalog_keeps_label_only_rejected_and_unclassified_receipts(tmp_path):
    store = AtlasStore(tmp_path / "atlas.sqlite3")
    seed_model(
        store,
        import_id="label-only",
        source_id=None,
        fitted=False,
        label_only=True,
        observations=[
            {
                "country_code": "CA",
                "behaviour": "go_out",
                "traits": {"extraversion": 0.8},
                "outcome": None,
                "weight": 1,
            }
        ],
    )
    seed_model(store, import_id="rejected", active=False)

    rows = {row.provenance.import_id: row for row in choice_evidence_catalog(store).rows}

    assert rows["label-only"].model_status == "label_only"
    assert rows["label-only"].source_status == "source_unclassified"
    assert rows["label-only"].source_type == "unclassified_upload"
    assert rows["label-only"].source_tier is None
    assert rows["label-only"].outcome_rate is None
    assert rows["rejected"].model_status == "rejected_fit"


def test_universal_feature_overview_contains_no_smoke_data():
    overview = universal_feature_overview()

    assert len(overview.registry.definitions) >= 20
    assert overview.registry.distributions == []
    assert all(
        not resolution.source or not resolution.source.startswith("FAKE")
        for resolution in overview.resolutions
    )
