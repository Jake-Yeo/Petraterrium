import pytest
from fastapi.testclient import TestClient

from petraterrium.main import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client
