import inspect
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException

from .confirmation import ChainConfirmationError, confirmed_chain_from_draft
from .models import (
    ChainDraft,
    ChainProposalRequest,
    ChainProposalResult,
    ConfirmationResult,
    ConfirmChainRequest,
    ConfirmedChainGraph,
)
from .proposal import propose_chain
from .validation import validate_chain_draft

PersistenceCallback = Callable[
    [ConfirmedChainGraph], Awaitable[str | None] | str | None
]


def create_markov_builder_router(
    persist_chain: PersistenceCallback | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/markov-builder", tags=["Markov chain builder"])

    @router.post("/proposals", response_model=ChainProposalResult)
    def create_proposal(request: ChainProposalRequest) -> ChainProposalResult:
        return propose_chain(request)

    @router.post("/validation")
    def validate_proposal(draft: ChainDraft):
        return validate_chain_draft(draft)

    @router.post("/confirm", response_model=ConfirmationResult)
    async def confirm_proposal(request: ConfirmChainRequest) -> ConfirmationResult:
        try:
            chain = confirmed_chain_from_draft(request.draft, request.user_confirmed)
        except ChainConfirmationError as error:
            raise HTTPException(
                status_code=422,
                detail=error.validation.model_dump(mode="json"),
            ) from error
        persistence_id = None
        persisted = persist_chain is not None
        if persist_chain:
            result = persist_chain(chain)
            if inspect.isawaitable(result):
                result = await result
            persistence_id = result
        return ConfirmationResult(
            chain=chain,
            validation=validate_chain_draft(request.draft),
            persisted=persisted,
            persistence_id=persistence_id,
        )

    return router
