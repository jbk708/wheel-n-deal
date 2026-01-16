import random

from celery import shared_task

from models import PriceHistory, Product, get_db_session
from services.notification import send_signal_message
from services.scraper import scrape_product_info
from utils.logging import get_logger

logger = get_logger("price_check")


@shared_task
def check_price(url: str, target_price: float) -> None:
    """
    Check the price of a product and send a notification if it drops below target.

    Args:
        url: The product URL to check.
        target_price: The price threshold for sending a notification.
    """
    try:
        product_info = scrape_product_info(url)
        current_price = float(product_info["price"].replace("$", "").replace(",", ""))

        db = get_db_session()
        try:
            product = db.query(Product).filter(Product.url == url).first()

            if product:
                price_history = PriceHistory(product_id=product.id, price=current_price)
                db.add(price_history)
                db.commit()

                if current_price <= target_price:
                    message = (
                        f"Price drop alert! {product_info['title']} is now {product_info['price']}.\n"
                        f"Target price was {target_price}.\n"
                        f"URL: {url}"
                    )
                    send_signal_message(message)
                else:
                    logger.info(
                        f"Product: {product_info['title']} is still priced at {product_info['price']}, "
                        f"target price was {target_price}."
                    )
            else:
                logger.warning(f"Product with URL {url} not found in the database.")
        except Exception as e:
            db.rollback()
            logger.error(f"Database error: {e!s}")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error occurred while checking price for {url}: {e!s}")

    # Reschedule with jitter: 1 hour +/- 10 minutes
    next_countdown = 3600 + random.randint(-600, 600)
    check_price.apply_async(args=[url, target_price], countdown=next_countdown)
