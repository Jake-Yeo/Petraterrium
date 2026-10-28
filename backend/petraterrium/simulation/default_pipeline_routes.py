from fastapi import APIRouter, HTTPException

from .default_pipeline_contracts import (
    ActivateDefaultPipelineRunRequest,
    DefaultPipelineActivation,
    DefaultPipelineRun,
    DefaultPipelineRunDiff,
    DefaultPipelineRunList,
    DefaultStateRestoreReceipt,
    RestoreDefaultPipelineRunRequest,
)
from .default_pipeline_service import DefaultPipelineRunService


def create_default_pipeline_router(service: DefaultPipelineRunService) -> APIRouter:
    router = APIRouter(
        prefix="/simulation/default-pipeline",
        tags=["Default research pipeline"],
    )

    @router.get("", response_model=DefaultPipelineRunList)
    def list_runs() -> DefaultPipelineRunList:
        return service.list_runs()

    @router.post("/duration-research", response_model=DefaultPipelineRun)
    def run_duration_research() -> DefaultPipelineRun:
        try:
            return service.run_duration_research()
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @router.get(
        "/{from_run_id}/diff/{to_run_id}",
        response_model=DefaultPipelineRunDiff,
    )
    def diff_runs(from_run_id: str, to_run_id: str) -> DefaultPipelineRunDiff:
        try:
            return service.diff(from_run_id, to_run_id)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @router.post(
        "/{run_id}/activate",
        response_model=DefaultPipelineActivation,
    )
    def activate_run(
        run_id: str,
        request: ActivateDefaultPipelineRunRequest,
    ) -> DefaultPipelineActivation:
        try:
            return service.activate(run_id, request)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @router.post("/restore", response_model=DefaultStateRestoreReceipt)
    def restore_default(
        request: RestoreDefaultPipelineRunRequest,
    ) -> DefaultStateRestoreReceipt:
        try:
            return service.restore(request)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @router.get("/{run_id}", response_model=DefaultPipelineRun)
    def inspect_run(run_id: str) -> DefaultPipelineRun:
        try:
            return service.inspect(run_id)
        except KeyError as error:
            raise HTTPException(404, str(error)) from error
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    return router

