from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from routers.tracker import get_tracked_products, track_product


@pytest.fixture
def mock_request():
    """Mock the Starlette request object for rate limiting."""
    mock_req = MagicMock(spec=Request)
    mock_req.client.host = "127.0.0.1"
    mock_req.app = MagicMock()
    mock_req.app.state.limiter = MagicMock()
    mock_req.state = MagicMock()
    return mock_req


@pytest.fixture
def mock_scraper():
    """Mock the scraper function."""
    with patch("routers.tracker.scrape_product_info") as mock:
        # Mock the scraper to return a valid product
        mock.return_value = {
            "title": "Test Product",
            "price": 100.0,
            "url": "https://example.com/product",
            "description": "A test product",
            "image_url": "https://example.com/image.jpg",
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
    with patch("tasks.price_check.check_price.apply_async") as mock:
        yield mock


@pytest.fixture
def mock_signal():
    """Mock the Signal notification function."""
    with patch("routers.tracker.send_signal_message_to_group") as mock:
        yield mock


@pytest.mark.asyncio
async def test_track_product_success(
    mock_request, mock_scraper, mock_db_session, mock_celery_task, mock_signal
):
    """Test the track_product function with valid data."""
    # Create a product to track
    from routers.tracker import Product

    product = Product(url="https://example.com/product", target_price=90.0)

    # Call the function
    response = await track_product(mock_request, product, mock_db_session)

    # Verify the response
    assert response["title"] == "Test Product"
    assert response["url"] == "https://example.com/product"
    assert response["target_price"] == 90.0
    assert response["current_price"] == 100.0

    # Verify that the product was added to the database
    assert mock_db_session.add.call_count == 2  # Product and PriceHistory
    assert mock_db_session.commit.call_count == 2

    # Verify that the price check task was scheduled
    mock_celery_task.assert_called_once()

    # Verify that a Signal notification was sent
    mock_signal.assert_called_once()


@pytest.mark.asyncio
async def test_track_product_no_target_price(
    mock_request, mock_scraper, mock_db_session, mock_celery_task, mock_signal
):
    """Test the track_product function without a target price."""
    # Create a product to track without a target price
    from routers.tracker import Product

    product = Product(url="https://example.com/product")

    # Call the function
    response = await track_product(mock_request, product, mock_db_session)

    # Verify the response
    assert response["title"] == "Test Product"
    assert response["url"] == "https://example.com/product"
    assert response["target_price"] == 90.0  # 10% off the current price

    # Verify that the product was added to the database
    assert mock_db_session.add.call_count == 2  # Product and PriceHistory
    assert mock_db_session.commit.call_count == 2

    # Verify that the price check task was scheduled
    mock_celery_task.assert_called_once()

    # Verify that a Signal notification was sent
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
        mock_existing_product.url = "https://example.com/product"
        mock_existing_product.target_price = 85.0

        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_existing_product
        )

        yield mock_session


@pytest.mark.asyncio
async def test_track_product_existing(
    mock_request, mock_scraper, mock_db_session_with_existing_product, mock_celery_task, mock_signal
):
    """Test the track_product function with an existing product."""
    # Create a product to track
    from routers.tracker import Product

    product = Product(url="https://example.com/product", target_price=90.0)

    # Call the function and expect an exception
    with pytest.raises(HTTPException) as exc_info:
        await track_product(mock_request, product, mock_db_session_with_existing_product)

    # Verify the exception
    assert exc_info.value.status_code == 400
    assert "already being tracked" in str(exc_info.value.detail)

    # Verify that no product was added to the database
    assert mock_db_session_with_existing_product.add.call_count == 0
    assert mock_db_session_with_existing_product.commit.call_count == 0

    # Verify that no price check task was scheduled
    mock_celery_task.assert_not_called()

    # Verify that no Signal notification was sent
    mock_signal.assert_not_called()


@pytest.mark.asyncio
async def test_track_product_scraper_error(mock_request, mock_db_session):
    """Test the track_product function with a scraper error."""
    # Mock the scraper to raise an exception
    with patch("routers.tracker.scrape_product_info", side_effect=Exception("Scraping failed")):
        # Create a product to track
        from routers.tracker import Product

        product = Product(url="https://example.com/product", target_price=90.0)

        # Call the function and expect an exception
        with pytest.raises(HTTPException) as exc_info:
            await track_product(mock_request, product, mock_db_session)

        # Verify the exception
        assert exc_info.value.status_code == 500
        assert "Error tracking product" in str(exc_info.value.detail)


@pytest.fixture
def mock_db_session_for_products():
    """Mock the database session for get_products."""
    with patch("routers.tracker.get_db_session") as mock:
        # Create a mock session
        mock_session = MagicMock()
        mock.return_value = mock_session

        # Create mock products
        mock_product1 = MagicMock()
        mock_product1.id = 1
        mock_product1.title = "Test Product 1"
        mock_product1.url = "https://example.com/product1"
        mock_product1.description = "Description 1"
        mock_product1.image_url = "https://example.com/image1.jpg"
        mock_product1.target_price = 90.0
        mock_product1.created_at = "2023-01-01T00:00:00"
        mock_product1.updated_at = "2023-01-01T00:00:00"

        mock_product2 = MagicMock()
        mock_product2.id = 2
        mock_product2.title = "Test Product 2"
        mock_product2.url = "https://example.com/product2"
        mock_product2.description = "Description 2"
        mock_product2.image_url = "https://example.com/image2.jpg"
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
async def test_get_products_success(mock_request, mock_db_session_for_products):
    """Test the get_products function."""
    # Call the function
    response = await get_tracked_products(mock_request, mock_db_session_for_products)

    # Verify the response
    assert len(response) == 2
    assert response[0]["id"] == 1
    assert response[0]["title"] == "Test Product 1"
    assert response[0]["current_price"] == 100.0
    assert response[1]["id"] == 2
    assert response[1]["title"] == "Test Product 2"
    assert response[1]["current_price"] == 95.0


@pytest.mark.asyncio
async def test_get_products_error(mock_request):
    """Test the get_products function with a database error."""
    # Mock the database session
    with patch("routers.tracker.get_db_session") as mock_get_db_session:
        # Create a mock session
        mock_session = MagicMock()
        mock_get_db_session.return_value = mock_session

        # Mock a database error
        mock_session.query.side_effect = Exception("Database error")

        # Call the function and expect an exception
        with pytest.raises(HTTPException) as exc_info:
            await get_tracked_products(mock_request, mock_session)

        # Verify the exception
        assert exc_info.value.status_code == 500
        assert "Error retrieving tracked products" in str(exc_info.value.detail)
