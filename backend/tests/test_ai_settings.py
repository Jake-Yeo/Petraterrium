import json
import shlex
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from petraterrium.ai_provider import AIProviderError, SelectedAIProvider
from petraterrium.ai_settings import (
    AISettingsStore,
    AISettingsUpdate,
    create_ai_settings_router,
)


class MemorySecretStore:
    def __init__(self):
        self.value = None

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def delete(self):
        self.value = None


def fake_command(tmp_path: Path, output: str, exit_code: int = 0, error: str = "") -> str:
    script = tmp_path / f"fake_cli_{len(list(tmp_path.glob('fake_cli_*.py')))}.py"
    invocation_log = tmp_path / "cli-invocations.jsonl"
    script.write_text(
        "\n".join(
            [
                "import json",
                "import os",
                "import pathlib",
                "import sys",
                f"log = pathlib.Path({str(invocation_log)!r})",
                "entry = {'argv': sys.argv[1:], 'prompt': sys.stdin.read(), "
                "'api_key_visible': bool(os.getenv('OPENAI_API_KEY'))}",
                "with log.open('a') as stream:",
                "    stream.write(json.dumps(entry) + '\\n')",
                f"error = {error!r}",
                "if error:",
                "    sys.stderr.write(error)",
                f"if {exit_code} == 0:",
                "    output_path = pathlib.Path("
                "sys.argv[sys.argv.index('--output-last-message') + 1])",
                f"    output_path.write_text({output!r})",
                f"raise SystemExit({exit_code})",
            ]
        )
    )
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"


def settings_store(tmp_path: Path) -> tuple[AISettingsStore, MemorySecretStore]:
    secrets = MemorySecretStore()
    return AISettingsStore(tmp_path / "ai-settings.json", secrets), secrets


def update_cli(store: AISettingsStore, command: str, model: str = "cli-test-model"):
    return store.update(
        AISettingsUpdate(
            source="openai_cli",
            cli_command=command,
            cli_model=model,
            api_model="api-test-model",
        )
    )


def test_settings_persist_without_writing_or_returning_api_key(tmp_path):
    store, secrets = settings_store(tmp_path)
    view = store.update(
        AISettingsUpdate(
            source="openai_api",
            cli_command="codex",
            cli_model="cli-model",
            api_model="api-model",
            api_key="sk-test-secret",
        )
    )

    stored = (tmp_path / "ai-settings.json").read_text()
    assert "sk-test-secret" not in stored
    assert "api_key" not in stored
    assert view.api_key_configured is True
    assert "secret" not in json.dumps(view.model_dump(mode="json"))
    assert secrets.value == "sk-test-secret"
    assert oct((tmp_path / "ai-settings.json").stat().st_mode & 0o777) == "0o600"

    reloaded = AISettingsStore(tmp_path / "ai-settings.json", secrets)
    assert reloaded.view().source == "openai_api"
    assert reloaded.view().api_model == "api-model"


def test_cli_generation_uses_existing_login_environment_without_app_api_key(
    tmp_path, monkeypatch
):
    store, _ = settings_store(tmp_path)
    command = fake_command(tmp_path, "proposal created")
    update_cli(store, command)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-cli")

    result = SelectedAIProvider(store).generate_text(
        "Propose one agent type.",
        system_prompt="Return only the proposal.",
        prompt_version="agent-type-v1",
    )

    assert result.output == "proposal created"
    assert result.provenance.source == "openai_cli"
    assert result.provenance.source_label == "OpenAI CLI"
    assert result.provenance.model == "cli-test-model"
    invocation = json.loads((tmp_path / "cli-invocations.jsonl").read_text())
    assert invocation["api_key_visible"] is False
    assert "exec" in invocation["argv"]
    assert "--ephemeral" in invocation["argv"]
    assert "--ask-for-approval" not in invocation["argv"]
    assert invocation["argv"][invocation["argv"].index("--model") + 1] == "cli-test-model"


def test_selected_source_never_falls_back_between_cli_and_api(tmp_path):
    store, _ = settings_store(tmp_path)
    command = fake_command(tmp_path, "PETRATERRIUM_AI_TEST_OK")
    update_cli(store, command)
    provider = SelectedAIProvider(store)

    first = provider.test_connection()
    assert first.ok is True
    assert first.provenance is not None
    assert first.provenance.source == "openai_cli"
    assert len((tmp_path / "cli-invocations.jsonl").read_text().splitlines()) == 1

    store.update(AISettingsUpdate(source="openai_api"))
    second = provider.test_connection()
    assert second.ok is False
    assert second.error == (
        "OpenAI API key is not configured. Save a key in AI Settings; "
        "no fallback was attempted."
    )
    assert len((tmp_path / "cli-invocations.jsonl").read_text().splitlines()) == 1

    store.update(AISettingsUpdate(source="openai_cli"))
    third = provider.test_connection()
    assert third.ok is True
    assert third.provenance is not None
    assert third.provenance.source == "openai_cli"
    assert len((tmp_path / "cli-invocations.jsonl").read_text().splitlines()) == 2


def test_api_generation_uses_only_the_secure_key_and_records_api_provenance(tmp_path):
    store, secrets = settings_store(tmp_path)
    secrets.set("sk-secure-test")
    store.update(
        AISettingsUpdate(
            source="openai_api",
            api_model="api-provenance-model",
        )
    )
    captured = {}

    class Responses:
        def create(self, **kwargs):
            captured["request"] = kwargs
            usage = type("Usage", (), {"input_tokens": 5, "output_tokens": 2})()
            return type(
                "Response",
                (),
                {"output_text": "proposal created", "usage": usage},
            )()

    class Client:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.responses = Responses()

    result = SelectedAIProvider(store, api_client_factory=Client).generate_text(
        "Propose an agent type.",
        prompt_version="api-proposal-v1",
    )

    assert result.output == "proposal created"
    assert result.provenance.source == "openai_api"
    assert result.provenance.source_label == "OpenAI API"
    assert result.provenance.model == "api-provenance-model"
    assert result.provenance.input_tokens == 5
    assert captured["client"]["api_key"] == "sk-secure-test"
    assert captured["request"]["store"] is False


def test_cli_failure_preserves_exact_diagnostic_and_does_not_call_api(tmp_path):
    store, _ = settings_store(tmp_path)
    command = fake_command(tmp_path, "", exit_code=17, error="not logged in: run codex login")
    update_cli(store, command)
    api_calls = []

    with pytest.raises(AIProviderError) as failure:
        provider = SelectedAIProvider(
            store, api_client_factory=lambda **kwargs: api_calls.append(kwargs)
        )
        provider.generate_text("test", prompt_version="failure-v1")

    assert str(failure.value) == (
        "OpenAI CLI exited with status 17: not logged in: run codex login"
    )
    assert api_calls == []


def test_cli_missing_binary_reports_configured_command_exactly(tmp_path):
    store, _ = settings_store(tmp_path)
    update_cli(store, "/definitely/missing/petraterrium-codex")

    result = SelectedAIProvider(store).test_connection()

    assert result.ok is False
    assert result.error == (
        "OpenAI CLI not installed: command not found: "
        "/definitely/missing/petraterrium-codex"
    )


def test_structured_cli_output_is_validated_and_carries_provenance(tmp_path):
    class Proposal(BaseModel):
        name: str

    store, _ = settings_store(tmp_path)
    command = fake_command(tmp_path, '{"name":"FamilyMan"}')
    update_cli(store, command)

    result = SelectedAIProvider(store).generate_structured(
        "Propose one type.",
        Proposal,
        system_prompt="Return a proposal.",
        prompt_version="structured-v1",
    )

    assert result.output == Proposal(name="FamilyMan")
    assert result.provenance.prompt_version == "structured-v1"
    invocation = json.loads((tmp_path / "cli-invocations.jsonl").read_text())
    assert "--output-schema" in invocation["argv"]


def test_structured_cli_schema_requires_nullable_fields_at_every_object_level(tmp_path):
    class Node(BaseModel):
        label: str
        source_excerpt: str | None = None

    class Proposal(BaseModel):
        name: str
        entry_label: str | None = None
        nodes: list[Node]

    captured = {}

    class CapturingProvider(SelectedAIProvider):
        def _run_cli(
            self,
            settings,
            system_prompt,
            user_prompt,
            response_schema=None,
        ):
            captured["schema"] = response_schema
            return json.dumps(
                {
                    "name": "Daily decision",
                    "entry_label": None,
                    "nodes": [{"label": "Stay home", "source_excerpt": None}],
                }
            )

    store, _ = settings_store(tmp_path)
    update_cli(store, "unused-cli")

    result = CapturingProvider(store).generate_structured(
        "Propose one chain.",
        Proposal,
        system_prompt="Return a proposal.",
        prompt_version="strict-schema-v1",
    )

    schema = captured["schema"]
    assert schema["required"] == ["name", "entry_label", "nodes"]
    assert schema["$defs"]["Node"]["required"] == ["label", "source_excerpt"]
    assert {"type": "null"} in schema["properties"]["entry_label"]["anyOf"]
    assert result.output.entry_label is None
    assert result.output.nodes[0].source_excerpt is None


def test_settings_router_exposes_redacted_persistence_and_exact_test_result(tmp_path):
    store, _ = settings_store(tmp_path)
    command = fake_command(tmp_path, "PETRATERRIUM_AI_TEST_OK")
    application = FastAPI()
    application.include_router(create_ai_settings_router(store))

    with TestClient(application) as client:
        saved = client.patch(
            "/settings/ai",
            json={
                "source": "openai_cli",
                "cli_command": command,
                "cli_model": "cli-test-model",
                "api_model": "api-test-model",
                "api_key": "sk-router-secret",
            },
        )
        assert saved.status_code == 200
        assert saved.json()["api_key_configured"] is True
        assert "sk-router-secret" not in saved.text

        tested = client.post("/settings/ai/test")
        assert tested.status_code == 200
        assert tested.json()["ok"] is True
        assert tested.json()["provenance"]["source_label"] == "OpenAI CLI"

        loaded = client.get("/settings/ai")
        assert loaded.json()["source"] == "openai_cli"
        assert "sk-router-secret" not in loaded.text
