"""The classify -> execute -> validate -> decide loop.

Built as a LangGraph graph, but every model/classifier/sandbox call is
injected rather than imported directly. That's what lets the control flow
itself — bootstrap bypass, routed-phase starting tier, one-tier-at-a-time
escalation, stopping at Opus — be unit tested with mocked functions and no
real API spend (see tests/test_cascade.py). app.models holds the real
Anthropic/Groq-backed implementations these get wired up to once there's
something to validate against (a later step).
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.orchestration.state import (
    Attempt,
    CascadeState,
    ClassifyFn,
    ExecuteFn,
    ValidateFn,
)
from app.schemas.models import ESCALATION_ORDER, Phase, PredictedTier, TaskStatus, Tier


def _next_tier(current: Tier) -> Tier | None:
    """The tier one step up from `current`, or None if already at the top."""
    idx = ESCALATION_ORDER.index(current)
    if idx + 1 >= len(ESCALATION_ORDER):
        return None
    return ESCALATION_ORDER[idx + 1]


def build_cascade_graph(
    classify_fn: ClassifyFn,
    execute_fn: ExecuteFn,
    validate_fn: ValidateFn,
):
    """Compile the cascade graph, with the three external calls injected.

    In bootstrap phase, classify_fn is never called — every task starts at
    Haiku, per the PRD's cold-start plan, and the staged escalation itself
    produces the labeled data the classifier will eventually train on. In
    routed phase, classify_fn's prediction picks Haiku (simple) or Sonnet
    (complex) as the starting tier; Opus is only ever reached by escalation,
    never predicted directly.
    """

    def classify_node(state: CascadeState) -> dict:
        if state["phase"] == Phase.BOOTSTRAP:
            return {"current_tier": Tier.HAIKU, "classifier_prediction": None}

        prediction = classify_fn(state["spec"])
        starting_tier = (
            Tier.HAIKU
            if prediction.predicted_tier == PredictedTier.SIMPLE
            else Tier.SONNET
        )
        return {"current_tier": starting_tier, "classifier_prediction": prediction}

    def execute_node(state: CascadeState) -> dict:
        result = execute_fn(state["current_tier"], state["spec"])
        return {"pending_execution": result}

    def validate_node(state: CascadeState) -> dict:
        pending = state["pending_execution"]
        outcome = validate_fn(pending.code_output, state["tests"])
        attempt = Attempt(
            tier=state["current_tier"],
            code_output=pending.code_output,
            passed=outcome.passed,
            validation_detail=outcome.detail,
            cost_usd=pending.cost_usd,
            latency_ms=pending.latency_ms,
            input_tokens=pending.input_tokens,
            output_tokens=pending.output_tokens,
        )
        return {"attempts": state["attempts"] + [attempt]}

    def decide_node(state: CascadeState) -> dict:
        last_attempt = state["attempts"][-1]
        if last_attempt.passed:
            return {"status": TaskStatus.DONE}

        next_tier = _next_tier(state["current_tier"])
        if next_tier is None:
            return {"status": TaskStatus.FAILED}

        return {"status": TaskStatus.PENDING, "current_tier": next_tier}

    def route_after_decide(state: CascadeState) -> str:
        return "escalate" if state["status"] == TaskStatus.PENDING else "done"

    graph = StateGraph(CascadeState)
    graph.add_node("classify", classify_node)
    graph.add_node("execute", execute_node)
    graph.add_node("validate", validate_node)
    graph.add_node("decide", decide_node)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "execute")
    graph.add_edge("execute", "validate")
    graph.add_edge("validate", "decide")
    graph.add_conditional_edges(
        "decide",
        route_after_decide,
        {"escalate": "execute", "done": END},
    )

    return graph.compile()


def run_cascade(
    spec: str,
    tests: str,
    phase: Phase,
    classify_fn: ClassifyFn,
    execute_fn: ExecuteFn,
    validate_fn: ValidateFn,
) -> CascadeState:
    """Build the graph and run it once for one task, start to finish."""
    graph = build_cascade_graph(classify_fn, execute_fn, validate_fn)
    initial_state: CascadeState = {
        "spec": spec,
        "tests": tests,
        "phase": phase,
        "current_tier": Tier.HAIKU,
        "classifier_prediction": None,
        "attempts": [],
        "status": TaskStatus.PENDING,
        "pending_execution": None,
    }
    return graph.invoke(initial_state)
