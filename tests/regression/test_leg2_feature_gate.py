"""Regression: Leg 2 feature-availability gate.

A field whose SDK method exists but is only populated when a feature_support
flag is enabled must NOT be green-lit when that flag is disabled. Covers both
the registry-tag path (``requires_feature``) and the platform fallback map
(``FEATURE_AVAILABILITY_GATES``), plus the demotion applied to verdicts.
"""

from __future__ import annotations

import unittest

from velocity_converter.leg2_fill_mapping import (
    apply_feature_gate,
    build_registry_index,
    feature_gate_violation,
)


def _reg(*, jurisdictional_scopes: bool, tagged: bool) -> dict:
    entry = {
        "field": "jurisdiction",
        "display_name": "Jurisdiction",
        "category": "quote_system",
        "velocity": "$data.jurisdiction",
        "requires_scope": [],
    }
    if tagged:
        entry["requires_feature"] = "jurisdictional_scopes"
    return {
        "feature_support": {"jurisdictional_scopes": jurisdictional_scopes},
        "system_paths": [
            {
                "field": "policyNumber",
                "display_name": "Policy number",
                "category": "system",
                "velocity": "$data.policyNumber",
                "requires_scope": [],
            },
            entry,
        ],
    }


_JURISDICTION_CAND = {
    "registry_field": "jurisdiction",
    "path": "$data.quote.jurisdiction",
}


class TestFeatureGateViolation(unittest.TestCase):
    def test_disabled_flag_via_fallback_map(self) -> None:
        idx = build_registry_index(_reg(jurisdictional_scopes=False, tagged=False))
        self.assertEqual(
            feature_gate_violation(_JURISDICTION_CAND, idx), "jurisdictional_scopes"
        )

    def test_disabled_flag_via_registry_tag(self) -> None:
        idx = build_registry_index(_reg(jurisdictional_scopes=False, tagged=True))
        self.assertEqual(
            feature_gate_violation(_JURISDICTION_CAND, idx), "jurisdictional_scopes"
        )

    def test_enabled_flag_is_not_a_violation(self) -> None:
        idx = build_registry_index(_reg(jurisdictional_scopes=True, tagged=True))
        self.assertIsNone(feature_gate_violation(_JURISDICTION_CAND, idx))

    def test_ungated_field_is_not_a_violation(self) -> None:
        idx = build_registry_index(_reg(jurisdictional_scopes=False, tagged=False))
        cand = {"registry_field": "policyNumber", "path": "$data.policyNumber"}
        self.assertIsNone(feature_gate_violation(cand, idx))

    def test_missing_flag_is_not_a_violation(self) -> None:
        # Flag absent entirely (not False) → JAR remains the authority.
        reg = _reg(jurisdictional_scopes=False, tagged=False)
        reg["feature_support"] = {}
        idx = build_registry_index(reg)
        self.assertIsNone(feature_gate_violation(_JURISDICTION_CAND, idx))


class TestApplyFeatureGate(unittest.TestCase):
    def test_demotes_and_clears_data_source(self) -> None:
        idx = build_registry_index(_reg(jurisdictional_scopes=False, tagged=False))
        verdicts = {
            "quote": {
                "data_source": "$data.quote.jurisdiction",
                "confidence": "high",
                "sdk_status": "verified",
                "reasoning": "verified jurisdiction() on Quote",
            }
        }
        flag = apply_feature_gate(verdicts, _JURISDICTION_CAND, idx)
        self.assertEqual(flag, "jurisdictional_scopes")
        v = verdicts["quote"]
        self.assertEqual(v["sdk_status"], "feature_gated")
        self.assertEqual(v["data_source"], "")  # not safe to auto-fill
        self.assertEqual(v["confidence"], "low")
        self.assertEqual(v["feature_gate"], "jurisdictional_scopes")
        self.assertIn("DEMOTED", v["reasoning"])

    def test_no_op_when_feature_enabled(self) -> None:
        idx = build_registry_index(_reg(jurisdictional_scopes=True, tagged=True))
        verdicts = {
            "quote": {
                "data_source": "$data.quote.jurisdiction",
                "confidence": "high",
                "sdk_status": "verified",
                "reasoning": "verified",
            }
        }
        self.assertIsNone(apply_feature_gate(verdicts, _JURISDICTION_CAND, idx))
        self.assertEqual(verdicts["quote"]["sdk_status"], "verified")
        self.assertEqual(verdicts["quote"]["data_source"], "$data.quote.jurisdiction")

    def test_skips_roots_with_no_auto_fill(self) -> None:
        idx = build_registry_index(_reg(jurisdictional_scopes=False, tagged=False))
        verdicts = {
            "segment": {
                "data_source": "",
                "confidence": "low",
                "sdk_status": "skipped",
                "reasoning": "root not resolved",
            }
        }
        apply_feature_gate(verdicts, _JURISDICTION_CAND, idx)
        # Nothing was auto-filled on this root → left untouched (not relabelled).
        self.assertEqual(verdicts["segment"]["sdk_status"], "skipped")


if __name__ == "__main__":
    unittest.main()
