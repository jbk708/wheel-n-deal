from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from models import Product as DBProduct, PriceHistory, get_db_session
from services.scraper import scrape_product_info
from services.notification import send_signal_message_to_group
from config import settings
from utils.logging import get_logger
from utils.monitoring import TRACKED_PRODUCTS, PRICE_ALERTS_SENT

# Setup logger
logger = get_logger("tracker")

router = APIRouter()


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
def track_product(product: Product, db: Session = Depends(get_db_session)):
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
        if not product.target_price:
            product.target_price = round(product_info["price"] * 0.9, 2)  # 10% discount
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
            price=product_info["price"],
        )
        
        db.add(price_history)
        db.commit()
        
        # Update tracked products metric
        TRACKED_PRODUCTS.inc()
        
        logger.info(f"Product tracked successfully: {db_product.title} (ID: {db_product.id})")
        
        # Return response
        return {
            "id": db_product.id,
            "url": db_product.url,
            "title": db_product.title,
            "description": db_product.description,
            "image_url": db_product.image_url,
            "target_price": db_product.target_price,
            "current_price": product_info["price"],
            "created_at": db_product.created_at,
            "updated_at": db_product.updated_at,
        }
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error tracking product: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error tracking product: {str(e)}")


@router.get("/products", response_model=List[ProductResponse])
def get_tracked_products(db: Session = Depends(get_db_session)):
    """
    Get all tracked products with their current prices.
    """
    logger.info("Getting all tracked products")
    
    try:
        products = db.query(DBProduct).all()
        
        response = []
        for product in products:
            # Get latest price
            latest_price = db.query(PriceHistory).filter(
                PriceHistory.product_id == product.id
            ).order_by(PriceHistory.timestamp.desc()).first()
            
            current_price = latest_price.price if latest_price else None
            
            response.append({
                "id": product.id,
                "url": product.url,
                "title": product.title,
                "description": product.description,
                "image_url": product.image_url,
                "target_price": product.target_price,
                "current_price": current_price,
                "created_at": product.created_at,
                "updated_at": product.updated_at,
            })
        
        logger.debug(f"Retrieved {len(response)} tracked products")
        return response
    
    except Exception as e:
        logger.error(f"Error retrieving tracked products: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving tracked products: {str(e)}")


@router.get("/products/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db_session)):
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
        latest_price = db.query(PriceHistory).filter(
            PriceHistory.product_id == product.id
        ).order_by(PriceHistory.timestamp.desc()).first()
        
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
        logger.error(f"Error retrieving product: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving product: {str(e)}")


@router.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db_session)):
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
        logger.error(f"Error deleting product: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error deleting product: {str(e)}")


@router.post("/check-prices")
def check_prices(db: Session = Depends(get_db_session)):
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
                product_info = scrape_product_info(product.url)
                
                if not product_info:
                    logger.warning(f"Failed to scrape product info: {product.url}")
                    continue
                
                current_price = product_info["price"]
                
                # Add to price history
                price_history = PriceHistory(
                    product_id=product.id,
                    price=current_price,
                )
                
                db.add(price_history)
                db.commit()
                
                # Check if target price is reached
                if current_price <= product.target_price:
                    logger.info(f"Target price reached for product: {product.title} (ID: {product.id})")
                    
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
                logger.error(f"Error checking price for product {product.id}: {str(e)}", exc_info=True)
                continue
        
        logger.info(f"Price check completed. Sent {notifications_sent} notifications.")
        return {"message": f"Checked prices for {len(products)} products. Sent {notifications_sent} notifications."}
    
    except Exception as e:
        logger.error(f"Error checking prices: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error checking prices: {str(e)}")
