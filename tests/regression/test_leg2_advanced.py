"""Unit tests for leg2_fill_mapping — loop suggestion, merge_delta, reorder_top_keys."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from leg2_fill_mapping import (  # noqa: E402
    annotate_mapping,
    build_registry_index,
    merge_delta,
    reorder_top_keys,
    suggest_loop_field,
    suggest_loop_root,
    suggest_variable,
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
        ds, conf, reason, iterator, foreach, _ = suggest_loop_root("Item", self.idx, None, self.reg)
        self.assertEqual(conf, "high")
        self.assertEqual(ds, "$data.items")
        self.assertEqual(iterator, "$item")

    def test_plural_match(self) -> None:
        # "Items" → plural of "Item"
        ds, conf, reason, iterator, foreach, _ = suggest_loop_root("Items", self.idx, None, self.reg)
        self.assertEqual(conf, "high")
        self.assertEqual(ds, "$data.items")

    def test_ci_match(self) -> None:
        ds, conf, _, _, _, _ = suggest_loop_root("item", self.idx, None, self.reg)
        self.assertEqual(conf, "high")
        self.assertEqual(ds, "$data.items")

    def test_no_match_returns_low(self) -> None:
        ds, conf, reason, it, fe, _ = suggest_loop_root("UnknownLoop", self.idx, None, self.reg)
        self.assertEqual(conf, "low")
        self.assertEqual(ds, "")
        self.assertIn("supply-from-plugin", reason)

    def test_terminology_match(self) -> None:
        terminology = {"synonyms": {"exposures": {"Item": ["Widget"]}}}
        ds, conf, reason, _, _, _ = suggest_loop_root("Widget", self.idx, terminology, self.reg)
        self.assertEqual(conf, "high")
        self.assertIn("terminology", reason)


class TestSuggestLoopField(unittest.TestCase):
    def setUp(self) -> None:
        self.reg = _make_reg()
        self.idx = build_registry_index(self.reg)

    def test_exact_field_match(self) -> None:
        ds, conf, reason = suggest_loop_field("$item.TBD_DESCRIPTION", "Item", self.idx, self.reg)
        self.assertEqual(conf, "high")
        self.assertEqual(ds, "$item.data.description")

    def test_unparseable_placeholder(self) -> None:
        ds, conf, reason = suggest_loop_field("NOTAPLACEHOLDER", "Item", self.idx, self.reg)
        self.assertEqual(conf, "low")
        self.assertIn("needs-skill-update", reason)

    def test_unknown_iterator_low(self) -> None:
        ds, conf, reason = suggest_loop_field("$ghost.TBD_FOO", "UnknownLoop", self.idx, self.reg)
        self.assertEqual(conf, "low")
        self.assertIn("supply-from-plugin", reason)

    def test_fuzzy_last_token_medium(self) -> None:
        # "ITEM_DESCRIPTION" → last token "description" fuzzy-matches exposure field
        ds, conf, reason = suggest_loop_field("$item.TBD_ITEM_DESCRIPTION", "Item", self.idx, self.reg)
        self.assertEqual(conf, "medium")
        self.assertEqual(ds, "$item.data.description")
        self.assertIn("confirm-assumption", reason)

    def test_unknown_field_in_known_loop_low(self) -> None:
        ds, conf, reason = suggest_loop_field("$item.TBD_TOTALLY_UNKNOWN_XYZ", "Item", self.idx, self.reg)
        self.assertEqual(conf, "low")


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


class TestMergeDelta(unittest.TestCase):
    def _base(self) -> dict:
        return {
            "schema_version": "1.0",
            "variables": [
                {
                    "name": "POLICY_NUMBER",
                    "placeholder": "{{POLICY_NUMBER}}",
                    "data_source": "$data.policyNumber",
                    "confidence": "high",
                    "confirmed": True,  # locked
                },
                {
                    "name": "UNKNOWN_FIELD",
                    "placeholder": "{{UNKNOWN_FIELD}}",
                    "data_source": "",
                    "confidence": "low",
                },
            ],
            "loops": [],
        }

    def _mapping(self) -> dict:
        return {
            "schema_version": "1.0",
            "variables": [
                {
                    "name": "POLICY_NUMBER",
                    "placeholder": "{{POLICY_NUMBER}}",
                    "label": "Policy Number",
                    "context": {"line": 1, "nearest_label": "Policy Number"},
                },
            ],
            "loops": [],
        }

    def test_locked_entry_not_overwritten(self) -> None:
        reg = _make_reg()
        base = self._base()
        mapping = self._mapping()
        result = merge_delta(base, mapping, reg, "registry/path-registry.yaml")
        policy_var = next(v for v in result["variables"] if v["name"] == "POLICY_NUMBER")
        self.assertTrue(policy_var.get("confirmed"))
        self.assertEqual(policy_var["data_source"], "$data.policyNumber")

    def test_new_entry_not_in_base_appended(self) -> None:
        reg = _make_reg()
        base = self._base()
        mapping = {
            "schema_version": "1.0",
            "variables": [
                {
                    "name": "POLICY_NUMBER",
                    "placeholder": "{{POLICY_NUMBER}}",
                    "label": "Policy Number",
                    "context": {"line": 1, "nearest_label": "Policy Number"},
                },
                {
                    "name": "BRAND_NEW",
                    "placeholder": "{{BRAND_NEW}}",
                    "label": "Brand New",
                    "context": {"line": 5, "nearest_label": ""},
                },
            ],
            "loops": [],
        }
        result = merge_delta(base, mapping, reg, "registry/path-registry.yaml")
        names = [v["name"] for v in result["variables"]]
        self.assertIn("BRAND_NEW", names)

    def test_unlocked_entry_data_source_updated(self) -> None:
        reg = _make_reg()
        base = self._base()
        mapping = {
            "schema_version": "1.0",
            "variables": [
                {
                    "name": "UNKNOWN_FIELD",
                    "placeholder": "{{UNKNOWN_FIELD}}",
                    "label": "Policy Number",  # now maps to policyNumber via CI match
                    "context": {"line": 2, "nearest_label": "Policy Number"},
                },
            ],
            "loops": [],
        }
        result = merge_delta(base, mapping, reg, "registry/path-registry.yaml")
        unknown = next(v for v in result["variables"] if v["name"] == "UNKNOWN_FIELD")
        self.assertEqual(unknown["data_source"], "$data.policyNumber")


    def _base_with_loop(self) -> dict:
        return {
            "schema_version": "1.0",
            "variables": [],
            "loops": [
                {
                    "name": "Item",
                    "placeholder": "[Item]",
                    "data_source": "",
                    "confidence": "low",
                    "fields": [
                        {
                            "placeholder": "$item.TBD_DESCRIPTION",
                            "data_source": "",
                            "confidence": "low",
                        }
                    ],
                }
            ],
        }

    def _mapping_with_loop(self) -> dict:
        return {
            "schema_version": "1.0",
            "variables": [],
            "loops": [
                {
                    "name": "Item",
                    "placeholder": "[Item]",
                    "fields": [
                        {
                            "placeholder": "$item.TBD_DESCRIPTION",
                            "label": "Description",
                            "context": {"line": 10, "nearest_label": "Description"},
                        }
                    ],
                }
            ],
        }

    def test_loop_root_data_source_updated(self) -> None:
        reg = _make_reg()
        result = merge_delta(self._base_with_loop(), self._mapping_with_loop(), reg, "registry/path-registry.yaml")
        loop = result["loops"][0]
        self.assertEqual(loop["data_source"], "$data.items")
        self.assertEqual(loop["confidence"], "high")

    def test_loop_field_data_source_updated(self) -> None:
        reg = _make_reg()
        result = merge_delta(self._base_with_loop(), self._mapping_with_loop(), reg, "registry/path-registry.yaml")
        field = result["loops"][0]["fields"][0]
        self.assertEqual(field["data_source"], "$item.data.description")

    def test_locked_loop_not_overwritten(self) -> None:
        reg = _make_reg()
        base = self._base_with_loop()
        base["loops"][0]["locked"] = True
        base["loops"][0]["data_source"] = "$data.custom"
        result = merge_delta(base, self._mapping_with_loop(), reg, "registry/path-registry.yaml")
        self.assertEqual(result["loops"][0]["data_source"], "$data.custom")


class TestAnnotateMapping(unittest.TestCase):
    def _mapping(self) -> dict:
        return {
            "schema_version": "1.0",
            "variables": [
                {
                    "name": "POLICY_NUMBER",
                    "placeholder": "{{POLICY_NUMBER}}",
                    "label": "Policy Number",
                    "context": {"line": 1, "nearest_label": "Policy Number"},
                }
            ],
            "loops": [],
        }

    def test_annotates_variable_confidence(self) -> None:
        reg = _make_reg()
        result = annotate_mapping(self._mapping(), reg, "registry/path-registry.yaml")
        v = result["variables"][0]
        self.assertIn("confidence", v)
        self.assertIn("data_source", v)

    def test_product_set_from_registry(self) -> None:
        reg = _make_reg()
        result = annotate_mapping(self._mapping(), reg, "registry/path-registry.yaml")
        self.assertEqual(result["product"], "TestProduct")

    def test_idx_attached(self) -> None:
        reg = _make_reg()
        result = annotate_mapping(self._mapping(), reg, "registry/path-registry.yaml")
        self.assertIn("_idx", result)


class TestInvariants(unittest.TestCase):
    """Assert contracts that must hold across all inputs, not just specific examples."""

    def _reg(self) -> dict:
        return _make_reg()

    def _idx(self) -> dict:
        return build_registry_index(self._reg())

    def test_high_confidence_variable_never_empty_data_source(self) -> None:
        idx = self._idx()
        # every field in the registry should produce a non-empty data_source when matched
        known_vars = [
            {"name": "POLICY_NUMBER", "context": {"nearest_label": "Policy Number", "line": 1}},
        ]
        for v in known_vars:
            with self.subTest(name=v["name"]):
                ds, conf, _ = suggest_variable(v, idx, None)
                if conf == "high":
                    self.assertNotEqual(ds, "", f"{v['name']} is high but data_source is empty")

    def test_low_confidence_variable_always_has_next_action(self) -> None:
        idx = self._idx()
        unknown_vars = [
            {"name": "COMPLETELY_UNKNOWN_ABC", "context": {"nearest_label": "", "line": 1}},
            {"name": "XYZ_BOGUS_FIELD", "context": {"nearest_label": "", "line": 2}},
        ]
        for v in unknown_vars:
            with self.subTest(name=v["name"]):
                ds, conf, reason = suggest_variable(v, idx, None)
                self.assertEqual(conf, "low")
                self.assertIn("next-action:", reason,
                              f"{v['name']} low confidence but no next-action in reasoning")

    def test_low_confidence_loop_always_has_next_action(self) -> None:
        reg = self._reg()
        idx = self._idx()
        unknown_loops = ["GhostLoop", "Nonexistent", "FakeIterable"]
        for name in unknown_loops:
            with self.subTest(loop=name):
                ds, conf, reason, _, _, _ = suggest_loop_root(name, idx, None, reg)
                self.assertEqual(conf, "low")
                self.assertIn("next-action:", reason,
                              f"loop {name!r} low confidence but no next-action in reasoning")

    def test_high_confidence_loop_root_always_has_data_source_and_iterator(self) -> None:
        reg = self._reg()
        idx = self._idx()
        for name in ("Item", "Items", "item"):
            with self.subTest(loop=name):
                ds, conf, _, iterator, foreach, _ = suggest_loop_root(name, idx, None, reg)
                self.assertEqual(conf, "high")
                self.assertNotEqual(ds, "")
                self.assertNotEqual(iterator, "")
                self.assertNotEqual(foreach, "")


if __name__ == "__main__":
    unittest.main()
