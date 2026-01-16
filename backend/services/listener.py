import re
import subprocess
import time

from config import settings
from models import PriceHistory, get_db_session
from models import Product as DBProduct
from services.notification import send_signal_message_to_group
from services.scraper import scrape_product_info
from utils.logging import get_logger
from utils.monitoring import TRACKED_PRODUCTS

logger = get_logger("listener")


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

        if url_match:
            url = url_match.group(0)
            # Look for target price AFTER the URL - must be a standalone number
            # Only match price if explicitly provided (e.g., "track <url> 15.99")
            after_url = message[url_match.end() :]
            # Match a price that's clearly separate: whitespace + number (with optional decimals)
            price_match = re.search(r"^\s+(\d+(?:\.\d{1,2})?)\s*$", after_url)
            target_price = float(price_match.group(1)) if price_match else None
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


def handle_help_message() -> str:
    """Generate a help message with available commands."""
    logger.debug("Generating help message")
    return """
Available commands:
- track <url> [target_price] - Track a product URL with optional target price
- status - Check if the bot is running
- list - List all tracked products
- stop <number> - Stop tracking a product by its number in the list
- help - Show this help message
    """


def handle_list_tracked_items() -> str:
    """Generate a message with all tracked items."""
    logger.info("Handling list tracked items command")
    db = get_db_session()
    try:
        products = db.query(DBProduct).all()

        if not products:
            logger.info("No products are currently being tracked")
            return "No products are currently being tracked."

        message = "Currently tracked products:\n"
        for i, product in enumerate(products, 1):
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


def stop_tracking_item(index: int) -> str:
    """Stop tracking the item by its index in the tracked products list."""
    logger.info(f"Handling stop tracking command for item at index {index}")
    db = get_db_session()
    try:
        products = db.query(DBProduct).all()

        if not (0 <= index < len(products)):
            logger.warning(f"Invalid product index: {index}, valid range is 0-{len(products) - 1}")
            return f"Invalid number. Please provide a number between 1 and {len(products)}."

        product_to_delete = products[index]
        db.delete(product_to_delete)
        db.commit()
        TRACKED_PRODUCTS.dec()

        logger.info(f"Stopped tracking product: {product_to_delete.title}")
        return f"Stopped tracking: {product_to_delete.title}."
    except Exception as e:
        db.rollback()
        logger.error(f"Error stopping tracking: {e!s}", exc_info=True)
        return f"Error stopping tracking: {e!s}"
    finally:
        db.close()


def handle_track_command(url: str, target_price: float | None) -> str:
    """
    Track a product by URL, scraping its info and storing in the database.

    Returns a message indicating success or failure.
    """
    logger.info(f"Tracking product: {url}")
    db = get_db_session()
    try:
        existing = db.query(DBProduct).filter(DBProduct.url == url).first()
        if existing:
            return f"Product is already being tracked: {url}"

        product_info = scrape_product_info(url)
        if not product_info:
            return f"Failed to scrape product info for: {url}"

        current_price = product_info.get("price_float")
        final_target_price = target_price

        if final_target_price is None and current_price:
            final_target_price = round(current_price * 0.9, 2)

        db_product = DBProduct(
            url=url,
            title=product_info.get("title", "Unknown"),
            target_price=final_target_price or 0,
            user_id=1,  # Default user for Signal tracking
        )
        db.add(db_product)
        db.commit()

        return (
            f"Now tracking: {product_info.get('title', url)}\n"
            f"Current price: ${current_price:.2f}\n"
            f"Target price: ${final_target_price:.2f}"
        )
    except Exception as e:
        logger.error(f"Failed to track product: {e!s}")
        return f"Failed to track product: {e!s}"
    finally:
        db.close()


def listen_to_group() -> None:
    """Listen to the Signal group for incoming messages and respond to commands."""
    group_id = settings.SIGNAL_GROUP_ID
    command = ["signal-cli", "-u", settings.SIGNAL_PHONE_NUMBER, "receive"]

    logger.info(f"Starting Signal listener for group {group_id[:8]}...")

    while True:
        try:
            logger.debug("Waiting for Signal messages...")
            result = subprocess.run(command, capture_output=True)

            if result.returncode != 0:
                error_message = result.stderr.decode("utf-8")
                logger.error(f"Failed to receive messages: {error_message}")
                time.sleep(5)
                continue

            output = result.stdout.decode("utf-8")
            if group_id not in output:
                time.sleep(5)
                continue

            logger.info(f"Message received from group: {output[:100]}...")
            message = output.lower()
            parsed_command = parse_message(message)
            cmd = parsed_command["command"]

            if cmd == "track":
                response = handle_track_command(
                    parsed_command["url"], parsed_command["target_price"]
                )
                send_signal_message_to_group(group_id, response)

            elif cmd == "status":
                logger.info("Sending status message")
                send_signal_message_to_group(group_id, "Bot is running and tracking products!")

            elif cmd == "list":
                logger.info("Sending list of tracked items")
                send_signal_message_to_group(group_id, handle_list_tracked_items())

            elif cmd == "stop":
                logger.info(f"Stopping tracking for item {parsed_command['number']}")
                stop_message = stop_tracking_item(parsed_command["number"] - 1)
                send_signal_message_to_group(group_id, stop_message)

            elif cmd == "help":
                logger.info("Sending help message")
                send_signal_message_to_group(group_id, handle_help_message())

            else:
                logger.warning(f"Invalid command: {parsed_command['message']}")
                send_signal_message_to_group(group_id, parsed_command["message"])

        except Exception as e:
            logger.error(f"Error while listening to Signal group: {e!s}", exc_info=True)

        logger.debug("Sleeping for 5 seconds before checking for new messages...")
        time.sleep(5)
