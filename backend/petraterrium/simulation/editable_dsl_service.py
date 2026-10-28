import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from .editable_dsl_adapter import (
    EditableDslRegistryOverlay,
    InstalledRegistryDslAdapter,
    RefreshingEditableDslRegistry,
)
from .editable_dsl_contracts import (
    ConfirmEditableDslRequest,
    EditableDslDiff,
    EditableDslDocument,
    EditableDslRevision,
    PreviewEditableDslRequest,
    PreviewEditableDslResponse,
)
from .editable_dsl_persistence import (
    JsonEditableDslRepository,
    editable_document_hash,
    editable_preview_hash,
)
from .editable_dsl_validation import validate_editable_dsl
from .registry_store import SimulationRegistryStore


def _flatten(
    value: Any,
    path: str = "",
    output: dict[str, str] | None = None,
) -> dict[str, str]:
    selected = output if output is not None else {}
    if isinstance(value, list | tuple):
        if not value:
            selected[path] = "[]"
        for index, item in enumerate(value):
            _flatten(item, f"{path}[{index}]", selected)
        return selected
    if isinstance(value, dict):
        if not value:
            selected[path] = "{}"
        for key, item in value.items():
            _flatten(item, f"{path}.{key}" if path else str(key), selected)
        return selected
    selected[path] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return selected


def diff_documents(
    before: EditableDslDocument,
    after: EditableDslDocument,
) -> tuple[EditableDslDiff, ...]:
    before_values = _flatten(before.model_dump(mode="json"))
    after_values = _flatten(after.model_dump(mode="json"))
    return tuple(
        EditableDslDiff(
            path=path,
            before=before_values.get(path, "(not present)"),
            after=after_values.get(path, "(removed)"),
        )
        for path in sorted(before_values.keys() | after_values.keys())
        if before_values.get(path) != after_values.get(path)
    )


class EditableDslService:
    def __init__(
        self,
        store: SimulationRegistryStore,
        repository: JsonEditableDslRepository | None = None,
        clock: Callable[[], str] | None = None,
        tick_hours: float = 1.0,
    ):
        self.store = store
        self.repository = repository or JsonEditableDslRepository()
        self.clock = clock or (lambda: datetime.now(UTC).isoformat())
        self.adapter = InstalledRegistryDslAdapter(store, tick_hours=tick_hours)
        self._overlay_registry: SimulationRegistryStore | None = None
        self._overlay_path = self.repository.root / "active-registry-overlay.json"
        self._materialized_signature: tuple[int, int, str | None] | None = None

    def current(self) -> EditableDslRevision:
        active = self.repository.active()
        if active is not None:
            return active
        document = self.adapter.document()
        return EditableDslRevision(
            revision=0,
            version=document.version,
            document_hash=editable_document_hash(document),
            parent_hash=None,
            accepted_at=None,
            source="installed_registry",
            document=document,
        )

    def history(self) -> tuple[EditableDslRevision, ...]:
        return self.repository.history()

    def preview(
        self,
        request: PreviewEditableDslRequest,
    ) -> PreviewEditableDslResponse:
        current = self.current()
        if request.expected_active_hash != current.document_hash:
            raise ValueError("Editable DSL changed since preview; load the active version again")
        validation = validate_editable_dsl(
            request.document,
            required_root_module_ids=self.adapter.required_root_module_ids(),
            baseline=self.adapter.document(),
        )
        document_hash = editable_document_hash(request.document)
        diff = diff_documents(current.document, request.document)
        preview_payload = {
            "expected_active_hash": request.expected_active_hash,
            "document_hash": document_hash,
            "validation": validation.model_dump(mode="json"),
            "diff": [item.model_dump(mode="json") for item in diff],
        }
        return PreviewEditableDslResponse(
            expected_active_hash=request.expected_active_hash,
            document_hash=document_hash,
            preview_hash=editable_preview_hash(preview_payload),
            validation=validation,
            diff=diff,
        )

    def confirm(
        self,
        request: ConfirmEditableDslRequest,
    ) -> EditableDslRevision:
        preview = self.preview(
            PreviewEditableDslRequest(
                expected_active_hash=request.expected_active_hash,
                document=request.document,
            )
        )
        if request.preview_hash != preview.preview_hash:
            raise ValueError("Editable DSL preview changed; inspect the current diff again")
        if not preview.validation.valid:
            raise ValueError("Editable DSL has validation errors and cannot be confirmed")
        if not preview.diff:
            raise ValueError("Editable DSL confirmation requires at least one staged change")
        revision_number = self.repository.next_revision()
        record = EditableDslRevision(
            revision=revision_number,
            version=f"{request.document.version}+edit.{revision_number}",
            document_hash=preview.document_hash,
            parent_hash=request.expected_active_hash,
            accepted_at=self.clock(),
            source="confirmed_edit",
            document=request.document,
        )
        self.repository.save_and_activate(
            record,
            expected_active_hash=request.expected_active_hash,
            installed_hash=self._installed_hash(),
        )
        if self._overlay_registry is not None:
            self._materialize_overlay(force=True)
        return record

    def registry_overlay(self) -> SimulationRegistryStore:
        if self._overlay_registry is None:
            self._overlay_registry = RefreshingEditableDslRegistry(
                self._overlay_path,
                self._materialize_overlay,
            )
        self._materialize_overlay(force=True)
        return self._overlay_registry

    def clear_active_overlay(self) -> None:
        self.repository.deactivate()
        if self._overlay_registry is not None:
            self._materialize_overlay(force=True)

    def _materialize_overlay(self, force: bool = False) -> None:
        if self._overlay_registry is None:
            return
        stat = self.store.path.stat() if self.store.path.exists() else None
        active = self.repository.active()
        signature = (
            stat.st_mtime_ns if stat is not None else 0,
            stat.st_size if stat is not None else 0,
            active.document_hash if active is not None else None,
        )
        if not force and signature == self._materialized_signature and self._overlay_path.exists():
            return
        if active is None:
            target = SimulationRegistryStore(self._overlay_path)
            with target._lock:
                target._write(self.store.payload_snapshot())
        else:
            EditableDslRegistryOverlay(
                self.store,
                active,
                path=self._overlay_path,
            )
        self._materialized_signature = signature

    def _installed_hash(self) -> str:
        document = self.adapter.document()
        return editable_document_hash(document)
