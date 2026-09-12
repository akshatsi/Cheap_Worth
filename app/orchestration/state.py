"""Shared types for the cascade orchestration graph.

Deliberately separate from app.schemas.models: the graph works with
in-progress attempts that don't have a task_id or a database id yet.
Turning a finished run into persisted Execution/ClassifierPrediction rows
is a storage-layer concern, wired up in a later step, not an orchestration
one — that's also what keeps this module free of any SQLite or API
dependency, so it can be unit tested on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol, TypedDict

from app.schemas.models import Phase, PredictedTier, TaskStatus, Tier


@dataclass
class ClassifyResult:
    predicted_tier: PredictedTier
    raw_response: dict[str, Any]
    latency_ms: float
    cost_usd: float


@dataclass
class ExecuteResult:
    code_output: str
    cost_usd: float
    latency_ms: float


@dataclass
class ValidateResult:
    passed: bool
    detail: dict[str, Any]


@dataclass
class Attempt:
    """One tier's attempt at a task: what it produced and whether it passed."""

    tier: Tier
    code_output: str
    passed: bool
    validation_detail: dict[str, Any]
    cost_usd: float
    latency_ms: float


class ClassifyFn(Protocol):
    def __call__(self, spec: str) -> ClassifyResult: ...


class ExecuteFn(Protocol):
    def __call__(self, tier: Tier, spec: str) -> ExecuteResult: ...


class ValidateFn(Protocol):
    def __call__(self, code_output: str, tests: str) -> ValidateResult: ...


class CascadeState(TypedDict):
    spec: str
    tests: str
    phase: Phase
    current_tier: Tier
    classifier_prediction: Optional[ClassifyResult]
    attempts: list[Attempt]
    status: TaskStatus
    pending_execution: Optional[ExecuteResult]
