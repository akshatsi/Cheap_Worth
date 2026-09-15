"""Per-token cost for the Groq classifier call — the one piece of this
system with genuine metered cost, now that the routed tiers run on a
local Ollama server (see app/models/timing.py for their currency: time,
not dollars).

The numbers below are placeholders shaped like real published pricing,
not verified figures — check them against Groq's current pricing page
before trusting any cost number this system reports for the classifier.
"""

from __future__ import annotations

GROQ_CLASSIFIER_PRICING_USD_PER_TOKEN: dict[str, float] = {
    "input": 0.00000005,
    "output": 0.00000008,
}


def estimate_classifier_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Cost of one Groq classify call."""
    rates = GROQ_CLASSIFIER_PRICING_USD_PER_TOKEN
    return input_tokens * rates["input"] + output_tokens * rates["output"]
