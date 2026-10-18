import sqlite3

import pytest

from wheel_n_deal.store import (
    Observation,
    Status,
    create_observation,
    open_store,
    read_alert_armed,
    read_item_id,
    read_observations,
    update_alert_armed,
    write_item,
)


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


def test_write_item_is_idempotent_by_url(tmp_path):
    conn = open_store(tmp_path / "state.db")
    a = write_item(conn, "https://shop.example/p/1", "Thing", 20.0)
    again = write_item(conn, "https://shop.example/p/1", "Thing v2", 18.0)
    b = write_item(conn, "https://shop.example/p/2", "Other", 5.0)
    assert a == again != b
    assert read_item_id(conn, "https://shop.example/p/1") == a
    assert read_item_id(conn, "https://shop.example/missing") is None
    row = conn.execute("SELECT name, target_price FROM items WHERE id = ?", (a,)).fetchone()
    assert row == ("Thing v2", 18.0)


def test_observations_round_trip_newest_first(tmp_path):
    conn = open_store(tmp_path / "state.db")
    item = write_item(conn, "https://shop.example/p/1", "Thing", 20.0)
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
    a = write_item(conn, "https://shop.example/p/1", "A", 1.0)
    b = write_item(conn, "https://shop.example/p/2", "B", 1.0)
    create_observation(conn, _obs(a, "2026-10-18T01:00:00+00:00"))
    assert read_observations(conn, b) == []


def test_status_values():
    assert {s.value for s in Status} == {"ok", "blocked", "stale", "error"}


def test_invalid_status_rejected_by_db(tmp_path):
    conn = open_store(tmp_path / "state.db")
    item = write_item(conn, "https://shop.example/p/1", "Thing", 20.0)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO observations (item_id, checked_at, status) VALUES (?, ?, ?)",
            (item, "t", "bogus"),
        )


def test_alert_state_defaults_armed_and_toggles(tmp_path):
    conn = open_store(tmp_path / "state.db")
    item = write_item(conn, "https://shop.example/p/1", "Thing", 20.0)
    assert read_alert_armed(conn, item) is True
    update_alert_armed(conn, item, False, "2026-10-18T01:00:00+00:00")
    assert read_alert_armed(conn, item) is False
    update_alert_armed(conn, item, True, "2026-10-18T02:00:00+00:00")
    assert read_alert_armed(conn, item) is True


def test_reopen_keeps_state(tmp_path):
    path = tmp_path / "state.db"
    conn = open_store(path)
    item = write_item(conn, "https://shop.example/p/1", "Thing", 20.0)
    create_observation(conn, _obs(item, "2026-10-18T01:00:00+00:00"))
    update_alert_armed(conn, item, False, "2026-10-18T01:00:00+00:00")
    conn.close()

    conn = open_store(path)
    assert len(read_observations(conn, item)) == 1
    assert read_alert_armed(conn, item) is False
