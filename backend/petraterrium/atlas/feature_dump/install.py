import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq

from ..database import AtlasStore
from ..validation import validate_value
from .electoral import (
    BLUE_DB_PUBLISHED_DATE,
    BLUE_DB_RELEASE,
    GISCO_LAU_URL,
    GISCO_LAU_YEAR,
)

TRANSFORM_VERSION = "city-feature-dump-v4"


def identity(source: str, version: str, year: int) -> str:
    value = json.dumps([source, version, year, TRANSFORM_VERSION], separators=(",", ":"))
    return "bulk-" + hashlib.sha256(value.encode()).hexdigest()[:28]


def electoral_identity(version: str, election_id: str) -> str:
    value = json.dumps(["BLUE_DB", version, election_id], separators=(",", ":"))
    return "bulk-" + hashlib.sha256(value.encode()).hexdigest()[:28]


def ballot_priority(row):
    vote_type = (row.get("vote_type") or "").casefold()
    preferred = int(
        any(label in vote_type for label in ("party", "list", "zweit", "proportional"))
    )
    unspecified = int(not vote_type)
    return row["election_date"], preferred * 2 + unspecified, row["election_id"]


def latest_electoral_rows(path: Path):
    columns = [
        "gisco_id",
        "election_id",
        "country_code",
        "parliament_name",
        "election_date",
        "round",
        "vote_type",
        "source_file",
        "valid_votes",
        "classified_vote_percent",
        "radical_left_percent",
        "left_or_center_left_percent",
        "center_or_center_right_percent",
        "radical_right_percent",
        "other_percent",
        "unknown_alignment_percent",
    ]
    latest = {}
    for batch in pq.ParquetFile(path).iter_batches(columns=columns, batch_size=50_000):
        for row in batch.to_pylist():
            if not row["election_date"] or row["valid_votes"] <= 0:
                continue
            existing = latest.get(row["gisco_id"])
            if existing is None or ballot_priority(row) > ballot_priority(existing):
                latest[row["gisco_id"]] = row
    return latest.values()


def electoral_value(row):
    value = {
        "radical_left": row["radical_left_percent"],
        "left_or_center_left": row["left_or_center_left_percent"],
        "center_or_center_right": row["center_or_center_right_percent"],
        "radical_right": row["radical_right_percent"],
        "other": row["other_percent"],
        "unknown": row["unknown_alignment_percent"],
    }
    validate_value("ideology", value, "percent_of_valid_votes")
    return value


def install_city_lau_matches(
    connection,
    matches_path: Path,
    version: str,
    boundary_sha256: str,
):
    city_ids = {row[0] for row in connection.execute("SELECT geonameid FROM cities")}
    source_rows = pq.read_table(matches_path).to_pylist()
    if source_rows and not city_ids:
        raise ValueError("Load the GeoNames city backbone before installing electoral data")
    rows = [
        (
            row["geonameid"],
            row["gisco_id"],
            row["status"],
            row["match_method"],
            "Eurostat GISCO Local Administrative Units",
            GISCO_LAU_URL,
            version,
            GISCO_LAU_YEAR,
            boundary_sha256,
        )
        for row in source_rows
        if row["geonameid"] in city_ids
    ]
    cursor = connection.executemany(
        """INSERT INTO city_lau_matches(
        geonameid,gisco_id,status,match_method,source,source_url,version,boundary_year,
        boundary_sha256) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(geonameid) DO UPDATE SET
        gisco_id=excluded.gisco_id,status=excluded.status,match_method=excluded.match_method,
        source=excluded.source,source_url=excluded.source_url,version=excluded.version,
        boundary_year=excluded.boundary_year,boundary_sha256=excluded.boundary_sha256
        WHERE gisco_id!=excluded.gisco_id OR status!=excluded.status
        OR match_method!=excluded.match_method OR source!=excluded.source
        OR source_url!=excluded.source_url OR version!=excluded.version
        OR boundary_year!=excluded.boundary_year OR boundary_sha256!=excluded.boundary_sha256""",
        rows,
    )
    return cursor.rowcount


def install_shared_electoral(
    store: AtlasStore,
    results_path: Path,
    matches_path: Path,
    source_sha256: str,
    boundary_sha256: str,
):
    version = (
        f"sha256:{source_sha256};release:{BLUE_DB_RELEASE};transform:{TRANSFORM_VERSION}"
    )
    grouped = defaultdict(list)
    for row in latest_electoral_rows(results_path):
        grouped[row["election_id"]].append(row)
    installed_observations = 0
    installed_matches = 0
    with store.connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        installed_matches = install_city_lau_matches(
            connection, matches_path, version, boundary_sha256
        )
        for election_id, rows in sorted(grouped.items()):
            import_id = electoral_identity(version, election_id)
            if connection.execute(
                "SELECT 1 FROM imports WHERE import_id=?", (import_id,)
            ).fetchone():
                continue
            example = rows[0]
            prepared = [
                {
                    "geo_level": "lau",
                    "geo_key": row["gisco_id"],
                    "field": "ideology",
                    "value": electoral_value(row),
                    "unit": "percent_of_valid_votes",
                }
                for row in rows
            ]
            metadata = {
                "run_id": "shared",
                "kind": "marginals",
                "source": "BLUE_DB Electoral Bulletins of the European Union",
                "source_date": example["election_date"],
                "published_date": BLUE_DB_PUBLISHED_DATE,
                "version": version,
                "uploader": "bulk-source-loader",
                "unit": "percent_of_valid_votes",
                "measurement": "electoral_alignment_among_valid_ballots",
                "geography": "local_administrative_unit",
                "redistribution_allowed": True,
                "processing_notes": [
                    "Party-family classifications are supplied by BLUE_DB.",
                    "City values are spatially imputed from the containing 2024 LAU.",
                    "The denominator is valid ballots, not residents or all registered voters.",
                ],
            }
            connection.execute(
                """INSERT INTO imports(import_id,source,source_date,published_date,version,scope,
                uploader,kind,filename,row_count,status,metadata_json,rows_json,mapping_json,
                audit_json,validation_json,validated_json,promoted_from,redistribution_allowed,
                created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    import_id,
                    metadata["source"],
                    example["election_date"],
                    BLUE_DB_PUBLISHED_DATE,
                    version,
                    "shared",
                    "bulk-source-loader",
                    "marginals",
                    "BLUE_DB.zip:" + example["source_file"],
                    len(prepared),
                    "committed",
                    json.dumps(metadata),
                    "[]",
                    "[]",
                    json.dumps(
                        {
                            "provider": "deterministic-loader",
                            "model": "none",
                            "prompt_version": TRANSFORM_VERSION,
                            "message": "No LLM mapping was used",
                        }
                    ),
                    json.dumps({"valid": True, "observations": len(prepared)}),
                    "[]",
                    None,
                    1,
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.executemany(
                """INSERT INTO observations(import_id,geo_level,geo_key,field,value_json,unit)
                VALUES(?,?,?,?,?,?)""",
                [
                    (
                        import_id,
                        row["geo_level"],
                        row["geo_key"],
                        row["field"],
                        json.dumps(row["value"], allow_nan=False),
                        row["unit"],
                    )
                    for row in prepared
                ],
            )
            installed_observations += len(prepared)
        if installed_observations or installed_matches:
            store.bump(connection)
    return {
        "observations": installed_observations,
        "city_matches": installed_matches,
    }


def install_shared_marginals(store: AtlasStore, rows: list[dict]):
    grouped = defaultdict(list)
    for row in rows:
        validate_value(row["field"], row["value"], row["unit"])
        grouped[(row["source"], row["version"], row["year"])].append(row)
    installed = 0
    with store.connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        for (source, version, year), observations in sorted(grouped.items()):
            import_id = identity(source, version, year)
            if connection.execute(
                "SELECT 1 FROM imports WHERE import_id=?", (import_id,)
            ).fetchone():
                continue
            example = observations[0]
            prepared = [
                {
                    "geo_level": "country",
                    "geo_key": row["country_code"],
                    "field": row["field"],
                    "value": row["value"],
                    "unit": row["unit"],
                }
                for row in observations
            ]
            metadata = {
                "run_id": "shared",
                "kind": "marginals",
                "source": source,
                "source_date": f"{year}-12-31",
                "published_date": example["published_date"],
                "version": version,
                "uploader": "bulk-source-loader",
                "unit": "mixed",
                "redistribution_allowed": True,
                "processing_notes": [
                    (
                        "Explicit shared-atlas bulk installation from a redistributable public"
                        " release."
                    ),
                    "Country observations resolve as inherited city archetypes.",
                ],
            }
            connection.execute(
                """INSERT INTO imports(import_id,source,source_date,published_date,version,scope,
                uploader,kind,filename,row_count,status,metadata_json,rows_json,mapping_json,
                audit_json,validation_json,validated_json,promoted_from,redistribution_allowed,
                created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    import_id,
                    source,
                    f"{year}-12-31",
                    example["published_date"],
                    version,
                    "shared",
                    "bulk-source-loader",
                    "marginals",
                    example["filename"],
                    len(observations),
                    "committed",
                    json.dumps(metadata),
                    "[]",
                    "[]",
                    json.dumps(
                        {
                            "provider": "deterministic-loader",
                            "model": "none",
                            "prompt_version": TRANSFORM_VERSION,
                            "message": "No LLM mapping was used",
                        }
                    ),
                    json.dumps({"valid": True, "observations": len(observations)}),
                    json.dumps(prepared),
                    None,
                    1,
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.executemany(
                """INSERT INTO observations(import_id,geo_level,geo_key,field,value_json,unit)
                VALUES(?,?,?,?,?,?)""",
                [
                    (
                        import_id,
                        row["geo_level"],
                        row["geo_key"],
                        row["field"],
                        json.dumps(row["value"], allow_nan=False),
                        row["unit"],
                    )
                    for row in prepared
                ],
            )
            installed += len(observations)
        if installed:
            store.bump(connection)
    return installed
