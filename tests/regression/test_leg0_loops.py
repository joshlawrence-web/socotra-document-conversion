"""Regression tests — [Name]...[/Name] loop sections in Leg 0.

Covers: marker detection (paragraph + table-row forms), #foreach/#end
scaffold emission, loop-field membership (all occurrences inside the
section), unmatched-marker warnings, [[conditional]] non-interference,
mapping shape (loop entry + loop_field context), and loop-in-conditional
handling (render: template flip → #if guard in template, Boolean put in
Leg 4, guard rewrite in Leg 3). No JARs required.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from velocity_converter.leg0_ingest import (
    _normalise_for_leg2,
    annotate_conditionals,
    annotate_fields,
    extract_conditionals,
    extract_fields,
    extract_loops,
    load_conditional_blocks,
    parse_variants_csv_to_blocks,
    write_conditional_blocks,
)
from velocity_converter.leg3_substitute import apply_cond_substitutions
from velocity_converter.leg4_generate_plugin import (
    _analyse_cond_fields,
    render_conditional_puts,
)
from velocity_converter.models import MappingDoc, validate_contract


def _annotate(html: str) -> tuple[str, list[dict]]:
    fields = extract_fields(html)
    return annotate_fields(html, fields), fields


PARA_LOOP_HTML = """<html>
<body>
<p>Dear {account.data.firstName},</p>
<p>[Item]</p>
<p>{item.data.itemTypeCode} bought for {item.data.purchasePrice}</p>
<p>[/Item]</p>
<p>ZenCover Limited</p>
</body>
</html>"""

TABLE_LOOP_HTML = """<html>
<body>
<table>
  <tr><td>Type</td><td>Price</td></tr>
  <tr><td>[Item]</td><td></td></tr>
  <tr><td>{item.data.itemTypeCode}</td><td>{item.data.purchasePrice}</td></tr>
  <tr><td>[/Item]</td><td></td></tr>
</table>
</body>
</html>"""


class TestExtractLoops(unittest.TestCase):
    def test_paragraph_markers_become_directive_lines(self) -> None:
        annotated, fields = _annotate(PARA_LOOP_HTML)
        html, top, loops = extract_loops(annotated, fields)
        self.assertIn("\n#foreach ($item in $TBD_Item)\n", html)
        self.assertIn("\n#end\n", html)
        self.assertNotIn("[Item]", html)
        self.assertNotIn("[/Item]", html)
        self.assertNotIn("<p>#foreach", html)
        self.assertNotIn("<p>#end</p>", html)

    def test_table_row_markers_become_directive_lines(self) -> None:
        annotated, fields = _annotate(TABLE_LOOP_HTML)
        html, top, loops = extract_loops(annotated, fields)
        self.assertIn("#foreach ($item in $TBD_Item)", html)
        self.assertNotIn("<tr><td>#foreach", html)
        self.assertNotIn("<td>#end</td>", html)
        # Header row stays outside the loop
        head, _, tail = html.partition("#foreach")
        self.assertIn("<tr><td>Type</td><td>Price</td></tr>", head)
        self.assertIn("$TBD_item.data.purchasePrice", tail)

    def test_field_membership(self) -> None:
        annotated, fields = _annotate(PARA_LOOP_HTML)
        _, top, loops = extract_loops(annotated, fields)
        self.assertEqual(len(loops), 1)
        loop = loops[0]
        self.assertEqual(loop["name"], "Item")
        self.assertEqual(loop["token"], "$TBD_Item")
        self.assertEqual(loop["iterator"], "$item")
        self.assertEqual(
            sorted(f["name"] for f in loop["fields"]),
            ["item.data.itemTypeCode", "item.data.purchasePrice"],
        )
        self.assertEqual([f["name"] for f in top], ["account.data.firstName"])

    def test_field_used_inside_and_outside_stays_top_level(self) -> None:
        html = (
            "<html><body>"
            "<p>Total: {item.data.purchasePrice}</p>"
            "<p>[Item]</p><p>{item.data.purchasePrice}</p><p>[/Item]</p>"
            "</body></html>"
        )
        annotated, fields = _annotate(html)
        _, top, loops = extract_loops(annotated, fields)
        self.assertEqual([f["name"] for f in top], ["item.data.purchasePrice"])
        self.assertEqual(loops[0]["fields"], [])

    def test_unmatched_markers_left_as_literal(self) -> None:
        html = "<html><body><p>[Item]</p><p>{item.data.purchasePrice}</p></body></html>"
        annotated, fields = _annotate(html)
        out, top, loops = extract_loops(annotated, fields)
        self.assertEqual(loops, [])
        self.assertIn("[Item]", out)
        self.assertEqual(len(top), 1)

    def test_conditional_blocks_untouched(self) -> None:
        html = (
            "<html><body>"
            "<p>[[Theft cover is included.]]$doc.cond1</p>"
            "<p>[Item]</p><p>$TBD_item.data.purchasePrice</p><p>[/Item]</p>"
            "</body></html>"
        )
        out, _, loops = extract_loops(html, [])
        self.assertIn("[[Theft cover is included.]]$doc.cond1", out)
        self.assertEqual(len(loops), 1)


COND_LOOP_HTML = """<html>
<body>
<p>Dear {account.data.firstName},</p>
<p>[[Gift items included:</p>
<p>[Item]</p>
<p>Gift: {item.data.itemTypeCode} at {item.data.purchasePrice}</p>
<p>[/Item]</p>
<p>Subject to availability.]]</p>
<p>[[Theft cover is included.]]</p>
</body>
</html>"""


def _annotate_with_conds(html: str) -> tuple[str, list[dict], list[dict]]:
    fields = extract_fields(html)
    annotated = annotate_fields(html, fields)
    blocks = extract_conditionals(annotated)
    annotated = annotate_conditionals(annotated, blocks)
    return annotated, fields, blocks


class TestLoopInsideConditional(unittest.TestCase):
    def test_block_flips_to_template_render(self) -> None:
        annotated, fields, blocks = _annotate_with_conds(COND_LOOP_HTML)
        out, top, loops = extract_loops(annotated, fields, cond_blocks=blocks)
        self.assertEqual(blocks[0].get("render"), "template")
        self.assertIsNone(blocks[1].get("render"))
        self.assertIn("#if($doc.cond1)", out)
        self.assertIn("#foreach ($item in $TBD_Item)", out)
        # The flipped block's [[ ]] wrapper is gone; the plain block keeps its.
        self.assertNotIn("[[Gift items included:", out)
        self.assertIn("[[Theft cover is included.]]$doc.cond2", out)
        # Guard #end (block) and loop #end both present.
        self.assertEqual(out.count("#end"), 2)
        self.assertEqual(len(loops), 1)
        self.assertEqual(
            sorted(f["name"] for f in loops[0]["fields"]),
            ["item.data.itemTypeCode", "item.data.purchasePrice"],
        )

    def test_loop_crossing_block_boundary_refused(self) -> None:
        # Opener inside the block, closer outside — a genuine crossing.
        crossing = (
            "<html><body>"
            "<p>[[Gift items: [Item] x]]$doc.cond1</p>"
            "<p>[/Item]</p>"
            "</body></html>"
        )
        blocks = [{"id": 1, "source_text": "x", "top_level": True}]
        out, _, loops = extract_loops(crossing, [], cond_blocks=blocks)
        self.assertEqual(loops, [])
        self.assertIn("[Item]", out)
        self.assertNotIn("render", blocks[0])

    def test_loop_inside_nested_conditional_refused(self) -> None:
        html = (
            "<html><body>"
            "<p>[[outer [[inner [Item] $TBD_item.data.purchasePrice [/Item]]]$doc.cond2 tail]]$doc.cond1</p>"
            "</body></html>"
        )
        blocks = [
            {"id": 1, "source_text": "outer", "top_level": True},
            {"id": 2, "source_text": "inner", "top_level": False},
        ]
        out, _, loops = extract_loops(html, [], cond_blocks=blocks)
        self.assertEqual(loops, [])
        self.assertIn("[Item]", out)
        self.assertNotIn("render", blocks[0])
        self.assertNotIn("render", blocks[1])

    def test_conditional_inside_loop_allowed(self) -> None:
        html = (
            "<html><body>"
            "<p>[Item]</p>"
            "<p>[[per-item note]]$doc.cond1</p>"
            "<p>[/Item]</p>"
            "</body></html>"
        )
        blocks = [{"id": 1, "source_text": "per-item note", "top_level": True}]
        out, _, loops = extract_loops(html, [], cond_blocks=blocks)
        self.assertEqual(len(loops), 1)
        self.assertIn("[[per-item note]]$doc.cond1", out)
        self.assertNotIn("render", blocks[0])

    def test_csv_round_trip_carries_render_flag(self) -> None:
        # Variants-only Decision A: the loop-in-conditional block (render:template)
        # rides as a when-only CSV row; the sidecar carries the render flag.
        annotated, fields, blocks = _annotate_with_conds(COND_LOOP_HTML)
        extract_loops(annotated, fields, cond_blocks=blocks)
        # blocks[0] → cond1 (template), blocks[1] → cond2 (binary).
        csv_text = (
            "placeholder,when,text\n"
            "cond1,policy.data.discountAmount present,\n"      # template: when-only
            "cond2,policy.data.discountAmount present,Theft cover is included.\n"
            "cond2,,\n"                                         # binary empty-default row
        )
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "x.variants.csv"
            csv_path.write_text(csv_text, encoding="utf-8")
            sidecar = Path(td) / "x.conditional-blocks.yaml"
            write_conditional_blocks(blocks, sidecar)
            meta = load_conditional_blocks(sidecar)
            parsed = parse_variants_csv_to_blocks(csv_path, meta)
        self.assertEqual(parsed[0].get("render"), "template")
        self.assertNotIn("render", parsed[1])

    def test_leg3_rewrites_template_guard(self) -> None:
        vm = "#if($doc.cond3)\ncontent\n#end\n[[plain]]$doc.cond4\n"
        out = apply_cond_substitutions(vm, {"$doc.cond4": "${data.cond4}"})
        self.assertIn("#if($data.cond3)", out)
        self.assertNotIn("$doc.cond3", out)
        self.assertIn("${data.cond4}", out)

    def test_leg4_template_block_puts_boolean(self) -> None:
        blocks = [
            {
                "id": 1,
                "source_text": "Gift: $TBD_item.data.purchasePrice",
                "conditions": ["policy.data.discountAmount != null"],
                "operator": "AND",
                "render": "template",
            },
        ]
        policy = render_conditional_puts(blocks, scope="policy")
        self.assertIn('renderingData.put("cond1", segment.data().discountAmount() != null);', policy)
        self.assertNotIn("String cond1", policy)
        self.assertNotIn("$TBD_", policy)
        # Out-of-scope overload and unfilled conditions put false, never "".
        quote = render_conditional_puts(blocks, scope="quote")
        self.assertIn('renderingData.put("cond1", false);', quote)
        unfilled = render_conditional_puts(
            [{**blocks[0], "conditions": []}], scope="policy"
        )
        self.assertIn('renderingData.put("cond1", false);', unfilled)

    def test_leg4_field_analysis_skips_template_blocks(self) -> None:
        blocks = [
            {
                "id": 1,
                "source_text": "Gift: $TBD_item.data.purchasePrice",
                "conditions": ["policy.data.discountAmount != null"],
                "operator": "AND",
                "render": "template",
            },
        ]
        lookup = {
            "item.data.purchasePrice": {
                "data_source": "",
                "scope": "policy",
                "unsupported_reason": "",
            },
        }
        unresolved, unsupported, mixed = _analyse_cond_fields(blocks, lookup)
        self.assertEqual(unresolved, [])
        self.assertEqual(unsupported, [])
        self.assertEqual(mixed, [])

    def test_mapping_shape_validates(self) -> None:
        annotated, fields = _annotate(PARA_LOOP_HTML)
        _, top, loops = extract_loops(annotated, fields)
        data = _normalise_for_leg2(top, "x.annotated.html", loops=loops)
        validate_contract(data, MappingDoc, artifact="mapping.yaml", path=None)
        self.assertEqual(len(data["loops"]), 1)
        entry = data["loops"][0]
        self.assertEqual(entry["placeholder"], "$TBD_Item")
        self.assertEqual(entry["type"], "loop")
        self.assertEqual(entry["detection"], "marker")
        self.assertEqual(entry["data_source"], "")
        for fld in entry["fields"]:
            self.assertEqual(fld["type"], "loop_field")
            self.assertEqual(fld["context"]["loop"], "Item")
        names = [v["name"] for v in data["variables"]]
        self.assertNotIn("item.data.purchasePrice", names)


if __name__ == "__main__":
    unittest.main()
