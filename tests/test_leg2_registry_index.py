"""Regression: generic matcher — registry indexing and 4-step name matching."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from leg2_fill_mapping import (  # noqa: E402
    build_registry_index,
    check_scope,
    match_name,
    normalize_mapping_field_name,
    suggest_variable,
)


class TestNormalize(unittest.TestCase):
    def test_screaming_snake(self) -> None:
        self.assertEqual(normalize_mapping_field_name("POLICY_NUMBER"), "policy_number")
        self.assertEqual(normalize_mapping_field_name("policy_number"), "policy_number")


class TestBuildIndex(unittest.TestCase):
    def _simple_reg(self) -> dict:
        return {
            "system_paths": [
                {
                    "field": "policyNumber",
                    "display_name": "Policy number",
                    "velocity": "$data.policyNumber",
                    "requires_scope": [],
                }
            ]
        }

    def test_by_field_populated(self) -> None:
        idx = build_registry_index(self._simple_reg())
        self.assertIn("policynumber", idx["by_field"])

    def test_by_display_name_populated(self) -> None:
        idx = build_registry_index(self._simple_reg())
        self.assertIn("policy number", idx["by_display_name"])


class TestMatchName(unittest.TestCase):
    def _make_idx(self) -> dict:
        return build_registry_index({
            "system_paths": [
                {
                    "field": "policyNumber",
                    "display_name": "Policy number",
                    "velocity": "$data.policyNumber",
                    "requires_scope": [],
                },
                {
                    "field": "name",
                    "display_name": "Account name",
                    "velocity": "$data.account.data.name",
                    "requires_scope": [],
                },
            ]
        })

    def test_step1_exact_field(self) -> None:
        idx = self._make_idx()
        entries, step, _ = match_name("POLICY_NUMBER", None, idx, None)
        self.assertEqual(step, "exact")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["velocity"], "$data.policyNumber")

    def test_step2_ci_label(self) -> None:
        idx = self._make_idx()
        # label "Policy Number" CI-matches display_name "Policy number"
        entries, step, _ = match_name("SOME_VAR", "Policy Number", idx, None)
        self.assertEqual(step, "ci")
        self.assertEqual(entries[0]["velocity"], "$data.policyNumber")

    def test_step4_fuzzy_last_token(self) -> None:
        idx = self._make_idx()
        # "policyholder_name" → last token "name" fuzzy matches "name" field
        entries, step, _ = match_name("POLICYHOLDER_NAME", "Policyholder", idx, None)
        self.assertEqual(step, "fuzzy")
        self.assertEqual(entries[0]["velocity"], "$data.account.data.name")

    def test_no_match(self) -> None:
        idx = self._make_idx()
        entries, step, _ = match_name("UNKNOWN_FIELD", None, idx, None)
        self.assertEqual(step, "none")
        self.assertEqual(entries, [])


class TestSuggestVariable(unittest.TestCase):
    def _idx(self) -> dict:
        return build_registry_index({
            "system_paths": [
                {
                    "field": "policyNumber",
                    "display_name": "Policy number",
                    "velocity": "$data.policyNumber",
                    "requires_scope": [],
                    "quantifier": "",
                },
            ],
            "account_paths": [
                {
                    "field": "name",
                    "display_name": "Account name",
                    "velocity": "$data.account.data.name",
                    "requires_scope": [],
                    "quantifier": "",
                }
            ],
        })

    def test_policy_number_high(self) -> None:
        idx = self._idx()
        v = {"name": "POLICY_NUMBER", "context": {"nearest_label": "Policy Number", "line": 1}}
        ds, conf, _ = suggest_variable(v, idx, None)
        self.assertEqual(conf, "high")
        self.assertEqual(ds, "$data.policyNumber")

    def test_policyholder_name_medium_fuzzy(self) -> None:
        idx = self._idx()
        v = {"name": "POLICYHOLDER_NAME", "context": {"nearest_label": "Policyholder", "line": 2}}
        ds, conf, reason = suggest_variable(v, idx, None)
        self.assertEqual(conf, "medium")
        self.assertEqual(ds, "$data.account.data.name")
        self.assertIn("confirm-assumption", reason)

    def test_no_match_low(self) -> None:
        idx = self._idx()
        v = {"name": "UNKNOWN_XYZ", "context": {"nearest_label": "", "line": 5}}
        ds, conf, reason = suggest_variable(v, idx, None)
        self.assertEqual(conf, "low")
        self.assertEqual(ds, "")
        self.assertIn("supply-from-plugin", reason)


class TestCheckScope(unittest.TestCase):
    def _scoped_entry(self) -> dict:
        return {
            "field": "goodsCategoryCode",
            "velocity": "$item.data.goodsCategoryCode",
            "requires_scope": [{"iterator": "$item", "foreach": "#foreach ($item in $data.items)"}],
        }

    def _idx(self) -> dict:
        return build_registry_index({
            "iterables": [
                {
                    "name": "Item",
                    "iterator": "$item",
                    "foreach": "#foreach ($item in $data.items)",
                    "list_velocity": "$data.items",
                }
            ]
        })

    def test_no_scope_required(self) -> None:
        idx = self._idx()
        e = {"field": "x", "velocity": "$data.x", "requires_scope": []}
        self.assertEqual(check_scope(e, {}, idx), "not_required")

    def test_scope_satisfied_by_loop(self) -> None:
        idx = self._idx()
        e = self._scoped_entry()
        ctx = {"loop": "items"}
        self.assertEqual(check_scope(e, ctx, idx), "satisfied")

    def test_scope_violated_with_hint(self) -> None:
        idx = self._idx()
        e = self._scoped_entry()
        ctx = {"loop_hint": "Item"}
        self.assertEqual(check_scope(e, ctx, idx), "violated_with_hint")

    def test_scope_violated_no_hint(self) -> None:
        idx = self._idx()
        e = self._scoped_entry()
        self.assertEqual(check_scope(e, {}, idx), "violated_no_hint")


if __name__ == "__main__":
    unittest.main()
