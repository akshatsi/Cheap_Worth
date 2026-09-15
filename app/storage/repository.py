"""Insert/read functions for the four tables, plus persist_cascade_run —
the one function that turns a finished cascade run into rows across all
of them, wiring escalated_from_execution_id along the way and computing
the efficiency_ledger comparison against an always-Opus baseline.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from app.models.timing import estimate_baseline_time_ms
from app.orchestration.state import Attempt, CascadeState, ClassifyResult
from app.schemas.models import (
    ClassifierPrediction,
    EfficiencyLedgerEntry,
    Execution,
    Phase,
    PredictedTier,
    Task,
    TaskStatus,
    Tier,
)

# --- tasks -------------------------------------------------------------


def insert_task(
    conn: sqlite3.Connection, spec: str, tests: str, status: TaskStatus
) -> int:
    cursor = conn.execute(
        "INSERT INTO tasks (spec, tests, status) VALUES (?, ?, ?)",
        (spec, tests, status.value),
    )
    conn.commit()
    return cursor.lastrowid


def get_task(conn: sqlite3.Connection, task_id: int) -> Optional[Task]:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        return None
    return Task(
        id=row["id"],
        spec=row["spec"],
        tests=row["tests"],
        status=TaskStatus(row["status"]),
        created_at=row["created_at"],
    )


def list_tasks(conn: sqlite3.Connection) -> list[Task]:
    rows = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
    return [
        Task(
            id=r["id"],
            spec=r["spec"],
            tests=r["tests"],
            status=TaskStatus(r["status"]),
            created_at=r["created_at"],
        )
        for r in rows
    ]


# --- classifier_predictions ---------------------------------------------


def insert_classifier_prediction(
    conn: sqlite3.Connection, task_id: int, prediction: ClassifyResult, phase: Phase
) -> int:
    cursor = conn.execute(
        """INSERT INTO classifier_predictions
           (task_id, predicted_tier, raw_response, latency_ms, cost_usd, phase)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            task_id,
            prediction.predicted_tier.value,
            json.dumps(prediction.raw_response),
            prediction.latency_ms,
            prediction.cost_usd,
            phase.value,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def list_classifier_predictions_for_task(
    conn: sqlite3.Connection, task_id: int
) -> list[ClassifierPrediction]:
    rows = conn.execute(
        "SELECT * FROM classifier_predictions WHERE task_id = ? ORDER BY id",
        (task_id,),
    ).fetchall()
    return [
        ClassifierPrediction(
            id=r["id"],
            task_id=r["task_id"],
            predicted_tier=PredictedTier(r["predicted_tier"]),
            raw_response=json.loads(r["raw_response"]),
            latency_ms=r["latency_ms"],
            cost_usd=r["cost_usd"],
            phase=Phase(r["phase"]),
        )
        for r in rows
    ]


# --- executions ----------------------------------------------------------


def insert_execution(
    conn: sqlite3.Connection,
    task_id: int,
    attempt: Attempt,
    escalated_from_execution_id: Optional[int] = None,
) -> int:
    cursor = conn.execute(
        """INSERT INTO executions
           (task_id, tier, code_output, passed, validation_detail,
            latency_ms, escalated_from_execution_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            task_id,
            attempt.tier.value,
            attempt.code_output,
            int(attempt.passed),
            json.dumps(attempt.validation_detail),
            attempt.latency_ms,
            escalated_from_execution_id,
        ),
    )
    conn.commit()
    return cursor.lastrowid


def list_executions_for_task(conn: sqlite3.Connection, task_id: int) -> list[Execution]:
    rows = conn.execute(
        "SELECT * FROM executions WHERE task_id = ? ORDER BY id", (task_id,)
    ).fetchall()
    return [
        Execution(
            id=r["id"],
            task_id=r["task_id"],
            tier=Tier(r["tier"]),
            code_output=r["code_output"],
            passed=bool(r["passed"]),
            validation_detail=json.loads(r["validation_detail"]),
            latency_ms=r["latency_ms"],
            escalated_from_execution_id=r["escalated_from_execution_id"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


# --- efficiency_ledger -----------------------------------------------------


def insert_efficiency_ledger_entry(
    conn: sqlite3.Connection, task_id: int, total_time_ms: float, baseline_time_ms: float
) -> int:
    time_saved_ms = baseline_time_ms - total_time_ms
    cursor = conn.execute(
        """INSERT INTO efficiency_ledger (task_id, total_time_ms, baseline_time_ms, time_saved_ms)
           VALUES (?, ?, ?, ?)""",
        (task_id, total_time_ms, baseline_time_ms, time_saved_ms),
    )
    conn.commit()
    return cursor.lastrowid


def get_efficiency_ledger_entry(
    conn: sqlite3.Connection, task_id: int
) -> Optional[EfficiencyLedgerEntry]:
    row = conn.execute(
        "SELECT * FROM efficiency_ledger WHERE task_id = ?", (task_id,)
    ).fetchone()
    if row is None:
        return None
    return EfficiencyLedgerEntry(
        id=row["id"],
        task_id=row["task_id"],
        total_time_ms=row["total_time_ms"],
        baseline_time_ms=row["baseline_time_ms"],
        time_saved_ms=row["time_saved_ms"],
    )


def efficiency_summary(conn: sqlite3.Connection) -> dict:
    """Aggregate time spent vs. baseline across every task — the number
    the frontend's efficiency dashboard and the /efficiency-summary
    endpoint report."""
    row = conn.execute(
        """SELECT COALESCE(SUM(total_time_ms), 0), COALESCE(SUM(baseline_time_ms), 0),
                  COALESCE(SUM(time_saved_ms), 0), COUNT(*)
           FROM efficiency_ledger"""
    ).fetchone()
    total, baseline, saved, count = row
    return {
        "task_count": count,
        "total_time_ms": total,
        "baseline_time_ms": baseline,
        "time_saved_ms": saved,
    }


# --- the one call that ties a finished cascade run to all four tables ------


def persist_cascade_run(
    conn: sqlite3.Connection, spec: str, tests: str, phase: Phase, result: CascadeState
) -> int:
    """Turn one finished run of the cascade graph into rows across tasks,
    classifier_predictions, executions, and efficiency_ledger. Returns
    the task id.

    total_time_ms is real, measured wall-clock time: every attempt's
    latency, plus the classifier's latency if it ran. baseline_time_ms is
    an estimate — the last attempt's output token count, priced at
    Opus's estimated ms-per-token (see app/models/timing.py) — the same
    approximation the old $-based baseline used, just in a different
    unit: token counts are roughly stable across tiers for the same task.
    """
    task_id = insert_task(conn, spec, tests, result["status"])

    total_time_ms = 0.0
    if result["classifier_prediction"] is not None:
        insert_classifier_prediction(conn, task_id, result["classifier_prediction"], phase)
        total_time_ms += result["classifier_prediction"].latency_ms

    previous_execution_id: Optional[int] = None
    for attempt in result["attempts"]:
        previous_execution_id = insert_execution(
            conn, task_id, attempt, previous_execution_id
        )
        total_time_ms += attempt.latency_ms

    last_attempt = result["attempts"][-1]
    baseline_time_ms = estimate_baseline_time_ms(last_attempt.output_tokens)
    insert_efficiency_ledger_entry(conn, task_id, total_time_ms, baseline_time_ms)

    return task_id
