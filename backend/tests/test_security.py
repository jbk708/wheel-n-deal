from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from jose import jwt
from utils.security import (
    ALGORITHM,
    SECRET_KEY,
    User,
    authenticate_user,
    block_ip,
    create_access_token,
    fake_users_db,
    get_current_active_user,
    get_current_user,
    get_password_hash,
    get_user,
    is_ip_blocked,
    setup_security,
    verify_password,
)


# Test password functions
def test_password_hashing():
    """Test that password hashing and verification work correctly."""
    password = "testpassword"
    hashed = get_password_hash(password)
    
    # Verify the hash is different from the original password
    assert hashed != password
    
    # Verify the password against the hash
    assert verify_password(password, hashed) is True
    
    # Verify an incorrect password fails
    assert verify_password("wrongpassword", hashed) is False


# Test user functions
def test_get_user():
    """Test retrieving a user from the database."""
    # Test with existing user
    user = get_user(fake_users_db, "admin")
    assert user is not None
    assert user.username == "admin"
    assert user.email == "admin@example.com"
    
    # Test with non-existent user
    user = get_user(fake_users_db, "nonexistent")
    assert user is None


def test_authenticate_user():
    """Test user authentication."""
    # Test with correct credentials
    user = authenticate_user(fake_users_db, "admin", "adminpassword")
    assert user is not None
    assert user.username == "admin"
    
    # Test with incorrect password
    user = authenticate_user(fake_users_db, "admin", "wrongpassword")
    assert user is False
    
    # Test with non-existent user
    user = authenticate_user(fake_users_db, "nonexistent", "password")
    assert user is False


# Test token functions
def test_create_access_token():
    """Test creating an access token."""
    data = {"sub": "testuser"}
    
    # Test with default expiry
    token = create_access_token(data)
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "testuser"
    assert "exp" in payload
    
    # Test with custom expiry
    token = create_access_token(data, expires_delta=timedelta(minutes=30))
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "testuser"
    assert "exp" in payload


@pytest.mark.asyncio
async def test_get_current_user():
    """Test getting the current user from a token."""
    # Create a valid token
    token = create_access_token({"sub": "admin"})
    
    # Mock the Depends function to return our token
    with patch("utils.security.oauth2_scheme", return_value=token):
        user = await get_current_user(token)
        assert user is not None
        assert user.username == "admin"


@pytest.mark.asyncio
async def test_get_current_user_invalid_token():
    """Test getting the current user with an invalid token."""
    # Create an invalid token
    token = "invalid_token"
    
    # Mock the Depends function to return our token
    with patch("utils.security.oauth2_scheme", return_value=token):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token)
        
        assert exc_info.value.status_code == 401
        assert "Could not validate credentials" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_current_active_user():
    """Test getting the current active user."""
    # Create a mock active user
    active_user = User(username="active", disabled=False)
    
    # Test with active user
    user = await get_current_active_user(active_user)
    assert user is not None
    assert user.username == "active"
    
    # Test with inactive user
    inactive_user = User(username="inactive", disabled=True)
    with pytest.raises(HTTPException) as exc_info:
        await get_current_active_user(inactive_user)
    
    assert exc_info.value.status_code == 400
    assert "Inactive user" in str(exc_info.value.detail)


# Test IP blocking functions
def test_is_ip_blocked():
    """Test checking if an IP is blocked."""
    # Create a mock request
    request = MagicMock()
    request.client.host = "192.168.1.1"
    
    # Test with unblocked IP
    with patch("utils.security.get_remote_address", return_value="192.168.1.1"):
        assert is_ip_blocked(request) is False
    
    # Block the IP
    block_ip("192.168.1.1")
    
    # Test with blocked IP
    with patch("utils.security.get_remote_address", return_value="192.168.1.1"):
        assert is_ip_blocked(request) is True


def test_block_ip():
    """Test blocking an IP."""
    # Block an IP
    block_ip("192.168.1.2")
    
    # Create a mock request
    request = MagicMock()
    request.client.host = "192.168.1.2"
    
    # Test that the IP is blocked
    with patch("utils.security.get_remote_address", return_value="192.168.1.2"):
        assert is_ip_blocked(request) is True


def test_setup_security():
    """Test setting up security for a FastAPI app."""
    # Create a mock FastAPI app
    app = MagicMock(spec=FastAPI)
    app.state = MagicMock()
    
    # Call setup_security
    setup_security(app)
    
    # Verify that the limiter was set
    assert hasattr(app.state, "limiter")
    
    # Verify that the middleware was added
    app.middleware.assert_called_once_with("http") 