from unittest.mock import MagicMock, patch

import pytest

from services.listener import (
    handle_help_message,
    handle_list_tracked_items,
    listen_to_group,
    parse_message,
    stop_tracking_item,
)


def test_parse_message_track_with_url_and_price():
    """Test parsing a track message with URL and price."""
    message = "track https://example.com/product 90.00"
    result = parse_message(message)

    assert result["command"] == "track"
    assert result["url"] == "https://example.com/product"
    assert result["target_price"] == 90.0


def test_parse_message_track_with_url_only():
    """Test parsing a track message with URL only."""
    message = "track https://example.com/product"
    result = parse_message(message)

    assert result["command"] == "track"
    assert result["url"] == "https://example.com/product"
    assert result["target_price"] is None


def test_parse_message_track_invalid_url():
    """Test parsing a track message with invalid URL."""
    message = "track invalid-url"
    result = parse_message(message)

    assert result["command"] == "invalid"
    assert "Invalid URL format" in result["message"]


def test_parse_message_status():
    """Test parsing a status message."""
    message = "status"
    result = parse_message(message)

    assert result["command"] == "status"


def test_parse_message_help():
    """Test parsing a help message."""
    message = "help"
    result = parse_message(message)

    assert result["command"] == "help"


def test_parse_message_list():
    """Test parsing a list message."""
    message = "list"
    result = parse_message(message)

    assert result["command"] == "list"


def test_parse_message_stop_valid():
    """Test parsing a valid stop message."""
    message = "stop 1"
    result = parse_message(message)

    assert result["command"] == "stop"
    assert result["number"] == 1


def test_parse_message_stop_invalid_format():
    """Test parsing an invalid stop message (no number)."""
    message = "stop"
    result = parse_message(message)

    assert result["command"] == "invalid"
    assert "Invalid stop command" in result["message"]


def test_parse_message_unknown():
    """Test parsing an unknown message."""
    message = "unknown command"
    result = parse_message(message)

    assert result["command"] == "invalid"
    assert "Unknown command" in result["message"]


def test_handle_help_message():
    """Test the help message handler."""
    result = handle_help_message()

    assert "Available commands" in result
    assert "track" in result
    assert "status" in result
    assert "list" in result
    assert "stop" in result
    assert "help" in result


@patch("services.listener.get_db_session")
def test_handle_list_tracked_items_empty(mock_get_db_session):
    """Test listing tracked items when there are none."""
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    # Mock the query result (empty list)
    mock_session.query.return_value.all.return_value = []

    result = handle_list_tracked_items()

    assert "No products are currently being tracked" in result
    mock_session.close.assert_called_once()


@patch("services.listener.get_db_session")
def test_handle_list_tracked_items_with_products(mock_get_db_session):
    """Test listing tracked items when there are products."""
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    # Create mock products
    mock_product1 = MagicMock()
    mock_product1.id = 1
    mock_product1.title = "Test Product 1"
    mock_product1.url = "https://example.com/product1"
    mock_product1.target_price = 90.0

    mock_product2 = MagicMock()
    mock_product2.id = 2
    mock_product2.title = "Test Product 2"
    mock_product2.url = "https://example.com/product2"
    mock_product2.target_price = 80.0

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

    result = handle_list_tracked_items()

    assert "Currently tracked products" in result
    assert "Test Product 1" in result
    assert "Test Product 2" in result
    assert "Current price: $100.0" in result
    assert "Target price: $90.0" in result
    mock_session.close.assert_called_once()


@patch("services.listener.get_db_session")
def test_stop_tracking_item_valid(mock_get_db_session):
    """Test stopping tracking an item with a valid index."""
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    # Create mock products
    mock_product1 = MagicMock()
    mock_product1.id = 1
    mock_product1.title = "Test Product 1"

    mock_product2 = MagicMock()
    mock_product2.id = 2
    mock_product2.title = "Test Product 2"

    # Mock the query result
    mock_session.query.return_value.all.return_value = [mock_product1, mock_product2]

    result = stop_tracking_item(0)  # Stop tracking the first product

    assert "Stopped tracking: Test Product 1" in result
    mock_session.delete.assert_called_once_with(mock_product1)
    mock_session.commit.assert_called_once()
    mock_session.close.assert_called_once()


@patch("services.listener.get_db_session")
def test_stop_tracking_item_invalid_index(mock_get_db_session):
    """Test stopping tracking an item with an invalid index."""
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    # Create mock products
    mock_product1 = MagicMock()
    mock_product1.id = 1
    mock_product1.title = "Test Product 1"

    # Mock the query result
    mock_session.query.return_value.all.return_value = [mock_product1]

    result = stop_tracking_item(1)  # Invalid index

    assert "Invalid number" in result
    mock_session.delete.assert_not_called()
    mock_session.commit.assert_not_called()
    mock_session.close.assert_called_once()


@patch("services.listener.get_db_session")
def test_stop_tracking_item_exception(mock_get_db_session):
    """Test stopping tracking an item when an exception occurs."""
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    # Create mock products
    mock_product1 = MagicMock()
    mock_product1.id = 1
    mock_product1.title = "Test Product 1"

    # Mock the query result
    mock_session.query.return_value.all.return_value = [mock_product1]

    # Mock an exception during delete
    mock_session.delete.side_effect = Exception("Database error")

    result = stop_tracking_item(0)

    assert "Error stopping tracking" in result
    mock_session.delete.assert_called_once_with(mock_product1)
    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()


class MockSubprocessResult:
    def __init__(self, returncode, stdout_text):
        self.returncode = returncode
        self.stdout = stdout_text.encode("utf-8")

    def decode(self):
        return self.stdout.decode("utf-8")


@patch("services.listener.subprocess.run")
@patch("services.listener.time.sleep")
@patch("services.listener.parse_message")
@patch("services.listener.scrape_product_info")
@patch("services.listener.get_db_session")
@patch("services.listener.send_signal_message_to_group")
@patch("services.listener.handle_help_message")
@patch("services.listener.handle_list_tracked_items")
@patch("services.listener.stop_tracking_item")
@patch("services.listener.settings")
def test_listen_to_group_track_command(
    mock_settings,
    mock_stop_tracking,
    mock_list_items,
    mock_help_message,
    mock_send_message,
    mock_get_db_session,
    mock_scrape,
    mock_parse_message,
    mock_sleep,
    mock_run,
):
    """Test the listen_to_group function with a track command."""
    # Set up the mock settings
    mock_settings.SIGNAL_GROUP_ID = "test-group-id"
    mock_settings.SIGNAL_PHONE_NUMBER = "test-phone-number"

    # Set up the mock subprocess run result
    mock_result = MockSubprocessResult(0, "test-group-id: track https://example.com/product 90.00")
    mock_run.return_value = mock_result

    # Set up the mock parse_message result
    mock_parse_message.return_value = {
        "command": "track",
        "url": "https://example.com/product",
        "target_price": 90.0,
    }

    # Set up the mock database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session
    mock_session.query.return_value.filter.return_value.first.return_value = None

    # Set up mock scrape result
    mock_scrape.return_value = {
        "title": "Test Product",
        "price": "$100.00",
        "price_float": 100.0,
    }

    # Make the function exit after one iteration
    mock_sleep.side_effect = Exception("Stop the loop")

    # Call the function
    with pytest.raises(Exception, match="Stop the loop"):
        listen_to_group()

    # Verify the function calls
    mock_run.assert_called_once()
    mock_parse_message.assert_called_once_with(
        "test-group-id: track https://example.com/product 90.00"
    )
    mock_scrape.assert_called_once_with("https://example.com/product")
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()
    mock_send_message.assert_called_once()
    mock_sleep.assert_called_once()
