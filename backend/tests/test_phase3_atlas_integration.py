from datetime import date

from petraterrium.atlas.database import FIELDS, AtlasStore
from petraterrium.atlas.features import canonical_feature_registry


def seed_places(store: AtlasStore) -> None:
    with store.connection() as connection:
        connection.executemany(
            "INSERT INTO countries(code,name) VALUES(?,?)",
            [("CA", "Canada"), ("MX", "Mexico")],
        )
        connection.executemany(
            "INSERT INTO cities VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    1, "Toronto", "Toronto", "CA", "08", "", 43.65, -79.38,
                    2_794_356, "America/Toronto", "PPL", "simulated",
                ),
                (
                    2, "Montreal", "Montreal", "CA", "10", "", 45.50, -73.57,
                    1_762_949, "America/Toronto", "PPL", "simulated",
                ),
                (
                    3, "Mexico City", "Mexico City", "MX", "09", "", 19.43, -99.13,
                    9_209_944, "America/Mexico_City", "PPL", "simulated",
                ),
            ],
        )


def test_active_marginals_replace_single_ideology_with_three_axes():
    assert "ideology" not in FIELDS
    assert {
        "ideology_economic",
        "ideology_state",
        "ideology_cultural",
    }.issubset(FIELDS)

    registry = canonical_feature_registry()
    definitions = {definition.id: definition for definition in registry.definitions}

    assert "ideology" not in definitions
    assert definitions["ideology_economic"].value_range.minimum == -1
    assert definitions["ideology_state"].value_range.maximum == 1
    assert "anarchist" in definitions["ideology_state"].description


def test_hierarchy_catalog_and_joined_query_routes_are_integrated(client):
    store = client.app.state.atlas
    seed_places(store)

    hierarchy = client.get("/atlas/hierarchy-browser")
    assert hierarchy.status_code == 200
    hierarchy_body = hierarchy.json()
    assert hierarchy_body["level"] == "region"
    assert {row["level"] for row in hierarchy_body["rows"]} == {"region"}
    assert hierarchy_body["queue"][0]["level"] == "region"

    catalog = client.get("/atlas/feature-catalog")
    assert catalog.status_code == 200
    catalog_by_id = {feature["id"]: feature for feature in catalog.json()["features"]}
    assert "ideology" not in catalog_by_id
    assert catalog_by_id["ideology_state"]["description"]

    created = client.post(
        "/atlas/feature-catalog",
        json={
            "id": "endurance",
            "name": "Endurance",
            "type": "continuous",
            "canonical_values": [],
            "value_range": {"minimum": 0, "maximum": 100, "unit": "score"},
            "description": "Sustained physical effort on a validated assessment.",
            "provenance_placeholder": "Population endurance survey",
            "status": "awaiting_data",
        },
    )
    assert created.status_code == 201
    assert created.json()["predictor_blocked"] is True

    places = client.get("/atlas/feature-query/places", params={"search": "Toronto"})
    assert places.status_code == 200
    assert any(place["level"] == "city" for place in places.json()["places"])

    estimate = client.post(
        "/atlas/feature-query/joined",
        json={
            "selector": {"level": "country", "place": "CA", "label": "Canada"},
            "filters": [
                {"feature_id": "sex", "operator": "eq", "values": ["female"]},
                {"feature_id": "education_isced", "operator": "eq", "values": ["6"]},
            ],
        },
    )
    assert estimate.status_code == 422
    assert "No resolved marginal" in estimate.json()["detail"]


def test_feature_description_is_editable_through_api(client):
    created = client.post(
        "/atlas/feature-catalog",
        json={
            "id": "endurance",
            "name": "Endurance",
            "type": "continuous",
            "canonical_values": [],
            "value_range": {"minimum": 0, "maximum": 100, "unit": "score"},
            "description": "",
            "provenance_placeholder": "Source pending",
            "status": "pending",
        },
    )
    assert created.status_code == 201
    assert created.json()["description"] == ""

    updated = client.patch(
        "/atlas/feature-catalog/endurance/description",
        json={"description": "Measured sustained effort."},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "Measured sustained effort."


def test_legacy_ideology_observation_is_excluded_from_active_coverage(tmp_path):
    store = AtlasStore(tmp_path / "atlas.sqlite3")
    seed_places(store)
    today = date.today().isoformat()
    with store.connection() as connection:
        connection.execute(
            "INSERT INTO imports VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "legacy",
                "Legacy survey",
                today,
                today,
                "v1",
                "shared",
                "test",
                "marginals",
                "legacy.json",
                1,
                "committed",
                "{}",
                "[]",
                "[]",
                "{}",
                "{}",
                "[]",
                None,
                1,
                today,
            ),
        )
        connection.execute(
            "INSERT INTO observations(import_id,geo_level,geo_key,field,value_json,unit) "
            "VALUES(?,?,?,?,?,?)",
            ("legacy", "country", "CA", "ideology", '{"left":50,"right":50}', "percent"),
        )

    from petraterrium.atlas.organizer import overview

    view = overview(store)
    assert view.summary.direct_plus_inherited.none == 3
    assert all(field.field != "ideology" for field in view.summary.fields)
