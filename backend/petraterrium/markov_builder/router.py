import inspect
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException

from ..llm_gateway import AIProviderError, SelectedAIProvider
from ..markov.pipeline_evidence import PipelineTransitionEstimate
from .confirmation import ChainConfirmationError, confirmed_chain_from_draft
from .models import (
    ChainDraft,
    ChainProposalRequest,
    ChainProposalResult,
    ConfirmationResult,
    ConfirmChainRequest,
    ConfirmedChainGraph,
)
from .probability_research import (
    MarkovProbabilityResearchService,
    TransitionProbabilityResearchRequest,
)
from .proposal import propose_chain
from .validation import validate_chain_draft

PersistenceCallback = Callable[
    [ConfirmedChainGraph], Awaitable[str | None] | str | None
]


def create_markov_builder_router(
    persist_chain: PersistenceCallback | None = None,
    ai_provider: SelectedAIProvider | None = None,
    probability_research: MarkovProbabilityResearchService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/markov-builder", tags=["Markov chain builder"])

    @router.post("/proposals", response_model=ChainProposalResult)
    def create_proposal(request: ChainProposalRequest) -> ChainProposalResult:
        try:
            return propose_chain(request, ai_provider=ai_provider)
        except AIProviderError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @router.post("/validation")
    def validate_proposal(draft: ChainDraft):
        return validate_chain_draft(draft)

    @router.post("/probability-research")
    def research_probability(
        request: TransitionProbabilityResearchRequest,
    ) -> PipelineTransitionEstimate:
        if probability_research is None:
            raise HTTPException(
                status_code=503,
                detail="Markov probability research is not configured",
            )
        return probability_research.research(request)

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
