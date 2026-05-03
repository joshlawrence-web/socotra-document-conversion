"""Unit tests for registry config fingerprint (State plan Workstream E)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from socotra_config_fingerprint import compute_source_config_sha256  # noqa: E402

MINIMAL_CFG = REPO / "conformance" / "fixtures" / "minimal" / "socotra-config"


class TestSocotraConfigFingerprint(unittest.TestCase):
    def test_minimal_fixture_deterministic(self) -> None:
        a = compute_source_config_sha256(MINIMAL_CFG)
        b = compute_source_config_sha256(MINIMAL_CFG)
        self.assertEqual(len(a), 64)
        self.assertEqual(a, b)

    def test_minimal_matches_registry_meta(self) -> None:
        """Fixture golden registry embeds the same digest extract_paths produced."""
        import yaml

        reg_path = (
            REPO / "conformance" / "fixtures" / "minimal" / "golden" / "path-registry.yaml"
        )
        reg = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
        embedded = (reg.get("meta") or {}).get("source_config_sha256")
        self.assertEqual(compute_source_config_sha256(MINIMAL_CFG), embedded)


if __name__ == "__main__":
    unittest.main()
