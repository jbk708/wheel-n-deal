from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from models import (
    Base,
    PriceHistory,
    Product,
    get_db_engine,
    get_db_session,
    init_db,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def test_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


def test_product_model(test_db):
    """Test creating a Product model instance."""
    # Create a new product
    product = Product(
        title="Test Product",
        url="https://example.com/product",
        target_price=90.0,
    )

    # Add to the database
    test_db.add(product)
    test_db.commit()

    # Query the product
    queried_product = test_db.query(Product).filter_by(title="Test Product").first()

    # Assertions
    assert queried_product is not None
    assert queried_product.title == "Test Product"
    assert queried_product.url == "https://example.com/product"
    assert queried_product.target_price == 90.0
    assert isinstance(queried_product.created_at, datetime)
    assert isinstance(queried_product.updated_at, datetime)


def test_price_history_model(test_db):
    """Test creating a PriceHistory model instance."""
    # Create a new product
    product = Product(
        title="Test Product",
        url="https://example.com/product",
        target_price=90.0,
    )

    # Add to the database
    test_db.add(product)
    test_db.commit()

    # Create a price history entry
    price_history = PriceHistory(
        product_id=product.id,
        price=100.0,
    )

    # Add to the database
    test_db.add(price_history)
    test_db.commit()

    # Query the price history
    queried_price_history = test_db.query(PriceHistory).filter_by(product_id=product.id).first()

    # Assertions
    assert queried_price_history is not None
    assert queried_price_history.product_id == product.id
    assert queried_price_history.price == 100.0
    assert isinstance(queried_price_history.timestamp, datetime)


def test_relationship(test_db):
    """Test the relationship between Product and PriceHistory."""
    # Create a new product
    product = Product(
        title="Test Product",
        url="https://example.com/product",
        target_price=90.0,
    )

    # Add to the database
    test_db.add(product)
    test_db.commit()

    # Create multiple price history entries
    price_history1 = PriceHistory(
        product_id=product.id,
        price=100.0,
    )

    price_history2 = PriceHistory(
        product_id=product.id,
        price=95.0,
    )

    # Add to the database
    test_db.add(price_history1)
    test_db.add(price_history2)
    test_db.commit()

    # Query the product with its price history
    queried_product = test_db.query(Product).filter_by(id=product.id).first()

    # Assertions
    assert len(queried_product.price_history) == 2
    assert queried_product.price_history[0].price == 100.0
    assert queried_product.price_history[1].price == 95.0


@patch("models.create_engine")
def test_get_db_engine(mock_create_engine):
    """Test the get_db_engine function."""
    mock_engine = MagicMock()
    mock_create_engine.return_value = mock_engine

    # Call the function
    engine = get_db_engine("sqlite:///test.db")

    # Assertions
    mock_create_engine.assert_called_once_with("sqlite:///test.db")
    assert engine == mock_engine


@patch("models.get_db_engine")
@patch("models.sessionmaker")
def test_get_db_session(mock_sessionmaker, mock_get_db_engine):
    """Test the get_db_session function."""
    mock_engine = MagicMock()
    mock_get_db_engine.return_value = mock_engine

    mock_session_class = MagicMock()
    mock_session = MagicMock()
    mock_session_class.return_value = mock_session
    mock_sessionmaker.return_value = mock_session_class

    # Call the function
    session = get_db_session()

    # Assertions
    mock_get_db_engine.assert_called_once()
    mock_sessionmaker.assert_called_once_with(autocommit=False, autoflush=False, bind=mock_engine)
    assert session == mock_session


@patch("models.get_db_engine")
@patch("models.Base.metadata.create_all")
def test_init_db(mock_create_all, mock_get_db_engine):
    """Test the init_db function."""
    mock_engine = MagicMock()
    mock_get_db_engine.return_value = mock_engine

    # Call the function
    init_db()

    # Assertions
    mock_get_db_engine.assert_called_once()
    mock_create_all.assert_called_once_with(bind=mock_engine)
