# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this project is

A routing layer that sits above LLM coding calls. It picks the cheapest Anthropic model tier likely to solve a given task, runs the task, checks the result by running the code's own tests, and escalates to a pricier tier only on failure. Read [PRD.md](PRD.md) for why, and [architecture.md](architecture.md) for how.

## Ground truth

Treat `PRD.md`, `architecture.md`, and `architecture_essentials.md` as the source of truth for scope and design. If a change would contradict one of them, flag the conflict rather than quietly picking a side.

## Working here

- Python throughout. Match the folder map in `architecture.md` — orchestration logic goes in `app/orchestration`, model clients in `app/models`, and so on. Don't blur those boundaries for convenience.
- The project is currently in the bootstrap phase by design (see `architecture.md`): the classifier is meant to be bypassed until enough logged task outcomes exist. Don't wire the classifier into the routing decision as a default without that data existing first.
- `app/sandbox` runs model-generated code on the local machine. Any change there must keep a timeout and a resource limit in place — that subprocess is running code an LLM just wrote, not code a person reviewed.
- This project's entire point is spending less on model calls. When touching orchestration or model-client code, notice if a change adds an LLM call that wasn't there before, and say so — an extra call anywhere in this codebase works against the project's own goal.
- Tests submitted inside a task (used to validate generated code) are not the same thing as this project's own test suite in `tests/`. Don't conflate the two.

## Running it

- API: `uvicorn app.api.main:app --reload` (once `app/api/main.py` exists)
- Frontend: `streamlit run frontend/app.py` (once that file exists)
- The SQLite file lives under `data/`

## Secrets

`ANTHROPIC_API_KEY` and `GROQ_API_KEY` are required. Never hardcode either; never log a raw key or a full request payload that might contain one.
