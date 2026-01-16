from unittest.mock import MagicMock, patch

import pytest

from tasks.price_check import check_price

# Mock product info data
mock_product_info = {
    "title": "Test Product",
    "price": "$80.00",
    "price_float": 80.0,
    "url": "https://example.com/product",
}


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
@patch("tasks.price_check.get_db_session")
def test_check_price_success(
    mock_get_db_session,
    mock_apply_async,
    mock_send_signal,
    mock_scrape,
    valid_url,
    target_price,
):
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    # Mock the product query
    mock_product = MagicMock()
    mock_product.id = 1
    mock_session.query.return_value.filter.return_value.first.return_value = mock_product

    check_price(valid_url, target_price)

    # Verify that scrape_product_info was called with the correct URL
    mock_scrape.assert_called_once_with(valid_url)

    # Verify that a price history entry was added
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()

    # Verify that send_signal_message was called since the price is lower than target_price
    mock_send_signal.assert_called_once_with(
        f"Price drop alert! Test Product is now $80.00.\nTarget price was 90.0.\nURL: {valid_url}"
    )

    # Verify that apply_async is called to reschedule the task
    assert mock_apply_async.called
    countdown = mock_apply_async.call_args[1]["countdown"]
    assert 3600 - 600 <= countdown <= 3600 + 600, (
        f"Countdown {countdown} is not within expected range"
    )

    # Verify that the database session was closed
    mock_session.close.assert_called_once()


# Test for no price drop (price is above target)
@patch("tasks.price_check.scrape_product_info", return_value=mock_product_info)
@patch("tasks.price_check.send_signal_message")
@patch("tasks.price_check.check_price.apply_async")
@patch("tasks.price_check.get_db_session")
def test_check_price_no_drop(
    mock_get_db_session,
    mock_apply_async,
    mock_send_signal,
    mock_scrape,
    valid_url,
    lower_target_price,
):
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    # Mock the product query
    mock_product = MagicMock()
    mock_product.id = 1
    mock_session.query.return_value.filter.return_value.first.return_value = mock_product

    check_price(valid_url, lower_target_price)

    # Verify that scrape_product_info was called with the correct URL
    mock_scrape.assert_called_once_with(valid_url)

    # Verify that a price history entry was added
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()

    # Verify that send_signal_message was not called since the price is higher than the target price
    mock_send_signal.assert_not_called()

    # Verify that apply_async is called to reschedule the task
    assert mock_apply_async.called
    countdown = mock_apply_async.call_args[1]["countdown"]
    assert 3600 - 600 <= countdown <= 3600 + 600, (
        f"Countdown {countdown} is not within expected range"
    )

    # Verify that the database session was closed
    mock_session.close.assert_called_once()


# Test for product not found in database
@patch("tasks.price_check.scrape_product_info", return_value=mock_product_info)
@patch("tasks.price_check.send_signal_message")
@patch("tasks.price_check.check_price.apply_async")
@patch("tasks.price_check.get_db_session")
def test_check_price_product_not_found(
    mock_get_db_session,
    mock_apply_async,
    mock_send_signal,
    mock_scrape,
    valid_url,
    target_price,
):
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    # Mock the product query (product not found)
    mock_session.query.return_value.filter.return_value.first.return_value = None

    check_price(valid_url, target_price)

    # Verify that scrape_product_info was called with the correct URL
    mock_scrape.assert_called_once_with(valid_url)

    # Verify that no price history entry was added
    mock_session.add.assert_not_called()
    mock_session.commit.assert_not_called()

    # Verify that send_signal_message was not called
    mock_send_signal.assert_not_called()

    # Verify that apply_async is called to reschedule the task
    assert mock_apply_async.called
    countdown = mock_apply_async.call_args[1]["countdown"]
    assert 3600 - 600 <= countdown <= 3600 + 600, (
        f"Countdown {countdown} is not within expected range"
    )

    # Verify that the database session was closed
    mock_session.close.assert_called_once()


# Test for database error
@patch("tasks.price_check.scrape_product_info", return_value=mock_product_info)
@patch("tasks.price_check.send_signal_message")
@patch("tasks.price_check.check_price.apply_async")
@patch("tasks.price_check.get_db_session")
def test_check_price_database_error(
    mock_get_db_session,
    mock_apply_async,
    mock_send_signal,
    mock_scrape,
    valid_url,
    target_price,
):
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    # Mock the product query
    mock_product = MagicMock()
    mock_product.id = 1
    mock_session.query.return_value.filter.return_value.first.return_value = mock_product

    # Mock a database error
    mock_session.add.side_effect = Exception("Database error")

    check_price(valid_url, target_price)

    # Verify that scrape_product_info was called with the correct URL
    mock_scrape.assert_called_once_with(valid_url)

    # Verify that rollback was called
    mock_session.rollback.assert_called_once()

    # Verify that send_signal_message was not called
    mock_send_signal.assert_not_called()

    # Verify that apply_async is called to reschedule the task
    assert mock_apply_async.called
    countdown = mock_apply_async.call_args[1]["countdown"]
    assert 3600 - 600 <= countdown <= 3600 + 600, (
        f"Countdown {countdown} is not within expected range"
    )

    # Verify that the database session was closed
    mock_session.close.assert_called_once()


# Test for failure during scraping (raises an exception)
@patch("tasks.price_check.scrape_product_info", side_effect=Exception("Scraping failed"))
@patch("tasks.price_check.send_signal_message")
@patch("tasks.price_check.check_price.apply_async")
@patch("tasks.price_check.get_db_session")
def test_check_price_scraping_failure(
    mock_get_db_session,
    mock_apply_async,
    mock_send_signal,
    mock_scrape,
    valid_url,
    target_price,
):
    check_price(valid_url, target_price)

    # Verify that scrape_product_info was called but failed
    mock_scrape.assert_called_once_with(valid_url)

    # Verify that the database session was not used
    mock_get_db_session.assert_not_called()

    # Verify that send_signal_message was not called due to failure
    mock_send_signal.assert_not_called()

    # Verify that apply_async is still called to reschedule the task
    assert mock_apply_async.called
    countdown = mock_apply_async.call_args[1]["countdown"]
    assert 3600 - 600 <= countdown <= 3600 + 600, (
        f"Countdown {countdown} is not within expected range"
    )
