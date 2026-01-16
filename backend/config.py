import os
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application settings
    APP_NAME: str = "Wheel-n-Deal"
    APP_VERSION: str = "0.1.0"
    APP_DESCRIPTION: str = "A price tracking and deal notification service"

    # Environment settings
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = ENVIRONMENT == "development"

    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = DEBUG

    # Database settings
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./wheel_n_deal.db")

    # Database connection pooling (ignored for SQLite)
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    DB_POOL_PRE_PING: bool = True

    # Signal settings
    SIGNAL_PHONE_NUMBER: str = os.getenv("SIGNAL_PHONE_NUMBER", "")
    SIGNAL_GROUP_ID: str = os.getenv("SIGNAL_GROUP_ID", "")

    # Logging settings
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Monitoring settings
    ENABLE_METRICS: bool = True
    METRICS_PORT: int = 8001

    # Security settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "CHANGE_ME_IN_PRODUCTION")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # CORS settings
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    CORS_ALLOW_HEADERS: List[str] = ["Authorization", "Content-Type"]

    # Rate limiting settings
    RATE_LIMIT_PER_MINUTE: int = 60

    # Scraper settings
    SCRAPER_TIMEOUT: int = 10  # seconds
    USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

    # Price check settings
    PRICE_CHECK_INTERVAL: int = 3600  # seconds (1 hour)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


# Create settings instance
settings = Settings()

# Log settings in debug mode
if settings.DEBUG:
    import json

    print(f"=== {settings.APP_NAME} Configuration ===")
    config_dict = {k: v for k, v in settings.model_dump().items() if not k.startswith("_")}
    # Hide sensitive information
    for key in ["SECRET_KEY", "DATABASE_URL", "SIGNAL_PHONE_NUMBER", "SIGNAL_GROUP_ID"]:
        if config_dict.get(key):
            config_dict[key] = "********"
    print(json.dumps(config_dict, indent=2))
