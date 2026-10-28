import json
import os
import shlex
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import ValidationError

from .ai_settings import (
    AIConnectionTest,
    AISettingsPersistenceError,
    AISettingsStore,
    AISourceProvenance,
    StoredAISettings,
)

OutputT = TypeVar("OutputT")
TEST_SENTINEL = "PETRATERRIUM_AI_TEST_OK"


def _strict_output_schema(value: Any) -> Any:
    if isinstance(value, list):
        return [_strict_output_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    schema = {key: _strict_output_schema(item) for key, item in value.items()}
    properties = schema.get("properties")
    if isinstance(properties, dict):
        schema["required"] = list(properties)
    if schema.get("type") == "object":
        schema.setdefault("additionalProperties", False)
    if schema.get("default", ...) is None:
        schema.pop("default")
    return schema


class AIProviderError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AIGeneration[OutputT]:
    output: OutputT
    provenance: AISourceProvenance


class SelectedAIProvider:
    def __init__(
        self,
        settings_store: AISettingsStore,
        api_client_factory: Callable[..., Any] | None = None,
        command_timeout_seconds: float = 120,
    ):
        self.settings_store = settings_store
        self.api_client_factory = api_client_factory
        self.command_timeout_seconds = command_timeout_seconds

    def selected_identity(self) -> tuple[str, str]:
        settings = self._settings()
        model = settings.cli_model if settings.source == "openai_cli" else settings.api_model
        return settings.source, model

    def generate_text(
        self,
        user_prompt: str,
        *,
        system_prompt: str = "Return only the requested result.",
        prompt_version: str,
    ) -> AIGeneration[str]:
        settings = self._settings()
        if settings.source == "openai_cli":
            output = self._run_cli(settings, system_prompt, user_prompt)
            return AIGeneration(
                output=output,
                provenance=self._provenance(settings, prompt_version),
            )
        return self._run_api_text(settings, system_prompt, user_prompt, prompt_version)

    def generate_structured(
        self,
        user_prompt: str,
        response_format: type[OutputT],
        *,
        system_prompt: str,
        prompt_version: str,
    ) -> AIGeneration[OutputT]:
        settings = self._settings()
        if settings.source == "openai_cli":
            raw = self._run_cli(
                settings,
                system_prompt,
                user_prompt,
                response_schema=_strict_output_schema(response_format.model_json_schema()),
            )
            try:
                parsed = response_format.model_validate_json(raw)
            except (ValidationError, ValueError) as error:
                raise AIProviderError(
                    "invalid_structured_output",
                    f"OpenAI CLI returned invalid structured output: {error}",
                ) from error
            return AIGeneration(
                output=parsed,
                provenance=self._provenance(settings, prompt_version),
            )
        return self._run_api_structured(
            settings,
            system_prompt,
            user_prompt,
            response_format,
            prompt_version,
        )

    def test_connection(self) -> AIConnectionTest:
        try:
            result = self.generate_text(
                f"Reply with exactly {TEST_SENTINEL}",
                system_prompt="Follow the response format exactly and return no other text.",
                prompt_version="ai-settings-test-v1",
            )
            if TEST_SENTINEL not in result.output:
                raise AIProviderError(
                    "unexpected_test_response",
                    f"AI source returned an unexpected test response: {result.output}",
                )
            return AIConnectionTest(
                ok=True,
                message=f"Connected through {result.provenance.source_label}",
                provenance=result.provenance,
            )
        except (AIProviderError, AISettingsPersistenceError) as error:
            return AIConnectionTest(ok=False, error=str(error))

    def _run_cli(
        self,
        settings: StoredAISettings,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict[str, Any] | None = None,
    ) -> str:
        try:
            command = shlex.split(settings.cli_command)
        except ValueError as error:
            raise AIProviderError(
                "invalid_cli_command",
                f"OpenAI CLI command is invalid: {error}",
            ) from error
        if not command:
            raise AIProviderError("invalid_cli_command", "OpenAI CLI command is empty")
        if "exec" not in command[1:]:
            command.append("exec")
        with tempfile.TemporaryDirectory(prefix="petraterrium-ai-") as directory:
            workspace = Path(directory)
            output_path = workspace / "response.txt"
            command.extend(
                [
                    "--ephemeral",
                    "--skip-git-repo-check",
                    "--sandbox",
                    "read-only",
                    "--color",
                    "never",
                    "--model",
                    settings.cli_model,
                    "--output-last-message",
                    str(output_path),
                ]
            )
            if response_schema is not None:
                schema_path = workspace / "response-schema.json"
                schema_path.write_text(json.dumps(response_schema))
                command.extend(["--output-schema", str(schema_path)])
            command.append("-")
            prompt = f"System instructions:\n{system_prompt}\n\nUser input:\n{user_prompt}\n"
            environment = os.environ.copy()
            environment.pop("OPENAI_API_KEY", None)
            try:
                completed = subprocess.run(
                    command,
                    input=prompt,
                    capture_output=True,
                    text=True,
                    timeout=self.command_timeout_seconds,
                    check=False,
                    cwd=workspace,
                    env=environment,
                )
            except FileNotFoundError as error:
                raise AIProviderError(
                    "cli_not_installed",
                    f"OpenAI CLI not installed: command not found: {command[0]}",
                ) from error
            except PermissionError as error:
                raise AIProviderError(
                    "cli_not_executable",
                    f"OpenAI CLI is not executable: {command[0]}",
                ) from error
            except subprocess.TimeoutExpired as error:
                raise AIProviderError(
                    "cli_timeout",
                    f"OpenAI CLI timed out after {self.command_timeout_seconds:g} seconds",
                ) from error
            if completed.returncode != 0:
                diagnostic = completed.stderr.strip() or completed.stdout.strip()
                if not diagnostic:
                    diagnostic = "no diagnostic output"
                raise AIProviderError(
                    "cli_failed",
                    f"OpenAI CLI exited with status {completed.returncode}: {diagnostic}",
                )
            if not output_path.exists():
                raise AIProviderError(
                    "cli_missing_output",
                    "OpenAI CLI completed without writing its final response",
                )
            output = output_path.read_text().strip()
            if not output:
                raise AIProviderError(
                    "cli_empty_output",
                    "OpenAI CLI completed with an empty final response",
                )
            return output

    def _settings(self) -> StoredAISettings:
        try:
            return self.settings_store.load()
        except AISettingsPersistenceError as error:
            raise AIProviderError(
                "settings_unavailable",
                f"AI settings are unavailable: {error}",
            ) from error

    def _run_api_text(
        self,
        settings: StoredAISettings,
        system_prompt: str,
        user_prompt: str,
        prompt_version: str,
    ) -> AIGeneration[str]:
        client = self._api_client()
        try:
            response = client.responses.create(
                model=settings.api_model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                store=False,
            )
        except Exception as error:
            raise AIProviderError("api_failed", f"OpenAI API failed: {error}") from error
        output = str(getattr(response, "output_text", "")).strip()
        if not output:
            raise AIProviderError("api_empty_output", "OpenAI API returned an empty response")
        return AIGeneration(
            output=output,
            provenance=self._provenance(
                settings,
                prompt_version,
                getattr(response, "usage", None),
            ),
        )

    def _run_api_structured(
        self,
        settings: StoredAISettings,
        system_prompt: str,
        user_prompt: str,
        response_format: type[OutputT],
        prompt_version: str,
    ) -> AIGeneration[OutputT]:
        client = self._api_client()
        try:
            response = client.responses.parse(
                model=settings.api_model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                text_format=response_format,
                store=False,
            )
        except Exception as error:
            raise AIProviderError("api_failed", f"OpenAI API failed: {error}") from error
        if response.output_parsed is None:
            raise AIProviderError(
                "api_invalid_structured_output",
                "OpenAI API did not return a structured response",
            )
        return AIGeneration(
            output=response.output_parsed,
            provenance=self._provenance(
                settings,
                prompt_version,
                getattr(response, "usage", None),
            ),
        )

    def _api_client(self):
        try:
            api_key = self.settings_store.api_key()
        except AISettingsPersistenceError as error:
            raise AIProviderError(
                "settings_unavailable",
                f"AI settings are unavailable: {error}",
            ) from error
        if not api_key:
            raise AIProviderError(
                "api_key_missing",
                "OpenAI API key is not configured. Save a key in AI Settings; "
                "no fallback was attempted.",
            )
        if self.api_client_factory is None:
            from openai import OpenAI

            factory = OpenAI
        else:
            factory = self.api_client_factory
        try:
            return factory(
                api_key=api_key,
                timeout=self.command_timeout_seconds,
                max_retries=0,
            )
        except Exception as error:
            raise AIProviderError(
                "api_client_failed",
                f"OpenAI API client could not be created: {error}",
            ) from error

    def _provenance(
        self,
        settings: StoredAISettings,
        prompt_version: str,
        usage: Any | None = None,
    ) -> AISourceProvenance:
        is_cli = settings.source == "openai_cli"
        return AISourceProvenance(
            source=settings.source,
            source_label="OpenAI CLI" if is_cli else "OpenAI API",
            model=settings.cli_model if is_cli else settings.api_model,
            generated_at=datetime.now(UTC),
            prompt_version=prompt_version,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )


def selected_provider_identity(provider: Any) -> tuple[str, str]:
    identity = getattr(provider, "selected_identity", None)
    if callable(identity):
        return identity()
    settings_store = getattr(provider, "settings_store", None)
    if settings_store is None:
        return type(provider).__name__, "configured"
    try:
        settings = settings_store.load()
    except AISettingsPersistenceError as error:
        raise AIProviderError(
            "settings_unavailable",
            f"AI settings are unavailable: {error}",
        ) from error
    model = settings.cli_model if settings.source == "openai_cli" else settings.api_model
    return settings.source, model
