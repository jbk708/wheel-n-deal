from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from models import PriceHistory, get_db_session
from models import Product as DBProduct
from services.notification import send_signal_message_to_group
from services.scraper import scrape_product_info
from utils.logging import get_logger
from utils.monitoring import PRICE_ALERTS_SENT, TRACKED_PRODUCTS
from utils.security import limiter

# Setup logger
logger = get_logger("tracker")

router = APIRouter()

# Create a module-level singleton for the database session dependency
db_dependency = Depends(get_db_session)


class Product(BaseModel):
    url: str
    target_price: Optional[float] = None


class ProductResponse(BaseModel):
    id: int
    url: str
    title: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    target_price: Optional[float] = None
    current_price: Optional[float] = None
    created_at: datetime
    updated_at: datetime


@router.post("/track", response_model=ProductResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def track_product(request: Request, product: Product, db: Session = db_dependency):
    """
    Track a product by URL with an optional target price.
    If target_price is not provided, it will be set to 90% of the current price.
    """
    logger.info(f"Tracking product: {product.url}")

    # Check if product is already being tracked
    existing_product = db.query(DBProduct).filter(DBProduct.url == product.url).first()
    if existing_product:
        logger.warning(f"Product already being tracked: {product.url}")
        raise HTTPException(status_code=400, detail="Product is already being tracked")

    try:
        # Scrape product info
        logger.debug(f"Scraping product info for: {product.url}")
        product_info = scrape_product_info(product.url)

        if not product_info:
            logger.error(f"Failed to scrape product info: {product.url}")
            raise HTTPException(status_code=400, detail="Failed to scrape product information")

        # Set target price if not provided
        current_price = product_info.get("price_float")
        if not product.target_price and current_price:
            product.target_price = round(current_price * 0.9, 2)  # 10% discount
            logger.info(f"Target price set to {product.target_price} (10% off current price)")

        # Create new product
        db_product = DBProduct(
            url=product.url,
            title=product_info["title"],
            description=product_info.get("description", ""),
            image_url=product_info.get("image_url", ""),
            target_price=product.target_price,
        )

        db.add(db_product)
        db.commit()
        db.refresh(db_product)

        # Add price history entry
        price_history = PriceHistory(
            product_id=db_product.id,
            price=current_price,
        )

        db.add(price_history)
        db.commit()

        # Update tracked products metric
        TRACKED_PRODUCTS.inc()

        # Schedule price check task
        from tasks.price_check import check_price

        check_price.apply_async(args=[product.url, product.target_price])

        # Send notification
        message = f"Product is now being tracked: {product_info['title']} at {product_info['price']}. Target price is ${product.target_price}."
        send_signal_message_to_group(settings.SIGNAL_GROUP_ID, message)

        logger.info(f"Product tracked successfully: {db_product.title} (ID: {db_product.id})")

        # Return response
        return {
            "id": db_product.id,
            "url": db_product.url,
            "title": db_product.title,
            "description": db_product.description,
            "image_url": db_product.image_url,
            "target_price": db_product.target_price,
            "current_price": current_price,
            "created_at": db_product.created_at,
            "updated_at": db_product.updated_at,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error tracking product: {e!s}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error tracking product: {e!s}") from e


@router.get("/products", response_model=List[ProductResponse])
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def get_tracked_products(request: Request, db: Session = db_dependency):
    """
    Get all tracked products with their current prices.
    """
    logger.info("Getting all tracked products")

    try:
        products = db.query(DBProduct).all()

        response = []
        for product in products:
            # Get latest price
            latest_price = (
                db.query(PriceHistory)
                .filter(PriceHistory.product_id == product.id)
                .order_by(PriceHistory.timestamp.desc())
                .first()
            )

            current_price = latest_price.price if latest_price else None

            response.append(
                {
                    "id": product.id,
                    "url": product.url,
                    "title": product.title,
                    "description": product.description,
                    "image_url": product.image_url,
                    "target_price": product.target_price,
                    "current_price": current_price,
                    "created_at": product.created_at,
                    "updated_at": product.updated_at,
                }
            )

        logger.debug(f"Retrieved {len(response)} tracked products")
        return response

    except Exception as e:
        logger.error(f"Error retrieving tracked products: {e!s}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Error retrieving tracked products: {e!s}"
        ) from e


@router.get("/products/{product_id}", response_model=ProductResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def get_product(request: Request, product_id: int, db: Session = db_dependency):
    """
    Get a specific tracked product by ID.
    """
    logger.info(f"Getting product with ID: {product_id}")

    try:
        product = db.query(DBProduct).filter(DBProduct.id == product_id).first()
        if not product:
            logger.warning(f"Product not found: ID {product_id}")
            raise HTTPException(status_code=404, detail="Product not found")

        # Get latest price
        latest_price = (
            db.query(PriceHistory)
            .filter(PriceHistory.product_id == product.id)
            .order_by(PriceHistory.timestamp.desc())
            .first()
        )

        current_price = latest_price.price if latest_price else None

        logger.debug(f"Retrieved product: {product.title} (ID: {product.id})")
        return {
            "id": product.id,
            "url": product.url,
            "title": product.title,
            "description": product.description,
            "image_url": product.image_url,
            "target_price": product.target_price,
            "current_price": current_price,
            "created_at": product.created_at,
            "updated_at": product.updated_at,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving product: {e!s}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving product: {e!s}") from e


@router.delete("/products/{product_id}")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def delete_product(request: Request, product_id: int, db: Session = db_dependency):
    """
    Delete a tracked product by ID.
    """
    logger.info(f"Deleting product with ID: {product_id}")

    try:
        product = db.query(DBProduct).filter(DBProduct.id == product_id).first()
        if not product:
            logger.warning(f"Product not found for deletion: ID {product_id}")
            raise HTTPException(status_code=404, detail="Product not found")

        db.delete(product)
        db.commit()

        # Update tracked products metric
        TRACKED_PRODUCTS.dec()

        logger.info(f"Product deleted: {product.title} (ID: {product.id})")
        return {"message": f"Product {product_id} deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting product: {e!s}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error deleting product: {e!s}") from e


@router.post("/check-prices")
@limiter.limit("10/minute")  # Stricter limit for expensive operation
async def check_prices(request: Request, db: Session = db_dependency):
    """
    Check prices for all tracked products and send notifications if target price is reached.
    """
    logger.info("Checking prices for all tracked products")

    try:
        products = db.query(DBProduct).all()

        if not products:
            logger.info("No products to check prices for")
            return {"message": "No products to check prices for"}

        notifications_sent = 0

        for product in products:
            logger.debug(f"Checking price for product: {product.title} (ID: {product.id})")

            try:
                # Scrape current price
                product_info = scrape_product_info(str(product.url))

                if not product_info:
                    logger.warning(f"Failed to scrape product info: {product.url}")
                    continue

                current_price = product_info.get("price_float")
                if current_price is None:
                    logger.warning(f"Could not parse price for {product.url}")
                    continue

                # Add to price history
                price_history = PriceHistory(
                    product_id=product.id,
                    price=current_price,
                )

                db.add(price_history)
                db.commit()

                # Check if target price is reached
                if current_price <= product.target_price:
                    logger.info(
                        f"Target price reached for product: {product.title} (ID: {product.id})"
                    )

                    # Send notification
                    message = f"🎯 Target price reached for {product.title}!\n"
                    message += f"Current price: ${current_price}\n"
                    message += f"Target price: ${product.target_price}\n"
                    message += f"URL: {product.url}"

                    send_signal_message_to_group(settings.SIGNAL_GROUP_ID, message)
                    notifications_sent += 1

                    # Update price alerts metric
                    PRICE_ALERTS_SENT.inc()

            except Exception as e:
                logger.error(f"Error checking price for product {product.id}: {e!s}", exc_info=True)
                continue

        logger.info(f"Price check completed. Sent {notifications_sent} notifications.")
        return {
            "message": f"Checked prices for {len(products)} products. Sent {notifications_sent} notifications."
        }

    except Exception as e:
        logger.error(f"Error checking prices: {e!s}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error checking prices: {e!s}") from e
