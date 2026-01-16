from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from jose import jwt

from utils.security import (
    ALGORITHM,
    SECRET_KEY,
    authenticate_user_db,
    block_ip,
    create_access_token,
    create_user,
    get_current_active_user,
    get_current_user,
    get_password_hash,
    get_user_by_email,
    is_ip_blocked,
    setup_security,
    verify_password,
)


def test_password_hashing():
    """Test that password hashing and verification work correctly."""
    password = "testpassword"
    hashed = get_password_hash(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrongpassword", hashed) is False


def test_get_user_by_email():
    """Test retrieving a user by email from the database."""
    mock_session = MagicMock()
    mock_user = MagicMock()
    mock_user.email = "test@example.com"

    mock_session.query.return_value.filter.return_value.first.return_value = mock_user

    user = get_user_by_email(mock_session, "test@example.com")
    assert user is not None
    assert user.email == "test@example.com"

    mock_session.query.return_value.filter.return_value.first.return_value = None
    user = get_user_by_email(mock_session, "nonexistent@example.com")
    assert user is None


def test_authenticate_user_db():
    """Test user authentication against the database."""
    mock_session = MagicMock()
    mock_user = MagicMock()
    mock_user.email = "test@example.com"
    mock_user.password_hash = get_password_hash("correctpassword")

    mock_session.query.return_value.filter.return_value.first.return_value = mock_user

    user = authenticate_user_db(mock_session, "test@example.com", "correctpassword")
    assert user is not None
    assert user.email == "test@example.com"

    user = authenticate_user_db(mock_session, "test@example.com", "wrongpassword")
    assert user is None

    mock_session.query.return_value.filter.return_value.first.return_value = None
    user = authenticate_user_db(mock_session, "nonexistent@example.com", "password")
    assert user is None


def test_authenticate_user_db_no_password():
    """Test authentication fails for users without password (Signal-only users)."""
    mock_session = MagicMock()
    mock_user = MagicMock()
    mock_user.email = "signal@example.com"
    mock_user.password_hash = None

    mock_session.query.return_value.filter.return_value.first.return_value = mock_user

    user = authenticate_user_db(mock_session, "signal@example.com", "anypassword")
    assert user is None


def test_create_user():
    """Test creating a new user in the database."""
    mock_session = MagicMock()

    create_user(mock_session, "new@example.com", "password123")

    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()
    mock_session.refresh.assert_called_once()

    added_user = mock_session.add.call_args[0][0]
    assert added_user.email == "new@example.com"
    assert added_user.password_hash is not None
    assert verify_password("password123", added_user.password_hash)


def test_create_access_token():
    """Test creating an access token."""
    data = {"sub": "test@example.com"}

    token = create_access_token(data)
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "test@example.com"
    assert "exp" in payload

    token = create_access_token(data, expires_delta=timedelta(minutes=30))
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "test@example.com"
    assert "exp" in payload


@pytest.mark.asyncio
async def test_get_current_user():
    """Test getting the current user from a token."""
    mock_user = MagicMock()
    mock_user.email = "test@example.com"

    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.first.return_value = mock_user

    token = create_access_token({"sub": "test@example.com"})

    with (
        patch("utils.security.oauth2_scheme", return_value=token),
        patch("utils.security.get_db_session", return_value=mock_session),
    ):
        user = await get_current_user(token)
        assert user is not None
        assert user.email == "test@example.com"


@pytest.mark.asyncio
async def test_get_current_user_invalid_token():
    """Test getting the current user with an invalid token."""
    token = "invalid_token"

    with patch("utils.security.oauth2_scheme", return_value=token):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token)

        assert exc_info.value.status_code == 401
        assert "Could not validate credentials" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_current_user_user_not_found():
    """Test getting a user that doesn't exist in the database."""
    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.first.return_value = None

    token = create_access_token({"sub": "nonexistent@example.com"})

    with (
        patch("utils.security.oauth2_scheme", return_value=token),
        patch("utils.security.get_db_session", return_value=mock_session),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token)

        assert exc_info.value.status_code == 401
        assert "Could not validate credentials" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_current_active_user():
    """Test getting the current active user."""
    mock_user = MagicMock()
    mock_user.email = "active@example.com"

    user = await get_current_active_user(mock_user)
    assert user is not None
    assert user.email == "active@example.com"


def test_is_ip_blocked():
    """Test checking if an IP is blocked."""
    request = MagicMock()
    request.client.host = "192.168.1.100"

    with patch("utils.security.get_remote_address", return_value="192.168.1.100"):
        assert is_ip_blocked(request) is False

    block_ip("192.168.1.100")

    with patch("utils.security.get_remote_address", return_value="192.168.1.100"):
        assert is_ip_blocked(request) is True


def test_block_ip():
    """Test blocking an IP."""
    block_ip("192.168.1.200")

    request = MagicMock()
    request.client.host = "192.168.1.200"

    with patch("utils.security.get_remote_address", return_value="192.168.1.200"):
        assert is_ip_blocked(request) is True


def test_setup_security():
    """Test setting up security for a FastAPI app."""
    app = MagicMock(spec=FastAPI)
    app.state = MagicMock()

    setup_security(app)

    assert hasattr(app.state, "limiter")
    app.middleware.assert_called_once_with("http")
