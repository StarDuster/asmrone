import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


def _default_sqlite_path():
    data_home = Path(os.environ.get("XDG_DATA_HOME", "~/.local/share")).expanduser()
    return data_home / "asmrone" / "asmrone.db"


def sqlite_path():
    return Path(os.environ.get("SQLITE_PATH", _default_sqlite_path())).expanduser()


def connect():
    path = sqlite_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_db(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS t_file (
            uuid TEXT PRIMARY KEY,
            work_id TEXT NOT NULL,
            path TEXT NOT NULL,
            download_url TEXT NOT NULL,
            cloudflare_etag TEXT,
            size INTEGER NOT NULL,
            md5 TEXT,
            download_date TEXT,
            masked INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS crawl_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.commit()


@contextmanager
def database():
    connection = connect()
    try:
        init_db(connection)
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_crawl_state(key):
    with database() as connection:
        row = connection.execute(
            "SELECT value FROM crawl_state WHERE key = ?",
            (key,),
        ).fetchone()
    return row[0] if row else None


def set_crawl_state(key, value):
    with database() as connection:
        connection.execute(
            """
            INSERT INTO crawl_state (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value, datetime.utcnow().isoformat()),
        )
