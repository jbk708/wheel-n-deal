from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from models import (
    Base,
    PriceHistory,
    Product,
    User,
    get_db_engine,
    get_db_session,
    init_db,
)


@pytest.fixture
def test_db():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


def test_user_model_with_signal_phone(test_db):
    """Test creating a User with Signal phone number."""
    user = User(signal_phone="+1234567890", signal_username="testuser")
    test_db.add(user)
    test_db.commit()

    queried_user = test_db.query(User).filter_by(signal_phone="+1234567890").first()

    assert queried_user is not None
    assert queried_user.signal_phone == "+1234567890"
    assert queried_user.signal_username == "testuser"
    assert queried_user.email is None
    assert queried_user.password_hash is None
    assert isinstance(queried_user.created_at, datetime)


def test_user_model_with_email(test_db):
    """Test creating a User with email and password for web login."""
    user = User(email="test@example.com", password_hash="hashed_password_here")  # noqa: S106
    test_db.add(user)
    test_db.commit()

    queried_user = test_db.query(User).filter_by(email="test@example.com").first()

    assert queried_user is not None
    assert queried_user.email == "test@example.com"
    assert queried_user.password_hash == "hashed_password_here"
    assert queried_user.signal_phone is None
    assert isinstance(queried_user.created_at, datetime)


def test_user_model_with_both_signal_and_email(test_db):
    """Test creating a User with both Signal and email credentials."""
    user = User(
        signal_phone="+1234567890",
        signal_username="testuser",
        email="test@example.com",
        password_hash="hashed_password_here",  # noqa: S106
    )
    test_db.add(user)
    test_db.commit()

    queried_user = test_db.query(User).filter_by(signal_phone="+1234567890").first()

    assert queried_user is not None
    assert queried_user.signal_phone == "+1234567890"
    assert queried_user.email == "test@example.com"


def test_user_signal_phone_unique_constraint(test_db):
    """Test that signal_phone must be unique."""
    user1 = User(signal_phone="+1234567890")
    test_db.add(user1)
    test_db.commit()

    user2 = User(signal_phone="+1234567890")
    test_db.add(user2)

    with pytest.raises(IntegrityError):
        test_db.commit()


def test_user_email_unique_constraint(test_db):
    """Test that email must be unique."""
    # Need a fresh session for this test due to previous rollback state
    test_db.rollback()

    user1 = User(email="test@example.com")
    test_db.add(user1)
    test_db.commit()

    user2 = User(email="test@example.com")
    test_db.add(user2)

    with pytest.raises(IntegrityError):
        test_db.commit()


def test_user_products_relationship(test_db):
    """Test the relationship between User and Products."""
    test_db.rollback()

    user = User(signal_phone="+5555555555")
    test_db.add(user)
    test_db.commit()

    # Create products for the user
    product1 = Product(
        user_id=user.id,
        title="Product 1",
        url="https://example.com/product1",
        target_price=50.0,
    )
    product2 = Product(
        user_id=user.id,
        title="Product 2",
        url="https://example.com/product2",
        target_price=75.0,
    )
    test_db.add(product1)
    test_db.add(product2)
    test_db.commit()

    # Query user and check products relationship
    queried_user = test_db.query(User).filter_by(id=user.id).first()
    assert len(queried_user.products) == 2
    assert queried_user.products[0].title == "Product 1"
    assert queried_user.products[1].title == "Product 2"


def test_product_user_relationship(test_db):
    """Test that Product has a back-reference to User."""
    user = User(signal_phone="+6666666666")
    test_db.add(user)
    test_db.commit()

    product = Product(
        user_id=user.id,
        title="Test Product",
        url="https://example.com/test",
        target_price=100.0,
    )
    test_db.add(product)
    test_db.commit()

    queried_product = test_db.query(Product).filter_by(id=product.id).first()
    assert queried_product.user is not None
    assert queried_product.user.signal_phone == "+6666666666"


def test_same_url_different_users_allowed(test_db):
    """Test that different users can track the same URL."""
    user1 = User(signal_phone="+7777777777")
    user2 = User(signal_phone="+8888888888")
    test_db.add(user1)
    test_db.add(user2)
    test_db.commit()

    # Both users track the same URL with different target prices
    product1 = Product(
        user_id=user1.id,
        title="Product",
        url="https://example.com/same-product",
        target_price=50.0,
    )
    product2 = Product(
        user_id=user2.id,
        title="Product",
        url="https://example.com/same-product",
        target_price=75.0,
    )
    test_db.add(product1)
    test_db.add(product2)
    test_db.commit()

    # Both should exist
    products = test_db.query(Product).filter_by(url="https://example.com/same-product").all()
    assert len(products) == 2
    assert products[0].target_price != products[1].target_price


def test_same_url_same_user_rejected(test_db):
    """Test that a user cannot track the same URL twice."""
    user = User(signal_phone="+9999999999")
    test_db.add(user)
    test_db.commit()

    product1 = Product(
        user_id=user.id,
        title="Product",
        url="https://example.com/duplicate",
        target_price=50.0,
    )
    test_db.add(product1)
    test_db.commit()

    product2 = Product(
        user_id=user.id,
        title="Product Again",
        url="https://example.com/duplicate",
        target_price=75.0,
    )
    test_db.add(product2)

    with pytest.raises(IntegrityError):
        test_db.commit()


def test_product_model(test_db):
    """Test creating a Product model instance."""
    # Create a user first (products require a user)
    user = User(signal_phone="+1111111111")
    test_db.add(user)
    test_db.commit()

    # Create a new product
    product = Product(
        user_id=user.id,
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
    assert queried_product.user_id == user.id
    assert queried_product.title == "Test Product"
    assert queried_product.url == "https://example.com/product"
    assert queried_product.target_price == 90.0
    assert isinstance(queried_product.created_at, datetime)
    assert isinstance(queried_product.updated_at, datetime)


def test_price_history_model(test_db):
    """Test creating a PriceHistory model instance."""
    # Create a user first
    user = User(signal_phone="+2222222222")
    test_db.add(user)
    test_db.commit()

    # Create a new product
    product = Product(
        user_id=user.id,
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


def test_product_price_history_relationship(test_db):
    """Test the relationship between Product and PriceHistory."""
    # Create a user first
    user = User(signal_phone="+3333333333")
    test_db.add(user)
    test_db.commit()

    # Create a new product
    product = Product(
        user_id=user.id,
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
def test_get_db_engine_sqlite(mock_create_engine):
    """Test the get_db_engine function with SQLite URL."""
    mock_engine = MagicMock()
    mock_create_engine.return_value = mock_engine

    engine = get_db_engine("sqlite:///test.db")

    mock_create_engine.assert_called_once_with(
        "sqlite:///test.db", connect_args={"check_same_thread": False}
    )
    assert engine == mock_engine


@patch("models.create_engine")
@patch("models.settings")
def test_get_db_engine_postgres(mock_settings, mock_create_engine):
    """Test the get_db_engine function with PostgreSQL URL uses connection pooling."""
    mock_engine = MagicMock()
    mock_create_engine.return_value = mock_engine
    mock_settings.DB_POOL_SIZE = 5
    mock_settings.DB_MAX_OVERFLOW = 10
    mock_settings.DB_POOL_TIMEOUT = 30
    mock_settings.DB_POOL_RECYCLE = 1800
    mock_settings.DB_POOL_PRE_PING = True

    engine = get_db_engine("postgresql://user:pass@localhost/db")

    mock_create_engine.assert_called_once_with(
        "postgresql://user:pass@localhost/db",
        pool_size=5,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
    )
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
