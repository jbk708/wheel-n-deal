from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import settings
from models import PriceHistory, get_db_session
from models import Product as DBProduct
from models import User as DBUser
from services.notification import send_signal_message_to_group
from services.scraper import scrape_product_info
from utils.logging import get_logger
from utils.monitoring import PRICE_ALERTS_SENT, TRACKED_PRODUCTS
from utils.security import get_current_active_user, limiter

logger = get_logger("tracker")

router = APIRouter()

_db_dependency = Depends(get_db_session)
_current_user_dependency = Depends(get_current_active_user)


class Product(BaseModel):
    url: str
    target_price: float | None = None


class ProductResponse(BaseModel):
    id: int
    url: str
    title: str
    description: str | None = None
    image_url: str | None = None
    target_price: float | None = None
    current_price: float | None = None
    created_at: datetime
    updated_at: datetime


def get_latest_price(db: Session, product_id: int) -> float | None:
    """Get the latest price for a product from price history."""
    latest_price = (
        db.query(PriceHistory)
        .filter(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.timestamp.desc())
        .first()
    )
    return latest_price.price if latest_price else None


def build_product_response(product: DBProduct, current_price: float | None) -> dict:
    """Build a product response dictionary from a database product."""
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


def get_user_product(db: Session, user_id: int, product_id: int) -> DBProduct | None:
    """Get a product by ID that belongs to a specific user."""
    return (
        db.query(DBProduct).filter(DBProduct.id == product_id, DBProduct.user_id == user_id).first()
    )


@router.post("/track", response_model=ProductResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def track_product(
    request: Request,
    product: Product,
    current_user: DBUser = _current_user_dependency,
    db: Session = _db_dependency,
):
    """Track a product by URL with an optional target price for the authenticated user."""
    logger.info(f"User {current_user.id} tracking product: {product.url}")

    existing_product = (
        db.query(DBProduct)
        .filter(DBProduct.user_id == current_user.id)
        .filter(DBProduct.url == product.url)
        .first()
    )
    if existing_product:
        logger.warning(f"User {current_user.id} already tracking product: {product.url}")
        raise HTTPException(status_code=400, detail="You are already tracking this product")

    try:
        logger.debug(f"Scraping product info for: {product.url}")
        product_info = scrape_product_info(product.url)

        if not product_info:
            logger.error(f"Failed to scrape product info: {product.url}")
            raise HTTPException(status_code=400, detail="Failed to scrape product information")

        current_price = product_info.get("price_float")
        if not product.target_price and current_price:
            product.target_price = round(current_price * 0.9, 2)
            logger.info(f"Target price set to {product.target_price} (10% off current price)")

        db_product = DBProduct(
            user_id=current_user.id,
            url=product.url,
            title=product_info["title"],
            description=product_info.get("description", ""),
            image_url=product_info.get("image_url", ""),
            target_price=product.target_price,
        )

        db.add(db_product)
        db.commit()
        db.refresh(db_product)

        price_history = PriceHistory(
            product_id=db_product.id,
            price=current_price,
        )

        db.add(price_history)
        db.commit()

        TRACKED_PRODUCTS.inc()

        from tasks.price_check import check_price

        check_price.apply_async(args=[product.url, product.target_price])

        message = f"Product is now being tracked: {product_info['title']} at {product_info['price']}. Target price is ${product.target_price}."
        send_signal_message_to_group(settings.SIGNAL_GROUP_ID, message)

        logger.info(f"Product tracked successfully: {db_product.title} (ID: {db_product.id})")

        return build_product_response(db_product, current_price)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error tracking product: {e!s}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error tracking product: {e!s}") from e


@router.get("/products", response_model=list[ProductResponse])
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def get_tracked_products(
    request: Request,
    current_user: DBUser = _current_user_dependency,
    db: Session = _db_dependency,
):
    """Get all tracked products for the authenticated user."""
    logger.info(f"Getting tracked products for user {current_user.id}")

    try:
        products = db.query(DBProduct).filter(DBProduct.user_id == current_user.id).all()

        response = [
            build_product_response(product, get_latest_price(db, product.id))
            for product in products
        ]

        logger.debug(f"Retrieved {len(response)} tracked products for user {current_user.id}")
        return response

    except Exception as e:
        logger.error(f"Error retrieving tracked products: {e!s}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Error retrieving tracked products: {e!s}"
        ) from e


@router.get("/products/{product_id}", response_model=ProductResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def get_product(
    request: Request,
    product_id: int,
    current_user: DBUser = _current_user_dependency,
    db: Session = _db_dependency,
):
    """Get a specific tracked product by ID for the authenticated user."""
    user_id = cast("int", current_user.id)
    logger.info(f"User {user_id} getting product with ID: {product_id}")

    try:
        product = get_user_product(db, user_id, product_id)
        if not product:
            logger.warning(f"Product not found: ID {product_id} for user {user_id}")
            raise HTTPException(status_code=404, detail="Product not found")

        current_price = get_latest_price(db, cast("int", product.id))

        logger.debug(f"Retrieved product: {product.title} (ID: {product.id})")
        return build_product_response(product, current_price)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving product: {e!s}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving product: {e!s}") from e


@router.delete("/products/{product_id}")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def delete_product(
    request: Request,
    product_id: int,
    current_user: DBUser = _current_user_dependency,
    db: Session = _db_dependency,
):
    """Delete a tracked product by ID for the authenticated user."""
    user_id = cast("int", current_user.id)
    logger.info(f"User {user_id} deleting product with ID: {product_id}")

    try:
        product = get_user_product(db, user_id, product_id)
        if not product:
            logger.warning(f"Product not found for deletion: ID {product_id} for user {user_id}")
            raise HTTPException(status_code=404, detail="Product not found")

        db.delete(product)
        db.commit()

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
@limiter.limit("10/minute")
async def check_prices(
    request: Request,
    current_user: DBUser = _current_user_dependency,
    db: Session = _db_dependency,
):
    """Check prices for all tracked products of the authenticated user."""
    logger.info(f"Checking prices for user {current_user.id}'s products")

    try:
        products = db.query(DBProduct).filter(DBProduct.user_id == current_user.id).all()

        if not products:
            logger.info(f"No products to check prices for user {current_user.id}")
            return {"message": "No products to check prices for"}

        notifications_sent = 0

        for product in products:
            logger.debug(f"Checking price for product: {product.title} (ID: {product.id})")

            try:
                product_info = scrape_product_info(str(product.url))

                if not product_info:
                    logger.warning(f"Failed to scrape product info: {product.url}")
                    continue

                current_price = product_info.get("price_float")
                if current_price is None:
                    logger.warning(f"Could not parse price for {product.url}")
                    continue

                price_history = PriceHistory(
                    product_id=product.id,
                    price=current_price,
                )

                db.add(price_history)
                db.commit()

                if current_price <= product.target_price:
                    logger.info(
                        f"Target price reached for product: {product.title} (ID: {product.id})"
                    )

                    message = f"🎯 Target price reached for {product.title}!\n"
                    message += f"Current price: ${current_price}\n"
                    message += f"Target price: ${product.target_price}\n"
                    message += f"URL: {product.url}"

                    send_signal_message_to_group(settings.SIGNAL_GROUP_ID, message)
                    notifications_sent += 1

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
