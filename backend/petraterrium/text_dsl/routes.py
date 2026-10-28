from fastapi import APIRouter, HTTPException

from ..rust_core import RustCoreError
from .models import (
    SaveTextDslRequest,
    TextDslDocument,
    TextDslRunRequest,
    TextDslRunResult,
    TextDslRunSummary,
    TextDslValidation,
    ValidateTextDslRequest,
)
from .service import TextDslService


def create_text_dsl_router(service: TextDslService) -> APIRouter:
    router = APIRouter(prefix="/simulation/text-dsl", tags=["Text DSL"])

    @router.get("", response_model=TextDslDocument)
    def current() -> TextDslDocument:
        return service.current()

    @router.post("/validate", response_model=TextDslValidation)
    def validate(request: ValidateTextDslRequest) -> TextDslValidation:
        return service.validate(request.code)

    @router.put("", response_model=TextDslDocument)
    def save(request: SaveTextDslRequest) -> TextDslDocument:
        try:
            return service.save(request.code, request.expected_hash)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @router.post("/reset", response_model=TextDslDocument)
    def reset() -> TextDslDocument:
        return service.reset()

    @router.post("/runs", response_model=TextDslRunResult)
    def run(request: TextDslRunRequest) -> TextDslRunResult:
        try:
            return service.run(request)
        except (ValueError, RustCoreError) as error:
            raise HTTPException(422, str(error)) from error

    @router.get("/runs", response_model=tuple[TextDslRunSummary, ...])
    def runs() -> tuple[TextDslRunSummary, ...]:
        return service.list_runs()

    @router.get("/runs/{run_id}", response_model=TextDslRunResult)
    def run_detail(run_id: str) -> TextDslRunResult:
        try:
            return service.get_run(run_id)
        except KeyError as error:
            raise HTTPException(404, "DSL run was not found") from error

    return router
