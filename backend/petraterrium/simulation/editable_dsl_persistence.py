import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from .editable_dsl_contracts import EditableDslDocument, EditableDslRevision


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def editable_document_hash(document: EditableDslDocument) -> str:
    content = canonical_json_bytes(document.model_dump(mode="json"))
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def editable_preview_hash(value: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical_json_bytes(value)).hexdigest()}"


def default_editable_dsl_path() -> Path:
    configured = os.getenv("PETRATERRIUM_EDITABLE_DSL_PATH")
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[2] / "data" / "editable_dsl"


class JsonEditableDslRepository:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or default_editable_dsl_path())
        self.revisions_path = self.root / "revisions"
        self.index_path = self.root / "index.json"
        self._lock = threading.RLock()
        self.revisions_path.mkdir(parents=True, exist_ok=True)

    def active(self) -> EditableDslRevision | None:
        with self._lock:
            document_hash = self._read_index()["active_document_hash"]
            return self.get(document_hash) if document_hash is not None else None

    def history(self) -> tuple[EditableDslRevision, ...]:
        with self._lock:
            records = tuple(
                self.get(f"sha256:{path.stem}")
                for path in self.revisions_path.glob("*.json")
                if path.is_file()
            )
            return tuple(
                sorted(
                    records,
                    key=lambda item: (item.revision, item.document_hash),
                    reverse=True,
                )
            )

    def get(self, document_hash: str) -> EditableDslRevision:
        path = self._revision_path(document_hash)
        if not path.exists():
            raise KeyError(f"Editable DSL revision {document_hash} does not exist")
        record = EditableDslRevision.model_validate_json(path.read_text(encoding="utf-8"))
        if record.document_hash != document_hash:
            raise ValueError("Editable DSL revision filename does not match its receipt")
        if editable_document_hash(record.document) != record.document_hash:
            raise ValueError("Editable DSL revision hash does not match its document")
        return record

    def save_and_activate(
        self,
        record: EditableDslRevision,
        expected_active_hash: str,
        installed_hash: str,
    ) -> None:
        if editable_document_hash(record.document) != record.document_hash:
            raise ValueError("Editable DSL revision hash does not match its document")
        destination = self._revision_path(record.document_hash)
        with self._lock:
            active_hash = self._read_index()["active_document_hash"] or installed_hash
            if active_hash != expected_active_hash:
                raise ValueError(
                    "Editable DSL changed since preview; preview the active version again"
                )
            expected_revision = max((item.revision for item in self.history()), default=0) + 1
            if record.revision != expected_revision:
                raise ValueError(
                    f"Editable DSL revision must be {expected_revision}, got {record.revision}"
                )
            if destination.exists():
                existing = self.get(record.document_hash)
                if existing != record:
                    raise ValueError("Editable DSL revision is immutable")
            else:
                self._atomic_write(
                    destination,
                    record.model_dump_json(indent=2).encode("utf-8"),
                )
            self._write_index(record.document_hash)

    def next_revision(self) -> int:
        return max((item.revision for item in self.history()), default=0) + 1

    def deactivate(self) -> None:
        with self._lock:
            self._atomic_write(
                self.index_path,
                canonical_json_bytes({"schema_version": "1", "active_document_hash": None}),
            )

    def _revision_path(self, document_hash: str) -> Path:
        prefix = "sha256:"
        if not document_hash.startswith(prefix):
            raise ValueError("Editable DSL hash must use sha256")
        digest = document_hash.removeprefix(prefix)
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("Editable DSL hash must contain 64 lowercase hexadecimal characters")
        return self.revisions_path / f"{digest}.json"

    def _read_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"schema_version": "1", "active_document_hash": None}
        value = json.loads(self.index_path.read_text(encoding="utf-8"))
        if value.get("schema_version") != "1":
            raise ValueError("Unsupported editable DSL index version")
        active_hash = value.get("active_document_hash")
        if active_hash is not None:
            self._revision_path(active_hash)
        return value

    def _write_index(self, document_hash: str) -> None:
        self._atomic_write(
            self.index_path,
            canonical_json_bytes({"schema_version": "1", "active_document_hash": document_hash}),
        )

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
