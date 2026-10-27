import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

import pyarrow as pa

from ..database import AtlasStore
from .downloads import acquire_sources, sha256_file
from .electoral import BLUE_DB_RECORD_URL, GISCO_LAU_URL, export_blue
from .geonames import export_geonames
from .households import HOUSEHOLD_URL, export_households
from .install import (
    TRANSFORM_VERSION,
    install_shared_electoral,
    install_shared_marginals,
)
from .parquet import RowWriter, write_rows
from .ucdb import UCDB_URL, export_ucdb
from .wdi import WDI_URL, export_wdi


def canonical_rows(wdi, households, digests):
    rows = []
    for row in wdi["canonical"]:
        rows.append(
            row
            | {
                "source": "World Bank World Development Indicators",
                "source_url": WDI_URL,
                "published_date": wdi["release_date"],
                "version": (
                    "sha256:" + digests["WDI_CSV.zip"] + ";transform:" + TRANSFORM_VERSION
                ),
                "filename": "WDI_CSV.zip",
            }
        )
    for row in households["canonical"]:
        rows.append(
            row
            | {
                "source": "UN DESA Database on Household Size and Composition 2026",
                "source_url": HOUSEHOLD_URL,
                "published_date": households["release_date"],
                "version": (
                    "sha256:"
                    + digests["UN_DESA_household_2026.xlsx"]
                    + ";transform:"
                    + TRANSFORM_VERSION
                ),
                "filename": "UN_DESA_household_2026.xlsx",
            }
        )
    return rows


def write_canonical(output: Path, rows: list[dict]):
    write_rows(
        output / "canonical_country_marginals.parquet",
        [
            {
                "country_code": row["country_code"],
                "field": row["field"],
                "year": row["year"],
                "value_json": json.dumps(row["value"], sort_keys=True, separators=(",", ":")),
                "unit": row["unit"],
                "source": row["source"],
                "source_url": row["source_url"],
                "published_date": row["published_date"],
                "version": row["version"],
            }
            for row in rows
        ],
    )


def write_availability(output, cities, wdi, households, ucdb, electoral):
    schema = pa.schema(
        [
            ("geonameid", pa.int64()),
            ("country_code", pa.string()),
            ("ucdb_id", pa.int64()),
            ("electoral_lau_id", pa.string()),
            ("spatially_imputed_feature_count", pa.int32()),
            ("electoral_imputed_feature_count", pa.int32()),
            ("electoral_election_count", pa.int32()),
            ("electoral_latest_date", pa.string()),
            ("electoral_alignment_status", pa.string()),
            ("country_inherited_feature_count", pa.int32()),
            ("total_available_feature_count", pa.int32()),
        ]
    )
    writer = RowWriter(output / "city_feature_availability.parquet", schema, 20_000)
    matched = ucdb["city_matches"]
    ucdb_counts = ucdb["feature_counts"]
    electoral_matches = electoral["city_matches"]
    electoral_counts = electoral["city_result_counts"]
    electoral_dates = electoral["city_latest_dates"]
    for row in cities.select(["geonameid", "country_code"]).to_pylist():
        urban_id = matched.get(row["geonameid"])
        spatial = int(ucdb_counts.get(urban_id, 0))
        election_count = int(electoral_counts.get(row["geonameid"], 0))
        electoral_feature = int(election_count > 0)
        inherited = int(wdi["latest_counts"].get(row["country_code"], 0)) + int(
            households["latest_counts"].get(row["country_code"], 0)
        )
        writer.add(
            {
                "geonameid": row["geonameid"],
                "country_code": row["country_code"],
                "ucdb_id": urban_id,
                "electoral_lau_id": electoral_matches.get(row["geonameid"]),
                "spatially_imputed_feature_count": spatial,
                "electoral_imputed_feature_count": electoral_feature,
                "electoral_election_count": election_count,
                "electoral_latest_date": electoral_dates.get(row["geonameid"]),
                "electoral_alignment_status": (
                    "imputed" if electoral_feature else "missing"
                ),
                "country_inherited_feature_count": inherited,
                "total_available_feature_count": spatial + inherited + electoral_feature,
            }
        )
    return writer.close()


def file_inventory(output: Path):
    return [
        {
            "path": str(path.relative_to(output)),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    ]


def extract_ucdb(source: Path, destination: Path):
    with ZipFile(source) as archive:
        with archive.open("GHS_UCDB_GLOBE_R2024A.gpkg") as source_file:
            with destination.open("wb") as target:
                shutil.copyfileobj(source_file, target, 1024 * 1024)


def build_feature_dump(
    data_directory: Path,
    output_directory: Path | None = None,
    database_path: Path | None = None,
    refresh=False,
    install_shared=False,
):
    data_directory = data_directory.resolve()
    output_directory = (output_directory or data_directory / "city_feature_dump").resolve()
    paths = acquire_sources(data_directory, refresh)
    digests = {name: sha256_file(path) for name, path in paths.items()}
    partial = output_directory.with_name(output_directory.name + ".partial")
    if partial.exists():
        shutil.rmtree(partial)
    partial.mkdir(parents=True)
    geopackage = data_directory / "sources" / "GHS_UCDB_GLOBE_R2024A.gpkg"
    extract_ucdb(paths["GHS_UCDB_GLOBE_R2024A_V1_2.zip"], geopackage)
    cities, geonames = export_geonames(paths["cities500.zip"], partial)
    wdi = export_wdi(paths["WDI_CSV.zip"], partial)
    households = export_households(paths["UN_DESA_household_2026.xlsx"], partial)
    ucdb = export_ucdb(
        paths["GHS_UCDB_GLOBE_R2024A_V1_2.zip"], geopackage, cities, partial
    )
    electoral = export_blue(
        paths["BLUE_DB.zip"],
        paths["LAU_RG_01M_2024_4326.gpkg"],
        cities,
        partial,
    )
    canonical = canonical_rows(wdi, households, digests)
    write_canonical(partial, canonical)
    availability_rows = write_availability(
        partial, cities, wdi, households, ucdb, electoral
    )
    manifest = {
        "format_version": 1,
        "transform_version": TRANSFORM_VERSION,
        "built_at": datetime.now(UTC).isoformat(),
        "geography": {
            "backbone": "GeoNames cities500 after documented exclusions",
            "cities": geonames["cities"],
            "countries": geonames["countries"],
            "city_availability_rows": availability_rows,
        },
        "sources": {
            "geonames": geonames | {"sha256": digests["cities500.zip"]},
            "ucdb": {
                key: value
                for key, value in ucdb.items()
                if key not in ("feature_counts", "city_matches")
            }
            | {"source_url": UCDB_URL, "sha256": digests["GHS_UCDB_GLOBE_R2024A_V1_2.zip"]},
            "wdi": {
                key: value
                for key, value in wdi.items()
                if key not in ("latest_counts", "canonical")
            }
            | {"source_url": WDI_URL, "sha256": digests["WDI_CSV.zip"]},
            "un_household": {
                key: value
                for key, value in households.items()
                if key not in ("latest_counts", "canonical")
            }
            | {
                "source_url": HOUSEHOLD_URL,
                "sha256": digests["UN_DESA_household_2026.xlsx"],
            },
            "blue_db": {
                key: value
                for key, value in electoral.items()
                if key
                not in ("city_matches", "city_result_counts", "city_latest_dates")
            }
            | {
                "source_url": BLUE_DB_RECORD_URL,
                "sha256": digests["BLUE_DB.zip"],
            },
            "gisco_lau_2024": {
                "source_url": GISCO_LAU_URL,
                "year": 2024,
                "sha256": digests["LAU_RG_01M_2024_4326.gpkg"],
                "use": "Point-in-polygon city-to-LAU matching; boundaries are not republished.",
            },
        },
        "canonical_marginals": {
            "observations": len(canonical),
            "fields": sorted({row["field"] for row in canonical}),
            "countries": len({row["country_code"] for row in canonical}),
        },
        "semantics": {
            "ucdb": "Urban-centre polygon values are spatially imputed onto contained city points.",
            "wdi": (
                "Country observations are inherited by cities and are never relabeled as city data."
            ),
            "un_household": (
                "Country observations are inherited by cities and retain source survey years."
            ),
            "ideology": (
                "BLUE_DB party-family shares measure valid ballots in an LAU, not all city"
                " residents or self-reported ideology. City joins are spatially imputed and"
                " remain separate from the canonical ideology marginal."
            ),
        },
    }
    manifest["files"] = file_inventory(partial)
    (partial / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if output_directory.exists():
        shutil.rmtree(output_directory)
    partial.replace(output_directory)
    installed_marginals = 0
    installed_electoral = {"observations": 0, "city_matches": 0}
    if install_shared:
        store = AtlasStore(database_path)
        installed_marginals = install_shared_marginals(store, canonical)
        installed_electoral = install_shared_electoral(
            store,
            output_directory / "blue_electoral_results.parquet",
            output_directory / "blue_city_matches.parquet",
            digests["BLUE_DB.zip"],
            digests["LAU_RG_01M_2024_4326.gpkg"],
        )
    return manifest | {
        "installed_shared_observations": (
            installed_marginals + installed_electoral["observations"]
        ),
        "installed_shared_marginals": installed_marginals,
        "installed_electoral_observations": installed_electoral["observations"],
        "installed_electoral_city_matches": installed_electoral["city_matches"],
    }
