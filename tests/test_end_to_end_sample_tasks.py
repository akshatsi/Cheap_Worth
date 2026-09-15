"""Step 6's "run every sample task through the whole pipeline" check,
automated and deterministic: each of the 16 fixtures goes through the
real API (FastAPI's TestClient), with a genuinely correct reference
solution mocked in for execute_fn — the real sandbox still validates it,
the real storage repositories still persist it. classify_fn is untouched
by these (bootstrap phase skips it entirely).

execute stays mocked here on purpose, same reasoning as every other
automated test in this project: no real Ollama server or API keys
required to run this suite, and no multi-minute runtime. The actual
real-Ollama batch run against these same fixtures is a one-off, done and
recorded in the repo's history rather than part of the test suite.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_connection, get_execute_fn
from app.api.main import app
from app.orchestration.state import ExecuteResult
from app.storage.db import get_connection, init_db

FIXTURES_DIR = Path("tests/fixtures/sample_tasks")

REFERENCE_SOLUTIONS = {
    "add_two_numbers": "def add(a, b):\n    return a + b\n",
    "reverse_string": "def reverse_string(s):\n    return s[::-1]\n",
    "is_palindrome": (
        "def is_palindrome(s):\n"
        "    cleaned = ''.join(ch.lower() for ch in s if ch != ' ')\n"
        "    return cleaned == cleaned[::-1]\n"
    ),
    "fibonacci": (
        "def fibonacci(n):\n"
        "    if n == 0:\n"
        "        return 0\n"
        "    a, b = 0, 1\n"
        "    for _ in range(n - 1):\n"
        "        a, b = b, a + b\n"
        "    return b\n"
    ),
    "merge_sorted_lists": (
        "def merge_sorted_lists(a, b):\n"
        "    result = []\n"
        "    i = j = 0\n"
        "    while i < len(a) and j < len(b):\n"
        "        if a[i] <= b[j]:\n"
        "            result.append(a[i]); i += 1\n"
        "        else:\n"
        "            result.append(b[j]); j += 1\n"
        "    result.extend(a[i:])\n"
        "    result.extend(b[j:])\n"
        "    return result\n"
    ),
    "valid_parentheses": (
        "def is_valid_parentheses(s):\n"
        "    pairs = {')': '(', ']': '[', '}': '{'}\n"
        "    stack = []\n"
        "    for ch in s:\n"
        "        if ch in '([{':\n"
        "            stack.append(ch)\n"
        "        elif ch in ')]}':\n"
        "            if not stack or stack.pop() != pairs[ch]:\n"
        "                return False\n"
        "    return not stack\n"
    ),
    "lru_cache": (
        "from collections import OrderedDict\n\n\n"
        "class LRUCache:\n"
        "    def __init__(self, capacity):\n"
        "        self.capacity = capacity\n"
        "        self.cache = OrderedDict()\n\n"
        "    def get(self, key):\n"
        "        if key not in self.cache:\n"
        "            return -1\n"
        "        self.cache.move_to_end(key)\n"
        "        return self.cache[key]\n\n"
        "    def put(self, key, value):\n"
        "        if key in self.cache:\n"
        "            self.cache.move_to_end(key)\n"
        "        self.cache[key] = value\n"
        "        if len(self.cache) > self.capacity:\n"
        "            self.cache.popitem(last=False)\n"
    ),
    "quicksort": (
        "def quicksort(arr):\n"
        "    if len(arr) <= 1:\n"
        "        return list(arr)\n"
        "    pivot = arr[len(arr) // 2]\n"
        "    left = [x for x in arr if x < pivot]\n"
        "    mid = [x for x in arr if x == pivot]\n"
        "    right = [x for x in arr if x > pivot]\n"
        "    return quicksort(left) + mid + quicksort(right)\n"
    ),
    "count_vowels": "def count_vowels(s):\n    return sum(1 for ch in s.lower() if ch in 'aeiou')\n",
    "max_of_three": "def max_of_three(a, b, c):\n    return max(a, b, c)\n",
    "is_prime": (
        "def is_prime(n):\n"
        "    if n < 2:\n"
        "        return False\n"
        "    for i in range(2, int(n ** 0.5) + 1):\n"
        "        if n % i == 0:\n"
        "            return False\n"
        "    return True\n"
    ),
    "flatten_list": (
        "def flatten_list(nested):\n"
        "    result = []\n"
        "    for item in nested:\n"
        "        if isinstance(item, list):\n"
        "            result.extend(flatten_list(item))\n"
        "        else:\n"
        "            result.append(item)\n"
        "    return result\n"
    ),
    "word_frequency": (
        "def word_frequency(text):\n"
        "    freq = {}\n"
        "    for word in text.split():\n"
        "        cleaned = word.lower().strip('.,!?')\n"
        "        if cleaned:\n"
        "            freq[cleaned] = freq.get(cleaned, 0) + 1\n"
        "    return freq\n"
    ),
    "binary_search": (
        "def binary_search(arr, target):\n"
        "    lo, hi = 0, len(arr) - 1\n"
        "    while lo <= hi:\n"
        "        mid = (lo + hi) // 2\n"
        "        if arr[mid] == target:\n"
        "            return mid\n"
        "        elif arr[mid] < target:\n"
        "            lo = mid + 1\n"
        "        else:\n"
        "            hi = mid - 1\n"
        "    return -1\n"
    ),
    "group_anagrams": (
        "def group_anagrams(words):\n"
        "    groups = {}\n"
        "    for w in words:\n"
        "        key = tuple(sorted(w))\n"
        "        groups.setdefault(key, []).append(w)\n"
        "    return list(groups.values())\n"
    ),
    "longest_common_subsequence": (
        "def longest_common_subsequence(a, b):\n"
        "    m, n = len(a), len(b)\n"
        "    dp = [[0] * (n + 1) for _ in range(m + 1)]\n"
        "    for i in range(1, m + 1):\n"
        "        for j in range(1, n + 1):\n"
        "            if a[i-1] == b[j-1]:\n"
        "                dp[i][j] = dp[i-1][j-1] + 1\n"
        "            else:\n"
        "                dp[i][j] = max(dp[i-1][j], dp[i][j-1])\n"
        "    return dp[m][n]\n"
    ),
}


def _load_fixtures() -> list[dict]:
    return [json.loads(path.read_text()) for path in sorted(FIXTURES_DIR.glob("*.json"))]


FIXTURES = _load_fixtures()


def test_every_sample_task_has_a_reference_solution():
    """Catches a new fixture being added without a solution to test it against."""
    missing = [f["id"] for f in FIXTURES if f["id"] not in REFERENCE_SOLUTIONS]
    assert missing == [], f"no reference solution for: {missing}"


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    def override_db():
        conn = get_connection(db_path)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db_connection] = override_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.mark.parametrize("fixture", FIXTURES, ids=[f["id"] for f in FIXTURES])
def test_sample_task_runs_end_to_end_and_lands_correctly_in_storage(client, fixture):
    solution = REFERENCE_SOLUTIONS[fixture["id"]]

    def execute_fn(tier, spec):
        # Ignores tier deliberately: this test is about the pipeline's
        # plumbing, not the escalation logic (tests/test_cascade.py owns
        # that). A correct solution regardless of tier means every task
        # here resolves on Haiku's first attempt, in bootstrap phase.
        return ExecuteResult(
            code_output=solution, cost_usd=0.0, latency_ms=1.0, input_tokens=10, output_tokens=10
        )

    app.dependency_overrides[get_execute_fn] = lambda: execute_fn

    response = client.post("/tasks", json={"spec": fixture["spec"], "tests": fixture["tests"]})
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["task"]["status"] == "done", body
    assert len(body["executions"]) == 1
    assert body["executions"][0]["tier"] == "haiku"
    assert body["executions"][0]["passed"] is True
    assert body["cost_ledger"] is not None
    assert body["cost_ledger"]["total_cost_usd"] == pytest.approx(0.0)

    task_id = body["task"]["id"]

    get_response = client.get(f"/tasks/{task_id}")
    assert get_response.status_code == 200
    assert get_response.json() == body

    history_response = client.get("/tasks")
    assert history_response.status_code == 200
    assert any(t["id"] == task_id for t in history_response.json())


def test_cost_summary_reflects_every_task_after_a_full_batch(client):
    """Definition of done, per IMPLEMENTATION_PLAN.md Step 6: the numbers
    the dashboard reports have to match what storage actually holds."""

    def make_execute_fn(solution):
        def execute_fn(tier, spec):
            return ExecuteResult(
                code_output=solution, cost_usd=0.0, latency_ms=1.0, input_tokens=10, output_tokens=10
            )

        return execute_fn

    for fixture in FIXTURES:
        app.dependency_overrides[get_execute_fn] = lambda f=fixture: make_execute_fn(
            REFERENCE_SOLUTIONS[f["id"]]
        )
        response = client.post("/tasks", json={"spec": fixture["spec"], "tests": fixture["tests"]})
        assert response.status_code == 200, response.text

    summary = client.get("/cost-summary").json()
    history = client.get("/tasks").json()

    assert summary["task_count"] == len(FIXTURES) == len(history)
    assert all(t["status"] == "done" for t in history)
    assert summary["total_cost_usd"] == pytest.approx(0.0)
