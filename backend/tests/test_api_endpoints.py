import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi import HTTPException
from routers.tracker import track_product, get_tracked_products
from models import Product as DBProduct, PriceHistory


@pytest.fixture
def mock_scraper():
    """Mock the scraper function."""
    with patch("routers.tracker.scrape_product_info") as mock:
        # Mock the scraper to return a valid product
        mock.return_value = {
            "title": "Test Product",
            "price": "$100",
            "url": "https://example.com/product",
        }
        yield mock


@pytest.fixture
def mock_db_session():
    """Mock the database session."""
    with patch("routers.tracker.get_db_session") as mock:
        # Create a mock session
        mock_session = MagicMock()
        mock.return_value = mock_session
        
        # Mock the product query (product not found)
        mock_session.query.return_value.filter.return_value.first.return_value = None
        
        yield mock_session


@pytest.fixture
def mock_celery_task():
    """Mock the Celery task."""
    with patch("routers.tracker.check_price.apply_async") as mock:
        yield mock


@pytest.fixture
def mock_signal():
    """Mock the Signal notification function."""
    with patch("routers.tracker.send_signal_message") as mock:
        yield mock


@pytest.mark.asyncio
async def test_track_product_success(mock_scraper, mock_db_session, mock_celery_task, mock_signal):
    """Test the track_product function with a valid product."""
    # Create a product
    from routers.tracker import Product
    product = Product(url="https://example.com/product", target_price=90.0)
    
    # Call the function
    response = await track_product(product)
    
    # Verify the response
    assert response["message"] == "Product is now being tracked"
    assert response["product_info"]["title"] == "Test Product"
    assert response["target_price"] == 90.0
    
    # Verify that the database functions were called
    mock_db_session.add.assert_called()
    mock_db_session.flush.assert_called_once()
    mock_db_session.commit.assert_called_once()
    
    # Verify that the scraper was called
    mock_scraper.assert_called_once_with("https://example.com/product")
    
    # Verify that the Celery task was scheduled
    mock_celery_task.assert_called_once()
    
    # Verify that the Signal notification was sent
    mock_signal.assert_called_once()


@pytest.mark.asyncio
async def test_track_product_no_target_price(mock_scraper, mock_db_session, mock_celery_task, mock_signal):
    """Test the track_product function without a target price."""
    # Create a product without a target price
    from routers.tracker import Product
    product = Product(url="https://example.com/product")
    
    # Call the function
    response = await track_product(product)
    
    # Verify the response
    assert response["message"] == "Product is now being tracked"
    assert response["product_info"]["title"] == "Test Product"
    assert response["target_price"] == 90.0  # 10% off $100
    
    # Verify that the database functions were called
    mock_db_session.add.assert_called()
    mock_db_session.flush.assert_called_once()
    mock_db_session.commit.assert_called_once()
    
    # Verify that the scraper was called
    mock_scraper.assert_called_once_with("https://example.com/product")
    
    # Verify that the Celery task was scheduled
    mock_celery_task.assert_called_once()
    
    # Verify that the Signal notification was sent
    mock_signal.assert_called_once()


@pytest.fixture
def mock_db_session_with_existing_product():
    """Mock the database session with an existing product."""
    with patch("routers.tracker.get_db_session") as mock:
        # Create a mock session
        mock_session = MagicMock()
        mock.return_value = mock_session
        
        # Mock the product query (product found)
        mock_existing_product = MagicMock()
        mock_existing_product.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_existing_product
        
        yield mock_session


@pytest.mark.asyncio
async def test_track_product_existing(mock_scraper, mock_db_session_with_existing_product, mock_celery_task, mock_signal):
    """Test the track_product function with an existing product."""
    # Create a product
    from routers.tracker import Product
    product = Product(url="https://example.com/product", target_price=90.0)
    
    # Call the function
    response = await track_product(product)
    
    # Verify the response
    assert response["message"] == "Product is now being tracked"
    assert response["product_info"]["title"] == "Test Product"
    assert response["target_price"] == 90.0
    
    # Verify that the existing product was updated
    mock_existing_product = mock_db_session_with_existing_product.query.return_value.filter.return_value.first.return_value
    assert mock_existing_product.target_price == 90.0
    
    # Verify that the database functions were called
    mock_db_session_with_existing_product.add.assert_called()
    mock_db_session_with_existing_product.commit.assert_called_once()
    
    # Verify that the scraper was called
    mock_scraper.assert_called_once_with("https://example.com/product")
    
    # Verify that the Celery task was scheduled
    mock_celery_task.assert_called_once()
    
    # Verify that the Signal notification was sent
    mock_signal.assert_called_once()


@pytest.mark.asyncio
async def test_track_product_scraper_error(mock_db_session):
    """Test the track_product function with a scraper error."""
    # Mock the scraper to raise an exception
    with patch("routers.tracker.scrape_product_info", side_effect=Exception("Scraping failed")):
        # Create a product
        from routers.tracker import Product
        product = Product(url="https://example.com/product", target_price=90.0)
        
        # Call the function and expect an exception
        with pytest.raises(HTTPException) as exc_info:
            await track_product(product)
        
        # Verify the exception
        assert exc_info.value.status_code == 400
        assert "Error tracking product" in str(exc_info.value.detail)


@pytest.fixture
def mock_db_session_for_products():
    """Mock the database session for getting products."""
    with patch("routers.tracker.get_db_session") as mock:
        # Create a mock session
        mock_session = MagicMock()
        mock.return_value = mock_session
        
        # Create mock products
        mock_product1 = MagicMock()
        mock_product1.id = 1
        mock_product1.title = "Test Product 1"
        mock_product1.url = "https://example.com/product1"
        mock_product1.target_price = 90.0
        mock_product1.created_at = "2023-01-01T00:00:00"
        mock_product1.updated_at = "2023-01-01T00:00:00"
        
        mock_product2 = MagicMock()
        mock_product2.id = 2
        mock_product2.title = "Test Product 2"
        mock_product2.url = "https://example.com/product2"
        mock_product2.target_price = 80.0
        mock_product2.created_at = "2023-01-02T00:00:00"
        mock_product2.updated_at = "2023-01-02T00:00:00"
        
        # Mock the query result
        mock_session.query.return_value.all.return_value = [mock_product1, mock_product2]
        
        # Mock the price history query
        mock_price_history1 = MagicMock()
        mock_price_history1.price = 100.0
        
        mock_price_history2 = MagicMock()
        mock_price_history2.price = 95.0
        
        # Set up the filter and order_by chain for price history
        mock_filter = MagicMock()
        mock_order_by = MagicMock()
        
        mock_session.query.return_value.filter.return_value = mock_filter
        mock_filter.order_by.return_value = mock_order_by
        mock_order_by.first.side_effect = [mock_price_history1, mock_price_history2]
        
        yield mock_session


@pytest.mark.asyncio
async def test_get_products_success(mock_db_session_for_products):
    """Test the get_products function."""
    # Call the function
    response = await get_tracked_products()
    
    # Verify the response
    assert len(response) == 2
    
    assert response[0]["id"] == 1
    assert response[0]["title"] == "Test Product 1"
    assert response[0]["url"] == "https://example.com/product1"
    assert response[0]["target_price"] == 90.0
    assert response[0]["current_price"] == 100.0
    
    assert response[1]["id"] == 2
    assert response[1]["title"] == "Test Product 2"
    assert response[1]["url"] == "https://example.com/product2"
    assert response[1]["target_price"] == 80.0
    assert response[1]["current_price"] == 95.0
    
    # Verify that the database session was closed
    mock_db_session_for_products.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_products_error():
    """Test the get_products function with a database error."""
    # Mock the database session to raise an exception
    with patch("routers.tracker.get_db_session") as mock:
        # Create a mock session
        mock_session = MagicMock()
        mock.return_value = mock_session
        
        # Mock a database error
        mock_session.query.side_effect = Exception("Database error")
        
        # Call the function and expect an exception
        with pytest.raises(HTTPException) as exc_info:
            await get_tracked_products()
        
        # Verify the exception
        assert exc_info.value.status_code == 500
        assert "Error retrieving products" in str(exc_info.value.detail)
        
        # Verify that the database session was closed
        mock_session.close.assert_called_once() 