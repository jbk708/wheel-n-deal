from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.scraper import scrape_product_info
from services.notification import send_signal_message_to_group
from config import settings

router = APIRouter()


class Product(BaseModel):
    url: str


@router.post("/track")
async def track_product(product: Product):
    """
    Track a new product by its URL and send a notification to the Signal group.
    """
    try:
        # Scrape the product details using the scraper service
        product_info = scrape_product_info(product.url)

        # Send a Signal message to the group to notify about the tracking
        message = f"Product is now being tracked: {product_info['title']} - {product_info['price']}"
        send_signal_message_to_group(settings.SIGNAL_GROUP_ID, message)

        return {"message": "Product is now being tracked", "product_info": product_info}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error tracking product: {e}")
