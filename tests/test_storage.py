"""Tests for the storage repositories, against a temporary SQLite file —
never the real data/cost_autopilot.db.
"""

import pytest

from app.models.timing import estimate_baseline_time_ms
from app.orchestration.state import Attempt, ClassifyResult
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


def make_attempt(tier, passed, latency_ms=12.0, input_tokens=100, output_tokens=50):
    return Attempt(
        tier=tier,
        code_output=f"code-for-{tier.value}",
        passed=passed,
        validation_detail={"returncode": 0 if passed else 1},
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def make_cascade_result(phase, attempts, classifier_prediction=None):
    return {
        "spec": "spec",
        "tests": "tests",
        "phase": phase,
        "current_tier": attempts[-1].tier,
        "classifier_prediction": classifier_prediction,
        "attempts": attempts,
        "status": TaskStatus.DONE if attempts[-1].passed else TaskStatus.FAILED,
        "pending_execution": None,
    }


def test_insert_and_get_task(conn):
    task_id = repository.insert_task(conn, "spec", "tests", TaskStatus.DONE)
    task = repository.get_task(conn, task_id)
    assert task is not None
    assert task.spec == "spec"
    assert task.status == TaskStatus.DONE


def test_get_missing_task_returns_none(conn):
    assert repository.get_task(conn, 999) is None


def test_insert_execution_and_list(conn):
    task_id = repository.insert_task(conn, "spec", "tests", TaskStatus.DONE)
    attempt = make_attempt(Tier.HAIKU, passed=True)
    execution_id = repository.insert_execution(conn, task_id, attempt)

    executions = repository.list_executions_for_task(conn, task_id)
    assert len(executions) == 1
    assert executions[0].id == execution_id
    assert executions[0].tier == Tier.HAIKU
    assert executions[0].passed is True


def test_escalation_chain_wires_escalated_from(conn):
    task_id = repository.insert_task(conn, "spec", "tests", TaskStatus.DONE)
    first_id = repository.insert_execution(conn, task_id, make_attempt(Tier.HAIKU, passed=False))
    repository.insert_execution(
        conn, task_id, make_attempt(Tier.SONNET, passed=True), escalated_from_execution_id=first_id
    )

    executions = repository.list_executions_for_task(conn, task_id)
    assert executions[0].escalated_from_execution_id is None
    assert executions[1].escalated_from_execution_id == first_id


def test_persist_cascade_run_writes_all_tables_and_computes_time_saved(conn):
    prediction = ClassifyResult(
        predicted_tier=PredictedTier.COMPLEX,
        raw_response={"text": "complex"},
        latency_ms=5.0,
        cost_usd=0.0001,
    )
    attempts = [
        make_attempt(Tier.SONNET, passed=False, latency_ms=100.0, input_tokens=200, output_tokens=100),
        make_attempt(Tier.OPUS, passed=True, latency_ms=250.0, input_tokens=200, output_tokens=100),
    ]
    result = make_cascade_result(Phase.ROUTED, attempts, prediction)

    task_id = repository.persist_cascade_run(conn, "spec", "tests", Phase.ROUTED, result)

    task = repository.get_task(conn, task_id)
    assert task.status == TaskStatus.DONE

    executions = repository.list_executions_for_task(conn, task_id)
    assert [e.tier for e in executions] == [Tier.SONNET, Tier.OPUS]
    assert executions[0].escalated_from_execution_id is None
    assert executions[1].escalated_from_execution_id == executions[0].id

    predictions = repository.list_classifier_predictions_for_task(conn, task_id)
    assert len(predictions) == 1
    assert predictions[0].predicted_tier == PredictedTier.COMPLEX

    ledger = repository.get_efficiency_ledger_entry(conn, task_id)
    assert ledger is not None
    # total_time_ms includes the classifier's latency plus every attempt's.
    assert ledger.total_time_ms == pytest.approx(5.0 + 100.0 + 250.0)
    # baseline uses the LAST attempt's output tokens, priced at Opus's rate.
    assert ledger.baseline_time_ms == pytest.approx(estimate_baseline_time_ms(100))
    assert ledger.time_saved_ms == pytest.approx(ledger.baseline_time_ms - ledger.total_time_ms)


def test_persist_cascade_run_without_classifier_prediction(conn):
    attempts = [make_attempt(Tier.HAIKU, passed=True, latency_ms=42.0)]
    result = make_cascade_result(Phase.BOOTSTRAP, attempts, classifier_prediction=None)

    task_id = repository.persist_cascade_run(conn, "spec", "tests", Phase.BOOTSTRAP, result)

    predictions = repository.list_classifier_predictions_for_task(conn, task_id)
    assert predictions == []

    ledger = repository.get_efficiency_ledger_entry(conn, task_id)
    assert ledger.total_time_ms == pytest.approx(42.0)


def test_efficiency_summary_aggregates_across_tasks(conn):
    for _ in range(2):
        attempts = [
            make_attempt(Tier.HAIKU, passed=True, latency_ms=20.0, input_tokens=50, output_tokens=20)
        ]
        result = make_cascade_result(Phase.BOOTSTRAP, attempts)
        repository.persist_cascade_run(conn, "s", "t", Phase.BOOTSTRAP, result)

    summary = repository.efficiency_summary(conn)
    assert summary["task_count"] == 2
    assert summary["total_time_ms"] == pytest.approx(40.0)
    assert summary["time_saved_ms"] == pytest.approx(
        summary["baseline_time_ms"] - summary["total_time_ms"]
    )
