"""SQLite connection and table definitions for the four tables in architecture.md.

No migration handling — this is pre-production. If an old data/*.db file
has a leftover cost_ledger table from before the $-to-time reframe, delete
it; a fresh efficiency_ledger table gets created alongside it otherwise."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "cost_autopilot.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spec TEXT NOT NULL,
    tests TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS classifier_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    predicted_tier TEXT NOT NULL,
    raw_response TEXT NOT NULL,
    latency_ms REAL NOT NULL,
    cost_usd REAL NOT NULL,
    phase TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    tier TEXT NOT NULL,
    code_output TEXT NOT NULL,
    passed INTEGER NOT NULL,
    validation_detail TEXT NOT NULL,
    latency_ms REAL NOT NULL,
    escalated_from_execution_id INTEGER REFERENCES executions(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS efficiency_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    total_time_ms REAL NOT NULL,
    baseline_time_ms REAL NOT NULL,
    time_saved_ms REAL NOT NULL
);
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a connection to a SQLite file, creating its folder and its
    tables (idempotently) if this is the first run. Defaults to the
    autopilot's real database; tests pass a temp path instead so they
    never touch real data — and never need to touch the real database's
    schema either, since every connection is self-initializing."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def init_db(db_path: Path | None = None) -> None:
    """Explicit convenience wrapper for CLI use — get_connection() already
    creates the tables on every call, so nothing outside this module needs
    to call init_db() to be safe."""
    get_connection(db_path).close()


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {DB_PATH}")
