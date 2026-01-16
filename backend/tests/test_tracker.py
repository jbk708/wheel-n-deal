from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from routers.tracker import Product, get_tracked_products, track_product

# Mock data for the product_info returned by scrape_product_info
mock_product_info = {
    "title": "Test Product",
    "price": 100.0,
    "url": "https://example.com/product",
    "description": "A test product",
    "image_url": "https://example.com/image.jpg",
}


@pytest.fixture
def valid_product():
    return Product(url="https://example.com/product", target_price=90.0)


@pytest.fixture
def product_without_target_price():
    return Product(url="https://example.com/product")


@pytest.fixture
def invalid_product():
    return Product(url="invalid-url")


# Test for successful product tracking with valid product data
@pytest.mark.asyncio
@patch("routers.tracker.scrape_product_info", return_value=mock_product_info)
@patch("routers.tracker.send_signal_message_to_group")
@patch("tasks.price_check.check_price.apply_async")
@patch("routers.tracker.get_db_session")
async def test_track_product_success(
    mock_get_db_session, mock_apply_async, mock_send_signal, mock_scrape, valid_product
):
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    # Mock the product query (product not found)
    mock_session.query.return_value.filter.return_value.first.return_value = None

    # Call the function directly with the mock session instead of using Depends
    response = await track_product(valid_product, mock_session)

    # Verify that scrape_product_info was called with the correct URL
    mock_scrape.assert_called_once_with(valid_product.url)

    # Verify that a new product was added to the database
    mock_session.add.assert_called()
    mock_session.commit.assert_called()

    # Verify that send_signal_message was called
    assert mock_send_signal.call_count == 1
    # Get the actual arguments
    args, _ = mock_send_signal.call_args
    # Check that the second argument (message) contains the expected text
    assert "Product is now being tracked" in args[1]
    assert mock_product_info["title"] in args[1]
    assert str(valid_product.target_price) in args[1]

    # Verify that check_price.apply_async was called with the correct arguments
    mock_apply_async.assert_called_once_with(args=[valid_product.url, valid_product.target_price])

    # Verify the response
    assert response["url"] == valid_product.url
    assert response["title"] == mock_product_info["title"]
    assert response["target_price"] == valid_product.target_price
    assert response["current_price"] == mock_product_info["price"]


# Test for product tracking without a target price
@pytest.mark.asyncio
@patch("routers.tracker.scrape_product_info", return_value=mock_product_info)
@patch("routers.tracker.send_signal_message_to_group")
@patch("tasks.price_check.check_price.apply_async")
@patch("routers.tracker.get_db_session")
async def test_track_product_no_target_price(
    mock_get_db_session,
    mock_apply_async,
    mock_send_signal,
    mock_scrape,
    product_without_target_price,
):
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    # Mock the product query (product not found)
    mock_session.query.return_value.filter.return_value.first.return_value = None

    # Call the function directly with the mock session
    await track_product(product_without_target_price, mock_session)

    # Verify that a target price was set (90% of current price)
    assert product_without_target_price.target_price == 90.0  # 90% of $100

    # Verify that a new product was added to the database
    mock_session.add.assert_called()
    mock_session.commit.assert_called()

    # Verify that send_signal_message was called
    mock_send_signal.assert_called_once()

    # Verify that the celery task was scheduled
    mock_apply_async.assert_called_once()


# Test for tracking a product that is already being tracked
@pytest.mark.asyncio
@patch("routers.tracker.scrape_product_info", return_value=mock_product_info)
@patch("routers.tracker.send_signal_message_to_group")
@patch("tasks.price_check.check_price.apply_async")
@patch("routers.tracker.get_db_session")
async def test_track_product_existing(
    mock_get_db_session, mock_apply_async, mock_send_signal, mock_scrape, valid_product
):
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    # Mock the product query (product found)
    mock_existing_product = MagicMock()
    mock_existing_product.id = 1
    mock_existing_product.url = "https://example.com/product"
    mock_existing_product.target_price = 85.0

    mock_session.query.return_value.filter.return_value.first.return_value = mock_existing_product

    # Call the function and expect an exception
    with pytest.raises(HTTPException) as exc_info:
        await track_product(valid_product, mock_session)

    # Verify that an HTTPException was raised with a 400 status code
    assert exc_info.value.status_code == 400
    assert "Product is already being tracked" in str(exc_info.value.detail)

    # Verify that no database operations were performed
    mock_session.add.assert_not_called()
    mock_session.commit.assert_not_called()

    # Verify that no notifications were sent
    mock_send_signal.assert_not_called()

    # Verify that no celery tasks were scheduled
    mock_apply_async.assert_not_called()


# Test for database error during product tracking
@pytest.mark.asyncio
@patch("routers.tracker.scrape_product_info", return_value=mock_product_info)
@patch("routers.tracker.send_signal_message_to_group")
@patch("tasks.price_check.check_price.apply_async")
@patch("routers.tracker.get_db_session")
async def test_track_product_database_error(
    mock_get_db_session, mock_apply_async, mock_send_signal, mock_scrape, valid_product
):
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    # Mock the product query (product not found)
    mock_session.query.return_value.filter.return_value.first.return_value = None

    # Mock a database error
    mock_session.commit.side_effect = Exception("Database error")

    # Call the function and expect an exception
    with pytest.raises(HTTPException) as exc_info:
        await track_product(valid_product, mock_session)

    # Verify that an HTTPException was raised with a 500 status code
    assert exc_info.value.status_code == 500
    assert "Error tracking product" in str(exc_info.value.detail)

    # Verify that rollback was called
    mock_session.rollback.assert_called_once()


# Test for scraping failure during product tracking
@pytest.mark.asyncio
@patch("routers.tracker.scrape_product_info", side_effect=Exception("Scraping failed"))
@patch("routers.tracker.send_signal_message_to_group")
@patch("tasks.price_check.check_price.apply_async")
@patch("routers.tracker.get_db_session")
async def test_track_product_scraping_failure(
    mock_get_db_session,
    mock_apply_async,
    mock_send_signal,
    mock_scrape,
    invalid_product,
):
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    # Mock the product query (product not found)
    mock_session.query.return_value.filter.return_value.first.return_value = None

    # Call the function and expect an exception
    with pytest.raises(HTTPException) as exc_info:
        await track_product(invalid_product, mock_session)

    # Verify that an HTTPException was raised with a 500 status code
    assert exc_info.value.status_code == 500
    assert "Error tracking product" in str(exc_info.value.detail)


# Test for successful retrieval of tracked products
@pytest.mark.asyncio
@patch("routers.tracker.get_db_session")
async def test_get_products_success(mock_get_db_session):
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

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

    response = await get_tracked_products(mock_session)

    # Verify the response
    assert len(response) == 2
    assert response[0]["id"] == 1
    assert response[0]["title"] == "Test Product 1"
    assert response[0]["current_price"] == 100.0
    assert response[1]["id"] == 2
    assert response[1]["title"] == "Test Product 2"
    assert response[1]["current_price"] == 95.0


# Test for error during retrieval of tracked products
@pytest.mark.asyncio
@patch("routers.tracker.get_db_session")
async def test_get_products_error(mock_get_db_session):
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    # Mock a database error
    mock_session.query.side_effect = Exception("Database error")

    with pytest.raises(HTTPException) as exc_info:
        await get_tracked_products(mock_session)

    # Verify that an HTTPException was raised with a 500 status code
    assert exc_info.value.status_code == 500
    assert "Error retrieving tracked products" in str(exc_info.value.detail)
