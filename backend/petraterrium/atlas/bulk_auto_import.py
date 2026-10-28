import asyncio
import inspect
import math
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from ..contracts import Contract

HierarchyLevel = Literal["region", "country", "city"]
CityCohort = Literal["priority", "below_threshold", "all"]
EvidenceStatus = Literal["measured", "estimated", "unresolved"]
ExecutionState = Literal["pending", "running", "review", "failed"]
PromotionState = Literal["not_requested", "promoting", "promoted", "failed"]
BatchState = Literal[
    "ready",
    "running",
    "review_ready",
    "failed",
    "partially_promoted",
    "promotion_complete",
]

DEFAULT_CITY_POPULATION_THRESHOLD = 1_000_000
LEVEL_ORDER: dict[HierarchyLevel, int] = {"region": 0, "country": 1, "city": 2}


class BulkImportTarget(Contract):
    item_id: str = Field(min_length=1)
    place_id: str = Field(min_length=1)
    place_name: str = Field(min_length=1)
    level: HierarchyLevel
    feature_id: str = Field(min_length=1)
    population: int = Field(ge=0)
    missing_impact: float = Field(ge=0, allow_inf_nan=False)
    attributes: dict[str, str] = Field(default_factory=dict)


class BulkImportSelection(Contract):
    levels: tuple[HierarchyLevel, ...] = ("region", "country", "city")
    feature_ids: tuple[str, ...] = ()
    place_ids: tuple[str, ...] = ()
    item_ids: tuple[str, ...] = ()
    search: str = Field(default="", max_length=200)
    filters: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    city_cohort: CityCohort = "priority"
    city_population_threshold: int = Field(
        default=DEFAULT_CITY_POPULATION_THRESHOLD,
        ge=1,
    )

    @field_validator("levels")
    @classmethod
    def selected_levels(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("Select at least one hierarchy level")
        if len(values) != len(set(values)):
            raise ValueError("Selection values must be unique")
        return values

    @field_validator("feature_ids", "place_ids", "item_ids")
    @classmethod
    def unique_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value.strip() for value in values):
            raise ValueError("Selection values cannot be blank")
        if len(values) != len(set(values)):
            raise ValueError("Selection values must be unique")
        return values

    @field_validator("filters")
    @classmethod
    def valid_filters(cls, filters: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
        for key, values in filters.items():
            if not key.strip() or not values or any(not value.strip() for value in values):
                raise ValueError("Filters require a name and at least one non-blank value")
            if len(values) != len(set(values)):
                raise ValueError("Filter values must be unique")
        return filters

    @classmethod
    def below_threshold_cities(
        cls,
        *,
        threshold: int = DEFAULT_CITY_POPULATION_THRESHOLD,
        feature_ids: tuple[str, ...] = (),
        filters: dict[str, tuple[str, ...]] | None = None,
    ) -> "BulkImportSelection":
        return cls(
            levels=("city",),
            feature_ids=feature_ids,
            filters=filters or {},
            city_cohort="below_threshold",
            city_population_threshold=threshold,
        )


class BulkExecutionRequest(Contract):
    batch_id: str
    target: BulkImportTarget
    attempt_number: int = Field(ge=1)
    previous_attempt_id: str | None = None


class BulkImportOutcome(Contract):
    attempt_id: str = Field(min_length=1)
    evidence_status: EvidenceStatus
    summary: str = Field(min_length=1)
    source_labels: tuple[str, ...] = ()
    confidence_interval: tuple[float, float] | None = None
    estimate_reason: str | None = None
    promotion_eligible: bool
    predictor_eligible: bool
    payload_reference: str | None = None
    trace_reference: str | None = None

    @model_validator(mode="before")
    @classmethod
    def readable_legacy_unresolved(cls, value):
        if not isinstance(value, dict) or value.get("evidence_status") != "unresolved":
            return value
        normalized = dict(value)
        if normalized.get("summary") in {
            "No credible distribution found",
            "No data found",
        }:
            normalized["summary"] = (
                "Retry with another source or engine to produce an estimated draft"
            )
        return normalized

    @model_validator(mode="after")
    def honest_evidence(self) -> "BulkImportOutcome":
        if self.confidence_interval is not None:
            low, high = self.confidence_interval
            if not math.isfinite(low) or not math.isfinite(high) or low > high:
                raise ValueError("Confidence interval must contain finite ordered bounds")
        if self.evidence_status in {"measured", "estimated"} and not self.source_labels:
            raise ValueError("Measured and estimated evidence require at least one source")
        if self.evidence_status == "estimated":
            if not self.estimate_reason or self.confidence_interval is None:
                raise ValueError("Estimated evidence requires reasoning and a confidence interval")
            if self.predictor_eligible:
                raise ValueError("Estimated evidence cannot fit a predictor")
        if self.evidence_status == "unresolved":
            if self.promotion_eligible or self.predictor_eligible:
                raise ValueError("Unresolved evidence cannot be promoted or fit a predictor")
        return self


class BulkPromotionRequest(Contract):
    batch_id: str
    target: BulkImportTarget
    outcome: BulkImportOutcome


class BulkPromotionReceipt(Contract):
    promotion_id: str = Field(min_length=1)
    observation_reference: str | None = None


class BulkPromotionSelection(Contract):
    item_ids: tuple[str, ...] = ()
    all_eligible: bool = False

    @model_validator(mode="after")
    def exactly_one_selection(self) -> "BulkPromotionSelection":
        if self.all_eligible == bool(self.item_ids):
            raise ValueError("Choose explicit item IDs or all eligible items")
        if len(self.item_ids) != len(set(self.item_ids)):
            raise ValueError("Promotion item IDs must be unique")
        return self


class BulkImportItemRecord(Contract):
    batch_id: str
    ordinal: int = Field(ge=0)
    target: BulkImportTarget
    execution_state: ExecutionState = "pending"
    attempt_count: int = Field(default=0, ge=0)
    last_attempt_id: str | None = None
    outcome: BulkImportOutcome | None = None
    error: str | None = None
    promotion_state: PromotionState = "not_requested"
    promotion_error: str | None = None
    promotion_receipt: BulkPromotionReceipt | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime


class BulkImportBatchRecord(Contract):
    batch_id: str = Field(min_length=1)
    selection: BulkImportSelection
    max_concurrency: int = Field(ge=1, le=32)
    state: BatchState
    total_items: int = Field(ge=1)
    total_places: int = Field(ge=1)
    total_population: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class BulkImportProgress(Contract):
    total_items: int = Field(ge=0)
    total_places: int = Field(ge=0)
    total_population: int = Field(ge=0)
    pending: int = Field(ge=0)
    running: int = Field(ge=0)
    review: int = Field(ge=0)
    failed: int = Field(ge=0)
    measured: int = Field(ge=0)
    estimated: int = Field(ge=0)
    unresolved: int = Field(ge=0)
    promotion_eligible: int = Field(ge=0)
    promoted: int = Field(ge=0)
    promotion_failed: int = Field(ge=0)
    completed: int = Field(ge=0)
    completion_percent: float = Field(ge=0, le=100)


class BulkImportReview(Contract):
    batch: BulkImportBatchRecord
    progress: BulkImportProgress
    items: tuple[BulkImportItemRecord, ...]


class BulkImportRepository(Protocol):
    async def create_batch(
        self,
        batch: BulkImportBatchRecord,
        items: Sequence[BulkImportItemRecord],
    ) -> None: ...

    async def get_batch(self, batch_id: str) -> BulkImportBatchRecord | None: ...

    async def list_batches(self, scope: str | None = None) -> tuple[BulkImportBatchRecord, ...]: ...

    async def save_batch(self, batch: BulkImportBatchRecord) -> None: ...

    async def list_items(self, batch_id: str) -> tuple[BulkImportItemRecord, ...]: ...

    async def save_item(self, item: BulkImportItemRecord) -> None: ...


BulkExecutor = Callable[
    [BulkExecutionRequest],
    BulkImportOutcome | dict[str, object] | object,
]
BulkPromoter = Callable[
    [BulkPromotionRequest],
    BulkPromotionReceipt | str | dict[str, object] | object,
]


class BulkItemExecutionError(RuntimeError):
    def __init__(self, message: str, attempt_id: str | None = None) -> None:
        super().__init__(message)
        self.attempt_id = attempt_id


class BulkBatchNotFound(LookupError):
    pass


class InMemoryBulkImportRepository:
    def __init__(self) -> None:
        self._batches: dict[str, BulkImportBatchRecord] = {}
        self._items: dict[str, dict[str, BulkImportItemRecord]] = {}
        self._lock = asyncio.Lock()

    async def create_batch(
        self,
        batch: BulkImportBatchRecord,
        items: Sequence[BulkImportItemRecord],
    ) -> None:
        async with self._lock:
            if batch.batch_id in self._batches:
                raise ValueError(f"Batch already exists: {batch.batch_id}")
            item_records = {item.target.item_id: item for item in items}
            if len(item_records) != len(items):
                raise ValueError("Batch item IDs must be unique")
            self._batches[batch.batch_id] = batch
            self._items[batch.batch_id] = item_records

    async def get_batch(self, batch_id: str) -> BulkImportBatchRecord | None:
        async with self._lock:
            return self._batches.get(batch_id)

    async def list_batches(self, scope: str | None = None) -> tuple[BulkImportBatchRecord, ...]:
        async with self._lock:
            batches = list(self._batches.values())
        return tuple(sorted(batches, key=lambda batch: batch.updated_at, reverse=True))

    async def save_batch(self, batch: BulkImportBatchRecord) -> None:
        async with self._lock:
            if batch.batch_id not in self._batches:
                raise BulkBatchNotFound(batch.batch_id)
            self._batches[batch.batch_id] = batch

    async def list_items(self, batch_id: str) -> tuple[BulkImportItemRecord, ...]:
        async with self._lock:
            if batch_id not in self._items:
                raise BulkBatchNotFound(batch_id)
            return tuple(sorted(self._items[batch_id].values(), key=lambda item: item.ordinal))

    async def save_item(self, item: BulkImportItemRecord) -> None:
        async with self._lock:
            if item.batch_id not in self._items:
                raise BulkBatchNotFound(item.batch_id)
            if item.target.item_id not in self._items[item.batch_id]:
                raise LookupError(item.target.item_id)
            self._items[item.batch_id][item.target.item_id] = item


def target_order(target: BulkImportTarget) -> tuple[int, float, int, str, str, str]:
    return (
        LEVEL_ORDER[target.level],
        -target.missing_impact,
        -target.population,
        target.place_name.casefold(),
        target.feature_id.casefold(),
        target.item_id,
    )


def _matches_city_cohort(
    target: BulkImportTarget,
    selection: BulkImportSelection,
) -> bool:
    if target.level != "city" or target.item_id in selection.item_ids:
        return True
    if selection.city_cohort == "all":
        return True
    if selection.city_cohort == "priority":
        return target.population >= selection.city_population_threshold
    return target.population < selection.city_population_threshold


def _matches_filters(target: BulkImportTarget, selection: BulkImportSelection) -> bool:
    for name, accepted in selection.filters.items():
        if target.attributes.get(name) not in accepted:
            return False
    return True


def _matches_search(target: BulkImportTarget, search: str) -> bool:
    term = search.casefold().strip()
    if not term:
        return True
    return (
        term
        in " ".join(
            (
                target.item_id,
                target.place_id,
                target.place_name,
                target.feature_id,
                *target.attributes.values(),
            )
        ).casefold()
    )


def select_bulk_targets(
    candidates: Iterable[BulkImportTarget],
    selection: BulkImportSelection,
) -> tuple[BulkImportTarget, ...]:
    seen: set[str] = set()
    selected: list[BulkImportTarget] = []
    for target in candidates:
        if target.item_id in seen:
            raise ValueError(f"Duplicate bulk target: {target.item_id}")
        seen.add(target.item_id)
        if target.level not in selection.levels:
            continue
        if selection.feature_ids and target.feature_id not in selection.feature_ids:
            continue
        if selection.place_ids and target.place_id not in selection.place_ids:
            continue
        if selection.item_ids and target.item_id not in selection.item_ids:
            continue
        if not _matches_city_cohort(target, selection):
            continue
        if not _matches_filters(target, selection):
            continue
        if not _matches_search(target, selection.search):
            continue
        selected.append(target)
    selected.sort(key=target_order)
    return tuple(selected)


class BulkAutoImportOrchestrator:
    def __init__(
        self,
        repository: BulkImportRepository,
        executor: BulkExecutor,
        promoter: BulkPromoter | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.repository = repository
        self.executor = executor
        self.promoter = promoter
        self.clock = clock or (lambda: datetime.now(UTC))
        self.id_factory = id_factory or (lambda: f"bulk-{uuid4().hex}")
        self._run_locks: dict[str, asyncio.Lock] = {}
        self._promotion_locks: dict[str, asyncio.Lock] = {}

    async def create_batch(
        self,
        candidates: Iterable[BulkImportTarget],
        selection: BulkImportSelection | None = None,
        *,
        max_concurrency: int = 4,
    ) -> BulkImportReview:
        chosen_selection = selection or BulkImportSelection()
        targets = select_bulk_targets(candidates, chosen_selection)
        if not targets:
            raise ValueError("No missing fields match this bulk selection")
        if not 1 <= max_concurrency <= 32:
            raise ValueError("Bulk concurrency must be between one and 32")
        batch_id = self.id_factory()
        now = self.clock()
        populations_by_place: dict[str, int] = {}
        for target in targets:
            populations_by_place[target.place_id] = max(
                target.population,
                populations_by_place.get(target.place_id, 0),
            )
        batch = BulkImportBatchRecord(
            batch_id=batch_id,
            selection=chosen_selection,
            max_concurrency=max_concurrency,
            state="ready",
            total_items=len(targets),
            total_places=len(populations_by_place),
            total_population=sum(populations_by_place.values()),
            created_at=now,
            updated_at=now,
        )
        items = tuple(
            BulkImportItemRecord(
                batch_id=batch_id,
                ordinal=ordinal,
                target=target,
                updated_at=now,
            )
            for ordinal, target in enumerate(targets)
        )
        await self.repository.create_batch(batch, items)
        return await self.review(batch_id)

    async def run(self, batch_id: str) -> BulkImportReview:
        return await self._run(batch_id, retry_failed=False, retry_unresolved=False)

    async def resume(
        self,
        batch_id: str,
        *,
        retry_unresolved: bool = False,
    ) -> BulkImportReview:
        return await self._run(
            batch_id,
            retry_failed=True,
            retry_unresolved=retry_unresolved,
        )

    async def _run(
        self,
        batch_id: str,
        *,
        retry_failed: bool,
        retry_unresolved: bool,
    ) -> BulkImportReview:
        lock = self._run_locks.setdefault(batch_id, asyncio.Lock())
        async with lock:
            batch = await self._require_batch(batch_id)
            items = await self.repository.list_items(batch_id)
            runnable = [
                item
                for item in items
                if item.execution_state in {"pending", "running"}
                or (retry_failed and item.execution_state == "failed")
                or (
                    retry_unresolved
                    and item.execution_state == "review"
                    and item.outcome is not None
                    and item.outcome.evidence_status == "unresolved"
                )
            ]
            if not runnable:
                await self._refresh_batch_state(batch_id)
                return await self.review(batch_id)
            await self.repository.save_batch(
                batch.model_copy(update={"state": "running", "updated_at": self.clock()})
            )
            queue: asyncio.Queue[BulkImportItemRecord | None] = asyncio.Queue()
            for item in runnable:
                queue.put_nowait(item)
            worker_count = min(batch.max_concurrency, len(runnable))
            for _ in range(worker_count):
                queue.put_nowait(None)
            workers = [asyncio.create_task(self._worker(queue)) for _ in range(worker_count)]
            await queue.join()
            await asyncio.gather(*workers)
            await self._refresh_batch_state(batch_id)
            return await self.review(batch_id)

    async def _worker(self, queue: asyncio.Queue[BulkImportItemRecord | None]) -> None:
        while True:
            item = await queue.get()
            try:
                if item is None:
                    return
                await self._execute_item(item)
            finally:
                queue.task_done()

    async def _execute_item(self, item: BulkImportItemRecord) -> None:
        now = self.clock()
        attempt_count = item.attempt_count + 1
        running = item.model_copy(
            update={
                "execution_state": "running",
                "attempt_count": attempt_count,
                "error": None,
                "started_at": now,
                "completed_at": None,
                "updated_at": now,
            }
        )
        await self.repository.save_item(running)
        request = BulkExecutionRequest(
            batch_id=item.batch_id,
            target=item.target,
            attempt_number=attempt_count,
            previous_attempt_id=item.last_attempt_id,
        )
        try:
            raw_outcome = self.executor(request)
            if inspect.isawaitable(raw_outcome):
                raw_outcome = await raw_outcome
            outcome = BulkImportOutcome.model_validate(raw_outcome)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            attempt_id = getattr(error, "attempt_id", None) or item.last_attempt_id
            failed_at = self.clock()
            failed = running.model_copy(
                update={
                    "execution_state": "failed",
                    "last_attempt_id": attempt_id,
                    "outcome": None,
                    "error": f"{type(error).__name__}: {error}",
                    "completed_at": failed_at,
                    "updated_at": failed_at,
                }
            )
            await self.repository.save_item(failed)
            return
        completed_at = self.clock()
        completed = running.model_copy(
            update={
                "execution_state": "review",
                "last_attempt_id": outcome.attempt_id,
                "outcome": outcome,
                "error": None,
                "completed_at": completed_at,
                "updated_at": completed_at,
                "promotion_state": "not_requested",
                "promotion_error": None,
                "promotion_receipt": None,
            }
        )
        await self.repository.save_item(completed)

    async def promote(
        self,
        batch_id: str,
        selection: BulkPromotionSelection,
    ) -> BulkImportReview:
        if self.promoter is None:
            raise RuntimeError("Bulk promotion requires an explicit promotion callback")
        lock = self._promotion_locks.setdefault(batch_id, asyncio.Lock())
        async with lock:
            await self._require_batch(batch_id)
            items = await self.repository.list_items(batch_id)
            items_by_id = {item.target.item_id: item for item in items}
            if selection.all_eligible:
                selected = [
                    item
                    for item in items
                    if self._is_promotion_eligible(item) and item.promotion_state != "promoted"
                ]
            else:
                unknown = [item_id for item_id in selection.item_ids if item_id not in items_by_id]
                if unknown:
                    raise ValueError(f"Unknown bulk item IDs: {', '.join(unknown)}")
                selected = [items_by_id[item_id] for item_id in selection.item_ids]
                ineligible = [
                    item.target.item_id
                    for item in selected
                    if not self._is_promotion_eligible(item)
                ]
                if ineligible:
                    raise ValueError(
                        f"Items are not eligible for promotion: {', '.join(ineligible)}"
                    )
                selected = [item for item in selected if item.promotion_state != "promoted"]
            for item in selected:
                await self._promote_item(item)
            await self._refresh_batch_state(batch_id)
            return await self.review(batch_id)

    @staticmethod
    def _is_promotion_eligible(item: BulkImportItemRecord) -> bool:
        return (
            item.execution_state == "review"
            and item.outcome is not None
            and item.outcome.promotion_eligible
        )

    async def _promote_item(self, item: BulkImportItemRecord) -> None:
        if self.promoter is None or item.outcome is None:
            raise RuntimeError("Promotion callback and reviewed outcome are required")
        promoting = item.model_copy(
            update={
                "promotion_state": "promoting",
                "promotion_error": None,
                "updated_at": self.clock(),
            }
        )
        await self.repository.save_item(promoting)
        request = BulkPromotionRequest(
            batch_id=item.batch_id,
            target=item.target,
            outcome=item.outcome,
        )
        try:
            raw_receipt = self.promoter(request)
            if inspect.isawaitable(raw_receipt):
                raw_receipt = await raw_receipt
            if isinstance(raw_receipt, str):
                receipt = BulkPromotionReceipt(promotion_id=raw_receipt)
            else:
                receipt = BulkPromotionReceipt.model_validate(raw_receipt)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            failed = promoting.model_copy(
                update={
                    "promotion_state": "failed",
                    "promotion_error": f"{type(error).__name__}: {error}",
                    "updated_at": self.clock(),
                }
            )
            await self.repository.save_item(failed)
            return
        promoted = promoting.model_copy(
            update={
                "promotion_state": "promoted",
                "promotion_receipt": receipt,
                "promotion_error": None,
                "updated_at": self.clock(),
            }
        )
        await self.repository.save_item(promoted)

    async def review(self, batch_id: str) -> BulkImportReview:
        batch = await self._require_batch(batch_id)
        items = await self.repository.list_items(batch_id)
        return BulkImportReview(
            batch=batch,
            progress=self._progress(batch, items),
            items=items,
        )

    async def refresh(self, batch_id: str) -> BulkImportReview:
        await self._refresh_batch_state(batch_id)
        return await self.review(batch_id)

    async def _require_batch(self, batch_id: str) -> BulkImportBatchRecord:
        batch = await self.repository.get_batch(batch_id)
        if batch is None:
            raise BulkBatchNotFound(batch_id)
        return batch

    async def _refresh_batch_state(self, batch_id: str) -> None:
        batch = await self._require_batch(batch_id)
        items = await self.repository.list_items(batch_id)
        state = self._batch_state(items)
        await self.repository.save_batch(
            batch.model_copy(update={"state": state, "updated_at": self.clock()})
        )

    @staticmethod
    def _batch_state(items: Sequence[BulkImportItemRecord]) -> BatchState:
        if any(item.execution_state == "running" for item in items):
            return "running"
        if any(item.execution_state == "pending" for item in items):
            return "ready"
        review_items = [item for item in items if item.execution_state == "review"]
        if not review_items:
            return "failed"
        eligible = [
            item for item in review_items if item.outcome and item.outcome.promotion_eligible
        ]
        promoted = [item for item in eligible if item.promotion_state == "promoted"]
        fully_resolved = bool(items) and all(
            item.execution_state == "review"
            and item.outcome is not None
            and item.outcome.evidence_status != "unresolved"
            and item.outcome.promotion_eligible
            and item.promotion_state == "promoted"
            for item in items
        )
        if fully_resolved:
            return "promotion_complete"
        if promoted:
            return "partially_promoted"
        return "review_ready"

    @staticmethod
    def _progress(
        batch: BulkImportBatchRecord,
        items: Sequence[BulkImportItemRecord],
    ) -> BulkImportProgress:
        execution_counts = Counter(item.execution_state for item in items)
        evidence_counts = Counter(
            item.outcome.evidence_status for item in items if item.outcome is not None
        )
        promotion_counts = Counter(item.promotion_state for item in items)
        completed = execution_counts["review"] + execution_counts["failed"]
        eligible = sum(bool(item.outcome and item.outcome.promotion_eligible) for item in items)
        completion_percent = round(completed * 100 / len(items), 6) if items else 0
        return BulkImportProgress(
            total_items=batch.total_items,
            total_places=batch.total_places,
            total_population=batch.total_population,
            pending=execution_counts["pending"],
            running=execution_counts["running"],
            review=execution_counts["review"],
            failed=execution_counts["failed"],
            measured=evidence_counts["measured"],
            estimated=evidence_counts["estimated"],
            unresolved=evidence_counts["unresolved"],
            promotion_eligible=eligible,
            promoted=promotion_counts["promoted"],
            promotion_failed=promotion_counts["failed"],
            completed=completed,
            completion_percent=completion_percent,
        )
