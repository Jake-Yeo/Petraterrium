import json
from datetime import UTC, datetime
from uuid import uuid4

from .behaviour import store_models
from .contracts import (
    BehaviourModel,
    ColumnMapping,
    ImportCommit,
    ImportHistory,
    ImportMetadata,
    ImportPreview,
    ImportVersion,
    MappingAudit,
    MappingConfirmation,
    Promotion,
)
from .database import AtlasStore
from .formats import preview_rows
from .llm import propose_mapping
from .organizer import provenance
from .validation import validate_rows


def stage_import(
    store: AtlasStore,
    filename: str,
    metadata: ImportMetadata,
    rows: list[dict],
    use_llm=True,
    ai_provider=None,
) -> ImportPreview:
    sample = preview_rows(rows)
    headers = list(dict.fromkeys(key for row in rows for key in row))
    mappings, audit = propose_mapping(
        store, metadata.run_id, headers, sample, use_llm, ai_provider
    )
    identity = uuid4().hex
    with store.connection() as conn:
        conn.execute(
            """INSERT INTO imports(import_id,source,source_date,published_date,version,scope,
            uploader,kind,filename,row_count,status,metadata_json,rows_json,mapping_json,audit_json,
            redistribution_allowed,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                identity,
                metadata.source,
                str(metadata.source_date),
                str(metadata.published_date),
                metadata.version,
                metadata.run_id,
                metadata.uploader,
                metadata.kind,
                filename,
                len(rows),
                "awaiting_confirmation",
                metadata.model_dump_json(),
                json.dumps(rows, allow_nan=False),
                json.dumps([m.model_dump() for m in mappings]),
                audit.model_dump_json(),
                metadata.redistribution_allowed,
                datetime.now(UTC).isoformat(),
            ),
        )
    return ImportPreview(
        import_id=identity,
        filename=filename,
        metadata=metadata,
        row_count=len(rows),
        sample_rows=sample,
        mappings=mappings,
        mapping_audit=audit,
    )


def require_import(conn, identity: str, scope: str):
    row = conn.execute(
        "SELECT * FROM imports WHERE import_id=? AND scope=?", (identity, scope)
    ).fetchone()
    if row is None:
        raise KeyError("Import does not exist in this scope")
    return row


def reopen_draft(store: AtlasStore, identity: str, scope: str) -> ImportPreview:
    with store.connection() as conn:
        row = require_import(conn, identity, scope)
        if row["status"] == "committed":
            raise ValueError("Committed imports are immutable; upload a new version")
        return ImportPreview(
            import_id=identity,
            filename=row["filename"],
            metadata=ImportMetadata.model_validate_json(row["metadata_json"]),
            row_count=row["row_count"],
            sample_rows=preview_rows(json.loads(row["rows_json"])),
            mappings=[ColumnMapping(**value) for value in json.loads(row["mapping_json"])],
            mapping_audit=MappingAudit.model_validate_json(row["audit_json"]),
        )


def validate_import(
    store: AtlasStore, identity: str, scope: str, confirmation: MappingConfirmation
):
    with store.connection() as conn:
        row = require_import(conn, identity, scope)
        if row["status"] == "committed":
            raise ValueError("A committed import is immutable; upload a new version")
        report, prepared = validate_rows(
            conn,
            identity,
            ImportMetadata.model_validate_json(row["metadata_json"]),
            json.loads(row["rows_json"]),
            confirmation,
        )
        conn.execute(
            (
                "UPDATE imports SET status=?,validation_json=?,validated_json=?,mapping_j"
                "son=? WHERE import_id=?"
            ),
            (
                "validated" if report.valid else "invalid",
                report.model_dump_json(),
                json.dumps(prepared),
                json.dumps([m.model_dump() for m in confirmation.mappings]),
                identity,
            ),
        )
        return report


def write_observations(conn, identity: str, kind: str, prepared: list[dict], scope: str):
    if kind == "marginals":
        conn.executemany(
            (
                "INSERT INTO observations(import_id,geo_level,geo_key,field,value_json,un"
                "it) VALUES(?,?,?,?,?,?)"
            ),
            [
                (
                    identity,
                    row["geo_level"],
                    row["geo_key"],
                    row["field"],
                    json.dumps(row["value"]),
                    row["unit"],
                )
                for row in prepared
            ],
        )
    elif kind == "behaviour":
        store_models(conn, identity, prepared, scope)
    else:
        conn.executemany(
            "INSERT INTO densities(import_id,geonameid,density) VALUES(?,?,?)",
            [(identity, row["geonameid"], row["density"]) for row in prepared],
        )


def commit_import(
    store: AtlasStore, identity: str, scope: str, commit: ImportCommit
) -> ImportVersion:
    with store.connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = require_import(conn, identity, scope)
        report = json.loads(row["validation_json"] or "{}")
        if (
            not commit.confirmed
            or row["status"] != "validated"
            or not report.get("valid")
            or report.get("mapping_hash") != commit.mapping_hash
        ):
            raise ValueError("Confirm a successfully validated mapping before committing")
        write_observations(conn, identity, row["kind"], json.loads(row["validated_json"]), scope)
        conn.execute("UPDATE imports SET status='committed' WHERE import_id=?", (identity,))
        store.bump(conn)
    return next(
        version
        for version in import_history(store, scope).versions
        if version.import_id == identity
    )


def promote_import(
    store: AtlasStore, identity: str, scope: str, promotion: Promotion
) -> ImportVersion:
    with store.connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = require_import(conn, identity, scope)
        if scope == "shared" or row["status"] != "committed":
            raise ValueError("Only a committed run-scoped import can be promoted")
        if (
            not promotion.confirmed
            or not promotion.redistribution_confirmed
            or not row["redistribution_allowed"]
        ):
            raise ValueError("Explicit promotion and confirmed redistribution rights are required")
        metadata = json.loads(row["metadata_json"])
        if metadata.get("source_id") in ("ipums", "dhs", "gallup", "pew"):
            raise ValueError(
                "This licensed source cannot be redistributed to the shared atlas; keep"
                " it in its licensed run"
            )
        values = dict(row)
        identity = uuid4().hex
        values.update(
            import_id=identity,
            scope="shared",
            promoted_from=row["import_id"],
            created_at=datetime.now(UTC).isoformat(),
        )
        columns = ",".join(values)
        placeholders = ",".join("?" for _ in values)
        conn.execute(
            f"INSERT INTO imports({columns}) VALUES({placeholders})", list(values.values())
        )
        write_observations(conn, identity, row["kind"], json.loads(row["validated_json"]), "shared")
        store.bump(conn)
    return next(
        version
        for version in import_history(store, "shared").versions
        if version.import_id == identity
    )


def import_history(store: AtlasStore, scope: str) -> ImportHistory:
    with store.connection() as conn:
        rows = conn.execute(
            "SELECT * FROM imports WHERE scope IN ('shared',?) ORDER BY created_at DESC", (scope,)
        ).fetchall()
        versions = []
        for row in rows:
            live = conn.execute(
                """SELECT COUNT(*) FROM observations o WHERE o.import_id=? AND NOT EXISTS(
                SELECT 1 FROM observations n JOIN imports v ON v.import_id=n.import_id
                WHERE v.status='committed' AND v.scope=? AND n.geo_level=o.geo_level
                AND n.geo_key=o.geo_key AND n.field=o.field AND n.id>o.id)""",
                (row["import_id"], row["scope"]),
            ).fetchone()[0]
            models = [
                BehaviourModel(
                    country_code=m["country_code"],
                    behaviour=m["behaviour"],
                    fitted=bool(m["fitted"]),
                    label_only=bool(m["label_only"]),
                    provenance=provenance(row),
                    heldout_loss=m["heldout_loss"],
                    baseline_loss=m["baseline_loss"],
                    training_rows=m["training_rows"],
                    heldout_rows=m["heldout_rows"],
                    traits=json.loads(m["traits_json"]),
                )
                for m in conn.execute("SELECT * FROM models WHERE import_id=?", (row["import_id"],))
            ]
            versions.append(
                ImportVersion(
                    **{
                        key: row[key]
                        for key in (
                            "import_id",
                            "source",
                            "source_date",
                            "published_date",
                            "version",
                            "scope",
                            "uploader",
                            "kind",
                            "filename",
                            "status",
                            "promoted_from",
                        )
                    },
                    rows=row["row_count"],
                    live_fields=live,
                    redistribution_allowed=bool(row["redistribution_allowed"]),
                    models=models,
                )
            )
        return ImportHistory(versions=versions)
