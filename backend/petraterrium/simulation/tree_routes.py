from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from .registry_store import SimulationRegistryStore
from .tree_modules import (
    DecisionTreeModuleRegistry,
    DecisionTreeRegistryDefinition,
    TreeRegistryValidation,
)


class DecisionTreeRouteModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DecisionTreeRegistryView(DecisionTreeRouteModel):
    registry: DecisionTreeRegistryDefinition
    validation: TreeRegistryValidation


class ConfirmDecisionTreeRegistryRequest(DecisionTreeRouteModel):
    registry: DecisionTreeRegistryDefinition
    user_confirmed: Literal[True]


def _view(registry: DecisionTreeRegistryDefinition) -> DecisionTreeRegistryView:
    resolved = DecisionTreeModuleRegistry(registry)
    return DecisionTreeRegistryView(registry=registry, validation=resolved.validation)


def create_decision_tree_router(store: SimulationRegistryStore) -> APIRouter:
    router = APIRouter(prefix="/simulation/decision-trees", tags=["Decision trees"])

    @router.get("", response_model=DecisionTreeRegistryView)
    def get_registry() -> DecisionTreeRegistryView:
        return _view(store.decision_trees())

    @router.post("/validate", response_model=TreeRegistryValidation)
    def validate_registry(
        registry: DecisionTreeRegistryDefinition,
    ) -> TreeRegistryValidation:
        return DecisionTreeModuleRegistry(registry).validation

    @router.post("/confirm", response_model=DecisionTreeRegistryView)
    def confirm_registry(
        request: ConfirmDecisionTreeRegistryRequest,
    ) -> DecisionTreeRegistryView:
        view = _view(request.registry)
        if not view.validation.valid:
            raise HTTPException(422, view.validation.model_dump(mode="json"))
        return _view(store.save_decision_trees(request.registry))

    return router
