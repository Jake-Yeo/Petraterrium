import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from petraterrium.simulation.locations import (
    AgentLocationColumns,
    LocationMovement,
    LocationPlace,
    LocationRegistry,
    LocationRunRegistry,
    LocationRuntimeState,
    apply_movements,
    create_location_router,
    face_to_face_allowed,
)


def places() -> tuple[LocationPlace, ...]:
    return (
        LocationPlace(
            id="canada",
            name="Canada",
            level="country",
            state={"tax_rate": 0.2},
        ),
        LocationPlace(
            id="british-columbia",
            name="British Columbia",
            level="state",
            parent_id="canada",
            state={"tax_rate": 0.25},
        ),
        LocationPlace(
            id="vancouver",
            name="Vancouver",
            level="city",
            parent_id="british-columbia",
            state={"air_quality": 0.8},
        ),
        LocationPlace(
            id="kitsilano",
            name="Kitsilano",
            level="district",
            parent_id="vancouver",
        ),
        LocationPlace(
            id="home-1",
            name="Home",
            level="building",
            parent_id="kitsilano",
            state={"contamination": 0.1},
        ),
        LocationPlace(
            id="living-room",
            name="Living room",
            level="room",
            parent_id="home-1",
            state={"contamination": 0.3},
        ),
        LocationPlace(
            id="kitchen",
            name="Kitchen",
            level="room",
            parent_id="home-1",
        ),
    )


def state() -> LocationRuntimeState:
    return LocationRuntimeState(
        agents=AgentLocationColumns(
            agent_ids=("avery", "sam", "mira"),
            current_location_ids=("living-room", "living-room", "kitchen"),
        )
    )


def test_movement_records_parent_aware_route_state_and_colocation():
    registry = LocationRegistry(places())

    result = apply_movements(
        registry,
        state(),
        4,
        (
            LocationMovement(
                agent_id="mira",
                destination_location_id="living-room",
                expected_parent_id="home-1",
            ),
        ),
    )

    assert result.state.agents.current_location_ids == (
        "living-room",
        "living-room",
        "living-room",
    )
    assert result.movements[0].route_location_ids == (
        "kitchen",
        "home-1",
        "living-room",
    )
    assert result.state.history == result.movements
    assert result.co_located_agent_ids["avery"] == ("sam", "mira")
    assert result.effective_place_state["mira"] == {
        "tax_rate": 0.25,
        "air_quality": 0.8,
        "contamination": 0.3,
    }
    assert face_to_face_allowed(registry, result.state, "avery", "mira")


def test_invalid_arrival_does_not_mutate_the_input_state():
    blocked = list(places())
    blocked[-1] = blocked[-1].model_copy(update={"accepts_arrivals": False})
    registry = LocationRegistry(blocked)
    initial = state()

    with pytest.raises(ValueError, match="does not accept arrivals"):
        apply_movements(
            registry,
            initial,
            4,
            (
                LocationMovement(
                    agent_id="avery",
                    destination_location_id="kitchen",
                    expected_parent_id="home-1",
                ),
            ),
        )

    assert initial.agents.current_location_ids == (
        "living-room",
        "living-room",
        "kitchen",
    )
    assert initial.history == ()


def test_hierarchy_rejects_skipped_levels():
    invalid = list(places())
    invalid[2] = invalid[2].model_copy(update={"parent_id": "canada"})

    with pytest.raises(ValueError, match="cannot have parent"):
        LocationRegistry(invalid)


def test_capacity_and_parent_are_validated_before_arrival():
    registry = LocationRegistry(
        tuple(
            place.model_copy(update={"capacity": 2})
            if place.id == "living-room"
            else place
            for place in places()
        )
    )
    with pytest.raises(ValueError, match="parent is 'home-1'"):
        apply_movements(
            registry,
            state(),
            4,
            (
                LocationMovement(
                    agent_id="mira",
                    destination_location_id="living-room",
                    expected_parent_id="kitsilano",
                ),
            ),
        )
    with pytest.raises(ValueError, match="capacity 2"):
        apply_movements(
            registry,
            state(),
            4,
            (
                LocationMovement(
                    agent_id="mira",
                    destination_location_id="living-room",
                    expected_parent_id="home-1",
                ),
            ),
        )


def test_face_to_face_requires_the_same_permitted_specific_place():
    restricted = list(places())
    restricted[-2] = restricted[-2].model_copy(update={"allows_in_person": False})
    registry = LocationRegistry(restricted)

    assert not face_to_face_allowed(registry, state(), "avery", "sam")
    assert not face_to_face_allowed(registry, state(), "avery", "mira")


def test_travel_between_country_roots_records_both_sides_of_the_route():
    registry = LocationRegistry(
        (
            LocationPlace(id="canada", name="Canada", level="country"),
            LocationPlace(id="mexico", name="Mexico", level="country"),
        )
    )
    initial = LocationRuntimeState(
        agents=AgentLocationColumns(
            agent_ids=("traveler",), current_location_ids=("canada",)
        )
    )

    result = apply_movements(
        registry,
        initial,
        9,
        (
            LocationMovement(
                agent_id="traveler",
                destination_location_id="mexico",
                expected_parent_id=None,
            ),
        ),
    )

    assert result.movements[0].route_location_ids == ("canada", "mexico")


def test_router_exposes_tree_and_agent_location_detail():
    registry = LocationRunRegistry()
    moved = apply_movements(
        LocationRegistry(places()),
        state(),
        4,
        (
            LocationMovement(
                agent_id="mira",
                destination_location_id="living-room",
                expected_parent_id="home-1",
            ),
        ),
    )
    registry.record(
        "run-1",
        4,
        places(),
        moved.state,
        {"avery": "Avery", "sam": "Sam", "mira": "Mira"},
    )
    app = FastAPI()
    app.include_router(create_location_router(registry))
    client = TestClient(app)

    snapshot = client.get("/simulation/runs/run-1/locations")
    detail = client.get("/simulation/runs/run-1/locations/agents/mira")

    assert snapshot.status_code == 200
    assert snapshot.json()["root_location_ids"] == ["canada"]
    room = next(
        place for place in snapshot.json()["places"] if place["id"] == "living-room"
    )
    assert room["current_agent_count"] == 3
    assert detail.status_code == 200
    assert detail.json()["current_location"]["name"] == "Living room"
    assert [place["name"] for place in detail.json()["ancestry"]] == [
        "Canada",
        "British Columbia",
        "Vancouver",
        "Kitsilano",
        "Home",
        "Living room",
    ]
    assert {agent["display_name"] for agent in detail.json()["co_located_agents"]} == {
        "Avery",
        "Sam",
    }
    assert [agent["display_name"] for agent in detail.json()["elsewhere_agents"]] == []
    assert detail.json()["history"][0]["route_location_ids"] == [
        "kitchen",
        "home-1",
        "living-room",
    ]


def test_agent_detail_separates_co_located_agents_from_everyone_else():
    registry = LocationRunRegistry()
    registry.record(
        "run-elsewhere",
        4,
        places(),
        state(),
        {"avery": "Avery", "sam": "Sam", "mira": "Mira"},
    )

    detail = registry.catalog("run-elsewhere").agent_detail("avery")

    assert [agent.display_name for agent in detail.co_located_agents] == ["Sam"]
    assert [agent.display_name for agent in detail.elsewhere_agents] == ["Mira"]
    assert detail.elsewhere_agents[0].current_location_id == "kitchen"
