from __future__ import annotations

import json
import os
import sqlite3
import threading
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RUN_ARTIFACT_FIELDS = ("prepared", "result", "final_output", "location_history")
FINAL_OUTPUT_HISTORY_FIELDS = (
    "transition_counts",
    "transition_outcomes",
    "events",
    "routine_actions",
    "routine_unavailable",
    "location_transitions",
    "interactions",
    "blocked_interactions",
    "state_ticks",
    "synchronization",
)
AGENT_FRAME_FIELDS = (
    "modules",
    "states",
    "locations",
    "memory",
    "state_receipts",
    "action_receipts",
    "actions",
    "routines",
    "interactions",
    "interaction_details",
    "decisions",
    "location_transitions",
)


@dataclass(frozen=True)
class StoredSimulationRun:
    metadata: dict[str, Any]
    frames: list[dict[str, Any]]
    events: list[dict[str, Any]]


def default_simulation_run_path() -> Path:
    configured = os.getenv("PETRATERRIUM_SIMULATION_RUNS_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[2] / "data" / "simulation_runs.sqlite3"


class SimulationRunRecorder:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or default_simulation_run_path())
        self._lock = threading.RLock()
        self._initialize()

    def load(self) -> list[StoredSimulationRun]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT run_id, metadata FROM simulation_runs ORDER BY created_sequence"
            ).fetchall()
            return [
                StoredSimulationRun(
                    metadata=self._metadata_with_artifacts(
                        connection, run_id, self._decode(metadata)
                    ),
                    frames=self._load_frames(connection, run_id),
                    events=self._load_events(connection, run_id),
                )
                for run_id, metadata in rows
            ]

    def load_metadata(self) -> list[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT simulation_runs.metadata, simulation_run_checkpoints.payload "
                "FROM simulation_runs LEFT JOIN simulation_run_checkpoints "
                "USING (run_id) ORDER BY simulation_runs.created_sequence"
            ).fetchall()
            metadata = []
            for stored_metadata, checkpoint in rows:
                restored = self._decode(stored_metadata)
                if checkpoint is not None:
                    restored.update(self._decode(checkpoint))
                metadata.append(restored)
            return metadata

    def load_prepared(self, run_id: str) -> dict[str, Any] | None:
        return self._load_dict_artifact(run_id, "prepared")

    def load_result(self, run_id: str) -> dict[str, Any] | None:
        return self._load_dict_artifact(run_id, "result")

    def load_location_history(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            value = self._load_artifact(connection, run_id, "location_history")
        if value is None:
            return []
        if not isinstance(value, list) or not all(
            isinstance(item, dict) for item in value
        ):
            raise ValueError("Persisted location history must be a list of objects")
        return value

    def load_frames(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            return self._load_frames(connection, run_id)

    def load_agent_frames(
        self, run_id: str, agent_index: int
    ) -> list[dict[str, Any]]:
        projected = []
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM simulation_run_frames "
                "WHERE run_id = ? ORDER BY frame_index",
                (run_id,),
            )
            for row in rows:
                frame = self._decode(row[0])
                selected = {
                    "day": frame["day"],
                    "date": frame["date"],
                    "tick": frame["tick"],
                    "live_places": [],
                }
                for field_name in AGENT_FRAME_FIELDS:
                    values = frame.get(field_name, [])
                    if not isinstance(values, list) or agent_index >= len(values):
                        raise ValueError(
                            f"Persisted frame {field_name} does not contain agent {agent_index}"
                        )
                    selected[field_name] = [values[agent_index]]
                projected.append(selected)
        return projected

    def load_latest_frame(self, run_id: str) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT payload FROM simulation_run_frames "
                "WHERE run_id = ? ORDER BY frame_index DESC LIMIT 1",
                (run_id,),
            ).fetchone()
            return self._decode(row[0]) if row is not None else None

    def load_events(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            return self._load_events(connection, run_id)

    def load_event_page(
        self,
        run_id: str,
        *,
        kind: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        start = (page - 1) * page_size
        end = start + page_size
        selected = []
        total = 0
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM simulation_run_events "
                "WHERE run_id = ? ORDER BY event_index",
                (run_id,),
            )
            for row in rows:
                event = self._decode(row[0])
                if kind is not None and event.get("kind") != kind:
                    continue
                if start <= total < end:
                    selected.append(event)
                total += 1
        return selected, total

    def iter_interactions(self, run_id: str) -> Iterator[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM simulation_run_events "
                "WHERE run_id = ? ORDER BY event_index",
                (run_id,),
            )
            for row in rows:
                event = self._decode(row[0])
                details = event.get("details")
                if event.get("kind") == "interaction" and isinstance(details, dict):
                    yield details

    def load_interactions(self, run_id: str) -> list[dict[str, Any]]:
        return list(self.iter_interactions(run_id))

    def load_final_output(self, run_id: str) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            final_output = self._load_artifact(connection, run_id, "final_output")
            if final_output is None:
                return None
            if not isinstance(final_output, dict):
                raise ValueError("Persisted Rust output must be an object")
            return self._compact_final_output(final_output)

    def save_metadata(self, run_id: str, metadata: dict[str, Any]) -> None:
        with self._lock, self._connection() as connection:
            stored_metadata = dict(metadata)
            artifacts = {}
            for field_name in RUN_ARTIFACT_FIELDS:
                if field_name not in stored_metadata:
                    continue
                value = stored_metadata.get(field_name)
                if value is not None:
                    artifacts[field_name] = value
                stored_metadata[field_name] = None
            connection.execute(
                "INSERT INTO simulation_runs (run_id, metadata) VALUES (?, ?) "
                "ON CONFLICT(run_id) DO UPDATE SET metadata = excluded.metadata",
                (run_id, self._encode(stored_metadata)),
            )
            for field_name, value in artifacts.items():
                if field_name == "final_output":
                    self._store_final_output(connection, run_id, value)
                else:
                    self._store_artifact(connection, run_id, field_name, value)
            if metadata.get("status") in {"completed", "failed", "cancelled"}:
                connection.execute(
                    "DELETE FROM simulation_run_checkpoints WHERE run_id = ?",
                    (run_id,),
                )

    def append_checkpoint(
        self,
        run_id: str,
        metadata: dict[str, Any],
        frame_index: int,
        frame: dict[str, Any],
        first_event_index: int,
        events: list[dict[str, Any]],
    ) -> None:
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT INTO simulation_run_checkpoints (run_id, payload) VALUES (?, ?) "
                "ON CONFLICT(run_id) DO UPDATE SET payload = excluded.payload",
                (run_id, self._encode(metadata)),
            )
            connection.execute(
                "INSERT INTO simulation_run_frames (run_id, frame_index, payload) "
                "VALUES (?, ?, ?) ON CONFLICT(run_id, frame_index) "
                "DO UPDATE SET payload = excluded.payload",
                (run_id, frame_index, self._encode(frame)),
            )
            connection.executemany(
                "INSERT INTO simulation_run_events (run_id, event_index, payload) "
                "VALUES (?, ?, ?) ON CONFLICT(run_id, event_index) "
                "DO UPDATE SET payload = excluded.payload",
                [
                    (run_id, first_event_index + offset, self._encode(event))
                    for offset, event in enumerate(events)
                ],
            )

    def delete(self, run_id: str) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                "DELETE FROM simulation_runs WHERE run_id = ?",
                (run_id,),
            )
            return cursor.rowcount > 0

    def _load_frames(
        self,
        connection: sqlite3.Connection,
        run_id: str,
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            "SELECT payload FROM simulation_run_frames "
            "WHERE run_id = ? ORDER BY frame_index",
            (run_id,),
        ).fetchall()
        return [self._decode(row[0]) for row in rows]

    def _load_events(
        self,
        connection: sqlite3.Connection,
        run_id: str,
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            "SELECT payload FROM simulation_run_events "
            "WHERE run_id = ? ORDER BY event_index",
            (run_id,),
        ).fetchall()
        return [self._decode(row[0]) for row in rows]

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS simulation_runs ("
                "created_sequence INTEGER PRIMARY KEY AUTOINCREMENT, "
                "run_id TEXT NOT NULL UNIQUE, "
                "metadata TEXT NOT NULL"
                ")"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS simulation_run_frames ("
                "run_id TEXT NOT NULL REFERENCES simulation_runs(run_id) ON DELETE CASCADE, "
                "frame_index INTEGER NOT NULL, "
                "payload TEXT NOT NULL, "
                "PRIMARY KEY (run_id, frame_index)"
                ")"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS simulation_run_events ("
                "run_id TEXT NOT NULL REFERENCES simulation_runs(run_id) ON DELETE CASCADE, "
                "event_index INTEGER NOT NULL, "
                "payload TEXT NOT NULL, "
                "PRIMARY KEY (run_id, event_index)"
                ")"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS simulation_run_checkpoints ("
                "run_id TEXT PRIMARY KEY REFERENCES simulation_runs(run_id) ON DELETE CASCADE, "
                "payload TEXT NOT NULL"
                ")"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS simulation_run_artifacts ("
                "run_id TEXT NOT NULL REFERENCES simulation_runs(run_id) ON DELETE CASCADE, "
                "artifact_kind TEXT NOT NULL, "
                "payload TEXT NOT NULL, "
                "PRIMARY KEY (run_id, artifact_kind)"
                ")"
            )
            self._migrate_embedded_artifacts(connection)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _encode(value: dict[str, Any]) -> bytes:
        return SimulationRunRecorder._encode_value(value)

    @staticmethod
    def _encode_value(value: Any) -> bytes:
        payload = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        return sqlite3.Binary(zlib.compress(payload, level=1))

    @staticmethod
    def _decode(value: str | bytes) -> dict[str, Any]:
        decoded = SimulationRunRecorder._decode_value(value)
        if not isinstance(decoded, dict):
            raise ValueError("Persisted simulation run payload must be an object")
        return decoded

    @staticmethod
    def _decode_value(value: str | bytes) -> Any:
        payload = (
            zlib.decompress(value).decode("utf-8")
            if isinstance(value, bytes)
            else value
        )
        return json.loads(payload)

    @staticmethod
    def _compact_final_output(final_output: dict[str, Any]) -> dict[str, Any]:
        compact_output = dict(final_output)
        for field_name in FINAL_OUTPUT_HISTORY_FIELDS:
            compact_output[field_name] = []
        return compact_output

    def _load_dict_artifact(
        self, run_id: str, artifact_kind: str
    ) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            value = self._load_artifact(connection, run_id, artifact_kind)
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError(f"Persisted {artifact_kind} artifact must be an object")
        return value

    def _metadata_with_artifacts(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        restored = dict(metadata)
        for field_name in RUN_ARTIFACT_FIELDS:
            artifact = self._load_artifact(
                connection, run_id, field_name
            )
            if artifact is not None:
                restored[field_name] = artifact
        final_output = restored.get("final_output")
        if isinstance(final_output, dict):
            final_output = dict(final_output)
            for field_name in FINAL_OUTPUT_HISTORY_FIELDS:
                history = self._load_artifact(
                    connection, run_id, f"final_output.{field_name}"
                )
                if history is not None:
                    final_output[field_name] = history
            restored["final_output"] = final_output
        return restored

    def _load_artifact(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        artifact_kind: str,
    ) -> Any:
        row = connection.execute(
            "SELECT payload FROM simulation_run_artifacts "
            "WHERE run_id = ? AND artifact_kind = ?",
            (run_id, artifact_kind),
        ).fetchone()
        return self._decode_value(row[0]) if row is not None else None

    def _store_artifact(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        artifact_kind: str,
        value: Any,
    ) -> None:
        connection.execute(
            "INSERT INTO simulation_run_artifacts (run_id, artifact_kind, payload) "
            "VALUES (?, ?, ?) ON CONFLICT(run_id, artifact_kind) "
            "DO UPDATE SET payload = excluded.payload",
            (run_id, artifact_kind, self._encode_value(value)),
        )

    def _store_final_output(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        value: Any,
    ) -> None:
        if not isinstance(value, dict):
            raise ValueError("Persisted Rust output must be an object")
        compact = dict(value)
        for field_name in FINAL_OUTPUT_HISTORY_FIELDS:
            connection.execute(
                "DELETE FROM simulation_run_artifacts "
                "WHERE run_id = ? AND artifact_kind = ?",
                (run_id, f"final_output.{field_name}"),
            )
            if field_name not in compact:
                continue
            history = compact.get(field_name)
            if isinstance(history, list) and history:
                self._store_artifact(
                    connection,
                    run_id,
                    f"final_output.{field_name}",
                    history,
                )
            compact[field_name] = []
        self._store_artifact(connection, run_id, "final_output", compact)

    def _migrate_embedded_artifacts(
        self, connection: sqlite3.Connection
    ) -> None:
        rows = connection.execute(
            "SELECT run_id, metadata FROM simulation_runs ORDER BY created_sequence"
        ).fetchall()
        for run_id, encoded in rows:
            metadata = self._decode(encoded)
            changed = False
            for field_name in RUN_ARTIFACT_FIELDS:
                value = metadata.get(field_name)
                if value is None:
                    continue
                if field_name == "final_output":
                    self._store_final_output(connection, run_id, value)
                else:
                    self._store_artifact(connection, run_id, field_name, value)
                metadata[field_name] = None
                changed = True
            if changed:
                connection.execute(
                    "UPDATE simulation_runs SET metadata = ? WHERE run_id = ?",
                    (self._encode(metadata), run_id),
                )
