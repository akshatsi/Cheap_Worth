"""Tests for the sandbox runner, against real subprocess execution — no
mocking here, since the point is to verify the subprocess/timeout/
syntax-error handling actually works, not just that it's wired correctly.
"""

import json
from pathlib import Path

from app.sandbox.runner import validate


def test_passing_code():
    code = "def add(a, b):\n    return a + b\n"
    tests = "def test_add():\n    assert add(2, 3) == 5\n"
    result = validate(code, tests)
    assert result.passed is True


def test_failing_code():
    code = "def add(a, b):\n    return a - b\n"  # wrong on purpose
    tests = "def test_add():\n    assert add(2, 3) == 5\n"
    result = validate(code, tests)
    assert result.passed is False
    assert result.detail["returncode"] != 0


def test_syntax_error_fails_cleanly_without_raising():
    code = "def add(a, b\n    return a + b\n"  # missing closing paren
    tests = "def test_add():\n    assert add(2, 3) == 5\n"
    result = validate(code, tests)
    assert result.passed is False


def test_runtime_crash_fails_cleanly():
    code = "def add(a, b):\n    return a / 0\n"
    tests = "def test_add():\n    assert add(2, 3) == 5\n"
    result = validate(code, tests)
    assert result.passed is False


def test_timeout_is_caught_and_reported():
    code = "def add(a, b):\n    while True:\n        pass\n"
    tests = "def test_add():\n    assert add(2, 3) == 5\n"
    result = validate(code, tests, timeout_seconds=2)
    assert result.passed is False
    assert result.detail.get("timeout") is True


def test_multiple_test_functions_all_must_pass():
    code = "def add(a, b):\n    return a + b\n"
    tests = (
        "def test_positive():\n    assert add(2, 3) == 5\n\n\n"
        "def test_this_one_is_wrong():\n    assert add(2, 3) == 999\n"
    )
    result = validate(code, tests)
    assert result.passed is False


def test_against_real_sample_task():
    fixture = json.loads(
        Path("tests/fixtures/sample_tasks/03_is_palindrome.json").read_text()
    )
    code = (
        "def is_palindrome(s):\n"
        "    cleaned = ''.join(ch.lower() for ch in s if ch != ' ')\n"
        "    return cleaned == cleaned[::-1]\n"
    )
    result = validate(code, fixture["tests"])
    assert result.passed is True
