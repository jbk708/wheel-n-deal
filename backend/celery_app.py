from celery import Celery

# Initialize the Celery app with Redis as the broker and backend
app = Celery(
    "price_tracker", broker="redis://broker:6379/0", backend="redis://broker:6379/0"
)


@app.task
def check_price(url: str, target_price: float):
    """
    Celery task to check the price of a product and notify the user if the price
    drops below the target price.

    Args:
        url (str): The URL of the product being tracked.
        target_price (float): The target price at which the user should be notified.
    """
    from services.notification import send_signal_message
    from services.scraper import scrape_product_info

    try:
        # Scrape the current price from the product page
        product_info = scrape_product_info(url)
        current_price = float(
            product_info["price"].replace("$", "")
        )  # Convert to float for comparison

        # Compare the current price to the target price
        if current_price <= target_price:
            # Send a notification if the current price is below or equal to the target price
            send_signal_message(
                f"Price drop alert! {product_info['title']} is now {product_info['price']}. "
                f"Target price was {target_price}."
            )
        else:
            # Optionally log or print that no price drop occurred
            print(
                f"{product_info['title']} is still priced at {product_info['price']}, target was {target_price}."
            )

    except Exception as e:
        # Log the exception or notify the user about the failure
        print(f"Error checking price for {url}: {str(e)}")
