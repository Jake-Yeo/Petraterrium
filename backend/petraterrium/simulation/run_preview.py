from fastapi import APIRouter, HTTPException
from pydantic import Field

from .run_service import (
    PreparedRunFactory,
    RunPreparationError,
    SimulationRunConfig,
    SimulationRunModel,
    SimulationRunService,
)
from .run_warnings import RunEvidenceSummary, RunEvidenceWarning


class SimulationRunPreview(SimulationRunModel):
    config: SimulationRunConfig
    agent_count: int = Field(ge=1)
    total_ticks: int = Field(ge=1)
    data_version: str = Field(min_length=1)
    program_version: str = Field(min_length=1)
    default_dsl_version: str | None = Field(default=None, min_length=1)
    default_dsl_hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    evidence_summary: RunEvidenceSummary
    evidence_warnings: tuple[RunEvidenceWarning, ...]


class SimulationRunPreviewService:
    def __init__(self, prepare_run: PreparedRunFactory):
        self._prepare_run = prepare_run

    def preview(self, config: SimulationRunConfig) -> SimulationRunPreview:
        try:
            prepared = self._prepare_run(config)
            SimulationRunService._validate_prepared(prepared, config)
        except ValueError as error:
            raise RunPreparationError(str(error)) from error
        return SimulationRunPreview(
            config=config,
            agent_count=len(prepared.agent_ids),
            total_ticks=config.total_ticks,
            data_version=prepared.data_version,
            program_version=prepared.program_version,
            default_dsl_version=prepared.default_dsl_version,
            default_dsl_hash=prepared.default_dsl_hash,
            evidence_summary=prepared.coefficient_evidence,
            evidence_warnings=tuple(prepared.evidence_warnings),
        )


def create_simulation_run_preview_router(
    service: SimulationRunPreviewService,
) -> APIRouter:
    router = APIRouter(prefix="/simulation/runs", tags=["Simulation runs"])

    @router.post("/preview", response_model=SimulationRunPreview)
    def preview_run(config: SimulationRunConfig) -> SimulationRunPreview:
        try:
            return service.preview(config)
        except RunPreparationError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    return router
