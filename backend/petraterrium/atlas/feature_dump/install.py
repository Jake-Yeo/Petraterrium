import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime

from ..database import AtlasStore
from ..validation import validate_value

TRANSFORM_VERSION = "city-feature-dump-v3"


def identity(source: str, version: str, year: int) -> str:
    value = json.dumps([source, version, year, TRANSFORM_VERSION], separators=(",", ":"))
    return "bulk-" + hashlib.sha256(value.encode()).hexdigest()[:28]


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
