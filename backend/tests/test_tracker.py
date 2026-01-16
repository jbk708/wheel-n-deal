from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from models import User as DBUser
from routers.tracker import (
    Product,
    delete_product,
    get_product,
    get_tracked_products,
    track_product,
)

MOCK_PRODUCT_INFO = {
    "title": "Test Product",
    "price": "$100.00",
    "price_float": 100.0,
    "url": "https://example.com/product",
    "description": "A test product",
    "image_url": "https://example.com/image.jpg",
}


def create_mock_user(user_id: int, email: str) -> MagicMock:
    """Create a mock user with standard attributes."""
    user = MagicMock(spec=DBUser)
    user.id = user_id
    user.email = email
    user.signal_phone = None
    user.signal_username = None
    return user


def create_mock_product(
    product_id: int,
    user_id: int,
    title: str = "Test Product",
    url: str = "https://example.com/product",
) -> MagicMock:
    """Create a mock product with standard attributes."""
    product = MagicMock()
    product.id = product_id
    product.user_id = user_id
    product.title = title
    product.url = url
    product.description = "Description"
    product.image_url = "https://example.com/image.jpg"
    product.target_price = 90.0
    product.created_at = datetime.now(UTC)
    product.updated_at = datetime.now(UTC)
    return product


@pytest.fixture
def mock_request():
    """Mock the Starlette request object for rate limiting."""
    mock_req = MagicMock(spec=Request)
    mock_req.client.host = "127.0.0.1"
    mock_req.app = MagicMock()
    mock_req.app.state.limiter = MagicMock()
    mock_req.state = MagicMock()
    return mock_req


@pytest.fixture
def mock_user():
    """Mock an authenticated user."""
    return create_mock_user(1, "test@example.com")


@pytest.fixture
def mock_other_user():
    """Mock a different authenticated user."""
    return create_mock_user(2, "other@example.com")


@pytest.fixture
def valid_product():
    return Product(url="https://example.com/product", target_price=90.0)


@pytest.fixture
def product_without_target_price():
    return Product(url="https://example.com/product")


@pytest.fixture
def invalid_product():
    return Product(url="invalid-url")


@pytest.mark.asyncio
@patch("routers.tracker.scrape_product_info", return_value=MOCK_PRODUCT_INFO)
@patch("routers.tracker.send_signal_message_to_group")
@patch("tasks.price_check.check_price.apply_async")
@patch("routers.tracker.get_db_session")
async def test_track_product_success(
    mock_get_db_session,
    mock_apply_async,
    mock_send_signal,
    mock_scrape,
    valid_product,
    mock_request,
    mock_user,
):
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
        None
    )

    response = await track_product(mock_request, valid_product, mock_user, mock_session)

    mock_scrape.assert_called_once_with(valid_product.url)

    mock_session.add.assert_called()
    mock_session.commit.assert_called()

    assert mock_send_signal.call_count == 1
    args, _ = mock_send_signal.call_args
    assert "Product is now being tracked" in args[1]
    assert MOCK_PRODUCT_INFO["title"] in args[1]
    assert str(valid_product.target_price) in args[1]

    mock_apply_async.assert_called_once_with(args=[valid_product.url, valid_product.target_price])

    assert response["url"] == valid_product.url
    assert response["title"] == MOCK_PRODUCT_INFO["title"]
    assert response["target_price"] == valid_product.target_price
    assert response["current_price"] == MOCK_PRODUCT_INFO["price_float"]


@pytest.mark.asyncio
@patch("routers.tracker.scrape_product_info", return_value=MOCK_PRODUCT_INFO)
@patch("routers.tracker.send_signal_message_to_group")
@patch("tasks.price_check.check_price.apply_async")
@patch("routers.tracker.get_db_session")
async def test_track_product_sets_user_id(
    mock_get_db_session,
    mock_apply_async,
    mock_send_signal,
    mock_scrape,
    valid_product,
    mock_request,
    mock_user,
):
    """Verify that tracked products are associated with the authenticated user."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
        None
    )

    await track_product(mock_request, valid_product, mock_user, mock_session)

    add_calls = mock_session.add.call_args_list
    db_product = add_calls[0][0][0]
    assert db_product.user_id == mock_user.id


@pytest.mark.asyncio
@patch("routers.tracker.scrape_product_info", return_value=MOCK_PRODUCT_INFO)
@patch("routers.tracker.send_signal_message_to_group")
@patch("tasks.price_check.check_price.apply_async")
@patch("routers.tracker.get_db_session")
async def test_track_product_no_target_price(
    mock_get_db_session,
    mock_apply_async,
    mock_send_signal,
    mock_scrape,
    product_without_target_price,
    mock_request,
    mock_user,
):
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
        None
    )

    await track_product(mock_request, product_without_target_price, mock_user, mock_session)

    assert product_without_target_price.target_price == 90.0

    mock_session.add.assert_called()
    mock_session.commit.assert_called()
    mock_send_signal.assert_called_once()
    mock_apply_async.assert_called_once()


@pytest.mark.asyncio
@patch("routers.tracker.scrape_product_info", return_value=MOCK_PRODUCT_INFO)
@patch("routers.tracker.send_signal_message_to_group")
@patch("tasks.price_check.check_price.apply_async")
@patch("routers.tracker.get_db_session")
async def test_track_product_existing_for_user(
    mock_get_db_session,
    mock_apply_async,
    mock_send_signal,
    mock_scrape,
    valid_product,
    mock_request,
    mock_user,
):
    """Test that a user cannot track the same URL twice."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_existing_product = MagicMock()
    mock_existing_product.id = 1
    mock_existing_product.url = "https://example.com/product"
    mock_existing_product.user_id = mock_user.id
    mock_existing_product.target_price = 85.0

    mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
        mock_existing_product
    )

    with pytest.raises(HTTPException) as exc_info:
        await track_product(mock_request, valid_product, mock_user, mock_session)

    assert exc_info.value.status_code == 400
    assert "already tracking this product" in str(exc_info.value.detail)

    mock_session.add.assert_not_called()
    mock_session.commit.assert_not_called()
    mock_send_signal.assert_not_called()
    mock_apply_async.assert_not_called()


@pytest.mark.asyncio
@patch("routers.tracker.scrape_product_info", return_value=MOCK_PRODUCT_INFO)
@patch("routers.tracker.send_signal_message_to_group")
@patch("tasks.price_check.check_price.apply_async")
@patch("routers.tracker.get_db_session")
async def test_track_product_same_url_different_users(
    mock_get_db_session,
    mock_apply_async,
    mock_send_signal,
    mock_scrape,
    valid_product,
    mock_request,
    mock_user,
    mock_other_user,
):
    """Test that different users can track the same URL."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
        None
    )

    response = await track_product(mock_request, valid_product, mock_other_user, mock_session)

    assert response["url"] == valid_product.url
    mock_session.add.assert_called()
    mock_session.commit.assert_called()


@pytest.mark.asyncio
@patch("routers.tracker.scrape_product_info", return_value=MOCK_PRODUCT_INFO)
@patch("routers.tracker.send_signal_message_to_group")
@patch("tasks.price_check.check_price.apply_async")
@patch("routers.tracker.get_db_session")
async def test_track_product_database_error(
    mock_get_db_session,
    mock_apply_async,
    mock_send_signal,
    mock_scrape,
    valid_product,
    mock_request,
    mock_user,
):
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
        None
    )

    mock_session.commit.side_effect = Exception("Database error")

    with pytest.raises(HTTPException) as exc_info:
        await track_product(mock_request, valid_product, mock_user, mock_session)

    assert exc_info.value.status_code == 500
    assert "Error tracking product" in str(exc_info.value.detail)

    mock_session.rollback.assert_called_once()


@pytest.mark.asyncio
@patch("routers.tracker.scrape_product_info", side_effect=Exception("Scraping failed"))
@patch("routers.tracker.send_signal_message_to_group")
@patch("tasks.price_check.check_price.apply_async")
@patch("routers.tracker.get_db_session")
async def test_track_product_scraping_failure(
    mock_get_db_session,
    mock_apply_async,
    mock_send_signal,
    mock_scrape,
    invalid_product,
    mock_request,
    mock_user,
):
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_session.query.return_value.filter.return_value.filter.return_value.first.return_value = (
        None
    )

    with pytest.raises(HTTPException) as exc_info:
        await track_product(mock_request, invalid_product, mock_user, mock_session)

    assert exc_info.value.status_code == 500
    assert "Error tracking product" in str(exc_info.value.detail)


@pytest.mark.asyncio
@patch("routers.tracker.get_db_session")
async def test_get_products_filters_by_user(mock_get_db_session, mock_request, mock_user):
    """Test that get_tracked_products only returns products for the authenticated user."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_product = create_mock_product(1, mock_user.id, title="User 1 Product")
    mock_session.query.return_value.filter.return_value.all.return_value = [mock_product]

    mock_price_history = MagicMock()
    mock_price_history.price = 100.0
    mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
        mock_price_history
    )

    response = await get_tracked_products(mock_request, mock_user, mock_session)

    assert len(response) == 1
    assert response[0]["id"] == 1
    assert response[0]["title"] == "User 1 Product"


@pytest.mark.asyncio
@patch("routers.tracker.get_db_session")
async def test_get_products_empty_for_new_user(mock_get_db_session, mock_request, mock_other_user):
    """Test that a new user sees no products."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_session.query.return_value.filter.return_value.all.return_value = []

    response = await get_tracked_products(mock_request, mock_other_user, mock_session)

    assert len(response) == 0


@pytest.mark.asyncio
@patch("routers.tracker.get_db_session")
async def test_get_products_error(mock_get_db_session, mock_request, mock_user):
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_session.query.side_effect = Exception("Database error")

    with pytest.raises(HTTPException) as exc_info:
        await get_tracked_products(mock_request, mock_user, mock_session)

    assert exc_info.value.status_code == 500
    assert "Error retrieving tracked products" in str(exc_info.value.detail)


@pytest.mark.asyncio
@patch("routers.tracker.get_db_session")
async def test_get_product_success(mock_get_db_session, mock_request, mock_user):
    """Test getting a specific product owned by the user."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_product = create_mock_product(1, mock_user.id)
    mock_session.query.return_value.filter.return_value.first.return_value = mock_product

    mock_price_history = MagicMock()
    mock_price_history.price = 100.0
    mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = (
        mock_price_history
    )

    response = await get_product(mock_request, 1, mock_user, mock_session)

    assert response["id"] == 1
    assert response["title"] == "Test Product"


@pytest.mark.asyncio
@patch("routers.tracker.get_db_session")
async def test_get_product_not_found(mock_get_db_session, mock_request, mock_user):
    """Test that 404 is returned when product doesn't exist."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_session.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await get_product(mock_request, 999, mock_user, mock_session)

    assert exc_info.value.status_code == 404
    assert "Product not found" in str(exc_info.value.detail)


@pytest.mark.asyncio
@patch("routers.tracker.get_db_session")
async def test_get_product_belongs_to_other_user(
    mock_get_db_session, mock_request, mock_user, mock_other_user
):
    """Test that a user cannot access another user's product."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_session.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await get_product(mock_request, 1, mock_user, mock_session)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
@patch("routers.tracker.get_db_session")
async def test_delete_product_success(mock_get_db_session, mock_request, mock_user):
    """Test successful deletion of a product owned by the user."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_product = create_mock_product(1, mock_user.id)
    mock_session.query.return_value.filter.return_value.first.return_value = mock_product

    response = await delete_product(mock_request, 1, mock_user, mock_session)

    mock_session.delete.assert_called_once_with(mock_product)
    mock_session.commit.assert_called_once()
    assert response["message"] == "Product 1 deleted successfully"


@pytest.mark.asyncio
@patch("routers.tracker.get_db_session")
async def test_delete_product_not_found(mock_get_db_session, mock_request, mock_user):
    """Test that 404 is returned when product doesn't exist."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_session.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await delete_product(mock_request, 999, mock_user, mock_session)

    assert exc_info.value.status_code == 404
    assert "Product not found" in str(exc_info.value.detail)


@pytest.mark.asyncio
@patch("routers.tracker.get_db_session")
async def test_delete_product_belongs_to_other_user(mock_get_db_session, mock_request, mock_user):
    """Test that a user cannot delete another user's product."""
    mock_session = MagicMock()
    mock_get_db_session.return_value = mock_session

    mock_session.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await delete_product(mock_request, 1, mock_user, mock_session)

    assert exc_info.value.status_code == 404
