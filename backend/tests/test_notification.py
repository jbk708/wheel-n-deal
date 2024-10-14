import os
from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv
from services.notification import send_signal_message

# Load environment variables from .env file
load_dotenv()

# Get phone number from .env
signal_phone_number = os.getenv("SIGNAL_PHONE_NUMBER")


# Test successful message sending
@patch("services.notification.subprocess.run")
def test_send_signal_message_success(mock_run):
    # Mock the result of subprocess.run to simulate a successful call
    mock_run.return_value = MagicMock(returncode=0)

    group_id = "group-id"
    message = "Test Signal Message"

    send_signal_message(group_id, message)

    # Verify that subprocess.run was called with the correct arguments
    mock_run.assert_called_once_with(
        [
            "signal-cli",
            "-u",
            signal_phone_number,  # Pull from .env file
            "send",
            "-g",
            group_id,
            "-m",
            message,
        ],
        stdout=-1,  # This matches the actual call behavior
        stderr=-1,  # This matches the actual call behavior
    )

    # Verify that no exceptions were raised and message was sent successfully
    assert mock_run.return_value.returncode == 0


# Test failure in message sending (non-zero return code)
@patch("services.notification.subprocess.run")
def test_send_signal_message_failure(mock_run):
    # Simulate a failure (non-zero return code)
    mock_run.return_value = MagicMock(
        returncode=1, stderr=MagicMock(decode=MagicMock(return_value="Failed to send"))
    )

    group_id = "group-id"
    message = "Test Signal Message"

    with pytest.raises(
        Exception, match="Signal message to group failed: Failed to send"
    ):
        send_signal_message(group_id, message)

    # Verify that subprocess.run was called with the correct arguments
    mock_run.assert_called_once_with(
        [
            "signal-cli",
            "-u",
            signal_phone_number,  # Pull from .env file
            "send",
            "-g",
            group_id,
            "-m",
            message,
        ],
        stdout=-1,  # This matches the actual call behavior
        stderr=-1,  # This matches the actual call behavior
    )

    # Verify that the exception is raised due to non-zero return code
    assert mock_run.return_value.returncode != 0


# Test exception handling for subprocess errors
@patch(
    "services.notification.subprocess.run", side_effect=Exception("Subprocess error")
)
def test_send_signal_message_exception(mock_run):
    group_id = "group-id"
    message = "Test Signal Message"

    with pytest.raises(Exception, match="Subprocess error"):
        send_signal_message(group_id, message)

    # Verify that subprocess.run was called with the correct arguments
    mock_run.assert_called_once_with(
        [
            "signal-cli",
            "-u",
            signal_phone_number,  # Pull from .env file
            "send",
            "-g",
            group_id,
            "-m",
            message,
        ],
        stdout=-1,  # This matches the actual call behavior
        stderr=-1,  # This matches the actual call behavior
    )
