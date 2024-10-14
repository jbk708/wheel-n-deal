from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from services.notification import send_signal_message
from services.scraper import scrape_product_info
from tasks.price_check import check_price

router = APIRouter()


class Product(BaseModel):
    url: str
    target_price: float = Field(
        None, description="The price threshold for notifications, defaults to 10% off"
    )


@router.post("/track")
async def track_product(product: Product):
    try:
        product_info = scrape_product_info(product.url)

        # Get the current price of the product
        current_price = float(product_info["price"].replace("$", ""))

        # If no target price is provided, default to 10% off the current price
        target_price = product.target_price or current_price * 0.9

        check_price.apply_async(args=[product.url, target_price])

        # Send Signal notification
        send_signal_message(
            f"Product is now being tracked: {product_info['title']} at {product_info['price']}. "
            f"Target price is {target_price}."
        )

        return {
            "message": "Product is now being tracked",
            "product_info": product_info,
            "target_price": target_price,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error tracking product: {str(e)}")
