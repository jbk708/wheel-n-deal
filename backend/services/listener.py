import subprocess
import time
from config import settings
from services.notification import send_signal_message_to_group


def listen_to_group():
    """
    Listens to the Signal group for incoming messages and responds to commands.
    """
    group_id = settings.SIGNAL_GROUP_ID
    command = ["signal-cli", "-u", settings.SIGNAL_PHONE_NUMBER, "receive"]

    while True:
        try:
            result = subprocess.run(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            if result.returncode == 0:
                output = result.stdout.decode("utf-8")
                if group_id in output:
                    print("Message received from group:", output)
                    # Respond if the message contains a specific command
                    if "status" in output.lower():
                        send_signal_message_to_group(
                            group_id, "Bot is running and tracking products!"
                        )
            else:
                print(f"Failed to receive messages: {result.stderr.decode('utf-8')}")
        except Exception as e:
            print(f"Error while listening to Signal group: {e}")

        time.sleep(5)
