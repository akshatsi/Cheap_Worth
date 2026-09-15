# Architecture Essentials

A quick-reference checklist. See [architecture.md](architecture.md) for the full picture and [PRD.md](PRD.md) for why each choice was made.

## Environment variables

- `GROQ_API_KEY`
- `OLLAMA_HOST` (optional, defaults to `http://localhost:11434`)
- `OLLAMA_HAIKU_MODEL`, `OLLAMA_SONNET_MODEL`, `OLLAMA_OPUS_MODEL` (optional — see Models below for defaults)

No Anthropic key needed. The routed tiers run on a local Ollama server, so all that's required there is `ollama serve` running and the models pulled.

## Models

- Ollama tiers, in escalation order, with their defaults: `llama3.2:1b` (Haiku) → `qwen2.5:7b` (Sonnet) → `qwen2.5:14b` (Opus). All are config values, not architectural decisions — override via the env vars above, or `ollama pull` a different model for any tier. The Opus default isn't pulled automatically; run `ollama pull qwen2.5:14b` before that tier is reachable.
- Haiku deliberately isn't a reasoning/"thinking" model. `qwen3:4b` was tried first and dropped: its default thinking mode generated 1,900+ output tokens for a task as simple as `is_prime`, with latency swinging from ~5s to 60s+ task to task — the opposite of what the fastest tier needs. `llama3.2:1b` doesn't have a thinking mode, so its latency actually tracks task size.
- Groq classifier: a small, fast model such as an 8B Llama on Groq — pick one at build time, it is a config value, not an architectural decision.

## Core packages

- `fastapi`, `uvicorn` — API
- `httpx` — calls the local Ollama server's REST API directly (no SDK needed)
- `groq` — the classifier's model client
- `langgraph` — orchestration
- `streamlit` — frontend
- `sqlite3` (standard library) or `sqlalchemy` — storage

## Orchestration graph nodes

1. `classify` — Groq call, skipped during bootstrap
2. `execute` — local Ollama call at the current tier
3. `validate` — run generated code against supplied tests in a subprocess
4. `decide` — pass → done; fail → escalate one tier and loop, or fail the task at Opus

## Storage tables

- `tasks`
- `classifier_predictions`
- `executions`
- `efficiency_ledger`

## Config that must exist before v1 runs

- Groq per-token pricing table (`app/models/pricing.py`) — the classifier's real, metered $ cost
- Ollama per-tier ms-per-output-token table (`app/models/timing.py`) — the routed tiers' currency now that they're local and free; a placeholder estimate, same as any pricing table, refine as real data accumulates
- Subprocess timeout and memory limit for validation runs
- Bootstrap-to-routed cutover rule (how many logged tasks before the classifier takes over the first guess)

## v1 constraints, restated

- Routed tiers run on a local Ollama server; Groq is the only external API still in the loop, for classification
- One task type: coding, submitted as a standalone spec
- No existing codebase, no multi-turn sessions
- Tests are required with every task — no test suite, no run
- Validation runs in a local subprocess, not a container
- The routed tiers' efficiency numbers are wall-clock time (ms), not dollars — see PRD.md's "What this actually optimizes." The Groq classifier keeps a real, separate $ cost.
