from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .dsl import DSLConfig
from .leaders import (
    EvidenceTable,
    InfluencerMessage,
    LeaderDecision,
    influencer_message,
    leader_decision,
)
from .llm_gateway import AIProviderError, SelectedAIProvider


class AIFeatureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LeaderDecisionRequest(AIFeatureRequest):
    leader: dict[str, Any]
    aggregated_state: dict[str, Any]
    week: int = Field(ge=0)
    dsl: DSLConfig


class NarrationRequest(AIFeatureRequest):
    narrator: dict[str, Any]
    recorded_context: dict[str, Any]


def create_ai_feature_router(provider: SelectedAIProvider) -> APIRouter:
    router = APIRouter(prefix="/ai-features", tags=["AI features"])

    @router.post("/leader-decision", response_model=LeaderDecision)
    def propose_leader_decision(request: LeaderDecisionRequest) -> LeaderDecision:
        evidence = EvidenceTable(
            {action.id: action.evidence for action in request.dsl.leader_actions}
        )
        try:
            return leader_decision(
                request.leader,
                request.aggregated_state,
                request.week,
                request.dsl,
                provider,
                evidence,
            )
        except AIProviderError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/narration", response_model=InfluencerMessage)
    def create_narration(request: NarrationRequest) -> InfluencerMessage:
        try:
            return influencer_message(
                request.narrator,
                request.recorded_context,
                provider,
            )
        except AIProviderError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return router
