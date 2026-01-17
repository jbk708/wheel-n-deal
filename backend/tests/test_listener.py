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
    """Test parsing a !track message with URL and price."""
    message = "!track https://example.com/product 90.00"
    result = parse_message(message)

    assert result["command"] == "track"
    assert result["url"] == "https://example.com/product"
    assert result["target_price"] == 90.0


def test_parse_message_track_with_url_only():
    """Test parsing a !track message with URL only."""
    message = "!track https://example.com/product"
    result = parse_message(message)

    assert result["command"] == "track"
    assert result["url"] == "https://example.com/product"
    assert result["target_price"] is None


def test_parse_message_track_invalid_url():
    """Test parsing a !track message with invalid URL."""
    message = "!track invalid-url"
    result = parse_message(message)

    assert result["command"] == "invalid"
    assert "Invalid URL format" in result["message"]


def test_parse_message_status():
    """Test parsing a !status message."""
    message = "!status"
    result = parse_message(message)

    assert result["command"] == "status"


def test_parse_message_help():
    """Test parsing a !help message."""
    message = "!help"
    result = parse_message(message)

    assert result["command"] == "help"


def test_parse_message_list():
    """Test parsing a !list message."""
    message = "!list"
    result = parse_message(message)

    assert result["command"] == "list"


def test_parse_message_stop_valid():
    """Test parsing a valid !stop message."""
    message = "!stop 1"
    result = parse_message(message)

    assert result["command"] == "stop"
    assert result["number"] == 1


def test_parse_message_stop_invalid_format():
    """Test parsing an invalid !stop message (no number)."""
    message = "!stop"
    result = parse_message(message)

    assert result["command"] == "invalid"
    assert "Invalid !stop command" in result["message"]


def test_parse_message_unknown_command():
    """Test parsing an unknown ! command."""
    message = "!unknown"
    result = parse_message(message)

    assert result["command"] == "invalid"
    assert "Unknown command" in result["message"]


def test_parse_message_without_prefix_ignored():
    """Test that messages without ! prefix are ignored."""
    message = "track https://example.com/product"
    result = parse_message(message)

    assert result["command"] == "ignore"


def test_parse_message_regular_chat_ignored():
    """Test that regular chat messages are ignored."""
    message = "hey, what's up?"
    result = parse_message(message)

    assert result["command"] == "ignore"


def test_parse_message_command_case_insensitive():
    """Test that commands are case-insensitive."""
    message = "!TRACK https://example.com/product"
    result = parse_message(message)

    assert result["command"] == "track"
    assert result["url"] == "https://example.com/product"


def test_parse_message_prefix_with_space():
    """Test that ! with space before command still works."""
    message = "! help"
    result = parse_message(message)

    # Should be ignored since there's a space after !
    assert result["command"] == "ignore"


def test_handle_help_message():
    """Test the help message handler."""
    result = handle_help_message()

    assert "Available commands" in result
    assert "!track" in result
    assert "!status" in result
    assert "!list" in result
    assert "!stop" in result
    assert "!help" in result


@patch("services.listener.get_db_session")
def test_handle_list_tracked_items_empty(mock_get_db_session):
    """Test listing tracked items when there are none for the user."""
    # Mock the database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    # Mock the query result (empty list)
    mock_session.query.return_value.filter.return_value.all.return_value = []

    result = handle_list_tracked_items(user_id=1)

    assert "not tracking any products" in result
    mock_session.close.assert_called_once()


@patch("services.listener.get_db_session")
def test_handle_list_tracked_items_with_products(mock_get_db_session):
    """Test listing tracked items when there are products for the user."""
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

    # Mock the price history query
    mock_price_history1 = MagicMock()
    mock_price_history1.price = 100.0

    mock_price_history2 = MagicMock()
    mock_price_history2.price = 95.0

    # Create separate mock chains for product query and price history queries
    mock_product_filter = MagicMock()
    mock_product_filter.all.return_value = [mock_product1, mock_product2]

    mock_price_filter = MagicMock()
    mock_price_order = MagicMock()
    mock_price_filter.order_by.return_value = mock_price_order
    mock_price_order.first.side_effect = [mock_price_history1, mock_price_history2]

    # Track which query is being called (DBProduct vs PriceHistory)
    call_count = [0]

    def mock_filter_side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_product_filter
        return mock_price_filter

    mock_session.query.return_value.filter.side_effect = mock_filter_side_effect

    result = handle_list_tracked_items(user_id=1)

    assert "Your tracked products" in result
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

    # Mock the query result (filtered by user_id)
    mock_session.query.return_value.filter.return_value.all.return_value = [
        mock_product1,
        mock_product2,
    ]

    result = stop_tracking_item(0, user_id=1)  # Stop tracking the first product

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

    # Mock the query result (filtered by user_id)
    mock_session.query.return_value.filter.return_value.all.return_value = [mock_product1]

    result = stop_tracking_item(1, user_id=1)  # Invalid index

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

    # Mock the query result (filtered by user_id)
    mock_session.query.return_value.filter.return_value.all.return_value = [mock_product1]

    # Mock an exception during delete
    mock_session.delete.side_effect = Exception("Database error")

    result = stop_tracking_item(0, user_id=1)

    assert "Error stopping tracking" in result
    mock_session.delete.assert_called_once_with(mock_product1)
    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()


class MockSubprocessResult:
    def __init__(self, returncode: int, stdout_text: str):
        self.returncode = returncode
        self.stdout = stdout_text.encode("utf-8")


@patch("services.listener.subprocess.run")
@patch("services.listener.time.sleep")
@patch("services.listener.parse_signal_json")
@patch("services.listener.get_or_create_signal_user")
@patch("services.listener.handle_track_command")
@patch("services.listener.get_db_session")
@patch("services.listener.send_signal_message_to_group")
@patch("services.listener.settings")
def test_listen_to_group_track_command(
    mock_settings,
    mock_send_message,
    mock_get_db_session,
    mock_handle_track,
    mock_get_or_create_user,
    mock_parse_signal_json,
    mock_sleep,
    mock_run,
):
    """Test the listen_to_group function with a track command."""
    # Set up the mock settings
    mock_settings.SIGNAL_GROUP_ID = "test-group-id"
    mock_settings.SIGNAL_PHONE_NUMBER = "test-phone-number"

    # Set up the mock subprocess run result (JSON output)
    mock_result = MockSubprocessResult(0, '{"envelope": {"source": "+1234567890"}}')
    mock_run.return_value = mock_result

    # Set up mock signal message from parse_signal_json
    mock_signal_msg = MagicMock()
    mock_signal_msg.group_id = "test-group-id"
    mock_signal_msg.sender_phone = "+1234567890"
    mock_signal_msg.sender_name = "Test User"
    mock_signal_msg.message = "!track https://example.com/product 90.00"
    mock_parse_signal_json.return_value = [mock_signal_msg]

    # Set up mock user
    mock_user = MagicMock()
    mock_user.id = 1
    mock_get_or_create_user.return_value = mock_user

    # Set up the mock database session
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    # Set up mock handle_track_command result
    mock_handle_track.return_value = "Now tracking: Test Product"

    # Make the function exit after one iteration
    mock_sleep.side_effect = Exception("Stop the loop")

    # Call the function
    with pytest.raises(Exception, match="Stop the loop"):
        listen_to_group()

    # Verify the function calls
    mock_run.assert_called_once()
    mock_parse_signal_json.assert_called_once()
    mock_get_or_create_user.assert_called_once_with(mock_session, "+1234567890", "Test User")
    mock_handle_track.assert_called_once_with("https://example.com/product", 90.0, 1)
    mock_send_message.assert_called_once_with("test-group-id", "Now tracking: Test Product")
    mock_sleep.assert_called_once()
