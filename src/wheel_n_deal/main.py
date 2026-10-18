import argparse
import logging
import sqlite3

from wheel_n_deal.config import Config, load_config
from wheel_n_deal.store import open_store, write_item

logger = logging.getLogger(__name__)


def sync_watch_list(conn: sqlite3.Connection, config: Config) -> dict[str, int]:
    return {
        item.url: write_item(conn, item.url, item.name, item.target_price) for item in config.watch
    }


def run() -> None:
    parser = argparse.ArgumentParser(prog="wheel-n-deal")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    config = load_config(args.config)
    conn = open_store(config.data_dir / "state.db")
    logger.info("watching %d items", len(sync_watch_list(conn, config)))
