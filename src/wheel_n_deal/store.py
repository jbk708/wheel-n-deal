import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


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
        target_price REAL NOT NULL
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
    conn.commit()
    return conn


def write_item(conn: sqlite3.Connection, url: str, name: str, target_price: float) -> int:
    (item_id,) = conn.execute(
        "INSERT INTO items (url, name, target_price) VALUES (?, ?, ?)"
        " ON CONFLICT(url) DO UPDATE SET name = excluded.name,"
        " target_price = excluded.target_price RETURNING id",
        (url, name, target_price),
    ).fetchone()
    conn.commit()
    return item_id


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
