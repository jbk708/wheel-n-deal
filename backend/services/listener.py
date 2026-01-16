import re
import subprocess
import time

from fastapi import HTTPException
from pydantic import BaseModel

from config import settings
from models import PriceHistory, get_db_session
from models import Product as DBProduct
from routers.tracker import track_product
from services.notification import send_signal_message_to_group
from utils.logging import get_logger
from utils.monitoring import TRACKED_PRODUCTS

# Setup logger
logger = get_logger("listener")


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
    logger.debug(f"Parsing message: {message}")

    if "track" in message.lower():
        # Extract URL and optional target price using regex
        url_match = re.search(r"(https?://\S+)", message)
        price_match = re.search(r"(\d+(\.\d{1,2})?)", message)

        if url_match:
            url = url_match.group(0)
            target_price = float(price_match.group(0)) if price_match else None
            logger.info(f"Parsed track command: URL={url}, target_price={target_price}")
            return {"command": "track", "url": url, "target_price": target_price}
        else:
            logger.warning("Invalid URL format in track command")
            return {
                "command": "invalid",
                "message": "Invalid URL format. Use 'track <url> <target_price>'.",
            }

    elif "status" in message.lower():
        logger.info("Parsed status command")
        return {"command": "status"}

    elif "help" in message.lower():
        logger.info("Parsed help command")
        return {"command": "help"}

    elif "list" in message.lower():
        logger.info("Parsed list command")
        return {"command": "list"}

    elif "stop" in message.lower():
        # Extract the number after "stop"
        number_match = re.search(r"stop\s+(\d+)", message.lower())
        if number_match:
            try:
                number = int(number_match.group(1))
                logger.info(f"Parsed stop command: number={number}")
                return {"command": "stop", "number": number}
            except ValueError:
                logger.warning("Invalid number format in stop command")
                return {
                    "command": "invalid",
                    "message": "Invalid number format. Use 'stop <number>'.",
                }
        else:
            logger.warning("Invalid stop command format")
            return {
                "command": "invalid",
                "message": "Invalid stop command. Use 'stop <number>'.",
            }

    else:
        logger.warning(f"Unknown command: {message}")
        return {
            "command": "invalid",
            "message": "Unknown command. Type 'help' for available commands.",
        }


def handle_help_message():
    """
    Generate a help message with available commands.
    """
    logger.debug("Generating help message")
    message = """
Available commands:
- track <url> [target_price] - Track a product URL with optional target price
- status - Check if the bot is running
- list - List all tracked products
- stop <number> - Stop tracking a product by its number in the list
- help - Show this help message
    """
    return message


def handle_list_tracked_items():
    """
    Generate a message with all tracked items.
    """
    logger.info("Handling list tracked items command")
    db = get_db_session()
    try:
        products = db.query(DBProduct).all()

        # Update the tracked products metric
        TRACKED_PRODUCTS.set(len(products))

        if not products:
            logger.info("No products are currently being tracked")
            return "No products are currently being tracked."

        message = "Currently tracked products:\n"
        for i, product in enumerate(products, 1):
            # Get the latest price
            latest_price = (
                db.query(PriceHistory)
                .filter(PriceHistory.product_id == product.id)
                .order_by(PriceHistory.timestamp.desc())
                .first()
            )

            current_price = latest_price.price if latest_price else "Unknown"

            message += f"{i}. {product.title}\n"
            message += f"   Current price: ${current_price}\n"
            message += f"   Target price: ${product.target_price}\n"
            message += f"   URL: {product.url}\n\n"

        logger.debug(f"Generated list of {len(products)} tracked products")
        return message
    except Exception as e:
        logger.error(f"Error retrieving tracked products: {e!s}", exc_info=True)
        return f"Error retrieving tracked products: {e!s}"
    finally:
        db.close()


def stop_tracking_item(index: int):
    """
    Stop tracking the item by its index in the tracked products list.
    """
    logger.info(f"Handling stop tracking command for item at index {index}")
    db = get_db_session()
    try:
        # Get all products
        products = db.query(DBProduct).all()

        # Update the tracked products metric
        TRACKED_PRODUCTS.set(len(products))

        if 0 <= index < len(products):
            product_to_delete = products[index]

            # Delete the product and its price history (cascade)
            db.delete(product_to_delete)
            db.commit()

            # Update the tracked products metric after deletion
            TRACKED_PRODUCTS.set(len(products) - 1)

            logger.info(f"Stopped tracking product: {product_to_delete.title}")
            return f"Stopped tracking: {product_to_delete.title}."
        else:
            logger.warning(f"Invalid product index: {index}, valid range is 0-{len(products) - 1}")
            return f"Invalid number. Please provide a number between 1 and {len(products)}."
    except Exception as e:
        db.rollback()
        logger.error(f"Error stopping tracking: {e!s}", exc_info=True)
        return f"Error stopping tracking: {e!s}"
    finally:
        db.close()


def listen_to_group():
    """
    Listens to the Signal group for incoming messages and responds to commands.
    """
    group_id = settings.SIGNAL_GROUP_ID
    command = ["signal-cli", "-u", settings.SIGNAL_PHONE_NUMBER, "receive"]

    logger.info(f"Starting Signal listener for group {group_id[:8]}...")

    while True:
        try:
            logger.debug("Waiting for Signal messages...")
            result = subprocess.run(command, capture_output=True)
            if result.returncode == 0:
                output = result.stdout.decode("utf-8")
                if group_id in output:
                    logger.info(f"Message received from group: {output[:100]}...")

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
                            # Call the API function to track the product
                            logger.info(f"Tracking product: {product.url}")
                            track_product(product)

                            send_signal_message_to_group(
                                group_id,
                                f"Product is now being tracked: {product.url}. Target price: {product.target_price}",
                            )
                        except HTTPException as e:
                            logger.error(f"Failed to track product: {e.detail!s}")
                            send_signal_message_to_group(
                                group_id, f"Failed to track product: {e.detail!s}"
                            )

                    elif parsed_command["command"] == "status":
                        # Respond with the bot's status
                        logger.info("Sending status message")
                        send_signal_message_to_group(
                            group_id, "Bot is running and tracking products!"
                        )

                    elif parsed_command["command"] == "list":
                        # Return the list of tracked items
                        logger.info("Sending list of tracked items")
                        list_message = handle_list_tracked_items()
                        send_signal_message_to_group(group_id, list_message)

                    elif parsed_command["command"] == "stop":
                        # Stop tracking the selected item
                        logger.info(f"Stopping tracking for item {parsed_command['number']}")
                        stop_message = stop_tracking_item(parsed_command["number"] - 1)
                        send_signal_message_to_group(group_id, stop_message)

                    elif parsed_command["command"] == "help":
                        # Send the help message
                        logger.info("Sending help message")
                        help_message = handle_help_message()
                        send_signal_message_to_group(group_id, help_message)

                    else:
                        # Handle invalid commands
                        logger.warning(f"Invalid command: {parsed_command['message']}")
                        send_signal_message_to_group(group_id, parsed_command["message"])

            else:
                error_message = result.stderr.decode("utf-8")
                logger.error(f"Failed to receive messages: {error_message}")
        except Exception as e:
            logger.error(f"Error while listening to Signal group: {e!s}", exc_info=True)

        logger.debug("Sleeping for 5 seconds before checking for new messages...")
        time.sleep(5)
