from datetime import UTC, datetime, timedelta

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

logger = get_logger("security")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

limiter = Limiter(key_func=get_remote_address)


class Token(BaseModel):
    access_token: str
    token_type: str


class UserCreate(BaseModel):
    """Schema for user registration."""

    email: str
    password: str


class UserResponse(BaseModel):
    """Schema for user response (excludes password)."""

    id: int
    email: str
    signal_phone: str | None = None
    signal_username: str | None = None

    model_config = {"from_attributes": True}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def get_user_by_email(db_session, email: str) -> DBUser | None:
    return db_session.query(DBUser).filter(DBUser.email == email).first()


def create_user(db_session, email: str, password: str) -> DBUser:
    hashed_password = get_password_hash(password)
    user = DBUser(email=email, password_hash=hashed_password)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def authenticate_user_db(db_session, email: str, password: str) -> DBUser | None:
    user = get_user_by_email(db_session, email)
    if not user or not user.password_hash:
        return None
    if not verify_password(password, str(user.password_hash)):
        return None
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> DBUser:
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


_current_user_dependency = Depends(get_current_user)


async def get_current_active_user(current_user: DBUser = _current_user_dependency) -> DBUser:
    return current_user


blocked_ips: set[str] = set()


def is_ip_blocked(request: Request) -> bool:
    client_ip = get_remote_address(request)
    return client_ip in blocked_ips


def block_ip(ip: str, duration: int = 3600) -> None:
    blocked_ips.add(ip)
    logger.warning(f"Blocked IP: {ip} for {duration} seconds")


def setup_security(app: FastAPI) -> None:
    app.state.limiter = limiter

    @app.middleware("http")
    async def block_banned_ips(request: Request, call_next):
        if is_ip_blocked(request):
            logger.warning(f"Blocked request from banned IP: {get_remote_address(request)}")
            return HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your IP has been blocked due to suspicious activity",
            )
        return await call_next(request)
