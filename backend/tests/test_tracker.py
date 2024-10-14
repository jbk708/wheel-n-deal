import pytest
from unittest.mock import patch
from fastapi import HTTPException
from routers.tracker import Product, track_product

# Mock data for the product_info returned by scrape_product_info
mock_product_info = {"title": "Test Product", "price": "$100"}


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
async def test_track_product_success(
    mock_apply_async, mock_send_signal, mock_scrape, valid_product
):
    response = await track_product(valid_product)

    # Verify that scrape_product_info was called with the correct URL
    mock_scrape.assert_called_once_with(valid_product.url)

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


# Test product tracking with valid product data and no target price provided (defaults to 10% off)
@pytest.mark.asyncio
@patch("routers.tracker.scrape_product_info", return_value=mock_product_info)
@patch("routers.tracker.send_signal_message")
@patch("routers.tracker.check_price.apply_async")
async def test_track_product_no_target_price(
    mock_apply_async, mock_send_signal, mock_scrape, product_without_target_price
):
    response = await track_product(product_without_target_price)

    # Verify that scrape_product_info was called with the correct URL
    mock_scrape.assert_called_once_with(product_without_target_price.url)

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


# Test for product tracking failure when an invalid URL is provided
@pytest.mark.asyncio
@patch("routers.tracker.scrape_product_info", side_effect=Exception("Scraping failed"))
@patch("routers.tracker.send_signal_message")
@patch("routers.tracker.check_price.apply_async")
async def test_track_product_failure(
    mock_apply_async, mock_send_signal, mock_scrape, invalid_product
):
    with pytest.raises(HTTPException) as exc_info:
        await track_product(invalid_product)

    # Verify that an HTTPException was raised with a 400 status code
    assert exc_info.value.status_code == 400
    assert "Error tracking product" in str(exc_info.value.detail)

    # Verify that scrape_product_info was called but failed
    mock_scrape.assert_called_once_with(invalid_product.url)

    # Verify that send_signal_message and apply_async were never called due to the error
    mock_send_signal.assert_not_called()
    mock_apply_async.assert_not_called()
