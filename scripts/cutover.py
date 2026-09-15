"""Bootstrap-to-routed cutover check.

Reads every task that ran through the bootstrap cascade (no
classifier_prediction row, since bootstrap skips the classifier — see
app/orchestration/cascade.py) and counts how many needed only Haiku
("simple") vs. how many needed escalation past it ("complex"). See
PRD.md's cold-start problem and architecture.md's two-phase design for
why this split matters: a classifier trained on one class alone has
nothing to actually discriminate.

Run directly against the real database: `python -m scripts.cutover`
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from app.storage.db import get_connection

DEFAULT_MIN_TASKS = 20
DEFAULT_MIN_PER_CLASS = 5


@dataclass
class CutoverReport:
    total_bootstrap_tasks: int
    simple_count: int  # first attempt (always Haiku, in bootstrap) passed
    complex_count: int  # first attempt failed — task needed escalation
    ready: bool
    reasons: list[str] = field(default_factory=list)


def check_cutover(
    conn: sqlite3.Connection,
    min_tasks: int = DEFAULT_MIN_TASKS,
    min_per_class: int = DEFAULT_MIN_PER_CLASS,
) -> CutoverReport:
    """Ready once there are enough bootstrap-phase tasks logged, with
    real examples of both classes — not just a pile of easy ones."""
    rows = conn.execute(
        """
        SELECT e.task_id, e.passed
        FROM executions e
        WHERE e.task_id NOT IN (SELECT task_id FROM classifier_predictions)
        ORDER BY e.task_id, e.id
        """
    ).fetchall()

    first_attempt_passed: dict[int, bool] = {}
    for row in rows:
        first_attempt_passed.setdefault(row["task_id"], bool(row["passed"]))

    total = len(first_attempt_passed)
    simple_count = sum(1 for passed in first_attempt_passed.values() if passed)
    complex_count = total - simple_count

    reasons = []
    if total < min_tasks:
        reasons.append(f"only {total} bootstrap tasks logged, need at least {min_tasks}")
    if simple_count < min_per_class:
        reasons.append(
            f"only {simple_count} simple examples (Haiku sufficed), need at least {min_per_class}"
        )
    if complex_count < min_per_class:
        reasons.append(
            f"only {complex_count} complex examples (needed escalation), need at least {min_per_class}"
        )

    return CutoverReport(
        total_bootstrap_tasks=total,
        simple_count=simple_count,
        complex_count=complex_count,
        ready=not reasons,
        reasons=reasons,
    )


def _print_report(report: CutoverReport) -> None:
    print(f"Bootstrap tasks logged: {report.total_bootstrap_tasks}")
    print(f"  simple (Haiku sufficed):     {report.simple_count}")
    print(f"  complex (needed escalation): {report.complex_count}")
    if report.ready:
        print()
        print("READY — enough data to switch CURRENT_PHASE to Phase.ROUTED in app/api/main.py")
    else:
        print()
        print("NOT READY:")
        for reason in report.reasons:
            print(f"  - {reason}")


if __name__ == "__main__":
    connection = get_connection()
    try:
        _print_report(check_cutover(connection))
    finally:
        connection.close()
