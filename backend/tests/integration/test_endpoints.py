"""Integration tests for API endpoints."""

from datetime import datetime
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient


def create_mock_product(
    product_id: int,
    user_id: int,
    title: str = "Test Product",
    target_price: float = 90.0,
) -> MagicMock:
    """Create a mock product with standard attributes."""
    product = MagicMock()
    product.id = product_id
    product.user_id = user_id
    product.url = f"https://example.com/product{product_id}"
    product.title = title
    product.description = f"Description {product_id}"
    product.image_url = f"https://example.com/image{product_id}.jpg"
    product.target_price = target_price
    product.created_at = f"2023-01-0{product_id}T00:00:00"
    product.updated_at = f"2023-01-0{product_id}T00:00:00"
    return product


def set_product_attributes(obj) -> None:
    """Set required attributes on a product object after db.refresh()."""
    obj.id = 1
    obj.created_at = datetime(2023, 1, 1)
    obj.updated_at = datetime(2023, 1, 1)


def test_root_endpoint():
    """Test a simple root endpoint returns welcome message."""
    test_app = FastAPI()

    @test_app.get("/")
    async def root():
        return {"message": "Welcome to Wheel-n-Deal API"}

    test_client = TestClient(test_app)
    response = test_client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to Wheel-n-Deal API"}


def test_track_product_endpoint(client, mock_db_session, mock_scraper, mock_signal, mock_celery):
    """Test tracking a new product stores it and returns product details."""
    mock_db_session.query.return_value.filter.return_value.filter.return_value.first.return_value = None
    mock_db_session.refresh.side_effect = set_product_attributes

    response = client.post(
        "/api/v1/tracker/track",
        json={"url": "https://example.com/product", "target_price": 90.0},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Test Product"
    assert data["target_price"] == 90.0
    assert data["current_price"] == 100.0


def test_track_product_endpoint_no_target_price(
    client, mock_db_session, mock_scraper, mock_signal, mock_celery
):
    """Test tracking without target price auto-calculates 10% discount."""
    mock_db_session.query.return_value.filter.return_value.filter.return_value.first.return_value = None
    mock_db_session.refresh.side_effect = set_product_attributes

    response = client.post(
        "/api/v1/tracker/track",
        json={"url": "https://example.com/product"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Test Product"
    assert data["target_price"] == 90.0  # 10% off $100


def test_track_product_endpoint_existing_product(
    client, mock_db_session, mock_scraper, mock_signal, mock_celery
):
    """Test tracking an already-tracked product returns 400 error."""
    mock_existing = MagicMock()
    mock_existing.url = "https://example.com/product"
    mock_existing.user_id = 1
    mock_db_session.query.return_value.filter.return_value.filter.return_value.first.return_value = mock_existing

    response = client.post(
        "/api/v1/tracker/track",
        json={"url": "https://example.com/product", "target_price": 90.0},
    )

    assert response.status_code == 400
    assert "already tracking this product" in response.json()["detail"]


def test_track_product_endpoint_scraper_error(
    client, mock_db_session, mock_scraper, mock_signal, mock_celery
):
    """Test scraper failure returns 500 error."""
    mock_db_session.query.return_value.filter.return_value.filter.return_value.first.return_value = None
    mock_scraper.side_effect = Exception("Scraping failed")

    response = client.post(
        "/api/v1/tracker/track",
        json={"url": "https://example.com/product", "target_price": 90.0},
    )

    assert response.status_code == 500
    assert "Error tracking product" in response.json()["detail"]


def test_get_products_endpoint(client, mock_db_session):
    """Test retrieving all tracked products for authenticated user."""
    mock_product1 = create_mock_product(1, user_id=1, title="Test Product 1")
    mock_product2 = create_mock_product(2, user_id=1, title="Test Product 2", target_price=80.0)

    mock_price1 = MagicMock()
    mock_price1.price = 100.0
    mock_price2 = MagicMock()
    mock_price2.price = 95.0

    mock_db_session.query.return_value.filter.return_value.all.return_value = [
        mock_product1,
        mock_product2,
    ]
    mock_db_session.query.return_value.filter.return_value.order_by.return_value.first.side_effect = [
        mock_price1,
        mock_price2,
    ]

    response = client.get("/api/v1/tracker/products")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["title"] == "Test Product 1"
    assert data[1]["title"] == "Test Product 2"


def test_get_products_endpoint_error(client, mock_db_session):
    """Test database error during product retrieval returns 500."""
    mock_db_session.query.side_effect = Exception("Database error")

    response = client.get("/api/v1/tracker/products")

    assert response.status_code == 500
    assert "Error retrieving tracked products" in response.json()["detail"]
