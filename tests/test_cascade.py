"""Unit tests for the cascade graph's control flow: bootstrap bypass,
routed-phase starting tier, and one-tier-at-a-time escalation up to and
stopping at Opus. Every model/classifier/validator call is a plain mocked
function — no real API spend, no network access, no API keys required.
"""

from app.orchestration.cascade import run_cascade
from app.orchestration.state import ClassifyResult, ExecuteResult, ValidateResult
from app.schemas.models import Phase, PredictedTier, TaskStatus, Tier


def make_execute_fn(code_by_tier=None, default_code="stub-code"):
    calls = []

    def execute_fn(tier, spec):
        calls.append(tier)
        code = (code_by_tier or {}).get(tier, default_code)
        return ExecuteResult(code_output=code, cost_usd=0.001, latency_ms=10.0)

    execute_fn.calls = calls
    return execute_fn


def make_validate_fn(pass_on_code):
    calls = []

    def validate_fn(code_output, tests):
        calls.append(code_output)
        return ValidateResult(passed=code_output in pass_on_code, detail={})

    validate_fn.calls = calls
    return validate_fn


def make_classify_fn(predicted_tier):
    calls = []

    def classify_fn(spec):
        calls.append(spec)
        return ClassifyResult(
            predicted_tier=predicted_tier,
            raw_response={},
            latency_ms=5.0,
            cost_usd=0.0001,
        )

    classify_fn.calls = calls
    return classify_fn


def test_bootstrap_never_calls_classifier_and_starts_at_haiku():
    execute_fn = make_execute_fn(default_code="haiku-code")
    validate_fn = make_validate_fn(pass_on_code={"haiku-code"})
    classify_fn = make_classify_fn(PredictedTier.COMPLEX)

    result = run_cascade(
        spec="spec",
        tests="tests",
        phase=Phase.BOOTSTRAP,
        classify_fn=classify_fn,
        execute_fn=execute_fn,
        validate_fn=validate_fn,
    )

    assert classify_fn.calls == []
    assert result["status"] == TaskStatus.DONE
    assert len(result["attempts"]) == 1
    assert result["attempts"][0].tier == Tier.HAIKU


def test_bootstrap_escalates_one_tier_at_a_time_on_failure():
    execute_fn = make_execute_fn(code_by_tier={Tier.OPUS: "opus-code"})
    validate_fn = make_validate_fn(pass_on_code={"opus-code"})
    classify_fn = make_classify_fn(PredictedTier.SIMPLE)

    result = run_cascade(
        spec="spec",
        tests="tests",
        phase=Phase.BOOTSTRAP,
        classify_fn=classify_fn,
        execute_fn=execute_fn,
        validate_fn=validate_fn,
    )

    assert result["status"] == TaskStatus.DONE
    tiers_tried = [a.tier for a in result["attempts"]]
    assert tiers_tried == [Tier.HAIKU, Tier.SONNET, Tier.OPUS]


def test_bootstrap_fails_task_when_opus_also_fails():
    execute_fn = make_execute_fn(default_code="bad-code")
    validate_fn = make_validate_fn(pass_on_code=set())
    classify_fn = make_classify_fn(PredictedTier.SIMPLE)

    result = run_cascade(
        spec="spec",
        tests="tests",
        phase=Phase.BOOTSTRAP,
        classify_fn=classify_fn,
        execute_fn=execute_fn,
        validate_fn=validate_fn,
    )

    assert result["status"] == TaskStatus.FAILED
    tiers_tried = [a.tier for a in result["attempts"]]
    assert tiers_tried == [Tier.HAIKU, Tier.SONNET, Tier.OPUS]
    assert all(not a.passed for a in result["attempts"])


def test_routed_phase_simple_prediction_starts_at_haiku():
    execute_fn = make_execute_fn(default_code="haiku-code")
    validate_fn = make_validate_fn(pass_on_code={"haiku-code"})
    classify_fn = make_classify_fn(PredictedTier.SIMPLE)

    result = run_cascade(
        spec="spec",
        tests="tests",
        phase=Phase.ROUTED,
        classify_fn=classify_fn,
        execute_fn=execute_fn,
        validate_fn=validate_fn,
    )

    assert len(classify_fn.calls) == 1
    assert result["attempts"][0].tier == Tier.HAIKU


def test_routed_phase_complex_prediction_starts_at_sonnet_and_never_tries_haiku():
    execute_fn = make_execute_fn(code_by_tier={Tier.OPUS: "opus-code"})
    validate_fn = make_validate_fn(pass_on_code={"opus-code"})
    classify_fn = make_classify_fn(PredictedTier.COMPLEX)

    result = run_cascade(
        spec="spec",
        tests="tests",
        phase=Phase.ROUTED,
        classify_fn=classify_fn,
        execute_fn=execute_fn,
        validate_fn=validate_fn,
    )

    tiers_tried = [a.tier for a in result["attempts"]]
    assert Tier.HAIKU not in tiers_tried
    assert tiers_tried == [Tier.SONNET, Tier.OPUS]


def test_routed_phase_never_predicts_opus_directly():
    """Opus should only ever be reached by escalation, never as classify_fn's
    own starting-tier prediction — PredictedTier has no OPUS option, but this
    pins the resulting starting-tier mapping too."""
    execute_fn = make_execute_fn(default_code="first-try-code")
    validate_fn = make_validate_fn(pass_on_code={"first-try-code"})

    for prediction, expected_start in (
        (PredictedTier.SIMPLE, Tier.HAIKU),
        (PredictedTier.COMPLEX, Tier.SONNET),
    ):
        classify_fn = make_classify_fn(prediction)
        result = run_cascade(
            spec="spec",
            tests="tests",
            phase=Phase.ROUTED,
            classify_fn=classify_fn,
            execute_fn=execute_fn,
            validate_fn=validate_fn,
        )
        assert result["attempts"][0].tier == expected_start
