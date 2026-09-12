# Architecture Essentials

A quick-reference checklist. See [architecture.md](architecture.md) for the full picture and [PRD.md](PRD.md) for why each choice was made.

## Environment variables

- `ANTHROPIC_API_KEY`
- `GROQ_API_KEY`

## Models

- Anthropic tiers, in escalation order: `claude-haiku-4-5-20251001` → `claude-sonnet-5` → `claude-opus-5`
- Groq classifier: a small, fast model such as an 8B Llama on Groq — pick one at build time, it is a config value, not an architectural decision

## Core packages

- `fastapi`, `uvicorn` — API
- `anthropic`, `groq` — model clients
- `langgraph` — orchestration
- `streamlit` — frontend
- `sqlite3` (standard library) or `sqlalchemy` — storage

## Orchestration graph nodes

1. `classify` — Groq call, skipped during bootstrap
2. `execute` — Anthropic call at the current tier
3. `validate` — run generated code against supplied tests in a subprocess
4. `decide` — pass → done; fail → escalate one tier and loop, or fail the task at Opus

## Storage tables

- `tasks`
- `classifier_predictions`
- `executions`
- `cost_ledger`

## Config that must exist before v1 runs

- Per-tier pricing table (input/output cost per token, for Haiku, Sonnet, Opus, and the Groq classifier model)
- Subprocess timeout and memory limit for validation runs
- Bootstrap-to-routed cutover rule (how many logged tasks before the classifier takes over the first guess)

## v1 constraints, restated

- Anthropic only, no other model providers
- One task type: coding, submitted as a standalone spec
- No existing codebase, no multi-turn sessions
- Tests are required with every task — no test suite, no run
- Validation runs in a local subprocess, not a container
