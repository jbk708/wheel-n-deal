from fastapi import APIRouter, HTTPException
from models import Product as DBProduct, PriceHistory, get_db_session
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
        # Scrape product information
        product_info = scrape_product_info(product.url)

        # Get the current price of the product
        current_price = float(product_info["price"].replace("$", "").replace(",", ""))

        # If no target price is provided, default to 10% off the current price
        target_price = product.target_price or current_price * 0.9

        # Store the product in the database
        db = get_db_session()
        try:
            # Check if the product already exists
            existing_product = db.query(DBProduct).filter(DBProduct.url == product.url).first()
            
            if existing_product:
                # Update the existing product
                existing_product.target_price = target_price
                db.add(existing_product)
                
                # Add a new price history entry
                price_history = PriceHistory(
                    product_id=existing_product.id,
                    price=current_price
                )
                db.add(price_history)
                db.commit()
                
                product_id = existing_product.id
            else:
                # Create a new product
                db_product = DBProduct(
                    title=product_info["title"],
                    url=product.url,
                    target_price=target_price
                )
                db.add(db_product)
                db.flush()  # Flush to get the ID
                
                # Add a price history entry
                price_history = PriceHistory(
                    product_id=db_product.id,
                    price=current_price
                )
                db.add(price_history)
                db.commit()
                
                product_id = db_product.id
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

        # Schedule the price check task
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


@router.get("/products")
async def get_products():
    """
    Get all tracked products.
    """
    try:
        db = get_db_session()
        products = db.query(DBProduct).all()
        
        result = []
        for product in products:
            # Get the latest price
            latest_price = db.query(PriceHistory).filter(
                PriceHistory.product_id == product.id
            ).order_by(PriceHistory.timestamp.desc()).first()
            
            result.append({
                "id": product.id,
                "title": product.title,
                "url": product.url,
                "target_price": product.target_price,
                "current_price": latest_price.price if latest_price else None,
                "created_at": product.created_at,
                "updated_at": product.updated_at
            })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving products: {str(e)}")
    finally:
        db.close()
