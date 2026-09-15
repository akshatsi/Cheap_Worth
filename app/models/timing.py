"""Estimated wall-clock cost of local Ollama inference, in milliseconds
per output token, by tier.

Unlike the Groq pricing table, there's no published rate to check these
against — a local model's speed depends on this machine's hardware, not
a provider's price sheet. The Haiku figure is a real measurement (see
below); Sonnet and Opus are rough estimates pending more real runs.
Recalibrate as actual data accumulates rather than trusting these
indefinitely — same spirit as the pricing table's own placeholder caveat,
just for a number nobody publishes for you.
"""

from __future__ import annotations

from app.schemas.models import Tier

MS_PER_OUTPUT_TOKEN: dict[Tier, float] = {
    # llama3.2:1b — measured directly: the is_prime task ran in 830ms for
    # 57 output tokens (~14.6ms/token) on this machine.
    Tier.HAIKU: 15.0,
    # qwen2.5:7b — not measured per-token yet; a rough multiple of Haiku's
    # rate based on relative model size, pending a real measurement.
    Tier.SONNET: 90.0,
    # qwen2.5:14b — pure estimate; hasn't run a real task yet in this
    # project (nothing in the Step 6 batch escalated this far).
    Tier.OPUS: 180.0,
}


def estimate_baseline_time_ms(output_tokens: int) -> float:
    """What this task's execution would likely have cost in wall-clock
    time if it had gone straight to Opus — the comparison point for
    PRD.md's success metric. Uses the same approximation the old $-based
    baseline used: the actual tier's output token count, priced (timed)
    at Opus's rate, on the assumption token counts are roughly stable
    across tiers for the same task."""
    return output_tokens * MS_PER_OUTPUT_TOKEN[Tier.OPUS]
