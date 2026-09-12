"""Per-tier cost table, in USD per token.

The numbers below are placeholders shaped like real published pricing, not
verified figures — check them against Anthropic's and Groq's current pricing
pages before trusting any cost number this system reports. Nothing about the
architecture depends on these exact values; they're a config file, not a
design decision (see architecture_essentials.md).
"""

from __future__ import annotations

from app.schemas.models import Tier

PRICING_USD_PER_TOKEN: dict[Tier, dict[str, float]] = {
    Tier.HAIKU: {"input": 0.0000008, "output": 0.000004},
    Tier.SONNET: {"input": 0.000003, "output": 0.000015},
    Tier.OPUS: {"input": 0.000015, "output": 0.000075},
}

GROQ_CLASSIFIER_PRICING_USD_PER_TOKEN: dict[str, float] = {
    "input": 0.00000005,
    "output": 0.00000008,
}


def estimate_cost_usd(tier: Tier, input_tokens: int, output_tokens: int) -> float:
    """Cost of one Anthropic call at the given tier."""
    rates = PRICING_USD_PER_TOKEN[tier]
    return input_tokens * rates["input"] + output_tokens * rates["output"]


def estimate_classifier_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Cost of one Groq classify call."""
    rates = GROQ_CLASSIFIER_PRICING_USD_PER_TOKEN
    return input_tokens * rates["input"] + output_tokens * rates["output"]


def baseline_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """What this task would have cost if it had gone straight to Opus —
    the comparison point for the savings the PRD's success metric tracks."""
    return estimate_cost_usd(Tier.OPUS, input_tokens, output_tokens)
