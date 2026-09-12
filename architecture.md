# Architecture

## Tech stack

| Layer | Choice | Role |
|---|---|---|
| API | Python + FastAPI | Accepts tasks, returns results and status |
| Routed models | Anthropic (Haiku, Sonnet, Opus) | The three tiers that actually do the coding work |
| Classifier | Groq (a small, fast open-weight model) | Guesses simple vs. complex before any Anthropic call runs |
| Orchestration | LangGraph | The classify → execute → validate → escalate loop, as a graph |
| Frontend | Streamlit | Submit tasks, view a task's tier trace, view running cost savings |
| Storage | SQLite + JSON | SQLite for structured records; JSON columns for raw, shape-varying data such as model responses and test output |

## Two operating phases

**Bootstrap phase.** The classifier is bypassed. Every task starts at Haiku. If validation fails, the task escalates one tier at a time up to Opus. Each run logs which tier finally passed, and that log is the classifier's future training data. This phase runs until there is enough logged data to trust a prediction.

**Routed phase.** The classifier makes the first guess (Haiku or Sonnet) from the task spec. Cascade escalation stays on as the safety net: if the guess was wrong, the task still climbs one tier at a time to the tier that works. Opus is never a direct classifier prediction — only an escalation target.

## Request flow

1. A client submits a task (spec + tests) through the FastAPI endpoint.
2. LangGraph runs the orchestration graph:
   - **Classify** — in the routed phase, calls Groq, predicts simple/complex, and sets the starting tier. In the bootstrap phase, this step is skipped and the starting tier is always Haiku.
   - **Execute** — calls the chosen Anthropic tier with the task spec, gets back code.
   - **Validate** — runs the code against the supplied tests in a local subprocess, under a timeout and resource limit, and returns pass/fail with detail.
   - **Decide** — pass: mark the task done. Fail, with a tier remaining above the current one: escalate to the next tier (Haiku → Sonnet → Opus) and loop back to Execute. Fail at Opus: mark the task failed.
3. Every outcome — tier tried, pass/fail, cost, latency — is written to SQLite.
4. Streamlit reads that storage to show task history, the tier trace per task, and cumulative cost savings against an always-Opus baseline.

## Data model

**tasks**
- `id`, `spec` (text), `tests` (JSON), `status` (pending / done / failed), `created_at`

**classifier_predictions**
- `id`, `task_id`, `predicted_tier` (simple / complex), `raw_response` (JSON), `latency_ms`, `cost_usd`, `phase` (bootstrap / routed)

**executions**
- `id`, `task_id`, `tier` (haiku / sonnet / opus), `code_output` (text), `passed` (bool), `validation_detail` (JSON), `cost_usd`, `latency_ms`, `escalated_from_execution_id` (nullable), `created_at`

**cost_ledger**
- `id`, `task_id`, `total_cost_usd`, `baseline_cost_usd` (cost if the task had gone straight to Opus), `savings_usd`

## Folder map

| Folder | Holds |
|---|---|
| `app/api` | FastAPI routes and request/response wiring |
| `app/orchestration` | The LangGraph graph and its node functions |
| `app/models` | Anthropic and Groq client wrappers, plus the per-tier pricing table |
| `app/sandbox` | The subprocess runner that executes and times out candidate code |
| `app/storage` | SQLite access and repository functions for each table above |
| `app/schemas` | Pydantic models shared across the API, orchestration, and storage layers |
| `frontend` | The Streamlit app |
| `data` | The SQLite database file and any bootstrap logs |
| `scripts` | One-off scripts, such as the bootstrap-to-routed cutover check |
| `tests` | Tests for the autopilot's own code, distinct from the tests submitted inside a task |
