"""Streamlit frontend: submit a task, browse history, watch cost savings.

Talks to the FastAPI backend over HTTP — run `uvicorn app.api.main:app`
in a separate terminal first (and `ollama serve`, for the routed tiers to
actually respond). Override the backend's address with API_BASE_URL if
it's not on localhost:8000.
"""

from __future__ import annotations

import httpx
import streamlit as st

from frontend.api_client import get_cost_summary, get_task, list_tasks, submit_task


def render_task_detail(detail: dict) -> None:
    """The tier trace for one task: what was tried, in what order, at
    what cost — the routing transparency the whole project is built
    around (see PRD.md)."""
    task = detail["task"]
    st.caption(f"Status: **{task['status']}** · submitted {task['created_at']}")
    with st.expander("Spec", expanded=False):
        st.write(task["spec"])

    predictions = detail.get("classifier_predictions") or []
    if predictions:
        prediction = predictions[0]
        st.write(
            f"Classifier predicted **{prediction['predicted_tier']}** "
            f"(phase: {prediction['phase']}, cost ${prediction['cost_usd']:.6f})"
        )
    else:
        st.write("Classifier bypassed — bootstrap phase, started straight at Haiku.")

    st.write("**Tier trace:**")
    for execution in detail["executions"]:
        icon = "✅" if execution["passed"] else "❌"
        st.markdown(
            f"{icon} `{execution['tier']}` — ${execution['cost_usd']:.6f}, "
            f"{execution['latency_ms']:.0f} ms"
        )
        with st.expander(f"Code + validation detail ({execution['tier']})", expanded=False):
            st.code(execution["code_output"], language="python")
            st.json(execution["validation_detail"])

    ledger = detail.get("cost_ledger")
    if ledger:
        cols = st.columns(3)
        cols[0].metric("Total cost", f"${ledger['total_cost_usd']:.6f}")
        cols[1].metric("Baseline (always Opus)", f"${ledger['baseline_cost_usd']:.6f}")
        cols[2].metric("Savings", f"${ledger['savings_usd']:.6f}")


st.set_page_config(page_title="LLM Cost Autopilot", layout="wide")
st.title("LLM Cost Autopilot")

tab_submit, tab_history, tab_cost = st.tabs(["Submit a task", "History", "Cost savings"])

with tab_submit:
    st.subheader("Submit a coding task")
    st.caption(
        "A self-contained spec plus its own tests — see architecture.md's "
        "standalone-mode scope. No existing codebase support yet."
    )
    spec = st.text_area(
        "Spec",
        height=150,
        placeholder="Write a function `add(a, b)` that returns the sum of two integers.",
    )
    tests = st.text_area(
        "Tests (pytest-style)",
        height=150,
        placeholder="def test_add():\n    assert add(2, 3) == 5",
    )

    if st.button("Run", type="primary"):
        if not spec.strip() or not tests.strip():
            st.error("Both spec and tests are required — standalone tasks without tests are rejected.")
        else:
            with st.spinner("Running the cascade — this can take a while on local models..."):
                try:
                    detail = submit_task(spec, tests)
                except httpx.HTTPError as exc:
                    st.error(f"Request failed: {exc}")
                else:
                    st.success(f"Task #{detail['task']['id']}: {detail['task']['status']}")
                    render_task_detail(detail)

with tab_history:
    st.subheader("Task history")
    try:
        tasks = list_tasks()
    except httpx.HTTPError as exc:
        st.error(f"Could not load history: {exc}")
        tasks = []

    if not tasks:
        st.info("No tasks yet — submit one on the first tab.")

    for task in reversed(tasks):
        with st.expander(f"#{task['id']} — {task['status']} — {task['created_at']}"):
            try:
                render_task_detail(get_task(task["id"]))
            except httpx.HTTPError as exc:
                st.error(f"Could not load task #{task['id']}: {exc}")

with tab_cost:
    st.subheader("Cost savings vs. an always-Opus baseline")
    try:
        summary = get_cost_summary()
    except httpx.HTTPError as exc:
        st.error(f"Could not load cost summary: {exc}")
    else:
        cols = st.columns(4)
        cols[0].metric("Tasks", summary["task_count"])
        cols[1].metric("Total spend", f"${summary['total_cost_usd']:.6f}")
        cols[2].metric("Baseline (always Opus)", f"${summary['baseline_cost_usd']:.6f}")
        cols[3].metric("Savings", f"${summary['savings_usd']:.6f}")
        if summary["task_count"] > 0 and summary["total_cost_usd"] == 0:
            st.caption(
                "Reading $0 because the routed tiers run on a local Ollama server — "
                "expected while running locally, see PRD.md's success metric note."
            )
