# Implementation Plan

Three people, one codebase. This plan splits the work into a short shared foundation, three tracks that can run at the same time without blocking each other, then an integration pass. Track names are roles, not people — assign them however fits.

## Sequencing at a glance

| Phase | What | Who | Rough length |
|---|---|---|---|
| 0 | Foundations — shared contracts everyone codes against | All three, together | 2–3 days |
| 1 | Three parallel build tracks | One person per track | 1–2 weeks |
| 2 | Wire the tracks together | All three | 2–3 days |
| 3 | Run the bootstrap phase, collect real data | All three, passive | Until the cutover threshold is hit |
| 4 | Turn the classifier on, watch it, polish | All three | Ongoing |

The order matters more than the day count. Don't start Phase 1 before Phase 0 is settled — every track in Phase 1 codes against the schemas and table definitions Phase 0 produces, and redoing those mid-flight costs far more than a few extra days up front.

## Phase 0 — Foundations

Everyone works on this together; nobody starts their own track until it's done.

1. **Shared schemas** (`app/schemas`) — Pydantic models for `TaskSubmission` (spec + tests), `Execution`, `ClassifierPrediction`, `CostLedgerEntry`. These are the contract every track below writes against, so get agreement here before anyone writes track code.
2. **SQLite table definitions** (`app/storage`) — the four tables from `architecture.md`: `tasks`, `classifier_predictions`, `executions`, `cost_ledger`. Write the `CREATE TABLE` statements and a small migration/init script.
3. **Config and secrets loading** — where `ANTHROPIC_API_KEY` and `GROQ_API_KEY` come from (a `.env` file, loaded once, never committed), plus a `.env.example` with placeholder values.
4. **Pricing table format** — a config file (JSON or Python dict) with cost-per-input-token and cost-per-output-token for Haiku, Sonnet, Opus, and the chosen Groq model. Doesn't need real numbers finalized yet, just the shape.
5. **A shared sample-task set** — 5–10 small coding tasks (spec + tests), spanning obviously-easy to obviously-hard. Every track needs something to run against during development, and using the same set means bugs found by one person are reproducible by the others.

Output of this phase: schemas, table definitions, config loading, and sample tasks all merged to `main` before Phase 1 starts.

## Phase 1 — Three tracks

### Track A — Model clients and orchestration

The routing brain: the part that decides which model runs and when to escalate.

- Anthropic client wrapper (`app/models`) — one function per tier that takes a task spec, returns generated code plus token counts and computed cost.
- Groq client wrapper (`app/models`) — calls the classifier model, returns a simple/complex prediction, raw response, latency, and cost.
- LangGraph graph (`app/orchestration`) — four nodes: `classify`, `execute`, `validate`, `decide`.
  - `classify` must support a bootstrap-bypass mode (always predict nothing, starting tier is always Haiku) and a routed mode (call Groq, predict a starting tier).
  - `decide` implements one-tier-at-a-time escalation: Haiku → Sonnet → Opus, stop and mark the task failed if Opus fails.
- Unit tests for the graph's control flow using mocked model and validator calls — no real API spend needed to verify the escalation logic is correct. This is the track where a wrong test is expensive to discover late, since every other track depends on this behavior being right.

**Depends on:** Phase 0 schemas. **Blocks:** the `execute`/`decide` calls Track B's API needs to invoke, and the validation result Track B's sandbox produces.

### Track B — Sandbox, storage, and API

The part that runs the world's code and remembers what happened.

- Sandbox runner (`app/sandbox`) — takes generated code and a set of tests, runs them in a subprocess with a timeout and memory limit, returns pass/fail plus stdout/stderr detail. Handle syntax errors and crashes as a plain fail, not an exception that kills the request.
- Storage repositories (`app/storage`) — insert/read functions for all four tables, built against Phase 0's table definitions.
- FastAPI endpoints (`app/api`):
  - `POST /tasks` — submit a spec + tests, kick off the orchestration graph.
  - `GET /tasks/{id}` — status and full tier trace for one task.
  - `GET /tasks` — history, for the frontend to list.
  - `GET /cost-summary` — aggregate spend vs. an always-Opus baseline.
- Wire the API to call Track A's graph and persist results through the storage repositories.

**Depends on:** Phase 0 table definitions and schemas. Can build the sandbox and storage layers independently of Track A, then wire the API to Track A's graph once both sides exist — until then, stub the graph call with a fake that returns canned pass/fail so the API and storage layers can be finished and tested on their own.

### Track C — Frontend, bootstrap tooling, and test harness

The part a human actually looks at, plus the machinery for the cold-start problem described in the PRD.

- Streamlit app (`frontend`) — a form to submit a task, a history view showing each task's tier trace and pass/fail, and a running cost-savings number against the always-Opus baseline.
- Bootstrap-to-routed cutover script (`scripts`) — reads the logged `executions`/`classifier_predictions` data, checks it against a cutover rule (for example, "at least N tasks logged with a clear tier split"), and reports whether the system is ready to flip from bootstrap to routed mode.
- Expanded sample-task library — grow Phase 0's 5–10 tasks into 15–20, covering a real spread of difficulty, for use as the initial bootstrap batch and as a standing regression check later.
- Project test suite (`tests`) — end-to-end tests that submit a sample task through the whole pipeline and check it lands correctly in storage. These can run against Track A's mocked graph early, then against the real thing once Phase 2 wires everything together.

**Depends on:** Phase 0's sample tasks and schemas. Can build the Streamlit UI against fake/mocked API responses before Track B's real endpoints exist.

## Phase 2 — Integration

All three together:

1. Point Track B's API at Track A's real graph (remove the stub).
2. Point Track C's Streamlit app at Track B's real API (remove the mocked responses).
3. Run the full sample-task library from Track C through the real pipeline in bootstrap mode.
4. Fix the seams: schema mismatches, sandbox timeout edge cases, cost numbers that don't add up.

Definition of done for this phase: every sample task runs end to end, and the numbers on the Streamlit cost dashboard match what the SQLite tables actually hold.

## Phase 3 — Bootstrap run

Passive, ongoing. Submit real coding tasks through the system day to day. Every task runs the full staged cascade and logs which tier actually worked. Watch the cutover script from Track C; once it says there's enough data, move to Phase 4.

## Phase 4 — Routed phase and polish

1. Flip the system to routed mode: the classifier makes the first guess instead of always starting at Haiku.
2. Watch the escalation rate closely for the first batch of routed tasks — a high rate means the classifier's guesses are often wrong, and it's worth checking why before trusting it further.
3. Revisit the non-goals list in the PRD to confirm nothing crept into scope during the build.

## Cross-cutting notes

- **Git workflow** — one branch per track during Phase 1, merged to `main` only after the other two have looked at it. Since all three tracks touch shared schemas from Phase 0, a change to those schemas after Phase 1 starts needs a heads-up to the other two before merging.
- **Secrets** — neither API key ever gets committed. `.env` stays out of git; `.env.example` holds the placeholders.
- **Cost awareness during development** — Track A's unit tests and Track C's early frontend work should run against mocked model calls, not real Anthropic/Groq calls, so building the system doesn't itself run up a bill before it's finished.
