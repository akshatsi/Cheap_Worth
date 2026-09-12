"""Groq client wrapper: the classify step's simple/complex prediction.

Kept as a real external call rather than something the caller judges for
itself, on purpose — a fixed classifier model gives a stable, reproducible
signal to calibrate the bootstrap-to-routed cutover against. Only touches
the network inside classify() itself.
"""

from __future__ import annotations

import time

from groq import Groq

from app.config import GROQ_API_KEY, GROQ_CLASSIFIER_MODEL, require_keys
from app.models.pricing import estimate_classifier_cost_usd
from app.orchestration.state import ClassifyResult
from app.schemas.models import PredictedTier

_CLASSIFY_PROMPT = (
    'You are judging the difficulty of a coding task. Reply with exactly '
    'one word: "simple" if a small, fast model could solve it correctly, '
    'or "complex" if it likely needs a stronger model.\n\nTask:\n{spec}'
)

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        require_keys()
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def classify(spec: str) -> ClassifyResult:
    """Ask the Groq classifier whether a task is simple or complex."""
    client = _get_client()
    start = time.monotonic()
    response = client.chat.completions.create(
        model=GROQ_CLASSIFIER_MODEL,
        max_tokens=5,
        messages=[{"role": "user", "content": _CLASSIFY_PROMPT.format(spec=spec)}],
    )
    latency_ms = (time.monotonic() - start) * 1000

    raw_text = response.choices[0].message.content.strip().lower()
    predicted_tier = (
        PredictedTier.COMPLEX if "complex" in raw_text else PredictedTier.SIMPLE
    )
    cost_usd = estimate_classifier_cost_usd(
        input_tokens=response.usage.prompt_tokens,
        output_tokens=response.usage.completion_tokens,
    )
    return ClassifyResult(
        predicted_tier=predicted_tier,
        raw_response={"text": raw_text},
        latency_ms=latency_ms,
        cost_usd=cost_usd,
    )
