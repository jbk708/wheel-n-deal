"""Shared fixtures for integration tests."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models import get_db_session
from routers.tracker import router

# Test app setup
app = FastAPI()
app.include_router(router, prefix="/api/v1/tracker", tags=["tracker"])


# Database fixtures


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def client(mock_db_session):
    """Create a test client with mocked database."""
    app.dependency_overrides[get_db_session] = lambda: mock_db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


# Mock product fixtures


@pytest.fixture
def mock_product():
    """Create a mock product with standard attributes."""
    product = MagicMock()
    product.id = 1
    product.url = "https://example.com/product"
    product.title = "Test Product"
    product.description = "A test product"
    product.image_url = "https://example.com/image.jpg"
    product.target_price = 90.0
    product.created_at = datetime(2023, 1, 1)
    product.updated_at = datetime(2023, 1, 1)
    return product


# Common mock patches


@pytest.fixture
def mock_scraper():
    """Mock the scraper function for tracker router."""
    with patch("routers.tracker.scrape_product_info") as mock:
        mock.return_value = {
            "title": "Test Product",
            "price": "$100.00",
            "price_float": 100.0,
            "url": "https://example.com/product",
            "description": "A test product",
            "image_url": "https://example.com/image.jpg",
        }
        yield mock


@pytest.fixture
def mock_signal():
    """Mock the Signal notification function for tracker router."""
    with patch("routers.tracker.send_signal_message_to_group") as mock:
        yield mock


@pytest.fixture
def mock_celery():
    """Mock the Celery task."""
    with patch("tasks.price_check.check_price.apply_async") as mock:
        yield mock


# Celery task fixtures


@pytest.fixture
def mock_celery_scraper():
    """Mock the scraper function for Celery tasks."""
    with patch("tasks.price_check.scrape_product_info") as mock:
        mock.return_value = {
            "title": "Test Product",
            "price": "$80.00",
            "price_float": 80.0,
            "url": "https://example.com/product",
        }
        yield mock


@pytest.fixture
def mock_celery_db_session():
    """Mock the database session for Celery tasks."""
    with patch("tasks.price_check.get_db_session") as mock:
        mock_session = MagicMock()
        mock.return_value = mock_session
        yield mock_session


@pytest.fixture
def mock_celery_signal():
    """Mock the Signal notification function for Celery tasks."""
    with patch("tasks.price_check.send_signal_message") as mock:
        yield mock


@pytest.fixture
def mock_apply_async():
    """Mock the apply_async method of the Celery task."""
    with patch("tasks.price_check.check_price.apply_async") as mock:
        yield mock
