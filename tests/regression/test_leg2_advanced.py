"""Unit tests for leg2_fill_mapping — loop suggestion, merge_delta, reorder_top_keys."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from leg2_fill_mapping import (  # noqa: E402
    build_registry_index,
    load_terminology,
    reorder_top_keys,
    suggest_loop_field,
    suggest_loop_root,
)


def _make_reg() -> dict:
    return {
        "meta": {"product": "TestProduct"},
        "schema_version": "1.1",
        "system_paths": [
            {
                "field": "policyNumber",
                "display_name": "Policy number",
                "velocity": "$data.policyNumber",
                "requires_scope": [],
                "quantifier": "",
            }
        ],
        "iterables": [
            {
                "name": "Item",
                "display_name": "Items",
                "iterator": "$item",
                "foreach": "#foreach ($item in $data.items)",
                "list_velocity": "$data.items",
            }
        ],
        "exposures": [
            {
                "name": "Item",
                "fields": [
                    {
                        "field": "description",
                        "display_name": "Item description",
                        "velocity": "$item.data.description",
                        "requires_scope": [{"iterator": "$item"}],
                        "quantifier": "",
                    }
                ],
                "coverages": [],
            }
        ],
    }


class TestSuggestLoopRoot(unittest.TestCase):
    def setUp(self) -> None:
        self.reg = _make_reg()
        self.idx = build_registry_index(self.reg)

    def test_exact_name_match(self) -> None:
        ds, step, reason, iterator, foreach, _ = suggest_loop_root("Item", self.idx, None, self.reg)
        self.assertEqual(step, "exact")
        self.assertEqual(ds, "$data.items")
        self.assertEqual(iterator, "$item")

    def test_plural_does_not_match_strict(self) -> None:
        # "Items" — plural of "Item" — no longer matches: exact name only
        ds, step, reason, iterator, foreach, _ = suggest_loop_root("Items", self.idx, None, self.reg)
        self.assertEqual(step, "none")
        self.assertEqual(ds, "")
        self.assertIn("supply-from-plugin", reason)

    def test_ci_does_not_match_strict(self) -> None:
        ds, step, reason, _, _, _ = suggest_loop_root("item", self.idx, None, self.reg)
        self.assertEqual(step, "none")
        self.assertEqual(ds, "")
        self.assertIn("supply-from-plugin", reason)

    def test_no_match_returns_low(self) -> None:
        ds, step, reason, it, fe, _ = suggest_loop_root("UnknownLoop", self.idx, None, self.reg)
        self.assertEqual(step, "none")
        self.assertEqual(ds, "")
        self.assertIn("supply-from-plugin", reason)

    def test_terminology_does_not_match_strict(self) -> None:
        # Synonyms are no longer consulted: exact name only
        terminology = {"synonyms": {"exposures": {"Item": ["Widget"]}}}
        ds, step, reason, _, _, _ = suggest_loop_root("Widget", self.idx, terminology, self.reg)
        self.assertEqual(step, "none")
        self.assertEqual(ds, "")
        self.assertIn("supply-from-plugin", reason)


class TestSuggestLoopField(unittest.TestCase):
    def setUp(self) -> None:
        self.reg = _make_reg()
        self.idx = build_registry_index(self.reg)

    def test_exact_field_match(self) -> None:
        ds, step, reason = suggest_loop_field("$item.TBD_DESCRIPTION", "Item", self.idx, self.reg)
        self.assertEqual(step, "exact")
        self.assertEqual(ds, "$item.data.description")

    def test_unparseable_placeholder(self) -> None:
        ds, step, reason = suggest_loop_field("NOTAPLACEHOLDER", "Item", self.idx, self.reg)
        self.assertEqual(step, "none")
        self.assertIn("needs-skill-update", reason)

    def test_unknown_iterator_low(self) -> None:
        ds, step, reason = suggest_loop_field("$ghost.TBD_FOO", "UnknownLoop", self.idx, self.reg)
        self.assertEqual(step, "none")
        self.assertIn("supply-from-plugin", reason)

    def test_fuzzy_last_token_medium(self) -> None:
        # "ITEM_DESCRIPTION" → last token "description" fuzzy-matches exposure field
        ds, step, reason = suggest_loop_field("$item.TBD_ITEM_DESCRIPTION", "Item", self.idx, self.reg)
        self.assertEqual(step, "fuzzy")
        self.assertEqual(ds, "$item.data.description")
        self.assertIn("confirm-assumption", reason)

    def test_unknown_field_in_known_loop_low(self) -> None:
        ds, step, reason = suggest_loop_field("$item.TBD_TOTALLY_UNKNOWN_XYZ", "Item", self.idx, self.reg)
        self.assertEqual(step, "none")


class TestReorderTopKeys(unittest.TestCase):
    def test_schema_version_first(self) -> None:
        d = {"variables": [], "schema_version": "1.0", "run_id": "abc"}
        out = reorder_top_keys(d)
        keys = list(out.keys())
        self.assertEqual(keys[0], "schema_version")
        self.assertEqual(keys[1], "run_id")

    def test_unknown_keys_preserved_at_end(self) -> None:
        d = {"my_custom_key": "val", "schema_version": "1.0"}
        out = reorder_top_keys(d)
        self.assertIn("my_custom_key", out)
        keys = list(out.keys())
        self.assertLess(keys.index("schema_version"), keys.index("my_custom_key"))

    def test_all_unknown_keys_preserved(self) -> None:
        d = {"z": 1, "a": 2}
        out = reorder_top_keys(d)
        self.assertEqual(set(out.keys()), {"z", "a"})


class TestInvariants(unittest.TestCase):
    """Assert contracts that must hold across all inputs, not just specific examples."""

    def _reg(self) -> dict:
        return _make_reg()

    def _idx(self) -> dict:
        return build_registry_index(self._reg())

    def test_low_confidence_loop_always_has_next_action(self) -> None:
        reg = self._reg()
        idx = self._idx()
        unknown_loops = ["GhostLoop", "Nonexistent", "FakeIterable"]
        for name in unknown_loops:
            with self.subTest(loop=name):
                ds, step, reason, _, _, _ = suggest_loop_root(name, idx, None, reg)
                self.assertEqual(step, "none")
                self.assertIn("next-action:", reason,
                              f"loop {name!r} no-match but no next-action in reasoning")

    def test_high_confidence_loop_root_always_has_data_source_and_iterator(self) -> None:
        reg = self._reg()
        idx = self._idx()
        for name in ("Item",):
            with self.subTest(loop=name):
                ds, step, _, iterator, foreach, _ = suggest_loop_root(name, idx, None, reg)
                self.assertEqual(step, "exact")
                self.assertNotEqual(ds, "")
                self.assertNotEqual(iterator, "")
                self.assertNotEqual(foreach, "")


class TestLoadTerminology(unittest.TestCase):
    def test_loads_registry_sibling_by_default(self) -> None:
        registry = REPO / "registry" / "path-registry.yaml"
        data = load_terminology(None, registry)
        self.assertIsNotNone(data)
        assert data is not None
        self.assertEqual(data.get("tenant"), "CommercialAuto")

    def test_explicit_flag_wins_over_registry_sibling(self) -> None:
        fixture_term = REPO / "conformance" / "fixtures" / "custom-naming" / "terminology.yaml"
        registry = REPO / "registry" / "path-registry.yaml"
        data = load_terminology(fixture_term, registry)
        self.assertIsNotNone(data)
        assert data is not None
        self.assertEqual(data.get("tenant"), "DeepSeaFleet")


if __name__ == "__main__":
    unittest.main()
