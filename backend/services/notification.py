import subprocess
from config import settings
from utils.logging import get_logger
from utils.monitoring import SIGNAL_MESSAGES_SENT, SIGNAL_MESSAGES_FAILED

# Setup logger
logger = get_logger("notification")


def send_signal_message(message: str):
    """
    Sends a message to a Signal group using signal-cli.
    Uses the group ID from settings.
    """
    group_id = settings.SIGNAL_GROUP_ID
    logger.info(f"Sending message to Signal group: {group_id[:8]}...")
    
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
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if result.returncode != 0:
            error_message = result.stderr.decode().strip()
            logger.error(f"Failed to send Signal message: {error_message}")
            SIGNAL_MESSAGES_FAILED.labels(type="group", error_type="command_error").inc()
            raise Exception(
                f"Signal message failed: {error_message}"
            )

        logger.info(f"Message sent to group {group_id[:8]}")
        SIGNAL_MESSAGES_SENT.labels(type="group").inc()
    except Exception as e:
        logger.error(f"Error sending Signal message: {str(e)}")
        if not isinstance(e, Exception) or "Signal message failed" not in str(e):
            SIGNAL_MESSAGES_FAILED.labels(type="group", error_type=type(e).__name__).inc()
        raise e  # Re-raise the exception so it can be caught by tests or calling code


def send_signal_message_to_group(group_id: str, message: str):
    """
    Sends a message to a specific Signal group using signal-cli.
    """
    logger.info(f"Sending message to specific Signal group: {group_id[:8]}...")
    
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
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if result.returncode != 0:
            error_message = result.stderr.decode().strip()
            logger.error(f"Failed to send Signal message to specific group: {error_message}")
            SIGNAL_MESSAGES_FAILED.labels(type="specific_group", error_type="command_error").inc()
            raise Exception(
                f"Signal message to group failed: {error_message}"
            )

        logger.info(f"Message sent to specific group {group_id[:8]}")
        SIGNAL_MESSAGES_SENT.labels(type="specific_group").inc()
    except Exception as e:
        logger.error(f"Error sending Signal message to specific group: {str(e)}")
        if not isinstance(e, Exception) or "Signal message to group failed" not in str(e):
            SIGNAL_MESSAGES_FAILED.labels(type="specific_group", error_type=type(e).__name__).inc()
        raise e  # Re-raise the exception so it can be caught by tests or calling code
