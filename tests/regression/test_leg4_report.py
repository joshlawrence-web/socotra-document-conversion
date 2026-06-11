"""Regression tests — leg4 plugin report content (no JARs required)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent

from velocity_converter.leg4_generate_plugin import render_java, write_report  # noqa: E402

FIXTURE_YAML = REPO / "tests" / "regression" / "fixtures" / "simple.suggested.yaml"


def _make_report(tmp_path, **overrides):
    java_content = render_java("TestProduct", "simple.suggested.yaml")
    java_path = tmp_path / "TestProductDocumentDataSnapshotPluginImpl.java"
    java_path.write_text(java_content, encoding="utf-8")
    report_path = tmp_path / "simple.plugin-report.md"
    write_report(
        report_path,
        stem="simple",
        product="TestProduct",
        suggested_path=FIXTURE_YAML,
        java_path=java_path,
        high_results=overrides.get("high_results", []),
        ignored_vars=overrides.get("ignored_vars", []),
        compile_status=overrides.get("compile_status", None),
        compile_detail=overrides.get("compile_detail", ""),
        generated_at="2026-01-01T00:00:00Z",
        cond_blocks=overrides.get("cond_blocks", []),
        additive_summary=overrides.get("additive_summary", None),
    )
    return report_path.read_text(encoding="utf-8")


def test_report_has_key_count(tmp_path):
    content = _make_report(tmp_path)
    assert "## Resolved paths" in content


def test_report_has_compile_check_section(tmp_path):
    content = _make_report(tmp_path)
    assert "## Compile check" in content


def test_report_additive_section_present(tmp_path):
    additive_summary = {
        "keys_already_present": 3,
        "keys_added": {"newField"},
        "cond_high_water_before": 0,
        "new_cond_ids": [],
        "preflight": {
            "existing_keys": {"quote", "policy", "productType"},
            "cond_high_water": 0,
            "is_valid": True,
            "errors": [],
        },
    }
    content = _make_report(tmp_path, additive_summary=additive_summary)
    assert "## Additive update summary" in content
    assert "Keys already present" in content
    assert "Keys added this run" in content


def test_report_no_additive_section_when_fresh(tmp_path):
    content = _make_report(tmp_path)
    assert "## Additive update summary" not in content


def test_report_unresolved_section_lists_empty_data_source(tmp_path):
    # Variables with empty data_source appear in the Unresolved section
    ignored = [{"name": "myUnresolvedField", "confidence": "medium", "data_source": ""}]
    content = _make_report(tmp_path, ignored_vars=ignored)
    assert "## Unresolved" in content
    assert "myUnresolvedField" in content


def test_report_compile_status_shown(tmp_path):
    content = _make_report(tmp_path, compile_status="PASS")
    assert "PASS" in content
