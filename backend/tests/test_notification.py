import os
from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv
from services.notification import send_signal_message, send_signal_message_to_group
from config import settings

# Load environment variables from .env file
load_dotenv()

# Get phone number from .env or use default test values
signal_phone_number = os.getenv("SIGNAL_PHONE_NUMBER", "+1234567890")
signal_group_id = os.getenv("SIGNAL_GROUP_ID", "test_group_id_12345678")


# Mock the Prometheus metrics
@pytest.fixture(autouse=True)
def mock_prometheus_metrics():
    with patch("services.notification.SIGNAL_MESSAGES_SENT") as mock_sent:
        with patch("services.notification.SIGNAL_MESSAGES_FAILED") as mock_failed:
            # Create mock Counter objects
            mock_sent.labels.return_value.inc = MagicMock()
            mock_failed.labels.return_value.inc = MagicMock()
            yield mock_sent, mock_failed


# Test successful message sending with send_signal_message
@patch("services.notification.subprocess.run")
@patch("services.notification.settings")
def test_send_signal_message_success(mock_settings, mock_run, mock_prometheus_metrics):
    # Unpack the mocks
    mock_sent, mock_failed = mock_prometheus_metrics
    
    # Reset mocks to ensure clean state
    mock_sent.reset_mock()
    mock_failed.reset_mock()
    
    # Mock the settings with valid test values
    mock_settings.SIGNAL_PHONE_NUMBER = signal_phone_number
    mock_settings.SIGNAL_GROUP_ID = signal_group_id
    
    # Mock the result of subprocess.run to simulate a successful call
    mock_run.return_value = MagicMock(returncode=0)
    
    message = "Test Signal Message"
    
    # Call the function
    send_signal_message(message)
    
    # Verify that subprocess.run was called with the correct arguments
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    command = args[0]
    
    assert command[0] == "signal-cli"
    assert command[1] == "-u"
    assert command[2] == signal_phone_number
    assert command[3] == "send"
    assert command[4] == "-g"
    assert command[5] == signal_group_id
    assert command[6] == "-m"
    assert command[7] == message
    
    # Verify that the success metric was incremented
    mock_sent.labels.assert_called_once_with(type="group")
    mock_sent.labels.return_value.inc.assert_called_once()


# Test failure in message sending (non-zero return code) with send_signal_message
@patch("services.notification.subprocess.run")
@patch("services.notification.settings")
def test_send_signal_message_failure(mock_settings, mock_run, mock_prometheus_metrics):
    # Unpack the mocks
    mock_sent, mock_failed = mock_prometheus_metrics
    
    # Reset mocks to ensure clean state
    mock_sent.reset_mock()
    mock_failed.reset_mock()
    
    # Mock the settings with valid test values
    mock_settings.SIGNAL_PHONE_NUMBER = signal_phone_number
    mock_settings.SIGNAL_GROUP_ID = signal_group_id
    
    # Simulate a failure (non-zero return code)
    mock_run.return_value = MagicMock(
        returncode=1, stderr=MagicMock(decode=MagicMock(return_value="Failed to send"))
    )
    
    message = "Test Signal Message"
    
    # Call the function and expect an exception
    with pytest.raises(Exception, match="Signal message failed: Failed to send"):
        send_signal_message(message)
    
    # Verify that the failure metric was incremented
    mock_failed.labels.assert_called_once_with(type="group", error_type="command_error")
    mock_failed.labels.return_value.inc.assert_called_once()


# Test exception handling for subprocess errors with send_signal_message
@patch("services.notification.subprocess.run", side_effect=Exception("Subprocess error"))
@patch("services.notification.settings")
def test_send_signal_message_exception(mock_settings, mock_run, mock_prometheus_metrics):
    # Unpack the mocks
    mock_sent, mock_failed = mock_prometheus_metrics
    
    # Reset mocks to ensure clean state
    mock_sent.reset_mock()
    mock_failed.reset_mock()
    
    # Mock the settings with valid test values
    mock_settings.SIGNAL_PHONE_NUMBER = signal_phone_number
    mock_settings.SIGNAL_GROUP_ID = signal_group_id
    
    message = "Test Signal Message"
    
    # Call the function and expect an exception
    with pytest.raises(Exception, match="Subprocess error"):
        send_signal_message(message)
    
    # Verify that the failure metric was incremented
    mock_failed.labels.assert_called_once_with(type="group", error_type="Exception")
    mock_failed.labels.return_value.inc.assert_called_once()


# Test successful message sending with send_signal_message_to_group
@patch("services.notification.subprocess.run")
@patch("services.notification.settings")
def test_send_signal_message_to_group_success(mock_settings, mock_run, mock_prometheus_metrics):
    # Unpack the mocks
    mock_sent, mock_failed = mock_prometheus_metrics
    
    # Reset mocks to ensure clean state
    mock_sent.reset_mock()
    mock_failed.reset_mock()
    
    # Mock the settings with valid test values
    mock_settings.SIGNAL_PHONE_NUMBER = signal_phone_number
    
    # Mock the result of subprocess.run to simulate a successful call
    mock_run.return_value = MagicMock(returncode=0)
    
    group_id = signal_group_id
    message = "Test Signal Message"
    
    # Call the function
    send_signal_message_to_group(group_id, message)
    
    # Verify that subprocess.run was called with the correct arguments
    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    command = args[0]
    
    assert command[0] == "signal-cli"
    assert command[1] == "-u"
    assert command[2] == signal_phone_number
    assert command[3] == "send"
    assert command[4] == "-g"
    assert command[5] == group_id
    assert command[6] == "-m"
    assert command[7] == message
    
    # Verify that the success metric was incremented
    mock_sent.labels.assert_called_once_with(type="specific_group")
    mock_sent.labels.return_value.inc.assert_called_once()


# Test failure in message sending (non-zero return code) with send_signal_message_to_group
@patch("services.notification.subprocess.run")
@patch("services.notification.settings")
def test_send_signal_message_to_group_failure(mock_settings, mock_run, mock_prometheus_metrics):
    # Unpack the mocks
    mock_sent, mock_failed = mock_prometheus_metrics
    
    # Reset mocks to ensure clean state
    mock_sent.reset_mock()
    mock_failed.reset_mock()
    
    # Mock the settings with valid test values
    mock_settings.SIGNAL_PHONE_NUMBER = signal_phone_number
    
    # Simulate a failure (non-zero return code)
    mock_run.return_value = MagicMock(
        returncode=1, stderr=MagicMock(decode=MagicMock(return_value="Failed to send"))
    )
    
    group_id = signal_group_id
    message = "Test Signal Message"
    
    # Call the function and expect an exception
    with pytest.raises(Exception, match="Failed to send Signal message to specific group: Failed to send"):
        send_signal_message_to_group(group_id, message)
    
    # Verify that the failure metric was incremented
    mock_failed.labels.assert_called_once_with(type="specific_group", error_type="command_error")
    mock_failed.labels.return_value.inc.assert_called_once()


# Test exception handling for subprocess errors with send_signal_message_to_group
@patch("services.notification.subprocess.run", side_effect=Exception("Subprocess error"))
@patch("services.notification.settings")
def test_send_signal_message_to_group_exception(mock_settings, mock_run, mock_prometheus_metrics):
    # Unpack the mocks
    mock_sent, mock_failed = mock_prometheus_metrics
    
    # Reset mocks to ensure clean state
    mock_sent.reset_mock()
    mock_failed.reset_mock()
    
    # Mock the settings with valid test values
    mock_settings.SIGNAL_PHONE_NUMBER = signal_phone_number
    
    group_id = signal_group_id
    message = "Test Signal Message"
    
    # Call the function and expect an exception
    with pytest.raises(Exception, match="Subprocess error"):
        send_signal_message_to_group(group_id, message)
    
    # Verify that the failure metric was incremented
    mock_failed.labels.assert_called_once_with(type="specific_group", error_type="Exception")
    mock_failed.labels.return_value.inc.assert_called_once()
