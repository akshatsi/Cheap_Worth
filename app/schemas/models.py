"""Shared data models for tasks, classifier predictions, executions, and cost tracking.

These are the contract every later piece of the system — the orchestration
graph, the storage layer, the API — writes against. See architecture.md for
the data model these mirror.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Tier(str, Enum):
    HAIKU = "haiku"
    SONNET = "sonnet"
    OPUS = "opus"


# Escalation order: index 0 is the cheapest, index -1 the most expensive.
ESCALATION_ORDER = [Tier.HAIKU, Tier.SONNET, Tier.OPUS]


class Phase(str, Enum):
    BOOTSTRAP = "bootstrap"
    ROUTED = "routed"


class TaskStatus(str, Enum):
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class PredictedTier(str, Enum):
    """The classifier's binary guess. Opus is never predicted directly —
    only ever reached through escalation."""

    SIMPLE = "simple"
    COMPLEX = "complex"


class TaskSubmission(BaseModel):
    """What comes in when a task is first submitted."""

    spec: str
    tests: str


class Task(TaskSubmission):
    """A submitted task, once it has an id and a status."""

    id: int
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ClassifierPrediction(BaseModel):
    id: Optional[int] = None
    task_id: int
    predicted_tier: PredictedTier
    raw_response: dict[str, Any]
    latency_ms: float
    cost_usd: float
    phase: Phase


class Execution(BaseModel):
    id: Optional[int] = None
    task_id: int
    tier: Tier
    code_output: str
    passed: bool
    validation_detail: dict[str, Any]
    cost_usd: float
    latency_ms: float
    escalated_from_execution_id: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CostLedgerEntry(BaseModel):
    id: Optional[int] = None
    task_id: int
    total_cost_usd: float
    baseline_cost_usd: float
    savings_usd: float
