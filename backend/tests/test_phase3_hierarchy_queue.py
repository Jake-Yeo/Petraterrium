import json

from petraterrium.atlas.database import FIELDS, AtlasStore
from petraterrium.atlas.hierarchy_queue import hierarchy_browser_page


def seed_store(tmp_path):
    store = AtlasStore(tmp_path / "atlas.sqlite3")
    with store.connection() as conn:
        conn.executemany(
            "INSERT INTO countries VALUES(?,?)",
            [("CN", "China"), ("MX", "Mexico"), ("US", "United States")],
        )
        conn.executemany(
            "INSERT INTO cities VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    1,
                    "Shanghai",
                    "Shanghai",
                    "CN",
                    "SH",
                    "",
                    31,
                    121,
                    20_000_000,
                    "Asia/Shanghai",
                    "PPL",
                    "simulated",
                ),
                (
                    2,
                    "Mexico City",
                    "Mexico City",
                    "MX",
                    "CMX",
                    "",
                    19,
                    -99,
                    10_000_000,
                    "America/Mexico_City",
                    "PPL",
                    "simulated",
                ),
                (
                    3,
                    "Big City",
                    "Big City",
                    "US",
                    "A",
                    "",
                    40,
                    -74,
                    8_000_000,
                    "America/New_York",
                    "PPL",
                    "simulated",
                ),
                (
                    4,
                    "Small City",
                    "Small City",
                    "US",
                    "B",
                    "",
                    39,
                    -75,
                    1_000_000,
                    "America/New_York",
                    "PPL",
                    "disaggregated",
                ),
            ],
        )
    add_observations(store, "seed", [("country", "MX", FIELDS[0])])
    add_observations(store, "direct", [("city", "3", feature) for feature in FIELDS])
    add_observations(store, "regional", [("region", "US:B", FIELDS[0])])
    return store


def add_observations(store, import_id, observations):
    with store.connection() as conn:
        conn.execute(
            """INSERT INTO imports(import_id,source,source_date,published_date,version,scope,
            uploader,kind,filename,row_count,status,metadata_json,rows_json,mapping_json,
            audit_json,validation_json,validated_json,promoted_from,redistribution_allowed,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                import_id,
                "FAKE hierarchy test",
                "2020-01-01",
                "2020-01-02",
                "v1",
                "shared",
                "test",
                "marginals",
                "test.json",
                len(observations),
                "committed",
                "{}",
                "[]",
                "[]",
                "{}",
                "{}",
                "[]",
                None,
                1,
                "2020-01-02T00:00:00",
            ),
        )
        conn.executemany(
            "INSERT INTO observations(import_id,geo_level,geo_key,field,value_json,unit) "
            "VALUES(?,?,?,?,?,?)",
            [
                (import_id, level, key, feature, json.dumps({"value": 100}), "percent")
                for level, key, feature in observations
            ],
        )


def test_regions_are_default_and_queue_uses_population_weighted_missing_impact(tmp_path):
    store = seed_store(tmp_path)
    result = hierarchy_browser_page(store, as_of="2021-01-01", page_size=20)
    assert result.level == "region"
    assert result.breadcrumbs[0].label == "Regions"
    assert all(row.level == "region" for row in result.rows)
    populated = {row.label: row for row in result.rows if row.population}
    assert populated["China"].status == "no_data"
    assert populated["Northern America"].status == "partial"
    assert populated["Latin America & Caribbean"].counts.inherited == 1
    assert populated["Latin America & Caribbean"].measured_coverage_percent == 0
    assert populated["Latin America & Caribbean"].effective_coverage_percent == round(
        100 / len(FIELDS), 6
    )
    assert result.queue[0].row_id == "region:China"
    assert result.queue[1].row_id == "country:CN"
    assert result.queue[0].missing_impact == result.queue[1].missing_impact


def test_drilldown_search_and_city_pagination_stay_within_current_level(tmp_path):
    store = seed_store(tmp_path)
    countries = hierarchy_browser_page(
        store,
        as_of="2021-01-01",
        level="country",
        parent_id="region:Northern America",
        search="unit",
    )
    assert countries.filtered_count == 1
    assert countries.rows[0].row_id == "country:US"
    first = hierarchy_browser_page(
        store,
        as_of="2021-01-01",
        level="city",
        parent_id="country:US",
        page_size=1,
    )
    assert first.filtered_count == 2
    assert len(first.rows) == 1
    assert first.rows[0].label == "Small City"
    assert first.rows[0].status == "partial"
    searched = hierarchy_browser_page(
        store,
        as_of="2021-01-01",
        level="city",
        parent_id="country:US",
        search="Big",
    )
    assert searched.filtered_count == 1
    assert searched.rows[0].label == "Big City"
    assert searched.rows[0].status == "complete"


def test_filling_missing_country_fields_removes_country_and_region_from_queue(tmp_path):
    store = seed_store(tmp_path)
    before = hierarchy_browser_page(store, as_of="2021-01-01")
    assert {row.row_id for row in before.queue} >= {"region:China", "country:CN"}
    add_observations(store, "china-complete", [("country", "CN", feature) for feature in FIELDS])
    after = hierarchy_browser_page(store, as_of="2021-01-01")
    queue_ids = {row.row_id for row in after.queue}
    assert "region:China" not in queue_ids
    assert "country:CN" not in queue_ids
    china = next(row for row in after.rows if row.label == "China")
    assert china.status == "complete"
    assert china.measured_coverage_percent == 0
    assert china.effective_coverage_percent == 100


def test_dynamic_field_list_does_not_assume_legacy_feature_names(tmp_path):
    store = seed_store(tmp_path)
    fields = ("economic_axis", "state_axis", "cultural_axis")
    add_observations(store, "new-axis", [("city", "3", fields[0])])
    result = hierarchy_browser_page(
        store,
        as_of="2021-01-01",
        level="city",
        parent_id="country:US",
        fields=fields,
    )
    big_city = next(row for row in result.rows if row.label == "Big City")
    assert big_city.counts.present == 1
    assert big_city.missing_fields == ["state_axis", "cultural_axis"]
    assert big_city.measured_coverage_percent == round(100 / 3, 6)
