from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from services.listener import (
    handle_help_message,
    handle_list_tracked_items,
    handle_me_command,
    listen_for_messages,
    listen_to_group,
    parse_message,
    send_response,
    stop_tracking_item,
)


def test_parse_message_track_with_url_and_price():
    """Test parsing a !track message with URL and price."""
    result = parse_message("!track https://example.com/product 90.00")

    assert result["command"] == "track"
    assert result["url"] == "https://example.com/product"
    assert result["target_price"] == 90.0


def test_parse_message_track_with_url_only():
    """Test parsing a !track message with URL only."""
    result = parse_message("!track https://example.com/product")

    assert result["command"] == "track"
    assert result["url"] == "https://example.com/product"
    assert result["target_price"] is None


def test_parse_message_track_invalid_url():
    """Test parsing a !track message with invalid URL."""
    result = parse_message("!track invalid-url")

    assert result["command"] == "invalid"
    assert "Invalid URL format" in result["message"]


def test_parse_message_status():
    """Test parsing a !status message."""
    assert parse_message("!status")["command"] == "status"


def test_parse_message_help():
    """Test parsing a !help message."""
    assert parse_message("!help")["command"] == "help"


def test_parse_message_list():
    """Test parsing a !list message."""
    assert parse_message("!list")["command"] == "list"


def test_parse_message_me():
    """Test parsing a !me message."""
    assert parse_message("!me")["command"] == "me"


def test_parse_message_stop_valid():
    """Test parsing a valid !stop message."""
    result = parse_message("!stop 1")

    assert result["command"] == "stop"
    assert result["number"] == 1


def test_parse_message_stop_invalid_format():
    """Test parsing an invalid !stop message (no number)."""
    result = parse_message("!stop")

    assert result["command"] == "invalid"
    assert "Invalid !stop command" in result["message"]


def test_parse_message_unknown_command():
    """Test parsing an unknown ! command."""
    result = parse_message("!unknown")

    assert result["command"] == "invalid"
    assert "Unknown command" in result["message"]


def test_parse_message_without_prefix_ignored():
    """Test that messages without ! prefix are ignored."""
    assert parse_message("track https://example.com/product")["command"] == "ignore"


def test_parse_message_regular_chat_ignored():
    """Test that regular chat messages are ignored."""
    assert parse_message("hey, what's up?")["command"] == "ignore"


def test_parse_message_command_case_insensitive():
    """Test that commands are case-insensitive."""
    result = parse_message("!TRACK https://example.com/product")

    assert result["command"] == "track"
    assert result["url"] == "https://example.com/product"


def test_parse_message_prefix_with_space():
    """Test that ! with space before command is ignored."""
    assert parse_message("! help")["command"] == "ignore"


def test_handle_help_message():
    """Test the help message handler."""
    result = handle_help_message()

    assert "Available commands" in result
    assert "!track" in result
    assert "!status" in result
    assert "!list" in result
    assert "!stop" in result
    assert "!me" in result
    assert "!help" in result


@patch("services.listener.get_db_session")
def test_handle_me_command_with_username(mock_get_db_session):
    """Test !me command with a user that has a username."""
    from datetime import datetime

    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_user = MagicMock(
        id=1,
        signal_username="TestUser",
        signal_phone="+1234567890",
        created_at=datetime(2026, 1, 15, 20, 0, 0),  # UTC
    )
    mock_session.query.return_value.filter.return_value.first.return_value = mock_user
    mock_session.query.return_value.filter.return_value.count.return_value = 3

    result = handle_me_command(user_id=1)

    assert "Your account info" in result
    assert "Name: TestUser" in result
    assert "Member since: Jan 15, 2026" in result
    assert "Products tracked: 3" in result
    mock_session.close.assert_called_once()


@patch("services.listener.get_db_session")
def test_handle_me_command_with_masked_phone(mock_get_db_session):
    """Test !me command with a user that has only a phone number."""
    from datetime import datetime

    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_user = MagicMock(
        id=1,
        signal_username=None,
        signal_phone="+1234567890",
        created_at=datetime(2026, 1, 10, 12, 0, 0),
    )
    mock_session.query.return_value.filter.return_value.first.return_value = mock_user
    mock_session.query.return_value.filter.return_value.count.return_value = 0

    result = handle_me_command(user_id=1)

    assert "Your account info" in result
    assert "Name: +12***7890" in result
    assert "Products tracked: 0" in result
    mock_session.close.assert_called_once()


@patch("services.listener.get_db_session")
def test_handle_me_command_user_not_found(mock_get_db_session):
    """Test !me command when user is not found."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session
    mock_session.query.return_value.filter.return_value.first.return_value = None

    result = handle_me_command(user_id=999)

    assert "Could not find your user record" in result
    mock_session.close.assert_called_once()


@patch("services.listener.get_db_session")
def test_handle_list_tracked_items_empty(mock_get_db_session):
    """Test listing tracked items when there are none for the user."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session
    mock_session.query.return_value.filter.return_value.all.return_value = []

    result = handle_list_tracked_items(user_id=1)

    assert "not tracking any products" in result
    mock_session.close.assert_called_once()


@patch("services.listener.get_db_session")
def test_handle_list_tracked_items_with_products(mock_get_db_session):
    """Test listing tracked items when there are products for the user."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_product1 = MagicMock(
        id=1, title="Test Product 1", url="https://example.com/product1", target_price=90.0
    )
    mock_product2 = MagicMock(
        id=2, title="Test Product 2", url="https://example.com/product2", target_price=80.0
    )

    from datetime import datetime

    # Database stores naive UTC timestamps (no tzinfo)
    mock_timestamp = datetime(2026, 1, 16, 22, 30, 0)  # 22:30 UTC = 2:30 PM Pacific
    mock_price_history1 = MagicMock(price=100.0, timestamp=mock_timestamp)
    mock_price_history2 = MagicMock(price=95.0, timestamp=mock_timestamp)

    mock_product_filter = MagicMock()
    mock_product_filter.all.return_value = [mock_product1, mock_product2]

    mock_price_filter = MagicMock()
    mock_price_order = MagicMock()
    mock_price_filter.order_by.return_value = mock_price_order
    mock_price_order.first.side_effect = [mock_price_history1, mock_price_history2]

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
    assert "Last updated:" in result
    mock_session.close.assert_called_once()


@patch("services.listener.get_db_session")
def test_stop_tracking_item_valid(mock_get_db_session):
    """Test stopping tracking an item with a valid index."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_product1 = MagicMock(id=1, title="Test Product 1")
    mock_product2 = MagicMock(id=2, title="Test Product 2")
    mock_session.query.return_value.filter.return_value.all.return_value = [
        mock_product1,
        mock_product2,
    ]

    result = stop_tracking_item(0, user_id=1)

    assert "Stopped tracking: Test Product 1" in result
    mock_session.delete.assert_called_once_with(mock_product1)
    mock_session.commit.assert_called_once()
    mock_session.close.assert_called_once()


@patch("services.listener.get_db_session")
def test_stop_tracking_item_invalid_index(mock_get_db_session):
    """Test stopping tracking an item with an invalid index."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_product1 = MagicMock(id=1, title="Test Product 1")
    mock_session.query.return_value.filter.return_value.all.return_value = [mock_product1]

    result = stop_tracking_item(1, user_id=1)

    assert "Invalid number" in result
    mock_session.delete.assert_not_called()
    mock_session.commit.assert_not_called()
    mock_session.close.assert_called_once()


@patch("services.listener.get_db_session")
def test_stop_tracking_item_exception(mock_get_db_session):
    """Test stopping tracking an item when an exception occurs."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_product1 = MagicMock(id=1, title="Test Product 1")
    mock_session.query.return_value.filter.return_value.all.return_value = [mock_product1]
    mock_session.delete.side_effect = Exception("Database error")

    result = stop_tracking_item(0, user_id=1)

    assert "Error stopping tracking" in result
    mock_session.delete.assert_called_once_with(mock_product1)
    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()


@dataclass
class MockSubprocessResult:
    returncode: int
    stdout: bytes

    @classmethod
    def success(cls, stdout_text: str) -> "MockSubprocessResult":
        return cls(returncode=0, stdout=stdout_text.encode("utf-8"))


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
    mock_settings.SIGNAL_GROUP_ID = "test-group-id"
    mock_settings.SIGNAL_PHONE_NUMBER = "test-phone-number"

    mock_run.return_value = MockSubprocessResult.success('{"envelope": {"source": "+1234567890"}}')

    mock_signal_msg = MagicMock(
        group_id="test-group-id",
        sender_phone="+1234567890",
        sender_name="Test User",
        message="!track https://example.com/product 90.00",
    )
    mock_parse_signal_json.return_value = [mock_signal_msg]

    mock_user = MagicMock(id=1)
    mock_get_or_create_user.return_value = mock_user

    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_handle_track.return_value = "Now tracking: Test Product"

    mock_sleep.side_effect = Exception("Stop the loop")

    with pytest.raises(Exception, match="Stop the loop"):
        listen_to_group()

    mock_run.assert_called_once()
    mock_parse_signal_json.assert_called_once()
    mock_get_or_create_user.assert_called_once_with(mock_session, "+1234567890", "Test User")
    mock_handle_track.assert_called_once_with("https://example.com/product", 90.0, 1)
    mock_send_message.assert_called_once_with("test-group-id", "Now tracking: Test Product")
    mock_sleep.assert_called_once()


@patch("services.listener.send_signal_message_to_group")
def test_send_response_to_group(mock_send_to_group):
    """Test send_response sends to group when group_id is provided."""
    send_response("test-group-id", "+1234567890", "Test message")
    mock_send_to_group.assert_called_once_with("test-group-id", "Test message")


@patch("services.listener.send_signal_message_to_user")
def test_send_response_to_user(mock_send_to_user):
    """Test send_response sends direct message when group_id is None."""
    send_response(None, "+1234567890", "Test message")
    mock_send_to_user.assert_called_once_with("+1234567890", "Test message")


@patch("services.listener.subprocess.run")
@patch("services.listener.time.sleep")
@patch("services.listener.parse_signal_json")
@patch("services.listener.get_or_create_signal_user")
@patch("services.listener.handle_track_command")
@patch("services.listener.get_db_session")
@patch("services.listener.send_response")
@patch("services.listener.settings")
def test_listen_for_messages_direct_message(
    mock_settings,
    mock_send_response,
    mock_get_db_session,
    mock_handle_track,
    mock_get_or_create_user,
    mock_parse_signal_json,
    mock_sleep,
    mock_run,
):
    """Test listen_for_messages handles direct messages (no group_id)."""
    mock_settings.SIGNAL_GROUP_ID = "test-group-id"
    mock_settings.SIGNAL_PHONE_NUMBER = "test-phone-number"

    mock_run.return_value = MockSubprocessResult.success('{"envelope": {"source": "+1234567890"}}')

    mock_signal_msg = MagicMock(
        group_id=None,
        sender_phone="+1234567890",
        sender_name="Test User",
        message="!track https://example.com/product 90.00",
    )
    mock_parse_signal_json.return_value = [mock_signal_msg]

    mock_user = MagicMock(id=1)
    mock_get_or_create_user.return_value = mock_user

    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_handle_track.return_value = "Now tracking: Test Product"

    mock_sleep.side_effect = Exception("Stop the loop")

    with pytest.raises(Exception, match="Stop the loop"):
        listen_for_messages()

    mock_run.assert_called_once()
    mock_parse_signal_json.assert_called_once()
    mock_get_or_create_user.assert_called_once_with(mock_session, "+1234567890", "Test User")
    mock_handle_track.assert_called_once_with("https://example.com/product", 90.0, 1)
    mock_send_response.assert_called_once_with(None, "+1234567890", "Now tracking: Test Product")
    mock_sleep.assert_called_once()
