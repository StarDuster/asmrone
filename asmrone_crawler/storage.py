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


def _ensure_column(connection, table, column, definition):
    columns = {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


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
    _ensure_column(connection, "t_file", "file_type", "file_type TEXT")
    _ensure_column(connection, "t_file", "title", "title TEXT")
    _ensure_column(connection, "t_file", "duration", "duration REAL")
    _ensure_column(connection, "t_file", "media_stream_url", "media_stream_url TEXT")
    _ensure_column(
        connection,
        "t_file",
        "stream_low_quality_url",
        "stream_low_quality_url TEXT",
    )
    _ensure_column(connection, "t_file", "work_title", "work_title TEXT")
    _ensure_column(connection, "t_file", "raw_json", "raw_json TEXT")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS t_work (
            work_id TEXT PRIMARY KEY,
            title TEXT,
            circle_id TEXT,
            circle_name TEXT,
            source_id TEXT,
            source_type TEXT,
            source_url TEXT,
            nsfw INTEGER,
            release_date TEXT,
            create_date TEXT,
            dl_count INTEGER,
            price INTEGER,
            review_count INTEGER,
            rate_count INTEGER,
            rate_average_2dp REAL,
            has_subtitle INTEGER,
            duration INTEGER,
            work_attributes TEXT,
            age_category_string TEXT,
            sam_cover_url TEXT,
            thumbnail_cover_url TEXT,
            main_cover_url TEXT,
            raw_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS t_va (
            va_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            raw_json TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS t_work_va (
            work_id TEXT NOT NULL,
            va_id TEXT NOT NULL,
            name TEXT NOT NULL,
            PRIMARY KEY (work_id, va_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS t_tag (
            tag_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            raw_json TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS t_work_tag (
            work_id TEXT NOT NULL,
            tag_id TEXT NOT NULL,
            name TEXT NOT NULL,
            PRIMARY KEY (work_id, tag_id)
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
    connection.execute("CREATE INDEX IF NOT EXISTS idx_t_file_work_id ON t_file(work_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_t_file_path ON t_file(path)")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_t_file_download ON t_file(masked, download_date)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_t_file_cloudflare_etag ON t_file(cloudflare_etag)"
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_t_file_md5 ON t_file(md5)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_t_work_title ON t_work(title)")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_t_work_circle_name ON t_work(circle_name)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_t_work_source_id ON t_work(source_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_t_work_create_date ON t_work(create_date)"
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_t_va_name ON t_va(name)")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_t_work_va_name ON t_work_va(name)"
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_t_tag_name ON t_tag(name)")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_t_work_tag_name ON t_work_tag(name)"
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
