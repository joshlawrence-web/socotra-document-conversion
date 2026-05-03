"""IT-4 — Cross-config permutation: structural invariants hold for every fixture.

Parameterised over all conformance fixtures.  For each fixture:
  - Output has required top-level keys
  - Every variable/loop entry has confidence in {high, medium, low}
  - Every entry has data_source as a string (not None, not missing)
  - No entry has confidence: high with empty data_source (worst failure mode)

Adding a new conformance fixture under conformance/fixtures/ automatically
adds a new test case — no test file changes required.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from leg2_fill_mapping import annotate_mapping  # noqa: E402

_FIXTURES_DIR = REPO / "conformance" / "fixtures"
_VALID_CONFIDENCES = {"high", "medium", "low"}
_REQUIRED_TOP_KEYS = {"schema_version", "variables", "loops"}


def _load_fixture(fixture_dir: Path) -> tuple[dict, dict] | None:
    """Return (mapping, registry) for the fixture, or None if files are missing."""
    mapping_path = fixture_dir / "mapping.yaml"
    registry_path = fixture_dir / "golden" / "path-registry.yaml"
    if not mapping_path.exists() or not registry_path.exists():
        return None
    mapping = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    if not isinstance(mapping, dict) or not isinstance(registry, dict):
        return None
    return mapping, registry


def _all_entries(result: dict) -> list[dict]:
    entries: list[dict] = list(result.get("variables") or [])
    for loop in result.get("loops") or []:
        entries.append(loop)
        entries.extend(loop.get("fields") or [])
    return entries


class TestCrossConfig(unittest.TestCase):
    pass


def _add_test(fixture_name: str, fixture_dir: Path) -> None:
    data = _load_fixture(fixture_dir)
    if data is None:
        return
    mapping, registry = data

    def test_required_keys(self, _m=mapping, _r=registry, _n=fixture_name) -> None:
        result = annotate_mapping(_m, _r, "golden/path-registry.yaml")
        result.pop("_idx", None)
        missing = _REQUIRED_TOP_KEYS - result.keys()
        self.assertEqual(
            missing, set(),
            f"[{_n}] missing required keys: {missing}",
        )

    def test_valid_confidence_and_string_data_source(
        self, _m=mapping, _r=registry, _n=fixture_name
    ) -> None:
        result = annotate_mapping(_m, _r, "golden/path-registry.yaml")
        for entry in _all_entries(result):
            name = entry.get("name") or entry.get("placeholder") or "?"
            with self.subTest(fixture=_n, entry=name):
                conf = entry.get("confidence")
                self.assertIn(
                    conf, _VALID_CONFIDENCES,
                    f"[{_n}] {name!r}: invalid confidence {conf!r}",
                )
                ds = entry.get("data_source")
                self.assertIsInstance(
                    ds, str,
                    f"[{_n}] {name!r}: data_source is not a string: {ds!r}",
                )

    def test_no_high_confidence_with_empty_data_source(
        self, _m=mapping, _r=registry, _n=fixture_name
    ) -> None:
        result = annotate_mapping(_m, _r, "golden/path-registry.yaml")
        for entry in _all_entries(result):
            name = entry.get("name") or entry.get("placeholder") or "?"
            with self.subTest(fixture=_n, entry=name):
                if entry.get("confidence") == "high":
                    self.assertNotEqual(
                        entry.get("data_source"), "",
                        f"[{_n}] {name!r}: confidence=high but data_source is empty",
                    )

    fixture_safe = fixture_name.replace("-", "_")
    setattr(TestCrossConfig, f"test_{fixture_safe}__required_keys", test_required_keys)
    setattr(
        TestCrossConfig,
        f"test_{fixture_safe}__valid_confidence_and_data_source",
        test_valid_confidence_and_string_data_source,
    )
    setattr(
        TestCrossConfig,
        f"test_{fixture_safe}__no_high_empty_data_source",
        test_no_high_confidence_with_empty_data_source,
    )


for _d in sorted(_FIXTURES_DIR.iterdir()):
    if _d.is_dir():
        _add_test(_d.name, _d)


if __name__ == "__main__":
    unittest.main()
