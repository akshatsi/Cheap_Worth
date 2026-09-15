# Implementation Plan

Solo build. No tracks to parallelize — just a build order that avoids backtracking: each step below produces something the next step needs, so working out of order means redoing work.

Steps 1–6 below are a build log and use the plan's original dollar-cost framing (`CostLedgerEntry`, `cost_ledger`, `/cost-summary`) — accurate at the time each step was built. After Step 6, the routed tiers moved fully to a local Ollama server, and the currency being tracked changed from dollars to wall-clock time: `CostLedgerEntry` → `EfficiencyLedgerEntry`, `cost_ledger` → `efficiency_ledger`, `/cost-summary` → `/efficiency-summary`. See PRD.md's "What this actually optimizes" for why. Code and docs outside this file reflect the current names; this file is left as a historical record rather than rewritten.

## Sequencing at a glance

| Step | What | Rough length |
|---|---|---|
| 1 | Foundations — schemas, tables, config, sample tasks | 1 day |
| 2 | Model clients and orchestration (the routing brain) | 3–4 days |
| 3 | Sandbox and storage (runs code, remembers outcomes) | 2–3 days |
| 4 | API | 1–2 days |
| 5 | Frontend | 1–2 days |
| 6 | Integration pass | 1–2 days |
| 7 | Bootstrap run | Until the cutover threshold is hit |
| 8 | Routed phase and polish | Ongoing |

Total hands-on build: roughly 1.5–2 weeks. Step 7 is elapsed time waiting on real usage, not more building — the classifier isn't trustworthy until it has data, and that only comes from actually running tasks through it.

## Step 1 — Foundations

1. **Schemas** (`app/schemas`) — Pydantic models for `TaskSubmission` (spec + tests), `Execution`, `ClassifierPrediction`, `CostLedgerEntry`. Every later step writes against these, so get the shape right before building on top of it.
2. **SQLite table definitions** (`app/storage`) — the four tables from `architecture.md`: `tasks`, `classifier_predictions`, `executions`, `cost_ledger`. Write the `CREATE TABLE` statements and a small init script.
3. **Config and secrets loading** — where `ANTHROPIC_API_KEY` and `GROQ_API_KEY` come from (a `.env` file, loaded once, never committed), plus a `.env.example` with placeholder values.
4. **Pricing table format** — a config file (JSON or Python dict) with cost-per-input-token and cost-per-output-token for Haiku, Sonnet, Opus, and the chosen Groq model. Doesn't need real numbers finalized yet, just the shape.
5. **A sample-task set** — 5–10 small coding tasks (spec + tests), spanning obviously-easy to obviously-hard. Something concrete to run against for every step from here on.

## Step 2 — Model clients and orchestration

The part that decides which model runs and when to escalate.

- Anthropic client wrapper (`app/models`) — one function per tier that takes a task spec, returns generated code plus token counts and computed cost.
- Groq client wrapper (`app/models`) — calls the classifier model, returns a simple/complex prediction, raw response, latency, and cost.
- LangGraph graph (`app/orchestration`) — four nodes: `classify`, `execute`, `validate`, `decide`.
  - `classify` must support a bootstrap-bypass mode (always predict nothing, starting tier is always Haiku) and a routed mode (call Groq, predict a starting tier).
  - `decide` implements one-tier-at-a-time escalation: Haiku → Sonnet → Opus, stop and mark the task failed if Opus fails.
- Unit tests for the graph's control flow using mocked model and validator calls — no real API spend needed to verify the escalation logic is correct, and this logic is expensive to get wrong later since everything else builds on it.

## Step 3 — Sandbox and storage

The part that runs the generated code and remembers what happened.

- Sandbox runner (`app/sandbox`) — takes generated code and a set of tests, runs them in a subprocess with a timeout and memory limit, returns pass/fail plus stdout/stderr detail. Handle syntax errors and crashes as a plain fail, not an exception that kills the request.
- Storage repositories (`app/storage`) — insert/read functions for all four tables, built against Step 1's table definitions.
- Wire the sandbox's validation result and Step 2's orchestration graph together — `validate` calls the sandbox runner, `decide` reads its result.

## Step 4 — API

- FastAPI endpoints (`app/api`):
  - `POST /tasks` — submit a spec + tests, kick off the orchestration graph.
  - `GET /tasks/{id}` — status and full tier trace for one task.
  - `GET /tasks` — history, for the frontend to list.
  - `GET /cost-summary` — aggregate spend vs. an always-Opus baseline.
- Wire the API to call the orchestration graph and persist results through the storage repositories.

## Step 5 — Frontend

- Streamlit app (`frontend`) — a form to submit a task, a history view showing each task's tier trace and pass/fail, and a running cost-savings number against the always-Opus baseline.
- Bootstrap-to-routed cutover script (`scripts`) — reads the logged `executions`/`classifier_predictions` data, checks it against a cutover rule (for example, "at least N tasks logged with a clear tier split"), and reports whether the system is ready to flip from bootstrap to routed mode.
- Expand the sample-task set from Step 1 to 15–20 tasks, covering a real spread of difficulty — the initial bootstrap batch, and a standing regression check afterward.

## Step 6 — Integration pass

1. Run the expanded sample-task set through the full pipeline in bootstrap mode, end to end through the real API and frontend.
2. Fix the seams: schema mismatches, sandbox timeout edge cases, cost numbers that don't add up.
3. Project test suite (`tests`) — end-to-end tests that submit a sample task through the whole pipeline and check it lands correctly in storage.

Definition of done: every sample task runs end to end, and the numbers on the Streamlit cost dashboard match what the SQLite tables actually hold.

## Step 7 — Bootstrap run

Passive, ongoing. Submit real coding tasks through the system day to day. Every task runs the full staged cascade and logs which tier actually worked. Check the cutover script periodically; once it says there's enough data, move to Step 8.

## Step 8 — Routed phase and polish

1. Flip the system to routed mode: the classifier makes the first guess instead of always starting at Haiku.
2. Watch the escalation rate closely for the first batch of routed tasks — a high rate means the classifier's guesses are often wrong, and it's worth checking why before trusting it further.
3. Revisit the non-goals list in the PRD to confirm nothing crept into scope during the build.

## Cross-cutting notes

- **Secrets** — neither API key ever gets committed. `.env` stays out of git; `.env.example` holds the placeholders.
- **Cost awareness during development** — unit tests and early frontend work should run against mocked model calls, not real Anthropic/Groq calls, so building the system doesn't itself run up a bill before it's finished.
