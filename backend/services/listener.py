import re
import subprocess
import time

from config import settings
from fastapi import HTTPException
from pydantic import BaseModel
from routers.tracker import track_product
from services.notification import send_signal_message_to_group

# List to store tracked products (in-memory for now)
tracked_products = []


# Define a simple Product model for incoming commands
class Product(BaseModel):
    url: str
    target_price: float = None  # Optional target price


def parse_message(message: str):
    """
    Parse the incoming message and extract command, URL, and target price if present.
    Supported commands:
    - "track <url> <target_price>" (target_price is optional)
    - "status"
    - "help"
    - "list" (List tracked items)
    - "stop <number>" (Stop tracking item by number)
    """
    if "track" in message.lower():
        # Extract URL and optional target price using regex
        url_match = re.search(r"(https?://\S+)", message)
        price_match = re.search(r"(\d+(\.\d{1,2})?)", message)

        if url_match:
            url = url_match.group(0)
            target_price = float(price_match.group(0)) if price_match else None
            return {"command": "track", "url": url, "target_price": target_price}
        else:
            return {
                "command": "invalid",
                "message": "Invalid URL format. Use 'track <url> <target_price>'.",
            }

    elif "status" in message.lower():
        return {"command": "status"}

    elif "help" in message.lower():
        return {"command": "help"}

    elif "list" in message.lower():
        return {"command": "list"}

    elif "stop" in message.lower():
        # Extract the number from the stop command
        number_match = re.search(r"(\d+)", message)
        if number_match:
            return {"command": "stop", "number": int(number_match.group(0))}
        else:
            return {
                "command": "invalid",
                "message": "Invalid format. Use 'stop <number>'.",
            }

    else:
        return {
            "command": "invalid",
            "message": "Unknown command. Use 'help' for available commands.",
        }


def handle_help_message():
    """
    Return a help message with available commands.
    """
    help_message = """
    Available commands:
    - track <url> <target_price>: Start tracking a product. Example: "track https://example.com/product 100.00"
      - URL is required, target price is optional (defaults to 10% off).
    - status: Check if the bot is running and tracking products.
    - list: List all currently tracked products.
    - stop <number>: Stop tracking a product by its number from the 'list' command.
    - help: Show this message.
    """
    return help_message


def handle_list_tracked_items():
    """
    Returns the list of currently tracked items.
    """
    if not tracked_products:
        return "No items are currently being tracked."

    message = "Tracked items:\n"
    for i, product in enumerate(tracked_products, 1):
        message += f"{i}. {product['title']} (Target price: {product['target_price']}) - {product['url']}\n"

    return message


def stop_tracking_item(index: int):
    """
    Stop tracking the item by its index in the tracked products list.
    """
    if 0 <= index < len(tracked_products):
        removed_product = tracked_products.pop(index)
        return f"Stopped tracking: {removed_product['title']}."
    else:
        return f"Invalid number. Please provide a number between 1 and {len(tracked_products)}."


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

                    # Extract message from the group
                    message = output.lower()

                    # Parse the message
                    parsed_command = parse_message(message)

                    if parsed_command["command"] == "track":
                        # Call track_product with parsed URL and target price
                        product = Product(
                            url=parsed_command["url"],
                            target_price=parsed_command["target_price"],
                        )

                        try:
                            # Simulate the API call to track_product (you may adapt this as needed)
                            response = track_product(product)

                            # Store the tracked product in memory
                            tracked_products.append(
                                {
                                    "title": response["product_info"]["title"],
                                    "url": product.url,
                                    "target_price": product.target_price or "10% off",
                                }
                            )

                            send_signal_message_to_group(
                                group_id,
                                f"Tracking product: {product.url} with target price {product.target_price or '10% off'}.",
                            )
                        except HTTPException as e:
                            send_signal_message_to_group(
                                group_id, f"Failed to track product: {str(e.detail)}"
                            )

                    elif parsed_command["command"] == "status":
                        # Respond with the bot's status
                        send_signal_message_to_group(
                            group_id, "Bot is running and tracking products!"
                        )

                    elif parsed_command["command"] == "list":
                        # Return the list of tracked items
                        list_message = handle_list_tracked_items()
                        send_signal_message_to_group(group_id, list_message)

                    elif parsed_command["command"] == "stop":
                        # Stop tracking the selected item
                        stop_message = stop_tracking_item(parsed_command["number"] - 1)
                        send_signal_message_to_group(group_id, stop_message)

                    elif parsed_command["command"] == "help":
                        # Send the help message
                        help_message = handle_help_message()
                        send_signal_message_to_group(group_id, help_message)

                    else:
                        # Handle invalid commands
                        send_signal_message_to_group(
                            group_id, parsed_command["message"]
                        )

            else:
                print(f"Failed to receive messages: {result.stderr.decode('utf-8')}")
        except Exception as e:
            print(f"Error while listening to Signal group: {e}")

        time.sleep(5)
