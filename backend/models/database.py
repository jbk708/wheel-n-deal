from datetime import datetime

from config import settings
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from utils.logging import get_logger
from utils.monitoring import DATABASE_CONNECTIONS, DATABASE_ERRORS

# Setup logger
logger = get_logger("database")

# Create database engine
try:
    engine = create_engine(settings.DATABASE_URL)
    logger.info(
        f"Database engine created with URL: {settings.DATABASE_URL.replace('://', '://*:*@')}"
    )
    # Increment the database connections metric
    DATABASE_CONNECTIONS.inc()
except Exception as e:
    logger.error(f"Failed to create database engine: {str(e)}", exc_info=True)
    # Increment the database errors metric
    DATABASE_ERRORS.inc()
    raise

# Create session factory
session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()


def get_db_session():
    """
    Get a database session.
    """
    db = session_local()
    try:
        logger.debug("Database session created")
        return db
    except Exception as e:
        db.close()
        logger.error(f"Error creating database session: {str(e)}", exc_info=True)
        # Increment the database errors metric
        DATABASE_ERRORS.inc()
        raise


def init_db():
    """
    Initialize the database by creating all tables.
    """
    try:
        logger.info("Initializing database tables")
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}", exc_info=True)
        # Increment the database errors metric
        DATABASE_ERRORS.inc()
        raise


# Product model
class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, index=True)
    title = Column(String)
    description = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    target_price = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship with PriceHistory
    price_history = relationship(
        "PriceHistory", back_populates="product", cascade="all, delete-orphan"
    )


# PriceHistory model
class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    price = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Relationship with Product
    product = relationship("Product", back_populates="price_history")
