"""IT-5 — Confidence stability: locked entries survive a leg2 delta re-run.

An entry marked locked: true (or status: "confirmed") must not be
overwritten by merge_delta.  Confirmed paths are a one-way gate.
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from leg2_fill_mapping import merge_delta  # noqa: E402

_FIXTURE = REPO / "conformance" / "fixtures" / "itemcare-simple"
_MAPPING = _FIXTURE / "mapping.yaml"
_REGISTRY = _FIXTURE / "golden" / "path-registry.yaml"
_GOLDEN = _FIXTURE / "golden" / "suggested.yaml"


def _strip_comment_header(text: str) -> str:
    lines = [ln for ln in text.splitlines() if not ln.startswith("#")]
    return "\n".join(lines)


class TestDeltaStability(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mapping = yaml.safe_load(_MAPPING.read_text(encoding="utf-8"))
        cls.reg = yaml.safe_load(_REGISTRY.read_text(encoding="utf-8"))
        raw_golden = _strip_comment_header(_GOLDEN.read_text(encoding="utf-8"))
        cls.golden = yaml.safe_load(raw_golden)

    def _base_with_locked(self) -> dict:
        base = copy.deepcopy(self.golden)
        # Lock the first variable (POLICY_NUMBER, high confidence)
        for v in base.get("variables") or []:
            if v.get("name") == "POLICY_NUMBER":
                v["locked"] = True
                v["data_source"] = "$data.CUSTOM_LOCKED_PATH"
                v["confidence"] = "high"
                break
        # Lock the loop (items, high confidence) by setting its data_source to a custom value
        for loop in base.get("loops") or []:
            if loop.get("name") == "items":
                loop["locked"] = True
                loop["data_source"] = "$data.CUSTOM_LOCKED_LOOP"
                break
        return base

    def test_locked_variable_not_overwritten(self) -> None:
        base = self._base_with_locked()
        result = merge_delta(base, self.mapping, self.reg, "golden/path-registry.yaml")
        policy_var = next(
            (v for v in result.get("variables") or [] if v.get("name") == "POLICY_NUMBER"),
            None,
        )
        self.assertIsNotNone(policy_var, "POLICY_NUMBER not found in result")
        self.assertEqual(
            policy_var["data_source"], "$data.CUSTOM_LOCKED_PATH",
            "Locked variable's data_source was overwritten by merge_delta",
        )
        self.assertTrue(policy_var.get("locked"), "locked flag was removed")

    def test_locked_loop_not_overwritten(self) -> None:
        base = self._base_with_locked()
        result = merge_delta(base, self.mapping, self.reg, "golden/path-registry.yaml")
        loop = next(
            (L for L in result.get("loops") or [] if L.get("name") == "items"),
            None,
        )
        self.assertIsNotNone(loop, "items loop not found in result")
        self.assertEqual(
            loop["data_source"], "$data.CUSTOM_LOCKED_LOOP",
            "Locked loop's data_source was overwritten by merge_delta",
        )

    def test_unlocked_variable_is_updated(self) -> None:
        """Control: unlocked entries SHOULD be updated on a delta re-run."""
        base = copy.deepcopy(self.golden)
        # Manually degrade POLICYHOLDER_NAME so we can observe it being refreshed
        for v in base.get("variables") or []:
            if v.get("name") == "POLICYHOLDER_NAME":
                v["data_source"] = "$data.STALE_PATH"
                v["confidence"] = "low"
                v.pop("locked", None)
                v.pop("status", None)
                break
        result = merge_delta(base, self.mapping, self.reg, "golden/path-registry.yaml")
        ph_var = next(
            (v for v in result.get("variables") or [] if v.get("name") == "POLICYHOLDER_NAME"),
            None,
        )
        self.assertIsNotNone(ph_var)
        self.assertNotEqual(
            ph_var.get("data_source"), "$data.STALE_PATH",
            "Unlocked variable was NOT updated by merge_delta (expected it to be refreshed)",
        )


if __name__ == "__main__":
    unittest.main()
