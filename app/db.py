"""SQLite database utilities for the YouTube download web UI.

- DB file: ./webui.db (project root)
- Table: downloads (created on startup if not exists)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "webui.db"
DOWNLOADS_DIR = ROOT_DIR / "downloads"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    title TEXT,
    -- ステータス：キュー登録(queued), ダウンロード中(downloading), 完了(completed), エラー(error), キャンセル(canceled)
    status TEXT NOT NULL CHECK(status IN ('queued', 'downloading', 'completed', 'error', 'canceled')) DEFAULT 'queued',
    -- 保存形式：動画(video), 音声(audio)
    download_type TEXT NOT NULL CHECK(download_type IN ('video', 'audio')),
    file_size INTEGER NOT NULL DEFAULT 0,
    progress INTEGER NOT NULL DEFAULT 0,
    file_path TEXT,
    error_message TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def get_connection() -> sqlite3.Connection:
    """Create a SQLite3 connection with sane defaults.

    Returns:
        sqlite3.Connection: connection with Row factory and timeouts set.
    """
    conn = sqlite3.connect(DB_PATH)
    # Return rows as dict-like objects
    conn.row_factory = sqlite3.Row
    # Avoid "database is locked" in light concurrent access
    conn.execute("PRAGMA busy_timeout = 5000;")
    # Safer journaling mode for concurrent readers/writers
    conn.execute("PRAGMA journal_mode = WAL;")
    # Enforce foreign keys (none yet, but good habit)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    """Initialize the database schema if it does not exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
