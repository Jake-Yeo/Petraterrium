from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from .mobility import MobilityRegistryDefinition
from .registry_store import SimulationRegistryStore


class MobilityRouteModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class MobilityRegistryView(MobilityRouteModel):
    configured: bool
    registry: MobilityRegistryDefinition | None


class ConfirmMobilityRequest(MobilityRouteModel):
    registry: MobilityRegistryDefinition
    user_confirmed: Literal[True]


def _view(store: SimulationRegistryStore) -> MobilityRegistryView:
    registry = store.mobility()
    return MobilityRegistryView(configured=registry is not None, registry=registry)


def _validate_tree_references(
    store: SimulationRegistryStore, registry: MobilityRegistryDefinition
) -> None:
    known_tree_ids = {tree.id for tree in store.decision_trees().trees}
    missing = sorted(
        {
            tree_id
            for profile in registry.place_profiles
            for tree_id in profile.available_decision_tree_ids
            if tree_id not in known_tree_ids
        }
    )
    if missing:
        raise HTTPException(
            status_code=422,
            detail="Mobility place profiles reference missing decision trees: "
            + ", ".join(missing),
        )


def create_mobility_router(store: SimulationRegistryStore) -> APIRouter:
    router = APIRouter(prefix="/simulation/mobility", tags=["Simulation mobility"])

    @router.get("", response_model=MobilityRegistryView)
    def get_mobility() -> MobilityRegistryView:
        return _view(store)

    @router.post("/confirm", response_model=MobilityRegistryView)
    def confirm_mobility(request: ConfirmMobilityRequest) -> MobilityRegistryView:
        if request.registry.status != "confirmed":
            raise HTTPException(
                status_code=422,
                detail="A mobility registry must have confirmed status before it can run",
            )
        _validate_tree_references(store, request.registry)
        store.save_mobility(request.registry)
        return _view(store)

    return router
