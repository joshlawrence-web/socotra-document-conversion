"""Regression tests — Leg 0 variant block detection + CSV stub (§1a / 50-state).

Covers: [[$token]] → variant block with a named key; bare [[text]] blocks and
duplicate tokens are hard errors (with a table hint); the variants.csv stub
shape (variant + loop when-only rows); and the variants-only round-trip
(variants.csv + machine sidecar → parse_variants_csv_to_blocks), including the
blank-when unconditional loop row.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from velocity_converter.leg0_ingest import (
    annotate_conditionals,
    extract_conditionals,
    extract_loops,
    load_conditional_blocks,
    parse_variants_csv_to_blocks,
    write_conditional_blocks,
    write_variants_csv,
)

# Minimal registry for variant-merge validation (policy custom string field).
_REGISTRY = {
    "policy_data": [
        {"velocity": "$data.data.state", "category": "policy_data", "base_type": "string"},
    ],
}


def _setup(d: str, csv_text: str, blocks: list[dict]) -> tuple[Path, list[dict]]:
    """Write a filled variants.csv + its machine sidecar; return (csv_path, meta)."""
    csv_path = Path(d) / "Demo.variants.csv"
    csv_path.write_text(csv_text)
    sidecar = Path(d) / "Demo.conditional-blocks.yaml"
    write_conditional_blocks(blocks, sidecar)
    return csv_path, load_conditional_blocks(sidecar)


def _loop_blocks(html: str) -> list[dict]:
    """extract_conditionals + extract_loops → the mutated block list."""
    blocks = extract_conditionals(html)
    extract_loops(html, [], cond_blocks=blocks)
    return blocks


class TestVariantDetection(unittest.TestCase):
    def test_variant_block_named_key(self):
        blocks = extract_conditionals("<p>[[$stateClause]]</p>")
        self.assertEqual(len(blocks), 1)
        b = blocks[0]
        self.assertTrue(b["variant"])
        self.assertEqual(b["placeholder"], "stateClause")
        self.assertEqual(b["key"], "stateClause")

    def test_bare_block_raises(self):
        with self.assertRaises(ValueError) as ctx:
            extract_conditionals("<p>[[some literal text]]</p>")
        self.assertIn("bare [[text]] blocks are not supported", str(ctx.exception))
        self.assertIn("some literal text", str(ctx.exception))

    def test_bare_block_error_lists_all_offenders(self):
        with self.assertRaises(ValueError) as ctx:
            extract_conditionals("<p>[[first]]</p><p>[[$ok]]</p><p>[[second]]</p>")
        msg = str(ctx.exception)
        self.assertIn("first", msg)
        self.assertIn("second", msg)

    def test_variant_annotation_uses_token(self):
        html = "<p>[[$stateClause]]</p>"
        blocks = extract_conditionals(html)
        self.assertEqual(annotate_conditionals(html, blocks), "<p>[[$stateClause]]$doc.stateClause</p>")

    def test_multi_word_dollar_raises(self):
        # "$state clause" is not a single identifier → bare block → error.
        with self.assertRaises(ValueError):
            extract_conditionals("<p>[[$state clause]]</p>")

    def test_duplicate_variant_key_dedupes_to_one_block(self):
        # A block's text lives in the CSV keyed by name — a repeated marker is
        # the same content by definition (e.g. a shared label reused across
        # benefit blocks). One block registers; every occurrence annotates.
        blocks = extract_conditionals("<p>[[$dup]]</p><p>[[$dup]]</p>")
        self.assertEqual([b["key"] for b in blocks], ["dup"])
        annotated = annotate_conditionals("<p>[[$dup]]</p><p>[[$dup]]</p>", blocks)
        self.assertEqual(annotated.count("[[$dup]]$doc.dup"), 2)

    def test_bare_block_with_table_adds_hint(self):
        html = (
            "<p>[[Optional cover applies.</p>\n"
            "<table><tr><td>Item</td><td>Limit</td></tr></table>\n"
            "<p>See schedule.]]</p>"
        )
        with self.assertRaises(ValueError) as ctx:
            extract_conditionals(html)
        self.assertIn("<table>", str(ctx.exception))


class TestVariantsCsvStub(unittest.TestCase):
    def test_csv_stub_shape(self):
        # A variant block's $token rows + a loop's when-only row in one CSV.
        html = "<p>[[$stateClause]]</p>\n<p>[Item/]</p>\n<p>{x}</p>\n<p>[/Item]</p>"
        blocks = _loop_blocks(html)
        with TemporaryDirectory() as d:
            out = Path(d) / "Demo.variants.csv"
            write_variants_csv(blocks, "Demo", out)
            text = out.read_text()
        self.assertIn("placeholder,when,text", text)
        # One example conditioned row + one default (empty when) row for the variant.
        data_rows = [ln for ln in text.splitlines() if ln.startswith("stateClause")]
        self.assertEqual(len(data_rows), 2)
        # The loop lands in the SAME CSV as a single when-only row under its name.
        loop_rows = [ln for ln in text.splitlines() if ln.startswith("Item")]
        self.assertEqual(loop_rows, ["Item,,"])

    def test_no_csv_without_blocks(self):
        with TemporaryDirectory() as d:
            out = Path(d) / "Demo.variants.csv"
            write_variants_csv([], "Demo", out)
            self.assertFalse(out.exists())

    def test_stub_has_no_fabricated_conditions(self):
        # The stub lists blocks with blank `when` cells — no invented sample
        # conditions for the customer to delete.
        blocks = extract_conditionals("<p>[[$note]]</p>")
        with TemporaryDirectory() as d:
            out = Path(d) / "Demo.variants.csv"
            write_variants_csv(blocks, "Demo", out)
            text = out.read_text()
        self.assertNotIn("!= null", text)
        import csv  # noqa: PLC0415
        lines = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
        rows = list(csv.reader(lines))[1:]  # drop the column header
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row[1].strip(), "", f"stub row has a fabricated when: {row}")

    def test_does_not_clobber_edited_csv(self):
        # Gap 2: a re-ingest must not overwrite a customer's filled CSV.
        blocks = extract_conditionals("<p>[[$note]]</p>")
        with TemporaryDirectory() as d:
            out = Path(d) / "Demo.variants.csv"
            write_variants_csv(blocks, "Demo", out)
            # Simulate the customer filling in the first blank row.
            edited = out.read_text().replace("note,,", 'note,"state == ""CA""",Cover applies', 1)
            assert edited != out.read_text(), "test edit must actually change the stub"
            out.write_text(edited, encoding="utf-8")
            # Re-ingest (same blocks) must keep the edited content, not regenerate.
            write_variants_csv(blocks, "Demo", out)
            self.assertEqual(out.read_text(), edited)

    def test_rewrites_identical_csv(self):
        # An unedited CSV is a harmless no-op rewrite (content identical).
        blocks = extract_conditionals("<p>[[$note]]</p>")
        with TemporaryDirectory() as d:
            out = Path(d) / "Demo.variants.csv"
            write_variants_csv(blocks, "Demo", out)
            first = out.read_text()
            write_variants_csv(blocks, "Demo", out)
            self.assertEqual(out.read_text(), first)

    def test_reingest_drops_orphans_keeps_edits_appends_new(self):
        # A re-ingest of a DIFFERENT document (or a doc with a marker removed)
        # must reconcile the CSV to the current blocks: keep the edited surviving
        # row, drop the departed block's orphan rows, append the new block's stub.
        # This is the CGL "Pet" residue fix.
        with TemporaryDirectory() as d:
            out = Path(d) / "Demo.variants.csv"
            write_variants_csv(extract_conditionals("<p>[[$alpha]]</p><p>[[$beta]]</p>"),
                               "Demo", out)
            edited = out.read_text().replace("alpha,,", 'alpha,"state == ""CA""",Keep me', 1)
            assert edited != out.read_text(), "test edit must actually change the stub"
            out.write_text(edited, encoding="utf-8")
            # Re-ingest: beta departed, gamma is new; alpha survives.
            write_variants_csv(extract_conditionals("<p>[[$alpha]]</p><p>[[$gamma]]</p>"),
                               "Demo", out)
            result = out.read_text()
        self.assertIn('alpha,"state == ""CA""",Keep me', result)  # edit preserved
        self.assertNotIn("beta", result)                          # orphan dropped
        self.assertIn("gamma", result)                            # new block appended


class TestParseVariantsCsvMerge(unittest.TestCase):
    GOOD_CSV = (
        "placeholder,when,text\n"
        'stateClause,"state == ""CA""","California text"\n'
        "stateClause,,Default text\n"
    )

    def _blocks(self):
        return extract_conditionals("<p>[[$stateClause]]</p>")

    def test_merges_sibling_csv(self):
        with TemporaryDirectory() as d:
            csv_path, meta = _setup(d, self.GOOD_CSV, self._blocks())
            blocks = parse_variants_csv_to_blocks(csv_path, meta, registry=_REGISTRY)
        b = blocks[0]
        self.assertEqual(b["key"], "stateClause")
        self.assertEqual(b["scope"], "policy")
        self.assertEqual(b["default"], "Default text")
        self.assertEqual(len(b["variants"]), 1)
        self.assertEqual(b["variants"][0]["when"]["path"], "policy.data.state")

    def test_bad_csv_raises(self):
        bad = (
            "placeholder,when,text\n"
            "stateClause,not a condition,x\n"
            "stateClause,,d\n"
        )
        with TemporaryDirectory() as d:
            csv_path, meta = _setup(d, bad, self._blocks())
            with self.assertRaises(ValueError):
                parse_variants_csv_to_blocks(csv_path, meta, registry=_REGISTRY)

    def test_missing_rows_raises(self):
        # Sidecar declares the block but the CSV has no rows for it.
        empty_csv = "placeholder,when,text\n"
        with TemporaryDirectory() as d:
            csv_path, meta = _setup(d, empty_csv, self._blocks())
            with self.assertRaises(ValueError):
                parse_variants_csv_to_blocks(csv_path, meta, registry=_REGISTRY)

    def test_default_only_variant_is_valid(self):
        # A variant block filled with a single blank-`when` (default) row and no
        # conditioned row is valid: it always renders that text. This is the
        # natural "just fill the text" case after sample conditions were dropped.
        default_only = (
            "placeholder,when,text\n"
            "stateClause,,Always this text\n"
        )
        with TemporaryDirectory() as d:
            csv_path, meta = _setup(d, default_only, self._blocks())
            blocks = parse_variants_csv_to_blocks(csv_path, meta, registry=_REGISTRY)
        b = blocks[0]
        self.assertEqual(b["key"], "stateClause")
        self.assertEqual(b["default"], "Always this text")
        self.assertEqual(b["variants"], [])
        self.assertEqual(b["scope"], "")  # no conditions → no scope


class TestLoopWhenRows(unittest.TestCase):
    _HTML = "<p>[Item/]</p>\n<p>{x}</p>\n<p>[/Item]</p>"

    def test_filled_when_becomes_template_block(self):
        filled = (
            "placeholder,when,text\n"
            'Item,"state == ""CA""",\n'
        )
        with TemporaryDirectory() as d:
            csv_path, meta = _setup(d, filled, _loop_blocks(self._HTML))
            blocks = parse_variants_csv_to_blocks(csv_path, meta, registry=_REGISTRY)
        self.assertEqual(len(blocks), 1)
        b = blocks[0]
        self.assertEqual(b["key"], "Item")
        self.assertEqual(b["render"], "template")
        self.assertEqual(len(b["variants"]), 1)
        self.assertIsNone(b["default"])

    def test_blank_when_omits_loop_from_registry(self):
        blank = "placeholder,when,text\nItem,,\n"
        with TemporaryDirectory() as d:
            csv_path, meta = _setup(d, blank, _loop_blocks(self._HTML))
            blocks = parse_variants_csv_to_blocks(csv_path, meta, registry=_REGISTRY)
        self.assertEqual(blocks, [])  # unconditional loop → no registry entry

    def test_loop_row_with_text_raises(self):
        with_text = "placeholder,when,text\nItem,,stray wording\n"
        with TemporaryDirectory() as d:
            csv_path, meta = _setup(d, with_text, _loop_blocks(self._HTML))
            with self.assertRaises(ValueError) as ctx:
                parse_variants_csv_to_blocks(csv_path, meta, registry=_REGISTRY)
        self.assertIn("take no text", str(ctx.exception))

    def test_loop_name_colliding_with_token_raises(self):
        html = "<p>[[$Item]]</p>\n<p>[Item/]</p>\n<p>{x}</p>\n<p>[/Item]</p>"
        with self.assertRaises(ValueError) as ctx:
            _loop_blocks(html)
        self.assertIn("collides", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
