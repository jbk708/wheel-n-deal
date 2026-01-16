from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import settings
from utils.logging import get_logger

# Setup logger
logger = get_logger("security")

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings from config
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

# OAuth2 scheme - tokenUrl matches the auth router endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

# Rate limiter
limiter = Limiter(key_func=get_remote_address)


# Models
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class User(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None


class UserInDB(User):
    hashed_password: str


# Fake user database - replace with actual database in production
fake_users_db = {
    "admin": {
        "username": "admin",
        "full_name": "Admin User",
        "email": "admin@example.com",
        "hashed_password": pwd_context.hash("adminpassword"),
        "disabled": False,
    }
}


# Password functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


# User functions
def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        return UserInDB(**user_dict)


def authenticate_user(fake_db, username: str, password: str):
    user = get_user(fake_db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


# Token functions
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception from None
    user = get_user(fake_users_db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


# Create a module-level singleton for the current_user dependency
current_user_dependency = Depends(get_current_user)


async def get_current_active_user(current_user: User = current_user_dependency):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


# Rate limiting decorator
def rate_limit(limit: str, key_func=get_remote_address):
    """
    Rate limiting decorator for FastAPI endpoints.

    Args:
        limit (str): The rate limit string (e.g., "5/minute", "100/hour").
        key_func (callable): Function to extract the key from the request.

    Returns:
        callable: The decorated function.
    """
    return limiter.limit(limit, key_func=key_func)


# IP blocking
blocked_ips = set()


def is_ip_blocked(request: Request) -> bool:
    """
    Check if an IP is blocked.

    Args:
        request (Request): The FastAPI request object.

    Returns:
        bool: True if the IP is blocked, False otherwise.
    """
    client_ip = get_remote_address(request)
    return client_ip in blocked_ips


def block_ip(ip: str, duration: int = 3600):
    """
    Block an IP address for a specified duration.

    Args:
        ip (str): The IP address to block.
        duration (int): The duration in seconds to block the IP.
    """
    blocked_ips.add(ip)
    logger.warning(f"Blocked IP: {ip} for {duration} seconds")

    # In a real implementation, you would use a background task to unblock the IP after the duration
    # For now, we'll just add it to the set


def setup_security(app: FastAPI):
    """
    Set up security for a FastAPI application.

    Args:
        app (FastAPI): The FastAPI application.
    """
    # Add rate limiter middleware
    app.state.limiter = limiter

    # Add IP blocking middleware
    @app.middleware("http")
    async def block_banned_ips(request: Request, call_next):
        if is_ip_blocked(request):
            logger.warning(f"Blocked request from banned IP: {get_remote_address(request)}")
            return HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your IP has been blocked due to suspicious activity",
            )
        return await call_next(request)
