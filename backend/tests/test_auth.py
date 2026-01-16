from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models import User as DBUser
from routers.auth import router
from utils.security import get_password_hash


@pytest.fixture
def app():
    """Create a FastAPI app with the auth router."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/auth")
    return app


@pytest.fixture
def client(app):
    """Create a test client for the app."""
    return TestClient(app)


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    return MagicMock()


@patch("routers.auth.get_db_session")
@patch("routers.auth.get_user_by_email")
@patch("routers.auth.create_user")
def test_register_user_success(mock_create_user, mock_get_user, mock_get_db_session, client):
    """Test successful user registration."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session
    mock_get_user.return_value = None

    mock_user = MagicMock(spec=DBUser)
    mock_user.id = 1
    mock_user.email = "newuser@example.com"
    mock_user.signal_phone = None
    mock_user.signal_username = None
    mock_create_user.return_value = mock_user

    response = client.post(
        "/api/v1/auth/register",
        json={"email": "newuser@example.com", "password": "password123"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["id"] == 1
    mock_create_user.assert_called_once()


@patch("routers.auth.get_db_session")
@patch("routers.auth.get_user_by_email")
def test_register_user_email_exists(mock_get_user, mock_get_db_session, client):
    """Test registration fails when email already exists."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    existing_user = MagicMock(spec=DBUser)
    existing_user.email = "existing@example.com"
    mock_get_user.return_value = existing_user

    response = client.post(
        "/api/v1/auth/register",
        json={"email": "existing@example.com", "password": "password123"},
    )

    assert response.status_code == 400
    assert "Email already registered" in response.json()["detail"]


@patch("routers.auth.get_db_session")
@patch("routers.auth.get_user_by_email")
@patch("routers.auth.create_user")
def test_register_user_database_error(mock_create_user, mock_get_user, mock_get_db_session, client):
    """Test registration handles database errors."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session
    mock_get_user.return_value = None
    mock_create_user.side_effect = Exception("Database error")

    response = client.post(
        "/api/v1/auth/register",
        json={"email": "newuser@example.com", "password": "password123"},
    )

    assert response.status_code == 500
    assert "Error registering user" in response.json()["detail"]
    mock_session.rollback.assert_called_once()


@patch("routers.auth.get_db_session")
@patch("routers.auth.authenticate_user_db")
def test_login_success(mock_auth_user, mock_get_db_session, client):
    """Test successful login."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_user = MagicMock(spec=DBUser)
    mock_user.email = "user@example.com"
    mock_user.password_hash = get_password_hash("correctpassword")
    mock_auth_user.return_value = mock_user

    response = client.post(
        "/api/v1/auth/token",
        data={"username": "user@example.com", "password": "correctpassword"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


@patch("routers.auth.get_db_session")
@patch("routers.auth.authenticate_user_db")
def test_login_invalid_credentials(mock_auth_user, mock_get_db_session, client):
    """Test login fails with invalid credentials."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session
    mock_auth_user.return_value = None

    response = client.post(
        "/api/v1/auth/token",
        data={"username": "user@example.com", "password": "wrongpassword"},
    )

    assert response.status_code == 401
    assert "Incorrect email or password" in response.json()["detail"]


@patch("utils.security.get_db_session")
@patch("utils.security.get_user_by_email")
def test_read_users_me(mock_get_user, mock_get_db_session, client):
    """Test getting current user info."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_user = MagicMock(spec=DBUser)
    mock_user.id = 1
    mock_user.email = "user@example.com"
    mock_user.signal_phone = "+1234567890"
    mock_user.signal_username = "testuser"
    mock_get_user.return_value = mock_user

    from utils.security import create_access_token

    token = create_access_token({"sub": "user@example.com"})

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "user@example.com"
    assert data["id"] == 1


def test_read_users_me_unauthorized(client):
    """Test /me endpoint returns 401 without token."""
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
