import json

from .auto_import_research import AutoImportAttempt
from .bulk_auto_import import (
    BulkImportBatchRecord,
    BulkImportItemRecord,
    BulkImportRepository,
)
from .database import AtlasStore


class SQLiteAttemptRepository:
    def __init__(self, store: AtlasStore):
        self.store = store

    def save(self, attempt: AutoImportAttempt) -> None:
        estimate = attempt.estimate_trace
        values = {
            "attempt_id": attempt.attempt_id,
            "scope": attempt.target.scope,
            "level": attempt.target.level,
            "place_key": attempt.target.place_id,
            "place_label": attempt.target.place_label,
            "country_code": attempt.target.country_code,
            "geonameid": int(attempt.target.place_id)
            if attempt.target.level == "city" and attempt.target.place_id.isdigit()
            else None,
            "feature": attempt.target.feature_id,
            "current_status": attempt.target.current_status,
            "status": attempt.status,
            "result_kind": attempt.result_kind,
            "requirement_json": attempt.requirement.model_dump_json(),
            "source_inputs_json": json.dumps(
                [source.model_dump(mode="json") for source in attempt.user_sources]
            ),
            "mapping_json": attempt.mapping_preview.model_dump_json()
            if attempt.mapping_preview
            else "null",
            "mapping_confirmed": int(attempt.mapping_confirmed),
            "verification_json": json.dumps(
                [verification.model_dump(mode="json") for verification in attempt.verifications]
            ),
            "candidate_json": json.dumps(
                {
                    "proposed": attempt.proposed_distribution,
                    "mapped": attempt.mapped_distribution,
                    "selected_source_ids": attempt.selected_source_ids,
                }
            ),
            "sources_json": json.dumps(
                {
                    "accepted": [source.model_dump(mode="json") for source in attempt.sources],
                    "rejected": [
                        source.model_dump(mode="json") for source in attempt.rejected_sources
                    ],
                }
            ),
            "search_log_json": json.dumps(
                [entry.model_dump(mode="json") for entry in attempt.search_log]
            ),
            "estimate_trace_json": estimate.model_dump_json() if estimate else None,
            "languages_json": json.dumps(attempt.languages_searched),
            "failure_reason": attempt.failure_reason,
            "better_data": estimate.better_data_needed
            if estimate
            else attempt.requirement.better_data_needed,
            "promoted_import_id": attempt.promotion_id,
            "created_at": attempt.created_at.isoformat(),
            "updated_at": attempt.updated_at.isoformat(),
            "attempt_json": attempt.model_dump_json(),
        }
        columns = tuple(values)
        assignments = ",".join(
            f"{column}=excluded.{column}" for column in columns if column != "attempt_id"
        )
        with self.store.connection() as connection:
            connection.execute(
                f"INSERT INTO auto_import_attempts({','.join(columns)}) "
                f"VALUES({','.join('?' for _ in columns)}) "
                f"ON CONFLICT(attempt_id) DO UPDATE SET {assignments}",
                [values[column] for column in columns],
            )

    def get(self, attempt_id: str) -> AutoImportAttempt:
        with self.store.connection() as connection:
            row = connection.execute(
                "SELECT attempt_json FROM auto_import_attempts WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Auto-import attempt {attempt_id} does not exist")
        return AutoImportAttempt.model_validate_json(row["attempt_json"])

    def list(self) -> list[AutoImportAttempt]:
        with self.store.connection() as connection:
            rows = connection.execute(
                "SELECT attempt_json FROM auto_import_attempts ORDER BY created_at,attempt_id"
            ).fetchall()
        return [AutoImportAttempt.model_validate_json(row["attempt_json"]) for row in rows]


class SQLiteBulkImportRepository(BulkImportRepository):
    def __init__(self, store: AtlasStore):
        self.store = store

    async def create_batch(
        self,
        batch: BulkImportBatchRecord,
        items: tuple[BulkImportItemRecord, ...] | list[BulkImportItemRecord],
    ) -> None:
        scope = items[0].target.attributes.get("scope", "shared") if items else "shared"
        with self.store.connection() as connection:
            connection.execute(
                "INSERT INTO auto_import_batches VALUES(?,?,?,?,?,?,?)",
                (
                    batch.batch_id,
                    scope,
                    batch.state,
                    batch.selection.model_dump_json(),
                    batch.model_dump_json(),
                    batch.created_at.isoformat(),
                    batch.updated_at.isoformat(),
                ),
            )
            connection.executemany(
                "INSERT INTO auto_import_batch_items VALUES(?,?,?,?)",
                [
                    (
                        item.batch_id,
                        item.target.item_id,
                        item.ordinal,
                        item.model_dump_json(),
                    )
                    for item in items
                ],
            )

    async def get_batch(self, batch_id: str) -> BulkImportBatchRecord | None:
        with self.store.connection() as connection:
            row = connection.execute(
                "SELECT result_json FROM auto_import_batches WHERE batch_id=?",
                (batch_id,),
            ).fetchone()
        return BulkImportBatchRecord.model_validate_json(row["result_json"]) if row else None

    async def list_batches(self, scope: str | None = None) -> tuple[BulkImportBatchRecord, ...]:
        statement = "SELECT result_json FROM auto_import_batches"
        parameters: tuple[str, ...] = ()
        if scope is not None:
            statement += " WHERE scope=?"
            parameters = (scope,)
        statement += " ORDER BY updated_at DESC,batch_id DESC"
        with self.store.connection() as connection:
            rows = connection.execute(statement, parameters).fetchall()
        return tuple(
            BulkImportBatchRecord.model_validate_json(row["result_json"]) for row in rows
        )

    async def save_batch(self, batch: BulkImportBatchRecord) -> None:
        with self.store.connection() as connection:
            changed = connection.execute(
                "UPDATE auto_import_batches SET status=?,result_json=?,updated_at=? "
                "WHERE batch_id=?",
                (
                    batch.state,
                    batch.model_dump_json(),
                    batch.updated_at.isoformat(),
                    batch.batch_id,
                ),
            ).rowcount
        if not changed:
            raise KeyError(batch.batch_id)

    async def list_items(self, batch_id: str) -> tuple[BulkImportItemRecord, ...]:
        with self.store.connection() as connection:
            rows = connection.execute(
                "SELECT record_json FROM auto_import_batch_items WHERE batch_id=? "
                "ORDER BY ordinal",
                (batch_id,),
            ).fetchall()
        if not rows and await self.get_batch(batch_id) is None:
            raise KeyError(batch_id)
        return tuple(BulkImportItemRecord.model_validate_json(row["record_json"]) for row in rows)

    async def save_item(self, item: BulkImportItemRecord) -> None:
        with self.store.connection() as connection:
            changed = connection.execute(
                "UPDATE auto_import_batch_items SET record_json=? "
                "WHERE batch_id=? AND item_id=?",
                (
                    item.model_dump_json(),
                    item.batch_id,
                    item.target.item_id,
                ),
            ).rowcount
        if not changed:
            raise KeyError(item.target.item_id)
