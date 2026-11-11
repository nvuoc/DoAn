"""SQLite connection manager and schema initializer."""
from __future__ import annotations

from pathlib import Path
import sqlite3

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


def get_connection(db_path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, autocommit=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    if db_path != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    ddl = SCHEMA_FILE.read_text(encoding="utf-8-sig")
    conn.executescript(ddl)
    conn.commit()
