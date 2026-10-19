import sqlite3

import pytest

from wheel_n_deal.config import WatchItem
from wheel_n_deal.store import (
    Observation,
    Status,
    create_item,
    create_observation,
    delete_item,
    delete_selector,
    open_store,
    read_alert_armed,
    read_item_id,
    read_items,
    read_last_priced,
    read_observations,
    read_selector,
    seed_item,
    update_alert_armed,
    write_selector,
)

REMOVED_AT = "2026-10-18T09:00:00+00:00"


def _item(url: str, name: str = "Thing", target_price: float = 20.0, notes=None) -> WatchItem:
    return WatchItem(url=url, name=name, target_price=target_price, notes=notes)


def _obs(item_id: int, checked_at: str, **overrides: object) -> Observation:
    defaults = dict(
        item_id=item_id,
        checked_at=checked_at,
        status=Status.OK,
        price=19.99,
        currency="USD",
        in_stock=True,
    )
    defaults.update(overrides)
    return Observation(**defaults)


def test_open_creates_parent_dir(tmp_path):
    path = tmp_path / "sub" / "state.db"
    open_store(path).close()
    assert path.exists()


def test_create_item_round_trips_and_rejects_active_duplicate(tmp_path):
    conn = open_store(tmp_path / "state.db")
    a = create_item(conn, _item("https://shop.example/p/1", "Thing", 20.0, "any colour"))
    b = create_item(conn, _item("https://shop.example/p/2", "Other", 5.0))
    assert a != b
    assert create_item(conn, _item("https://shop.example/p/1", "Thing v2", 18.0)) is None
    assert read_item_id(conn, "https://shop.example/p/1") == a
    assert read_item_id(conn, "https://shop.example/missing") is None
    assert read_items(conn) == {
        a: _item("https://shop.example/p/1", "Thing", 20.0, "any colour"),
        b: _item("https://shop.example/p/2", "Other", 5.0),
    }


def test_delete_item_soft_removes(tmp_path):
    conn = open_store(tmp_path / "state.db")
    a = create_item(conn, _item("https://shop.example/p/1"))
    b = create_item(conn, _item("https://shop.example/p/2"))
    create_observation(conn, _obs(a, "2026-10-18T01:00:00+00:00"))
    assert delete_item(conn, a, REMOVED_AT) is True
    assert delete_item(conn, a, REMOVED_AT) is False
    assert delete_item(conn, 999, REMOVED_AT) is False
    assert list(read_items(conn)) == [b]
    assert len(read_observations(conn, a)) == 1


def test_create_item_revives_removed_url_with_new_fields(tmp_path):
    conn = open_store(tmp_path / "state.db")
    a = create_item(conn, _item("https://shop.example/p/1", "Old", 20.0))
    create_observation(conn, _obs(a, "2026-10-18T01:00:00+00:00"))
    update_alert_armed(conn, a, False, "2026-10-18T01:00:00+00:00")
    delete_item(conn, a, REMOVED_AT)
    again = create_item(conn, _item("https://shop.example/p/1", "New", 15.0, "n"))
    assert again == a
    assert read_items(conn) == {a: _item("https://shop.example/p/1", "New", 15.0, "n")}
    assert len(read_observations(conn, a)) == 1
    assert read_alert_armed(conn, a) is True


def test_seed_item_only_imports_unseen_urls(tmp_path):
    conn = open_store(tmp_path / "state.db")
    kept = create_item(conn, _item("https://shop.example/p/1", "Edited in DB", 9.0))
    gone = create_item(conn, _item("https://shop.example/p/2"))
    delete_item(conn, gone, REMOVED_AT)
    seed_item(conn, _item("https://shop.example/p/1", "From config", 20.0))
    seed_item(conn, _item("https://shop.example/p/2"))
    seed_item(conn, _item("https://shop.example/p/3", "New", 30.0, "seeded"))
    new = read_item_id(conn, "https://shop.example/p/3")
    assert read_items(conn) == {
        kept: _item("https://shop.example/p/1", "Edited in DB", 9.0),
        new: _item("https://shop.example/p/3", "New", 30.0, "seeded"),
    }


def test_open_store_migrates_pre_notes_schema(tmp_path):
    path = tmp_path / "state.db"
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE items (id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE,"
        " name TEXT NOT NULL, target_price REAL NOT NULL)"
    )
    old.execute(
        "INSERT INTO items (url, name, target_price) VALUES ('https://a.example/1', 'A', 5)"
    )
    old.commit()
    old.close()
    conn = open_store(path)
    assert read_items(conn) == {1: _item("https://a.example/1", "A", 5.0)}
    open_store(path).close()


def test_open_store_migrates_pre_block_reason_observations(tmp_path):
    path = tmp_path / "state.db"
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE items (id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE,"
        " name TEXT NOT NULL, target_price REAL NOT NULL, notes TEXT, removed_at TEXT)"
    )
    old.execute(
        "CREATE TABLE observations (id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL,"
        " checked_at TEXT NOT NULL, status TEXT NOT NULL, price REAL, currency TEXT,"
        " in_stock INTEGER)"
    )
    old.execute(
        "INSERT INTO items (url, name, target_price) VALUES ('https://a.example/1', 'A', 5)"
    )
    old.execute(
        "INSERT INTO observations (item_id, checked_at, status, price, currency, in_stock)"
        " VALUES (1, '2026-10-18T01:00:00+00:00', 'ok', 4.5, 'USD', 1)"
    )
    old.commit()
    old.close()
    conn = open_store(path)
    assert read_observations(conn, 1) == [_obs(1, "2026-10-18T01:00:00+00:00", price=4.5)]
    blocked = _obs(
        1,
        "2026-10-18T07:00:00+00:00",
        status=Status.BLOCKED,
        price=None,
        currency=None,
        in_stock=None,
        http_status=403,
        block_reason="http 403",
    )
    create_observation(conn, blocked)
    assert read_observations(conn, 1, limit=1) == [blocked]
    open_store(path).close()


def test_observations_round_trip_newest_first(tmp_path):
    conn = open_store(tmp_path / "state.db")
    item = create_item(conn, _item("https://shop.example/p/1", "Thing", 20.0))
    create_observation(conn, _obs(item, "2026-10-18T01:00:00+00:00"))
    create_observation(
        conn,
        _obs(
            item,
            "2026-10-18T07:00:00+00:00",
            status=Status.BLOCKED,
            price=None,
            currency=None,
            in_stock=None,
        ),
    )
    create_observation(conn, _obs(item, "2026-10-18T04:00:00+00:00", price=17.5, in_stock=False))

    history = read_observations(conn, item)
    assert [o.checked_at[11:13] for o in history] == ["07", "04", "01"]
    assert history[0].status is Status.BLOCKED
    assert history[0].price is None and history[0].in_stock is None
    assert history[1].price == 17.5 and history[1].in_stock is False
    assert history[2] == _obs(item, "2026-10-18T01:00:00+00:00")
    assert read_observations(conn, item, limit=1) == history[:1]


def test_observations_scoped_to_item(tmp_path):
    conn = open_store(tmp_path / "state.db")
    a = create_item(conn, _item("https://shop.example/p/1", "A", 1.0))
    b = create_item(conn, _item("https://shop.example/p/2", "B", 1.0))
    create_observation(conn, _obs(a, "2026-10-18T01:00:00+00:00"))
    assert read_observations(conn, b) == []


def test_read_last_priced_skips_priceless(tmp_path):
    conn = open_store(tmp_path / "state.db")
    item_id = create_item(conn, _item("https://a.example/1", "A", 10.0))
    assert read_last_priced(conn, item_id) is None
    create_observation(conn, _obs(item_id, "2026-10-18T00:00:00+00:00", price=9.5))
    create_observation(
        conn, _obs(item_id, "2026-10-18T06:00:00+00:00", status=Status.ERROR, price=None)
    )
    assert read_last_priced(conn, item_id).price == 9.5


def test_selector_crud(tmp_path):
    conn = open_store(tmp_path / "state.db")
    item_id = create_item(conn, _item("https://a.example/1", "A", 10.0))
    assert read_selector(conn, item_id) is None
    write_selector(conn, item_id, "css:#price", "2026-10-18T00:00:00+00:00")
    write_selector(conn, item_id, "css:#new-price", "2026-10-18T06:00:00+00:00")
    assert read_selector(conn, item_id) == "css:#new-price"
    delete_selector(conn, item_id)
    assert read_selector(conn, item_id) is None


def test_status_values():
    assert {s.value for s in Status} == {"ok", "blocked", "stale", "error"}


def test_invalid_status_rejected_by_db(tmp_path):
    conn = open_store(tmp_path / "state.db")
    item = create_item(conn, _item("https://shop.example/p/1", "Thing", 20.0))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO observations (item_id, checked_at, status) VALUES (?, ?, ?)",
            (item, "t", "bogus"),
        )


def test_alert_state_defaults_armed_and_toggles(tmp_path):
    conn = open_store(tmp_path / "state.db")
    item = create_item(conn, _item("https://shop.example/p/1", "Thing", 20.0))
    assert read_alert_armed(conn, item) is True
    update_alert_armed(conn, item, False, "2026-10-18T01:00:00+00:00")
    assert read_alert_armed(conn, item) is False
    update_alert_armed(conn, item, True, "2026-10-18T02:00:00+00:00")
    assert read_alert_armed(conn, item) is True


def test_reopen_keeps_state(tmp_path):
    path = tmp_path / "state.db"
    conn = open_store(path)
    item = create_item(conn, _item("https://shop.example/p/1", "Thing", 20.0))
    create_observation(conn, _obs(item, "2026-10-18T01:00:00+00:00"))
    update_alert_armed(conn, item, False, "2026-10-18T01:00:00+00:00")
    conn.close()

    conn = open_store(path)
    assert len(read_observations(conn, item)) == 1
    assert read_alert_armed(conn, item) is False
