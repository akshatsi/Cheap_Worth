"""Tests for the frontend's API client functions, using httpx.MockTransport
— no real server, no Streamlit, just verifying the request shape and
response parsing.
"""

import json

import httpx
import pytest

from frontend.api_client import get_cost_summary, get_task, list_tasks, submit_task


def _client_with(handler) -> httpx.Client:
    return httpx.Client(base_url="http://testserver", transport=httpx.MockTransport(handler))


def test_submit_task_posts_spec_and_tests_and_returns_detail():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "task": {"id": 1, "spec": "s", "tests": "t", "status": "done", "created_at": "now"},
                "executions": [],
                "classifier_predictions": [],
                "cost_ledger": None,
            },
        )

    client = _client_with(handler)
    result = submit_task("spec text", "tests text", client=client)

    assert captured["method"] == "POST"
    assert captured["path"] == "/tasks"
    assert captured["body"] == {"spec": "spec text", "tests": "tests text"}
    assert result["task"]["id"] == 1


def test_list_tasks_returns_parsed_json():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/tasks"
        return httpx.Response(200, json=[{"id": 1}, {"id": 2}])

    result = list_tasks(client=_client_with(handler))
    assert result == [{"id": 1}, {"id": 2}]


def test_get_task_hits_the_right_path():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tasks/42"
        return httpx.Response(200, json={"task": {"id": 42}})

    result = get_task(42, client=_client_with(handler))
    assert result["task"]["id"] == 42


def test_get_cost_summary_returns_parsed_json():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/cost-summary"
        return httpx.Response(
            200, json={"task_count": 3, "total_cost_usd": 0.0, "baseline_cost_usd": 0.0, "savings_usd": 0.0}
        )

    result = get_cost_summary(client=_client_with(handler))
    assert result["task_count"] == 3


def test_raises_on_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "No task with id 999"})

    with pytest.raises(httpx.HTTPStatusError):
        get_task(999, client=_client_with(handler))
