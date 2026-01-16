import warnings
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from config import settings
from utils.logging import get_logger

logger = get_logger("models")

Base = declarative_base()


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    url = Column(String, unique=True, index=True)
    description = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    target_price = Column(Float)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    price_history = relationship(
        "PriceHistory", back_populates="product", cascade="all, delete-orphan"
    )


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    price = Column(Float)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    product = relationship("Product", back_populates="price_history")


def get_db_engine(db_url: str | None = None):
    """Create a database engine with connection pooling for non-SQLite databases."""
    url = db_url or settings.DATABASE_URL

    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})

    return create_engine(
        url,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_pre_ping=settings.DB_POOL_PRE_PING,
    )


def get_db_session(engine=None):
    """Create a database session."""
    if engine is None:
        engine = get_db_engine()
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return session_local()


def init_db() -> None:
    """
    Initialize the database by creating all tables.

    Note: For new deployments, prefer using Alembic migrations: alembic upgrade head
    """
    warnings.warn(
        "init_db() uses create_all() which may not reflect all migrations. "
        "Consider using 'alembic upgrade head' instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    logger.info("Initializing database tables")
    engine = get_db_engine()
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized")
