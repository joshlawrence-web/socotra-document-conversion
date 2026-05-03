"""IT-3 — Unresolvable fields are always flagged, never silently wrong.

A mapping variable whose name and label don't match anything in the registry
must get confidence: low, data_source: "", and "next-action:" in reasoning.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from leg2_fill_mapping import annotate_mapping  # noqa: E402

_REGISTRY = REPO / "conformance" / "fixtures" / "itemcare-simple" / "golden" / "path-registry.yaml"

_BOGUS_NAMES = [
    "COMPLETELY_NONEXISTENT_FIELD_QQQ99",
    "XYZZY_BOGUS_ZZTOP_777",
    "NO_SUCH_THING_IN_ANY_REGISTRY_ABC",
    "PHANTOM_FIELD_ZZZZZ",
]
_BOGUS_LABEL = "No Such Label ZZZ_999_XYZ"


class TestUnresolvableFlagged(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = yaml.safe_load(_REGISTRY.read_text(encoding="utf-8"))
        variables = [
            {
                "name": name,
                "placeholder": f"$TBD_{name}",
                "type": "variable",
                "context": {"nearest_label": _BOGUS_LABEL, "line": i + 1},
                "data_source": "",
            }
            for i, name in enumerate(_BOGUS_NAMES)
        ]
        mapping = {
            "schema_version": "1.0",
            "source": "test.html",
            "generated_at": "2026-01-01T00:00:00Z",
            "variables": variables,
            "loops": [],
        }
        cls.result = annotate_mapping(mapping, cls.reg, "golden/path-registry.yaml")

    def test_all_unresolvable_have_low_confidence(self) -> None:
        for v in self.result["variables"]:
            with self.subTest(name=v["name"]):
                self.assertEqual(
                    v["confidence"], "low",
                    f"{v['name']!r}: expected confidence=low, got {v['confidence']!r}",
                )

    def test_all_unresolvable_have_empty_data_source(self) -> None:
        for v in self.result["variables"]:
            with self.subTest(name=v["name"]):
                self.assertEqual(
                    v["data_source"], "",
                    f"{v['name']!r}: expected empty data_source, got {v['data_source']!r}",
                )

    def test_all_unresolvable_have_next_action_in_reasoning(self) -> None:
        for v in self.result["variables"]:
            with self.subTest(name=v["name"]):
                self.assertIn(
                    "next-action:", v.get("reasoning", ""),
                    f"{v['name']!r}: missing 'next-action:' in reasoning: {v.get('reasoning')!r}",
                )


if __name__ == "__main__":
    unittest.main()
