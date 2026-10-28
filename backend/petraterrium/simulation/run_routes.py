from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response

from .aggregate_statistics import RunAggregatePage
from .run_service import (
    RunAgentDetail,
    RunAgentPage,
    RunDeletionConfirmationError,
    RunDeletionConflictError,
    RunEventPage,
    RunNotFoundError,
    RunNotReadyError,
    RunPreparationError,
    SimulationRunConfig,
    SimulationRunService,
    SimulationRunView,
)
from .spatial_projection import MAX_SPATIAL_QUERY_LIMIT, SpatialPointPage


def create_simulation_run_router(service: SimulationRunService) -> APIRouter:
    router = APIRouter(prefix="/simulation/runs", tags=["Simulation runs"])

    @router.post("", response_model=SimulationRunView, status_code=202)
    def launch_run(config: SimulationRunConfig) -> SimulationRunView:
        try:
            return service.launch(config)
        except RunPreparationError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("", response_model=list[SimulationRunView])
    def list_runs() -> list[SimulationRunView]:
        return service.list()

    @router.get("/{run_id}", response_model=SimulationRunView)
    def get_run(run_id: str) -> SimulationRunView:
        try:
            return service.get(run_id)
        except RunNotFoundError as error:
            raise HTTPException(status_code=404, detail="Simulation run was not found") from error

    @router.post("/{run_id}/cancel", response_model=SimulationRunView)
    def cancel_run(run_id: str) -> SimulationRunView:
        try:
            return service.cancel(run_id)
        except RunNotFoundError as error:
            raise HTTPException(status_code=404, detail="Simulation run was not found") from error

    @router.delete("/{run_id}", status_code=204)
    def delete_run(run_id: str, confirm_run_id: str = Query(min_length=1)) -> Response:
        try:
            service.delete(run_id, confirm_run_id)
        except RunNotFoundError as error:
            raise HTTPException(status_code=404, detail="Simulation run was not found") from error
        except RunDeletionConfirmationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except RunDeletionConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return Response(status_code=204)

    @router.get("/{run_id}/agents", response_model=RunAgentPage)
    def list_agents(
        run_id: str,
        search: str = "",
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=100, ge=1, le=500),
    ) -> RunAgentPage:
        try:
            return service.agents(
                run_id,
                search=search,
                page=page,
                page_size=page_size,
            )
        except RunNotFoundError as error:
            raise HTTPException(status_code=404, detail="Simulation run was not found") from error
        except RunNotReadyError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/{run_id}/agents/{agent_id}", response_model=RunAgentDetail)
    def get_agent(run_id: str, agent_id: str) -> RunAgentDetail:
        try:
            return service.agent(run_id, agent_id)
        except RunNotFoundError as error:
            raise HTTPException(status_code=404, detail="Simulation agent was not found") from error
        except RunNotReadyError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/{run_id}/events", response_model=RunEventPage)
    def list_events(
        run_id: str,
        kind: Literal[
            "action",
            "routine",
            "transition",
            "location",
            "availability",
            "synchronization",
            "interaction",
        ]
        | None = None,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=100, ge=1, le=500),
    ) -> RunEventPage:
        try:
            return service.events(
                run_id,
                kind=kind,
                page=page,
                page_size=page_size,
            )
        except RunNotFoundError as error:
            raise HTTPException(status_code=404, detail="Simulation run was not found") from error
        except RunNotReadyError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/{run_id}/statistics", response_model=RunAggregatePage)
    def list_statistics(
        run_id: str,
        place_level: Literal["city", "country", "region", "global"] | None = None,
        place_id: str | None = None,
        day: int | None = Query(default=None, ge=1),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=500, ge=1, le=1_000),
    ) -> RunAggregatePage:
        try:
            return service.statistics(
                run_id,
                place_level=place_level,
                place_id=place_id,
                day=day,
                page=page,
                page_size=page_size,
            )
        except RunNotFoundError as error:
            raise HTTPException(
                status_code=404, detail="Simulation run was not found"
            ) from error

    @router.get("/{run_id}/spatial-points", response_model=SpatialPointPage)
    def list_spatial_points(
        run_id: str,
        day: int = Query(ge=1),
        tick: int = Query(ge=1),
        detail_level: Literal["city", "neighborhood"] = "city",
        north: float = Query(ge=-90, le=90),
        east: float = Query(ge=-180, le=180),
        south: float = Query(ge=-90, le=90),
        west: float = Query(ge=-180, le=180),
        city_id: Annotated[list[str] | None, Query()] = None,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=20_000, ge=1, le=MAX_SPATIAL_QUERY_LIMIT),
    ) -> SpatialPointPage:
        try:
            return service.spatial_points(
                run_id,
                day=day,
                tick=tick,
                detail_level=detail_level,
                north=north,
                east=east,
                south=south,
                west=west,
                city_ids=city_id or (),
                offset=offset,
                limit=limit,
            )
        except RunNotFoundError as error:
            raise HTTPException(
                status_code=404, detail="Simulation run was not found"
            ) from error
        except RunNotReadyError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return router
