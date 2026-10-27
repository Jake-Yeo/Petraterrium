import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    BackgroundTasks,
    Body,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .atlas.contracts import ImportMetadata, ImportPreview
from .atlas.database import FIELDS, AtlasStore
from .atlas.feature_catalog import create_feature_catalog_router
from .atlas.feature_queries import create_feature_query_router
from .atlas.features import canonical_feature_registry
from .atlas.formats import MAX_BYTES
from .atlas.imports import stage_import
from .atlas.organizer import overview
from .atlas.routes import create_atlas_router
from .atlas.source_adapters import source_rows
from .atlas.sources import SOURCE_BY_ID
from .contracts import (
    AgentDetail,
    AgentPointList,
    Catalog,
    DecisionGraph,
    DecisionGraphFilter,
    DSLRender,
    PlaceDetail,
    RunConfig,
    RunCreated,
    RunDetail,
    RunList,
    StoryDetail,
    StoryList,
)
from .data import COUNTRIES, DATA_VERSION
from .decision_graph import run_decision_graph, static_decision_graph
from .dsl import DSLConfig, load_dsl, render_plain_language, render_sliders, validate_dsl
from .output_views import (
    agent_detail,
    agent_points,
    find_agent,
    place_detail,
    story_detail,
)
from .recorder import RunRecord, RunStore
from .runtime import resolve_runtime
from .service import RunService
from .versions import ENGINE_VERSION


def create_app(store: RunStore | None = None, atlas_path=None) -> FastAPI:
    run_store = store or RunStore()
    service = RunService(run_store)
    application = FastAPI(title="Petraterrium · DSL simulation framework", version="0.2.0")
    application.state.store = run_store
    application.state.service = service
    atlas_store = AtlasStore(atlas_path)
    application.state.atlas = atlas_store
    application.include_router(create_atlas_router(atlas_store, run_store))
    application.include_router(
        create_feature_catalog_router(atlas_store, canonical_feature_registry)
    )
    application.include_router(create_feature_query_router(atlas_store))
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )

    def require_run(run_id: str) -> RunRecord:
        record = run_store.get(run_id)
        if record is None:
            raise HTTPException(404, "Run not found; the in-memory store resets on server restart")
        return record

    def newest_record(predicate) -> RunRecord:
        for record in reversed(list(run_store.records.values())):
            if predicate(record):
                return record
        raise HTTPException(404, "No recorded run contains this resource")

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "data": "FAKE smoke inputs available"}

    @application.get("/catalog", response_model=Catalog)
    def catalog() -> Catalog:
        return Catalog(
            countries=list(COUNTRIES),
            engine_version=ENGINE_VERSION,
            data_version=DATA_VERSION,
            notice=(
                "The generic DSL engine is operational. The bundled smoke population and "
                "compatibility coefficients are FAKE and unfitted."
            ),
        )

    @application.get("/dsl/schema")
    def dsl_schema() -> dict[str, Any]:
        return DSLConfig.model_json_schema(mode="serialization")

    @application.get("/dsl/smoke")
    def smoke_dsl() -> dict[str, Any]:
        path = Path(__file__).resolve().parents[2] / "shared" / "dsl-schema" / "smoke-spread.json"
        return json.loads(path.read_text())

    @application.post("/dsl/validate")
    def validate_dsl_route(config: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
        return validate_dsl(config).model_dump()

    @application.post("/dsl/render", response_model=DSLRender)
    def render_dsl_route(config: Annotated[dict[str, Any], Body()]) -> DSLRender:
        result = validate_dsl(config)
        if not result.valid:
            raise HTTPException(422, result.model_dump())
        dsl = load_dsl(config)
        return DSLRender(
            plain_language=render_plain_language(dsl),
            sliders=[slider.model_dump() for slider in render_sliders(dsl)],
        )

    @application.post("/dsl/decision-graph", response_model=DecisionGraph)
    def static_graph_route(
        config: Annotated[dict[str, Any], Body()],
        state: str = "",
        segment: str = "",
        place: str = "",
        role: str = "",
    ) -> DecisionGraph:
        result = validate_dsl(config)
        if not result.valid:
            raise HTTPException(422, result.model_dump())
        return static_decision_graph(
            load_dsl(config),
            DecisionGraphFilter(state=state, segment=segment, place=place, role=role),
        )

    @application.post("/runs", status_code=202, response_model=RunCreated)
    async def create_run(config: RunConfig, background: BackgroundTasks) -> RunCreated:
        try:
            record, cached = service.create(config)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not cached:
            background.add_task(service.execute, record)
        return RunCreated(**record.detail().model_dump(), cached=cached)

    @application.get("/runs", response_model=RunList)
    def list_runs() -> RunList:
        return RunList(runs=[r.summary() for r in reversed(list(run_store.records.values()))])

    @application.get("/runs/{run_id}/agents", response_model=AgentPointList)
    def get_run_agents(
        run_id: str,
        place: str,
        day: int | None = Query(default=None, ge=0),
        state: str = "",
        action: str = "",
        limit: int = Query(default=5000, ge=1, le=10000),
        offset: int = Query(default=0, ge=0),
    ) -> AgentPointList:
        try:
            return agent_points(require_run(run_id), place, day, state, action, limit, offset)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @application.get("/runs/{run_id}/stories", response_model=StoryList)
    def get_run_stories(run_id: str) -> StoryList:
        return StoryList(stories=list(require_run(run_id).stories))

    @application.get("/runs/{run_id}/decision-graph", response_model=DecisionGraph)
    def get_run_decision_graph(
        run_id: str,
        state: str = "",
        segment: str = "",
        place: str = "",
        role: str = "",
        tick_start: int | None = Query(default=None, ge=0),
        tick_end: int | None = Query(default=None, ge=0),
        agent_id: str | None = None,
    ) -> DecisionGraph:
        record = require_run(run_id)
        runtime = resolve_runtime(record.config)
        return run_decision_graph(
            runtime.dsl,
            record.action_logs,
            run_id,
            DecisionGraphFilter(
                state=state,
                segment=segment,
                place=place,
                role=role,
                tick_start=tick_start,
                tick_end=tick_end,
            ),
            agent_id,
        )

    @application.get("/runs/{run_id}", response_model=RunDetail)
    def get_run(run_id: str) -> RunDetail:
        return require_run(run_id).detail()

    @application.delete("/runs/{run_id}", status_code=204)
    async def delete_run(run_id: str) -> Response:
        await service.delete(require_run(run_id))
        return Response(status_code=204)

    @application.get("/runs/{run_id}/stream")
    async def stream_run(
        run_id: str, request: Request, after: int = Query(default=0, ge=0)
    ) -> StreamingResponse:
        record = require_run(run_id)
        header = request.headers.get("last-event-id")
        if header is not None:
            try:
                after = int(header)
            except ValueError as exc:
                raise HTTPException(422, "Last-Event-ID must be a nonnegative integer") from exc
        if after < 0 or after > len(record.events):
            raise HTTPException(422, "Sequence ID is outside this run's recorded events")

        async def events():
            yield "retry: 1500\n\n"
            async for event in record.follow(after):
                if await request.is_disconnected():
                    return
                yield event.as_sse() if event else ": heartbeat\n\n"

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @application.get("/agents/{agent_id}", response_model=AgentDetail)
    def get_agent(agent_id: str, run_id: str | None = None) -> AgentDetail:
        record = (
            require_run(run_id)
            if run_id
            else newest_record(lambda candidate: find_agent(candidate, agent_id) is not None)
        )
        agent = find_agent(record, agent_id)
        if agent is None:
            raise HTTPException(404, "Synthetic agent not found in this run")
        return agent_detail(record, agent)

    @application.get("/places/{place_id}", response_model=PlaceDetail)
    def get_place(place_id: str, run_id: str | None = None) -> PlaceDetail:
        record = (
            require_run(run_id)
            if run_id
            else newest_record(
                lambda candidate: any(
                    place.country == place_id
                    for snapshot in candidate.snapshots[-1:]
                    for place in snapshot.places
                )
            )
        )
        try:
            return place_detail(record, place_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(404, "Place not found in recorded output") from exc

    @application.get("/stories/{story_id}", response_model=StoryDetail)
    def get_story(story_id: str, run_id: str | None = None) -> StoryDetail:
        record = (
            require_run(run_id)
            if run_id
            else newest_record(
                lambda candidate: any(story.story_id == story_id for story in candidate.stories)
            )
        )
        try:
            return story_detail(record, story_id)
        except (KeyError, ValueError) as exc:
            raise HTTPException(404, "Story not found in recorded output") from exc

    @application.get("/data/coverage")
    def data_coverage(field: str, scope: str = "shared", as_of: date | None = None):
        if field not in FIELDS:
            raise HTTPException(422, "Unknown marginal field")
        report = overview(
            atlas_store,
            scope=scope,
            as_of=as_of.isoformat() if as_of else None,
            page=1,
            page_size=1,
        )
        return next(item for item in report.summary.fields if item.field == field)

    @application.post("/data/import", response_model=ImportPreview)
    async def data_import(
        file: Annotated[UploadFile, File()],
        metadata: Annotated[str, Form()],
        use_llm: Annotated[bool, Form()] = True,
    ) -> ImportPreview:
        try:
            parsed = ImportMetadata.model_validate_json(metadata)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        require_run(parsed.run_id)
        if parsed.source_id and parsed.source_id not in SOURCE_BY_ID:
            raise HTTPException(422, "Unknown source loader")
        contents = await file.read(MAX_BYTES + 1)
        if len(contents) > MAX_BYTES:
            raise HTTPException(413, "Upload exceeds configured byte limit")
        filename = Path(file.filename or "upload").name
        try:
            rows, parsed = await asyncio.to_thread(
                source_rows, atlas_store, filename, contents, parsed
            )
            return await asyncio.to_thread(
                stage_import, atlas_store, filename, parsed, rows, use_llm
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    return application


app = create_app()
