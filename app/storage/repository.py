"""Insert/read functions for the four tables, plus persist_cascade_run —
the one function that turns a finished cascade run into rows across all
of them, wiring escalated_from_execution_id along the way and computing
the cost_ledger comparison against an always-Opus baseline.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from app.models.pricing import baseline_cost_usd as compute_baseline_cost_usd
from app.orchestration.state import Attempt, CascadeState, ClassifyResult
from app.schemas.models import (
    ClassifierPrediction,
    CostLedgerEntry,
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
           (task_id, tier, code_output, passed, validation_detail, cost_usd,
            latency_ms, escalated_from_execution_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            task_id,
            attempt.tier.value,
            attempt.code_output,
            int(attempt.passed),
            json.dumps(attempt.validation_detail),
            attempt.cost_usd,
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
            cost_usd=r["cost_usd"],
            latency_ms=r["latency_ms"],
            escalated_from_execution_id=r["escalated_from_execution_id"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


# --- cost_ledger -----------------------------------------------------------


def insert_cost_ledger_entry(
    conn: sqlite3.Connection, task_id: int, total_cost_usd: float, baseline_cost_usd: float
) -> int:
    savings_usd = baseline_cost_usd - total_cost_usd
    cursor = conn.execute(
        """INSERT INTO cost_ledger (task_id, total_cost_usd, baseline_cost_usd, savings_usd)
           VALUES (?, ?, ?, ?)""",
        (task_id, total_cost_usd, baseline_cost_usd, savings_usd),
    )
    conn.commit()
    return cursor.lastrowid


def get_cost_ledger_entry(conn: sqlite3.Connection, task_id: int) -> Optional[CostLedgerEntry]:
    row = conn.execute(
        "SELECT * FROM cost_ledger WHERE task_id = ?", (task_id,)
    ).fetchone()
    if row is None:
        return None
    return CostLedgerEntry(
        id=row["id"],
        task_id=row["task_id"],
        total_cost_usd=row["total_cost_usd"],
        baseline_cost_usd=row["baseline_cost_usd"],
        savings_usd=row["savings_usd"],
    )


def cost_summary(conn: sqlite3.Connection) -> dict:
    """Aggregate spend vs. baseline across every task — the number the
    frontend's cost dashboard and a future /cost-summary endpoint report."""
    row = conn.execute(
        """SELECT COALESCE(SUM(total_cost_usd), 0), COALESCE(SUM(baseline_cost_usd), 0),
                  COALESCE(SUM(savings_usd), 0), COUNT(*)
           FROM cost_ledger"""
    ).fetchone()
    total, baseline, savings, count = row
    return {
        "task_count": count,
        "total_cost_usd": total,
        "baseline_cost_usd": baseline,
        "savings_usd": savings,
    }


# --- the one call that ties a finished cascade run to all four tables ------


def persist_cascade_run(
    conn: sqlite3.Connection, spec: str, tests: str, phase: Phase, result: CascadeState
) -> int:
    """Turn one finished run of the cascade graph into rows across tasks,
    classifier_predictions, executions, and cost_ledger. Returns the task id.

    The baseline for cost_ledger uses the last attempt's token counts,
    priced at Opus rates — a proxy for "what this task would have cost
    straight to Opus," not a real Opus call. Token counts are roughly
    stable across tiers for the same task (same input; output length
    varies some by model), so this is a reasonable approximation given the
    placeholder pricing already in play (see app/models/pricing.py).
    """
    task_id = insert_task(conn, spec, tests, result["status"])

    if result["classifier_prediction"] is not None:
        insert_classifier_prediction(conn, task_id, result["classifier_prediction"], phase)

    previous_execution_id: Optional[int] = None
    for attempt in result["attempts"]:
        previous_execution_id = insert_execution(
            conn, task_id, attempt, previous_execution_id
        )

    total_cost_usd = sum(a.cost_usd for a in result["attempts"])
    if result["classifier_prediction"] is not None:
        total_cost_usd += result["classifier_prediction"].cost_usd

    last_attempt = result["attempts"][-1]
    baseline = compute_baseline_cost_usd(last_attempt.input_tokens, last_attempt.output_tokens)
    insert_cost_ledger_entry(conn, task_id, total_cost_usd, baseline)

    return task_id
