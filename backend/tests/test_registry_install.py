import json

from petraterrium.atlas.database import AtlasStore
from petraterrium.atlas.feature_catalog import FeatureCatalogStore
from petraterrium.atlas.feature_dump.parquet import write_rows
from petraterrium.atlas.feature_dump.registry_install import install_registry_dump
from petraterrium.atlas.feature_queries import FeatureQueryService
from petraterrium.atlas.features import canonical_feature_registry
from petraterrium.atlas.hierarchy_queue import hierarchy_browser_page
from petraterrium.atlas.joint_estimates import PlaceSelector, feature_inheritance


def write_registry_dump(path):
    path.mkdir()
    country_age_sex = [
        {
            "country_code": code,
            "country_name": name,
            "region": region,
            "year": 2023,
            "age_group": age,
            "sex": sex,
            "population": population,
            "population_percent": 0.0,
            "source_variant": "Medium",
        }
        for code, name, region, values in [
            ("CA", "Canada", "Northern America", (30, 20, 25, 25)),
            ("MX", "Mexico", "Latin America & Caribbean", (50, 30, 40, 30)),
        ]
        for age, sex, population in [
            ("0-4", "female", values[0]),
            ("0-4", "male", values[1]),
            ("5-9", "female", values[2]),
            ("5-9", "male", values[3]),
        ]
    ]
    region_age_sex = [
        {
            "region": region,
            "year": 2023,
            "age_group": row["age_group"],
            "sex": row["sex"],
            "population": row["population"],
            "population_percent": 0.0,
            "countries_covered": 1,
            "source_variant": "Medium",
        }
        for row in country_age_sex
        for region in [row["region"]]
    ]
    country_population = [
        {
            "country_code": "CA",
            "country_name": "Canada",
            "region": "Northern America",
            "year": 2023,
            "population": 100,
            "source_variant": "Medium",
            "global_population_percent": 40.0,
            "region_population_percent": 100.0,
        },
        {
            "country_code": "MX",
            "country_name": "Mexico",
            "region": "Latin America & Caribbean",
            "year": 2023,
            "population": 150,
            "source_variant": "Medium",
            "global_population_percent": 60.0,
            "region_population_percent": 100.0,
        },
    ]
    region_population = [
        {
            "region": row["region"],
            "year": 2023,
            "population": row["population"],
            "global_population_percent": row["global_population_percent"],
            "countries_covered": 1,
            "source_variant": "Medium",
        }
        for row in country_population
    ]
    indicators = [
        {
            "country_code": "CA",
            "country_name": "Canada",
            "region": "Northern America",
            "year": 2023,
            "indicator": "MedianAgePop",
            "indicator_name": "Median age",
            "topic": "Age structure",
            "unit": "years",
            "value": 41.0,
            "source_variant": "Medium",
        }
    ]
    write_rows(path / "wpp_country_age_sex.parquet", country_age_sex)
    write_rows(path / "wpp_region_age_sex.parquet", region_age_sex)
    write_rows(path / "wpp_country_population.parquet", country_population)
    write_rows(path / "wpp_region_population.parquet", region_population)
    write_rows(path / "wpp_country_demographic_indicators.parquet", indicators)
    inventory = [
        {
            "source_id": "un_wpp_2024_regions",
            "source": "UN World Population Prospects",
            "scope_order": 1,
            "level": "region",
            "access_status": "imported",
            "source_url": "https://population.un.org/wpp/",
            "version": "2024 Revision",
            "source_date": "2024-07-11",
            "license": "CC BY 3.0 IGO",
            "mapping": {"age": "UN five-year age groups"},
            "coverage": {"regions": 2},
            "restriction_reason": "",
            "fallback": "No projection fallback",
            "required_action": "",
            "files": [],
        },
        {
            "source_id": "world_values_survey",
            "source": "World Values Survey",
            "scope_order": 2,
            "level": "country",
            "access_status": "unavailable",
            "source_url": "https://www.worldvaluessurvey.org/",
            "version": "User-selected wave required",
            "source_date": "",
            "license": "Registered access",
            "mapping": {"ideology_axes": "Separate item sets"},
            "coverage": {"imported_countries": 0},
            "restriction_reason": "No authorized extract is present",
            "fallback": "No ideology fallback",
            "required_action": "Supply a licensed wave and weights",
            "files": [],
        },
    ]
    (path / "source_inventory.json").write_text(json.dumps(inventory))
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "wpp": {
                    "source": "United Nations Population Division",
                    "version": "2024 Revision",
                    "published_date": "2024-07-11",
                    "license": "CC BY 3.0 IGO",
                    "estimate_year": 2023,
                    "mapping": {"age": "UN five-year age groups"},
                    "source_files": [{"role": "age_sex", "sha256": "abc"}],
                },
            }
        )
    )


def seed_places(store):
    with store.connection() as connection:
        connection.executemany(
            "INSERT INTO countries VALUES(?,?)",
            [("CA", "Canada"), ("MX", "Mexico")],
        )
        connection.executemany(
            "INSERT INTO cities VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    1,
                    "Toronto",
                    "Toronto",
                    "CA",
                    "08",
                    "",
                    43.65,
                    -79.38,
                    10,
                    "America/Toronto",
                    "PPL",
                    "simulated",
                ),
                (
                    2,
                    "Mexico City",
                    "Mexico City",
                    "MX",
                    "09",
                    "",
                    19.43,
                    -99.13,
                    20,
                    "America/Mexico_City",
                    "PPL",
                    "simulated",
                ),
            ],
        )


def test_registry_dump_installs_wpp_coverage_weights_features_and_inventory(tmp_path):
    dump = tmp_path / "dump"
    write_registry_dump(dump)
    store = AtlasStore(tmp_path / "atlas.sqlite3")
    seed_places(store)

    result = install_registry_dump(store, dump)
    repeated = install_registry_dump(store, dump)

    assert result["marginal_observations"] == 2
    assert result["feature_distributions"] == 8
    assert result["population_weights"] == 4
    assert result["place_indicators"] == 1
    assert repeated["marginal_observations"] == 0
    with store.connection() as connection:
        observations = connection.execute(
            "SELECT geo_key,value_json FROM observations WHERE field='age_sex' ORDER BY geo_key"
        ).fetchall()
        assert len(observations) == 2
        assert sum(json.loads(observations[0]["value_json"]).values()) == 100
        metadata = json.loads(
            connection.execute(
                "SELECT metadata_json FROM imports WHERE import_id=?",
                (result["import_id"],),
            ).fetchone()[0]
        )
        assert metadata["license"] == "CC BY 3.0 IGO"
        assert (
            connection.execute("SELECT COUNT(*) FROM registry_source_inventory").fetchone()[0]
            == 2
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM registry_place_indicators").fetchone()[0]
            == 1
        )

    catalog = FeatureCatalogStore(store)
    registry = catalog.enriched_registry(canonical_feature_registry())
    definitions = {definition.id for definition in registry.definitions}
    assert "age_band" in definitions
    assert len([item for item in registry.distributions if item.feature_id == "age_band"]) == 4
    service = FeatureQueryService(store)
    places = service.population_places(
        PlaceSelector(level="country", place="CA", label="Canada")
    )
    assert [(place.level, place.place, place.population) for place in places] == [
        ("country", "CA", 100)
    ]
    inheritance = feature_inheritance(
        service.registry(),
        places,
        PlaceSelector(level="country", place="CA", label="Canada"),
        "age_band",
    )
    assert inheritance.values[0].sources[0].status == "present"
    hierarchy = hierarchy_browser_page(store, as_of="2026-01-01")
    northern_america = next(row for row in hierarchy.rows if row.label == "Northern America")
    assert northern_america.population == 100
    assert northern_america.weight_source == "UN WPP 2024 Revision population"
