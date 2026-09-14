"""FastAPI dependencies for the classify/execute/validate calls and the
database connection.

Defined as overridable dependencies specifically so tests can swap in
fakes — see tests/test_api.py — without needing real API keys or ever
touching the real database. The route handlers in app.api.main never
import app.models or app.storage.db directly; they only see these.
"""

from __future__ import annotations

from app.models.classify import classify as _real_classify
from app.models.execute import execute as _real_execute
from app.sandbox.runner import validate as _real_validate
from app.storage.db import get_connection


def get_classify_fn():
    return _real_classify


def get_execute_fn():
    return _real_execute


def get_validate_fn():
    return _real_validate


def get_db_connection():
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
