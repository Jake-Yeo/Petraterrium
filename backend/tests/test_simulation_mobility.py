import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from petraterrium.main import create_app
from petraterrium.simulation.mobility import (
    MobilityEvidence,
    MobilityRegistryDefinition,
    PlaceProfileDefinition,
    TravelRouteDefinition,
    resolve_mobility,
)
from petraterrium.simulation.mobility_routes import create_mobility_router
from petraterrium.simulation.registry_store import SimulationRegistryStore


def evidence(status: str = "measured") -> MobilityEvidence:
    return MobilityEvidence(
        status=status,
        source_title="Vancouver travel survey",
        source_version="2025",
        source_date="2025-04-01",
        licence="Open Government Licence",
        evidence_id="vancouver-travel-2025",
        uncertainty=0.08,
    )


def registry(status: str = "confirmed") -> MobilityRegistryDefinition:
    return MobilityRegistryDefinition(
        version="mobility-2025",
        status=status,
        place_profiles=[
            PlaceProfileDefinition(
                id="home-profile",
                place_kind="home",
                accepts_arrivals=True,
                allows_in_person=True,
                capacity=8,
                state={"crowd_density": 0.25, "contamination": 0.02},
                available_decision_tree_ids=["family-dinner", "rest"],
                evidence=evidence(),
            ),
            PlaceProfileDefinition(
                id="transit-profile",
                place_kind="transit",
                accepts_arrivals=True,
                allows_in_person=True,
                capacity=80,
                state={"crowd_density": 0.7, "contamination": 0.1},
                available_decision_tree_ids=[],
                evidence=evidence(),
            ),
            PlaceProfileDefinition(
                id="work-profile",
                place_kind="work",
                accepts_arrivals=True,
                allows_in_person=True,
                capacity=120,
                state={"crowd_density": 0.45, "contamination": 0.04},
                available_decision_tree_ids=["work-task", "coworker-talk"],
                evidence=evidence(),
            ),
            PlaceProfileDefinition(
                id="bar-profile",
                place_kind="bar",
                accepts_arrivals=True,
                allows_in_person=True,
                capacity=60,
                state={"crowd_density": 0.8, "contamination": 0.12},
                available_decision_tree_ids=["drink", "bar-talk"],
                evidence=evidence(),
            ),
        ],
        routes=[
            TravelRouteDefinition(
                id="home-to-work",
                from_place_kind="home",
                to_place_kind="work",
                transit_place_kind="transit",
                duration_minutes=60,
                evidence=evidence(),
            ),
            TravelRouteDefinition(
                id="work-to-bar",
                from_place_kind="work",
                to_place_kind="bar",
                transit_place_kind="transit",
                duration_minutes=30,
                evidence=evidence(),
            ),
            TravelRouteDefinition(
                id="bar-to-home",
                from_place_kind="bar",
                to_place_kind="home",
                transit_place_kind="transit",
                duration_minutes=60,
                evidence=evidence(),
            ),
        ],
    )


def test_confirmed_mobility_resolves_only_exact_evidenced_routes_and_profiles():
    resolved = resolve_mobility(registry())

    assert resolved.profile("bar").state["crowd_density"] == 0.8
    assert resolved.route("home", "work").id == "home-to-work"
    assert resolved.travel_ticks("work", "bar", tick_interval_hours=1) == 1
    assert resolved.travel_ticks("home", "work", tick_interval_hours=0.5) == 2
    assert resolved.route("home", "bar") is None
    assert resolved.profile("school") is None


def test_specific_place_profile_overrides_kind_default_without_ambiguity():
    default = next(profile for profile in registry().place_profiles if profile.place_kind == "bar")
    clean_bar = default.model_copy(
        update={
            "id": "clean-bar-profile",
            "place_id": "runtime-clean-bar",
            "capacity": 20,
            "state": {"contamination": 0.02},
            "available_decision_tree_ids": ["drink"],
        }
    )
    dirty_bar = default.model_copy(
        update={
            "id": "dirty-bar-profile",
            "place_id": "runtime-dirty-bar",
            "accepts_arrivals": False,
            "allows_in_person": False,
            "capacity": 4,
            "state": {"contamination": 0.8},
            "available_decision_tree_ids": [],
        }
    )
    definition = registry().model_copy(
        update={"place_profiles": [*registry().place_profiles, clean_bar, dirty_bar]}
    )

    resolved = resolve_mobility(definition)

    assert resolved.profile("bar", "runtime-clean-bar") == clean_bar
    assert resolved.profile("bar", "runtime-dirty-bar") == dirty_bar
    assert resolved.profile("bar", "runtime-other-bar") == default

    duplicate = definition.model_dump(mode="python")
    duplicate["place_profiles"].append(
        {
            **dirty_bar.model_dump(mode="python"),
            "id": "duplicate-dirty-bar-profile",
        }
    )
    with pytest.raises(ValidationError, match="specific place"):
        MobilityRegistryDefinition.model_validate(duplicate)


def test_draft_or_non_executable_mobility_never_enters_the_runtime():
    with pytest.raises(ValueError, match="confirmed"):
        resolve_mobility(registry(status="draft"))

    payload = registry().model_dump(mode="python")
    payload["routes"][0]["evidence"] = MobilityEvidence(
        status="unknown",
        note="No travel-time evidence",
    ).model_dump(mode="python")
    with pytest.raises(ValidationError, match="executable evidence"):
        MobilityRegistryDefinition.model_validate(payload)


def test_measured_mobility_requires_complete_provenance():
    with pytest.raises(ValidationError, match="source_title"):
        MobilityEvidence(status="measured", uncertainty=0.2)


def test_route_pairs_and_place_kinds_are_unique_and_transit_is_defined():
    payload = registry().model_dump(mode="python")
    duplicate_pair = {**payload["routes"][0], "id": "duplicate-home-to-work"}
    payload["routes"].append(duplicate_pair)
    with pytest.raises(ValidationError, match="route pairs"):
        MobilityRegistryDefinition.model_validate(payload)

    payload = registry().model_dump(mode="python")
    payload["place_profiles"] = [
        item for item in payload["place_profiles"] if item["place_kind"] != "transit"
    ]
    with pytest.raises(ValidationError, match="transit place kind"):
        MobilityRegistryDefinition.model_validate(payload)


def test_confirmed_registry_round_trips_through_store_and_routes(tmp_path):
    store = SimulationRegistryStore(tmp_path / "registry.json")
    route_registry = registry().model_copy(
        update={
            "place_profiles": [
                profile.model_copy(update={"available_decision_tree_ids": []})
                for profile in registry().place_profiles
            ]
        }
    )
    app = FastAPI()
    app.include_router(create_mobility_router(store))
    client = TestClient(app)

    response = client.post(
        "/simulation/mobility/confirm",
        json={
            "registry": route_registry.model_dump(mode="json"),
            "user_confirmed": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert response.json()["registry"]["version"] == "mobility-2025"
    assert store.mobility() == route_registry


def test_confirm_route_rejects_unknown_place_decision_tree_reference(tmp_path):
    store = SimulationRegistryStore(tmp_path / "registry.json")
    app = FastAPI()
    app.include_router(create_mobility_router(store))
    client = TestClient(app)

    response = client.post(
        "/simulation/mobility/confirm",
        json={"registry": registry().model_dump(mode="json"), "user_confirmed": True},
    )

    assert response.status_code == 422
    assert "missing decision trees" in response.json()["detail"]
    assert store.mobility() is None


def test_application_mounts_the_mobility_registry_route(tmp_path, monkeypatch):
    monkeypatch.setenv("PETRATERRIUM_SIMULATION_RUNS_PATH", str(tmp_path / "runs.sqlite3"))
    monkeypatch.setenv("PETRATERRIUM_AI_SETTINGS_PATH", str(tmp_path / "ai-settings.json"))
    store = SimulationRegistryStore(tmp_path / "registry.json")
    with TestClient(
        create_app(
            atlas_path=tmp_path / "atlas.sqlite3",
            simulation_registry_store=store,
        )
    ) as client:
        response = client.get("/simulation/mobility")

    assert response.status_code == 200
    assert response.json() == {"configured": False, "registry": None}
