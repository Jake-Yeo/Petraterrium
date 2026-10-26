import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

import pyarrow as pa

from ..database import AtlasStore
from .downloads import acquire_sources, sha256_file
from .geonames import export_geonames
from .households import HOUSEHOLD_URL, export_households
from .install import TRANSFORM_VERSION, install_shared_marginals
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


def write_availability(output, cities, wdi, households, ucdb):
    schema = pa.schema(
        [
            ("geonameid", pa.int64()),
            ("country_code", pa.string()),
            ("ucdb_id", pa.int64()),
            ("spatially_imputed_feature_count", pa.int32()),
            ("country_inherited_feature_count", pa.int32()),
            ("total_available_feature_count", pa.int32()),
        ]
    )
    writer = RowWriter(output / "city_feature_availability.parquet", schema, 20_000)
    matched = ucdb["city_matches"]
    ucdb_counts = ucdb["feature_counts"]
    for row in cities.select(["geonameid", "country_code"]).to_pylist():
        urban_id = matched.get(row["geonameid"])
        spatial = int(ucdb_counts.get(urban_id, 0))
        inherited = int(wdi["latest_counts"].get(row["country_code"], 0)) + int(
            households["latest_counts"].get(row["country_code"], 0)
        )
        writer.add(
            {
                "geonameid": row["geonameid"],
                "country_code": row["country_code"],
                "ucdb_id": urban_id,
                "spatially_imputed_feature_count": spatial,
                "country_inherited_feature_count": inherited,
                "total_available_feature_count": spatial + inherited,
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
    canonical = canonical_rows(wdi, households, digests)
    write_canonical(partial, canonical)
    availability_rows = write_availability(partial, cities, wdi, households, ucdb)
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
                "No redistributable globally comparable city ideology distribution was found."
            ),
        },
    }
    manifest["files"] = file_inventory(partial)
    (partial / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if output_directory.exists():
        shutil.rmtree(output_directory)
    partial.replace(output_directory)
    installed = 0
    if install_shared:
        installed = install_shared_marginals(AtlasStore(database_path), canonical)
    return manifest | {"installed_shared_observations": installed}
