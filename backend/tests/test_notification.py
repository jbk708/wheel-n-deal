from unittest.mock import MagicMock, patch

import pytest

from services.notification import (
    send_signal_message,
    send_signal_message_to_group,
    send_signal_message_to_user,
)

SIGNAL_PHONE_NUMBER = "+1234567890"
SIGNAL_GROUP_ID = "test_group_id_12345678"


@pytest.fixture(autouse=True)
def mock_prometheus_metrics():
    """Mock Prometheus metrics for all tests."""
    with (
        patch("services.notification.SIGNAL_MESSAGES_SENT") as mock_sent,
        patch("services.notification.SIGNAL_MESSAGES_FAILED") as mock_failed,
    ):
        mock_sent.labels.return_value.inc = MagicMock()
        mock_failed.labels.return_value.inc = MagicMock()
        yield mock_sent, mock_failed


@patch("services.notification.subprocess.run")
@patch("services.notification.settings")
def test_send_signal_message_success(mock_settings, mock_run, mock_prometheus_metrics):
    """Test successful message sending with send_signal_message."""
    mock_sent, _ = mock_prometheus_metrics
    mock_sent.reset_mock()

    mock_settings.SIGNAL_PHONE_NUMBER = SIGNAL_PHONE_NUMBER
    mock_settings.SIGNAL_GROUP_ID = SIGNAL_GROUP_ID
    mock_run.return_value = MagicMock(returncode=0)

    send_signal_message("Test Signal Message")

    mock_run.assert_called_once()
    command = mock_run.call_args[0][0]

    assert command == [
        "signal-cli",
        "-u",
        SIGNAL_PHONE_NUMBER,
        "send",
        "-g",
        SIGNAL_GROUP_ID,
        "-m",
        "Test Signal Message",
    ]

    mock_sent.labels.assert_called_once_with(type="group")
    mock_sent.labels.return_value.inc.assert_called_once()


@patch("services.notification.subprocess.run")
@patch("services.notification.settings")
def test_send_signal_message_failure(mock_settings, mock_run, mock_prometheus_metrics):
    """Test failure in message sending (non-zero return code) with send_signal_message."""
    _, mock_failed = mock_prometheus_metrics
    mock_failed.reset_mock()

    mock_settings.SIGNAL_PHONE_NUMBER = SIGNAL_PHONE_NUMBER
    mock_settings.SIGNAL_GROUP_ID = SIGNAL_GROUP_ID
    mock_run.return_value = MagicMock(
        returncode=1, stderr=MagicMock(decode=MagicMock(return_value="Failed to send"))
    )

    with pytest.raises(RuntimeError, match="Signal message failed: Failed to send"):
        send_signal_message("Test Signal Message")

    mock_failed.labels.assert_called_once_with(type="group", error_type="command_error")
    mock_failed.labels.return_value.inc.assert_called_once()


@patch("services.notification.subprocess.run", side_effect=Exception("Subprocess error"))
@patch("services.notification.settings")
def test_send_signal_message_exception(mock_settings, mock_run, mock_prometheus_metrics):
    """Test exception handling for subprocess errors with send_signal_message."""
    _, mock_failed = mock_prometheus_metrics
    mock_failed.reset_mock()

    mock_settings.SIGNAL_PHONE_NUMBER = SIGNAL_PHONE_NUMBER
    mock_settings.SIGNAL_GROUP_ID = SIGNAL_GROUP_ID

    with pytest.raises(Exception, match="Subprocess error"):
        send_signal_message("Test Signal Message")

    mock_failed.labels.assert_called_once_with(type="group", error_type="Exception")
    mock_failed.labels.return_value.inc.assert_called_once()


@patch("services.notification.subprocess.run")
@patch("services.notification.settings")
def test_send_signal_message_to_group_success(mock_settings, mock_run, mock_prometheus_metrics):
    """Test successful message sending with send_signal_message_to_group."""
    mock_sent, _ = mock_prometheus_metrics
    mock_sent.reset_mock()

    mock_settings.SIGNAL_PHONE_NUMBER = SIGNAL_PHONE_NUMBER
    mock_run.return_value = MagicMock(returncode=0)

    send_signal_message_to_group(SIGNAL_GROUP_ID, "Test Signal Message")

    mock_run.assert_called_once()
    command = mock_run.call_args[0][0]

    assert command == [
        "signal-cli",
        "-u",
        SIGNAL_PHONE_NUMBER,
        "send",
        "-g",
        SIGNAL_GROUP_ID,
        "-m",
        "Test Signal Message",
    ]

    mock_sent.labels.assert_called_once_with(type="group")
    mock_sent.labels.return_value.inc.assert_called_once()


@patch("services.notification.subprocess.run")
@patch("services.notification.settings")
def test_send_signal_message_to_group_failure(mock_settings, mock_run, mock_prometheus_metrics):
    """Test failure in message sending (non-zero return code) with send_signal_message_to_group."""
    _, mock_failed = mock_prometheus_metrics
    mock_failed.reset_mock()

    mock_settings.SIGNAL_PHONE_NUMBER = SIGNAL_PHONE_NUMBER
    mock_run.return_value = MagicMock(
        returncode=1, stderr=MagicMock(decode=MagicMock(return_value="Failed to send"))
    )

    with pytest.raises(RuntimeError, match="Signal message failed: Failed to send"):
        send_signal_message_to_group(SIGNAL_GROUP_ID, "Test Signal Message")

    mock_failed.labels.assert_called_once_with(type="group", error_type="command_error")
    mock_failed.labels.return_value.inc.assert_called_once()


@patch("services.notification.subprocess.run", side_effect=Exception("Subprocess error"))
@patch("services.notification.settings")
def test_send_signal_message_to_group_exception(mock_settings, mock_run, mock_prometheus_metrics):
    """Test exception handling for subprocess errors with send_signal_message_to_group."""
    _, mock_failed = mock_prometheus_metrics
    mock_failed.reset_mock()

    mock_settings.SIGNAL_PHONE_NUMBER = SIGNAL_PHONE_NUMBER

    with pytest.raises(Exception, match="Subprocess error"):
        send_signal_message_to_group(SIGNAL_GROUP_ID, "Test Signal Message")

    mock_failed.labels.assert_called_once_with(type="group", error_type="Exception")
    mock_failed.labels.return_value.inc.assert_called_once()


@patch("services.notification.subprocess.run")
@patch("services.notification.settings")
def test_send_signal_message_to_user_success(mock_settings, mock_run, mock_prometheus_metrics):
    """Test successful direct message sending with send_signal_message_to_user."""
    mock_sent, _ = mock_prometheus_metrics
    mock_sent.reset_mock()

    mock_settings.SIGNAL_PHONE_NUMBER = SIGNAL_PHONE_NUMBER
    mock_run.return_value = MagicMock(returncode=0)

    recipient_phone = "+19876543210"
    send_signal_message_to_user(recipient_phone, "Test Direct Message")

    mock_run.assert_called_once()
    command = mock_run.call_args[0][0]

    assert command == [
        "signal-cli",
        "-u",
        SIGNAL_PHONE_NUMBER,
        "send",
        "-m",
        "Test Direct Message",
        recipient_phone,
    ]

    mock_sent.labels.assert_called_once_with(type="direct")
    mock_sent.labels.return_value.inc.assert_called_once()


@patch("services.notification.subprocess.run")
@patch("services.notification.settings")
def test_send_signal_message_to_user_failure(mock_settings, mock_run, mock_prometheus_metrics):
    """Test failure in direct message sending (non-zero return code)."""
    _, mock_failed = mock_prometheus_metrics
    mock_failed.reset_mock()

    mock_settings.SIGNAL_PHONE_NUMBER = SIGNAL_PHONE_NUMBER
    mock_run.return_value = MagicMock(
        returncode=1, stderr=MagicMock(decode=MagicMock(return_value="Failed to send"))
    )

    with pytest.raises(RuntimeError, match="Signal message failed: Failed to send"):
        send_signal_message_to_user("+19876543210", "Test Direct Message")

    mock_failed.labels.assert_called_once_with(type="direct", error_type="command_error")
    mock_failed.labels.return_value.inc.assert_called_once()


def test_send_signal_message_to_user_empty_phone(mock_prometheus_metrics):
    """Test empty phone number raises ValueError."""
    _, mock_failed = mock_prometheus_metrics
    mock_failed.reset_mock()

    with pytest.raises(ValueError, match="Recipient phone number is required"):
        send_signal_message_to_user("", "Test message")

    mock_failed.labels.assert_called_once_with(type="direct", error_type="configuration_error")
    mock_failed.labels.return_value.inc.assert_called_once()
