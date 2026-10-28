from fastapi import APIRouter, HTTPException

from .editable_dsl_contracts import (
    ConfirmEditableDslRequest,
    EditableDslRevision,
    PreviewEditableDslRequest,
    PreviewEditableDslResponse,
)
from .editable_dsl_service import EditableDslService


def create_editable_dsl_router(service: EditableDslService) -> APIRouter:
    router = APIRouter(prefix="/simulation/editable-dsl", tags=["Editable DSL"])

    @router.get("", response_model=EditableDslRevision)
    def current() -> EditableDslRevision:
        return service.current()

    @router.get("/history", response_model=tuple[EditableDslRevision, ...])
    def history() -> tuple[EditableDslRevision, ...]:
        return service.history()

    @router.post("/preview", response_model=PreviewEditableDslResponse)
    def preview(request: PreviewEditableDslRequest) -> PreviewEditableDslResponse:
        try:
            return service.preview(request)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @router.post("/confirm", response_model=EditableDslRevision)
    def confirm(request: ConfirmEditableDslRequest) -> EditableDslRevision:
        try:
            return service.confirm(request)
        except ValueError as error:
            status = 422 if "validation errors" in str(error) else 409
            raise HTTPException(status, str(error)) from error

    return router
