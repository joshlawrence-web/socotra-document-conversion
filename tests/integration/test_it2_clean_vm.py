"""IT-2 — End-to-end: a fully resolvable document produces a clean .vm.

Uses the itemcare-simple fixture's registry plus a synthetic mapping whose
every variable has an exact display_name match (so all entries are high
confidence after leg2).  After running leg2 annotate_mapping then leg3
substitute(), the final .vm must contain zero $TBD_* tokens and every
substituted path must be a valid Velocity reference.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from leg2_fill_mapping import annotate_mapping  # noqa: E402
from leg3_substitute import substitute  # noqa: E402

_REGISTRY = REPO / "conformance" / "fixtures" / "itemcare-simple" / "golden" / "path-registry.yaml"

# Variables whose display_names exactly match the itemcare-simple registry entries
# (all have requires_scope: [] so no loop context is needed)
_SYNTHETIC_MAPPING = {
    "schema_version": "1.0",
    "source": "test.html",
    "generated_at": "2026-01-01T00:00:00Z",
    "variables": [
        {
            "name": "VAR_0",
            "placeholder": "$TBD_VAR_0",
            "type": "variable",
            "context": {"nearest_label": "Policy number", "line": 1},
            "data_source": "",
        },
        {
            "name": "VAR_1",
            "placeholder": "$TBD_VAR_1",
            "type": "variable",
            "context": {"nearest_label": "Account name", "line": 2},
            "data_source": "",
        },
        {
            "name": "VAR_2",
            "placeholder": "$TBD_VAR_2",
            "type": "variable",
            "context": {"nearest_label": "Currency", "line": 3},
            "data_source": "",
        },
    ],
    "loops": [],
}

_VM_TEXT = """\
Policy Number: $TBD_VAR_0
Account: $TBD_VAR_1
Currency: $TBD_VAR_2
"""

_TBD_RE = re.compile(r"\$TBD_\w+")
_VELOCITY_PATH_RE = re.compile(r"^\$[a-zA-Z]\w*\.")
_FOREACH_RE = re.compile(r"#foreach\b")
_END_RE = re.compile(r"#end\b")


class TestEndToEndCleanVm(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        reg = yaml.safe_load(_REGISTRY.read_text(encoding="utf-8"))
        annotated = annotate_mapping(_SYNTHETIC_MAPPING, reg, "golden/path-registry.yaml")

        # Sanity: all variables must be high confidence after annotation
        for v in annotated["variables"]:
            assert v.get("confidence") == "high", (
                f"Precondition failed: {v['name']!r} is not high confidence "
                f"({v.get('confidence')!r}). reasoning={v.get('reasoning')!r}"
            )

        cls.final_vm = substitute(annotated, _VM_TEXT)

    def test_no_tbd_tokens_remain(self) -> None:
        remaining = _TBD_RE.findall(self.final_vm)
        self.assertEqual(
            remaining, [],
            f"$TBD_* tokens remain in final .vm: {remaining}\n\n{self.final_vm}",
        )

    def test_every_substituted_path_is_velocity_reference(self) -> None:
        for line in self.final_vm.splitlines():
            # Extract bare $... tokens that are NOT $TBD_*
            for token in re.findall(r"\$[a-zA-Z]\w*(?:\.\w+)+", line):
                self.assertRegex(
                    token,
                    _VELOCITY_PATH_RE,
                    f"Substituted token {token!r} does not look like a Velocity path",
                )

    def test_foreach_end_balanced(self) -> None:
        foreach_count = len(_FOREACH_RE.findall(self.final_vm))
        end_count = len(_END_RE.findall(self.final_vm))
        self.assertEqual(
            foreach_count, end_count,
            f"#foreach/#end mismatch: {foreach_count} foreach, {end_count} end",
        )


if __name__ == "__main__":
    unittest.main()
