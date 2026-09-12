"""Anthropic client wrapper: calls whichever tier the cascade picked and
returns generated code plus its cost and latency.

Only touches the network inside execute() itself — importing this module,
or building the cascade graph, never requires ANTHROPIC_API_KEY to be set.
"""

from __future__ import annotations

import time

from anthropic import Anthropic

from app.config import ANTHROPIC_API_KEY, require_keys
from app.models.pricing import estimate_cost_usd
from app.orchestration.state import ExecuteResult
from app.schemas.models import Tier

MODEL_NAMES: dict[Tier, str] = {
    Tier.HAIKU: "claude-haiku-4-5-20251001",
    Tier.SONNET: "claude-sonnet-5",
    Tier.OPUS: "claude-opus-5",
}

_PROMPT_TEMPLATE = (
    "Write Python code that satisfies this specification. Respond with "
    "only the code, no explanation, no markdown fences.\n\n{spec}"
)

_client: Anthropic | None = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        require_keys()
        _client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def execute(tier: Tier, spec: str) -> ExecuteResult:
    """Call the given Anthropic tier with a coding task spec."""
    client = _get_client()
    start = time.monotonic()
    response = client.messages.create(
        model=MODEL_NAMES[tier],
        max_tokens=4096,
        messages=[{"role": "user", "content": _PROMPT_TEMPLATE.format(spec=spec)}],
    )
    latency_ms = (time.monotonic() - start) * 1000

    code_output = "".join(
        block.text for block in response.content if block.type == "text"
    )
    cost_usd = estimate_cost_usd(
        tier,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
    return ExecuteResult(code_output=code_output, cost_usd=cost_usd, latency_ms=latency_ms)
