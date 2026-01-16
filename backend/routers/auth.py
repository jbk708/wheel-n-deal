from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from config import settings
from utils.logging import get_logger
from utils.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    Token,
    User,
    authenticate_user,
    create_access_token,
    fake_users_db,
    get_current_active_user,
    limiter,
)

# Setup logger
logger = get_logger("auth")

# Create router
router = APIRouter()

# Module-level singletons for dependencies
form_data_dependency = Depends(OAuth2PasswordRequestForm)
current_user_dependency = Depends(get_current_active_user)


@router.post("/token", response_model=Token)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = form_data_dependency,
):
    """
    OAuth2 compatible token login endpoint.

    Authenticates the user and returns a JWT access token.
    """
    user = authenticate_user(fake_users_db, form_data.username, form_data.password)
    if not user:
        logger.warning(f"Failed login attempt for username: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    logger.info(f"User {user.username} logged in successfully")
    return Token(access_token=access_token, token_type="bearer")  # noqa: S106


@router.get("/me", response_model=User)
async def read_users_me(current_user: User = current_user_dependency):
    """
    Get current authenticated user information.
    """
    return current_user
