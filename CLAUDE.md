# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this project is

A routing layer that sits above LLM coding calls. It picks the smallest capable model tier for a given task, runs the task, checks the result by running the code's own tests, and escalates to a stronger tier only on failure. The routed tiers run on a local Ollama server; the classifier is a separate Groq call. Read [PRD.md](PRD.md) for why, and [architecture.md](architecture.md) for how.

## Ground truth

Treat `PRD.md`, `architecture.md`, and `architecture_essentials.md` as the source of truth for scope and design. If a change would contradict one of them, flag the conflict rather than quietly picking a side.

## Working here

- Python throughout. Match the folder map in `architecture.md` — orchestration logic goes in `app/orchestration`, model clients in `app/models`, and so on. Don't blur those boundaries for convenience.
- The project is currently in the bootstrap phase by design (see `architecture.md`): the classifier is meant to be bypassed until enough logged task outcomes exist. Don't wire the classifier into the routing decision as a default without that data existing first.
- `app/sandbox` runs model-generated code on the local machine. Any change there must keep a timeout and a resource limit in place — that subprocess is running code an LLM just wrote, not code a person reviewed.
- The routed tiers (`app/models/execute.py`) call a local Ollama server, not a paid API — no key, no metered cost. This project tracks **time**, not dollars, for those tiers (`app/models/timing.py`, `efficiency_ledger`) — don't reintroduce a `cost_usd` field on `Execution`/`Attempt` for them without a real reason to. The classifier (`app/models/classify.py`) is still a real, metered Groq call and keeps its own `cost_usd`, untouched by this. When touching orchestration or model-client code, notice if a change adds a call that wasn't there before, and say so — this project's whole point is minimizing wasted work, whichever currency that's measured in.
- Tests submitted inside a task (used to validate generated code) are not the same thing as this project's own test suite in `tests/`. Don't conflate the two.

## Running it

- API: `uvicorn app.api.main:app --reload`
- Frontend: `streamlit run frontend/app.py`
- Tests: `pytest tests/`
- The SQLite file lives under `data/`
- Ollama must be running locally (`ollama serve`) with the tier models pulled — see `architecture_essentials.md` for the default model names and how to override them

## Secrets

`GROQ_API_KEY` is required for the classifier. Never hardcode it; never log a raw key or a full request payload that might contain one. Ollama needs no key.
