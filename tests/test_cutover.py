"""Tests for the bootstrap-to-routed cutover check, against a temp SQLite
file with logged cascade runs — no real API calls needed to exercise the
counting logic.
"""

import pytest

from app.orchestration.state import Attempt, ClassifyResult
from app.schemas.models import Phase, PredictedTier, TaskStatus, Tier
from app.storage import repository
from app.storage.db import get_connection, init_db
from scripts.cutover import check_cutover


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    connection = get_connection(db_path)
    yield connection
    connection.close()


def _log_bootstrap_task(conn, tiers_and_pass):
    """tiers_and_pass: [(Tier, passed), ...] in the order they were tried."""
    attempts = [
        Attempt(
            tier=tier,
            code_output="code",
            passed=passed,
            validation_detail={},
            latency_ms=1.0,
            input_tokens=10,
            output_tokens=5,
        )
        for tier, passed in tiers_and_pass
    ]
    result = {
        "spec": "s",
        "tests": "t",
        "phase": Phase.BOOTSTRAP,
        "current_tier": attempts[-1].tier,
        "classifier_prediction": None,
        "attempts": attempts,
        "status": TaskStatus.DONE if attempts[-1].passed else TaskStatus.FAILED,
        "pending_execution": None,
    }
    repository.persist_cascade_run(conn, "s", "t", Phase.BOOTSTRAP, result)


def test_not_ready_with_too_few_tasks(conn):
    _log_bootstrap_task(conn, [(Tier.HAIKU, True)])

    report = check_cutover(conn, min_tasks=5, min_per_class=1)

    assert report.ready is False
    assert report.total_bootstrap_tasks == 1
    assert any("5" in reason for reason in report.reasons)


def test_ready_once_both_classes_have_enough_examples(conn):
    for _ in range(3):
        _log_bootstrap_task(conn, [(Tier.HAIKU, True)])  # simple
    for _ in range(3):
        _log_bootstrap_task(conn, [(Tier.HAIKU, False), (Tier.SONNET, True)])  # complex

    report = check_cutover(conn, min_tasks=5, min_per_class=2)

    assert report.ready is True
    assert report.total_bootstrap_tasks == 6
    assert report.simple_count == 3
    assert report.complex_count == 3
    assert report.reasons == []


def test_not_ready_if_every_example_is_the_same_class(conn):
    for _ in range(10):
        _log_bootstrap_task(conn, [(Tier.HAIKU, True)])  # all simple, zero complex examples

    report = check_cutover(conn, min_tasks=5, min_per_class=2)

    assert report.ready is False
    assert report.complex_count == 0
    assert any("complex" in reason for reason in report.reasons)


def test_ignores_tasks_that_already_went_through_the_classifier(conn):
    routed_attempt = Attempt(
        tier=Tier.HAIKU, code_output="c", passed=True, validation_detail={}, latency_ms=1.0
    )
    routed_result = {
        "spec": "s",
        "tests": "t",
        "phase": Phase.ROUTED,
        "current_tier": Tier.HAIKU,
        "classifier_prediction": ClassifyResult(
            predicted_tier=PredictedTier.SIMPLE, raw_response={}, latency_ms=1.0, cost_usd=0.0
        ),
        "attempts": [routed_attempt],
        "status": TaskStatus.DONE,
        "pending_execution": None,
    }
    repository.persist_cascade_run(conn, "s", "t", Phase.ROUTED, routed_result)

    report = check_cutover(conn, min_tasks=1, min_per_class=1)

    assert report.total_bootstrap_tasks == 0
    assert report.ready is False


def test_escalation_beyond_haiku_always_counts_as_complex_even_if_sonnet_also_fails(conn):
    _log_bootstrap_task(conn, [(Tier.HAIKU, False), (Tier.SONNET, False), (Tier.OPUS, True)])

    report = check_cutover(conn, min_tasks=1, min_per_class=1)

    assert report.complex_count == 1
    assert report.simple_count == 0
