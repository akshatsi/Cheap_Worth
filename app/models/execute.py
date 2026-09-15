"""Ollama client wrapper: calls whichever tier the cascade picked, against
a locally running Ollama server, and returns generated code plus token
counts and latency.

No API key needed — Ollama runs on this machine, with no metered cost.
The three tiers are different local model sizes standing in for
Haiku/Sonnet/Opus, not three paid API tiers, so latency and token counts
are the real signal here, not a dollar figure (see app/models/timing.py
for how they turn into an efficiency estimate). Only touches the network
inside execute() itself — importing this module never requires Ollama to
be running.
"""

from __future__ import annotations

import time

import httpx

from app.config import (
    OLLAMA_HAIKU_MODEL,
    OLLAMA_HOST,
    OLLAMA_OPUS_MODEL,
    OLLAMA_SONNET_MODEL,
)
from app.orchestration.state import ExecuteResult
from app.schemas.models import Tier

MODEL_NAMES: dict[Tier, str] = {
    Tier.HAIKU: OLLAMA_HAIKU_MODEL,
    Tier.SONNET: OLLAMA_SONNET_MODEL,
    Tier.OPUS: OLLAMA_OPUS_MODEL,
}

_PROMPT_TEMPLATE = (
    "Write Python code that satisfies this specification. Respond with "
    "only the code, no explanation, no markdown fences.\n\n{spec}"
)

# Local inference, possibly on CPU, can be slow — generous compared to a
# hosted API's usual timeout.
REQUEST_TIMEOUT_SECONDS = 120


def _strip_markdown_fences(text: str) -> str:
    """Some local models wrap code in a markdown fence despite being told
    not to — left as-is, that's a guaranteed syntax error in the sandbox
    (a false negative on genuinely correct code, not a real failure).
    Strip a leading ``` / ```python line and a trailing ``` line if present."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    lines = lines[1:]  # drop the opening fence (``` or ```python, etc.)
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def execute(tier: Tier, spec: str) -> ExecuteResult:
    """Call the given tier's local Ollama model with a coding task spec."""
    start = time.monotonic()
    response = httpx.post(
        f"{OLLAMA_HOST}/api/chat",
        json={
            "model": MODEL_NAMES[tier],
            "messages": [{"role": "user", "content": _PROMPT_TEMPLATE.format(spec=spec)}],
            "stream": False,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    latency_ms = (time.monotonic() - start) * 1000

    data = response.json()
    code_output = _strip_markdown_fences(data["message"]["content"])
    input_tokens = data.get("prompt_eval_count", 0)
    output_tokens = data.get("eval_count", 0)

    return ExecuteResult(
        code_output=code_output,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
