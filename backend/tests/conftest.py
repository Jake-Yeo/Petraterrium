import os
import tempfile
from importlib import import_module
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_IMPORT_RUNTIME = tempfile.TemporaryDirectory(prefix="petraterrium-test-import-")
_IMPORT_RUNTIME_PATH = Path(_IMPORT_RUNTIME.name)
os.environ["PETRATERRIUM_ATLAS_PATH"] = str(_IMPORT_RUNTIME_PATH / "atlas.sqlite3")
os.environ["PETRATERRIUM_SIMULATION_REGISTRY_PATH"] = str(
    _IMPORT_RUNTIME_PATH / "simulation-registry.json"
)
os.environ["PETRATERRIUM_SIMULATION_RUNS_PATH"] = str(
    _IMPORT_RUNTIME_PATH / "simulation-runs.sqlite3"
)
os.environ["PETRATERRIUM_AI_SETTINGS_PATH"] = str(
    _IMPORT_RUNTIME_PATH / "ai-settings.json"
)

create_app = import_module("petraterrium.main").create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PETRATERRIUM_SIMULATION_REGISTRY_PATH",
        str(tmp_path / "simulation-registry.json"),
    )
    monkeypatch.setenv(
        "PETRATERRIUM_SIMULATION_RUNS_PATH",
        str(tmp_path / "simulation-runs.sqlite3"),
    )
    monkeypatch.setenv("PETRATERRIUM_AI_SETTINGS_PATH", str(tmp_path / "ai-settings.json"))
    with TestClient(create_app(atlas_path=tmp_path / "atlas.sqlite3")) as test_client:
        yield test_client
