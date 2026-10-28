import asyncio
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import (
    BackgroundTasks,
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

from .ai_feature_routes import create_ai_feature_router
from .ai_settings import AISettingsStore, create_ai_settings_router, default_ai_settings_store
from .atlas.auto_import_provider import PublicResearchProvider
from .atlas.auto_import_routes import create_auto_import_router
from .atlas.contracts import ImportMetadata, ImportPreview
from .atlas.database import FIELDS, AtlasStore
from .atlas.evidence_receipts import AtlasEvidenceReceiptRegistry
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
    PlaceDetail,
    RunConfig,
    RunCreated,
    RunDetail,
    RunList,
    StoryDetail,
    StoryList,
)
from .data import COUNTRIES, DATA_VERSION
from .decision_graph import run_decision_graph
from .llm_gateway import AIProviderError, SelectedAIProvider
from .markov_builder import (
    MarkovProbabilityResearchService,
    PublicTransitionResearchProvider,
    create_markov_builder_router,
)
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
from .simulation.agent_type_routes import create_agent_type_router
from .simulation.coefficient_promotions import create_coefficient_promotion_router
from .simulation.decision_evidence_routes import create_decision_evidence_router
from .simulation.default_dsl import DefaultDslService, create_default_dsl_router
from .simulation.default_pipeline_bootstrap import build_default_pipeline_service
from .simulation.default_pipeline_routes import create_default_pipeline_router
from .simulation.default_pipeline_service import SimulationRegistryDefaultStateAdapter
from .simulation.editable_dsl_routes import create_editable_dsl_router
from .simulation.editable_dsl_service import EditableDslService
from .simulation.evidence_guard import require_trusted_simulation_evidence
from .simulation.interaction_program_routes import create_interaction_program_router
from .simulation.interaction_trees import (
    InteractionTreeRegistry,
    create_interaction_tree_router,
)
from .simulation.interactions import InteractionRunRegistry, create_interaction_router
from .simulation.locations import LocationRunRegistry, create_location_router
from .simulation.mobility_routes import create_mobility_router
from .simulation.population_routes import create_population_router
from .simulation.registry_store import SimulationRegistryStore
from .simulation.routines_routes import create_routine_router
from .simulation.run_persistence import SimulationRunRecorder
from .simulation.run_preparation import LazyRustCoreClient, prepare_registry_run
from .simulation.run_preview import (
    SimulationRunPreviewService,
    create_simulation_run_preview_router,
)
from .simulation.run_routes import create_simulation_run_router
from .simulation.run_service import SimulationRunService
from .simulation.tree_routes import create_decision_tree_router
from .text_dsl import TextDslService, create_text_dsl_router
from .versions import ENGINE_VERSION


def create_app(
    store: RunStore | None = None,
    atlas_path=None,
    research_provider=None,
    ai_settings_store: AISettingsStore | None = None,
    ai_provider=None,
    markov_research_provider=None,
    simulation_registry_store: SimulationRegistryStore | None = None,
    simulation_run_service: SimulationRunService | None = None,
) -> FastAPI:
    run_store = store or RunStore()
    service = RunService(run_store)
    application = FastAPI(title="Petraterrium · Simulation framework", version="0.2.0")
    application.state.store = run_store
    application.state.service = service
    atlas_store = AtlasStore(atlas_path)
    evidence_receipts = AtlasEvidenceReceiptRegistry(atlas_store)
    settings_store = ai_settings_store or default_ai_settings_store()
    selected_ai = ai_provider or SelectedAIProvider(settings_store)
    configured_research_provider = research_provider or PublicResearchProvider(
        ai_provider=selected_ai
    )
    transition_research_provider = markov_research_provider or PublicTransitionResearchProvider(
        configured_research_provider
    )
    markov_probability_research = MarkovProbabilityResearchService(
        transition_research_provider,
        selected_ai,
    )
    simulation_registry = simulation_registry_store or SimulationRegistryStore()
    rust_core = LazyRustCoreClient()
    text_dsl = TextDslService(rust=rust_core)
    default_dsl = DefaultDslService(simulation_registry)
    default_dsl.ensure()
    default_pipeline = build_default_pipeline_service(simulation_registry)

    def select_cached_pipeline_default(sections, version):
        prior_receipt = simulation_registry.default_dsl_receipt()
        prior_managed_sections = (
            set(prior_receipt.managed_sections) if prior_receipt is not None else set()
        )
        default_dsl.set_cached_pipeline_default(sections, version)
        for section in tuple(sections):
            sections[section] = default_dsl.package.content[section]
        installed_payload = simulation_registry.payload_snapshot()
        missing_sections = {
            section: default_dsl.package.content[section]
            for section in default_dsl.package.receipt.managed_sections
            if section not in installed_payload and section not in prior_managed_sections
        }
        simulation_registry.restore_default_dsl_sections(
            missing_sections,
            default_dsl.package.receipt.model_dump(mode="json"),
        )

    active_pipeline_snapshot = default_pipeline.active_snapshot()
    if active_pipeline_snapshot is not None:
        active_pipeline_run, active_pipeline_sections = active_pipeline_snapshot
        select_cached_pipeline_default(
            active_pipeline_sections,
            active_pipeline_run.version,
        )
    default_pipeline.add_restore_hook(select_cached_pipeline_default)
    try:
        default_pipeline.restore_active()
        default_pipeline_restore_error = None
    except (KeyError, ValueError) as error:
        default_pipeline_restore_error = str(error)
    editable_dsl = EditableDslService(simulation_registry)
    runtime_simulation_registry = editable_dsl.registry_overlay()
    default_pipeline.state_provider = SimulationRegistryDefaultStateAdapter(
        runtime_simulation_registry
    )
    interaction_registry = InteractionRunRegistry()
    location_registry = LocationRunRegistry()
    interaction_tree_registry = InteractionTreeRegistry(
        simulation_registry.interaction_trees(),
        simulation_registry.save_interaction_tree,
        evidence_receipts,
    )
    default_dsl.add_reset_hook(
        lambda: interaction_tree_registry.reload(simulation_registry.interaction_trees())
    )
    default_dsl.add_reset_hook(default_pipeline.restore_active)
    default_dsl.add_reset_hook(editable_dsl.clear_active_overlay)
    default_pipeline.add_restore_hook(
        lambda _sections, _version: editable_dsl.clear_active_overlay()
    )
    def prepare_simulation(config):
        require_trusted_simulation_evidence(
            runtime_simulation_registry,
            evidence_receipts,
            interaction_tree_registry,
        )
        return prepare_registry_run(
            runtime_simulation_registry,
            config,
            evidence_receipts=evidence_receipts,
        )

    simulation_runs = simulation_run_service or SimulationRunService(
        prepare_simulation,
        rust_core,
        record_interactions=interaction_registry.record,
        record_locations=location_registry.record,
        persistence=SimulationRunRecorder(),
    )
    simulation_run_previews = SimulationRunPreviewService(prepare_simulation)
    application.state.atlas = atlas_store
    application.state.ai_settings = settings_store
    application.state.ai_provider = selected_ai
    application.state.markov_probability_research = markov_probability_research
    application.state.simulation_registry = simulation_registry
    application.state.default_dsl = default_dsl
    application.state.default_pipeline = default_pipeline
    application.state.default_pipeline_restore_error = default_pipeline_restore_error
    application.state.editable_dsl = editable_dsl
    application.state.simulation_runs = simulation_runs
    application.state.simulation_run_previews = simulation_run_previews
    application.state.simulation_interactions = interaction_registry
    application.state.simulation_locations = location_registry
    application.state.text_dsl = text_dsl
    application.state.simulation_interaction_trees = interaction_tree_registry
    application.include_router(create_atlas_router(atlas_store, run_store, selected_ai))
    application.include_router(
        create_auto_import_router(
            atlas_store,
            configured_research_provider,
            selected_ai,
        )
    )
    application.include_router(
        create_feature_catalog_router(atlas_store, canonical_feature_registry)
    )
    application.include_router(create_feature_query_router(atlas_store))
    application.include_router(
        create_markov_builder_router(
            persist_chain=simulation_registry.save_confirmed_chain,
            ai_provider=selected_ai,
            probability_research=markov_probability_research,
        )
    )
    application.include_router(
        create_agent_type_router(simulation_registry, selected_ai, atlas_store)
    )
    application.include_router(create_default_dsl_router(default_dsl))
    application.include_router(create_default_pipeline_router(default_pipeline))
    application.include_router(create_editable_dsl_router(editable_dsl))
    application.include_router(create_text_dsl_router(text_dsl))
    application.include_router(create_population_router(simulation_registry, atlas_store))
    application.include_router(create_decision_tree_router(runtime_simulation_registry))
    application.include_router(create_routine_router(simulation_registry))
    application.include_router(create_mobility_router(simulation_registry))
    application.include_router(
        create_decision_evidence_router(simulation_registry, evidence_receipts)
    )
    application.include_router(
        create_coefficient_promotion_router(simulation_registry, evidence_receipts)
    )
    application.include_router(
        create_interaction_program_router(simulation_registry, evidence_receipts)
    )
    application.include_router(create_simulation_run_router(simulation_runs))
    application.include_router(create_simulation_run_preview_router(simulation_run_previews))
    application.include_router(create_interaction_router(interaction_registry))
    application.include_router(create_location_router(location_registry))
    application.include_router(
        create_interaction_tree_router(
            interaction_tree_registry,
            rust_core.run_interaction_tree,
        )
    )
    application.include_router(create_ai_settings_router(settings_store, lambda _: selected_ai))
    application.include_router(create_ai_feature_router(selected_ai))
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )
    application.router.add_event_handler("shutdown", simulation_runs.shutdown)

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
                "The generic simulation engine is operational. The bundled smoke population and "
                "compatibility coefficients are FAKE and unfitted."
            ),
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

    @application.get(
        "/simulation/recorded-runs/{run_id}/graph",
        response_model=DecisionGraph,
    )
    def get_recorded_action_graph(
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
        return run_decision_graph(
            resolve_runtime(record.config).dsl,
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
                stage_import,
                atlas_store,
                filename,
                parsed,
                rows,
                use_llm,
                selected_ai,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except AIProviderError as exc:
            raise HTTPException(502, str(exc)) from exc

    return application


def create_dsl_demo_app() -> FastAPI:
    application = FastAPI(title="Petraterrium · Rust DSL demo", version="0.3.0")
    rust_core = LazyRustCoreClient()
    text_dsl = TextDslService(rust=rust_core)
    application.state.text_dsl = text_dsl
    application.include_router(create_text_dsl_router(text_dsl))
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type"],
    )

    @application.get("/health")
    def dsl_health() -> dict[str, str]:
        return {"status": "ok", "engine": "rust_text_dsl"}

    return application


app = create_dsl_demo_app()
