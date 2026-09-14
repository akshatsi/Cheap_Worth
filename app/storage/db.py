"""SQLite connection and table definitions for the four tables in architecture.md."""

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
    cost_usd REAL NOT NULL,
    latency_ms REAL NOT NULL,
    escalated_from_execution_id INTEGER REFERENCES executions(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cost_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    total_cost_usd REAL NOT NULL,
    baseline_cost_usd REAL NOT NULL,
    savings_usd REAL NOT NULL
);
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Open a connection to a SQLite file, creating its folder if this is
    the first run. Defaults to the autopilot's real database; tests pass
    a temp path instead so they never touch real data."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path | None = None) -> None:
    """Create the four tables if they don't already exist. Safe to call
    on every startup."""
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {DB_PATH}")
