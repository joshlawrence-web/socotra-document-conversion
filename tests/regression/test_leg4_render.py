"""Regression tests — leg4 Java rendering (no JARs required)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent

from velocity_converter.leg4_generate_plugin import render_java, write_report  # noqa: E402

FIXTURE_YAML = REPO / "tests" / "regression" / "fixtures" / "simple.suggested.yaml"

_DF_CALL = {
    "key": "agentInfo",
    "method": "getAgentInfo",
    "arg": "segment.locator()",
    "return_type": "Object",
    "return_fqcn": "",
}


class TestRenderJavaFresh(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.java = render_java("TestProduct", "simple.suggested.yaml")
        cls.java_with_df = render_java(
            "TestProduct",
            "simple.suggested.yaml",
            quote_df_calls=[_DF_CALL],
        )

    def test_class_name_in_output(self):
        self.assertIn("TestProductDocumentDataSnapshotPluginImpl", self.java)

    def test_put_calls_for_all_keys(self):
        self.assertIn('put("agentInfo"', self.java_with_df)

    def test_builder_pattern_present(self):
        self.assertIn("DocumentDataSnapshot.builder()", self.java)
        self.assertIn(".build();", self.java)

    def test_no_tbd_in_output(self):
        self.assertNotIn("$TBD_", self.java)

    def test_rendering_data_map_present(self):
        self.assertIn("renderingData.put(", self.java)


def test_plugin_report_written(tmp_path):
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
        high_results=[],
        ignored_vars=[],
        compile_status=None,
        compile_detail="",
        generated_at="2026-01-01T00:00:00Z",
        cond_blocks=[],
        additive_summary=None,
    )
    assert report_path.exists()
    assert "Leg 4 Plugin Report" in report_path.read_text(encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
