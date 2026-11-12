"""SQLite persistence layer. One connection per request, WAL enabled."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS rulesets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    version INTEGER NOT NULL UNIQUE,
    metrics TEXT NOT NULL,
    warnings TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS batches (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ruleset_id INTEGER NOT NULL,
    rules_version INTEGER NOT NULL,
    rules_snapshot TEXT NOT NULL,
    dataset_path TEXT NOT NULL,
    dataset_filename TEXT NOT NULL,
    dataset_hash TEXT NOT NULL,
    dataset_rows INTEGER NOT NULL DEFAULT 0,
    column_map TEXT NOT NULL,
    confirmations TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    published_at TEXT,
    parent_batch_id TEXT,
    note TEXT
);
CREATE TABLE IF NOT EXISTS rows (
    batch_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    row_no INTEGER NOT NULL,
    metric TEXT,
    status TEXT NOT NULL,
    category TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (batch_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_rows_batch_cat ON rows(batch_id, category);
CREATE INDEX IF NOT EXISTS idx_rows_batch_metric ON rows(batch_id, metric);
CREATE TABLE IF NOT EXISTS exports (
    batch_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (batch_id, kind)
);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


@contextmanager
def session(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        init_db(conn)
        yield conn
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}


def loads(value: str | None, default):
    if value is None or value == "":
        return default
    return json.loads(value)
