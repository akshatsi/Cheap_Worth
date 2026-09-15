"""HTTP client functions for the Streamlit frontend, talking to the
FastAPI backend (API_BASE_URL, default http://localhost:8000).

Split out from app.py specifically so the request/response handling can
be unit tested without running Streamlit or a real server — tests inject
an httpx.MockTransport instead. app.py imports these functions and stays
thin UI glue on top.
"""

from __future__ import annotations

import os

import httpx

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

# POST /tasks can make up to three sequential Ollama calls if a task
# escalates all the way to Opus (see app/orchestration/cascade.py), each
# with its own REQUEST_TIMEOUT_SECONDS=120 in app/models/execute.py — a
# worst case of 360s before the backend itself would time out. This has
# to comfortably exceed that, not just "feel generous": a value under it
# would cut the frontend off on a legitimately-still-working escalation,
# not a stuck one.
REQUEST_TIMEOUT_SECONDS = 420


def _request(
    method: str, path: str, json: dict | None = None, client: httpx.Client | None = None
):
    if client is not None:
        response = client.request(method, path, json=json)
    else:
        response = httpx.request(
            method, f"{API_BASE_URL}{path}", json=json, timeout=REQUEST_TIMEOUT_SECONDS
        )
    response.raise_for_status()
    return response.json()


def submit_task(spec: str, tests: str, client: httpx.Client | None = None) -> dict:
    return _request("POST", "/tasks", json={"spec": spec, "tests": tests}, client=client)


def list_tasks(client: httpx.Client | None = None) -> list[dict]:
    return _request("GET", "/tasks", client=client)


def get_task(task_id: int, client: httpx.Client | None = None) -> dict:
    return _request("GET", f"/tasks/{task_id}", client=client)


def get_cost_summary(client: httpx.Client | None = None) -> dict:
    return _request("GET", "/cost-summary", client=client)
