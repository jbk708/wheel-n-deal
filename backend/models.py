from datetime import datetime
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import relationship, sessionmaker, declarative_base

# Use declarative_base from sqlalchemy.orm instead of sqlalchemy.ext.declarative
Base = declarative_base()


class Product(Base):
    """
    Model for storing product information.
    """

    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    url = Column(String, unique=True, index=True)
    description = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    target_price = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship with PriceHistory
    price_history = relationship(
        "PriceHistory", back_populates="product", cascade="all, delete-orphan"
    )


class PriceHistory(Base):
    """
    Model for storing price history for products.
    """

    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    price = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Relationship with Product
    product = relationship("Product", back_populates="price_history")


# Database connection
def get_db_engine(db_url="sqlite:///wheel_n_deal.db"):
    """
    Create a database engine.
    """
    return create_engine(db_url)


def get_db_session(engine=None):
    """
    Create a database session.
    """
    if engine is None:
        engine = get_db_engine()

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def init_db():
    """
    Initialize the database by creating all tables.
    """
    engine = get_db_engine()
    Base.metadata.create_all(bind=engine)
