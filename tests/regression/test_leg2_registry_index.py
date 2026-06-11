"""Regression: generic matcher — registry indexing and scope checking."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
from velocity_converter.leg2_fill_mapping import (  # noqa: E402
    build_registry_index,
    check_scope,
    normalize_mapping_field_name,
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
