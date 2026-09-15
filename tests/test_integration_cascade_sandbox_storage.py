"""One end-to-end check that the real sandbox and real storage actually
connect to the cascade graph — not just each other's unit tests in
isolation. execute_fn and classify_fn stay mocked (no API keys needed),
but validate_fn is the real subprocess-based sandbox, and the result gets
persisted through the real storage repositories into a temp SQLite file.
"""

import json
from pathlib import Path

import pytest

from app.orchestration.cascade import run_cascade
from app.orchestration.state import ClassifyResult, ExecuteResult
from app.sandbox.runner import validate
from app.schemas.models import Phase, PredictedTier, TaskStatus, Tier
from app.storage import repository
from app.storage.db import get_connection, init_db


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    connection = get_connection(db_path)
    yield connection
    connection.close()


def test_correct_solution_passes_on_first_attempt_and_persists(conn):
    fixture = json.loads(
        Path("tests/fixtures/sample_tasks/01_add_two_numbers.json").read_text()
    )
    correct_code = "def add(a, b):\n    return a + b\n"

    def execute_fn(tier, spec):
        return ExecuteResult(
            code_output=correct_code, latency_ms=10.0,
            input_tokens=50, output_tokens=20,
        )

    def classify_fn(spec):  # unused in bootstrap phase, present for the signature
        return ClassifyResult(
            predicted_tier=PredictedTier.SIMPLE, raw_response={}, latency_ms=1.0, cost_usd=0.0
        )

    result = run_cascade(
        spec=fixture["spec"],
        tests=fixture["tests"],
        phase=Phase.BOOTSTRAP,
        classify_fn=classify_fn,
        execute_fn=execute_fn,
        validate_fn=validate,  # the real sandbox, not a mock
    )

    assert result["status"] == TaskStatus.DONE
    assert len(result["attempts"]) == 1
    assert result["attempts"][0].passed is True

    task_id = repository.persist_cascade_run(
        conn, fixture["spec"], fixture["tests"], Phase.BOOTSTRAP, result
    )

    task = repository.get_task(conn, task_id)
    assert task.status == TaskStatus.DONE

    executions = repository.list_executions_for_task(conn, task_id)
    assert len(executions) == 1
    assert executions[0].tier == Tier.HAIKU
    assert executions[0].passed is True

    ledger = repository.get_efficiency_ledger_entry(conn, task_id)
    assert ledger.total_time_ms == pytest.approx(10.0)


def test_wrong_then_right_solution_escalates_and_persists_the_chain(conn):
    fixture = json.loads(
        Path("tests/fixtures/sample_tasks/01_add_two_numbers.json").read_text()
    )
    wrong_code = "def add(a, b):\n    return a - b\n"
    right_code = "def add(a, b):\n    return a + b\n"

    def execute_fn(tier, spec):
        code = wrong_code if tier == Tier.HAIKU else right_code
        return ExecuteResult(
            code_output=code, latency_ms=10.0,
            input_tokens=50, output_tokens=20,
        )

    def classify_fn(spec):
        return ClassifyResult(
            predicted_tier=PredictedTier.SIMPLE, raw_response={}, latency_ms=1.0, cost_usd=0.0
        )

    result = run_cascade(
        spec=fixture["spec"],
        tests=fixture["tests"],
        phase=Phase.BOOTSTRAP,
        classify_fn=classify_fn,
        execute_fn=execute_fn,
        validate_fn=validate,
    )

    assert result["status"] == TaskStatus.DONE
    tiers_tried = [a.tier for a in result["attempts"]]
    assert tiers_tried == [Tier.HAIKU, Tier.SONNET]
    assert result["attempts"][0].passed is False
    assert result["attempts"][1].passed is True

    task_id = repository.persist_cascade_run(
        conn, fixture["spec"], fixture["tests"], Phase.BOOTSTRAP, result
    )
    executions = repository.list_executions_for_task(conn, task_id)
    assert executions[0].escalated_from_execution_id is None
    assert executions[1].escalated_from_execution_id == executions[0].id
