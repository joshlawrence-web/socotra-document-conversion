"""IT-7 — High-only mode: medium/low fields stay as $TBD_* after leg3.

When substitute() is called with high_only=True, only confidence: high
entries are substituted.  Medium/low entries with a data_source are deferred
and remain as $TBD_* in the output.  High entries must NOT appear as $TBD_*.

Covers both bare $TBD_* tokens and $iterator.TBD_field loop field tokens.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from leg3_substitute import substitute  # noqa: E402

_TBD_RE = re.compile(r"\$(?:\w+\.)?TBD_\w+")

# Synthetic suggested mapping with a mix of high / medium / low entries.
_SUGGESTED: dict = {
    "schema_version": "1.1",
    "variables": [
        {
            "name": "POLICY_NUMBER",
            "placeholder": "$TBD_POLICY_NUMBER",
            "confidence": "high",
            "data_source": "$data.policyNumber",
            "reasoning": "exact match",
        },
        {
            "name": "POLICYHOLDER_NAME",
            "placeholder": "$TBD_POLICYHOLDER_NAME",
            "confidence": "medium",
            "data_source": "$data.account.data.name",
            "reasoning": "fuzzy match — next-action: confirm-assumption",
        },
        {
            "name": "SCOPE_VIOLATION",
            "placeholder": "$TBD_SCOPE_VIOLATION",
            "confidence": "low",
            "data_source": "",
            "reasoning": "scope violation — next-action: restructure-template",
        },
    ],
    "loops": [
        {
            "name": "items",
            "placeholder": "$TBD_items",
            "confidence": "high",
            "data_source": "$data.items",
            "foreach": "#foreach ($item in $data.items)",
            "reasoning": "exact iterable match",
            "fields": [
                {
                    "name": "serial_number",
                    "placeholder": "$item.TBD_serial_number",
                    "confidence": "high",
                    "data_source": "$item.data.serialNumber",
                    "reasoning": "exact field match",
                },
                {
                    "name": "item_value",
                    "placeholder": "$item.TBD_item_value",
                    "confidence": "medium",
                    "data_source": "$item.data.itemValue",
                    "reasoning": "fuzzy match — next-action: confirm-assumption",
                },
            ],
        }
    ],
}

_VM_TEXT = """\
Policy: $TBD_POLICY_NUMBER
Holder: $TBD_POLICYHOLDER_NAME
Scope: $TBD_SCOPE_VIOLATION
#foreach ($item in $TBD_items)
Serial: $item.TBD_serial_number
Value: $item.TBD_item_value
#end
"""

_HIGH_PLACEHOLDERS = {
    "$TBD_POLICY_NUMBER",
    "$TBD_items",
    "$item.TBD_serial_number",
}
_MEDIUM_PLACEHOLDERS = {
    "$TBD_POLICYHOLDER_NAME",
    "$item.TBD_item_value",
}
_LOW_PLACEHOLDERS = {
    "$TBD_SCOPE_VIOLATION",
}


class TestHighOnlyMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.final_vm_high = substitute(_SUGGESTED, _VM_TEXT, high_only=True)
        cls.final_vm_normal = substitute(_SUGGESTED, _VM_TEXT, high_only=False)
        cls.remaining_high = set(_TBD_RE.findall(cls.final_vm_high))
        cls.remaining_normal = set(_TBD_RE.findall(cls.final_vm_normal))

    def test_high_confidence_entries_are_substituted(self) -> None:
        for ph in _HIGH_PLACEHOLDERS:
            with self.subTest(placeholder=ph):
                self.assertNotIn(
                    ph, self.remaining_high,
                    f"High-confidence placeholder {ph!r} was NOT substituted in high-only mode",
                )

    def test_medium_confidence_entries_stay_as_tbd(self) -> None:
        for ph in _MEDIUM_PLACEHOLDERS:
            with self.subTest(placeholder=ph):
                self.assertIn(
                    ph, self.remaining_high,
                    f"Medium-confidence placeholder {ph!r} was incorrectly substituted "
                    f"in high-only mode",
                )

    def test_low_confidence_entries_stay_as_tbd(self) -> None:
        for ph in _LOW_PLACEHOLDERS:
            with self.subTest(placeholder=ph):
                self.assertIn(
                    ph, self.remaining_high,
                    f"Low-confidence placeholder {ph!r} was incorrectly substituted "
                    f"in high-only mode (empty data_source should always remain)",
                )

    def test_high_confidence_loop_foreach_replaced(self) -> None:
        self.assertIn(
            "#foreach ($item in $data.items)", self.final_vm_high,
            "High-confidence loop's #foreach directive was NOT substituted in high-only mode",
        )

    def test_medium_tokens_substituted_in_normal_mode(self) -> None:
        for ph in _MEDIUM_PLACEHOLDERS:
            with self.subTest(placeholder=ph):
                self.assertNotIn(
                    ph, self.remaining_normal,
                    f"Medium-confidence placeholder {ph!r} was NOT substituted in normal mode "
                    f"(it should only be deferred in high-only mode)",
                )

    def test_no_remaining_tbd_is_high_confidence(self) -> None:
        for ph in self.remaining_high:
            with self.subTest(placeholder=ph):
                self.assertNotIn(
                    ph, _HIGH_PLACEHOLDERS,
                    f"{ph!r} is high-confidence but was NOT substituted in high-only mode",
                )


if __name__ == "__main__":
    unittest.main()
