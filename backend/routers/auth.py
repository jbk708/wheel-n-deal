from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from config import settings
from models import User as DBUser
from models import get_db_session
from utils.logging import get_logger
from utils.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    Token,
    UserCreate,
    UserResponse,
    authenticate_user_db,
    create_access_token,
    create_user,
    get_current_active_user,
    get_user_by_email,
    limiter,
)

logger = get_logger("auth")

router = APIRouter()

_form_data_dependency = Depends(OAuth2PasswordRequestForm)
_current_user_dependency = Depends(get_current_active_user)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def register_user(request: Request, user_data: UserCreate) -> DBUser:
    db_session = get_db_session()
    try:
        existing_user = get_user_by_email(db_session, user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered",
            )
        user = create_user(db_session, user_data.email, user_data.password)
        logger.info(f"New user registered: {user.email}")
        return user
    except HTTPException:
        raise
    except Exception as e:
        db_session.rollback()
        logger.error(f"Error registering user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error registering user",
        ) from e
    finally:
        db_session.close()


@router.post("/token", response_model=Token)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = _form_data_dependency,
) -> Token:
    db_session = get_db_session()
    try:
        user = authenticate_user_db(db_session, form_data.username, form_data.password)
        if not user:
            logger.warning(f"Failed login attempt for: {form_data.username}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email}, expires_delta=access_token_expires
        )
        logger.info(f"User {user.email} logged in successfully")
        return Token(access_token=access_token, token_type="bearer")  # noqa: S106
    finally:
        db_session.close()


@router.get("/me", response_model=UserResponse)
async def read_users_me(current_user: DBUser = _current_user_dependency) -> DBUser:
    return current_user
