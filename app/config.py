"""Environment and secrets loading. See .env.example for the variables this reads."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# The Groq model used for the classify step. A config value, not an
# architectural decision — swap it here if a better fast/cheap option shows up.
GROQ_CLASSIFIER_MODEL = os.environ.get("GROQ_CLASSIFIER_MODEL", "llama-3.1-8b-instant")

# The tiers do the actual coding work on a local Ollama server instead of
# Anthropic's API — no key needed, no metered cost, everything runs on this
# machine. Defaults below match what's already pulled locally; override any
# of them, or `ollama pull` a bigger model for the Opus tier, which isn't
# pulled by default.
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_HAIKU_MODEL = os.environ.get("OLLAMA_HAIKU_MODEL", "qwen3:4b")
OLLAMA_SONNET_MODEL = os.environ.get("OLLAMA_SONNET_MODEL", "qwen2.5:7b")
OLLAMA_OPUS_MODEL = os.environ.get("OLLAMA_OPUS_MODEL", "qwen2.5:14b")


def require_keys() -> None:
    """Raise with a clear message if a required key is missing, instead of
    failing deep inside a client call. Only the classify step needs a real
    key now — the execute step's Ollama calls need nothing but a running
    local server."""
    if not GROQ_API_KEY:
        raise RuntimeError(
            "Missing required environment variable: GROQ_API_KEY. "
            "Copy .env.example to .env and fill it in."
        )
