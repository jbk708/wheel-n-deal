"""Local HTTP API for an assistant on the same host: list, add and remove watched items and
read their price history.

It binds to loopback only and runs on its own threads beside the asyncio scheduler. Each
request opens its own SQLite connection; the scheduler sees changes on its next reload.
"""

import asyncio
import hmac
import json
import logging
import re
import sqlite3
import threading
from contextlib import closing
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
from pydantic import ValidationError

from wheel_n_deal.config import WatchItem
from wheel_n_deal.fetch import canonical_url, make_shop_client
from wheel_n_deal.store import (
    Observation,
    create_item,
    delete_item,
    read_items,
    read_last_priced,
    read_observations,
)

logger = logging.getLogger(__name__)

HOST = "127.0.0.1"
PORT = 8090
_MAX_BODY_BYTES = 64 * 1024
_DEFAULT_HISTORY = 30
_ITEM_PATH = re.compile(r"/items/(\d+)")
_HISTORY_PATH = re.compile(r"/items/(\d+)/history")


class _BadRequest(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status


# Diagnostic fields are opt-in (?detail=1): clients that validate the original shape
# strictly would reject unknown keys.
def item_json(
    conn: sqlite3.Connection, item_id: int, item: WatchItem, detail: bool = False
) -> dict:
    latest = read_observations(conn, item_id, limit=1)
    # A blocked or failed check has no price, so report the last one actually seen.
    priced = read_last_priced(conn, item_id)
    found = {
        "id": item_id,
        "name": item.name,
        "url": item.url,
        "target_price": item.target_price,
        "notes": item.notes,
        "last_price": priced.price if priced else None,
        "currency": priced.currency if priced else None,
        "in_stock": priced.in_stock if priced else None,
        "last_checked": latest[0].checked_at if latest else None,
        "last_status": latest[0].status.value if latest else None,
    }
    if detail:
        found["last_http_status"] = latest[0].http_status if latest else None
        found["last_block_reason"] = latest[0].block_reason if latest else None
    return found


def observation_json(obs: Observation, detail: bool = False) -> dict:
    found = {
        "checked_at": obs.checked_at,
        "status": obs.status.value,
        "price": obs.price,
        "currency": obs.currency,
        "in_stock": obs.in_stock,
    }
    if detail:
        found["http_status"] = obs.http_status
        found["block_reason"] = obs.block_reason
    return found


def _parse_detail(query: str) -> bool:
    return parse_qs(query).get("detail") == ["1"]


async def _canonical(url: str) -> str:
    async with make_shop_client() as client:
        return await canonical_url(client, url)


def _parse_limit(query: str) -> int:
    values = parse_qs(query).get("limit")
    if not values:
        return _DEFAULT_HISTORY
    if not values[0].isdigit() or int(values[0]) < 1:
        raise _BadRequest(HTTPStatus.BAD_REQUEST, "limit must be a positive integer")
    return int(values[0])


def _parse_item(raw: bytes) -> WatchItem:
    try:
        return WatchItem.model_validate(json.loads(raw))
    except json.JSONDecodeError as exc:
        raise _BadRequest(HTTPStatus.BAD_REQUEST, "body is not JSON") from exc
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(map(str, e['loc'])) or 'body'}: {e['msg']}" for e in exc.errors()
        )
        raise _BadRequest(HTTPStatus.BAD_REQUEST, f"invalid item: {problems}") from exc


def make_server(db_path: Path, token: str, port: int = PORT) -> ThreadingHTTPServer:
    expected = f"Bearer {token}".encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._route("GET")

        def do_POST(self) -> None:
            self._route("POST")

        def do_DELETE(self) -> None:
            self._route("DELETE")

        def log_message(self, format: str, *args: object) -> None:
            logger.info("api: %s", format % args)

        def _route(self, method: str) -> None:
            url = urlsplit(self.path)
            if method == "GET" and url.path == "/healthz":
                return self._send(HTTPStatus.OK, {"ok": True})
            if not self._authorized():
                return self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            try:
                with closing(sqlite3.connect(db_path, timeout=10)) as conn:
                    conn.execute("PRAGMA foreign_keys = ON")
                    self._dispatch(conn, method, url.path, url.query)
            except _BadRequest as exc:
                self._send(exc.status, {"error": str(exc)})
            except Exception:
                logger.exception("api: %s %s failed", method, url.path)
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal error"})

        def _dispatch(self, conn: sqlite3.Connection, method: str, path: str, query: str) -> None:
            item_path = _ITEM_PATH.fullmatch(path)
            history_path = _HISTORY_PATH.fullmatch(path)
            if method == "GET" and path == "/items":
                items = read_items(conn)
                detail = _parse_detail(query)
                return self._send(
                    HTTPStatus.OK, [item_json(conn, i, it, detail) for i, it in items.items()]
                )
            if method == "POST" and path == "/items":
                return self._add(conn)
            if method == "DELETE" and item_path:
                at = datetime.now(UTC).isoformat()
                if delete_item(conn, int(item_path[1]), at):
                    return self._send(HTTPStatus.NO_CONTENT, None)
                return self._send(HTTPStatus.NOT_FOUND, {"error": "no such active item"})
            if method == "GET" and history_path:
                return self._history(conn, int(history_path[1]), query)
            self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def _add(self, conn: sqlite3.Connection) -> None:
            item = _parse_item(self._body())
            try:
                url = asyncio.run(_canonical(item.url))
            except httpx.HTTPError as exc:
                raise _BadRequest(
                    HTTPStatus.BAD_GATEWAY, f"could not resolve short link: {type(exc).__name__}"
                ) from exc
            item = item.model_copy(update={"url": url})
            item_id = create_item(conn, item)
            if item_id is None:
                return self._send(HTTPStatus.CONFLICT, {"error": "url is already watched"})
            self._send(HTTPStatus.CREATED, item_json(conn, item_id, item))

        def _history(self, conn: sqlite3.Connection, item_id: int, query: str) -> None:
            exists = conn.execute("SELECT 1 FROM items WHERE id = ?", (item_id,)).fetchone()
            if not exists:
                return self._send(HTTPStatus.NOT_FOUND, {"error": "no such item"})
            history = read_observations(conn, item_id, limit=_parse_limit(query))
            detail = _parse_detail(query)
            self._send(HTTPStatus.OK, [observation_json(obs, detail) for obs in history])

        def _authorized(self) -> bool:
            given = self.headers.get("Authorization", "").encode()
            return hmac.compare_digest(given, expected)

        def _body(self) -> bytes:
            header = self.headers.get("Content-Length") or "0"
            if not (header.isascii() and header.isdigit()):
                raise _BadRequest(HTTPStatus.BAD_REQUEST, "bad Content-Length")
            length = int(header)
            if length > _MAX_BODY_BYTES:
                raise _BadRequest(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body too large")
            return self.rfile.read(length)

        def _send(self, status: HTTPStatus, payload: object) -> None:
            body = b"" if payload is None else json.dumps(payload).encode()
            self.send_response(status)
            if payload is not None:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            if status is HTTPStatus.UNAUTHORIZED:
                self.send_header("WWW-Authenticate", "Bearer")
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer((HOST, port), Handler)


def start_api(db_path: Path, token: str | None) -> ThreadingHTTPServer | None:
    if not token:
        logger.warning("WND_API_TOKEN is not set; local API disabled")
        return None
    server = make_server(db_path, token)
    threading.Thread(target=server.serve_forever, name="api", daemon=True).start()
    logger.info("api listening on http://%s:%d", HOST, PORT)
    return server
