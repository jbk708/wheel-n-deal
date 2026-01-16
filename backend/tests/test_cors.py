from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from config import Settings


@pytest.fixture
def mock_services():
    """Mock external services to prevent startup errors."""
    with (
        patch("main.init_db"),
        patch("main.listen_to_group"),
        patch("main.make_server"),
    ):
        yield


@pytest.fixture
def client(mock_services):
    """Create test client with mocked services."""
    from main import app

    return TestClient(app)


def test_cors_allows_configured_origin(client):
    """Test that CORS allows requests from configured origins."""
    response = client.options(
        "/",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "GET" in response.headers.get("access-control-allow-methods", "")


def test_cors_blocks_unconfigured_origin(client):
    """Test that CORS blocks requests from unconfigured origins."""
    response = client.options(
        "/",
        headers={
            "Origin": "http://malicious-site.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.headers.get("access-control-allow-origin") != "http://malicious-site.com"


def test_cors_does_not_allow_wildcard_by_default():
    """Test that CORS does not default to allowing all origins."""
    default_settings = Settings()
    assert "*" not in default_settings.CORS_ORIGINS
