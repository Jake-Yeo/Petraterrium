from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
            result = []
            for run_id, metadata in rows:
                frame_rows = connection.execute(
                    "SELECT payload FROM simulation_run_frames "
                    "WHERE run_id = ? ORDER BY frame_index",
                    (run_id,),
                ).fetchall()
                event_rows = connection.execute(
                    "SELECT payload FROM simulation_run_events "
                    "WHERE run_id = ? ORDER BY event_index",
                    (run_id,),
                ).fetchall()
                result.append(
                    StoredSimulationRun(
                        metadata=self._decode(metadata),
                        frames=[self._decode(row[0]) for row in frame_rows],
                        events=[self._decode(row[0]) for row in event_rows],
                    )
                )
            return result

    def save_metadata(self, run_id: str, metadata: dict[str, Any]) -> None:
        encoded = self._encode(metadata)
        with self._lock, self._connection() as connection:
            connection.execute(
                "INSERT INTO simulation_runs (run_id, metadata) VALUES (?, ?) "
                "ON CONFLICT(run_id) DO UPDATE SET metadata = excluded.metadata",
                (run_id, encoded),
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
                "INSERT INTO simulation_runs (run_id, metadata) VALUES (?, ?) "
                "ON CONFLICT(run_id) DO UPDATE SET metadata = excluded.metadata",
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
    def _encode(value: dict[str, Any]) -> str:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )

    @staticmethod
    def _decode(value: str) -> dict[str, Any]:
        decoded = json.loads(value)
        if not isinstance(decoded, dict):
            raise ValueError("Persisted simulation run payload must be an object")
        return decoded
