import json
import shlex
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from petraterrium.ai_provider import AIGeneration, AIProviderError
from petraterrium.ai_settings import (
    AIConnectionTest,
    AISettingsStore,
    AISettingsUpdate,
    AISourceProvenance,
)
from petraterrium.atlas import llm
from petraterrium.atlas.contracts import ColumnMapping, MappingProposal
from petraterrium.atlas.database import AtlasStore
from petraterrium.leaders import LeaderActionProposal
from petraterrium.main import create_app

SMOKE_PATH = Path(__file__).resolve().parents[2] / "shared" / "dsl-schema" / "smoke-spread.json"


class MemorySecretStore:
    storage_label = "Test memory"

    def __init__(self):
        self.value: str | None = None

    def get(self) -> str | None:
        return self.value

    def set(self, value: str) -> None:
        self.value = value

    def delete(self) -> None:
        self.value = None


def provenance() -> AISourceProvenance:
    return AISourceProvenance(
        source="openai_cli",
        source_label="OpenAI CLI",
        model="test-cli-model",
        generated_at="2026-10-27T12:00:00Z",
        prompt_version="test-v1",
    )


class FailingProvider:
    def generate_structured(self, *args, **kwargs):
        raise AIProviderError("cli_failed", "Selected OpenAI CLI failed exactly")

    def test_connection(self) -> AIConnectionTest:
        return AIConnectionTest(ok=False, error="Selected OpenAI CLI failed exactly")


class MappingProvider:
    def generate_structured(self, *args, **kwargs):
        return AIGeneration(
            output=MappingProposal(
                mappings=[
                    ColumnMapping(
                        column="hh_mean",
                        target="household_size",
                        ambiguous=False,
                        reason="Proposed mean",
                    )
                ]
            ),
            provenance=provenance(),
        )


class WorkflowProvider:
    def generate_structured(self, *args, **kwargs):
        return AIGeneration(
            output=LeaderActionProposal(
                action="public-address",
                target="Northport",
                parameters={"spread_rate": -0.02},
            ),
            provenance=provenance(),
        )

    def generate_text(self, *args, **kwargs):
        return AIGeneration(
            output="Recorded-state narration",
            provenance=provenance(),
        )

    def test_connection(self) -> AIConnectionTest:
        return AIConnectionTest(ok=True, provenance=provenance())


def settings_store(path: Path) -> AISettingsStore:
    return AISettingsStore(path, MemorySecretStore())


def graph_cli_command(tmp_path: Path) -> str:
    script = tmp_path / "graph-cli.py"
    output = json.dumps(
        {
            "name": "Reviewed social choice",
            "entry_label": "Decide",
            "nodes": [
                {
                    "label": "Decide",
                    "terminal": False,
                    "source_excerpt": "decides whether to stay home",
                },
                {
                    "label": "Stay home",
                    "terminal": True,
                    "source_excerpt": "stay home",
                },
            ],
            "transitions": [
                {
                    "from_label": "Decide",
                    "to_label": "Stay home",
                    "probability": None,
                    "condition": None,
                    "source_excerpt": "decides whether to stay home",
                }
            ],
        }
    )
    script.write_text(
        "\n".join(
            [
                "import pathlib",
                "import sys",
                "sys.stdin.read()",
                "path = pathlib.Path(sys.argv[sys.argv.index('--output-last-message') + 1])",
                f"path.write_text({output!r})",
            ]
        )
    )
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"


def test_markov_ai_failure_surfaces_without_a_parser_fallback(tmp_path):
    application = create_app(
        atlas_path=tmp_path / "atlas.sqlite3",
        ai_settings_store=settings_store(tmp_path / "ai-settings.json"),
        ai_provider=FailingProvider(),
    )

    with TestClient(application) as client:
        response = client.post(
            "/markov-builder/proposals",
            json={"text": "An agent decides whether to stay home or go out", "use_llm": True},
        )
        manual = client.post(
            "/markov-builder/proposals",
            json={"text": "An agent decides whether to stay home or go out", "use_llm": False},
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "Selected OpenAI CLI failed exactly"
    assert manual.status_code == 200
    assert manual.json()["audit"]["provider"] == "deterministic-parser"


def test_atlas_mapping_uses_the_selected_source_and_records_provenance(tmp_path):
    store = AtlasStore(tmp_path / "atlas.sqlite3")

    mappings, audit = llm.propose_mapping(
        store,
        "run-a",
        ["hh_mean"],
        [{"hh_mean": 2}],
        True,
        MappingProvider(),
    )

    assert mappings[0].target == "household_size"
    assert audit.provider == "openai_cli"
    assert audit.model == "test-cli-model"


def test_leader_and_narration_workflows_use_selected_source_with_provenance(tmp_path):
    application = create_app(
        atlas_path=tmp_path / "atlas.sqlite3",
        ai_settings_store=settings_store(tmp_path / "ai-settings.json"),
        ai_provider=WorkflowProvider(),
    )
    dsl = json.loads(SMOKE_PATH.read_text())

    with TestClient(application) as client:
        leader = client.post(
            "/ai-features/leader-decision",
            json={
                "leader": {"id": "mayor"},
                "aggregated_state": {"Northport": {"aware": 14}},
                "week": 2,
                "dsl": dsl,
            },
        )
        narration = client.post(
            "/ai-features/narration",
            json={
                "narrator": {"id": "local-reporter"},
                "recorded_context": {"run_id": "run-1", "day": 7},
            },
        )

    assert leader.status_code == 200
    assert leader.json()["action"] == "public-address"
    assert leader.json()["ai_provenance"]["source"] == "openai_cli"
    assert narration.status_code == 200
    assert narration.json()["text"] == "Recorded-state narration"
    assert narration.json()["ai_provenance"]["model"] == "test-cli-model"


def test_leader_workflow_surfaces_selected_source_failure_without_fallback(tmp_path):
    application = create_app(
        atlas_path=tmp_path / "atlas.sqlite3",
        ai_settings_store=settings_store(tmp_path / "ai-settings.json"),
        ai_provider=FailingProvider(),
    )

    with TestClient(application) as client:
        response = client.post(
            "/ai-features/leader-decision",
            json={
                "leader": {"id": "mayor"},
                "aggregated_state": {},
                "week": 0,
                "dsl": json.loads(SMOKE_PATH.read_text()),
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "Selected OpenAI CLI failed exactly"


def test_feature_endpoint_tracks_live_source_switches_without_fallback(tmp_path):
    store = settings_store(tmp_path / "ai-settings.json")
    store.update(
        AISettingsUpdate(
            source="openai_cli",
            cli_command=graph_cli_command(tmp_path),
            cli_model="cli-feature-model",
            api_model="api-feature-model",
        )
    )
    application = create_app(
        atlas_path=tmp_path / "atlas.sqlite3",
        ai_settings_store=store,
    )

    with TestClient(application) as client:
        first = client.post(
            "/markov-builder/proposals",
            json={"text": "Agent chooses home unique one", "use_llm": True},
        )
        client.patch("/settings/ai", json={"source": "openai_api"})
        missing_key = client.post(
            "/markov-builder/proposals",
            json={"text": "Agent chooses home unique two", "use_llm": True},
        )
        client.patch("/settings/ai", json={"source": "openai_cli"})
        restored = client.post(
            "/markov-builder/proposals",
            json={"text": "Agent chooses home unique three", "use_llm": True},
        )

    assert first.status_code == 200
    assert first.json()["audit"]["provider"] == "openai_cli"
    assert first.json()["audit"]["model"] == "cli-feature-model"
    assert missing_key.status_code == 502
    assert missing_key.json()["detail"].endswith("no fallback was attempted.")
    assert restored.status_code == 200
    assert restored.json()["audit"]["provider"] == "openai_cli"


def test_corrupt_persisted_ai_settings_surface_as_feature_error(tmp_path):
    settings_path = tmp_path / "ai-settings.json"
    settings_path.write_text("{")
    application = create_app(
        atlas_path=tmp_path / "atlas.sqlite3",
        ai_settings_store=settings_store(settings_path),
    )

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.post(
            "/markov-builder/proposals",
            json={"text": "Agent chooses home corrupt settings", "use_llm": True},
        )

    assert response.status_code == 502
    assert "AI settings are unavailable" in response.json()["detail"]

