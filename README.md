# Cheap_Worth: LLM Cost Autopilot

A routing layer for coding tasks. It starts each task on the smallest local model, runs the result against the task's own tests, and moves to a bigger model only when the tests fail.

Most tools send every task to one fixed model, usually the strongest one, because nobody wants to guess wrong on a hard task. That makes a one-line function cost as much time as a hard bug fix. Cheap_Worth aims to spend the least total time across a batch of tasks while still getting each one done.

This is a personal tool built around one person's workflow, not a product for other people.

## How it works

A client sends a task: a spec and the tests that prove it works. The task then runs through four steps:

1. **Classify.** A small model on Groq guesses whether the task is simple or complex, which sets the starting tier. This step is skipped in the bootstrap phase (see below).
2. **Execute.** The chosen tier's local Ollama model writes the code.
3. **Validate.** The code runs against the supplied tests in a subprocess, with a timeout and a memory limit. Pass or fail is the only judge. No model grades another model's work.
4. **Decide.** On a pass, the task is done. On a fail, the task moves up one tier and runs again. A fail at the top tier marks the task failed.

Every attempt (tier, pass or fail, time taken) is saved to SQLite.

### Tiers

The tiers use Claude's names for their rank, but all three run on a local Ollama server. No API key and no per-call cost.

| Tier | Default model | Role |
|---|---|---|
| Haiku | `llama3.2:1b` | First try for every task in bootstrap |
| Sonnet | `qwen2.5:7b` | First escalation |
| Opus | `qwen2.5:14b` | Last resort. Never a direct classifier pick |

All three are settings. Change them with the environment variables below.

The Haiku tier is a model without a "thinking" mode on purpose. `qwen3:4b` was tried first and dropped: it produced over 1,900 output tokens for a task as simple as `is_prime`, and its speed swung from about 5 seconds to over a minute.

### Two phases

- **Bootstrap.** The classifier is off. Every task starts at Haiku and climbs on failure. Each run records which tier finally passed. That record is the classifier's future training data.
- **Routed.** The classifier picks the starting tier (Haiku or Sonnet). Escalation stays on in case the guess was wrong.

The API runs in bootstrap today. The phase is a constant in `app/api/main.py`. A script checks when there is enough data to switch (see [Check if you can switch phases](#check-if-you-can-switch-phases)).

## What it measures: time, not dollars

The project began by counting dollars. Once the tiers moved to local Ollama, every tier cost $0, so there was nothing left to compare. What differs between tiers is wall-clock time: a 1B model answers in about a second, and a 14B model takes many times longer.

So the success metric is total time across a batch of tasks, compared against an estimate of running every task on the top tier. The estimate lives in `app/models/timing.py` and is a placeholder until there are more real measurements.

The Groq classifier call is the only metered call left. Its dollar cost is tracked on its own and is not part of the time comparison.

## Stack

| Layer | Choice |
|---|---|
| API | Python, FastAPI |
| Models | Local Ollama (three tiers), Groq (classifier) |
| Orchestration | LangGraph |
| Frontend | Streamlit |
| Storage | SQLite, with JSON columns for raw model output and test results |

## Project layout

```text
app/
  api/            FastAPI routes
  models/         Ollama and Groq clients, pricing and timing tables
  orchestration/  The LangGraph cascade (classify, execute, validate, decide)
  sandbox/        Subprocess runner that executes and times out generated code
  schemas/        Pydantic models shared across layers
  storage/        SQLite tables and repository functions
frontend/         Streamlit app and its HTTP client
scripts/          One-off scripts, such as the phase cutover check
tests/            Tests, plus 16 sample tasks in tests/fixtures/sample_tasks
```

More detail is in [PRD.md](PRD.md), [architecture.md](architecture.md) and [architecture_essentials.md](architecture_essentials.md).

## Setup

You need Python 3 and [Ollama](https://ollama.com).

```bash
git clone https://github.com/akshatsi/Cheap_Worth.git
cd Cheap_Worth
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Pull the three models:

```bash
ollama pull llama3.2:1b
ollama pull qwen2.5:7b
ollama pull qwen2.5:14b
```

### Settings

Set these in `.env`. All are optional while the API runs in bootstrap.

| Variable | Default | Use |
|---|---|---|
| `GROQ_API_KEY` | none | Needed only for the routed phase |
| `GROQ_CLASSIFIER_MODEL` | `llama-3.1-8b-instant` | Model that guesses simple or complex |
| `OLLAMA_HOST` | `http://localhost:11434` | Address of your Ollama server |
| `OLLAMA_HAIKU_MODEL` | `llama3.2:1b` | First tier |
| `OLLAMA_SONNET_MODEL` | `qwen2.5:7b` | Second tier |
| `OLLAMA_OPUS_MODEL` | `qwen2.5:14b` | Top tier |

## Run

Start each of these in its own terminal:

```bash
ollama serve
```

```bash
uvicorn app.api.main:app
```

```bash
streamlit run frontend/app.py
```

The frontend lets you submit a task, browse past tasks with the tier trace for each, and see the time saved. It expects the API at `http://localhost:8000`. Set `API_BASE_URL` to change that.

### Use the API directly

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "spec": "Write a function `add(a, b)` that returns the sum of two numbers.",
    "tests": "def test_add():\n    assert add(2, 3) == 5\n"
  }'
```

| Route | Returns |
|---|---|
| `POST /tasks` | Runs the task and returns its result and tier trace |
| `GET /tasks` | All past tasks |
| `GET /tasks/{id}` | One task with every attempt |
| `GET /efficiency-summary` | Total time against the top-tier estimate |

A task needs tests. Without a test suite there is nothing to run, so there is no result.

### Check if you can switch phases

```bash
python -m scripts.cutover
```

It reads the logged bootstrap runs and reports whether there are enough tasks, with real examples of both easy and hard ones. The defaults are 20 tasks, with at least 5 of each kind. A classifier trained only on easy tasks has nothing to tell apart.

## Tests

```bash
pytest
```

The tests use fake model calls, so they need no Ollama server and no API keys. They cover the cascade logic, the sandbox, storage, the API and the frontend client. The 16 sample tasks in `tests/fixtures/sample_tasks` run through the real API and sandbox with correct reference solutions standing in for the model.

## Limits

- Coding tasks only, sent as a standalone spec with tests. No existing codebase and no multi-turn sessions.
- The sandbox is a subprocess with a timeout and a memory limit. It stops a runaway process. It does not protect you from hostile code.
- A request runs the whole cascade before it returns, and it handles one task at a time.
- The time estimates for each tier are placeholders.

## What came next

The routing idea continued in [LLM-Cost-Autopilot](https://github.com/akshatsi/LLM-Cost-Autopilot), a fork of Aider that picks a model for each message in a live coding session.
