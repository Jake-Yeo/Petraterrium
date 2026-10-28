from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from ..atlas.database import AtlasStore
from ..atlas.feature_queries import FeatureQueryService, PlaceOptions
from .agent_state import (
    AgentStateSystemView,
    core_agent_state_catalog,
    relationship_state_catalog,
)
from .atlas_population import (
    AtlasPopulationMaterializer,
    AtlasPopulationRequest,
    AtlasPopulationResult,
)
from .initial_agents import (
    DecisionTreeLink,
    InitialAgentCatalog,
    InitialAgentDetail,
    InitialAgentPage,
    InitialAgentQuery,
    RoutineLink,
)
from .interactions import RelationshipKindEvidence
from .population_generation import (
    InitialPopulationMaterialization,
    InitialPopulationRequest,
    InitialPopulationValidation,
    InitialPopulationValidationError,
    materialize_initial_population,
    validate_population_request,
)
from .registry_store import SimulationRegistryStore
from .routines import resolve_routines


class PopulationRouteModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InitialPopulationStatus(PopulationRouteModel):
    configured: bool
    population_id: str | None = None
    version: str | None = None
    seed: int | None = None
    agent_count: int = Field(default=0, ge=0)
    input_hash: str | None = None
    agent_type_mix: dict[str, float] = Field(default_factory=dict)


def _population_type_mix(materialization: InitialPopulationMaterialization) -> dict[str, float]:
    counts: dict[str, int] = {}
    for agent in materialization.population.agents:
        agent_type = str(agent.traits.get("agent_type") or agent.role)
        counts[agent_type] = counts.get(agent_type, 0) + 1
    total = len(materialization.population.agents)
    return {
        agent_type: count / total for agent_type, count in sorted(counts.items())
    }


def _catalog(store: SimulationRegistryStore) -> InitialAgentCatalog:
    materialization = store.initial_population()
    population = materialization.population if materialization else None
    if population is None:
        return InitialAgentCatalog([])
    routines_by_type: dict[str, list[RoutineLink]] = {}
    routine_registry = store.routines()
    if routine_registry is not None:
        known_modules = {module.id for module in store.decision_trees().modules}
        resolved_routines = resolve_routines(routine_registry, known_modules)
        routines_by_type = {
            agent_type.agent_type_id: [
                RoutineLink(
                    routine_id=item.routine.id,
                    name=item.routine.name,
                    agent_type=agent_type.agent_type_id,
                    inherited_from=item.source_type_id if item.inherited else None,
                )
                for item in agent_type.routines
            ]
            for agent_type in resolved_routines.agent_types
        }
    tree_registry = store.decision_trees()
    trees_by_id = {tree.id: tree for tree in tree_registry.trees}
    decision_trees_by_type: dict[str, list[DecisionTreeLink]] = {}
    for agent_type in store.resolved_agent_types().types:
        links: dict[str, DecisionTreeLink] = {}
        for member in agent_type.decisions:
            tree = trees_by_id.get(member.member.id)
            if tree is None:
                continue
            links[tree.id] = DecisionTreeLink(
                tree_id=tree.id,
                name=tree.name,
                agent_type=agent_type.id,
                inherited_from=member.source_type_id if member.inherited else None,
            )
        for tree in tree_registry.trees:
            if agent_type.id in tree.agent_type_ids:
                links.setdefault(
                    tree.id,
                    DecisionTreeLink(
                        tree_id=tree.id,
                        name=tree.name,
                        agent_type=agent_type.id,
                    ),
                )
        decision_trees_by_type[agent_type.id] = list(links.values())
    return InitialAgentCatalog.from_population(
        population,
        routines_by_type=routines_by_type,
        decision_trees_by_type=decision_trees_by_type,
        interaction_program=store.interaction_program(),
    )


def _confirmed_relationship_evidence(
    store: SimulationRegistryStore,
) -> tuple[RelationshipKindEvidence, ...]:
    program = store.interaction_program()
    return (
        program.relationship_evidence
        if program is not None and program.status == "confirmed"
        else ()
    )


def create_population_router(
    store: SimulationRegistryStore, atlas_store: AtlasStore | None = None
) -> APIRouter:
    router = APIRouter(prefix="/simulation", tags=["Simulation initial population"])
    feature_queries = FeatureQueryService(atlas_store) if atlas_store is not None else None

    def require_atlas() -> tuple[AtlasStore, FeatureQueryService]:
        if atlas_store is None or feature_queries is None:
            raise HTTPException(503, "The data atlas is not configured")
        return atlas_store, feature_queries

    @router.get("/initial-population", response_model=InitialPopulationStatus)
    def population_status() -> InitialPopulationStatus:
        materialization = store.initial_population()
        if materialization is None:
            return InitialPopulationStatus(configured=False)
        population = materialization.population
        return InitialPopulationStatus(
            configured=True,
            population_id=population.population_id,
            version=population.version,
            seed=population.seed,
            agent_count=len(population.agents),
            input_hash=materialization.input_hash,
            agent_type_mix=_population_type_mix(materialization),
        )

    @router.get("/agent-state-system", response_model=AgentStateSystemView)
    def agent_state_system() -> AgentStateSystemView:
        return AgentStateSystemView(
            agent_states=core_agent_state_catalog(),
            relationship_states=relationship_state_catalog(),
        )

    @router.post("/initial-population/validate", response_model=InitialPopulationValidation)
    def validate_population(
        request: InitialPopulationRequest,
    ) -> InitialPopulationValidation:
        return validate_population_request(request)

    @router.post(
        "/initial-population/materialize",
        response_model=InitialPopulationMaterialization,
    )
    def materialize_population(
        request: InitialPopulationRequest,
    ) -> InitialPopulationMaterialization:
        try:
            result = materialize_initial_population(
                request,
                _confirmed_relationship_evidence(store),
            )
        except InitialPopulationValidationError as error:
            raise HTTPException(422, error.validation.model_dump(mode="json")) from error
        return store.save_initial_population(result)

    @router.get("/initial-population/atlas/places", response_model=PlaceOptions)
    def atlas_places(
        search: str = Query("", max_length=120), limit: int = Query(25, ge=1, le=50)
    ) -> PlaceOptions:
        _, queries = require_atlas()
        return queries.place_options(search, limit)

    @router.post(
        "/initial-population/atlas/materialize",
        response_model=AtlasPopulationResult,
    )
    def materialize_atlas_population(
        request: AtlasPopulationRequest,
    ) -> AtlasPopulationResult:
        if request.scope != "shared":
            raise HTTPException(
                409,
                "Run-scoped imports cannot be installed in the shared simulation registry; "
                "promote the import to the shared atlas explicitly",
            )
        configured_atlas, _ = require_atlas()
        try:
            result = AtlasPopulationMaterializer(configured_atlas).materialize(
                request,
                _confirmed_relationship_evidence(store),
            )
        except InitialPopulationValidationError as error:
            raise HTTPException(422, error.validation.model_dump(mode="json")) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        store.save_initial_population(result.materialization)
        return result

    @router.get("/initial-agents", response_model=InitialAgentPage)
    def list_initial_agents(
        search: str = Query("", max_length=160),
        agent_type: str | None = None,
        country: str | None = None,
        city: str | None = None,
        age_min: float | None = Query(default=None, ge=0),
        age_max: float | None = Query(default=None, ge=0),
        household: str | None = None,
        family_status: str | None = None,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
    ) -> InitialAgentPage:
        try:
            query = InitialAgentQuery(
                search=search,
                agent_type=agent_type,
                country=country,
                city=city,
                age_min=age_min,
                age_max=age_max,
                household=household,
                family_status=family_status,
                page=page,
                page_size=page_size,
            )
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return _catalog(store).search(query)

    @router.get("/initial-agents/{agent_id}", response_model=InitialAgentDetail)
    def initial_agent_detail(agent_id: str) -> InitialAgentDetail:
        try:
            return _catalog(store).detail(agent_id)
        except KeyError as error:
            raise HTTPException(404, "Initial agent not found") from error

    return router

