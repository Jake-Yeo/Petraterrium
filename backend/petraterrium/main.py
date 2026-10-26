from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .atlas.database import AtlasStore
from .atlas.routes import create_atlas_router
from .contracts import Catalog, RunConfig, RunCreated, RunDetail, RunList
from .data import COUNTRIES, DATA_VERSION
from .recorder import RunRecord, RunStore
from .service import RunService
from .versions import ENGINE_VERSION


def create_app(store: RunStore | None = None, atlas_path=None) -> FastAPI:
    run_store = store or RunStore()
    service = RunService(run_store)
    application = FastAPI(title="Petraterrium · FAKE data scaffold", version="0.1.0")
    application.state.store = run_store
    application.state.service = service
    atlas_store = AtlasStore(atlas_path)
    application.state.atlas = atlas_store
    application.include_router(create_atlas_router(atlas_store, run_store))
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )

    def require_run(run_id: str) -> RunRecord:
        record = run_store.get(run_id)
        if record is None:
            raise HTTPException(404, "Run not found; the in-memory store resets on server restart")
        return record

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "data": "FAKE"}

    @application.get("/catalog", response_model=Catalog)
    def catalog() -> Catalog:
        return Catalog(
            countries=list(COUNTRIES),
            engine_version=ENGINE_VERSION,
            data_version=DATA_VERSION,
            notice=(
                "FAKE populations and unfitted placeholder SEIR. "
                "Demonstration only; not a forecast."
            ),
        )

    @application.post("/runs", status_code=202, response_model=RunCreated)
    async def create_run(config: RunConfig, background: BackgroundTasks) -> RunCreated:
        record, cached = service.create(config)
        if not cached:
            background.add_task(service.execute, record)
        return RunCreated(**record.detail().model_dump(), cached=cached)

    @application.get("/runs", response_model=RunList)
    def list_runs() -> RunList:
        return RunList(runs=[r.summary() for r in reversed(list(run_store.records.values()))])

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

    return application


app = create_app()
