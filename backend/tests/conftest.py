import pytest
from fastapi.testclient import TestClient

from petraterrium.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(atlas_path=tmp_path / "atlas.sqlite3")) as test_client:
        yield test_client
