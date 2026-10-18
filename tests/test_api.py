import logging
import socket
import threading
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from wheel_n_deal.api import make_server, start_api
from wheel_n_deal.config import WatchItem
from wheel_n_deal.store import (
    Observation,
    Status,
    create_item,
    create_observation,
    delete_item,
    open_store,
    read_items,
)

TOKEN = "test-api-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
URL_A = "https://shop.example/products/a"
URL_B = "https://shop.example/products/b"


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "state.db"
    open_store(path).close()
    return path


@pytest.fixture
def api(db_path):
    server = make_server(db_path, TOKEN, port=0)
    thread = threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    with httpx.Client(base_url=f"http://{host}:{port}", timeout=5) as client:
        yield client
    server.shutdown()
    server.server_close()


def _obs(item_id: int, at: str, status: Status = Status.OK, price: float | None = 9.5):
    return Observation(
        item_id, at, status, price, "USD" if price else None, True if price else None
    )


def test_binds_loopback_only(db_path):
    server = make_server(db_path, TOKEN, port=0)
    assert server.server_address[0] == "127.0.0.1"
    server.server_close()


def test_healthz_needs_no_auth(api):
    response = api.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/items"), ("POST", "/items"), ("DELETE", "/items/1"), ("GET", "/items/1/history")],
)
@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": TOKEN}]
)
def test_routes_need_the_token(api, method, path, headers):
    assert api.request(method, path, headers=headers).status_code == 401


def test_list_items_with_latest_observation(api, db_path):
    conn = open_store(db_path)
    a = create_item(conn, WatchItem(url=URL_A, name="A", target_price=10, notes="any colour"))
    b = create_item(conn, WatchItem(url=URL_B, name="B", target_price=20))
    gone = create_item(conn, WatchItem(url="https://shop.example/gone", name="G", target_price=1))
    delete_item(conn, gone, "2026-10-18T00:00:00+00:00")
    create_observation(conn, _obs(a, "2026-10-18T01:00:00+00:00", price=9.5))
    create_observation(conn, _obs(a, "2026-10-18T07:00:00+00:00", Status.BLOCKED, None))

    response = api.get("/items", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == [
        {
            "id": a,
            "name": "A",
            "url": URL_A,
            "target_price": 10.0,
            "notes": "any colour",
            "last_price": 9.5,
            "currency": "USD",
            "in_stock": True,
            "last_checked": "2026-10-18T07:00:00+00:00",
            "last_status": "blocked",
        },
        {
            "id": b,
            "name": "B",
            "url": URL_B,
            "target_price": 20.0,
            "notes": None,
            "last_price": None,
            "currency": None,
            "in_stock": None,
            "last_checked": None,
            "last_status": None,
        },
    ]


def test_add_item(api, db_path):
    response = api.post(
        "/items", headers=AUTH, json={"url": URL_A, "name": "A", "target_price": 12.5}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["url"] == URL_A and body["target_price"] == 12.5 and body["notes"] is None
    assert body["last_status"] is None
    assert read_items(open_store(db_path)) == {
        body["id"]: WatchItem(url=URL_A, name="A", target_price=12.5)
    }


def test_add_active_url_conflicts(api):
    item = {"url": URL_A, "name": "A", "target_price": 12.5, "notes": "n"}
    assert api.post("/items", headers=AUTH, json=item).status_code == 201
    assert api.post("/items", headers=AUTH, json=item).status_code == 409


def test_add_removed_url_revives_it(api):
    item = {"url": URL_A, "name": "A", "target_price": 12.5}
    first = api.post("/items", headers=AUTH, json=item).json()
    assert api.delete(f"/items/{first['id']}", headers=AUTH).status_code == 204
    again = api.post("/items", headers=AUTH, json=item | {"target_price": 9})
    assert again.status_code == 201
    assert again.json()["id"] == first["id"] and again.json()["target_price"] == 9.0


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        b'{"url": "ftp://x", "name": "A", "target_price": 1}',
        b'{"url": "https://shop.example/a", "name": "A", "target_price": 0}',
        b'{"url": "https://shop.example/a", "target_price": 1}',
        b'{"url": "https://shop.example/a", "name": "A", "target_price": 1, "extra": 1}',
    ],
)
def test_add_rejects_invalid_body(api, body):
    response = api.post("/items", headers=AUTH | {"Content-Type": "application/json"}, content=body)
    assert response.status_code == 400
    assert "error" in response.json()


def test_add_rejects_oversized_body(api):
    big = b'{"notes": "' + b"x" * 70_000 + b'"}'
    assert api.post("/items", headers=AUTH, content=big).status_code == 413


@pytest.mark.parametrize("length", ["-1", "abc"])
def test_add_rejects_bad_content_length(api, length):
    host, port = api.base_url.host, api.base_url.port
    request = (
        f"POST /items HTTP/1.1\r\nHost: x\r\nAuthorization: Bearer {TOKEN}\r\n"
        f"Content-Length: {length}\r\nConnection: close\r\n\r\n"
    )
    with socket.create_connection((host, port), timeout=5) as sock:
        sock.sendall(request.encode())
        status_line = sock.makefile("rb").readline()
    assert status_line.split()[1] == b"400"


def test_remove_item(api, db_path):
    conn = open_store(db_path)
    a = create_item(conn, WatchItem(url=URL_A, name="A", target_price=10))
    assert api.delete(f"/items/{a}", headers=AUTH).status_code == 204
    assert read_items(conn) == {}
    assert api.delete(f"/items/{a}", headers=AUTH).status_code == 404
    assert api.delete("/items/999", headers=AUTH).status_code == 404
    assert api.get("/items", headers=AUTH).json() == []


def test_history_newest_first_with_limit(api, db_path):
    conn = open_store(db_path)
    a = create_item(conn, WatchItem(url=URL_A, name="A", target_price=10))
    start = datetime(2026, 10, 17, tzinfo=UTC)
    for hour in range(35):
        create_observation(conn, _obs(a, (start + timedelta(hours=hour)).isoformat()))
    create_observation(conn, _obs(a, "2026-10-19T00:00:00+00:00", Status.STALE, None))

    default = api.get(f"/items/{a}/history", headers=AUTH)
    assert default.status_code == 200
    assert len(default.json()) == 30
    assert default.json()[0] == {
        "checked_at": "2026-10-19T00:00:00+00:00",
        "status": "stale",
        "price": None,
        "currency": None,
        "in_stock": None,
    }
    assert default.json()[1] == {
        "checked_at": "2026-10-18T10:00:00+00:00",
        "status": "ok",
        "price": 9.5,
        "currency": "USD",
        "in_stock": True,
    }
    assert len(api.get(f"/items/{a}/history?limit=2", headers=AUTH).json()) == 2


def test_history_of_removed_item_still_readable(api, db_path):
    conn = open_store(db_path)
    a = create_item(conn, WatchItem(url=URL_A, name="A", target_price=10))
    create_observation(conn, _obs(a, "2026-10-18T01:00:00+00:00"))
    delete_item(conn, a, "2026-10-18T02:00:00+00:00")
    assert len(api.get(f"/items/{a}/history", headers=AUTH).json()) == 1


@pytest.mark.parametrize("query", ["?limit=0", "?limit=-1", "?limit=abc"])
def test_history_rejects_bad_limit(api, db_path, query):
    a = create_item(open_store(db_path), WatchItem(url=URL_A, name="A", target_price=10))
    assert api.get(f"/items/{a}/history{query}", headers=AUTH).status_code == 400


def test_unknown_item_and_path_are_404(api):
    assert api.get("/items/999/history", headers=AUTH).status_code == 404
    assert api.get("/nope", headers=AUTH).status_code == 404
    assert api.get("/items/abc/history", headers=AUTH).status_code == 404


def test_start_api_disabled_without_token(db_path, caplog):
    caplog.set_level(logging.WARNING)
    assert start_api(db_path, None) is None
    assert "WND_API_TOKEN" in caplog.text
