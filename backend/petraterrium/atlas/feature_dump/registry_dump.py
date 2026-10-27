import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from .downloads import download, sha256_file
from .parquet import write_rows
from .source_inventory import source_inventory
from .wpp import (
    WPP_AGE_SEX_URL,
    WPP_DEMOGRAPHIC_INDICATORS_URL,
    WPP_DEMOGRAPHIC_NOTES_URL,
    WPP_ESTIMATE_YEAR,
    WPP_LICENSE,
    WPP_VERSION,
    aggregate_region_age_sex,
    aggregate_region_populations,
    country_age_sex_rows,
    country_population_rows,
    demographic_indicator_rows,
)

WPP_FILES = {
    "age_sex": "WPP2024_PopulationByAge5GroupSex_Medium.csv.gz",
    "demographic_indicators": "WPP2024_Demographic_Indicators_Medium.csv.gz",
    "demographic_notes": "WPP2024_Demographic_Indicators_notes.csv",
}
WPP_URLS = {
    "age_sex": WPP_AGE_SEX_URL,
    "demographic_indicators": WPP_DEMOGRAPHIC_INDICATORS_URL,
    "demographic_notes": WPP_DEMOGRAPHIC_NOTES_URL,
}
EXPECTED_WPP_SHA256 = {
    "age_sex": "a04d7d1486a5eb2832cc812d599448f0a71e8ac9e1e7e6fa4066673d6a2487cd",
    "demographic_indicators": "286ac36bb1415e2e1ade03acfef0a29f0e4c087e2f78e38c48f50c5df89082bc",
    "demographic_notes": "c6063ba18b23e899c02bb7f9c78b6e410f25b30cb9d40b66eda032e1127bea49",
}


def acquire_wpp_sources(data_directory: Path, refresh=False) -> dict[str, Path]:
    source_directory = data_directory / "sources"
    return {
        key: download(url, source_directory / WPP_FILES[key], refresh)
        for key, url in WPP_URLS.items()
    }


def verified_source_files(
    paths: dict[str, Path], expected_digests: dict[str, str] | None
) -> tuple[dict[str, str], list[dict]]:
    digests = {key: sha256_file(path) for key, path in paths.items()}
    if expected_digests is not None:
        for key, expected in expected_digests.items():
            actual = digests.get(key)
            if actual != expected:
                raise ValueError(
                    f"SHA-256 mismatch for {key}: expected {expected}, received {actual}"
                )
    files = [
        {
            "role": key,
            "filename": path.name,
            "bytes": path.stat().st_size,
            "sha256": digests[key],
            "expected_sha256": expected_digests.get(key) if expected_digests else None,
            "digest_verified": expected_digests is not None,
            "source_url": WPP_URLS[key],
        }
        for key, path in sorted(paths.items())
    ]
    return digests, files


def output_file_inventory(output: Path) -> list[dict]:
    return [
        {
            "path": str(path.relative_to(output)),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    ]


def write_source_inventory(output: Path, records: list[dict]) -> None:
    (output / "source_inventory.json").write_text(json.dumps(records, indent=2) + "\n")
    write_rows(
        output / "source_inventory.parquet",
        [
            {
                "source_id": row["source_id"],
                "source": row["source"],
                "scope_order": row["scope_order"],
                "level": row["level"],
                "access_status": row["access_status"],
                "source_url": row["source_url"],
                "version": row["version"],
                "source_date": row["source_date"],
                "license": row["license"],
                "mapping_json": json.dumps(row["mapping"], sort_keys=True),
                "coverage_json": json.dumps(row["coverage"], sort_keys=True),
                "restriction_reason": row["restriction_reason"],
                "fallback": row["fallback"],
                "required_action": row["required_action"],
                "files_json": json.dumps(row["files"], sort_keys=True),
            }
            for row in records
        ],
    )


def build_registry_dump(
    data_directory: Path,
    output_directory: Path | None = None,
    refresh=False,
    expected_digests: dict[str, str] | None = EXPECTED_WPP_SHA256,
) -> dict:
    data_directory = data_directory.resolve()
    output_directory = (output_directory or data_directory / "registry_feature_dump").resolve()
    paths = acquire_wpp_sources(data_directory, refresh)
    _, source_files = verified_source_files(paths, expected_digests)
    partial = output_directory.with_name(output_directory.name + ".partial")
    if partial.exists():
        shutil.rmtree(partial)
    partial.mkdir(parents=True)
    country_age_sex = country_age_sex_rows(paths["age_sex"], WPP_ESTIMATE_YEAR)
    country_population = country_population_rows(paths["demographic_indicators"], WPP_ESTIMATE_YEAR)
    region_age_sex = aggregate_region_age_sex(country_age_sex)
    region_population = aggregate_region_populations(country_population)
    indicators = demographic_indicator_rows(
        paths["demographic_indicators"],
        WPP_ESTIMATE_YEAR,
        paths["demographic_notes"],
    )
    write_rows(partial / "wpp_region_age_sex.parquet", region_age_sex)
    write_rows(partial / "wpp_region_population.parquet", region_population)
    write_rows(partial / "wpp_country_age_sex.parquet", country_age_sex)
    write_rows(partial / "wpp_country_population.parquet", country_population)
    write_rows(partial / "wpp_country_demographic_indicators.parquet", indicators)
    inventory = source_inventory(data_directory, partial)
    write_source_inventory(partial, inventory)
    countries = {row["country_code"] for row in country_population}
    regions = {row["region"] for row in region_population}
    manifest = {
        "format_version": 1,
        "built_at": datetime.now(UTC).isoformat(),
        "level_order": ["region", "country", "city"],
        "wpp": {
            "source": (
                "United Nations, Department of Economic and Social Affairs, "
                "Population Division"
            ),
            "version": WPP_VERSION,
            "published_date": "2024-07-11",
            "license": WPP_LICENSE,
            "license_url": "https://creativecommons.org/licenses/by/3.0/igo/",
            "estimate_year": WPP_ESTIMATE_YEAR,
            "source_file_variant": "Medium",
            "period_classification": "estimate",
            "projection_rows_used": 0,
            "country_age_sex_rows": len(country_age_sex),
            "country_population_rows": len(country_population),
            "country_demographic_indicator_rows": len(indicators),
            "region_age_sex_rows": len(region_age_sex),
            "region_population_rows": len(region_population),
            "countries": len(countries),
            "regions": len(regions),
            "represented_population": sum(row["population"] for row in country_population),
            "coverage": {
                "country_population_percent": 100.0,
                "country_age_sex_percent": round(
                    len({row["country_code"] for row in country_age_sex}) * 100 / len(countries),
                    6,
                ),
                "canonical_regions_present": sorted(regions),
            },
            "mapping": {
                "geography": "UN ISO alpha-3 to ISO alpha-2, then canonical Petraterrium region",
                "age": "UN five-year age groups retained",
                "sex": "PopFemale and PopMale become separate female and male rows",
                "population": "Source thousands multiplied by 1,000 and rounded to persons",
                "demographic_indicators": (
                    "Indicator name, topic, and source unit joined from the official notes file"
                ),
                "regional_aggregation": (
                    "Country counts summed, then divided by covered region population"
                ),
            },
            "source_files": source_files,
        },
        "sources": inventory,
        "semantics": {
            "priority": (
                "Region outputs precede country outputs; city sources follow in the inventory"
            ),
            "estimate_cutoff": (
                "Only 2023 records from the Medium file are imported; the WPP 2024 estimate "
                "period ends in 2023 and projections begin in 2024"
            ),
            "inheritance": "Country and region observations retain their source place",
            "unavailable_sources": (
                "Restricted or account-gated microdata remain unavailable with required "
                "actions; no values "
                "are inferred"
            ),
        },
    }
    manifest["files"] = output_file_inventory(partial)
    (partial / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if output_directory.exists():
        shutil.rmtree(output_directory)
    partial.replace(output_directory)
    return manifest
