from unittest.mock import MagicMock, patch

import pytest

from tasks.price_check import check_price


@pytest.fixture
def mock_scraper():
    """Mock the scraper function."""
    with patch("tasks.price_check.scrape_product_info") as mock:
        # Mock the scraper to return a valid product
        mock.return_value = {
            "title": "Test Product",
            "price": "$80",
            "url": "https://example.com/product",
        }
        yield mock


@pytest.fixture
def mock_db_session():
    """Mock the database session."""
    with patch("tasks.price_check.get_db_session") as mock:
        # Create a mock session
        mock_session = MagicMock()
        mock.return_value = mock_session
        yield mock_session


@pytest.fixture
def mock_signal():
    """Mock the Signal notification function."""
    with patch("tasks.price_check.send_signal_message") as mock:
        yield mock


@pytest.fixture
def mock_apply_async():
    """Mock the apply_async method of the Celery task."""
    with patch("tasks.price_check.check_price.apply_async") as mock:
        yield mock


def test_check_price_task_price_drop(mock_scraper, mock_db_session, mock_signal, mock_apply_async):
    """Test the check_price task when the price drops below the target price."""
    # Mock the database query to return a product
    mock_product = MagicMock()
    mock_product.id = 1
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_product

    # Call the task
    url = "https://example.com/product"
    target_price = 90.0
    check_price(url, target_price)

    # Verify that the scraper was called
    mock_scraper.assert_called_once_with(url)

    # Verify that a price history entry was added
    mock_db_session.add.assert_called_once()
    mock_db_session.commit.assert_called_once()

    # Verify that a notification was sent
    mock_signal.assert_called_once_with(
        f"Price drop alert! Test Product is now $80.\nTarget price was 90.0.\nURL: {url}"
    )

    # Verify that the task was rescheduled
    mock_apply_async.assert_called_once()
    # Check that args parameter contains the URL and target price
    assert mock_apply_async.call_args.kwargs["args"] == [url, target_price]
    # Check that countdown parameter is present
    assert "countdown" in mock_apply_async.call_args.kwargs


def test_check_price_task_no_price_drop(
    mock_scraper, mock_db_session, mock_signal, mock_apply_async
):
    """Test the check_price task when the price is above the target price."""
    # Mock the database query to return a product
    mock_product = MagicMock()
    mock_product.id = 1
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_product

    # Call the task
    url = "https://example.com/product"
    target_price = 70.0
    check_price(url, target_price)

    # Verify that the scraper was called
    mock_scraper.assert_called_once_with(url)

    # Verify that a price history entry was added
    mock_db_session.add.assert_called_once()
    mock_db_session.commit.assert_called_once()

    # Verify that no notification was sent
    mock_signal.assert_not_called()

    # Verify that the task was rescheduled
    mock_apply_async.assert_called_once()
    # Check that args parameter contains the URL and target price
    assert mock_apply_async.call_args.kwargs["args"] == [url, target_price]
    # Check that countdown parameter is present
    assert "countdown" in mock_apply_async.call_args.kwargs


def test_check_price_task_product_not_found(
    mock_scraper, mock_db_session, mock_signal, mock_apply_async
):
    """Test the check_price task when the product is not found in the database."""
    # Mock the database query to return None
    mock_db_session.query.return_value.filter.return_value.first.return_value = None

    # Call the task
    url = "https://example.com/product"
    target_price = 90.0
    check_price(url, target_price)

    # Verify that the scraper was called
    mock_scraper.assert_called_once_with(url)

    # Verify that no price history entry was added
    mock_db_session.add.assert_not_called()
    mock_db_session.commit.assert_not_called()

    # Verify that no notification was sent
    mock_signal.assert_not_called()

    # Verify that the task was rescheduled
    mock_apply_async.assert_called_once()
    # Check that args parameter contains the URL and target price
    assert mock_apply_async.call_args.kwargs["args"] == [url, target_price]
    # Check that countdown parameter is present
    assert "countdown" in mock_apply_async.call_args.kwargs


def test_check_price_task_database_error(
    mock_scraper, mock_db_session, mock_signal, mock_apply_async
):
    """Test the check_price task when there is a database error."""
    # Mock the database query to return a product
    mock_product = MagicMock()
    mock_product.id = 1
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_product

    # Mock a database error
    mock_db_session.add.side_effect = Exception("Database error")

    # Call the task
    url = "https://example.com/product"
    target_price = 90.0
    check_price(url, target_price)

    # Verify that the scraper was called
    mock_scraper.assert_called_once_with(url)

    # Verify that rollback was called
    mock_db_session.rollback.assert_called_once()

    # Verify that no notification was sent
    mock_signal.assert_not_called()

    # Verify that the task was rescheduled
    mock_apply_async.assert_called_once()
    # Check that args parameter contains the URL and target price
    assert mock_apply_async.call_args.kwargs["args"] == [url, target_price]
    # Check that countdown parameter is present
    assert "countdown" in mock_apply_async.call_args.kwargs


def test_check_price_task_scraper_error(
    mock_scraper, mock_db_session, mock_signal, mock_apply_async
):
    """Test the check_price task when there is a scraper error."""
    # Mock a scraper error
    mock_scraper.side_effect = Exception("Scraping failed")

    # Call the task
    url = "https://example.com/product"
    target_price = 90.0
    check_price(url, target_price)

    # Verify that the scraper was called
    mock_scraper.assert_called_once_with(url)

    # Verify that the database session was not used
    mock_db_session.query.assert_not_called()

    # Verify that no notification was sent
    mock_signal.assert_not_called()

    # Verify that the task was rescheduled
    mock_apply_async.assert_called_once()
    # Check that args parameter contains the URL and target price
    assert mock_apply_async.call_args.kwargs["args"] == [url, target_price]
    # Check that countdown parameter is present
    assert "countdown" in mock_apply_async.call_args.kwargs
