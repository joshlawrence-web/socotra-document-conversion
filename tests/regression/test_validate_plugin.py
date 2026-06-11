"""Tests for parse_plugin_keys() and the validate_plugin.py CLI."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent

from velocity_converter.leg4_generate_plugin import parse_plugin_keys  # noqa: E402

# ---------------------------------------------------------------------------
# Minimal valid plugin fixture — matches actual generated template structure
# ---------------------------------------------------------------------------

_VALID_PLUGIN = """\
public class ZenCoverDocumentDataSnapshotPluginImpl {

    public DocumentDataSnapshot dataSnapshot(ZenCoverQuoteRequest request) {
        HashMap<String, Object> renderingData = new HashMap<>();
        renderingData.put("quote", quote);
        renderingData.put("policyNumber", "PZ-001");
        renderingData.put("productType", "ZenCover");
        renderingData.put("cond1", "");
        renderingData.put("cond3", "");
        return DocumentDataSnapshot.builder()
                .renderingData(renderingData)
                .build();
    }

    public DocumentDataSnapshot dataSnapshot(ZenCoverRequest request) {
        HashMap<String, Object> renderingData = new HashMap<>();
        renderingData.put("policy", policy);
        renderingData.put("policyNumber", "PZ-001");
        renderingData.put("productType", "ZenCover");
        renderingData.put("cond1", "");
        renderingData.put("cond3", "");
        return DocumentDataSnapshot.builder()
                .renderingData(renderingData)
                .build();
    }
}
"""

# ---------------------------------------------------------------------------
# parse_plugin_keys — valid file
# ---------------------------------------------------------------------------


def test_valid_plugin_is_valid(tmp_path):
    java = tmp_path / "ZenCoverDocumentDataSnapshotPluginImpl.java"
    java.write_text(_VALID_PLUGIN, encoding="utf-8")
    result = parse_plugin_keys(java)
    assert result["is_valid"] is True
    assert result["errors"] == []


def test_valid_plugin_key_count(tmp_path):
    java = tmp_path / "ZenCoverDocumentDataSnapshotPluginImpl.java"
    java.write_text(_VALID_PLUGIN, encoding="utf-8")
    result = parse_plugin_keys(java)
    # Keys across both overloads (union); policyNumber/productType/cond1/cond3 appear in both
    assert result["existing_keys"] == {"quote", "policy", "policyNumber", "productType", "cond1", "cond3"}


def test_valid_plugin_cond_high_water(tmp_path):
    java = tmp_path / "ZenCoverDocumentDataSnapshotPluginImpl.java"
    java.write_text(_VALID_PLUGIN, encoding="utf-8")
    result = parse_plugin_keys(java)
    assert result["cond_high_water"] == 3


def test_shared_keys_across_overloads_not_duplicate(tmp_path):
    """Keys shared between quote and policy overloads are intentional, not errors."""
    java = tmp_path / "ZenCoverDocumentDataSnapshotPluginImpl.java"
    java.write_text(_VALID_PLUGIN, encoding="utf-8")
    result = parse_plugin_keys(java)
    assert result["is_valid"] is True
    assert not any("Duplicate" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# parse_plugin_keys — duplicate key within the same overload
# ---------------------------------------------------------------------------

_DUP_PLUGIN = """\
public class ZenCoverDocumentDataSnapshotPluginImpl {
    public DocumentDataSnapshot dataSnapshot(ZenCoverQuoteRequest request) {
        HashMap<String, Object> renderingData = new HashMap<>();
        renderingData.put("quote", quote);
        renderingData.put("policyNumber", "first");
        renderingData.put("policyNumber", "second");
        return DocumentDataSnapshot.builder()
                .renderingData(renderingData)
                .build();
    }
}
"""


def test_duplicate_key_within_scope_is_invalid(tmp_path):
    java = tmp_path / "ZenCoverDocumentDataSnapshotPluginImpl.java"
    java.write_text(_DUP_PLUGIN, encoding="utf-8")
    result = parse_plugin_keys(java)
    assert result["is_valid"] is False
    assert any("policyNumber" in e for e in result["errors"])


def test_duplicate_key_error_names_key(tmp_path):
    java = tmp_path / "ZenCoverDocumentDataSnapshotPluginImpl.java"
    java.write_text(_DUP_PLUGIN, encoding="utf-8")
    result = parse_plugin_keys(java)
    assert any('"policyNumber"' in e for e in result["errors"])


# ---------------------------------------------------------------------------
# parse_plugin_keys — missing builder pattern
# ---------------------------------------------------------------------------


def test_missing_builder_is_invalid(tmp_path):
    src = (
        'public class Foo {\n'
        '    public void run() {\n'
        '        HashMap<String, Object> renderingData = new HashMap<>();\n'
        '        renderingData.put("key", "val");\n'
        '        // builder call absent\n'
        '    }\n'
        '}\n'
    )
    java = tmp_path / "Foo.java"
    java.write_text(src, encoding="utf-8")
    result = parse_plugin_keys(java)
    assert result["is_valid"] is False
    assert any("DocumentDataSnapshot.builder()" in e for e in result["errors"])


def test_missing_build_call_is_invalid(tmp_path):
    src = (
        'public class Foo {\n'
        '    public void run() {\n'
        '        HashMap<String, Object> renderingData = new HashMap<>();\n'
        '        renderingData.put("key", "val");\n'
        '        DocumentDataSnapshot.builder()\n'
        '                .renderingData(renderingData);\n'
        '        // terminal call omitted\n'
        '    }\n'
        '}\n'
    )
    java = tmp_path / "Foo.java"
    java.write_text(src, encoding="utf-8")
    result = parse_plugin_keys(java)
    assert result["is_valid"] is False
    assert any(".build()" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# parse_plugin_keys — empty file
# ---------------------------------------------------------------------------


def test_empty_file_is_invalid(tmp_path):
    java = tmp_path / "Empty.java"
    java.write_text("", encoding="utf-8")
    result = parse_plugin_keys(java)
    assert result["is_valid"] is False
    assert result["errors"]


def test_whitespace_only_file_is_invalid(tmp_path):
    java = tmp_path / "Whitespace.java"
    java.write_text("   \n\n  \t\n", encoding="utf-8")
    result = parse_plugin_keys(java)
    assert result["is_valid"] is False


# ---------------------------------------------------------------------------
# validate_plugin.py CLI — exit codes
# ---------------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "velocity_converter.validate_plugin", *args],
        capture_output=True,
        text=True,
    )


def test_cli_exits_0_on_valid(tmp_path):
    java = tmp_path / "ZenCoverDocumentDataSnapshotPluginImpl.java"
    java.write_text(_VALID_PLUGIN, encoding="utf-8")
    proc = _run_cli(str(java))
    assert proc.returncode == 0
    assert "VALID" in proc.stdout


def test_cli_exits_1_on_invalid(tmp_path):
    java = tmp_path / "Bad.java"
    java.write_text("public class Bad {}", encoding="utf-8")
    proc = _run_cli(str(java))
    assert proc.returncode == 1
    assert "INVALID" in proc.stdout


def test_cli_json_flag_valid(tmp_path):
    import json as _json
    java = tmp_path / "ZenCoverDocumentDataSnapshotPluginImpl.java"
    java.write_text(_VALID_PLUGIN, encoding="utf-8")
    proc = _run_cli(str(java), "--json")
    assert proc.returncode == 0
    data = _json.loads(proc.stdout)
    assert data["is_valid"] is True
    assert data["keys"] > 0


def test_cli_json_flag_invalid(tmp_path):
    import json as _json
    java = tmp_path / "Bad.java"
    java.write_text("public class Bad {}", encoding="utf-8")
    proc = _run_cli(str(java), "--json")
    assert proc.returncode == 1
    data = _json.loads(proc.stdout)
    assert data["is_valid"] is False
    assert len(data["errors"]) > 0


def test_cli_keys_flag(tmp_path):
    java = tmp_path / "ZenCoverDocumentDataSnapshotPluginImpl.java"
    java.write_text(_VALID_PLUGIN, encoding="utf-8")
    proc = _run_cli(str(java), "--keys")
    assert proc.returncode == 0
    keys = set(proc.stdout.strip().splitlines())
    assert "policyNumber" in keys
    assert "cond1" in keys


def test_cli_missing_file_exits_1():
    proc = _run_cli("/nonexistent/path/Plugin.java")
    assert proc.returncode == 1


# ---------------------------------------------------------------------------
# --validate-only flag on leg4_generate_plugin.py
# ---------------------------------------------------------------------------


def test_validate_only_exits_0_on_valid(tmp_path):
    java = tmp_path / "ZenCoverDocumentDataSnapshotPluginImpl.java"
    java.write_text(_VALID_PLUGIN, encoding="utf-8")
    suggested = tmp_path / "ZenCover.suggested.yaml"
    suggested.write_text("product: ZenCover\nvariables: []\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "velocity_converter.leg4_generate_plugin",
         "--suggested", str(suggested),
         "--output-dir", str(tmp_path),
         "--validate-only"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
    assert "VALID" in proc.stdout


def test_validate_only_exits_1_on_invalid(tmp_path):
    java = tmp_path / "ZenCoverDocumentDataSnapshotPluginImpl.java"
    java.write_text("public class ZenCoverDocumentDataSnapshotPluginImpl {}", encoding="utf-8")
    suggested = tmp_path / "ZenCover.suggested.yaml"
    suggested.write_text("product: ZenCover\nvariables: []\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "velocity_converter.leg4_generate_plugin",
         "--suggested", str(suggested),
         "--output-dir", str(tmp_path),
         "--validate-only"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 1
    assert "INVALID" in proc.stdout


def test_validate_only_writes_no_files(tmp_path):
    java = tmp_path / "ZenCoverDocumentDataSnapshotPluginImpl.java"
    java.write_text(_VALID_PLUGIN, encoding="utf-8")
    suggested = tmp_path / "ZenCover.suggested.yaml"
    suggested.write_text("product: ZenCover\nvariables: []\n", encoding="utf-8")
    files_before = set(tmp_path.iterdir())
    subprocess.run(
        [sys.executable, "-m", "velocity_converter.leg4_generate_plugin",
         "--suggested", str(suggested),
         "--output-dir", str(tmp_path),
         "--validate-only"],
        capture_output=True, text=True,
    )
    files_after = set(tmp_path.iterdir())
    assert files_before == files_after, "validate-only must not write any files"


def test_validate_only_no_existing_plugin_exits_0(tmp_path):
    suggested = tmp_path / "ZenCover.suggested.yaml"
    suggested.write_text("product: ZenCover\nvariables: []\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "velocity_converter.leg4_generate_plugin",
         "--suggested", str(suggested),
         "--output-dir", str(tmp_path),
         "--validate-only"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
