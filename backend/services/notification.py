import subprocess
from config import settings


def send_signal_message(recipient_number: str, message: str):
    """
    Sends a message to a Signal user using signal-cli.
    """
    try:
        command = [
            "signal-cli",
            "-u",
            settings.SIGNAL_PHONE_NUMBER,
            "send",
            recipient_number,
            "-m",
            message,
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if result.returncode != 0:
            raise Exception(f"Signal message failed: {result.stderr.decode().strip()}")

        print(f"Message sent to {recipient_number}: {message}")
    except Exception as e:
        print(f"Error sending Signal message: {e}")
