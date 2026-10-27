import ctypes
import json
import os
import sys
import tempfile
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Protocol

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

AISource = Literal["openai_cli", "openai_api"]


class AISettingsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StoredAISettings(AISettingsModel):
    schema_version: Literal["1"] = "1"
    source: AISource = "openai_cli"
    cli_command: str = "codex"
    cli_model: str = "gpt-5-mini"
    api_model: str = "gpt-5-mini"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("cli_command", "cli_model", "api_model")
    @classmethod
    def validate_nonempty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("AI command and model values cannot be empty")
        if "\x00" in cleaned or "\n" in cleaned or "\r" in cleaned:
            raise ValueError("AI command and model values must stay on one line")
        return cleaned


class AISettingsUpdate(AISettingsModel):
    source: AISource | None = None
    cli_command: str | None = None
    cli_model: str | None = None
    api_model: str | None = None
    api_key: SecretStr | None = None
    clear_api_key: bool = False

    @field_validator("cli_command", "cli_model", "api_model")
    @classmethod
    def validate_optional_nonempty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("AI command and model values cannot be empty")
        if "\x00" in cleaned or "\n" in cleaned or "\r" in cleaned:
            raise ValueError("AI command and model values must stay on one line")
        return cleaned


class AISettingsView(AISettingsModel):
    source: AISource
    cli_command: str
    cli_model: str
    api_model: str
    api_key_configured: bool
    api_key_storage: str
    updated_at: datetime


class AISourceProvenance(AISettingsModel):
    source: AISource
    source_label: Literal["OpenAI CLI", "OpenAI API"]
    model: str
    generated_at: datetime
    prompt_version: str
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class AIConnectionTest(AISettingsModel):
    ok: bool
    message: str | None = None
    error: str | None = None
    provenance: AISourceProvenance | None = None


class SecretStore(Protocol):
    def get(self) -> str | None: ...

    def set(self, value: str) -> None: ...

    def delete(self) -> None: ...


class AISettingsPersistenceError(RuntimeError):
    pass


class MacOSKeychainSecretStore:
    def __init__(
        self,
        service: str = "Petraterrium OpenAI API",
        account: str = "default",
        security_library: str = (
            "/System/Library/Frameworks/Security.framework/Security"
        ),
        core_foundation_library: str = (
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        ),
    ):
        self.service = service
        self.account = account
        try:
            self.security = ctypes.CDLL(security_library)
            self.core_foundation = ctypes.CDLL(core_foundation_library)
        except OSError as error:
            raise AISettingsPersistenceError(
                f"macOS Keychain framework is unavailable: {error}"
            ) from error
        self._configure_functions()

    @property
    def storage_label(self) -> str:
        return "macOS Keychain"

    def get(self) -> str | None:
        item, value = self._find()
        self._release(item)
        return value

    def set(self, value: str) -> None:
        item, _ = self._find()
        encoded = value.encode()
        try:
            if item:
                status = self.security.SecKeychainItemModifyAttributesAndData(
                    item,
                    None,
                    len(encoded),
                    encoded,
                )
            else:
                service = self.service.encode()
                account = self.account.encode()
                status = self.security.SecKeychainAddGenericPassword(
                    None,
                    len(service),
                    service,
                    len(account),
                    account,
                    len(encoded),
                    encoded,
                    None,
                )
            self._require_success(status, "save")
        finally:
            self._release(item)

    def delete(self) -> None:
        item, _ = self._find()
        if not item:
            return
        try:
            status = self.security.SecKeychainItemDelete(item)
            self._require_success(status, "delete")
        finally:
            self._release(item)

    def _configure_functions(self) -> None:
        self.security.SecKeychainFindGenericPassword.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self.security.SecKeychainFindGenericPassword.restype = ctypes.c_int32
        self.security.SecKeychainAddGenericPassword.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.c_uint32,
            ctypes.c_char_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self.security.SecKeychainAddGenericPassword.restype = ctypes.c_int32
        self.security.SecKeychainItemModifyAttributesAndData.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        self.security.SecKeychainItemModifyAttributesAndData.restype = ctypes.c_int32
        self.security.SecKeychainItemDelete.argtypes = [ctypes.c_void_p]
        self.security.SecKeychainItemDelete.restype = ctypes.c_int32
        self.security.SecKeychainItemFreeContent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        self.security.SecKeychainItemFreeContent.restype = ctypes.c_int32
        self.security.SecCopyErrorMessageString.argtypes = [
            ctypes.c_int32,
            ctypes.c_void_p,
        ]
        self.security.SecCopyErrorMessageString.restype = ctypes.c_void_p
        self.core_foundation.CFStringGetCString.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_long,
            ctypes.c_uint32,
        ]
        self.core_foundation.CFStringGetCString.restype = ctypes.c_bool
        self.core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
        self.core_foundation.CFRelease.restype = None

    def _find(self) -> tuple[ctypes.c_void_p | None, str | None]:
        service = self.service.encode()
        account = self.account.encode()
        password_length = ctypes.c_uint32()
        password_data = ctypes.c_void_p()
        item = ctypes.c_void_p()
        status = self.security.SecKeychainFindGenericPassword(
            None,
            len(service),
            service,
            len(account),
            account,
            ctypes.byref(password_length),
            ctypes.byref(password_data),
            ctypes.byref(item),
        )
        if status == -25300:
            return None, None
        self._require_success(status, "read")
        try:
            value = ctypes.string_at(password_data, password_length.value).decode()
        finally:
            self.security.SecKeychainItemFreeContent(None, password_data)
        return ctypes.c_void_p(item.value), value

    def _require_success(self, status: int, action: str) -> None:
        if status == 0:
            return
        raise AISettingsPersistenceError(
            f"Could not {action} the OpenAI API key in macOS Keychain: "
            f"{self._status_message(status)} (OSStatus {status})"
        )

    def _status_message(self, status: int) -> str:
        message = self.security.SecCopyErrorMessageString(status, None)
        if not message:
            return "Unknown Keychain error"
        try:
            buffer = ctypes.create_string_buffer(1024)
            copied = self.core_foundation.CFStringGetCString(
                message,
                buffer,
                len(buffer),
                0x08000100,
            )
            return buffer.value.decode() if copied else "Unknown Keychain error"
        finally:
            self.core_foundation.CFRelease(message)

    def _release(self, item: ctypes.c_void_p | None) -> None:
        if item:
            self.core_foundation.CFRelease(item)


class UnavailableSecretStore:
    storage_label = "Unavailable"

    def get(self) -> str | None:
        return None

    def set(self, value: str) -> None:
        raise AISettingsPersistenceError(
            "Secure API-key storage is unavailable on this operating system"
        )

    def delete(self) -> None:
        return None


def default_ai_settings_path() -> Path:
    configured = os.getenv("PETRATERRIUM_AI_SETTINGS_PATH")
    if configured:
        return Path(configured).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Petraterrium" / "ai-settings.json"
    config_home = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "petraterrium" / "ai-settings.json"


def default_secret_store() -> SecretStore:
    if sys.platform == "darwin":
        return MacOSKeychainSecretStore()
    return UnavailableSecretStore()


class AISettingsStore:
    def __init__(self, path: Path | str, secret_store: SecretStore):
        self.path = Path(path).expanduser()
        self.secret_store = secret_store
        self._lock = threading.RLock()

    def load(self) -> StoredAISettings:
        with self._lock:
            if not self.path.exists():
                return StoredAISettings()
            try:
                return StoredAISettings.model_validate_json(self.path.read_text())
            except (OSError, ValueError) as error:
                raise AISettingsPersistenceError(
                    f"Could not read AI settings from {self.path}: {error}"
                ) from error

    def api_key(self) -> str | None:
        with self._lock:
            return self.secret_store.get()

    def view(self) -> AISettingsView:
        with self._lock:
            settings = self.load()
            configured = bool(self.secret_store.get())
            storage_label = getattr(self.secret_store, "storage_label", "Secure credential store")
            return AISettingsView(
                source=settings.source,
                cli_command=settings.cli_command,
                cli_model=settings.cli_model,
                api_model=settings.api_model,
                api_key_configured=configured,
                api_key_storage=storage_label,
                updated_at=settings.updated_at,
            )

    def update(self, request: AISettingsUpdate) -> AISettingsView:
        with self._lock:
            current = self.load()
            values = current.model_dump()
            for field_name in ("source", "cli_command", "cli_model", "api_model"):
                value = getattr(request, field_name)
                if value is not None:
                    values[field_name] = value
            values["updated_at"] = datetime.now(UTC)
            updated = StoredAISettings.model_validate(values)
            if request.clear_api_key:
                self.secret_store.delete()
            elif request.api_key is not None:
                secret = request.api_key.get_secret_value().strip()
                if not secret:
                    raise AISettingsPersistenceError("The OpenAI API key cannot be empty")
                self.secret_store.set(secret)
            self._write(updated)
            return self.view()

    def _write(self, settings: StoredAISettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = json.dumps(settings.model_dump(mode="json"), indent=2) + "\n"
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                dir=self.path.parent,
                prefix=".ai-settings-",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                os.chmod(temporary_path, 0o600)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
            os.chmod(self.path, 0o600)
        except OSError as error:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise AISettingsPersistenceError(
                f"Could not save AI settings to {self.path}: {error}"
            ) from error


@lru_cache(maxsize=1)
def default_ai_settings_store() -> AISettingsStore:
    return AISettingsStore(default_ai_settings_path(), default_secret_store())


ProviderFactory = Callable[[AISettingsStore], Any]


def create_ai_settings_router(
    store: AISettingsStore | None = None,
    provider_factory: ProviderFactory | None = None,
) -> APIRouter:
    settings_store = store or default_ai_settings_store()
    router = APIRouter(prefix="/settings/ai", tags=["AI settings"])

    @router.get("", response_model=AISettingsView)
    def get_settings() -> AISettingsView:
        try:
            return settings_store.view()
        except AISettingsPersistenceError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @router.patch("", response_model=AISettingsView)
    def save_settings(request: AISettingsUpdate) -> AISettingsView:
        try:
            return settings_store.update(request)
        except AISettingsPersistenceError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/test", response_model=AIConnectionTest)
    def test_settings() -> AIConnectionTest:
        if provider_factory is None:
            from .llm_gateway import SelectedAIProvider

            provider = SelectedAIProvider(settings_store)
        else:
            provider = provider_factory(settings_store)
        return provider.test_connection()

    return router
