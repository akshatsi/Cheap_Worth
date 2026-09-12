"""Environment and secrets loading. See .env.example for the variables this reads."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# The Groq model used for the classify step. A config value, not an
# architectural decision — swap it here if a better fast/cheap option shows up.
GROQ_CLASSIFIER_MODEL = os.environ.get("GROQ_CLASSIFIER_MODEL", "llama-3.1-8b-instant")


def require_keys() -> None:
    """Raise with a clear message if a required key is missing, instead of
    failing deep inside a client call."""
    missing = [
        name
        for name, value in [
            ("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY),
            ("GROQ_API_KEY", GROQ_API_KEY),
        ]
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Copy .env.example to .env and fill them in."
        )
