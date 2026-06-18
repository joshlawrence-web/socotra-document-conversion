"""Regression tests — Leg 0 variant block detection + CSV stub (§1a / 50-state).

Covers: [[$token]] → variant block with a named key; binary blocks keep their
cond<id> key (byte-identical annotation); duplicate-key fallback; the
variants.csv stub shape; and the variants-only round-trip (variants.csv +
machine sidecar → parse_variants_csv_to_blocks).
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from velocity_converter.leg0_ingest import (
    annotate_conditionals,
    extract_conditionals,
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


class TestVariantDetection(unittest.TestCase):
    def test_variant_block_named_key(self):
        blocks = extract_conditionals("<p>[[$stateClause]]</p>")
        self.assertEqual(len(blocks), 1)
        b = blocks[0]
        self.assertTrue(b["variant"])
        self.assertEqual(b["placeholder"], "stateClause")
        self.assertEqual(b["key"], "stateClause")

    def test_binary_block_keeps_cond_key(self):
        blocks = extract_conditionals("<p>[[some literal text]]</p>")
        self.assertFalse(blocks[0]["variant"])
        self.assertEqual(blocks[0]["key"], "cond1")

    def test_binary_annotation_byte_identical(self):
        html = "<p>[[literal]]</p>"
        blocks = extract_conditionals(html)
        self.assertEqual(annotate_conditionals(html, blocks), "<p>[[literal]]$doc.cond1</p>")

    def test_variant_annotation_uses_token(self):
        html = "<p>[[$stateClause]]</p>"
        blocks = extract_conditionals(html)
        self.assertEqual(annotate_conditionals(html, blocks), "<p>[[$stateClause]]$doc.stateClause</p>")

    def test_multi_word_dollar_is_literal(self):
        # "$state clause" is not a single identifier → binary literal block.
        blocks = extract_conditionals("<p>[[$state clause]]</p>")
        self.assertFalse(blocks[0]["variant"])
        self.assertEqual(blocks[0]["key"], "cond1")

    def test_duplicate_variant_key_falls_back(self):
        blocks = extract_conditionals("<p>[[$dup]]</p><p>[[$dup]]</p>")
        keys = [b["key"] for b in blocks]
        self.assertIn("dup", keys)
        self.assertIn("cond2", keys)  # second collides → positional fallback
        self.assertFalse(blocks[1]["variant"])


class TestVariantsCsvStub(unittest.TestCase):
    def test_csv_stub_shape(self):
        # The variant block's $token row + a binary block both land in one CSV.
        blocks = extract_conditionals("<p>[[$stateClause]]</p><p>[[literal]]</p>")
        with TemporaryDirectory() as d:
            out = Path(d) / "Demo.variants.csv"
            write_variants_csv(blocks, "Demo", out)
            text = out.read_text()
        self.assertIn("placeholder,when,text", text)
        # The variant block keeps its named key.
        self.assertIn("stateClause", text)
        # One example conditioned row + one default (empty when) row for the variant.
        data_rows = [ln for ln in text.splitlines() if ln.startswith("stateClause")]
        self.assertEqual(len(data_rows), 2)
        # The binary block folds into the SAME CSV under its cond<id> key.
        self.assertTrue(any(ln.startswith("cond2") for ln in text.splitlines()))

    def test_no_csv_without_blocks(self):
        with TemporaryDirectory() as d:
            out = Path(d) / "Demo.variants.csv"
            write_variants_csv([], "Demo", out)
            self.assertFalse(out.exists())

    def test_stub_when_uses_present_not_null(self):
        # Gap 3: pre-filled `when` examples must be valid DSL — never `!= null`.
        blocks = extract_conditionals("<p>[[literal]]</p>")
        with TemporaryDirectory() as d:
            out = Path(d) / "Demo.variants.csv"
            write_variants_csv(blocks, "Demo", out)
            text = out.read_text()
        self.assertNotIn("!= null", text)
        self.assertIn("present", text)

    def test_does_not_clobber_edited_csv(self):
        # Gap 2: a re-ingest must not overwrite a customer's filled CSV.
        blocks = extract_conditionals("<p>[[literal]]</p>")
        with TemporaryDirectory() as d:
            out = Path(d) / "Demo.variants.csv"
            write_variants_csv(blocks, "Demo", out)
            edited = out.read_text().replace("quote.quoteNumber present", 'state == "CA"')
            out.write_text(edited, encoding="utf-8")
            # Re-ingest (same blocks) must keep the edited content, not regenerate.
            write_variants_csv(blocks, "Demo", out)
            self.assertEqual(out.read_text(), edited)

    def test_rewrites_identical_csv(self):
        # An unedited CSV is a harmless no-op rewrite (content identical).
        blocks = extract_conditionals("<p>[[literal]]</p>")
        with TemporaryDirectory() as d:
            out = Path(d) / "Demo.variants.csv"
            write_variants_csv(blocks, "Demo", out)
            first = out.read_text()
            write_variants_csv(blocks, "Demo", out)
            self.assertEqual(out.read_text(), first)


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


if __name__ == "__main__":
    unittest.main()
