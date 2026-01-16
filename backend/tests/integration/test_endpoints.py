"""Integration tests for API endpoints."""

from datetime import datetime
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient


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
    mock_db_session.query.return_value.filter.return_value.first.return_value = None

    def set_product_attributes(obj):
        obj.id = 1
        obj.created_at = datetime(2023, 1, 1)
        obj.updated_at = datetime(2023, 1, 1)

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
    mock_db_session.query.return_value.filter.return_value.first.return_value = None

    def set_product_attributes(obj):
        obj.id = 1
        obj.created_at = datetime(2023, 1, 1)
        obj.updated_at = datetime(2023, 1, 1)

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
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_existing

    response = client.post(
        "/api/v1/tracker/track",
        json={"url": "https://example.com/product", "target_price": 90.0},
    )

    assert response.status_code == 400
    assert "already being tracked" in response.json()["detail"]


def test_track_product_endpoint_scraper_error(
    client, mock_db_session, mock_scraper, mock_signal, mock_celery
):
    """Test scraper failure returns 500 error."""
    mock_db_session.query.return_value.filter.return_value.first.return_value = None
    mock_scraper.side_effect = Exception("Scraping failed")

    response = client.post(
        "/api/v1/tracker/track",
        json={"url": "https://example.com/product", "target_price": 90.0},
    )

    assert response.status_code == 500
    assert "Error tracking product" in response.json()["detail"]


def test_get_products_endpoint(client, mock_db_session):
    """Test retrieving all tracked products."""
    mock_product1 = MagicMock()
    mock_product1.id = 1
    mock_product1.url = "https://example.com/product1"
    mock_product1.title = "Test Product 1"
    mock_product1.description = "Description 1"
    mock_product1.image_url = "https://example.com/image1.jpg"
    mock_product1.target_price = 90.0
    mock_product1.created_at = "2023-01-01T00:00:00"
    mock_product1.updated_at = "2023-01-01T00:00:00"

    mock_product2 = MagicMock()
    mock_product2.id = 2
    mock_product2.url = "https://example.com/product2"
    mock_product2.title = "Test Product 2"
    mock_product2.description = "Description 2"
    mock_product2.image_url = "https://example.com/image2.jpg"
    mock_product2.target_price = 80.0
    mock_product2.created_at = "2023-01-02T00:00:00"
    mock_product2.updated_at = "2023-01-02T00:00:00"

    mock_price1 = MagicMock()
    mock_price1.price = 100.0
    mock_price2 = MagicMock()
    mock_price2.price = 95.0

    mock_db_session.query.return_value.all.return_value = [mock_product1, mock_product2]
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
