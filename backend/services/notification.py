import subprocess
from config import settings


def send_signal_message_to_group(group_id: str, message: str):
    """
    Sends a message to a Signal group using signal-cli.
    """
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
            raise Exception(
                f"Signal message to group failed: {result.stderr.decode().strip()}"
            )

        print(f"Message sent to group {group_id}: {message}")
    except Exception as e:
        print(f"Error sending Signal message to group: {e}")
