"""Response shapes for the API layer.

TaskDetail is what both POST /tasks and GET /tasks/{id} return — the whole
tier trace for one task, not just the task row, since that trace is the
entire point of the routing transparency this project is built around.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.schemas.models import ClassifierPrediction, EfficiencyLedgerEntry, Execution, Task


class TaskDetail(BaseModel):
    task: Task
    executions: list[Execution]
    classifier_predictions: list[ClassifierPrediction]
    efficiency: Optional[EfficiencyLedgerEntry]
