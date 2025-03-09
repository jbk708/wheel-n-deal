import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
from models import Product as DBProduct, PriceHistory
from routers.tracker import Product, track_product, get_tracked_products

# Mock data for the product_info returned by scrape_product_info
mock_product_info = {"title": "Test Product", "price": "$100", "url": "https://example.com/product"}


@pytest.fixture
def valid_product():
    return Product(url="https://example.com/product", target_price=90.0)


@pytest.fixture
def product_without_target_price():
    return Product(url="https://example.com/product")


@pytest.fixture
def invalid_product():
    return Product(url="")


# Test for successful product tracking with valid product data
@pytest.mark.asyncio
@patch("routers.tracker.scrape_product_info", return_value=mock_product_info)
@patch("routers.tracker.send_signal_message")
@patch("routers.tracker.check_price.apply_async")
@patch("routers.tracker.get_db_session")
async def test_track_product_success(
    mock_get_db_session, mock_apply_async, mock_send_signal, mock_scrape, valid_product
):
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session
    
    # Mock the product query (product not found)
    mock_session.query.return_value.filter.return_value.first.return_value = None
    
    response = await track_product(valid_product)

    # Verify that scrape_product_info was called with the correct URL
    mock_scrape.assert_called_once_with(valid_product.url)
    
    # Verify that a new product was added to the database
    mock_session.add.assert_called()
    mock_session.flush.assert_called_once()
    mock_session.commit.assert_called_once()

    # Verify that send_signal_message was called
    mock_send_signal.assert_called_once_with(
        "Product is now being tracked: Test Product at $100. Target price is 90.0."
    )

    # Verify that check_price.apply_async was called with the correct arguments
    mock_apply_async.assert_called_once_with(
        args=[valid_product.url, valid_product.target_price]
    )

    # Verify the response
    assert response["message"] == "Product is now being tracked"
    assert response["product_info"]["title"] == "Test Product"
    assert response["target_price"] == 90.0
    
    # Verify that the database session was closed
    mock_session.close.assert_called_once()


# Test product tracking with valid product data and no target price provided (defaults to 10% off)
@pytest.mark.asyncio
@patch("routers.tracker.scrape_product_info", return_value=mock_product_info)
@patch("routers.tracker.send_signal_message")
@patch("routers.tracker.check_price.apply_async")
@patch("routers.tracker.get_db_session")
async def test_track_product_no_target_price(
    mock_get_db_session, mock_apply_async, mock_send_signal, mock_scrape, product_without_target_price
):
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session
    
    # Mock the product query (product not found)
    mock_session.query.return_value.filter.return_value.first.return_value = None
    
    response = await track_product(product_without_target_price)

    # Verify that scrape_product_info was called with the correct URL
    mock_scrape.assert_called_once_with(product_without_target_price.url)
    
    # Verify that a new product was added to the database
    mock_session.add.assert_called()
    mock_session.flush.assert_called_once()
    mock_session.commit.assert_called_once()

    # Verify that send_signal_message was called
    expected_target_price = 90.0  # 10% off of $100
    mock_send_signal.assert_called_once_with(
        f"Product is now being tracked: Test Product at $100. Target price is {expected_target_price}."
    )

    # Verify that check_price.apply_async was called with the correct arguments
    mock_apply_async.assert_called_once_with(
        args=[product_without_target_price.url, expected_target_price]
    )

    # Verify the response
    assert response["message"] == "Product is now being tracked"
    assert response["product_info"]["title"] == "Test Product"
    assert response["target_price"] == expected_target_price
    
    # Verify that the database session was closed
    mock_session.close.assert_called_once()


# Test for product tracking with existing product (update)
@pytest.mark.asyncio
@patch("routers.tracker.scrape_product_info", return_value=mock_product_info)
@patch("routers.tracker.send_signal_message")
@patch("routers.tracker.check_price.apply_async")
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
    mock_session.query.return_value.filter.return_value.first.return_value = mock_existing_product
    
    response = await track_product(valid_product)

    # Verify that scrape_product_info was called with the correct URL
    mock_scrape.assert_called_once_with(valid_product.url)
    
    # Verify that the existing product was updated
    assert mock_existing_product.target_price == valid_product.target_price
    mock_session.add.assert_called()
    mock_session.commit.assert_called_once()

    # Verify that send_signal_message was called
    mock_send_signal.assert_called_once_with(
        "Product is now being tracked: Test Product at $100. Target price is 90.0."
    )

    # Verify that check_price.apply_async was called with the correct arguments
    mock_apply_async.assert_called_once_with(
        args=[valid_product.url, valid_product.target_price]
    )

    # Verify the response
    assert response["message"] == "Product is now being tracked"
    assert response["product_info"]["title"] == "Test Product"
    assert response["target_price"] == 90.0
    
    # Verify that the database session was closed
    mock_session.close.assert_called_once()


# Test for database error during product tracking
@pytest.mark.asyncio
@patch("routers.tracker.scrape_product_info", return_value=mock_product_info)
@patch("routers.tracker.send_signal_message")
@patch("routers.tracker.check_price.apply_async")
@patch("routers.tracker.get_db_session")
async def test_track_product_database_error(
    mock_get_db_session, mock_apply_async, mock_send_signal, mock_scrape, valid_product
):
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session
    
    # Mock a database error
    mock_session.add.side_effect = Exception("Database error")
    
    with pytest.raises(HTTPException) as exc_info:
        await track_product(valid_product)

    # Verify that an HTTPException was raised with a 400 status code
    assert exc_info.value.status_code == 400
    assert "Error tracking product" in str(exc_info.value.detail)
    
    # Verify that rollback was called
    mock_session.rollback.assert_called_once()
    
    # Verify that the database session was closed
    mock_session.close.assert_called_once()
    
    # Verify that send_signal_message and apply_async were never called due to the error
    mock_send_signal.assert_not_called()
    mock_apply_async.assert_not_called()


# Test for product tracking failure when an invalid URL is provided
@pytest.mark.asyncio
@patch("routers.tracker.scrape_product_info", side_effect=Exception("Scraping failed"))
@patch("routers.tracker.send_signal_message")
@patch("routers.tracker.check_price.apply_async")
@patch("routers.tracker.get_db_session")
async def test_track_product_scraping_failure(
    mock_get_db_session, mock_apply_async, mock_send_signal, mock_scrape, invalid_product
):
    with pytest.raises(HTTPException) as exc_info:
        await track_product(invalid_product)

    # Verify that an HTTPException was raised with a 400 status code
    assert exc_info.value.status_code == 400
    assert "Error tracking product" in str(exc_info.value.detail)

    # Verify that scrape_product_info was called but failed
    mock_scrape.assert_called_once_with(invalid_product.url)

    # Verify that the database session was not used
    mock_get_db_session.assert_not_called()

    # Verify that send_signal_message and apply_async were never called due to the error
    mock_send_signal.assert_not_called()
    mock_apply_async.assert_not_called()


# Test for getting products
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
    mock_first = MagicMock()
    
    mock_session.query.return_value.filter.return_value = mock_filter
    mock_filter.order_by.return_value = mock_order_by
    mock_order_by.first.side_effect = [mock_price_history1, mock_price_history2]
    
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
    mock_session.close.assert_called_once()


# Test for getting products with database error
@pytest.mark.asyncio
@patch("routers.tracker.get_db_session")
async def test_get_products_error(mock_get_db_session):
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session
    
    # Mock a database error
    mock_session.query.side_effect = Exception("Database error")
    
    with pytest.raises(HTTPException) as exc_info:
        await get_tracked_products()
    
    # Verify that an HTTPException was raised with a 500 status code
    assert exc_info.value.status_code == 500
    assert "Error retrieving products" in str(exc_info.value.detail)
    
    # Verify that the database session was closed
    mock_session.close.assert_called_once()
