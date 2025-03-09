import os
from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv
from services.notification import send_signal_message, send_signal_message_to_group

# Load environment variables from .env file
load_dotenv()

# Get phone number from .env
signal_phone_number = os.getenv("SIGNAL_PHONE_NUMBER")
signal_group_id = os.getenv("SIGNAL_GROUP_ID")


# Test successful message sending with send_signal_message
@patch("services.notification.subprocess.run")
@patch("services.notification.settings")
def test_send_signal_message_success(mock_settings, mock_run):
    # Mock the settings
    mock_settings.SIGNAL_PHONE_NUMBER = signal_phone_number
    mock_settings.SIGNAL_GROUP_ID = signal_group_id
    
    # Mock the result of subprocess.run to simulate a successful call
    mock_run.return_value = MagicMock(returncode=0)

    message = "Test Signal Message"

    send_signal_message(message)

    # Verify that subprocess.run was called with the correct arguments
    mock_run.assert_called_once_with(
        [
            "signal-cli",
            "-u",
            signal_phone_number,
            "send",
            "-g",
            signal_group_id,
            "-m",
            message,
        ],
        stdout=-1,
        stderr=-1,
    )

    # Verify that no exceptions were raised and message was sent successfully
    assert mock_run.return_value.returncode == 0


# Test failure in message sending (non-zero return code) with send_signal_message
@patch("services.notification.subprocess.run")
@patch("services.notification.settings")
def test_send_signal_message_failure(mock_settings, mock_run):
    # Mock the settings
    mock_settings.SIGNAL_PHONE_NUMBER = signal_phone_number
    mock_settings.SIGNAL_GROUP_ID = signal_group_id
    
    # Simulate a failure (non-zero return code)
    mock_run.return_value = MagicMock(
        returncode=1, stderr=MagicMock(decode=MagicMock(return_value="Failed to send"))
    )

    message = "Test Signal Message"

    with pytest.raises(
        Exception, match="Signal message to group failed: Failed to send"
    ):
        send_signal_message(message)

    # Verify that subprocess.run was called with the correct arguments
    mock_run.assert_called_once_with(
        [
            "signal-cli",
            "-u",
            signal_phone_number,
            "send",
            "-g",
            signal_group_id,
            "-m",
            message,
        ],
        stdout=-1,
        stderr=-1,
    )

    # Verify that the exception is raised due to non-zero return code
    assert mock_run.return_value.returncode != 0


# Test exception handling for subprocess errors with send_signal_message
@patch("services.notification.subprocess.run", side_effect=Exception("Subprocess error"))
@patch("services.notification.settings")
def test_send_signal_message_exception(mock_settings, mock_run):
    # Mock the settings
    mock_settings.SIGNAL_PHONE_NUMBER = signal_phone_number
    mock_settings.SIGNAL_GROUP_ID = signal_group_id
    
    message = "Test Signal Message"

    with pytest.raises(Exception, match="Subprocess error"):
        send_signal_message(message)

    # Verify that subprocess.run was called with the correct arguments
    mock_run.assert_called_once_with(
        [
            "signal-cli",
            "-u",
            signal_phone_number,
            "send",
            "-g",
            signal_group_id,
            "-m",
            message,
        ],
        stdout=-1,
        stderr=-1,
    )


# Test successful message sending with send_signal_message_to_group
@patch("services.notification.subprocess.run")
@patch("services.notification.settings")
def test_send_signal_message_to_group_success(mock_settings, mock_run):
    # Mock the settings
    mock_settings.SIGNAL_PHONE_NUMBER = signal_phone_number
    
    # Mock the result of subprocess.run to simulate a successful call
    mock_run.return_value = MagicMock(returncode=0)

    group_id = "custom-group-id"
    message = "Test Signal Message"

    send_signal_message_to_group(group_id, message)

    # Verify that subprocess.run was called with the correct arguments
    mock_run.assert_called_once_with(
        [
            "signal-cli",
            "-u",
            signal_phone_number,
            "send",
            "-g",
            group_id,
            "-m",
            message,
        ],
        stdout=-1,
        stderr=-1,
    )

    # Verify that no exceptions were raised and message was sent successfully
    assert mock_run.return_value.returncode == 0


# Test failure in message sending (non-zero return code) with send_signal_message_to_group
@patch("services.notification.subprocess.run")
@patch("services.notification.settings")
def test_send_signal_message_to_group_failure(mock_settings, mock_run):
    # Mock the settings
    mock_settings.SIGNAL_PHONE_NUMBER = signal_phone_number
    
    # Simulate a failure (non-zero return code)
    mock_run.return_value = MagicMock(
        returncode=1, stderr=MagicMock(decode=MagicMock(return_value="Failed to send"))
    )

    group_id = "custom-group-id"
    message = "Test Signal Message"

    with pytest.raises(
        Exception, match="Signal message to group failed: Failed to send"
    ):
        send_signal_message_to_group(group_id, message)

    # Verify that subprocess.run was called with the correct arguments
    mock_run.assert_called_once_with(
        [
            "signal-cli",
            "-u",
            signal_phone_number,
            "send",
            "-g",
            group_id,
            "-m",
            message,
        ],
        stdout=-1,
        stderr=-1,
    )

    # Verify that the exception is raised due to non-zero return code
    assert mock_run.return_value.returncode != 0


# Test exception handling for subprocess errors with send_signal_message_to_group
@patch("services.notification.subprocess.run", side_effect=Exception("Subprocess error"))
@patch("services.notification.settings")
def test_send_signal_message_to_group_exception(mock_settings, mock_run):
    # Mock the settings
    mock_settings.SIGNAL_PHONE_NUMBER = signal_phone_number
    
    group_id = "custom-group-id"
    message = "Test Signal Message"

    with pytest.raises(Exception, match="Subprocess error"):
        send_signal_message_to_group(group_id, message)

    # Verify that subprocess.run was called with the correct arguments
    mock_run.assert_called_once_with(
        [
            "signal-cli",
            "-u",
            signal_phone_number,
            "send",
            "-g",
            group_id,
            "-m",
            message,
        ],
        stdout=-1,
        stderr=-1,
    )
