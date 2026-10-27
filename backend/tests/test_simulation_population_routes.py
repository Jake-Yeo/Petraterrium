from fastapi.testclient import TestClient

from petraterrium.main import create_app
from petraterrium.simulation.registry_store import SimulationRegistryStore


def population_payload() -> dict:
    return {
        "population_id": "verified-population",
        "version": "2026-10-27",
        "seed": 17,
        "target_agents": 1,
        "evidence": [
            {
                "evidence_id": "joint-1",
                "source": "Verified household record",
                "source_version": "v1",
                "observed_at": "2026-01-01",
                "licence": "Test licence",
                "place": "CA",
                "status": "measured_joint",
                "fields": ["age", "sex", "household_composition"],
                "uncertainty": "One test record",
            }
        ],
        "household_templates": [
            {
                "template_id": "single-adult",
                "place": "CA",
                "country": "Canada",
                "region": "Northern America",
                "city": "Vancouver",
                "latitude": 49.2827,
                "longitude": -123.1207,
                "weight": 1,
                "evidence_id": "joint-1",
                "members": [
                    {
                        "member_id": "reference",
                        "name": "Avery",
                        "age": 40,
                        "sex": "female",
                        "relationship_to_reference": "self",
                        "agent_types": ["person"],
                        "traits": {"occupation": "Engineer"},
                        "states": {"location": "home:single-adult"},
                        "field_evidence": {
                            "age": "joint-1",
                            "sex": "joint-1",
                        },
                    }
                ],
            }
        ],
    }


def test_materialized_population_drives_server_paged_initial_agents(tmp_path):
    registry = SimulationRegistryStore(tmp_path / "simulation-registry.json")
    application = create_app(
        atlas_path=tmp_path / "atlas.sqlite3",
        simulation_registry_store=registry,
    )

    with TestClient(application) as client:
        before = client.get("/simulation/initial-agents")
        materialized = client.post(
            "/simulation/initial-population/materialize",
            json=population_payload(),
        )
        listed = client.get(
            "/simulation/initial-agents",
            params={"search": "Avery", "country": "Canada", "page_size": 10},
        )
        agent_id = listed.json()["items"][0]["agent_id"]
        detail = client.get(f"/simulation/initial-agents/{agent_id}")

    assert before.status_code == 200 and before.json()["total"] == 0
    assert materialized.status_code == 200
    assert listed.status_code == 200 and listed.json()["total"] == 1
    assert detail.json()["age"] == 40
    assert detail.json()["household"]["members"][0]["agent_id"] == agent_id
    assert detail.json()["interaction_context"] == {
        "program_status": "absent",
        "program_version": None,
        "history_available": False,
        "history_message": (
            "No interaction frequency or history exists before a run. Run the simulation, "
            "then open Run Results for recorded interactions."
        ),
        "counterparts": [],
        "rules": [],
    }

