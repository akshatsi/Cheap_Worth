"""Sandbox runner: executes model-generated code against its tests in a
local subprocess, under a timeout and a best-effort memory limit.

Matches the ValidateFn protocol in app.orchestration.state, so this is what
gets wired in as the cascade's real validate_fn once a later step connects
the pieces — Step 2's tests use a mocked validate_fn instead, on purpose,
so this module's real subprocess behavior never affects them.

A syntax error or a runtime crash in the candidate code is just a failed
validation, same as a failing assertion. Nothing in here is a security
boundary — see architecture.md's non-goal on container isolation; this is
a backstop against a runaway subprocess, not protection against hostile code.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from app.orchestration.state import ValidateResult

DEFAULT_TIMEOUT_SECONDS = 10
MEMORY_LIMIT_BYTES = 256 * 1024 * 1024  # 256 MB, best-effort


def _limit_resources() -> None:
    """Applied via subprocess's preexec_fn on POSIX systems. Caps address
    space so a runaway allocation gets killed instead of eating the host's
    memory. The OS may not enforce this strictly on every platform — it's
    a backstop, not a guarantee."""
    import resource

    try:
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
    except (ValueError, OSError):
        pass


def validate(
    code_output: str, tests: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
) -> ValidateResult:
    """Run `tests` (pytest-style test functions) against `code_output` (a
    candidate solution module) in an isolated subprocess. Never raises —
    every failure mode of the candidate code, or of the sandbox itself,
    comes back as ValidateResult(passed=False, ...)."""
    try:
        with tempfile.TemporaryDirectory(prefix="cost_autopilot_sandbox_") as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "solution.py").write_text(code_output)
            (tmp_path / "test_solution.py").write_text(
                "from solution import *  # noqa: F401,F403\n\n" + tests
            )

            result = subprocess.run(
                [sys.executable, "-m", "pytest", "test_solution.py", "-q", "--no-header"],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                preexec_fn=_limit_resources if sys.platform != "win32" else None,
            )

            return ValidateResult(
                passed=result.returncode == 0,
                detail={
                    "returncode": result.returncode,
                    "stdout": result.stdout[-4000:],
                    "stderr": result.stderr[-4000:],
                },
            )
    except subprocess.TimeoutExpired as exc:
        return ValidateResult(
            passed=False,
            detail={
                "timeout": True,
                "timeout_seconds": timeout_seconds,
                "partial_stdout": (exc.stdout or "")[-2000:] if exc.stdout else "",
            },
        )
    except Exception as exc:  # sandbox failure itself, not the candidate code
        return ValidateResult(passed=False, detail={"sandbox_error": str(exc)})
