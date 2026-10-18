import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from wheel_n_deal.config import WatchItem


class Status(StrEnum):
    OK = "ok"
    BLOCKED = "blocked"
    STALE = "stale"
    ERROR = "error"


_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY,
        url TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        target_price REAL NOT NULL,
        notes TEXT,
        removed_at TEXT
    )
    """,
    f"""
    CREATE TABLE IF NOT EXISTS observations (
        id INTEGER PRIMARY KEY,
        item_id INTEGER NOT NULL REFERENCES items(id),
        checked_at TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ({", ".join(f"'{s.value}'" for s in Status)})),
        price REAL,
        currency TEXT,
        in_stock INTEGER
    )
    """,
    "CREATE INDEX IF NOT EXISTS observations_item ON observations (item_id, checked_at)",
    """
    CREATE TABLE IF NOT EXISTS learned_selectors (
        item_id INTEGER PRIMARY KEY REFERENCES items(id),
        selector TEXT NOT NULL,
        learned_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS alert_state (
        item_id INTEGER PRIMARY KEY REFERENCES items(id),
        armed INTEGER NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
]


@dataclass(frozen=True)
class Observation:
    item_id: int
    checked_at: str
    status: Status
    price: float | None
    currency: str | None
    in_stock: bool | None


def _observation(row: tuple) -> Observation:
    return Observation(
        item_id=row[0],
        checked_at=row[1],
        status=Status(row[2]),
        price=row[3],
        currency=row[4],
        in_stock=None if row[5] is None else bool(row[5]),
    )


def open_store(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    for statement in _SCHEMA:
        conn.execute(statement)
    _add_missing_item_columns(conn)
    conn.commit()
    return conn


def _add_missing_item_columns(conn: sqlite3.Connection) -> None:
    """Databases created before the watch list moved into SQLite lack these columns."""
    have = {row[1] for row in conn.execute("PRAGMA table_info(items)")}
    for column in ("notes", "removed_at"):
        if column not in have:
            conn.execute(f"ALTER TABLE items ADD COLUMN {column} TEXT")


def seed_item(conn: sqlite3.Connection, item: WatchItem) -> None:
    conn.execute(
        "INSERT INTO items (url, name, target_price, notes) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(url) DO NOTHING",
        (item.url, item.name, item.target_price, item.notes),
    )
    conn.commit()


def create_item(conn: sqlite3.Connection, item: WatchItem) -> int | None:
    """Insert a new item, or revive a removed one with the same URL; None if already active."""
    row = conn.execute(
        "INSERT INTO items (url, name, target_price, notes) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(url) DO UPDATE SET name = excluded.name,"
        " target_price = excluded.target_price, notes = excluded.notes, removed_at = NULL"
        " WHERE items.removed_at IS NOT NULL RETURNING id",
        (item.url, item.name, item.target_price, item.notes),
    ).fetchone()
    if row is None:
        conn.rollback()
        return None
    # A revived item starts with a fresh alert so a new target can fire.
    conn.execute("DELETE FROM alert_state WHERE item_id = ?", row)
    conn.commit()
    return row[0]


def read_items(conn: sqlite3.Connection) -> dict[int, WatchItem]:
    rows = conn.execute(
        "SELECT id, url, name, target_price, notes FROM items WHERE removed_at IS NULL ORDER BY id"
    )
    return {
        row[0]: WatchItem(url=row[1], name=row[2], target_price=row[3], notes=row[4])
        for row in rows
    }


def delete_item(conn: sqlite3.Connection, item_id: int, at: str) -> bool:
    """Soft-remove: the row and its history stay, so the seed never re-imports the URL."""
    removed = conn.execute(
        "UPDATE items SET removed_at = ? WHERE id = ? AND removed_at IS NULL", (at, item_id)
    ).rowcount
    conn.commit()
    return removed == 1


def read_item_id(conn: sqlite3.Connection, url: str) -> int | None:
    row = conn.execute("SELECT id FROM items WHERE url = ?", (url,)).fetchone()
    return row[0] if row else None


def create_observation(conn: sqlite3.Connection, obs: Observation) -> None:
    conn.execute(
        "INSERT INTO observations (item_id, checked_at, status, price, currency, in_stock)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            obs.item_id,
            obs.checked_at,
            obs.status.value,
            obs.price,
            obs.currency,
            None if obs.in_stock is None else int(obs.in_stock),
        ),
    )
    conn.commit()


def read_observations(
    conn: sqlite3.Connection, item_id: int, limit: int | None = None
) -> list[Observation]:
    rows = conn.execute(
        "SELECT item_id, checked_at, status, price, currency, in_stock FROM observations"
        " WHERE item_id = ? ORDER BY checked_at DESC, id DESC LIMIT ?",
        (item_id, -1 if limit is None else limit),
    )
    return [_observation(row) for row in rows]


def read_alert_armed(conn: sqlite3.Connection, item_id: int) -> bool:
    row = conn.execute("SELECT armed FROM alert_state WHERE item_id = ?", (item_id,)).fetchone()
    return True if row is None else bool(row[0])


def update_alert_armed(conn: sqlite3.Connection, item_id: int, armed: bool, at: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO alert_state (item_id, armed, updated_at) VALUES (?, ?, ?)",
        (item_id, int(armed), at),
    )
    conn.commit()


def read_last_priced(conn: sqlite3.Connection, item_id: int) -> Observation | None:
    row = conn.execute(
        "SELECT item_id, checked_at, status, price, currency, in_stock FROM observations"
        " WHERE item_id = ? AND price IS NOT NULL ORDER BY checked_at DESC, id DESC LIMIT 1",
        (item_id,),
    ).fetchone()
    return _observation(row) if row else None


def read_selector(conn: sqlite3.Connection, item_id: int) -> str | None:
    row = conn.execute(
        "SELECT selector FROM learned_selectors WHERE item_id = ?", (item_id,)
    ).fetchone()
    return row[0] if row else None


def write_selector(conn: sqlite3.Connection, item_id: int, selector: str, at: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO learned_selectors (item_id, selector, learned_at) VALUES (?, ?, ?)",
        (item_id, selector, at),
    )
    conn.commit()


def delete_selector(conn: sqlite3.Connection, item_id: int) -> None:
    conn.execute("DELETE FROM learned_selectors WHERE item_id = ?", (item_id,))
    conn.commit()
