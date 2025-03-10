import random

from celery import shared_task
from models import PriceHistory, Product, get_db_session
from services.notification import send_signal_message
from services.scraper import scrape_product_info


@shared_task
def check_price(url: str, target_price: float):
    """
    This task will check the price of a product from the given URL.
    If the price drops below the target price, a Signal notification is sent.

    Args:
    - url: str - The product URL to check.
    - target_price: float - The price threshold for sending a notification.
    """
    try:
        # Scrape product information (price and title)
        product_info = scrape_product_info(url)
        current_price = float(
            product_info["price"].replace("$", "").replace(",", "")
        )  # Handle comma and currency format

        # Store the price in the database
        db = get_db_session()
        try:
            # Get the product from the database
            product = db.query(Product).filter(Product.url == url).first()

            if product:
                # Add a new price history entry
                price_history = PriceHistory(product_id=product.id, price=current_price)
                db.add(price_history)
                db.commit()

                # Check if the current price is below or equal to the target price
                if current_price <= target_price:
                    message = (
                        f"Price drop alert! {product_info['title']} is now {product_info['price']}.\n"
                        f"Target price was {target_price}.\n"
                        f"URL: {url}"
                    )
                    send_signal_message(message)
                else:
                    print(
                        f"Product: {product_info['title']} is still priced at {product_info['price']}, "
                        f"target price was {target_price}."
                    )
            else:
                print(f"Product with URL {url} not found in the database.")
        except Exception as e:
            db.rollback()
            print(f"Database error: {str(e)}")
        finally:
            db.close()
    except Exception as e:
        # Log the exception (or notify the user about the failure)
        print(f"Error occurred while checking price for {url}: {str(e)}")

    # Add randomness to the next task schedule: + or - 10 minutes from the hour
    random_offset = random.randint(-600, 600)
    next_countdown = 3600 + random_offset

    # Reschedule the task to run again after the random countdown
    check_price.apply_async(args=[url, target_price], countdown=next_countdown)
