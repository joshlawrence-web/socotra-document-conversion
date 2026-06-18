"""Regression tests — parse_invocation() in agent.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent

from velocity_converter.agent import parse_invocation  # noqa: E402


# ---------------------------------------------------------------------------
# Valid invocations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected_op,expected_keys",
    [
        (
            "RUN_PIPELINE leg1 input=foo.html",
            "leg1",
            {"input": "foo.html"},
        ),
        (
            "RUN_PIPELINE leg1+leg2+leg3 input=foo.html registry=r.yaml",
            "leg1+leg2+leg3",
            {"input": "foo.html", "registry": "r.yaml"},
        ),
        (
            "RUN_PIPELINE leg0 input=form.docx output=workspace/output",
            "leg0",
            {"input": "form.docx", "output": "workspace/output"},
        ),
        (
            # leg0_scan must NOT be truncated to leg0 (+ stray _scan) by the regex
            "RUN_PIPELINE leg0_scan input=form.docx output=workspace/output",
            "leg0_scan",
            {"input": "form.docx", "output": "workspace/output"},
        ),
        (
            "RUN_PIPELINE intake input=form.docx registry=r.yaml output=workspace/output",
            "intake",
            {"input": "form.docx", "registry": "r.yaml"},
        ),
        (
            "RUN_PIPELINE list_paths registry=r.yaml",
            "list_paths",
            {"registry": "r.yaml"},
        ),
        (
            "RUN_PIPELINE leg4 suggested=foo.suggested.yaml",
            "leg4",
            {"suggested": "foo.suggested.yaml"},
        ),
        (
            "RUN_PIPELINE leg3 keep=intermediates suggested=foo.yaml",
            "leg3",
            {"keep": "intermediates", "suggested": "foo.yaml"},
        ),
    ],
)
def test_valid_invocation(text, expected_op, expected_keys):
    result = parse_invocation(text)
    assert result is not None
    assert result.get("operation") == expected_op
    for key, val in expected_keys.items():
        assert result.get(key) == val, f"Expected {key}={val!r}, got {result.get(key)!r}"


# ---------------------------------------------------------------------------
# Invalid invocations
# ---------------------------------------------------------------------------


def test_unknown_operation_returns_falsy():
    # No regex match for unknown op — returns empty dict (falsy)
    result = parse_invocation("RUN_PIPELINE unknown_op")
    assert not result


def test_no_run_pipeline_token_returns_none():
    result = parse_invocation("not a pipeline invocation")
    assert result is None


def test_empty_string_returns_none():
    result = parse_invocation("")
    assert result is None


def test_missing_input_still_parses_operation():
    # parse_invocation is pure parsing — missing-input validation is in run()
    result = parse_invocation("RUN_PIPELINE leg1")
    assert result is not None
    assert result.get("operation") == "leg1"
    assert "input" not in result


def test_case_insensitive_run_pipeline():
    result = parse_invocation("run_pipeline leg1 input=foo.html")
    assert result is not None
    assert result.get("operation") == "leg1"
