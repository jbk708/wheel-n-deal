"""Tests for signal-cli JSON parsing."""

import json

from services.signal_parser import SignalMessage, parse_signal_json


class TestSignalMessage:
    """Tests for the SignalMessage dataclass."""

    def test_create_message_with_all_fields(self):
        """SignalMessage can be created with all fields."""
        msg = SignalMessage(
            sender_phone="+1234567890",
            sender_name="John Doe",
            message="Hello world",
            group_id="abc123==",
            timestamp=1704067200000,
        )
        assert msg.sender_phone == "+1234567890"
        assert msg.sender_name == "John Doe"
        assert msg.message == "Hello world"
        assert msg.group_id == "abc123=="
        assert msg.timestamp == 1704067200000

    def test_create_message_without_optional_fields(self):
        """SignalMessage can be created with None for optional fields."""
        msg = SignalMessage(
            sender_phone="+1234567890",
            sender_name=None,
            message="Hello",
            group_id=None,
            timestamp=1704067200000,
        )
        assert msg.sender_phone == "+1234567890"
        assert msg.sender_name is None
        assert msg.group_id is None


class TestParseSignalJson:
    """Tests for parsing signal-cli JSON output."""

    def test_parse_group_message_with_sender_name(self):
        """Parse a group message with sender name."""
        json_data = {
            "envelope": {
                "source": "+1234567890",
                "sourceName": "John Doe",
                "timestamp": 1704067200000,
                "dataMessage": {
                    "message": "track https://amazon.com/product 29.99",
                    "groupInfo": {"groupId": "dGVzdGdyb3VwaWQ="},
                },
            }
        }
        result = parse_signal_json(json.dumps(json_data))

        assert len(result) == 1
        msg = result[0]
        assert msg.sender_phone == "+1234567890"
        assert msg.sender_name == "John Doe"
        assert msg.message == "track https://amazon.com/product 29.99"
        assert msg.group_id == "dGVzdGdyb3VwaWQ="
        assert msg.timestamp == 1704067200000

    def test_parse_group_message_without_sender_name(self):
        """Parse a group message when sender name is not available."""
        json_data = {
            "envelope": {
                "source": "+1987654321",
                "timestamp": 1704067200000,
                "dataMessage": {
                    "message": "help",
                    "groupInfo": {"groupId": "dGVzdGdyb3VwaWQ="},
                },
            }
        }
        result = parse_signal_json(json.dumps(json_data))

        assert len(result) == 1
        msg = result[0]
        assert msg.sender_phone == "+1987654321"
        assert msg.sender_name is None
        assert msg.message == "help"

    def test_parse_direct_message(self):
        """Parse a direct message (no group)."""
        json_data = {
            "envelope": {
                "source": "+1234567890",
                "sourceName": "Jane Smith",
                "timestamp": 1704067200000,
                "dataMessage": {"message": "status"},
            }
        }
        result = parse_signal_json(json.dumps(json_data))

        assert len(result) == 1
        msg = result[0]
        assert msg.sender_phone == "+1234567890"
        assert msg.sender_name == "Jane Smith"
        assert msg.message == "status"
        assert msg.group_id is None

    def test_parse_multiple_messages(self):
        """Parse multiple newline-separated JSON objects."""
        msg1 = {
            "envelope": {
                "source": "+1111111111",
                "sourceName": "User One",
                "timestamp": 1704067200000,
                "dataMessage": {"message": "first message"},
            }
        }
        msg2 = {
            "envelope": {
                "source": "+2222222222",
                "sourceName": "User Two",
                "timestamp": 1704067201000,
                "dataMessage": {"message": "second message"},
            }
        }
        json_output = json.dumps(msg1) + "\n" + json.dumps(msg2)
        result = parse_signal_json(json_output)

        assert len(result) == 2
        assert result[0].sender_phone == "+1111111111"
        assert result[0].message == "first message"
        assert result[1].sender_phone == "+2222222222"
        assert result[1].message == "second message"

    def test_parse_empty_string_returns_empty_list(self):
        """Empty input returns empty list."""
        result = parse_signal_json("")
        assert result == []

    def test_parse_whitespace_only_returns_empty_list(self):
        """Whitespace-only input returns empty list."""
        result = parse_signal_json("   \n\n   ")
        assert result == []

    def test_skip_receipt_messages(self):
        """Skip receipt messages (no dataMessage)."""
        json_data = {
            "envelope": {
                "source": "+1234567890",
                "timestamp": 1704067200000,
                "receiptMessage": {"type": "DELIVERY", "timestamps": [1704067199000]},
            }
        }
        result = parse_signal_json(json.dumps(json_data))
        assert result == []

    def test_skip_typing_indicators(self):
        """Skip typing indicator messages."""
        json_data = {
            "envelope": {
                "source": "+1234567890",
                "timestamp": 1704067200000,
                "typingMessage": {"action": "STARTED"},
            }
        }
        result = parse_signal_json(json.dumps(json_data))
        assert result == []

    def test_skip_messages_without_text(self):
        """Skip data messages that have no text content."""
        json_data = {
            "envelope": {
                "source": "+1234567890",
                "timestamp": 1704067200000,
                "dataMessage": {
                    "attachments": [{"contentType": "image/jpeg"}],
                },
            }
        }
        result = parse_signal_json(json.dumps(json_data))
        assert result == []

    def test_handle_invalid_json_gracefully(self):
        """Invalid JSON is skipped without raising an error."""
        json_output = "not valid json\n" + json.dumps(
            {
                "envelope": {
                    "source": "+1234567890",
                    "timestamp": 1704067200000,
                    "dataMessage": {"message": "valid message"},
                }
            }
        )
        result = parse_signal_json(json_output)

        assert len(result) == 1
        assert result[0].message == "valid message"

    def test_handle_missing_envelope_gracefully(self):
        """JSON without envelope field is skipped."""
        json_data = {"something": "else"}
        result = parse_signal_json(json.dumps(json_data))
        assert result == []

    def test_parse_source_number_field(self):
        """Some signal-cli versions use sourceNumber instead of source."""
        json_data = {
            "envelope": {
                "sourceNumber": "+1234567890",
                "sourceName": "Test User",
                "timestamp": 1704067200000,
                "dataMessage": {"message": "test"},
            }
        }
        result = parse_signal_json(json.dumps(json_data))

        assert len(result) == 1
        assert result[0].sender_phone == "+1234567890"

    def test_prefer_source_over_source_number(self):
        """When both source and sourceNumber exist, prefer source."""
        json_data = {
            "envelope": {
                "source": "+1111111111",
                "sourceNumber": "+2222222222",
                "timestamp": 1704067200000,
                "dataMessage": {"message": "test"},
            }
        }
        result = parse_signal_json(json.dumps(json_data))

        assert len(result) == 1
        assert result[0].sender_phone == "+1111111111"
