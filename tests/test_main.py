from pathlib import Path

from wheel_n_deal.config import load_config
from wheel_n_deal.main import sync_watch_list
from wheel_n_deal.store import open_store, read_item_id

ROOT = Path(__file__).parent.parent


def test_sync_watch_list_writes_every_item(tmp_path):
    config = load_config(ROOT / "config.example.yaml")
    conn = open_store(tmp_path / "state.db")
    ids = sync_watch_list(conn, config)
    assert len(ids) == len(config.watch)
    for item in config.watch:
        assert read_item_id(conn, item.url) == ids[item.url]
