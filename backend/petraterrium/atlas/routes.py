import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import ValidationError

from ..llm_gateway import AIProviderError
from .backbone import load_cities500
from .contracts import (
    AtlasOverview,
    AtlasScope,
    AtlasScopes,
    Backbone,
    ChoiceEvidenceCatalog,
    CityDetail,
    HierarchyOverview,
    ImportCommit,
    ImportHistory,
    ImportMetadata,
    ImportPreview,
    ImportVersion,
    MappingConfirmation,
    Promotion,
    RegistrySource,
    SourceCatalog,
    SourceFetch,
    UniversalFeatureOverview,
    ValidationReport,
)
from .database import FIELDS, AtlasStore
from .evidence_views import choice_evidence_catalog, universal_feature_overview
from .formats import MAX_BYTES
from .hierarchy import hierarchy_overview
from .hierarchy_queue import HierarchyBrowserPage, hierarchy_browser_page
from .imports import (
    commit_import,
    import_history,
    promote_import,
    reopen_draft,
    stage_import,
    validate_import,
)
from .organizer import city_detail, overview
from .source_adapters import source_rows
from .sources import SOURCE_BY_ID, SOURCES, fetch_source


def create_atlas_router(store: AtlasStore, run_store, ai_provider=None) -> APIRouter:
    router = APIRouter(prefix="/atlas", tags=["Data atlas"])

    def require_run(run_id: str):
        if run_store.get(run_id) is None:
            raise HTTPException(
                404, "Choose an existing run before uploading; data defaults to that run"
            )

    def checked(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except (ValueError, ValidationError, json.JSONDecodeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                502, "Source download failed; check source access or upload an authorized export"
            ) from exc
        except AIProviderError as exc:
            raise HTTPException(502, str(exc)) from exc

    @router.get("/overview", response_model=AtlasOverview)
    def get_overview(
        scope: str = "shared",
        as_of: date | None = None,
        search: str = Query("", max_length=120),
        country: str = Query("", max_length=3),
        tier: str = "",
        status: str = "",
        missing_field: str = "",
        page: int = Query(1, ge=1),
        page_size: int = Query(25, ge=1, le=100),
    ):
        if tier and tier not in ("simulated", "disaggregated"):
            raise HTTPException(422, "Invalid simulation tier")
        if status and status not in (
            "present",
            "inherited",
            "imputed",
            "estimated",
            "missing",
        ):
            raise HTTPException(422, "Invalid coverage status")
        if missing_field and missing_field not in FIELDS:
            raise HTTPException(422, "Unknown marginal field")
        return overview(
            store,
            scope,
            as_of.isoformat() if as_of else None,
            search,
            country,
            tier,
            status,
            missing_field,
            page,
            page_size,
        )

    @router.get("/cities/{geonameid}", response_model=CityDetail)
    def get_city(geonameid: int, scope: str = "shared", as_of: date | None = None):
        return checked(city_detail, store, geonameid, scope, as_of.isoformat() if as_of else None)

    @router.post("/backbone", response_model=Backbone)
    def load_backbone():
        return checked(load_cities500, store)

    @router.get("/sources", response_model=SourceCatalog)
    def get_sources():
        with store.connection() as connection:
            registry_sources = [
                RegistrySource.model_validate_json(row["record_json"])
                for row in connection.execute(
                    """SELECT record_json FROM registry_source_inventory
                    ORDER BY scope_order,level,source_id"""
                )
            ]
        return SourceCatalog(
            sources=SOURCES,
            llm_available=ai_provider is not None,
            registry_sources=registry_sources,
        )

    @router.get("/features", response_model=UniversalFeatureOverview)
    def features():
        return universal_feature_overview()

    @router.get("/hierarchy", response_model=HierarchyOverview)
    def hierarchy(scope: str = "shared", as_of: date | None = None):
        return hierarchy_overview(
            store,
            scope,
            as_of.isoformat() if as_of else None,
        )

    @router.get("/hierarchy-browser", response_model=HierarchyBrowserPage)
    def hierarchy_browser(
        scope: str = "shared",
        as_of: date | None = None,
        level: str = "region",
        parent_id: str | None = None,
        search: str = Query("", max_length=120),
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=100),
        queue_limit: int = Query(20, ge=1, le=100),
    ):
        return checked(
            hierarchy_browser_page,
            store,
            scope,
            as_of.isoformat() if as_of else None,
            level,
            parent_id,
            search,
            page,
            page_size,
            queue_limit,
            FIELDS,
        )

    @router.get("/choice-evidence", response_model=ChoiceEvidenceCatalog)
    def choices():
        return choice_evidence_catalog()

    @router.get("/scopes", response_model=AtlasScopes)
    def scopes():
        values = {
            record.run_id: AtlasScope(
                run_id=record.run_id, label=f"Run #{record.config.seed}", run_available=True
            )
            for record in run_store.records.values()
        }
        with store.connection() as conn:
            for row in conn.execute("SELECT DISTINCT scope FROM imports WHERE scope!='shared'"):
                identity = row["scope"]
                values.setdefault(
                    identity,
                    AtlasScope(
                        run_id=identity, label="Archived scope " + identity[:8], run_available=False
                    ),
                )
        return AtlasScopes(scopes=list(values.values()))

    @router.get("/imports/{import_id}", response_model=ImportPreview)
    def get_draft(import_id: str, scope: str):
        return checked(reopen_draft, store, import_id, scope)

    @router.post("/imports/preview", response_model=ImportPreview)
    async def preview(
        file: Annotated[UploadFile, File()],
        metadata: Annotated[str, Form()],
        use_llm: Annotated[bool, Form()] = True,
    ):
        parsed = checked(ImportMetadata.model_validate_json, metadata)
        require_run(parsed.run_id)
        contents = await file.read(MAX_BYTES + 1)
        if len(contents) > MAX_BYTES:
            raise HTTPException(413, "Upload exceeds configured byte limit")
        filename = Path(file.filename or "upload").name
        if parsed.source_id and parsed.source_id not in SOURCE_BY_ID:
            raise HTTPException(422, "Unknown source loader")
        rows, parsed = await asyncio.to_thread(
            checked, source_rows, store, filename, contents, parsed
        )
        return await asyncio.to_thread(
            checked, stage_import, store, filename, parsed, rows, use_llm, ai_provider
        )

    @router.post("/sources/{source_id}/fetch", response_model=ImportPreview)
    def load_source(source_id: str, request: SourceFetch):
        require_run(request.metadata.run_id)
        if source_id not in SOURCE_BY_ID:
            raise HTTPException(404, "Unknown source loader")
        filename, contents = checked(fetch_source, source_id, request.url, request.access_confirmed)
        metadata = request.metadata.model_copy(
            update={"source_id": source_id, "source": SOURCE_BY_ID[source_id].name}
        )
        rows, metadata = checked(source_rows, store, filename, contents, metadata)
        return checked(stage_import, store, filename, metadata, rows, True, ai_provider)

    @router.post("/imports/{import_id}/validate", response_model=ValidationReport)
    def validate(import_id: str, request: MappingConfirmation, scope: str):
        return checked(validate_import, store, import_id, scope, request)

    @router.post("/imports/{import_id}/commit", response_model=ImportVersion)
    def commit(import_id: str, request: ImportCommit, scope: str):
        return checked(commit_import, store, import_id, scope, request)

    @router.post("/imports/{import_id}/promote", response_model=ImportVersion)
    def promote(import_id: str, request: Promotion, scope: str):
        return checked(promote_import, store, import_id, scope, request)

    @router.get("/imports", response_model=ImportHistory)
    def history(scope: str = "shared"):
        return import_history(store, scope)

    return router
