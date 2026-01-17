import re
import subprocess
import time
from zoneinfo import ZoneInfo

from config import settings
from models import PriceHistory, get_db_session
from models import Product as DBProduct
from services.notification import send_signal_message_to_group, send_signal_message_to_user
from services.scraper import scrape_product_info
from services.signal_parser import parse_signal_json
from services.user_service import get_or_create_signal_user
from utils.logging import get_logger
from utils.monitoring import TRACKED_PRODUCTS

logger = get_logger("listener")


def parse_message(message: str) -> dict:
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

    stripped = message.strip()
    if not stripped.startswith("!"):
        return {"command": "ignore"}

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

    if command_lower == "status":
        return {"command": "status"}

    if command_lower == "help":
        return {"command": "help"}

    if command_lower == "list":
        return {"command": "list"}

    if command_lower.startswith("stop"):
        number_match = re.search(r"^stop\s+(\d+)$", command_lower)
        if number_match:
            number = int(number_match.group(1))
            logger.info("Parsed !stop command: number=%s", number)
            return {"command": "stop", "number": number}
        logger.warning("Invalid !stop command format")
        return {
            "command": "invalid",
            "message": "Invalid !stop command. Use '!stop <number>'.",
        }

    logger.warning("Unknown command: %s", command_text)
    return {
        "command": "invalid",
        "message": "Unknown command. Type '!help' for available commands.",
    }


def handle_help_message() -> str:
    """Generate a help message with available commands."""
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

            if latest_price:
                current_price = f"${latest_price.price}"
                pacific_time = latest_price.timestamp.astimezone(ZoneInfo("America/Los_Angeles"))
                last_updated = pacific_time.strftime("%b %d, %I:%M %p")
            else:
                current_price = "Unknown"
                last_updated = "Never"

            message += f"{i}. {product.title}\n"
            message += f"   Current price: {current_price}\n"
            message += f"   Target price: ${product.target_price}\n"
            message += f"   Last updated: {last_updated}\n"
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
        db.flush()  # Get the product ID before committing

        # Store initial price in history
        if current_price:
            initial_price = PriceHistory(product_id=db_product.id, price=current_price)
            db.add(initial_price)

        db.commit()
        TRACKED_PRODUCTS.inc()

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


def _get_command_response(cmd: str, parsed_command: dict, user_id: int) -> str:
    """Get the response message for a parsed command."""
    if cmd == "track":
        return handle_track_command(parsed_command["url"], parsed_command["target_price"], user_id)

    if cmd == "status":
        return "Bot is running and tracking products!"

    if cmd == "list":
        return handle_list_tracked_items(user_id)

    if cmd == "stop":
        return stop_tracking_item(parsed_command["number"] - 1, user_id)

    if cmd == "help":
        return handle_help_message()

    if cmd == "invalid":
        logger.warning("Invalid command: %s", parsed_command["message"])
        return parsed_command["message"]

    return "Unknown command. Type '!help' for available commands."


def send_response(group_id: str | None, sender_phone: str, message: str) -> None:
    """Send a response to the appropriate destination (group or direct message)."""
    if group_id:
        send_signal_message_to_group(group_id, message)
    else:
        send_signal_message_to_user(sender_phone, message)


def listen_for_messages() -> None:
    """Listen for Signal messages (both group and direct) and respond to commands."""
    group_id = settings.SIGNAL_GROUP_ID
    command = ["signal-cli", "-u", settings.SIGNAL_PHONE_NUMBER, "--output=json", "receive"]

    logger.info("Starting Signal listener (group: %s, direct messages: enabled)...", group_id[:8])

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
                # Process messages from our group OR direct messages (no group_id)
                is_group_message = signal_msg.group_id == group_id
                is_direct_message = signal_msg.group_id is None

                if not is_group_message and not is_direct_message:
                    # Message from a different group - ignore
                    continue

                msg_type = "group" if is_group_message else "direct"
                logger.info(
                    "[%s] Message from %s (%s): %s",
                    msg_type,
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

                response_group_id = signal_msg.group_id if is_group_message else None
                response = _get_command_response(cmd, parsed_command, user_id)
                send_response(response_group_id, signal_msg.sender_phone, response)

        except Exception as e:
            logger.error("Error while listening for Signal messages: %s", e, exc_info=True)

        logger.debug("Sleeping for 5 seconds before checking for new messages...")
        time.sleep(5)


# Backward compatibility alias
def listen_to_group() -> None:
    """Listen for Signal messages. Alias for listen_for_messages()."""
    listen_for_messages()
