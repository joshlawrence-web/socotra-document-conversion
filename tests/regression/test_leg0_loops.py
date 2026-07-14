"""Regression tests — [Name/]...[/Name] loop sections in Leg 0.

Covers: marker detection (paragraph + table-row forms), the #if($doc.<Name>)
+ #foreach/#end + #end scaffold emission, loop-field membership (all
occurrences inside the section), unmatched/legacy-marker warnings,
[[$token]] non-interference, mapping shape (loop entry + loop_field context),
the per-loop when-only row (template block appended to cond_blocks), and the
Leg 3 guard rewrite/strip + Leg 4 Boolean put. No JARs required.
"""

from __future__ import annotations

import contextlib
import io
import unittest

from velocity_converter.leg0_ingest import (
    _normalise_for_leg2,
    annotate_fields,
    extract_fields,
    extract_loops,
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
<p>[Item/]</p>
<p>{item.data.itemTypeCode} bought for {item.data.purchasePrice}</p>
<p>[/Item]</p>
<p>ZenCover Limited</p>
</body>
</html>"""

TABLE_LOOP_HTML = """<html>
<body>
<table>
  <tr><td>Type</td><td>Price</td></tr>
  <tr><td>[Item/]</td><td></td></tr>
  <tr><td>{item.data.itemTypeCode}</td><td>{item.data.purchasePrice}</td></tr>
  <tr><td>[/Item]</td><td></td></tr>
</table>
</body>
</html>"""


class TestExtractLoops(unittest.TestCase):
    def test_paragraph_markers_become_directive_lines(self) -> None:
        annotated, fields = _annotate(PARA_LOOP_HTML)
        html, top, loops = extract_loops(annotated, fields)
        self.assertIn("#if($doc.Item)\n#foreach ($item in $TBD_Item)\n", html)
        self.assertIn("\n#end\n#end\n", html)
        self.assertNotIn("[Item/]", html)
        self.assertNotIn("[/Item]", html)
        self.assertNotIn("<p>#if", html)
        self.assertNotIn("<p>#foreach", html)
        self.assertNotIn("#end</p>", html)

    def test_classed_paragraph_markers_become_directive_lines(self) -> None:
        # XHTML Writer filter emits <p class="paragraph-Standard"> around
        # markers — cleanup must still peel them so Leg 3 can strip a blank
        # when-guard. Without this, #if($data.Item) survives and hides the
        # loop when the plugin Boolean is absent.
        html = """<html><body>
<p class="paragraph-Standard">[Item/]</p>
<p class="paragraph-Standard">{item.data.itemTypeCode}</p>
<p class="paragraph-Standard">[/Item]</p>
</body></html>"""
        annotated, fields = _annotate(html)
        out, _, loops = extract_loops(annotated, fields)
        self.assertEqual(len(loops), 1)
        self.assertIn("#if($doc.Item)\n#foreach ($item in $TBD_Item)", out)
        self.assertNotRegex(out, r"<p[^>]*>#if")
        self.assertNotRegex(out, r"#end</p>")
        # Blank when → Leg 3 strips the guard; content must be bare lines.
        stripped = apply_cond_substitutions(out, {})
        self.assertNotIn("#if", stripped)
        self.assertIn("#foreach ($item in $TBD_Item)", stripped)

    def test_table_row_markers_become_directive_lines(self) -> None:
        annotated, fields = _annotate(TABLE_LOOP_HTML)
        html, top, loops = extract_loops(annotated, fields)
        self.assertIn("#if($doc.Item)\n#foreach ($item in $TBD_Item)", html)
        self.assertNotIn("<tr><td>#if", html)
        self.assertNotIn("<td>#end", html)
        # Header row stays outside the loop
        head, _, tail = html.partition("#foreach")
        self.assertIn("<tr><td>Type</td><td>Price</td></tr>", head)
        self.assertIn("$TBD_item.data.purchasePrice", tail)

    def test_xhtml_table_marker_rows_collapse_not_blank_gaps(self) -> None:
        # XHTML Writer puts [Item/] / [/Item] in their own <tr> with nbsp
        # sibling cells. Those rows must collapse to bare directives — if they
        # stay as <tr>s the PDF shows a huge gap between header and data.
        html = """<html><body>
<table>
<tr class="row"><td class="c"><p class="paragraph-Standard">Type</p></td>
<td class="c"><p class="paragraph-Standard">Price</p></td></tr>
<tr class="row"><td class="c"><p class="paragraph-Standard">[Item/]</p></td>
<td class="c"><p class="paragraph-Standard">\u00a0</p></td></tr>
<tr class="row"><td class="c"><p class="paragraph-Standard">{item.data.itemTypeCode}</p></td>
<td class="c"><p class="paragraph-Standard">{item.data.purchasePrice}</p></td></tr>
<tr class="row"><td class="c"><p class="paragraph-Standard">[/Item]</p></td>
<td class="c"><p class="paragraph-Standard">\u00a0</p></td></tr>
</table>
</body></html>"""
        annotated, fields = _annotate(html)
        out, _, loops = extract_loops(annotated, fields)
        self.assertEqual(len(loops), 1)
        self.assertIn("#if($doc.Item)\n#foreach ($item in $TBD_Item)", out)
        self.assertIn("#end\n#end", out)
        # Directives must be bare lines — not inside a <tr> and not glued to tags.
        for line in out.splitlines():
            if "#foreach" in line or line.strip() in {"#end", "#if($doc.Item)"} or line.startswith("#if($doc."):
                self.assertNotIn("<", line, msg=repr(line))
                self.assertNotIn(">", line, msg=repr(line))
        # Data row remains a real <tr>.
        self.assertRegex(out, r"<tr[^>]*>[\s\S]*?\$TBD_item\.data\.itemTypeCode")
        stripped = apply_cond_substitutions(out, {})
        self.assertNotIn("#if", stripped)
        self.assertIn("#foreach ($item in $TBD_Item)", stripped)
        # foreach still on its own line after strip
        self.assertTrue(
            any(line.strip().startswith("#foreach") and "<" not in line
                for line in stripped.splitlines())
        )

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

    def test_loop_field_followed_by_period_stays_in_loop(self) -> None:
        # Regression: a dotted-accessor placeholder ending a sentence (trailing
        # `.`) must still be recognised as a loop field. The membership regex's
        # `(?![\w.])` lookahead used to reject the trailing period, dropping the
        # field to document scope (and losing its #if($item.Cov) coverage guard).
        html = (
            "<html><body>"
            "<p>[Item/]</p>"
            "<p>Cover: parts {item.AccidentalDamage.data.partsCovered}.</p>"
            "<p>[/Item]</p>"
            "</body></html>"
        )
        annotated, fields = _annotate(html)
        _, top, loops = extract_loops(annotated, fields)
        self.assertEqual(
            [f["name"] for f in loops[0]["fields"]],
            ["item.AccidentalDamage.data.partsCovered"],
        )
        self.assertEqual(top, [])

    def test_field_used_inside_and_outside_stays_top_level(self) -> None:
        html = (
            "<html><body>"
            "<p>Total: {item.data.purchasePrice}</p>"
            "<p>[Item/]</p><p>{item.data.purchasePrice}</p><p>[/Item]</p>"
            "</body></html>"
        )
        annotated, fields = _annotate(html)
        _, top, loops = extract_loops(annotated, fields)
        self.assertEqual([f["name"] for f in top], ["item.data.purchasePrice"])
        self.assertEqual(loops[0]["fields"], [])

    def test_unmatched_markers_left_as_literal(self) -> None:
        html = "<html><body><p>[Item/]</p><p>{item.data.purchasePrice}</p></body></html>"
        annotated, fields = _annotate(html)
        out, top, loops = extract_loops(annotated, fields)
        self.assertEqual(loops, [])
        self.assertIn("[Item/]", out)
        self.assertEqual(len(top), 1)

    def test_legacy_opener_warns_and_stays_literal(self) -> None:
        html = "<html><body><p>[Item]</p><p>{item.data.purchasePrice}</p><p>[/Item]</p></body></html>"
        annotated, fields = _annotate(html)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            out, _top, loops = extract_loops(annotated, fields)
        self.assertEqual(loops, [])
        self.assertIn("[Item]", out)
        self.assertIn("legacy loop syntax", stderr.getvalue())
        self.assertIn("[Item/]", stderr.getvalue())

    def test_plain_bracket_word_is_silent(self) -> None:
        # Prose in single brackets with no closer is not a loop attempt — no noise.
        html = "<html><body><p>see [note] above</p></body></html>"
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            out, _top, loops = extract_loops(html, [])
        self.assertEqual(loops, [])
        self.assertIn("[note]", out)
        self.assertEqual(stderr.getvalue(), "")

    def test_conditional_blocks_untouched(self) -> None:
        html = (
            "<html><body>"
            "<p>[[$theftNote]]$doc.theftNote</p>"
            "<p>[Item/]</p><p>$TBD_item.data.purchasePrice</p><p>[/Item]</p>"
            "</body></html>"
        )
        out, _, loops = extract_loops(html, [])
        self.assertIn("[[$theftNote]]$doc.theftNote", out)
        self.assertEqual(len(loops), 1)


class TestLoopWhenRow(unittest.TestCase):
    """Every [Name/] loop appends a render: template block (its when-only row)."""

    def test_loop_appends_template_block(self) -> None:
        annotated, fields = _annotate(PARA_LOOP_HTML)
        blocks: list[dict] = []
        out, _top, loops = extract_loops(annotated, fields, cond_blocks=blocks)
        self.assertEqual(len(loops), 1)
        self.assertEqual(len(blocks), 1)
        b = blocks[0]
        self.assertEqual(b["key"], "Item")
        self.assertEqual(b["render"], "template")
        self.assertFalse(b["variant"])
        self.assertIn("#if($doc.Item)", out)

    def test_loop_block_id_continues_after_tokens(self) -> None:
        blocks = [{"id": 1, "key": "theftNote", "placeholder": "theftNote", "variant": True}]
        annotated, fields = _annotate(PARA_LOOP_HTML)
        extract_loops(annotated, fields, cond_blocks=blocks)
        self.assertEqual([b["id"] for b in blocks], [1, 2])

    def test_conditional_inside_loop_allowed_but_warned(self) -> None:
        html = (
            "<html><body>"
            "<p>[Item/]</p>"
            "<p>[[$perItemNote]]$doc.perItemNote</p>"
            "<p>[/Item]</p>"
            "</body></html>"
        )
        blocks = [{"id": 1, "key": "perItemNote", "placeholder": "perItemNote", "variant": True}]
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            out, _, loops = extract_loops(html, [], cond_blocks=blocks)
        self.assertEqual(len(loops), 1)
        self.assertIn("[[$perItemNote]]$doc.perItemNote", out)
        self.assertIn("document-scoped", stderr.getvalue())
        # The token block is untouched; the loop's template block is appended.
        self.assertEqual(blocks[0].get("render"), None)
        self.assertEqual(blocks[1]["key"], "Item")


class TestLeg3GuardHandling(unittest.TestCase):
    def test_filled_when_guard_is_rewritten(self) -> None:
        vm = "#if($doc.Item)\n#foreach ($item in $data.segment.items)\nrow\n#end\n#end\n"
        out = apply_cond_substitutions(vm, {"$doc.Item": "${data.Item}"})
        self.assertIn("#if($data.Item)", out)
        self.assertNotIn("$doc.Item", out)

    def test_blank_when_guard_is_stripped(self) -> None:
        # No registry entry for Item → unconditional loop: guard pair removed,
        # loop content kept intact.
        vm = "#if($doc.Item)\n#foreach ($item in $data.segment.items)\nrow\n#end\n#end\n"
        out = apply_cond_substitutions(vm, {})
        self.assertNotIn("#if", out)
        self.assertNotIn("$doc.Item", out)
        self.assertIn("#foreach ($item in $data.segment.items)\nrow\n#end\n", out)
        self.assertEqual(out.count("#end"), 1)

    def test_strip_keeps_sibling_registered_guard(self) -> None:
        vm = (
            "#if($doc.Item)\n#foreach ($x in $y)\nrow\n#end\n#end\n"
            "#if($doc.Gift)\n#foreach ($g in $h)\ngift\n#end\n#end\n"
        )
        out = apply_cond_substitutions(vm, {"$doc.Gift": "${data.Gift}"})
        self.assertNotIn("$doc.Item", out)
        self.assertIn("#if($data.Gift)", out)


class TestLeg4TemplatePut(unittest.TestCase):
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


class TestMappingShape(unittest.TestCase):
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
