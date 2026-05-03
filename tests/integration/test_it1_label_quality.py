"""IT-1 — Label-match quality contract.

If a field's nearest_label exactly matches a display_name in the registry,
leg2 MUST return confidence: high and the exact velocity path.

Scope: only tests entries that have no scope requirement (requires_scope: [])
so the test doesn't depend on loop context setup.  Exposure-scoped fields are
excluded — they are covered by IT-6 (loop scope) and IT-4 (cross-config).
"""
from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from leg2_fill_mapping import _collect_entries, annotate_mapping  # noqa: E402

_REGISTRY = REPO / "registry" / "path-registry.yaml"


def _no_scope_unique_entries(reg: dict) -> list[dict]:
    """Return registry entries that need no scope and have a unique display_name."""
    entries = _collect_entries(reg)
    no_scope = [
        e for e in entries
        if not e.get("requires_scope")
        and e.get("display_name")
        and e.get("velocity")
    ]
    # Keep only entries whose display_name appears exactly once (case-sensitive)
    dn_count: Counter[str] = Counter(e["display_name"] for e in no_scope)
    return [e for e in no_scope if dn_count[e["display_name"]] == 1]


class TestLabelMatchQuality(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = yaml.safe_load(_REGISTRY.read_text(encoding="utf-8"))
        cls.target_entries = _no_scope_unique_entries(cls.reg)
        if not cls.target_entries:
            raise RuntimeError("No suitable registry entries found for IT-1")

        # Build a variable per entry using a non-matching name so only the label path fires
        variables = [
            {
                "name": f"VAR_{i}",
                "placeholder": f"$TBD_VAR_{i}",
                "type": "variable",
                "context": {"nearest_label": e["display_name"], "line": i + 1},
                "data_source": "",
            }
            for i, e in enumerate(cls.target_entries)
        ]
        mapping = {
            "schema_version": "1.0",
            "source": "test.html",
            "generated_at": "2026-01-01T00:00:00Z",
            "variables": variables,
            "loops": [],
        }
        cls.result_vars = annotate_mapping(mapping, cls.reg, "registry/path-registry.yaml")["variables"]

    def test_all_exact_label_matches_are_high_confidence(self) -> None:
        for i, entry in enumerate(self.target_entries):
            v = self.result_vars[i]
            with self.subTest(display_name=entry["display_name"]):
                self.assertEqual(
                    v["confidence"], "high",
                    f"display_name={entry['display_name']!r}: expected confidence=high, "
                    f"got {v['confidence']!r}. reasoning={v.get('reasoning')!r}",
                )

    def test_all_exact_label_matches_return_correct_velocity_path(self) -> None:
        for i, entry in enumerate(self.target_entries):
            v = self.result_vars[i]
            with self.subTest(display_name=entry["display_name"]):
                self.assertEqual(
                    v["data_source"], entry["velocity"],
                    f"display_name={entry['display_name']!r}: "
                    f"expected data_source={entry['velocity']!r}, got {v['data_source']!r}",
                )


if __name__ == "__main__":
    unittest.main()
