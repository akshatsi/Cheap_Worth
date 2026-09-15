"""The FastAPI app: submit a coding task, read back its result.

Every request runs the cascade synchronously — classify, execute, validate,
escalate, persist — and returns the finished result. No background job
queue; appropriate for a personal-scale tool with one task in flight at a
time, not a multi-tenant service.

CURRENT_PHASE is hardcoded to bootstrap for now. Step 5's cutover script
is what will eventually make this dynamic, once there's enough logged
data to trust the classifier's first guess (see architecture.md).
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException

from app.api.dependencies import (
    get_classify_fn,
    get_db_connection,
    get_execute_fn,
    get_validate_fn,
)
from app.api.schemas import TaskDetail
from app.orchestration.cascade import run_cascade
from app.orchestration.state import ClassifyFn, ExecuteFn, ValidateFn
from app.schemas.models import Phase, Task, TaskSubmission
from app.storage import repository

CURRENT_PHASE = Phase.BOOTSTRAP

# No startup hook needed: get_db_connection() (app.api.dependencies) opens
# a connection through app.storage.db.get_connection(), which creates its
# tables on every call. That also means tests overriding get_db_connection
# to a temp path never touch the real database's schema, let alone its data.
app = FastAPI(title="LLM Cost Autopilot")


def _load_task_detail(conn, task_id: int) -> TaskDetail:
    task = repository.get_task(conn, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"No task with id {task_id}")
    return TaskDetail(
        task=task,
        executions=repository.list_executions_for_task(conn, task_id),
        classifier_predictions=repository.list_classifier_predictions_for_task(conn, task_id),
        efficiency=repository.get_efficiency_ledger_entry(conn, task_id),
    )


@app.post("/tasks", response_model=TaskDetail)
def create_task(
    submission: TaskSubmission,
    classify_fn: ClassifyFn = Depends(get_classify_fn),
    execute_fn: ExecuteFn = Depends(get_execute_fn),
    validate_fn: ValidateFn = Depends(get_validate_fn),
    conn=Depends(get_db_connection),
) -> TaskDetail:
    result = run_cascade(
        spec=submission.spec,
        tests=submission.tests,
        phase=CURRENT_PHASE,
        classify_fn=classify_fn,
        execute_fn=execute_fn,
        validate_fn=validate_fn,
    )
    task_id = repository.persist_cascade_run(
        conn, submission.spec, submission.tests, CURRENT_PHASE, result
    )
    return _load_task_detail(conn, task_id)


@app.get("/tasks/{task_id}", response_model=TaskDetail)
def get_task(task_id: int, conn=Depends(get_db_connection)) -> TaskDetail:
    return _load_task_detail(conn, task_id)


@app.get("/tasks", response_model=list[Task])
def list_tasks(conn=Depends(get_db_connection)) -> list[Task]:
    return repository.list_tasks(conn)


@app.get("/efficiency-summary")
def efficiency_summary(conn=Depends(get_db_connection)) -> dict:
    return repository.efficiency_summary(conn)
