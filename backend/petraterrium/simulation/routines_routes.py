from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .registry_store import SimulationRegistryStore
from .routines import (
    ResolvedAgentRoutines,
    ResolvedRoutineRegistry,
    RoutineRegistryDefinition,
    RoutineValidationResult,
    resolve_routines,
    validate_routines,
)


class RoutineRouteModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class RoutineRegistryStatus(RoutineRouteModel):
    configured: bool
    agent_type_count: int = Field(default=0, ge=0)
    routine_count: int = Field(default=0, ge=0)
    valid: bool | None = None
    issue_count: int = Field(default=0, ge=0)


class RoutineRegistryView(RoutineRouteModel):
    status: RoutineRegistryStatus
    registry: RoutineRegistryDefinition | None
    validation: RoutineValidationResult | None
    resolved: ResolvedRoutineRegistry | None


class ConfirmRoutineRegistryRequest(RoutineRouteModel):
    registry: RoutineRegistryDefinition
    user_confirmed: Literal[True]


def _known_module_ids(store: SimulationRegistryStore) -> set[str]:
    return {module.id for module in store.decision_trees().modules}


def _view(store: SimulationRegistryStore) -> RoutineRegistryView:
    registry = store.routines()
    if registry is None:
        return RoutineRegistryView(
            status=RoutineRegistryStatus(configured=False),
            registry=None,
            validation=None,
            resolved=None,
        )
    module_ids = _known_module_ids(store)
    validation = validate_routines(registry, module_ids)
    resolved = resolve_routines(registry, module_ids) if validation.valid else None
    return RoutineRegistryView(
        status=RoutineRegistryStatus(
            configured=True,
            agent_type_count=len(registry.agent_types),
            routine_count=len(registry.routines),
            valid=validation.valid,
            issue_count=len(validation.issues),
        ),
        registry=registry,
        validation=validation,
        resolved=resolved,
    )


def create_routine_router(store: SimulationRegistryStore) -> APIRouter:
    router = APIRouter(prefix="/simulation/routines", tags=["Simulation routines"])

    @router.get("", response_model=RoutineRegistryView)
    def get_registry() -> RoutineRegistryView:
        return _view(store)

    @router.get("/status", response_model=RoutineRegistryStatus)
    def get_status() -> RoutineRegistryStatus:
        return _view(store).status

    @router.post("/validate", response_model=RoutineValidationResult)
    def validate_registry(
        registry: RoutineRegistryDefinition,
    ) -> RoutineValidationResult:
        return validate_routines(registry, _known_module_ids(store))

    @router.post("/confirm", response_model=RoutineRegistryView)
    def confirm_registry(
        request: ConfirmRoutineRegistryRequest,
    ) -> RoutineRegistryView:
        validation = validate_routines(
            request.registry,
            _known_module_ids(store),
        )
        if not validation.valid:
            raise HTTPException(422, validation.model_dump(mode="json"))
        store.save_routines(request.registry)
        return _view(store)

    @router.get(
        "/agent-types/{agent_type_id}",
        response_model=ResolvedAgentRoutines,
    )
    def get_agent_type_routines(agent_type_id: str) -> ResolvedAgentRoutines:
        view = _view(store)
        if not view.status.configured:
            raise HTTPException(404, "Routine registry is not configured")
        if view.resolved is None:
            raise HTTPException(
                409,
                view.validation.model_dump(mode="json") if view.validation else {},
            )
        try:
            return view.resolved.by_agent_type_id(agent_type_id)
        except KeyError as error:
            raise HTTPException(404, "Agent type has no routine registry entry") from error

    return router
