import random
from unittest.mock import patch

import pytest
from tasks.price_check import check_price

# Mock product info data
mock_product_info = {"title": "Test Product", "price": "$80"}


@pytest.fixture
def valid_url():
    return "https://example.com/product"


@pytest.fixture
def target_price():
    return 90.0


@pytest.fixture
def lower_target_price():
    return 70.0


# Test for a successful price drop
@patch("tasks.price_check.scrape_product_info", return_value=mock_product_info)
@patch("tasks.price_check.send_signal_message")
@patch("tasks.price_check.check_price.apply_async")
def test_check_price_success(
    mock_apply_async, mock_send_signal, mock_scrape, valid_url, target_price
):
    check_price(valid_url, target_price)

    # Verify that scrape_product_info was called with the correct URL
    mock_scrape.assert_called_once_with(valid_url)

    # Verify that send_signal_message was called since the price is lower than target_price
    mock_send_signal.assert_called_once_with(
        "Price drop alert! Test Product is now $80.\nTarget price was 90.0."
    )

    # Verify that apply_async is called to reschedule the task
    assert mock_apply_async.called
    assert mock_apply_async.call_args[1]["countdown"] in range(3600 - 600, 3600 + 600)


# Test for no price drop (price is above target)
@patch("tasks.price_check.scrape_product_info", return_value=mock_product_info)
@patch("tasks.price_check.send_signal_message")
@patch("tasks.price_check.check_price.apply_async")
def test_check_price_no_drop(
    mock_apply_async, mock_send_signal, mock_scrape, valid_url, lower_target_price
):
    check_price(valid_url, lower_target_price)

    # Verify that scrape_product_info was called with the correct URL
    mock_scrape.assert_called_once_with(valid_url)

    # Verify that send_signal_message was not called since the price is higher than the target price
    mock_send_signal.assert_not_called()

    # Verify that apply_async is called to reschedule the task
    assert mock_apply_async.called
    assert mock_apply_async.call_args[1]["countdown"] in range(3600 - 600, 3600 + 600)


# Test for failure during scraping (raises an exception)
@patch("tasks.price_check.scrape_product_info", side_effect=Exception("Scraping failed"))
@patch("tasks.price_check.send_signal_message")
@patch("tasks.price_check.check_price.apply_async")
def test_check_price_failure(
    mock_apply_async, mock_send_signal, mock_scrape, valid_url, target_price
):
    check_price(valid_url, target_price)

    # Verify that scrape_product_info was called but failed
    mock_scrape.assert_called_once_with(valid_url)

    # Verify that send_signal_message was not called due to failure
    mock_send_signal.assert_not_called()

    # Verify that apply_async is still called to reschedule the task
    assert mock_apply_async.called
    assert mock_apply_async.call_args[1]["countdown"] in range(3600 - 600, 3600 + 600)
