"""Tests for the Ollama wrapper's markdown-fence stripping — the fix for a
real bug: small local models sometimes wrap code in a fence despite being
told not to, which is a guaranteed syntax error in the sandbox otherwise.
No network calls here, just the pure string-handling logic.
"""

from app.models.execute import _strip_markdown_fences


def test_leaves_unfenced_code_unchanged():
    code = "def add(a, b):\n    return a + b\n"
    assert _strip_markdown_fences(code) == code.strip()


def test_strips_language_tagged_fence():
    fenced = "```python\ndef add(a, b):\n    return a + b\n```"
    assert _strip_markdown_fences(fenced) == "def add(a, b):\n    return a + b"


def test_strips_plain_fence():
    fenced = "```\ndef add(a, b):\n    return a + b\n```"
    assert _strip_markdown_fences(fenced) == "def add(a, b):\n    return a + b"


def test_strips_fence_with_surrounding_whitespace():
    fenced = "  \n```python\ndef add(a, b):\n    return a + b\n```\n  "
    assert _strip_markdown_fences(fenced) == "def add(a, b):\n    return a + b"


def test_leaves_a_lone_opening_fence_mostly_alone():
    # No closing fence to pair with — still drop the opening line, since a
    # lone ``` at the start is never valid Python either way.
    fenced = "```python\ndef add(a, b):\n    return a + b\n"
    assert _strip_markdown_fences(fenced) == "def add(a, b):\n    return a + b"


def test_real_case_that_previously_broke_the_sandbox():
    """The exact llama3.2:1b output that failed sandbox validation with a
    SyntaxError before this fix existed."""
    from app.sandbox.runner import validate

    fenced_output = (
        "```python\n"
        "def is_prime(n):\n"
        "    if n < 2:\n"
        "        return False\n"
        "    for i in range(2, int(n**0.5) + 1):\n"
        "        if n % i == 0:\n"
        "            return False\n"
        "    return True\n"
        "```"
    )
    tests = (
        "def test_small_primes():\n"
        "    assert is_prime(2) is True\n"
        "    assert is_prime(7) is True\n\n\n"
        "def test_non_primes():\n"
        "    assert is_prime(1) is False\n"
        "    assert is_prime(9) is False\n"
    )

    result = validate(_strip_markdown_fences(fenced_output), tests)

    assert result.passed is True
