import asyncio
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import ValidationError

from .auto_import_contracts import (
    AutoImportAttemptView,
    AutoImportBatchPromotionRequest,
    AutoImportBatchRequest,
    AutoImportBatchView,
    AutoImportEvidenceView,
    AutoImportExplicitSelection,
    AutoImportMappingReview,
    AutoImportPromotionRequest,
    AutoImportQueuePageView,
    AutoImportTargetView,
)
from .auto_import_persistence import SQLiteAttemptRepository, SQLiteBulkImportRepository
from .auto_import_promotion import AtlasAutoImportPromotionWriter, sync_missing_document
from .auto_import_provider import MAX_RESEARCH_BYTES, PublicResearchProvider
from .auto_import_queue import AutoImportQueueItem, auto_import_queue
from .auto_import_requirements import canonical_requirement
from .auto_import_research import (
    ConfirmedLabelMapping,
    ContextPlace,
    MappingConfirmation,
    PlaceFeatureTarget,
    ResearchProvider,
    UserSourceInput,
)
from .auto_import_service import (
    AutoImportResearchService,
    PromotionCommand,
)
from .bulk_auto_import import (
    BulkAutoImportOrchestrator,
    BulkExecutionRequest,
    BulkImportOutcome,
    BulkImportSelection,
    BulkImportTarget,
    BulkPromotionReceipt,
    BulkPromotionSelection,
)
from .bulk_auto_import import (
    BulkPromotionRequest as DomainBulkPromotionRequest,
)
from .database import DEFAULT_PATH, FIELDS, AtlasStore
from .regions import CANONICAL_REGIONS, country_languages, country_region


def _missing_path(store: AtlasStore) -> Path:
    if store.path.resolve() == DEFAULT_PATH.resolve():
        return Path(__file__).resolve().parents[3] / "MISSING.md"
    return store.path.parent / "MISSING.md"


def _label(value: str) -> str:
    return " ".join(part.capitalize() for part in value.replace("_", " ").split())


def _require_shared_licence(attempt) -> None:
    if attempt.target.scope != "shared":
        return
    selected = set(attempt.selected_source_ids)
    unknown = [
        source.title
        for source in attempt.sources
        if source.candidate_id in selected
        and source.license.strip().casefold() in {"", "unknown", "not stated"}
    ]
    if unknown:
        raise ValueError(
            "Shared-atlas promotion requires a stated redistribution licence: "
            + ", ".join(unknown)
        )


def _requirement_view(feature_id: str) -> dict[str, Any]:
    requirement = canonical_requirement(feature_id)
    return {
        "values": [
            {"id": value, "label": _label(value)} for value in requirement.canonical_values
        ],
        "denominator": requirement.denominator,
        "time_unit": requirement.time_unit,
        "unit": requirement.accepted_units[0],
        "range": requirement.value_specification,
        "total": f"{requirement.distribution_total:g}%",
    }


def _queue_item_view(
    item: AutoImportQueueItem,
    threshold: int | None,
    as_of: str,
) -> dict[str, Any]:
    return {
        "item_id": item.target_id,
        "place_id": item.place_key,
        "place_label": item.place_label,
        "level": item.level,
        "country_code": item.country_code,
        "geonameid": item.geonameid,
        "population": item.population,
        "field_id": item.feature,
        "field_label": canonical_requirement(item.feature).name,
        "current_status": item.current_status,
        "as_of": as_of,
        "required_distribution": _requirement_view(item.feature),
        "missing_impact": item.missing_impact,
        "place_item_count": item.place_item_count,
        "priority": "lower"
        if item.level == "city" and threshold is not None and item.population < threshold
        else "primary",
    }


def _attempt_view(attempt) -> dict[str, Any]:
    stage = {
        "draft": "collecting",
        "researching": "collecting",
        "awaiting_mapping_confirmation": "mapping",
        "ready": "ready",
        "not_found": "failed",
        "rejected": "failed",
        "promoted": "promoted",
    }[attempt.status]
    options = [
        {"id": value, "label": _label(value)}
        for value in attempt.requirement.canonical_values
    ]
    values = attempt.proposed_distribution or {}
    mappings = []
    if attempt.mapping_preview:
        for row in attempt.mapping_preview.rows:
            mappings.append(
                {
                    "column": row.source_label,
                    "target": row.proposed_label,
                    "ambiguous": row.confidence == "unknown",
                    "samples": [str(values.get(row.source_label, ""))],
                    "options": options,
                }
            )
    verification = [
        {
            "id": f"{result.candidate_id}:{check.name}",
            "label": _label(check.name),
            "status": "passed" if check.passed else "failed",
            "detail": f"{check.reason} · expected {check.expected} · found {check.actual}",
        }
        for result in attempt.verifications
        for check in result.checks
    ]
    accepted_ids = {source.candidate_id for source in attempt.sources}
    rejected = {
        source.candidate.candidate_id: source for source in attempt.rejected_sources
    }
    all_sources = [*attempt.sources, *(item.candidate for item in attempt.rejected_sources)]
    sources = []
    for source in all_sources:
        rejected_source = rejected.get(source.candidate_id)
        sources.append(
            {
                "source_id": source.candidate_id,
                "title": source.title,
                "publisher": _label(source.source_kind),
                "url": source.url,
                "source_date": source.observation_date.isoformat()
                if source.observation_date
                else None,
                "published_date": source.published_date.isoformat()
                if source.published_date
                else None,
                "version": source.source_version,
                "licence": source.license,
                "language": source.language,
                "original_excerpt": source.original_excerpt,
                "translated_excerpt": source.translated_excerpt,
                "accepted": source.candidate_id in accepted_ids,
                "rejection_reason": "; ".join(rejected_source.verification.reasons)
                if rejected_source
                else None,
            }
        )
    search_log = [
        {
            "engine": entry.engine,
            "language": entry.language,
            "query": entry.query_or_source,
            "searched_at": attempt.updated_at.isoformat(),
            "result_count": len(entry.candidate_ids),
            "outcome": entry.outcome,
            "rejection_reasons": list(entry.rejection_reasons),
        }
        for entry in attempt.search_log
    ]
    estimate = None
    if attempt.estimate_trace:
        trace = attempt.estimate_trace
        estimate = {
            "method": _label(trace.method),
            "calculation": " ".join(trace.calculation),
            "assumptions": list(trace.assumptions),
            "inputs": [
                {
                    "label": f"{extraction.title} · {label}",
                    "value": f"{value:g}% ({extraction.weight_basis})",
                    "source_id": extraction.candidate_id,
                }
                for extraction in trace.extractions
                for label, value in extraction.extracted_distribution.items()
            ],
            "confidence_interval": "; ".join(
                f"{label}: {interval.lower:g}–{interval.upper:g}%"
                for label, interval in trace.confidence_intervals.items()
            ),
            "limitations": [trace.better_data_needed],
        }
    target = attempt.target
    target_view = {
        "place_id": target.place_id,
        "place_label": target.place_label,
        "level": target.level,
        "country_code": target.country_code,
        "geonameid": int(target.place_id)
        if target.level == "city" and target.place_id.isdigit()
        else None,
        "population": target.population,
        "field_id": target.feature_id,
        "field_label": attempt.requirement.name,
        "current_status": target.current_status,
        "as_of": target.as_of.isoformat(),
        "required_distribution": _requirement_view(target.feature_id),
    }
    return {
        "attempt_id": attempt.attempt_id,
        "target": target_view,
        "stage": stage,
        "mappings": mappings,
        "verification": verification,
        "sources": sources,
        "search_log": search_log,
        "evidence_kind": attempt.result_kind,
        "estimate_trace": estimate,
        "candidate_values": attempt.mapped_distribution
        or attempt.proposed_distribution
        or {},
        "can_promote": attempt.status == "ready" and attempt.mapping_confirmed,
        "error": attempt.failure_reason,
        "promoted_at": attempt.updated_at.isoformat()
        if attempt.status == "promoted"
        else None,
    }


def _population_weights(connection) -> dict[str, int]:
    return {
        row["place"]: row["population"]
        for row in connection.execute(
            """SELECT p.place,p.population FROM registry_population_weights p
            WHERE p.level='country' AND p.rowid=(
                SELECT MAX(current.rowid) FROM registry_population_weights current
                WHERE current.level='country' AND current.place=p.place
            )"""
        )
    }


def _place_target(
    store: AtlasStore,
    target: dict[str, Any],
    scope: str,
) -> PlaceFeatureTarget:
    level = str(target.get("level", ""))
    place_id = str(target.get("place_id", ""))
    feature_id = str(target.get("field_id", ""))
    as_of = date.fromisoformat(str(target.get("as_of", date.today().isoformat())))
    if level not in {"region", "country", "city"} or feature_id not in FIELDS:
        raise ValueError("Unknown auto-import target")
    with store.connection() as connection:
        weights = _population_weights(connection)
        countries = {
            row["code"]: row["name"]
            for row in connection.execute("SELECT code,name FROM countries")
        }
        if level == "region":
            if place_id not in CANONICAL_REGIONS:
                raise ValueError("Unknown canonical region")
            codes = [code for code in countries if country_region(code) == place_id]
            city_populations = {
                row["country_code"]: row["population"]
                for row in connection.execute(
                    "SELECT country_code,COALESCE(SUM(population),0) population "
                    "FROM cities GROUP BY country_code"
                )
            }
            population = sum(weights.get(code, city_populations.get(code, 0)) for code in codes)
            languages = Counter(
                language
                for code in codes
                for language in country_languages().get(code, ())[:1]
                if language != "en"
            )
            dominant = tuple(value for value, _ in languages.most_common(3))
            country_code = {"China": "CN", "India": "IN"}.get(place_id)
            return PlaceFeatureTarget(
                level="region",
                place_id=place_id,
                place_label=place_id,
                feature_id=feature_id,
                population=population,
                current_status=str(target.get("current_status", "missing")),
                scope=scope,
                as_of=as_of,
                country_code=country_code,
                dominant_languages=dominant,
            )
        if level == "country":
            code = place_id.upper()
            if code not in countries:
                raise ValueError("Unknown country")
            city_population = connection.execute(
                "SELECT COALESCE(SUM(population),0) FROM cities WHERE country_code=?",
                (code,),
            ).fetchone()[0]
            region = country_region(code)
            return PlaceFeatureTarget(
                level="country",
                place_id=code,
                place_label=countries[code],
                feature_id=feature_id,
                population=weights.get(code, city_population),
                current_status=str(target.get("current_status", "missing")),
                scope=scope,
                as_of=as_of,
                country_code=code,
                dominant_languages=country_languages().get(code, ()),
                context_places=(
                    ContextPlace(level="region", place_id=region, place_label=region),
                ),
            )
        if not place_id.isdigit():
            raise ValueError("City targets require a GeoNames identifier")
        city = connection.execute(
            "SELECT * FROM cities WHERE geonameid=?", (int(place_id),)
        ).fetchone()
        if city is None:
            raise ValueError("Unknown city")
        code = city["country_code"]
        region = country_region(code)
        label = countries.get(code, code)
        languages = country_languages().get(code, ())
        local_names = {languages[0]: city["name"]} if languages else {}
        return PlaceFeatureTarget(
            level="city",
            place_id=place_id,
            place_label=city["name"],
            feature_id=feature_id,
            population=city["population"],
            current_status=str(target.get("current_status", "missing")),
            scope=scope,
            as_of=as_of,
            country_code=code,
            local_names=local_names,
            dominant_languages=languages,
            place_aliases=tuple(
                value
                for value in dict.fromkeys((city["name"], city["asciiname"]))
                if value
            ),
            context_places=(
                ContextPlace(level="country", place_id=code, place_label=label),
                ContextPlace(level="region", place_id=region, place_label=region),
            ),
        )


async def _user_sources(
    urls: str,
    pasted_text: str,
    files: list[UploadFile],
) -> list[UserSourceInput]:
    try:
        parsed_urls = json.loads(urls or "[]")
    except json.JSONDecodeError as error:
        raise ValueError("Source URLs must be a JSON list") from error
    if not isinstance(parsed_urls, list) or any(not isinstance(url, str) for url in parsed_urls):
        raise ValueError("Source URLs must be a JSON list")
    values = [
        UserSourceInput(kind="url", name=url, locator=url) for url in parsed_urls if url.strip()
    ]
    if pasted_text.strip():
        values.append(UserSourceInput(kind="text", name="Pasted source", content=pasted_text))
    for upload in files:
        content = await upload.read(MAX_RESEARCH_BYTES + 1)
        if len(content) > MAX_RESEARCH_BYTES:
            raise ValueError(f"{upload.filename or 'Upload'} exceeds the source size limit")
        filename = Path(upload.filename or "upload").name
        if filename.casefold().endswith(".pdf"):
            raise ValueError("PDF sources are not supported; upload CSV, JSON, Parquet, or text")
        if filename.casefold().endswith(".parquet"):
            import io

            import pyarrow.parquet as parquet

            rows = parquet.read_table(io.BytesIO(content)).to_pylist()
            decoded = json.dumps(rows, default=str)
        else:
            decoded = content.decode("utf-8", errors="replace")
        values.append(UserSourceInput(kind="upload", name=filename, content=decoded))
    return values


def _queue_query(
    store: AtlasStore,
    scope: str,
    as_of: str,
    level: str,
    feature_id: str,
    search: str,
    sort: str,
    priority: str,
    threshold: int | None,
    page: int,
    page_size: int,
):
    levels = (level,) if level in {"region", "country", "city"} else (
        "region",
        "country",
        "city",
    )
    features = (feature_id,) if feature_id else FIELDS
    queue_sort = {
        "hierarchy_impact": "hierarchy",
        "impact": "impact",
        "population": "population",
    }.get(sort, "hierarchy")
    queue_threshold = 0 if priority == "lower" and threshold is None else threshold
    city_batch = "low_priority" if priority == "lower" else (
        "all" if threshold is None else "primary"
    )
    return auto_import_queue(
        store,
        scope=scope,
        as_of=as_of,
        levels=levels,
        features=features,
        search=search,
        sort=queue_sort,
        city_population_threshold=queue_threshold,
        city_batch=city_batch,
        page=page,
        page_size=page_size,
    )


def _queue_response(page, threshold: int | None) -> dict[str, Any]:
    return {
        "items": [_queue_item_view(item, threshold, page.as_of) for item in page.items],
        "filtered_count": page.filtered_count,
        "filtered_population": page.selected_population,
        "page": page.page,
        "page_size": page.page_size,
        "primary_count": page.primary_count,
        "primary_population": page.primary_population,
        "lower_priority_count": page.low_priority_count,
        "lower_priority_population": page.low_priority_population,
    }


def _bulk_target(item: dict[str, Any], scope: str) -> BulkImportTarget:
    return BulkImportTarget(
        item_id=item["item_id"],
        place_id=item["place_id"],
        place_name=item["place_label"],
        level=item["level"],
        feature_id=item["field_id"],
        population=item["population"],
        missing_impact=item["missing_impact"],
        attributes={
            "scope": scope,
            "country_code": item.get("country_code") or "",
            "target_json": json.dumps(item),
        },
    )


def _batch_view(review, service: AutoImportResearchService) -> dict[str, Any]:
    status = {
        "ready": "queued",
        "running": "running",
        "review_ready": "partial" if review.progress.failed else "review",
        "failed": "failed",
        "partially_promoted": "partial",
        "promotion_complete": "complete",
    }[review.batch.state]
    items = []
    for item in review.items:
        outcome = item.outcome
        attempt_view = None
        if item.last_attempt_id:
            try:
                attempt_view = _attempt_view(service.get_attempt(item.last_attempt_id))
            except KeyError:
                attempt_view = None
        if item.promotion_state == "promoted":
            item_status = "promoted"
        elif item.execution_state == "pending":
            item_status = "queued"
        elif item.execution_state == "running":
            item_status = "running"
        elif item.execution_state == "failed" or (
            outcome is not None and outcome.evidence_status == "unresolved"
        ):
            item_status = "failed"
        else:
            item_status = "ready"
        target = json.loads(item.target.attributes["target_json"])
        items.append(
            {
                "item_id": item.target.item_id,
                "attempt_id": item.last_attempt_id,
                "target": {
                    key: target[key] for key in AutoImportTargetView.model_fields
                },
                "status": item_status,
                "evidence_kind": outcome.evidence_status
                if outcome and outcome.evidence_status != "unresolved"
                else None,
                "can_promote": bool(
                    outcome
                    and outcome.promotion_eligible
                    and item.promotion_state != "promoted"
                ),
                "mappings": attempt_view["mappings"] if attempt_view else [],
                "mapping_confirmed": bool(
                    attempt_view and attempt_view["stage"] in {"ready", "promoted"}
                ),
                "error": item.error
                or (
                    outcome.summary
                    if outcome and outcome.evidence_status == "unresolved"
                    else None
                )
                or item.promotion_error,
            }
        )
    failed = review.progress.failed + review.progress.unresolved
    ready = sum(
        bool(
            item.execution_state == "review"
            and item.outcome is not None
            and item.outcome.evidence_status != "unresolved"
            and item.promotion_state != "promoted"
        )
        for item in review.items
    )
    return {
        "batch_id": review.batch.batch_id,
        "status": status,
        "summary": {
            "total": review.progress.total_items,
            "queued": review.progress.pending,
            "running": review.progress.running,
            "ready": ready,
            "measured": review.progress.measured,
            "estimated": review.progress.estimated,
            "failed": failed,
            "retryable_failed": review.progress.failed,
            "promoted": review.progress.promoted,
            "completed": review.progress.completed,
        },
        "items": items,
        "created_at": review.batch.created_at.isoformat(),
        "updated_at": review.batch.updated_at.isoformat(),
    }


def create_auto_import_router(
    store: AtlasStore,
    provider: ResearchProvider | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/atlas/auto-import", tags=["Atlas auto-import"])
    repository = SQLiteAttemptRepository(store)
    missing_path = _missing_path(store)
    writer = AtlasAutoImportPromotionWriter(store, missing_path)
    service = AutoImportResearchService(
        repository,
        provider or PublicResearchProvider(),
        writer,
    )

    async def execute_bulk(request: BulkExecutionRequest) -> BulkImportOutcome:
        target_data = json.loads(request.target.attributes["target_json"])
        target = _place_target(
            store,
            target_data,
            request.target.attributes.get("scope", "shared"),
        )
        attempt = service.create_attempt(target)
        attempt = await asyncio.to_thread(service.research, attempt.attempt_id)
        await asyncio.to_thread(sync_missing_document, store, missing_path)
        if attempt.status == "not_found" or attempt.result_kind is None:
            return BulkImportOutcome(
                attempt_id=attempt.attempt_id,
                evidence_status="unresolved",
                summary=attempt.failure_reason or "No credible distribution found",
                promotion_eligible=False,
                predictor_eligible=False,
                trace_reference=attempt.attempt_id,
            )
        preview = attempt.mapping_preview
        unambiguous = bool(preview) and all(row.proposed_label for row in preview.rows)
        interval = None
        estimate_reason = None
        if attempt.estimate_trace:
            intervals = attempt.estimate_trace.confidence_intervals.values()
            interval = (
                min(value.lower for value in intervals),
                max(value.upper for value in intervals),
            )
            estimate_reason = " ".join(attempt.estimate_trace.calculation)
        return BulkImportOutcome(
            attempt_id=attempt.attempt_id,
            evidence_status=attempt.result_kind,
            summary=(
                "Verified source and mapping ready for review"
                if unambiguous
                else "Mapping contains Unknown values and needs individual review"
            ),
            source_labels=tuple(source.title for source in attempt.sources),
            confidence_interval=interval,
            estimate_reason=estimate_reason,
            promotion_eligible=False,
            predictor_eligible=attempt.result_kind == "measured",
            payload_reference=attempt.attempt_id,
            trace_reference=attempt.attempt_id,
        )

    async def promote_bulk(request: DomainBulkPromotionRequest):
        attempt = service.get_attempt(request.outcome.attempt_id)
        if attempt.status != "ready" or not attempt.mapping_confirmed:
            raise ValueError("Confirm the mapping before promotion")
        _require_shared_licence(attempt)
        promoted = await asyncio.to_thread(
            service.promote,
            attempt.attempt_id,
            PromotionCommand(confirmed=True),
        )
        await asyncio.to_thread(sync_missing_document, store, missing_path)
        return promoted.promotion_id or promoted.attempt_id

    bulk_repository = SQLiteBulkImportRepository(store)
    bulk = BulkAutoImportOrchestrator(
        bulk_repository,
        execute_bulk,
        promote_bulk,
    )
    tasks: set[asyncio.Task] = set()

    def checked(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error
        except (ValueError, ValidationError, json.JSONDecodeError) as error:
            raise HTTPException(422, str(error)) from error

    def launch(coroutine) -> None:
        task = asyncio.create_task(coroutine)
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    async def reconcile_batch(batch_id: str):
        items = await bulk_repository.list_items(batch_id)
        for item in items:
            if item.last_attempt_id is None or item.outcome is None:
                continue
            try:
                attempt = service.get_attempt(item.last_attempt_id)
            except KeyError:
                continue
            promotion_eligible = bool(
                attempt.status in {"ready", "promoted"}
                and attempt.mapping_confirmed
                and attempt.mapped_distribution is not None
            )
            outcome = item.outcome.model_copy(
                update={"promotion_eligible": promotion_eligible}
            )
            changes: dict[str, Any] = {"outcome": outcome}
            if attempt.status == "promoted" and attempt.promotion_id:
                changes.update(
                    {
                        "promotion_state": "promoted",
                        "promotion_receipt": BulkPromotionReceipt(
                            promotion_id=attempt.promotion_id
                        ),
                        "promotion_error": None,
                    }
                )
            updated = item.model_copy(update=changes)
            if updated != item:
                await bulk_repository.save_item(updated)
        return await bulk.refresh(batch_id)

    @router.get("/queue", response_model=AutoImportQueuePageView)
    def queue(
        scope: str = "shared",
        as_of: date | None = None,
        level: str = "all",
        feature_id: str = "",
        search: str = Query("", max_length=200),
        sort: str = "hierarchy_impact",
        priority: str = "primary",
        city_population_threshold: int | None = Query(1_000_000, ge=0),
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=500),
    ):
        if level not in {"all", "region", "country", "city"}:
            raise HTTPException(422, "Unknown hierarchy level")
        if feature_id and feature_id not in FIELDS:
            raise HTTPException(422, "Unknown marginal feature")
        if priority not in {"primary", "lower"}:
            raise HTTPException(422, "Unknown priority cohort")
        threshold = None if city_population_threshold == 0 else city_population_threshold
        result = checked(
            _queue_query,
            store,
            scope,
            as_of.isoformat() if as_of else date.today().isoformat(),
            level,
            feature_id,
            search,
            sort,
            priority,
            threshold,
            page,
            page_size,
        )
        return _queue_response(result, threshold)

    @router.post("/attempts", response_model=AutoImportAttemptView)
    async def create_attempt(
        target: Annotated[str, Form()],
        scope: Annotated[str, Form()],
        urls: Annotated[str, Form()] = "[]",
        pasted_text: Annotated[str, Form()] = "",
        files: Annotated[list[UploadFile] | None, File()] = None,
    ):
        try:
            target_data = json.loads(target)
            place_target = _place_target(store, target_data, scope)
            sources = await _user_sources(urls, pasted_text, files or [])
            attempt = service.create_attempt(place_target, sources)
            attempt = await asyncio.to_thread(service.research, attempt.attempt_id)
            await asyncio.to_thread(sync_missing_document, store, missing_path)
            return _attempt_view(attempt)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error
        except (ValueError, ValidationError, json.JSONDecodeError) as error:
            raise HTTPException(422, str(error)) from error

    @router.get("/attempts/{attempt_id}", response_model=AutoImportAttemptView)
    def attempt(attempt_id: str):
        return _attempt_view(checked(service.get_attempt, attempt_id))

    @router.get("/evidence/{feature_id}", response_model=AutoImportEvidenceView)
    def feature_evidence(
        feature_id: str,
        scope: str = "shared",
        as_of: date | None = None,
    ):
        mapped_fields = {
            "age": ("age_sex",),
            "sex": ("age_sex",),
            "education_isced": ("education",),
        }
        fields = mapped_fields.get(feature_id, (feature_id,))
        cutoff = as_of or date.today()
        allowed_scopes = {"shared", scope}
        attempts = [
            attempt
            for attempt in repository.list()
            if attempt.status == "promoted"
            and attempt.target.scope in allowed_scopes
            and attempt.target.feature_id in fields
            and all(
                source.observation_date is not None
                and source.published_date is not None
                and source.observation_date <= cutoff
                and source.published_date <= cutoff
                for source in attempt.sources
                if source.candidate_id in attempt.selected_source_ids
            )
        ]
        return {"attempts": [_attempt_view(attempt) for attempt in attempts]}

    @router.post("/attempts/{attempt_id}/research", response_model=AutoImportAttemptView)
    async def research(attempt_id: str):
        try:
            result = await asyncio.to_thread(service.research, attempt_id)
            await asyncio.to_thread(sync_missing_document, store, missing_path)
            return _attempt_view(result)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @router.post("/attempts/{attempt_id}/mapping", response_model=AutoImportAttemptView)
    def confirm_mapping(attempt_id: str, request: AutoImportMappingReview):
        confirmation = MappingConfirmation(
            confirmed=request.reviewed,
            mappings=tuple(
                ConfirmedLabelMapping(
                    source_label=mapping.column,
                    target_label=mapping.target,
                )
                for mapping in request.mappings
            ),
        )
        return _attempt_view(checked(service.confirm_mapping, attempt_id, confirmation))

    @router.post("/attempts/{attempt_id}/promote", response_model=AutoImportAttemptView)
    async def promote(attempt_id: str, request: AutoImportPromotionRequest):
        if not request.redistribution_confirmed:
            raise HTTPException(422, "Confirm redistribution rights before promotion")
        try:
            _require_shared_licence(service.get_attempt(attempt_id))
            result = await asyncio.to_thread(
                service.promote,
                attempt_id,
                PromotionCommand(confirmed=True),
            )
            await asyncio.to_thread(sync_missing_document, store, missing_path)
            return _attempt_view(result)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    async def selected_targets(request: AutoImportBatchRequest) -> list[BulkImportTarget]:
        if isinstance(request.selection, AutoImportExplicitSelection):
            targets = []
            for item_id in request.selection.item_ids:
                parts = item_id.split("|", 2)
                if len(parts) != 3:
                    raise ValueError(f"Invalid queue item {item_id}")
                level, place_id, feature_id = parts
                page = _queue_query(
                    store,
                    request.scope,
                    request.as_of,
                    level,
                    feature_id,
                    place_id,
                    "hierarchy_impact",
                    "primary",
                    None,
                    1,
                    500,
                )
                item = next((value for value in page.items if value.target_id == item_id), None)
                if item is None:
                    raise ValueError(f"Queue item is no longer missing: {item_id}")
                targets.append(
                    _bulk_target(_queue_item_view(item, None, page.as_of), request.scope)
                )
            return targets
        query = request.selection.query
        threshold_value = int(query.get("city_population_threshold", 1_000_000))
        threshold = None if threshold_value == 0 else threshold_value
        page_number = 1
        targets = []
        excluded = set(request.selection.excluded_item_ids)
        while True:
            result = _queue_query(
                store,
                request.scope,
                request.as_of,
                str(query.get("level", "all")),
                str(query.get("feature_id", "")),
                str(query.get("search", "")),
                str(query.get("sort", "hierarchy_impact")),
                str(query.get("priority", "primary")),
                threshold,
                page_number,
                500,
            )
            targets.extend(
                _bulk_target(_queue_item_view(item, threshold, result.as_of), request.scope)
                for item in result.items
                if item.target_id not in excluded
            )
            if page_number * 500 >= result.filtered_count:
                break
            page_number += 1
        return targets

    @router.post("/batches", response_model=AutoImportBatchView)
    async def create_batch(request: AutoImportBatchRequest):
        try:
            candidates = await selected_targets(request)
            review = await bulk.create_batch(
                candidates,
                BulkImportSelection(
                    levels=("region", "country", "city"),
                    city_cohort="all",
                ),
                max_concurrency=request.concurrency,
            )
            launch(bulk.run(review.batch.batch_id))
            await asyncio.sleep(0)
            return _batch_view(await bulk.review(review.batch.batch_id), service)
        except (ValueError, ValidationError) as error:
            raise HTTPException(422, str(error)) from error

    @router.get("/batches/latest", response_model=AutoImportBatchView | None)
    async def latest_batch(scope: str = "shared"):
        batches = await bulk_repository.list_batches(scope)
        if not batches:
            return None
        review = await reconcile_batch(batches[0].batch_id)
        return _batch_view(review, service)

    @router.get("/batches/{batch_id}", response_model=AutoImportBatchView)
    async def batch(batch_id: str):
        try:
            return _batch_view(await reconcile_batch(batch_id), service)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error

    @router.post("/batches/{batch_id}/retry", response_model=AutoImportBatchView)
    async def retry_batch(batch_id: str):
        try:
            launch(bulk.resume(batch_id))
            await asyncio.sleep(0)
            return _batch_view(await bulk.review(batch_id), service)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error

    @router.post("/batches/{batch_id}/promote", response_model=AutoImportBatchView)
    async def promote_batch(batch_id: str, request: AutoImportBatchPromotionRequest):
        if not request.mapping_confirmed:
            raise HTTPException(422, "Confirm the reviewed mappings before promotion")
        if not request.redistribution_confirmed:
            raise HTTPException(422, "Confirm redistribution rights before promotion")
        try:
            review = await reconcile_batch(batch_id)
            items_by_id = {item.target.item_id: item for item in review.items}
            if request.mode == "selected":
                unknown = [item_id for item_id in request.item_ids if item_id not in items_by_id]
                if unknown:
                    raise ValueError(f"Unknown bulk item IDs: {', '.join(unknown)}")
                candidates = [items_by_id[item_id] for item_id in request.item_ids]
            else:
                candidates = [
                    item
                    for item in review.items
                    if item.execution_state == "review"
                    and item.outcome is not None
                    and item.outcome.evidence_status != "unresolved"
                    and item.promotion_state != "promoted"
                ]
            incomplete = []
            for item in candidates:
                if item.last_attempt_id is None:
                    incomplete.append(item.target.item_id)
                    continue
                attempt = service.get_attempt(item.last_attempt_id)
                if attempt.status == "awaiting_mapping_confirmation":
                    preview = attempt.mapping_preview
                    if preview is None or any(
                        row.proposed_label is None for row in preview.rows
                    ):
                        incomplete.append(item.target.item_id)
                        continue
                    service.confirm_proposed_mapping(attempt.attempt_id)
                elif attempt.status not in {"ready", "promoted"}:
                    incomplete.append(item.target.item_id)
            if request.mode == "selected" and incomplete:
                raise ValueError(
                    "Review Unknown mappings before promotion: " + ", ".join(incomplete)
                )
            review = await reconcile_batch(batch_id)
            promotable_ids = tuple(
                item.target.item_id
                for item in review.items
                if item.target.item_id in {candidate.target.item_id for candidate in candidates}
                and item.outcome is not None
                and item.outcome.promotion_eligible
                and item.promotion_state != "promoted"
            )
            if not promotable_ids:
                return _batch_view(review, service)
            selection = BulkPromotionSelection(item_ids=promotable_ids)
            promoted = await bulk.promote(batch_id, selection)
            return _batch_view(promoted, service)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    return router
