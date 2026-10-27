import csv
import gzip
import json

import pyarrow.parquet as pq
import pytest

from petraterrium.atlas.feature_dump.registry_dump import build_registry_dump
from petraterrium.atlas.feature_dump.source_inventory import source_inventory
from petraterrium.atlas.feature_dump.wpp import (
    aggregate_region_age_sex,
    country_age_sex_rows,
    country_population_rows,
)


def write_gzip_csv(path, rows):
    with gzip.open(path, "wt", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


def test_wpp_uses_2023_estimates_without_projection_leakage(tmp_path):
    age_path = tmp_path / "age.csv.gz"
    population_path = tmp_path / "population.csv.gz"
    base = {
        "Region, subregion, country or area *": "United States of America",
        "ISO3 Alpha-code": "USA",
        "Type": "Country/Area",
        "Age": "0-4",
        "PopMale": "10",
        "PopFemale": "11",
    }
    write_gzip_csv(
        age_path,
        [
            base | {"Variant": "Estimates", "Time": "2022"},
            base | {"Variant": "Estimates", "Time": "2023"},
            base | {"Variant": "Medium", "Time": "2024", "PopMale": "900"},
            base
            | {
                "Region, subregion, country or area *": "Northern America",
                "ISO3 Alpha-code": "",
                "Type": "Subregion",
                "Variant": "Estimates",
                "Time": "2023",
            },
        ],
    )
    write_gzip_csv(
        population_path,
        [
            {
                "Region, subregion, country or area *": "United States of America",
                "ISO3 Alpha-code": "USA",
                "Type": "Country/Area",
                "Variant": "Estimates",
                "Year": "2023",
                "PopTotal": "21",
                "PopMale": "10",
                "PopFemale": "11",
            },
            {
                "Region, subregion, country or area *": "United States of America",
                "ISO3 Alpha-code": "USA",
                "Type": "Country/Area",
                "Variant": "Medium",
                "Year": "2024",
                "PopTotal": "999",
                "PopMale": "499",
                "PopFemale": "500",
            },
        ],
    )
    age_rows = country_age_sex_rows(age_path, 2023)
    population_rows = country_population_rows(population_path, 2023)
    assert {(row["year"], row["sex"], row["population"]) for row in age_rows} == {
        (2023, "female", 11_000),
        (2023, "male", 10_000),
    }
    assert population_rows == [
        {
            "country_code": "US",
            "country_name": "United States of America",
            "region": "Northern America",
            "year": 2023,
            "population": 21_000,
            "source_variant": "Estimates",
            "global_population_percent": 100.0,
            "region_population_percent": 100.0,
        }
    ]
    with pytest.raises(ValueError, match="2024 is projection"):
        country_age_sex_rows(age_path, 2024)


def test_wpp_region_aggregation_is_population_weighted():
    rows = [
        {
            "country_code": "US",
            "country_name": "United States",
            "region": "Northern America",
            "year": 2023,
            "age_group": "0-4",
            "sex": "female",
            "population": 10,
            "population_percent": 10.0,
            "source_variant": "Estimates",
        },
        {
            "country_code": "US",
            "country_name": "United States",
            "region": "Northern America",
            "year": 2023,
            "age_group": "5-9",
            "sex": "female",
            "population": 90,
            "population_percent": 90.0,
            "source_variant": "Estimates",
        },
        {
            "country_code": "CA",
            "country_name": "Canada",
            "region": "Northern America",
            "year": 2023,
            "age_group": "0-4",
            "sex": "female",
            "population": 90,
            "population_percent": 90.0,
            "source_variant": "Estimates",
        },
        {
            "country_code": "CA",
            "country_name": "Canada",
            "region": "Northern America",
            "year": 2023,
            "age_group": "5-9",
            "sex": "female",
            "population": 10,
            "population_percent": 10.0,
            "source_variant": "Estimates",
        },
    ]
    result = aggregate_region_age_sex(rows)
    assert [(row["age_group"], row["population"]) for row in result] == [
        ("0-4", 100),
        ("5-9", 100),
    ]
    assert all(row["population_percent"] == 50.0 for row in result)
    assert all(row["countries_covered"] == 2 for row in result)


def test_source_inventory_has_honest_mappings_and_restrictions(tmp_path):
    records = source_inventory(tmp_path)
    by_id = {record["source_id"]: record for record in records}
    assert by_id["world_bank_wdi"]["mapping"]["education"]["standard"] == "ISCED 2011"
    assert by_id["world_bank_wdi"]["mapping"]["income"]["limitation"].startswith(
        "Income quintile shares"
    )
    assert by_id["ipums_international"]["access_status"] == "unavailable"
    assert "redistribution" in by_id["ipums_international"]["restriction_reason"].lower()
    assert by_id["world_values_survey"]["access_status"] == "unavailable"
    assert by_id["european_social_survey"]["license"] == "CC BY-NC-SA 4.0"
    assert by_id["pew_global_attitudes"]["required_action"]
    assert by_id["worldpop"]["license"] == "CC BY 4.0"
    assert all(record["scope_order"] in {1, 2, 3} for record in records)
    assert all("coverage" in record for record in records)


def test_registry_manifest_orders_levels_and_records_verified_files(tmp_path, monkeypatch):
    data_directory = tmp_path / "data"
    source_directory = data_directory / "sources"
    source_directory.mkdir(parents=True)
    age_path = source_directory / "WPP2024_PopulationByAge5GroupSex_Medium.csv.gz"
    population_path = source_directory / "WPP2024_Demographic_Indicators_Medium.csv.gz"
    notes_path = source_directory / "WPP2024_Demographic_Indicators_notes.csv"
    write_gzip_csv(
        age_path,
        [
            {
                "Region, subregion, country or area *": "Mexico",
                "ISO3 Alpha-code": "MEX",
                "Type": "Country/Area",
                "Variant": "Estimates",
                "Time": "2023",
                "Age": "0-4",
                "PopMale": "40",
                "PopFemale": "60",
            }
        ],
    )
    write_gzip_csv(
        population_path,
        [
            {
                "Region, subregion, country or area *": "Mexico",
                "ISO3 Alpha-code": "MEX",
                "Type": "Country/Area",
                "Variant": "Estimates",
                "Year": "2023",
                "PopTotal": "100",
                "PopMale": "40",
                "PopFemale": "60",
            }
        ],
    )
    write_csv(
        notes_path,
        [
            {
                "IndicatorNo": "1",
                "Topic": "Population",
                "Indicator": "PopTotal",
                "IndicatorName": "Total population",
                "Unit": "thousands",
            }
        ],
    )
    monkeypatch.setattr(
        "petraterrium.atlas.feature_dump.registry_dump.acquire_wpp_sources",
        lambda *_args, **_kwargs: {
            "age_sex": age_path,
            "demographic_indicators": population_path,
            "demographic_notes": notes_path,
        },
    )
    manifest = build_registry_dump(data_directory, expected_digests=None)
    output = data_directory / "registry_feature_dump"
    assert manifest["level_order"] == ["region", "country", "city"]
    assert manifest["wpp"]["estimate_year"] == 2023
    assert manifest["wpp"]["projection_rows_used"] == 0
    assert manifest["wpp"]["country_age_sex_rows"] == 2
    assert manifest["wpp"]["region_age_sex_rows"] == 2
    assert all(source["sha256"] for source in manifest["wpp"]["source_files"])
    assert (
        pq.read_table(output / "wpp_country_population.parquet").to_pylist()[0]["population"]
        == 100_000
    )
    indicators = pq.read_table(
        output / "wpp_country_demographic_indicators.parquet"
    ).to_pylist()
    indicator = next(row for row in indicators if row["indicator"] == "PopTotal")
    assert indicator["indicator_name"] == "Total population"
    assert indicator["unit"] == "thousands"
    assert json.loads((output / "manifest.json").read_text())["sources"][0]["scope_order"] == 1


def test_registry_build_rejects_digest_mismatch(tmp_path, monkeypatch):
    source_directory = tmp_path / "sources"
    source_directory.mkdir()
    source = source_directory / "source.csv.gz"
    write_gzip_csv(source, [{"a": "b"}])
    monkeypatch.setattr(
        "petraterrium.atlas.feature_dump.registry_dump.acquire_wpp_sources",
        lambda *_args, **_kwargs: {
            "age_sex": source,
            "demographic_indicators": source,
            "demographic_notes": source,
        },
    )
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        build_registry_dump(
            tmp_path,
            expected_digests={"age_sex": "0" * 64, "demographic_indicators": "0" * 64},
        )
