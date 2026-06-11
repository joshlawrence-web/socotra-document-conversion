"""Unit tests for leg2_review_writer — helpers and _write_review_md."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent

from velocity_converter.leg2_review_writer import (  # noqa: E402
    _all_entries,
    _check_minor_mismatch,
    _extract_na,
    _fmt_line,
    _write_review_md,
)


class TestExtractNa(unittest.TestCase):
    def test_extracts_supply_from_plugin(self) -> None:
        self.assertEqual(_extract_na("next-action: supply-from-plugin"), "supply-from-plugin")

    def test_extracts_pick_one(self) -> None:
        self.assertEqual(_extract_na("some text — next-action: pick-one"), "pick-one")

    def test_returns_none_on_no_match(self) -> None:
        self.assertIsNone(_extract_na("no action here"))

    def test_empty_string(self) -> None:
        self.assertIsNone(_extract_na(""))


class TestFmtLine(unittest.TestCase):
    def test_returns_line_number(self) -> None:
        self.assertEqual(_fmt_line({"context": {"line": 42}}), 42)

    def test_missing_context_fallback(self) -> None:
        self.assertEqual(_fmt_line({}), 999)

    def test_none_context_fallback(self) -> None:
        self.assertEqual(_fmt_line({"context": None}), 999)

    def test_missing_line_fallback(self) -> None:
        self.assertEqual(_fmt_line({"context": {"parent_tag": "td"}}), 999)


class TestAllEntries(unittest.TestCase):
    def test_combines_variables_and_loops(self) -> None:
        suggested = {
            "variables": [{"name": "A"}],
            "loops": [{"name": "B"}],
        }
        self.assertEqual(_all_entries(suggested), [{"name": "A"}, {"name": "B"}])

    def test_missing_both_returns_empty(self) -> None:
        self.assertEqual(_all_entries({}), [])

    def test_only_variables(self) -> None:
        self.assertEqual(_all_entries({"variables": [{"name": "X"}]}), [{"name": "X"}])


class TestCheckMinorMismatch(unittest.TestCase):
    def test_1_0_ok(self) -> None:
        self.assertIsNone(_check_minor_mismatch({"registry_schema_version": "1.0"}))

    def test_1_1_ok(self) -> None:
        self.assertIsNone(_check_minor_mismatch({"registry_schema_version": "1.1"}))

    def test_1_2_flagged(self) -> None:
        self.assertEqual(_check_minor_mismatch({"registry_schema_version": "1.2"}), "1.2")

    def test_missing_defaults_to_1_0(self) -> None:
        self.assertIsNone(_check_minor_mismatch({}))

    def test_invalid_version_safe(self) -> None:
        self.assertIsNone(_check_minor_mismatch({"registry_schema_version": "bad"}))


class TestWriteReviewMd(unittest.TestCase):
    def _minimal_suggested(self) -> dict:
        return {
            "run_id": "test-run",
            "product": "TestProduct",
            "generated_at": "2026-01-01T00:00:00",
            "input_mapping_sha256": "abc123",
            "input_registry_sha256": "def456",
            "registry_generated_at": "",
            "registry_config_dir": "",
            "registry_config_verified": True,
            "registry_config_check": "pass",
            "input_mapping_version": "1.0",
            "input_registry_version": "1.0",
            "variables": [
                {
                    "name": "POLICY_NUMBER",
                    "placeholder": "{{POLICY_NUMBER}}",
                    "data_source": "$data.policyNumber",
                    "confidence": "high",
                    "reasoning": "exact match",
                    "context": {"line": 10},
                },
                {
                    "name": "UNKNOWN",
                    "placeholder": "{{UNKNOWN}}",
                    "data_source": "",
                    "confidence": "low",
                    "reasoning": "next-action: supply-from-plugin",
                    "context": {"line": 20},
                },
            ],
            "loops": [],
            "_idx": {"refusal_flags": [], "partial_flags": []},
        }

    def test_file_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "test.review.md"
            _write_review_md(
                out,
                stem="test",
                suggested_path=Path(tmp) / "test.suggested.yaml",
                suggested=self._minimal_suggested(),
                mapping_path=Path(tmp) / "test.mapping.yaml",
                registry_path=Path(tmp) / "registry.yaml",
                gate_label="pass",
                escape_note="",
            )
            self.assertTrue(out.exists())

    def test_contains_schema_comment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "test.review.md"
            _write_review_md(
                out,
                stem="test",
                suggested_path=Path(tmp) / "test.suggested.yaml",
                suggested=self._minimal_suggested(),
                mapping_path=Path(tmp) / "test.mapping.yaml",
                registry_path=Path(tmp) / "registry.yaml",
                gate_label="pass",
                escape_note="",
            )
            content = out.read_text()
            self.assertIn("schema_version: 2.0", content)

    def test_blockers_section_lists_low_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "test.review.md"
            _write_review_md(
                out,
                stem="test",
                suggested_path=Path(tmp) / "test.suggested.yaml",
                suggested=self._minimal_suggested(),
                mapping_path=Path(tmp) / "test.mapping.yaml",
                registry_path=Path(tmp) / "registry.yaml",
                gate_label="pass",
                escape_note="",
            )
            content = out.read_text()
            self.assertIn("## Blockers", content)
            self.assertIn("UNKNOWN", content)

    def test_no_blockers_message_when_all_high(self) -> None:
        suggested = self._minimal_suggested()
        suggested["variables"] = [suggested["variables"][0]]  # only high
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "test.review.md"
            _write_review_md(
                out,
                stem="test",
                suggested_path=Path(tmp) / "test.suggested.yaml",
                suggested=suggested,
                mapping_path=Path(tmp) / "test.mapping.yaml",
                registry_path=Path(tmp) / "registry.yaml",
                gate_label="pass",
                escape_note="",
            )
            content = out.read_text()
            self.assertIn("No blockers.", content)

    def test_escape_note_rendered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "test.review.md"
            _write_review_md(
                out,
                stem="test",
                suggested_path=Path(tmp) / "test.suggested.yaml",
                suggested=self._minimal_suggested(),
                mapping_path=Path(tmp) / "test.mapping.yaml",
                registry_path=Path(tmp) / "registry.yaml",
                gate_label="pass",
                escape_note="Registry mismatch — proceed with caution",
            )
            content = out.read_text()
            self.assertIn("Registry mismatch", content)

    def test_minor_mismatch_appears_in_unrecognised(self) -> None:
        suggested = self._minimal_suggested()
        suggested["registry_schema_version"] = "1.2"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "test.review.md"
            _write_review_md(
                out,
                stem="test",
                suggested_path=Path(tmp) / "test.suggested.yaml",
                suggested=suggested,
                mapping_path=Path(tmp) / "test.mapping.yaml",
                registry_path=Path(tmp) / "registry.yaml",
                gate_label="pass",
                escape_note="",
            )
            content = out.read_text()
            self.assertIn("## Unrecognised inputs", content)
            self.assertIn("MINOR=1.2", content)


    def _run(self, suggested: dict, escape_note: str = "") -> str:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "test.review.md"
            _write_review_md(
                out,
                stem="test",
                suggested_path=Path(tmp) / "test.suggested.yaml",
                suggested=suggested,
                mapping_path=Path(tmp) / "test.mapping.yaml",
                registry_path=Path(tmp) / "registry.yaml",
                gate_label="pass",
                escape_note=escape_note,
            )
            return out.read_text()

    # --- single (terse) output behavior ---

    def test_blockers_render_as_table(self) -> None:
        suggested = self._minimal_suggested()
        content = self._run(suggested)
        self.assertIn("| Placeholder | Line | Root | sdk_status | next-action |", content)
        self.assertIn("`{{UNKNOWN}}`", content)

    def test_assumptions_render_count_only(self) -> None:
        suggested = self._minimal_suggested()
        suggested["variables"].append({
            "name": "FUZZY_FIELD",
            "placeholder": "{{FUZZY_FIELD}}",
            "data_source": "$data.account.data.name",
            "confidence": "medium",
            "reasoning": "confirm-assumption: check this — next-action: confirm-assumption",
            "context": {"line": 15},
        })
        content = self._run(suggested)
        self.assertIn("assumption(s) to confirm", content)
        self.assertNotIn("- [ ]", content)

    # --- §5 scope warning branch ---

    def test_scope_violation_entry_renders_table_row(self) -> None:
        suggested = self._minimal_suggested()
        suggested["variables"].append({
            "name": "SCOPED_FIELD",
            "placeholder": "{{SCOPED_FIELD}}",
            "data_source": "$item.data.description",
            "confidence": "medium",
            "reasoning": (
                "scope violation: registry candidate `$item.data.description` "
                "requires `#foreach ($item in $data.items)`"
            ),
            "context": {"line": 50},
        })
        content = self._run(suggested)
        self.assertIn("## Cross-scope warnings", content)
        self.assertIn("restructure-template", content)
        self.assertNotIn("No cross-scope warnings.", content)

    def test_scope_restructure_template_plus_registry_candidate_triggers(self) -> None:
        suggested = self._minimal_suggested()
        suggested["variables"].append({
            "name": "OTHER_SCOPED",
            "placeholder": "{{OTHER_SCOPED}}",
            "data_source": "",
            "confidence": "low",
            "reasoning": "restructure-template needed — registry candidate `$item.data.foo` found",
            "context": {"line": 55},
        })
        content = self._run(suggested)
        self.assertNotIn("No cross-scope warnings.", content)

    # --- invariants ---

    def test_all_seven_section_headers_always_present(self) -> None:
        content = self._run(self._minimal_suggested())
        for header in (
            "## State summary",
            "## Summary",
            "## Blockers",
            "## Assumptions to confirm",
            "## Cross-scope warnings",
            "## Done",
            "## Unrecognised inputs",
        ):
            self.assertIn(header, content, f"missing {header!r}")

    def test_high_confidence_always_in_done_section(self) -> None:
        suggested = self._minimal_suggested()
        content = self._run(suggested)
        # POLICY_NUMBER is high — must appear under Done, not Blockers
        done_pos = content.index("## Done")
        blockers_pos = content.index("## Blockers")
        policy_pos = content.index("POLICY_NUMBER", done_pos)
        self.assertGreater(policy_pos, done_pos)
        # confirm it's not also listed in Blockers table
        blockers_section = content[blockers_pos:done_pos]
        self.assertNotIn("POLICY_NUMBER", blockers_section)


if __name__ == "__main__":
    unittest.main()
