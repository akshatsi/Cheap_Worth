"""API tests via FastAPI's TestClient. classify/execute stay mocked — no
API keys, no network; validate uses the real sandbox since it's local and
free. The database dependency is overridden to a temp file so these tests
never touch the real data/cost_autopilot.db.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_classify_fn,
    get_db_connection,
    get_execute_fn,
    get_validate_fn,
)
from app.api.main import app
from app.orchestration.state import ClassifyResult, ExecuteResult
from app.sandbox.runner import validate as real_validate
from app.schemas.models import PredictedTier, Tier
from app.storage.db import get_connection, init_db

CORRECT_ADD_CODE = "def add(a, b):\n    return a + b\n"
WRONG_ADD_CODE = "def add(a, b):\n    return a - b\n"


def _fixture_task():
    return json.loads(Path("tests/fixtures/sample_tasks/01_add_two_numbers.json").read_text())


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    def override_db():
        conn = get_connection(db_path)
        try:
            yield conn
        finally:
            conn.close()

    def fake_execute(tier, spec):
        return ExecuteResult(
            code_output=CORRECT_ADD_CODE,
            latency_ms=10.0,
            input_tokens=50,
            output_tokens=20,
        )

    def fake_classify(spec):
        return ClassifyResult(
            predicted_tier=PredictedTier.SIMPLE, raw_response={}, latency_ms=1.0, cost_usd=0.0
        )

    app.dependency_overrides[get_db_connection] = override_db
    app.dependency_overrides[get_execute_fn] = lambda: fake_execute
    app.dependency_overrides[get_classify_fn] = lambda: fake_classify
    app.dependency_overrides[get_validate_fn] = lambda: real_validate

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


def test_create_task_runs_cascade_and_returns_full_detail(client):
    task_data = _fixture_task()
    response = client.post(
        "/tasks", json={"spec": task_data["spec"], "tests": task_data["tests"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["task"]["status"] == "done"
    assert len(body["executions"]) == 1
    assert body["executions"][0]["tier"] == Tier.HAIKU.value
    assert body["efficiency"] is not None
    assert body["efficiency"]["total_time_ms"] == pytest.approx(10.0)


def test_get_task_returns_the_same_detail(client):
    task_data = _fixture_task()
    create_response = client.post(
        "/tasks", json={"spec": task_data["spec"], "tests": task_data["tests"]}
    )
    task_id = create_response.json()["task"]["id"]

    response = client.get(f"/tasks/{task_id}")

    assert response.status_code == 200
    assert response.json()["task"]["id"] == task_id


def test_get_missing_task_returns_404(client):
    response = client.get("/tasks/9999")
    assert response.status_code == 404


def test_list_tasks_returns_history_in_order(client):
    task_data = _fixture_task()
    client.post("/tasks", json={"spec": task_data["spec"], "tests": task_data["tests"]})
    client.post("/tasks", json={"spec": task_data["spec"], "tests": task_data["tests"]})

    response = client.get("/tasks")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["id"] < body[1]["id"]


def test_efficiency_summary_aggregates_across_tasks(client):
    task_data = _fixture_task()
    client.post("/tasks", json={"spec": task_data["spec"], "tests": task_data["tests"]})
    client.post("/tasks", json={"spec": task_data["spec"], "tests": task_data["tests"]})

    response = client.get("/efficiency-summary")

    assert response.status_code == 200
    body = response.json()
    assert body["task_count"] == 2
    assert body["total_time_ms"] == pytest.approx(20.0)


def test_create_task_with_failing_code_escalates_and_reports_failure(client):
    def fake_execute_always_wrong(tier, spec):
        return ExecuteResult(
            code_output=WRONG_ADD_CODE,
            latency_ms=10.0,
            input_tokens=50,
            output_tokens=20,
        )

    app.dependency_overrides[get_execute_fn] = lambda: fake_execute_always_wrong

    task_data = _fixture_task()
    response = client.post(
        "/tasks", json={"spec": task_data["spec"], "tests": task_data["tests"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["task"]["status"] == "failed"
    assert len(body["executions"]) == 3
    assert [e["tier"] for e in body["executions"]] == [
        Tier.HAIKU.value,
        Tier.SONNET.value,
        Tier.OPUS.value,
    ]
