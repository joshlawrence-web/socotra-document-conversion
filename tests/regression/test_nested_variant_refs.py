"""Regression — nested [[$x]] references inside a variant text cell.

A variant block's text may embed [[$other]], pointing at another row in the same
sheet. condition_dsl peels [[$x]] → $doc.x; parse_variants_csv_to_blocks synthesizes
a block for a nested-only label (referenced but absent from the sidecar) and validates
the reference graph (missing referent, self-ref, cycle, scope clash). Leg 4 then
composes the label into its referrer's plugin string (covered by the
TestNestedVariantLabel pipeline fixture).
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from velocity_converter.condition_dsl import _peel_nested_refs
from velocity_converter.leg0_ingest import (
    extract_conditionals,
    load_conditional_blocks,
    parse_variants_csv_to_blocks,
    write_conditional_blocks,
)


def _run(csv_text: str, marker_doc: str):
    """Parse a CSV against a sidecar built from a one-marker document."""
    blocks = extract_conditionals(marker_doc)
    with TemporaryDirectory() as d:
        csv_path = Path(d) / "Demo.variants.csv"
        csv_path.write_text(csv_text)
        sidecar = Path(d) / "Demo.conditional-blocks.yaml"
        write_conditional_blocks(blocks, sidecar)
        return parse_variants_csv_to_blocks(csv_path, load_conditional_blocks(sidecar))


class TestPeel(unittest.TestCase):
    def test_peels_nested_ref(self):
        self.assertEqual(_peel_nested_refs("Max[[$label]]: x"), "Max$doc.label: x")

    def test_leaves_plain_text(self):
        self.assertEqual(_peel_nested_refs("no refs here"), "no refs here")

    def test_ignores_binary_brackets(self):
        # [[literal]] (no leading $) is not a named ref — left untouched.
        self.assertEqual(_peel_nested_refs("[[just text]]"), "[[just text]]")


class TestSynthesis(unittest.TestCase):
    def test_nested_only_label_is_synthesized(self):
        csv = (
            "placeholder,when,text\n"
            "parentClause,policy.data.tier present,Gold[[$childLabel]] benefit\n"
            "parentClause,,Standard benefit\n"
            "childLabel,policy.data.tier present,gold tier\n"
            "childLabel,,\n"
        )
        blocks = _run(csv, "<p>[[$parentClause]]</p>")
        by_key = {b["key"]: b for b in blocks}
        # The nested-only label got its own block even though it has no doc marker.
        self.assertIn("childLabel", by_key)
        child = by_key["childLabel"]
        self.assertEqual(child["scope"], "policy")
        self.assertEqual(child["source_text"], "")  # no document marker
        self.assertEqual(len(child["variants"]), 1)
        # The parent's variant text carries the peeled machine ref.
        parent_text = by_key["parentClause"]["variants"][0]["text"]
        self.assertIn("$doc.childLabel", parent_text)


class TestGuards(unittest.TestCase):
    def test_missing_referent_raises(self):
        csv = (
            "placeholder,when,text\n"
            "parentClause,policy.data.tier present,X[[$ghost]]\n"
            "parentClause,,\n"
        )
        with self.assertRaisesRegex(ValueError, "ghost"):
            _run(csv, "<p>[[$parentClause]]</p>")

    def test_self_reference_raises(self):
        csv = (
            "placeholder,when,text\n"
            "selfie,policy.data.tier present,loops[[$selfie]]\n"
            "selfie,,\n"
        )
        with self.assertRaisesRegex(ValueError, "self-referential"):
            _run(csv, "<p>[[$selfie]]</p>")

    def test_cycle_raises(self):
        csv = (
            "placeholder,when,text\n"
            "a,policy.data.tier present,x[[$b]]\n"
            "a,,\n"
            "b,policy.data.tier present,y[[$a]]\n"
            "b,,\n"
        )
        with self.assertRaisesRegex(ValueError, "cycle"):
            _run(csv, "<p>[[$a]]</p>")

    def test_scope_clash_raises(self):
        # Parent conditions on policy.*, child on quote.* — the child's local would
        # not exist in the parent's overload.
        csv = (
            "placeholder,when,text\n"
            "parentClause,policy.data.tier present,X[[$childLabel]]\n"
            "parentClause,,\n"
            "childLabel,quote.data.region present,Y\n"
            "childLabel,,\n"
        )
        with self.assertRaisesRegex(ValueError, "scope"):
            _run(csv, "<p>[[$parentClause]]</p>")


if __name__ == "__main__":
    unittest.main()
