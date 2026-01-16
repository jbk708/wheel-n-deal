"""Parse signal-cli JSON output to extract sender and message information."""

import json
from dataclasses import dataclass

from utils.logging import get_logger

logger = get_logger("signal_parser")


@dataclass
class SignalMessage:
    """Parsed Signal message with sender information.

    Attributes:
        sender_phone: The sender's phone number in E.164 format (e.g., "+1234567890").
        sender_name: The sender's profile name if available, otherwise None.
        message: The text content of the message.
        group_id: The base64-encoded group ID if this is a group message, otherwise None.
        timestamp: Unix timestamp of the message in milliseconds.
    """

    sender_phone: str
    sender_name: str | None
    message: str
    group_id: str | None
    timestamp: int


def parse_signal_json(json_output: str) -> list[SignalMessage]:
    """Parse signal-cli JSON output and extract message information.

    signal-cli outputs one JSON object per line when run with --output=json.
    Each JSON object contains an envelope with source, message, and optional group info.

    Args:
        json_output: Raw JSON string output from signal-cli receive --output=json.
            May contain multiple newline-separated JSON objects.

    Returns:
        A list of SignalMessage objects parsed from the JSON output.
        Returns an empty list if no valid messages are found.

    Example JSON structure from signal-cli:
        {
          "envelope": {
            "source": "+1234567890",
            "sourceName": "John Doe",
            "timestamp": 1234567890000,
            "dataMessage": {
              "message": "Hello world",
              "groupInfo": {
                "groupId": "base64groupid=="
              }
            }
          }
        }
    """
    messages: list[SignalMessage] = []
    lines = [line.strip() for line in json_output.strip().split("\n") if line.strip()]

    for line in lines:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("Skipping invalid JSON line: %s...", line[:50])
            continue

        envelope = data.get("envelope")
        if not envelope:
            continue

        data_message = envelope.get("dataMessage")
        if not data_message:
            continue

        message_text = data_message.get("message")
        if not message_text:
            continue

        sender_phone = envelope.get("source") or envelope.get("sourceNumber")
        if not sender_phone:
            logger.warning("Message has no source phone number, skipping")
            continue

        sender_name = envelope.get("sourceName")
        timestamp = envelope.get("timestamp", 0)

        group_info = data_message.get("groupInfo")
        group_id = group_info.get("groupId") if group_info else None

        messages.append(
            SignalMessage(
                sender_phone=sender_phone,
                sender_name=sender_name,
                message=message_text,
                group_id=group_id,
                timestamp=timestamp,
            )
        )

    return messages
