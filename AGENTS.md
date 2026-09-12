# AGENTS.md

Guidance for any coding agent working in this repository, regardless of tool.

## Project summary

A routing layer above LLM coding calls. Given a coding task with tests attached, it picks the cheapest Anthropic model tier likely to pass those tests, runs the task, validates the result by executing the code against the supplied tests, and escalates to the next tier only when validation fails. The full reasoning is in `PRD.md`; the design is in `architecture.md`; a condensed checklist is in `architecture_essentials.md`.

## Before making changes

Read `PRD.md` and `architecture.md` first. Both documents record deliberate choices — for example, that tests are required with every task, that validation is deterministic rather than judged by another model, and that escalation moves one tier at a time rather than jumping straight to the top tier. Don't reverse one of these choices without calling it out; assume it was decided on purpose.

## Structure

- `app/api` — FastAPI routes
- `app/orchestration` — the LangGraph graph (classify, execute, validate, decide)
- `app/models` — Anthropic and Groq client wrappers, pricing table
- `app/sandbox` — subprocess runner that executes and times out candidate code
- `app/storage` — SQLite access, one repository per table
- `app/schemas` — shared Pydantic models
- `frontend` — Streamlit app
- `data` — SQLite database file, bootstrap logs
- `scripts` — one-off scripts, including the bootstrap-to-routed cutover check
- `tests` — tests for this project's own code

## Two phases, one codebase

The system runs in a bootstrap phase (classifier bypassed, every task starts at the cheapest tier, staged escalation gathers labeled data) before it switches to a routed phase (classifier picks the starting tier, escalation remains as a fallback). Check `architecture.md` for the cutover condition before assuming the classifier is live.

## Boundaries to respect

- Anthropic is the only model provider in scope for v1. Don't add another provider's client without the user's say-so.
- A task without tests should be rejected, not silently passed through with a weaker check.
- Sandbox execution stays a local subprocess with a timeout and memory limit — don't add container isolation as a "nice to have" without checking that the threat model has actually changed.
- Every added LLM call has a cost, and this project's job is to minimize total LLM cost. Treat a new model call the same way you'd treat a new dependency — justify it.
