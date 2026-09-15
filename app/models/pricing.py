"""Per-tier cost table, in USD per token.

The routed tiers (Haiku/Sonnet/Opus) run on a local Ollama server now, not
Anthropic's API — see app/models/execute.py — so their per-token cost is
genuinely $0, not an approximation. Kept as a per-token table rather than
a flat constant so the shape stays compatible if a paid provider comes
back later; total_cost_usd and savings_usd will read $0 for the routed
tiers while everything runs locally, which is expected, not a bug.

The Groq classifier is still a real metered API call — those numbers are
placeholders shaped like real published pricing, not verified figures;
check them against Groq's current pricing page before trusting that part
of any cost number this system reports.
"""

from __future__ import annotations

from app.schemas.models import Tier

PRICING_USD_PER_TOKEN: dict[Tier, dict[str, float]] = {
    Tier.HAIKU: {"input": 0.0, "output": 0.0},
    Tier.SONNET: {"input": 0.0, "output": 0.0},
    Tier.OPUS: {"input": 0.0, "output": 0.0},
}

GROQ_CLASSIFIER_PRICING_USD_PER_TOKEN: dict[str, float] = {
    "input": 0.00000005,
    "output": 0.00000008,
}


def estimate_cost_usd(tier: Tier, input_tokens: int, output_tokens: int) -> float:
    """Cost of one local Ollama call at the given tier — always $0."""
    rates = PRICING_USD_PER_TOKEN[tier]
    return input_tokens * rates["input"] + output_tokens * rates["output"]


def estimate_classifier_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Cost of one Groq classify call."""
    rates = GROQ_CLASSIFIER_PRICING_USD_PER_TOKEN
    return input_tokens * rates["input"] + output_tokens * rates["output"]


def baseline_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """What this task would have cost if it had gone straight to Opus —
    the comparison point for the savings the PRD's success metric tracks.
    Also $0 while Opus is a local model; this stops being a meaningful
    savings figure until a paid tier is back in the mix."""
    return estimate_cost_usd(Tier.OPUS, input_tokens, output_tokens)
