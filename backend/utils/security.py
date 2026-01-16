from datetime import UTC, datetime, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from config import settings
from models import User as DBUser
from models import get_db_session
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


class UserCreate(BaseModel):
    """Schema for user registration."""

    email: str
    password: str


class UserResponse(BaseModel):
    """Schema for user response (excludes password)."""

    id: int
    email: str
    signal_phone: Optional[str] = None
    signal_username: Optional[str] = None

    model_config = {"from_attributes": True}


# Password functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


# User functions
def get_user_by_email(db_session, email: str) -> DBUser | None:
    """Get a user by email from the database."""
    return db_session.query(DBUser).filter(DBUser.email == email).first()


def create_user(db_session, email: str, password: str) -> DBUser:
    """Create a new user in the database."""
    hashed_password = get_password_hash(password)
    user = DBUser(email=email, password_hash=hashed_password)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def authenticate_user_db(db_session, email: str, password: str) -> DBUser | None:
    """Authenticate a user against the database."""
    user = get_user_by_email(db_session, email)
    if not user:
        return None
    if not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


# Token functions
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Get the current user from the JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception from None

    db_session = get_db_session()
    try:
        user = get_user_by_email(db_session, email)
        if user is None:
            raise credentials_exception
        return user
    finally:
        db_session.close()


# Create a module-level singleton for the current_user dependency
current_user_dependency = Depends(get_current_user)


async def get_current_active_user(current_user: DBUser = current_user_dependency):
    """Get the current active user. Returns the user if authenticated."""
    return current_user


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
