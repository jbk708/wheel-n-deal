import subprocess

from config import settings
from utils.logging import get_logger
from utils.monitoring import SIGNAL_MESSAGES_FAILED, SIGNAL_MESSAGES_SENT

# Setup logger
logger = get_logger("notification")


def send_signal_message(message: str):
    """
    Sends a message to a Signal group using signal-cli.
    Uses the group ID from settings.
    """
    group_id = settings.SIGNAL_GROUP_ID
    if not group_id:
        error_msg = "Signal group ID is not configured"
        logger.error(error_msg)
        SIGNAL_MESSAGES_FAILED.labels(type="group", error_type="configuration_error").inc()
        raise Exception(f"Signal message failed: {error_msg}")
        
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
        result = subprocess.run(command, capture_output=True)

        if result.returncode != 0:
            error_message = result.stderr.decode().strip()
            logger.error(f"Failed to send Signal message: {error_message}")
            SIGNAL_MESSAGES_FAILED.labels(type="group", error_type="command_error").inc()
            raise Exception(f"Signal message failed: {error_message}")

        logger.info(f"Message sent to group {group_id[:8]}")
        SIGNAL_MESSAGES_SENT.labels(type="group").inc()
    except Exception as e:
        # Only log and increment metrics if it's not our own exception
        if not str(e).startswith("Signal message failed:"):
            logger.error(f"Error sending Signal message: {str(e)}")
            SIGNAL_MESSAGES_FAILED.labels(type="group", error_type=type(e).__name__).inc()
        raise


def send_signal_message_to_group(group_id: str, message: str):
    """
    Sends a message to a specific Signal group using signal-cli.
    """
    if not group_id:
        error_msg = "Signal group ID is not provided"
        logger.error(error_msg)
        SIGNAL_MESSAGES_FAILED.labels(type="specific_group", error_type="configuration_error").inc()
        raise Exception(f"Failed to send Signal message to specific group: {error_msg}")
        
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
        result = subprocess.run(command, capture_output=True)

        if result.returncode != 0:
            error_message = result.stderr.decode().strip()
            logger.error(f"Failed to send Signal message to specific group: {error_message}")
            SIGNAL_MESSAGES_FAILED.labels(type="specific_group", error_type="command_error").inc()
            raise Exception(f"Failed to send Signal message to specific group: {error_message}")

        logger.info(f"Message sent to specific group {group_id[:8]}")
        SIGNAL_MESSAGES_SENT.labels(type="specific_group").inc()
    except Exception as e:
        # Only log and increment metrics if it's not our own exception
        if not str(e).startswith("Failed to send Signal message to specific group:"):
            logger.error(f"Error sending Signal message to specific group: {str(e)}")
            SIGNAL_MESSAGES_FAILED.labels(type="specific_group", error_type=type(e).__name__).inc()
        raise
