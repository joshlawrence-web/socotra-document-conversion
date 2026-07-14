"""Regression tests — [Name?]...[/Name] conditional row regions (Leg 0/3/4)
and the always-guard on coverage-hop loop fields (Leg 3).

Covers: region marker parsing (the `?` opener), the three region shapes
(inside a loop → direct #if($<iter>.<Name>); document-level coverage →
presence block, skipped in the variants.csv, auto-registered at parse;
document-level generic → plain render: template block with a when-only CSV
row), run-flattening/verify treating [Name?] as atomic, Leg 3 leaving
#if($item.X) guards untouched, Leg 3 guarding EVERY coverage hop regardless of
quantifier, and Leg 4's presence Boolean codegen. No JARs required.
"""

from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path

import yaml

from velocity_converter.leg0_ingest import (
    _atomic_token_spans,
    annotate_fields,
    extract_fields,
    extract_loops,
    parse_variants_csv_to_blocks,
    write_variants_csv,
)
from velocity_converter.leg3_substitute import (
    _coverage_prefix,
    apply_cond_substitutions,
    build_cond_map,
    build_substitution_map,
)
from velocity_converter.leg4_generate_plugin import render_conditional_puts

REPO = Path(__file__).resolve().parent.parent.parent
REGISTRY = REPO / "registry" / "path-registry.yaml"


def _annotate(html: str) -> tuple[str, list[dict]]:
    fields = extract_fields(html)
    return annotate_fields(html, fields), fields


GRID_HTML = """<html>
<body>
<p>[Item/]</p>
<p>{item.data.itemTypeCode}</p>
<p>[AccidentalDamage?]</p>
<p>{item.AccidentalDamage.data.labourCovered}</p>
<p>[/AccidentalDamage]</p>
<p>[/Item]</p>
<p>[Theft?]</p>
<p>Theft cover included.</p>
<p>[/Theft]</p>
<p>[SpecialOffer?]</p>
<p>Offer row.</p>
<p>[/SpecialOffer]</p>
</body>
</html>"""


class ConditionalRegionExtractionTests(unittest.TestCase):
    def _extract(self):
        annotated, fields = _annotate(GRID_HTML)
        blocks: list[dict] = []
        with contextlib.redirect_stderr(io.StringIO()):
            html, top_fields, loops = extract_loops(
                annotated, fields, cond_blocks=blocks, registry_path=REGISTRY
            )
        return html, top_fields, loops, blocks

    def test_in_loop_region_emits_iterator_guard(self):
        html, _f, _l, _b = self._extract()
        self.assertIn("#if($item.AccidentalDamage)", html)
        self.assertNotIn("[AccidentalDamage?]", html)
        self.assertNotIn("[/AccidentalDamage]", html)

    def test_doc_level_coverage_region_becomes_presence_block(self):
        html, _f, _l, blocks = self._extract()
        self.assertIn("#if($doc.Theft)", html)
        theft = next(b for b in blocks if b["key"] == "Theft")
        self.assertEqual(theft["render"], "template")
        self.assertEqual(theft["presence"]["coverage"], "Theft")
        self.assertEqual(theft["presence"]["exposure"], "Item")
        self.assertEqual(theft["presence"]["list_method"], "items")

    def test_doc_level_generic_region_is_plain_template_block(self):
        html, _f, _l, blocks = self._extract()
        self.assertIn("#if($doc.SpecialOffer)", html)
        offer = next(b for b in blocks if b["key"] == "SpecialOffer")
        self.assertEqual(offer["render"], "template")
        self.assertNotIn("presence", offer)

    def test_region_fields_stay_with_enclosing_loop(self):
        _h, top_fields, loops, _b = self._extract()
        loop_names = {f["name"] for f in loops[0]["fields"]}
        self.assertIn("item.AccidentalDamage.data.labourCovered", loop_names)
        self.assertNotIn(
            "item.AccidentalDamage.data.labourCovered",
            {f["name"] for f in top_fields},
        )

    def test_region_marker_is_atomic_for_run_flattening(self):
        spans = _atomic_token_spans("x [AccidentalDamage?] y [/AccidentalDamage] z")
        self.assertEqual(len(spans), 2)

    def test_unclosed_region_warns_and_stays_literal(self):
        annotated, fields = _annotate("<p>[Theft?]</p><p>x</p>")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            html, _f, loops = extract_loops(annotated, fields, cond_blocks=[])
        self.assertIn("[Theft?] never closed", err.getvalue())
        self.assertIn("[Theft?]", html)
        self.assertEqual(loops, [])


class VariantsCsvPresenceTests(unittest.TestCase):
    def _blocks(self):
        annotated, fields = _annotate(GRID_HTML)
        blocks: list[dict] = []
        with contextlib.redirect_stderr(io.StringIO()):
            extract_loops(annotated, fields, cond_blocks=blocks, registry_path=REGISTRY)
        return blocks

    def test_presence_block_skipped_in_csv(self, tmp_name="t.variants.csv"):
        import tempfile
        blocks = self._blocks()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / tmp_name
            write_variants_csv(blocks, "t", path)
            content = path.read_text(encoding="utf-8")
        self.assertNotIn("Theft", content)
        self.assertIn("Item,,", content)
        self.assertIn("SpecialOffer,,", content)

    def test_parse_auto_registers_presence_block(self):
        import tempfile
        blocks = self._blocks()
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "t.variants.csv"
            csv_path.write_text(
                "placeholder,when,text\nItem,,\nSpecialOffer,,\n", encoding="utf-8"
            )
            out = parse_variants_csv_to_blocks(csv_path, blocks)
        theft = next(b for b in out if b["key"] == "Theft")
        self.assertEqual(theft["render"], "template")
        self.assertEqual(theft["presence"]["coverage"], "Theft")
        # blank-when template rows (Item, SpecialOffer) are omitted entirely
        self.assertNotIn("Item", {b["key"] for b in out})


class Leg3RegionGuardTests(unittest.TestCase):
    def test_iterator_guard_survives_leg3_untouched(self):
        vm = "#if($item.AccidentalDamage)\n<tr>row</tr>\n#end\n"
        out = apply_cond_substitutions(vm, {})
        self.assertEqual(out, vm)

    def test_registered_doc_guard_renames_unregistered_strips(self):
        vm = "#if($doc.Theft)\nrow\n#end\n#if($doc.Blank)\nkept\n#end\n"
        cond_map = build_cond_map([{"key": "Theft", "id": 1, "source_text": ""}])
        out = apply_cond_substitutions(vm, cond_map)
        self.assertIn("#if($data.Theft)", out)
        self.assertNotIn("$doc.Blank", out)
        self.assertIn("kept", out)


class CoverageAlwaysGuardTests(unittest.TestCase):
    COVERAGES = [
        {"name": "AccidentalDamage", "velocity": "$item.AccidentalDamage",
         "quantifier": "?", "cardinality": "zero_or_one"},
        {"name": "Breakdown", "velocity": "$item.Breakdown",
         "quantifier": "!", "cardinality": "exactly_one_auto"},
    ]

    def test_coverage_prefix_matches_regardless_of_quantifier(self):
        self.assertEqual(
            _coverage_prefix("$item.Breakdown.data.labourCovered", self.COVERAGES),
            "$item.Breakdown",
        )
        self.assertEqual(
            _coverage_prefix("$item.AccidentalDamage.data.partsCovered", self.COVERAGES),
            "$item.AccidentalDamage",
        )
        self.assertIsNone(_coverage_prefix("$item.data.purchasePrice", self.COVERAGES))

    def test_substitution_map_guards_mandatory_coverage_hop(self):
        suggested = {
            "variables": [],
            "loops": [{
                "placeholder": "$TBD_Item",
                "data_source": "$data.segment.items",
                "available_coverages": self.COVERAGES,
                "fields": [{
                    "placeholder": "$TBD_item.Breakdown.data.labourCovered",
                    "data_source": "$item.Breakdown.data.labourCovered",
                }],
            }],
        }
        smap = build_substitution_map(suggested)
        self.assertEqual(
            smap["$TBD_item.Breakdown.data.labourCovered"],
            "#if($item.Breakdown)$item.Breakdown.data.labourCovered#end",
        )


class Leg4PresenceBooleanTests(unittest.TestCase):
    BLOCK = {
        "id": 2,
        "key": "Theft",
        "source_text": "",
        "render": "template",
        "presence": {"coverage": "Theft", "exposure": "Item", "list_method": "items"},
        "variants": [],
    }

    def test_policy_scope_walks_segment_items(self):
        code = render_conditional_puts([dict(self.BLOCK)], scope="policy")
        self.assertIn('renderingData.put("Theft", theftPresent)', code)
        self.assertIn("segment.items()", code)
        self.assertIn("presenceItem.theft() != null", code)

    def test_quote_scope_walks_quote_items(self):
        code = render_conditional_puts([dict(self.BLOCK)], scope="quote")
        self.assertIn("quote.items()", code)


if __name__ == "__main__":
    unittest.main()
