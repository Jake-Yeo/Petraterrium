import json
from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import Connection, Row
from uuid import NAMESPACE_URL, uuid5

from .auto_import_service import PromotionPayload
from .database import AtlasStore


class AtlasAutoImportPromotionWriter:
    def __init__(self, store: AtlasStore, missing_path: str | Path | None = None):
        self.store = store
        self.missing_path = Path(missing_path) if missing_path else _default_missing_path()

    def promote(self, payload: PromotionPayload) -> str:
        identity = _promotion_identity(payload.attempt_id)
        source_dates = [source.observation_date for source in payload.sources]
        source_date = max(value for value in source_dates if value is not None)
        published_dates = [source.published_date for source in payload.sources]
        published_date = max(value for value in published_dates if value is not None)
        versions = sorted({source.source_version for source in payload.sources})
        source_titles = [source.title for source in payload.sources]
        licenses = sorted({source.license for source in payload.sources})
        target = payload.target
        geo_level = {
            "region": "canonical_region",
            "country": "country",
            "city": "city",
        }[target.level]
        metadata = {
            "attempt_id": payload.attempt_id,
            "evidence_status": payload.evidence_status,
            "sources": [source.model_dump(mode="json") for source in payload.sources],
            "mapping": payload.mapping.model_dump(mode="json"),
            "verifications": [item.model_dump(mode="json") for item in payload.verifications],
            "estimate_trace": payload.estimate_trace.model_dump(mode="json")
            if payload.estimate_trace
            else None,
            "search_log": [entry.model_dump(mode="json") for entry in payload.search_log],
            "languages_searched": list(payload.languages_searched),
            "predictive_evidence_eligible": payload.predictive_evidence_eligible,
            "coverage_percent": payload.coverage_percent,
            "licenses": licenses,
        }
        prepared = [
            {
                "geo_level": geo_level,
                "geo_key": target.place_id,
                "field": target.feature_id,
                "value": payload.distribution,
                "unit": payload.unit,
                "evidence_status": payload.evidence_status,
            }
        ]
        now = datetime.now(UTC).isoformat()
        with self.store.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = _existing_promotion(connection, identity, payload.attempt_id)
            if existing is None:
                connection.execute(
                    """INSERT INTO imports(
                    import_id,source,source_date,published_date,version,scope,
                    uploader,kind,filename,row_count,status,metadata_json,rows_json,mapping_json,
                    audit_json,validation_json,validated_json,promoted_from,redistribution_allowed,
                    created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        identity,
                        "Auto-import · " + " · ".join(source_titles),
                        source_date.isoformat(),
                        published_date.isoformat(),
                        "+".join(versions) + "+" + payload.mapping.version,
                        target.scope,
                        "auto-import",
                        "marginals",
                        f"auto-import-{payload.attempt_id}.json",
                        1,
                        "committed",
                        json.dumps(metadata),
                        json.dumps([payload.distribution]),
                        payload.mapping.model_dump_json(),
                        json.dumps(
                            {
                                "search_log": metadata["search_log"],
                                "languages": payload.languages_searched,
                            }
                        ),
                        json.dumps(
                            {
                                "valid": True,
                                "evidence_status": payload.evidence_status,
                                "coverage_percent": payload.coverage_percent,
                            }
                        ),
                        json.dumps(prepared),
                        None,
                        1,
                        now,
                    ),
                )
                connection.execute(
                    """INSERT INTO observations(
                    import_id,geo_level,geo_key,field,value_json,unit,evidence_status
                    ) VALUES(?,?,?,?,?,?,?)""",
                    (
                        identity,
                        geo_level,
                        target.place_id,
                        target.feature_id,
                        json.dumps(payload.distribution),
                        payload.unit,
                        payload.evidence_status,
                    ),
                )
                self.store.bump(connection)
            else:
                identity = existing["import_id"]
                _require_matching_promotion(
                    connection,
                    existing,
                    payload,
                    metadata,
                    geo_level,
                )
        sync_missing_document(self.store, self.missing_path)
        return identity


def _promotion_identity(attempt_id: str) -> str:
    return uuid5(NAMESPACE_URL, f"petraterrium:auto-import:{attempt_id}").hex


def _existing_promotion(
    connection: Connection,
    identity: str,
    attempt_id: str,
) -> Row | None:
    candidates = connection.execute(
        """SELECT * FROM imports
        WHERE import_id=? OR (uploader='auto-import' AND filename=?)
        ORDER BY created_at""",
        (identity, f"auto-import-{attempt_id}.json"),
    ).fetchall()
    matches = []
    for candidate in candidates:
        metadata = json.loads(candidate["metadata_json"])
        if candidate["import_id"] == identity and metadata.get("attempt_id") != attempt_id:
            raise RuntimeError("Auto-import promotion identity is already in use")
        if metadata.get("attempt_id") == attempt_id:
            matches.append(candidate)
    if len(matches) > 1:
        raise RuntimeError("Auto-import attempt already has multiple promotion records")
    return matches[0] if matches else None


def _require_matching_promotion(
    connection: Connection,
    existing: Row,
    payload: PromotionPayload,
    metadata: dict,
    geo_level: str,
) -> None:
    target = payload.target
    expected_import = {
        "scope": target.scope,
        "status": "committed",
        "metadata_json": metadata,
        "rows_json": [payload.distribution],
        "mapping_json": payload.mapping.model_dump(mode="json"),
    }
    mismatches = [
        field
        for field, expected in expected_import.items()
        if (
            json.loads(existing[field])
            if field.endswith("_json")
            else existing[field]
        )
        != expected
    ]
    observations = connection.execute(
        """SELECT geo_level,geo_key,field,value_json,unit,evidence_status
        FROM observations WHERE import_id=?""",
        (existing["import_id"],),
    ).fetchall()
    if len(observations) != 1:
        mismatches.append("observations")
    else:
        observation = observations[0]
        expected_observation = {
            "geo_level": geo_level,
            "geo_key": target.place_id,
            "field": target.feature_id,
            "value_json": payload.distribution,
            "unit": payload.unit,
            "evidence_status": payload.evidence_status,
        }
        mismatches.extend(
            field
            for field, expected in expected_observation.items()
            if (
                json.loads(observation[field])
                if field == "value_json"
                else observation[field]
            )
            != expected
        )
    if mismatches:
        fields = ", ".join(sorted(set(mismatches)))
        raise RuntimeError(
            f"Auto-import attempt promotion conflicts with stored fields: {fields}"
        )


def _default_missing_path() -> Path:
    return Path(__file__).resolve().parents[3] / "MISSING.md"


def _latest_attempt_rows(store: AtlasStore):
    with store.connection() as connection:
        return connection.execute(
            """SELECT current.* FROM auto_import_attempts current
            WHERE current.updated_at=(
                SELECT MAX(candidate.updated_at) FROM auto_import_attempts candidate
                WHERE candidate.scope=current.scope AND candidate.level=current.level
                AND candidate.place_key=current.place_key AND candidate.feature=current.feature
            ) ORDER BY current.level,current.place_label,current.feature"""
        ).fetchall()


def sync_missing_document(
    store: AtlasStore,
    path: str | Path | None = None,
) -> None:
    destination = Path(path) if path else _default_missing_path()
    heading = "## Auto-import field evidence"
    existing = destination.read_text(encoding="utf-8") if destination.exists() else ""
    base = existing.split(heading, 1)[0].rstrip()
    rows = []
    for row in _latest_attempt_rows(store):
        if row["status"] == "promoted" and row["result_kind"] == "measured":
            state = "Resolved with measured evidence"
            next_evidence = "No missing evidence at this level"
        elif row["status"] == "promoted" and row["result_kind"] == "estimated":
            state = "Estimated with a stored uncertainty and reasoning trace"
            next_evidence = row["better_data"]
        elif row["status"] in {"not_found", "rejected"}:
            state = "Earlier research attempt is ready to retry"
            next_evidence = (
                "Retry with another source or engine to create an estimated draft"
            )
        else:
            state = "Research or review in progress"
            next_evidence = row["better_data"]
        target = f"{row['level']} · {row['place_label']} · {row['feature']}"
        rows.append(
            "| "
            + " | ".join(
                value.replace("|", "\\|").replace("\n", " ")
                for value in (
                    target,
                    state,
                    next_evidence or "A qualifying measured distribution",
                    row["updated_at"],
                )
            )
            + " |"
        )
    section = [
        heading,
        "",
        "This table is generated from durable auto-import attempts and promotion records.",
        "",
        "| Target | Evidence state | What closes the gap | Last attempt |",
        "| --- | --- | --- | --- |",
        *rows,
    ]
    text = base + "\n\n" + "\n".join(section).rstrip() + "\n"
    destination.write_text(text, encoding="utf-8")
