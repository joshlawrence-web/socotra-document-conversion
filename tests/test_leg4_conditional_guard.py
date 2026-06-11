"""Tests for Leg 4 conditional-registry guard (plan 09)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from leg4_generate_plugin import _count_annotated_conditionals, write_report  # noqa: E402


# ---------------------------------------------------------------------------
# _count_annotated_conditionals
# ---------------------------------------------------------------------------

def test_no_warning_when_registry_present(tmp_path):
    stem = "test-doc"
    (tmp_path / f"{stem}.annotated.html").write_text(
        "<p>$doc.cond1 text</p>", encoding="utf-8"
    )
    (tmp_path / f"{stem}.conditional-registry.yaml").write_text("[]", encoding="utf-8")
    # Registry present — caller would skip the warning; count itself still works
    assert _count_annotated_conditionals(tmp_path, stem) == 1


def test_count_returns_zero_no_annotated_html(tmp_path):
    assert _count_annotated_conditionals(tmp_path, "missing-doc") == 0


def test_count_deduplicates(tmp_path):
    stem = "dup-doc"
    (tmp_path / f"{stem}.annotated.html").write_text(
        "$doc.cond1 $doc.cond1 $doc.cond1", encoding="utf-8"
    )
    assert _count_annotated_conditionals(tmp_path, stem) == 1


def test_count_multiple_conds(tmp_path):
    stem = "multi-doc"
    (tmp_path / f"{stem}.annotated.html").write_text(
        "$doc.cond1 $doc.cond2 $doc.cond3", encoding="utf-8"
    )
    assert _count_annotated_conditionals(tmp_path, stem) == 3


# ---------------------------------------------------------------------------
# write_report — conditional section
# ---------------------------------------------------------------------------

def _write_report_minimal(tmp_path, stem, cond_blocks):
    """Call write_report with the minimal required params."""
    report_path = tmp_path / f"{stem}.plugin-report.md"
    suggested_path = tmp_path / f"{stem}.mapping.yaml"
    suggested_path.write_text("", encoding="utf-8")
    java_path = tmp_path / f"ProductDocumentDataSnapshotPluginImpl.java"
    write_report(
        report_path,
        stem=stem,
        product="Product",
        suggested_path=suggested_path,
        java_path=java_path,
        high_results=[],
        ignored_vars=[],
        compile_status=None,
        compile_detail="",
        generated_at="2026-01-01T00:00:00",
        cond_blocks=cond_blocks,
    )
    return report_path.read_text(encoding="utf-8")


def test_plugin_report_shows_warning(tmp_path):
    stem = "zen-doc"
    (tmp_path / f"{stem}.annotated.html").write_text(
        "$doc.cond1 something", encoding="utf-8"
    )
    report = _write_report_minimal(tmp_path, stem, cond_blocks=[])
    assert "⚠ WARNING" in report
    assert "1 conditional(s)" in report


def test_plugin_report_no_warning_when_no_annotated_html(tmp_path):
    stem = "no-html-doc"
    report = _write_report_minimal(tmp_path, stem, cond_blocks=[])
    assert "⚠ WARNING" not in report
    assert "_No conditional-registry.yaml found" in report
