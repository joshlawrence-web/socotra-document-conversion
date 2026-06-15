"""Regression tests — Leg 0 variant block detection + CSV stub (§1a / 50-state).

Covers: [[$token]] → variant block with a named key; binary blocks keep their
cond<id> key (byte-identical annotation); duplicate-key fallback; the
conditional-form variant pointer; and the variants.csv stub shape.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from velocity_converter.leg0_ingest import (
    annotate_conditionals,
    extract_conditionals,
    parse_conditional_form,
    write_conditional_form,
    write_variants_csv_stub,
)

# Minimal registry for variant-merge validation (policy custom string field).
_REGISTRY = {
    "policy_data": [
        {"velocity": "$data.data.state", "category": "policy_data", "base_type": "string"},
    ],
}

_FORM = (
    "# Conditional Text Review — Demo\n\n"
    "---\n\n## Block 1\n\n> $stateClause\n\n"
    "Variant placeholder: `$stateClause` — fill `Demo.variants.csv`. No `Condition:` line needed.\n"
)


def _setup(d: str, csv_text: str) -> Path:
    form = Path(d) / "Demo.conditional-form.md"
    form.write_text(_FORM)
    (Path(d) / "Demo.variants.csv").write_text(csv_text)
    return form


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


class TestFormsAndStub(unittest.TestCase):
    def test_form_variant_pointer(self):
        blocks = extract_conditionals("<p>[[$stateClause]]</p><p>[[literal]]</p>")
        with TemporaryDirectory() as d:
            out = Path(d) / "Demo.conditional-form.md"
            write_conditional_form(blocks, "Demo", out)
            text = out.read_text()
        self.assertIn("Variant placeholder: `$stateClause`", text)
        self.assertIn("Demo.variants.csv", text)
        # Binary block still gets a Condition: line.
        self.assertIn("Condition:", text)

    def test_csv_stub_shape(self):
        blocks = extract_conditionals("<p>[[$stateClause]]</p>")
        with TemporaryDirectory() as d:
            out = Path(d) / "Demo.variants.csv"
            write_variants_csv_stub(blocks, "Demo", out)
            text = out.read_text()
        self.assertIn("placeholder,when,text", text)
        self.assertIn("stateClause", text)
        # One example conditioned row + one default (empty when) row.
        data_rows = [ln for ln in text.splitlines() if ln.startswith("stateClause")]
        self.assertEqual(len(data_rows), 2)

    def test_no_stub_without_variants(self):
        blocks = extract_conditionals("<p>[[literal]]</p>")
        with TemporaryDirectory() as d:
            out = Path(d) / "Demo.variants.csv"
            write_variants_csv_stub(blocks, "Demo", out)
            self.assertFalse(out.exists())


class TestParseFormMerge(unittest.TestCase):
    GOOD_CSV = (
        "placeholder,when,text\n"
        'stateClause,"state == ""CA""","California text"\n'
        "stateClause,,Default text\n"
    )

    def test_merges_sibling_csv(self):
        with TemporaryDirectory() as d:
            form = _setup(d, self.GOOD_CSV)
            blocks = parse_conditional_form(form, registry=_REGISTRY)
        b = blocks[0]
        self.assertTrue(b["variant"])
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
            form = _setup(d, bad)
            with self.assertRaises(ValueError):
                parse_conditional_form(form, registry=_REGISTRY)

    def test_missing_csv_raises(self):
        with TemporaryDirectory() as d:
            form = Path(d) / "Demo.conditional-form.md"
            form.write_text(_FORM)
            with self.assertRaises(ValueError):
                parse_conditional_form(form, registry=_REGISTRY)


if __name__ == "__main__":
    unittest.main()
