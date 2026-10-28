from fastapi.testclient import TestClient

from petraterrium.ai_provider import AIGeneration
from petraterrium.ai_settings import AISourceProvenance
from petraterrium.main import create_app
from petraterrium.simulation.agent_type_routes import AgentTypeProposalShape
from petraterrium.simulation.agent_types import AgentTypeDefinition, AgentTypeMember
from petraterrium.simulation.registry_store import SimulationRegistryStore


class ProposalProvider:
    def generate_structured(self, *args, **kwargs):
        return AIGeneration(
            output=AgentTypeProposalShape(
                types=[
                    AgentTypeDefinition(
                        id="person",
                        name="Person",
                        parent_ids=[],
                        traits=[
                            AgentTypeMember(
                                id="age",
                                name="Age",
                                definition="Completed years",
                                source_feature_ids=["age"],
                            )
                        ],
                    ),
                    AgentTypeDefinition(
                        id="professional",
                        name="Professional",
                        parent_ids=["person"],
                    ),
                ]
            ),
            provenance=AISourceProvenance(
                source="openai_cli",
                source_label="OpenAI CLI",
                model="test-cli-model",
                generated_at="2026-10-27T12:00:00Z",
                prompt_version="agent-type-proposal-v1",
            ),
        )

    def test_connection(self):
        raise AssertionError("Connection test was not requested")


def test_agent_type_proposal_requires_confirmation_and_persists(tmp_path):
    registry_store = SimulationRegistryStore(tmp_path / "simulation-registry.json")
    application = create_app(
        atlas_path=tmp_path / "atlas.sqlite3",
        ai_provider=ProposalProvider(),
        simulation_registry_store=registry_store,
    )

    with TestClient(application) as client:
        proposed = client.post(
            "/simulation/agent-types/proposals",
            json={"prompt": "People and professionals"},
        )
        before = client.get("/simulation/agent-types")
        confirmed = client.post(
            "/simulation/agent-types/confirm",
            json={"draft": proposed.json(), "user_confirmed": True},
        )
        after = client.get("/simulation/agent-types")

    assert proposed.status_code == 200
    assert proposed.json()["audit"]["provider"] == "openai_cli"
    assert before.json()["configured"] is True
    assert "person" in {
        item["id"] for item in before.json()["resolved"]["types"]
    }
    assert confirmed.status_code == 200
    assert after.json()["configured"] is True
    assert [item["id"] for item in after.json()["resolved"]["types"]] == [
        "person",
        "professional",
    ]
    assert registry_store.agent_types() is not None

