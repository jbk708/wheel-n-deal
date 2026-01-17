import subprocess

from config import settings
from utils.logging import get_logger
from utils.monitoring import SIGNAL_MESSAGES_FAILED, SIGNAL_MESSAGES_SENT

logger = get_logger("notification")


def send_signal_message_to_group(group_id: str | None = None, message: str = "") -> None:
    """
    Sends a message to a Signal group using signal-cli.

    Args:
        group_id: The Signal group ID. Defaults to settings.SIGNAL_GROUP_ID if not provided.
        message: The message to send.
    """
    group_id = group_id or settings.SIGNAL_GROUP_ID
    if not group_id:
        logger.error("Signal group ID is not configured")
        SIGNAL_MESSAGES_FAILED.labels(type="group", error_type="configuration_error").inc()
        raise RuntimeError("Signal message failed: Signal group ID is not configured")

    logger.info("Sending message to Signal group: %s...", group_id[:8])

    try:
        command = [
            "signal-cli",
            "-u",
            settings.SIGNAL_PHONE_NUMBER,
            "send",
            "-g",
            group_id,
            "-m",
            message,
        ]
        result = subprocess.run(command, capture_output=True)

        if result.returncode != 0:
            error_message = result.stderr.decode().strip()
            logger.error("Failed to send Signal message: %s", error_message)
            SIGNAL_MESSAGES_FAILED.labels(type="group", error_type="command_error").inc()
            raise RuntimeError(f"Signal message failed: {error_message}")

        logger.info("Message sent to group %s", group_id[:8])
        SIGNAL_MESSAGES_SENT.labels(type="group").inc()
    except RuntimeError:
        raise
    except Exception as e:
        logger.error("Error sending Signal message: %s", e)
        SIGNAL_MESSAGES_FAILED.labels(type="group", error_type=type(e).__name__).inc()
        raise


def send_signal_message_to_user(phone_number: str, message: str) -> None:
    """
    Sends a direct message to a Signal user using signal-cli.

    Args:
        phone_number: The recipient's phone number in E.164 format (e.g., "+1234567890").
        message: The message to send.
    """
    if not phone_number:
        logger.error("Recipient phone number is required")
        SIGNAL_MESSAGES_FAILED.labels(type="direct", error_type="configuration_error").inc()
        raise ValueError("Recipient phone number is required")

    logger.info("Sending direct message to %s...", phone_number[:6])

    try:
        command = [
            "signal-cli",
            "-u",
            settings.SIGNAL_PHONE_NUMBER,
            "send",
            "-m",
            message,
            phone_number,
        ]
        result = subprocess.run(command, capture_output=True)

        if result.returncode != 0:
            error_message = result.stderr.decode().strip()
            logger.error("Failed to send direct Signal message: %s", error_message)
            SIGNAL_MESSAGES_FAILED.labels(type="direct", error_type="command_error").inc()
            raise RuntimeError(f"Signal message failed: {error_message}")

        logger.info("Direct message sent to %s", phone_number[:6])
        SIGNAL_MESSAGES_SENT.labels(type="direct").inc()
    except (RuntimeError, ValueError):
        raise
    except Exception as e:
        logger.error("Error sending direct Signal message: %s", e)
        SIGNAL_MESSAGES_FAILED.labels(type="direct", error_type=type(e).__name__).inc()
        raise


# Alias for backward compatibility
def send_signal_message(message: str):
    """Sends a message to the default Signal group from settings."""
    send_signal_message_to_group(message=message)
