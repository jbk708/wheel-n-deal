"""Integration tests for Celery tasks."""

from unittest.mock import MagicMock

from tasks.price_check import check_price

TEST_URL = "https://example.com/product"
TEST_TARGET_PRICE = 90.0


def assert_task_rescheduled(mock_apply_async, url: str, target_price: float) -> None:
    """Verify that the Celery task was rescheduled with correct arguments."""
    mock_apply_async.assert_called_once()
    assert mock_apply_async.call_args.kwargs["args"] == [url, target_price]
    assert "countdown" in mock_apply_async.call_args.kwargs


def test_check_price_task_price_drop(
    mock_celery_scraper, mock_celery_db_session, mock_celery_signal, mock_apply_async
):
    """Test notification is sent when price drops below target."""
    mock_product = MagicMock()
    mock_product.id = 1
    mock_celery_db_session.query.return_value.filter.return_value.first.return_value = mock_product

    check_price(TEST_URL, TEST_TARGET_PRICE)

    mock_celery_scraper.assert_called_once_with(TEST_URL)
    mock_celery_db_session.add.assert_called_once()
    mock_celery_db_session.commit.assert_called_once()
    mock_celery_signal.assert_called_once_with(
        f"Price drop alert! Test Product is now $80.00.\n"
        f"Target price was {TEST_TARGET_PRICE}.\nURL: {TEST_URL}"
    )
    assert_task_rescheduled(mock_apply_async, TEST_URL, TEST_TARGET_PRICE)


def test_check_price_task_no_price_drop(
    mock_celery_scraper, mock_celery_db_session, mock_celery_signal, mock_apply_async
):
    """Test no notification when price is above target."""
    mock_product = MagicMock()
    mock_product.id = 1
    mock_celery_db_session.query.return_value.filter.return_value.first.return_value = mock_product

    target_price = 70.0
    check_price(TEST_URL, target_price)

    mock_celery_scraper.assert_called_once_with(TEST_URL)
    mock_celery_db_session.add.assert_called_once()
    mock_celery_db_session.commit.assert_called_once()
    mock_celery_signal.assert_not_called()
    assert_task_rescheduled(mock_apply_async, TEST_URL, target_price)


def test_check_price_task_product_not_found(
    mock_celery_scraper, mock_celery_db_session, mock_celery_signal, mock_apply_async
):
    """Test graceful handling when product is not in database."""
    mock_celery_db_session.query.return_value.filter.return_value.first.return_value = None

    check_price(TEST_URL, TEST_TARGET_PRICE)

    mock_celery_scraper.assert_called_once_with(TEST_URL)
    mock_celery_db_session.add.assert_not_called()
    mock_celery_db_session.commit.assert_not_called()
    mock_celery_signal.assert_not_called()
    assert_task_rescheduled(mock_apply_async, TEST_URL, TEST_TARGET_PRICE)


def test_check_price_task_database_error(
    mock_celery_scraper, mock_celery_db_session, mock_celery_signal, mock_apply_async
):
    """Test rollback and reschedule on database error."""
    mock_product = MagicMock()
    mock_product.id = 1
    mock_celery_db_session.query.return_value.filter.return_value.first.return_value = mock_product
    mock_celery_db_session.add.side_effect = Exception("Database error")

    check_price(TEST_URL, TEST_TARGET_PRICE)

    mock_celery_scraper.assert_called_once_with(TEST_URL)
    mock_celery_db_session.rollback.assert_called_once()
    mock_celery_signal.assert_not_called()
    assert_task_rescheduled(mock_apply_async, TEST_URL, TEST_TARGET_PRICE)


def test_check_price_task_scraper_error(
    mock_celery_scraper, mock_celery_db_session, mock_celery_signal, mock_apply_async
):
    """Test reschedule on scraper error without database interaction."""
    mock_celery_scraper.side_effect = Exception("Scraping failed")

    check_price(TEST_URL, TEST_TARGET_PRICE)

    mock_celery_scraper.assert_called_once_with(TEST_URL)
    mock_celery_db_session.query.assert_not_called()
    mock_celery_signal.assert_not_called()
    assert_task_rescheduled(mock_apply_async, TEST_URL, TEST_TARGET_PRICE)
