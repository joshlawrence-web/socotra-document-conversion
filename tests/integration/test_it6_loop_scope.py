"""IT-6 — Loop fields are never placed in mapping.variables.

Proves Leg 1 scope tracking: a field inside [name]...[/name] goes to
mapping.loops[*].fields with context.loop set, never into mapping.variables.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
CONVERT_SCRIPTS = REPO / ".cursor" / "skills" / "html-to-velocity" / "scripts"
sys.path.insert(0, str(CONVERT_SCRIPTS))

from bs4 import BeautifulSoup  # noqa: E402

from convert import Mapping, process_all_mustache_loops, rewrite_vars_in_subtree  # noqa: E402

_HTML = """\
<body>
<p>{{FIELD_A}}</p>
<p>{{FIELD_B}}</p>
[items]
<p>{{FIELD_X}}</p>
<p>{{FIELD_Y}}</p>
<p>{{FIELD_Z}}</p>
[/items]
</body>
"""


def _build() -> Mapping:
    soup = BeautifulSoup(_HTML, "html.parser")
    m = Mapping(source="test.html")
    process_all_mustache_loops(soup, m)
    rewrite_vars_in_subtree(soup, prefix="$TBD_", mapping=m, in_loop=False)
    return m


class TestLoopFieldScope(unittest.TestCase):
    def setUp(self) -> None:
        self.m = _build()

    def test_two_top_level_variables(self) -> None:
        names = [v["name"] for v in self.m.variables]
        self.assertEqual(
            len(self.m.variables), 2,
            f"Expected 2 top-level variables, got {len(self.m.variables)}: {names}",
        )

    def test_one_loop_with_three_fields(self) -> None:
        self.assertEqual(len(self.m.loops), 1)
        fields = self.m.loops[0]["fields"]
        phs = [f["placeholder"] for f in fields]
        self.assertEqual(
            len(fields), 3,
            f"Expected 3 loop fields, got {len(fields)}: {phs}",
        )

    def test_loop_fields_carry_context_loop(self) -> None:
        for fld in self.m.loops[0]["fields"]:
            ctx = fld.get("context") or {}
            self.assertIn(
                "loop", ctx,
                f"Loop field {fld.get('placeholder')!r} missing context.loop",
            )

    def test_no_loop_field_in_variables(self) -> None:
        var_names = {v["name"] for v in self.m.variables}
        loop_names = {f["name"] for f in self.m.loops[0]["fields"]}
        overlap = var_names & loop_names
        self.assertEqual(overlap, set(), f"Loop fields leaked into variables: {overlap}")


if __name__ == "__main__":
    unittest.main()
