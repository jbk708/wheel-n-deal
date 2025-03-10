import pytest
from models import Base, PriceHistory, Product
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def test_db_engine():
    """Create an in-memory SQLite database engine for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def test_db_session(test_db_engine):
    """Create a database session for testing."""
    session_factory = sessionmaker(bind=test_db_engine)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def sample_product(test_db_session):
    """Create a sample product for testing."""
    product = Product(
        title="Test Product",
        url="https://example.com/product",
        target_price=90.0,
    )
    test_db_session.add(product)
    test_db_session.commit()
    
    # Refresh the product to get the ID
    test_db_session.refresh(product)
    
    yield product


@pytest.fixture
def sample_price_history(test_db_session, sample_product):
    """Create a sample price history for testing."""
    price_history = PriceHistory(
        product_id=sample_product.id,
        price=100.0,
    )
    test_db_session.add(price_history)
    test_db_session.commit()
    
    # Refresh the price history to get the ID
    test_db_session.refresh(price_history)
    
    yield price_history


@pytest.fixture
def multiple_products(test_db_session):
    """Create multiple products for testing."""
    products = [
        Product(
            title="Test Product 1",
            url="https://example.com/product1",
            target_price=90.0,
        ),
        Product(
            title="Test Product 2",
            url="https://example.com/product2",
            target_price=80.0,
        ),
        Product(
            title="Test Product 3",
            url="https://example.com/product3",
            target_price=70.0,
        ),
    ]
    
    for product in products:
        test_db_session.add(product)
    
    test_db_session.commit()
    
    # Refresh the products to get the IDs
    for product in products:
        test_db_session.refresh(product)
    
    yield products


@pytest.fixture
def multiple_price_histories(test_db_session, multiple_products):
    """Create multiple price histories for testing."""
    price_histories = [
        PriceHistory(
            product_id=multiple_products[0].id,
            price=100.0,
        ),
        PriceHistory(
            product_id=multiple_products[0].id,
            price=95.0,
        ),
        PriceHistory(
            product_id=multiple_products[1].id,
            price=90.0,
        ),
        PriceHistory(
            product_id=multiple_products[2].id,
            price=80.0,
        ),
    ]
    
    for price_history in price_histories:
        test_db_session.add(price_history)
    
    test_db_session.commit()
    
    # Refresh the price histories to get the IDs
    for price_history in price_histories:
        test_db_session.refresh(price_history)
    
    yield price_histories
