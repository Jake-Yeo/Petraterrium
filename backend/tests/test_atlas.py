import io
import json
from datetime import date
from decimal import Decimal

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from petraterrium.atlas.contracts import (
    ImportCommit,
    ImportMetadata,
    MappingConfirmation,
    Promotion,
)
from petraterrium.atlas.database import FIELDS, AtlasStore
from petraterrium.atlas.formats import parse_upload
from petraterrium.atlas.imports import (
    commit_import,
    import_history,
    promote_import,
    stage_import,
    validate_import,
)
from petraterrium.atlas.organizer import city_detail, overview


@pytest.fixture
def atlas(tmp_path):
    store = AtlasStore(tmp_path / "atlas.sqlite3")
    with store.connection() as conn:
        conn.executemany(
            "INSERT INTO countries VALUES(?,?)",
            [("IT", "Italy"), ("FR", "France"), ("DE", "Germany")],
        )
        conn.executemany(
            "INSERT INTO cities VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    1,
                    "Alpha",
                    "Alpha",
                    "IT",
                    "A",
                    "",
                    42,
                    12,
                    1000,
                    "Europe/Rome",
                    "PPL",
                    "disaggregated",
                ),
                (
                    2,
                    "Alpha Town",
                    "Alpha Town",
                    "IT",
                    "B",
                    "",
                    43,
                    13,
                    2000,
                    "Europe/Rome",
                    "PPL",
                    "disaggregated",
                ),
                (
                    3,
                    "Beta",
                    "Beta",
                    "FR",
                    "C",
                    "",
                    44,
                    14,
                    3000,
                    "Europe/Paris",
                    "PPL",
                    "disaggregated",
                ),
                (
                    4,
                    "Gamma",
                    "Gamma",
                    "DE",
                    "D",
                    "",
                    45,
                    15,
                    4000,
                    "Europe/Berlin",
                    "PPL",
                    "disaggregated",
                ),
                (
                    5,
                    "Delta",
                    "Delta",
                    "DE",
                    "E",
                    "",
                    46,
                    16,
                    5000,
                    "Europe/Berlin",
                    "PPL",
                    "simulated",
                ),
            ],
        )
    return store


def metadata(**updates):
    return ImportMetadata(
        run_id="run-a",
        source="FAKE test observations",
        source_date=date(2020, 1, 1),
        published_date=date(2020, 1, 2),
        version="v1",
        redistribution_allowed=True,
        **updates,
    )


def preview_and_confirmation(store, rows, meta=None):
    preview = stage_import(store, "test.json", meta or metadata(), rows, use_llm=False)
    confirmation = MappingConfirmation(
        mappings=[mapping.model_copy(update={"ambiguous": False}) for mapping in preview.mappings],
        confirmed=True,
    )
    return preview, confirmation


def save(store, rows, meta=None):
    preview, confirmation = preview_and_confirmation(store, rows, meta)
    report = validate_import(store, preview.import_id, preview.metadata.run_id, confirmation)
    assert report.valid, report.issues
    return commit_import(
        store,
        preview.import_id,
        preview.metadata.run_id,
        ImportCommit(mapping_hash=report.mapping_hash, confirmed=True),
    )


def marginals():
    return {
        field: ({"first": 50, "second": 50} if field != "household_size" else 2.5)
        for field in FIELDS
    }


def seed_coverage(atlas):
    return save(
        atlas,
        [
            {"geonameid": 1, "country_code": "IT", **marginals()},
            {"country_code": "IT", **marginals()},
            {"country_code": "FR", "admin1": "C", **marginals()},
            {"geonameid": 5, "country_code": "DE", "age_sex": {"male": 40, "female": 60}},
        ],
    )


def test_exact_coverage_statuses_weighting_and_missing_priorities(atlas):
    seed_coverage(atlas)
    result = overview(atlas, scope="run-a")
    assert result.summary.total_cities == 5
    assert result.summary.direct.model_dump() == {"full": 1, "partial": 1, "none": 3}
    assert result.summary.direct_plus_inherited.model_dump() == {"full": 2, "partial": 1, "none": 2}
    age = next(field for field in result.summary.fields if field.field == "age_sex")
    assert (age.present, age.inherited, age.imputed, age.missing) == (2, 1, 1, 1)
    assert age.direct_percent == 40
    assert age.direct_plus_inherited_percent == 60
    assert age.direct_population_percent == 40
    assert age.direct_plus_inherited_population_percent == pytest.approx(53.333333)
    income = next(field for field in result.summary.fields if field.field == "income")
    assert (income.present, income.inherited, income.imputed, income.missing) == (1, 1, 1, 2)
    assert income.direct_population_percent == pytest.approx(6.666667)
    assert income.direct_plus_inherited_population_percent == 20
    cities = {city.geonameid: city for city in result.cities}
    assert [cities[i].status for i in (1, 2, 3, 4)] == [
        "present",
        "inherited",
        "imputed",
        "missing",
    ]
    assert cities[3].coverage_percent == 0 and cities[3].resolved_coverage_percent == 100
    assert all(gap.population == 5000 for gap in result.gaps[:4])
    assert set(city_detail(atlas, 5, "run-a").missing_fields) == set(FIELDS) - {"age_sex"}


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("age_sex", {"male": 50, "female": 49}, "expected 100"),
        ("education", {"one": 120, "two": -20}, "between 0 and 100"),
        ("household_size", 42, "outside"),
        ("ideology", 1.2, "distribution"),
    ],
)
def test_invalid_data_blocks_every_write_and_identifies_row_field(atlas, field, value, message):
    preview, confirmation = preview_and_confirmation(
        atlas, [{"geonameid": 1, "country_code": "IT", field: value}]
    )
    report = validate_import(atlas, preview.import_id, "run-a", confirmation)
    assert not report.valid
    assert report.issues[0].row == 1 and report.issues[0].field == field
    assert message in report.issues[0].message
    with pytest.raises(ValueError):
        commit_import(
            atlas,
            preview.import_id,
            "run-a",
            ImportCommit(mapping_hash=report.mapping_hash, confirmed=True),
        )
    with atlas.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0


def test_ambiguous_mapping_waits_for_explicit_confirmation(atlas):
    preview = stage_import(
        atlas, "ambiguous.json", metadata(), [{"country_code": "IT", "score": 4}], False
    )
    assert next(m for m in preview.mappings if m.column == "score").ambiguous
    report = validate_import(
        atlas,
        preview.import_id,
        "run-a",
        MappingConfirmation(mappings=preview.mappings, confirmed=True),
    )
    assert not report.valid and report.issues[0].field == "mapping"
    with atlas.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0


def test_whole_field_and_component_mapping_conflict_is_reported(atlas):
    draft, confirmation = preview_and_confirmation(
        atlas, [{"geonameid": 1, "age_sex": {"m": 50, "f": 50}, "age_sex.m": 50}]
    )
    report = validate_import(atlas, draft.import_id, "run-a", confirmation)
    assert not report.valid and report.issues[0].field == "mapping"


def test_fractional_geonameid_is_rejected(atlas):
    draft, confirmation = preview_and_confirmation(atlas, [{"geonameid": 1.5, "household_size": 2}])
    report = validate_import(atlas, draft.import_id, "run-a", confirmation)
    assert not report.valid


def test_scopes_versions_promotion_and_as_of_are_isolated(atlas):
    version = save(atlas, [{"geonameid": 1, "household_size": 2}])
    assert overview(atlas, "shared").summary.direct.none == 5
    assert overview(atlas, "run-b").summary.direct.none == 5
    with pytest.raises(ValueError):
        promote_import(
            atlas,
            version.import_id,
            "run-a",
            Promotion(confirmed=False, redistribution_confirmed=True),
        )
    promoted = promote_import(
        atlas, version.import_id, "run-a", Promotion(confirmed=True, redistribution_confirmed=True)
    )
    assert promoted.scope == "shared" and promoted.promoted_from == version.import_id
    newer = metadata().model_copy(
        update={
            "source_date": date(2021, 1, 1),
            "published_date": date(2021, 1, 2),
            "version": "v2",
        }
    )
    save(atlas, [{"geonameid": 1, "household_size": 3}], newer)
    current = city_detail(atlas, 1, "run-a")
    historical = city_detail(atlas, 1, "run-a", "2020-06-01")

    def field(detail):
        return next(f for f in detail.city.fields if f.field == "household_size")

    assert field(current).value == 3
    assert field(current).provenance.version == "v2"
    assert field(historical).value == 2
    assert field(historical).provenance.version == "v1"
    assert len(current.history) == 3
    assert len(import_history(atlas, "run-a").versions) == 3
    assert field(city_detail(atlas, 1, "run-b")).value == 2


def test_search_country_filters_missing_field_and_pagination(atlas):
    result = overview(atlas, search="Alpha", country="IT", page_size=1)
    assert result.filtered_count == 2 and len(result.cities) == 1
    assert result.cities[0].geonameid == 2
    assert overview(atlas, search="Alpha", country="FR").filtered_count == 0
    seed_coverage(atlas)
    assert [c.geonameid for c in overview(atlas, "run-a", missing_field="age_sex").cities] == [4]
    assert overview(atlas, tier="simulated").cities[0].geonameid == 5


def test_csv_json_and_parquet_are_all_accepted():
    assert parse_upload("rows.csv", b"geonameid,household_size\n1,2\n")[0]["household_size"] == "2"
    rows = [{"geonameid": 1, "household_size": 2}]
    assert parse_upload("rows.json", json.dumps(rows).encode()) == rows
    buffer = io.BytesIO()
    pq.write_table(pa.Table.from_pylist(rows), buffer)
    assert parse_upload("rows.parquet", buffer.getvalue()) == rows


def test_parquet_decimals_survive_staging_without_json_serialization_errors():
    buffer = io.BytesIO()
    pq.write_table(
        pa.Table.from_pylist([{"geonameid": 1, "household_size": Decimal("2.50")}]), buffer
    )
    rows = parse_upload("decimal.parquet", buffer.getvalue())
    assert rows[0]["household_size"] == "2.50"
    assert json.loads(json.dumps(rows))[0]["household_size"] == "2.50"


def test_commit_returns_the_committed_version_when_a_newer_draft_exists(atlas):
    first, confirmation = preview_and_confirmation(atlas, [{"geonameid": 1, "household_size": 2}])
    preview_and_confirmation(atlas, [{"geonameid": 2, "household_size": 3}])
    report = validate_import(atlas, first.import_id, "run-a", confirmation)
    committed = commit_import(
        atlas,
        first.import_id,
        "run-a",
        ImportCommit(mapping_hash=report.mapping_hash, confirmed=True),
    )
    assert committed.import_id == first.import_id
    assert committed.status == "committed"


def test_label_only_behaviour_never_gets_invented_coefficients(atlas):
    save(atlas, [{"country_code": "IT", "trait.income": 3}], metadata(kind="behaviour"))
    model = city_detail(atlas, 1, "run-a").city.behaviour[0]
    assert model.label_only and not model.fitted
    with atlas.connection() as conn:
        assert "coefficients" not in json.loads(
            conn.execute("SELECT specification_json FROM models").fetchone()[0]
        )


def test_behaviour_validation_reports_missing_actions_and_traits(atlas):
    draft, confirmation = preview_and_confirmation(
        atlas, [{"country_code": "IT", "trait.income": 3}], metadata(kind="behaviour")
    )
    report = validate_import(atlas, draft.import_id, "run-a", confirmation)
    assert report.valid
    assert report.missingness["outcome"] == 1
    assert report.missingness["trait.income"] == 0


def test_logit_is_fitted_from_linked_data_and_only_activated_if_better(atlas):
    rng = np.random.default_rng(73)
    rows = []
    for _ in range(400):
        trait = float(rng.normal())
        rows.append(
            {
                "country_code": "IT",
                "trait.income": trait,
                "outcome": int(rng.random() < 1 / (1 + np.exp(-3 * trait))),
            }
        )
    version = save(atlas, rows, metadata(kind="behaviour"))
    model = city_detail(atlas, 1, "run-a").city.behaviour[0]
    assert model.fitted and not model.label_only
    assert model.heldout_loss < model.baseline_loss
    assert model.training_rows + model.heldout_rows == 400
    with atlas.connection() as conn:
        first = json.loads(
            conn.execute(
                "SELECT specification_json FROM models WHERE import_id=?", (version.import_id,)
            ).fetchone()[0]
        )
    assert first["algorithm"] == "weighted-logit-irls-v1"
    assert first["coefficients"][1] > 0


def test_atlas_api_pagination_and_explicit_import_commit(client):
    store = client.app.state.atlas
    with store.connection() as conn:
        conn.execute("INSERT INTO countries VALUES('IT','Italy')")
        conn.execute(
            "INSERT INTO cities VALUES(1,'Alpha','Alpha','IT','A','',42,12,1000,'Euro"
            "pe/Rome','PPL','disaggregated')"
        )
    identity = client.post("/runs", json={"countries": ["ITA"], "end_day": 2}).json()["run_id"]
    meta = metadata().model_copy(update={"run_id": identity})
    preview = client.post(
        "/atlas/imports/preview",
        files={"file": ("rows.json", b'[{"geonameid":1,"household_size":2}]', "application/json")},
        data={"metadata": meta.model_dump_json(), "use_llm": "false"},
    )
    assert preview.status_code == 200, preview.text
    draft = preview.json()
    assert client.get("/atlas/overview").json()["summary"]["direct"]["none"] == 1
    confirmation = {
        "confirmed": True,
        "mappings": [{**m, "ambiguous": False} for m in draft["mappings"]],
    }
    validated = client.post(
        f"/atlas/imports/{draft['import_id']}/validate?scope={identity}", json=confirmation
    ).json()
    assert validated["valid"]
    committed = client.post(
        f"/atlas/imports/{draft['import_id']}/commit?scope={identity}",
        json={"confirmed": True, "mapping_hash": validated["mapping_hash"]},
    )
    assert committed.status_code == 200, committed.text
    assert (
        client.get("/atlas/overview", params={"scope": identity}).json()["summary"]["direct"][
            "partial"
        ]
        == 1
    )
    assert client.get("/atlas/overview", params={"page_size": 101}).status_code == 422
    assert (
        client.get("/atlas/overview", params={"scope": "other"}).json()["summary"]["direct"]["none"]
        == 1
    )
