import gzip
import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from .default_pipeline_contracts import (
    DefaultPipelineRun,
    DefaultStateSnapshotReference,
)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def sha256_digest(value: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical_json_bytes(value)).hexdigest()}"


def calculate_run_hash(run: DefaultPipelineRun) -> str:
    return sha256_digest(run.model_dump(mode="json", exclude={"run_hash"}))


def default_pipeline_cache_path() -> Path:
    configured = os.getenv("PETRATERRIUM_DEFAULT_PIPELINE_CACHE")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).with_name("defaults") / "pipeline_runs"


def _section_count(name: str, value: Any) -> int:
    if name == "initial_population" and isinstance(value, dict):
        population = value.get("population", {})
        if isinstance(population, dict) and isinstance(population.get("agents"), list):
            return len(population["agents"])
    if isinstance(value, list | tuple):
        return len(value)
    if isinstance(value, dict):
        for key in ("definitions", "programs", "countries", "defaults"):
            records = value.get(key)
            if isinstance(records, list):
                return len(records)
        return len(value)
    return 1


class JsonDefaultPipelineRepository:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or default_pipeline_cache_path())
        self.runs_path = self.root / "runs"
        self.snapshots_path = self.root / "snapshots"
        self.index_path = self.root / "index.json"
        self._lock = threading.RLock()
        self.runs_path.mkdir(parents=True, exist_ok=True)
        self.snapshots_path.mkdir(parents=True, exist_ok=True)

    def next_version(self) -> tuple[int, str | None]:
        with self._lock:
            runs = self.list()
            if not runs:
                return 1, None
            latest = max(runs, key=lambda item: item.version)
            return latest.version + 1, latest.run_id

    def store_snapshot(self, sections: dict[str, Any]) -> DefaultStateSnapshotReference:
        if not sections:
            raise ValueError("A default-state snapshot needs at least one section")
        content = canonical_json_bytes(sections)
        raw_digest = hashlib.sha256(content).hexdigest()
        compressed = gzip.compress(content, compresslevel=9, mtime=0)
        relative_path = f"snapshots/{raw_digest}.json.gz"
        destination = self.root / relative_path
        with self._lock:
            if not destination.exists():
                self._atomic_write(destination, compressed)
        return DefaultStateSnapshotReference(
            snapshot_id=raw_digest,
            relative_path=relative_path,
            content_hash=f"sha256:{raw_digest}",
            section_hashes={
                name: sha256_digest(value) for name, value in sorted(sections.items())
            },
            section_counts={
                name: _section_count(name, value)
                for name, value in sorted(sections.items())
            },
            compressed_bytes=len(compressed),
        )

    def read_snapshot(self, reference: DefaultStateSnapshotReference) -> dict[str, Any]:
        path = self.root / reference.relative_path
        if not path.exists():
            raise KeyError(f"Default-state snapshot {reference.snapshot_id} does not exist")
        compressed = path.read_bytes()
        if len(compressed) != reference.compressed_bytes:
            raise ValueError("Cached default-state snapshot byte size does not match its receipt")
        try:
            content = gzip.decompress(compressed)
        except gzip.BadGzipFile as error:
            raise ValueError("Cached default-state snapshot is not valid gzip data") from error
        digest = hashlib.sha256(content).hexdigest()
        if digest != reference.snapshot_id or f"sha256:{digest}" != reference.content_hash:
            raise ValueError("Cached default-state snapshot hash does not match its receipt")
        value = json.loads(content)
        if not isinstance(value, dict):
            raise ValueError("Cached default-state snapshot must contain an object")
        actual_hashes = {name: sha256_digest(item) for name, item in sorted(value.items())}
        if actual_hashes != reference.section_hashes:
            raise ValueError("Cached default-state snapshot section hashes do not match")
        return value

    def save(self, run: DefaultPipelineRun) -> None:
        if calculate_run_hash(run) != run.run_hash:
            raise ValueError("Default pipeline run hash does not match its contents")
        destination = self._run_path(run.run_id)
        with self._lock:
            if destination.exists():
                existing = self.get(run.run_id)
                if existing != run:
                    raise ValueError(f"Default pipeline run {run.run_id} is immutable")
                return
            if any(item.version == run.version for item in self.list()):
                raise ValueError(f"Default pipeline version {run.version} already exists")
            self._atomic_write(
                destination,
                run.model_dump_json(indent=2).encode("utf-8"),
            )

    def get(self, run_id: str) -> DefaultPipelineRun:
        path = self._run_path(run_id)
        if not path.exists():
            raise KeyError(f"Default pipeline run {run_id} does not exist")
        run = DefaultPipelineRun.model_validate_json(path.read_text(encoding="utf-8"))
        if calculate_run_hash(run) != run.run_hash:
            raise ValueError(f"Default pipeline run {run_id} failed integrity validation")
        return run

    def list(self) -> tuple[DefaultPipelineRun, ...]:
        runs = tuple(
            self.get(path.stem)
            for path in self.runs_path.glob("*.json")
            if path.is_file()
        )
        return tuple(sorted(runs, key=lambda item: (item.version, item.run_id), reverse=True))

    def active_run_id(self) -> str | None:
        with self._lock:
            return self._read_index().get("active_run_id")

    def activate(self, run_id: str) -> None:
        self.get(run_id)
        with self._lock:
            self._write_index({"schema_version": "1", "active_run_id": run_id})

    def _run_path(self, run_id: str) -> Path:
        if len(run_id) != 32 or any(character not in "0123456789abcdef" for character in run_id):
            raise ValueError("Default pipeline run id must be a 32-character hexadecimal value")
        return self.runs_path / f"{run_id}.json"

    def _read_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"schema_version": "1", "active_run_id": None}
        value = json.loads(self.index_path.read_text(encoding="utf-8"))
        if value.get("schema_version") != "1":
            raise ValueError("Unsupported default pipeline cache index version")
        active = value.get("active_run_id")
        if active is not None:
            self._run_path(active)
        return value

    def _write_index(self, value: dict[str, Any]) -> None:
        self._atomic_write(self.index_path, canonical_json_bytes(value))

    @staticmethod
    def _atomic_write(destination: Path, content: bytes) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            delete=False,
        )
        temporary = Path(handle.name)
        try:
            with handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(destination)
        finally:
            if temporary.exists():
                temporary.unlink()

