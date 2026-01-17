import re
import subprocess
import time

from config import settings
from models import PriceHistory, get_db_session
from models import Product as DBProduct
from services.notification import send_signal_message_to_group
from services.scraper import scrape_product_info
from services.signal_parser import parse_signal_json
from services.user_service import get_or_create_signal_user
from utils.logging import get_logger
from utils.monitoring import TRACKED_PRODUCTS

logger = get_logger("listener")


def parse_message(message: str):
    """
    Parse the incoming message and extract command, URL, and target price if present.

    Commands must start with ! prefix. Messages without prefix are ignored.
    Supported commands:
    - "!track <url> [target_price]" (target_price is optional)
    - "!status"
    - "!help"
    - "!list" (List tracked items)
    - "!stop <number>" (Stop tracking item by number)
    """
    logger.debug("Parsing message: %s", message)

    # Check for ! prefix - ignore messages without it
    stripped = message.strip()
    if not stripped.startswith("!"):
        return {"command": "ignore"}

    # Command must immediately follow ! (no space between ! and command)
    # e.g., "!track url" is valid, "! track url" is not
    command_text = stripped[1:]
    if not command_text or command_text[0].isspace():
        return {"command": "ignore"}

    command_lower = command_text.lower()

    if command_lower.startswith("track"):
        url_match = re.search(r"(https?://\S+)", command_text)
        if not url_match:
            logger.warning("Invalid URL format in !track command")
            return {
                "command": "invalid",
                "message": "Invalid URL format. Use '!track <url> [target_price]'.",
            }

        url = url_match.group(0)
        after_url = command_text[url_match.end() :]
        price_match = re.search(r"^\s+(\d+(?:\.\d{1,2})?)\s*$", after_url)
        target_price = float(price_match.group(1)) if price_match else None
        logger.info("Parsed !track command: URL=%s, target_price=%s", url, target_price)
        return {"command": "track", "url": url, "target_price": target_price}

    elif command_lower == "status":
        logger.info("Parsed !status command")
        return {"command": "status"}

    elif command_lower == "help":
        logger.info("Parsed !help command")
        return {"command": "help"}

    elif command_lower == "list":
        logger.info("Parsed !list command")
        return {"command": "list"}

    elif command_lower.startswith("stop"):
        # Extract the number after "stop"
        number_match = re.search(r"^stop\s+(\d+)$", command_lower)
        if number_match:
            number = int(number_match.group(1))
            logger.info("Parsed !stop command: number=%s", number)
            return {"command": "stop", "number": number}
        else:
            logger.warning("Invalid !stop command format")
            return {
                "command": "invalid",
                "message": "Invalid !stop command. Use '!stop <number>'.",
            }

    else:
        logger.warning("Unknown command: %s", command_text)
        return {
            "command": "invalid",
            "message": "Unknown command. Type '!help' for available commands.",
        }


def handle_help_message() -> str:
    """Generate a help message with available commands."""
    logger.debug("Generating help message")
    return (
        "Available commands:\n"
        "- !track <url> [target_price] - Track a product URL with optional target price\n"
        "- !status - Check if the bot is running\n"
        "- !list - List all tracked products\n"
        "- !stop <number> - Stop tracking a product by its number in the list\n"
        "- !help - Show this help message"
    )


def handle_list_tracked_items(user_id: int) -> str:
    """Generate a message with the user's tracked items."""
    logger.info("Handling list tracked items command for user_id=%s", user_id)
    db = get_db_session()
    try:
        products = db.query(DBProduct).filter(DBProduct.user_id == user_id).all()

        if not products:
            logger.info("No products are currently being tracked for user_id=%s", user_id)
            return "You're not tracking any products yet. Use !track <url> to start."

        message = "Your tracked products:\n"
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

        logger.debug("Generated list of %d tracked products for user_id=%s", len(products), user_id)
        return message
    except Exception as e:
        logger.error("Error retrieving tracked products: %s", e, exc_info=True)
        return f"Error retrieving tracked products: {e!s}"
    finally:
        db.close()


def stop_tracking_item(index: int, user_id: int) -> str:
    """Stop tracking the item by its index in the user's tracked products list."""
    logger.info("Handling stop tracking command for item %d, user_id=%s", index, user_id)
    db = get_db_session()
    try:
        products = db.query(DBProduct).filter(DBProduct.user_id == user_id).all()

        if not products:
            return "You're not tracking any products yet."

        if index < 0 or index >= len(products):
            logger.warning(
                "Invalid product index: %d, valid range is 0-%d", index, len(products) - 1
            )
            return f"Invalid number. Please provide a number between 1 and {len(products)}."

        product_to_delete = products[index]
        db.delete(product_to_delete)
        db.commit()
        TRACKED_PRODUCTS.dec()

        logger.info("Stopped tracking product: %s", product_to_delete.title)
        return f"Stopped tracking: {product_to_delete.title}."
    except Exception as e:
        db.rollback()
        logger.error("Error stopping tracking: %s", e, exc_info=True)
        return f"Error stopping tracking: {e!s}"
    finally:
        db.close()


def handle_track_command(url: str, target_price: float | None, user_id: int) -> str:
    """
    Track a product by URL, scraping its info and storing in the database.

    Args:
        url: The product URL to track.
        target_price: Optional target price for alerts.
        user_id: The user ID to associate with this product.

    Returns:
        A message indicating success or failure.
    """
    logger.info("Tracking product: %s for user_id=%s", url, user_id)
    db = get_db_session()
    try:
        # Check if this user is already tracking this URL
        existing = (
            db.query(DBProduct).filter(DBProduct.url == url, DBProduct.user_id == user_id).first()
        )
        if existing:
            return "You're already tracking this product."

        product_info = scrape_product_info(url)
        if not product_info:
            return f"Failed to scrape product info for: {url}"

        current_price = product_info.get("price_float")
        if target_price is None and current_price:
            target_price = round(current_price * 0.9, 2)

        db_product = DBProduct(
            url=url,
            title=product_info.get("title", "Unknown"),
            target_price=target_price or 0,
            user_id=user_id,
        )
        db.add(db_product)
        db.commit()

        return (
            f"Now tracking: {product_info.get('title', url)}\n"
            f"Current price: ${current_price:.2f}\n"
            f"Target price: ${target_price:.2f}"
        )
    except Exception as e:
        logger.error("Failed to track product: %s", e)
        return f"Failed to track product: {e!s}"
    finally:
        db.close()


def listen_to_group() -> None:
    """Listen to the Signal group for incoming messages and respond to commands."""
    group_id = settings.SIGNAL_GROUP_ID
    command = ["signal-cli", "-u", settings.SIGNAL_PHONE_NUMBER, "--output=json", "receive"]

    logger.info("Starting Signal listener for group %s...", group_id[:8])

    while True:
        try:
            logger.debug("Waiting for Signal messages...")
            result = subprocess.run(command, capture_output=True)

            if result.returncode != 0:
                error_message = result.stderr.decode("utf-8")
                logger.error("Failed to receive messages: %s", error_message)
                time.sleep(5)
                continue

            output = result.stdout.decode("utf-8")
            if not output.strip():
                time.sleep(5)
                continue

            # Parse JSON output to get messages with sender info
            messages = parse_signal_json(output)
            if not messages:
                time.sleep(5)
                continue

            for signal_msg in messages:
                # Only process messages from our group
                if signal_msg.group_id != group_id:
                    continue

                logger.info(
                    "Message from %s (%s): %s",
                    signal_msg.sender_name or "Unknown",
                    signal_msg.sender_phone,
                    signal_msg.message[:50],
                )

                # Parse the command
                parsed_command = parse_message(signal_msg.message)
                cmd = parsed_command["command"]

                if cmd == "ignore":
                    continue

                # Get or create user for this sender
                db = get_db_session()
                try:
                    user = get_or_create_signal_user(
                        db, signal_msg.sender_phone, signal_msg.sender_name
                    )
                    user_id: int = user.id  # type: ignore[assignment]
                finally:
                    db.close()

                logger.debug("Processing command '%s' for user_id=%s", cmd, user_id)

                if cmd == "track":
                    response = handle_track_command(
                        parsed_command["url"], parsed_command["target_price"], user_id
                    )
                    send_signal_message_to_group(group_id, response)

                elif cmd == "status":
                    logger.info("Sending status message")
                    send_signal_message_to_group(group_id, "Bot is running and tracking products!")

                elif cmd == "list":
                    logger.info("Sending list of tracked items")
                    send_signal_message_to_group(group_id, handle_list_tracked_items(user_id))

                elif cmd == "stop":
                    logger.info("Stopping tracking for item %s", parsed_command["number"])
                    stop_message = stop_tracking_item(parsed_command["number"] - 1, user_id)
                    send_signal_message_to_group(group_id, stop_message)

                elif cmd == "help":
                    logger.info("Sending help message")
                    send_signal_message_to_group(group_id, handle_help_message())

                elif cmd == "invalid":
                    logger.warning("Invalid command: %s", parsed_command["message"])
                    send_signal_message_to_group(group_id, parsed_command["message"])

        except Exception as e:
            logger.error("Error while listening to Signal group: %s", e, exc_info=True)

        logger.debug("Sleeping for 5 seconds before checking for new messages...")
        time.sleep(5)
