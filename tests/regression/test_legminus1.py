"""Regression tests — Leg -1 (bare {leaf} → full accessor resolution).

Covers: the registry-only candidate index, bare-leaf matching (exact / dedupe /
loop-scoped / within-scope ambiguity / unmatched), placeholder + loop-membership
extraction, the path-review round-trip parse, and Leg 0's --path-map application.
No JAR / SDK is consulted — these are pure registry matches.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from velocity_converter.leg0_ingest import apply_path_map
from velocity_converter.legminus1_resolve_paths import (
    collect_placeholders,
    parse_path_review,
    resolve_fields,
)
from velocity_converter.registry_match import build_candidate_index, match_leaf

_REGISTRY = Path(__file__).resolve().parents[2] / "registry" / "path-registry.yaml"


def _reg() -> dict:
    return yaml.safe_load(_REGISTRY.read_text(encoding="utf-8"))


class TestCandidateIndex(unittest.TestCase):
    def test_account_field_accessor(self):
        cands = build_candidate_index(_reg())
        firstname = [c for c in cands if c["leaf"] == "firstname"]
        self.assertTrue(firstname)
        self.assertIn("account.data.firstName", {c["accessor"] for c in firstname})

    def test_exposure_fields_tagged_with_exposure(self):
        cands = build_candidate_index(_reg())
        itc = [c for c in cands if c["leaf"] == "itemtypecode"]
        self.assertTrue(itc)
        self.assertEqual(itc[0]["exposure"], "Item")
        self.assertEqual(itc[0]["accessor"], "item.data.itemTypeCode")


class TestMatchLeaf(unittest.TestCase):
    def setUp(self):
        self.cands = build_candidate_index(_reg(), roots=["segment"])

    def test_exact_unique(self):
        r = match_leaf("firstName", None, self.cands)
        self.assertEqual(r["status"], "resolved")
        self.assertEqual(r["match"], "exact")
        self.assertEqual(r["chosen"], "account.data.firstName")

    def test_same_accessor_is_not_ambiguous(self):
        # firstName exists in account_paths AND mirrored as a DataFetcher row;
        # both collapse to one accessor → resolved, not ambiguous.
        r = match_leaf("firstName", None, self.cands)
        self.assertEqual(r["status"], "resolved")

    def test_loop_scoped(self):
        r = match_leaf("purchasePrice", "Item", self.cands)
        self.assertEqual(r["status"], "resolved")
        self.assertEqual(r["chosen"], "item.data.purchasePrice")

    def test_within_scope_ambiguity(self):
        # 'premium' inside the Item loop matches three coverage charges → human pick.
        r = match_leaf("premium", "Item", self.cands)
        self.assertEqual(r["status"], "ambiguous")
        self.assertEqual(r["chosen"], "")
        self.assertGreaterEqual(len(r["alternatives"]), 2)

    def test_unmatched(self):
        r = match_leaf("totallyNotAField", None, self.cands)
        self.assertEqual(r["status"], "unmatched")
        self.assertEqual(r["chosen"], "")

    def test_exact_beats_name_similar(self):
        # policyNumber (system, exact) wins over reservedPolicyNumber (name-similar).
        r = match_leaf("policyNumber", None, self.cands)
        self.assertEqual(r["status"], "resolved")
        self.assertEqual(r["chosen"], "policy.policyNumber")


class TestPlaceholderExtraction(unittest.TestCase):
    def test_loop_membership(self):
        text = (
            "Dear {firstName}, [Item] type {itemTypeCode} price {purchasePrice} [/Item]"
        )
        fields = collect_placeholders(text)
        by_leaf = {f["leaf"]: f for f in fields}
        self.assertIsNone(by_leaf["firstName"]["loop"])
        self.assertEqual(by_leaf["itemTypeCode"]["loop"], "Item")
        self.assertEqual(by_leaf["purchasePrice"]["loop"], "Item")

    def test_field_in_and_out_of_loop_is_document_level(self):
        text = "Total {premium}. [Item] cover {premium} [/Item]"
        fields = collect_placeholders(text)
        self.assertIsNone(fields[0]["loop"])

    def test_occurrence_symbol(self):
        fields = collect_placeholders("Items: {+itemTypeCode}")
        self.assertEqual(fields[0]["occurrence"], "one_or_more")


class TestResolveFields(unittest.TestCase):
    def test_non_iterable_loop_demoted(self):
        fields = [{"leaf": "firstName", "occurrence": "required", "loop": "NotAnIterable"}]
        results = resolve_fields(fields, _reg(), ["segment"])
        self.assertIsNone(results[0]["loop"])
        self.assertIn("not a registry iterable", results[0]["warn"])


class TestPathReviewRoundTrip(unittest.TestCase):
    def test_parse_final_and_scope(self):
        md = (
            "# Path Review — X\n\n"
            "<!-- legminus1 input: /tmp/X(segment).docx -->\n"
            "<!-- legminus1 source: X(segment).docx -->\n\n"
            "---\n\n## Field: {firstName}\n\n"
            "- Scope: document-level\n- Occurrence: required\n"
            "- Status: resolved (exact)\nFinal: account.data.firstName\n\n"
            "---\n\n## Field: {purchasePrice}\n\n"
            "- Scope: loop: Item\n- Occurrence: required\nFinal: item.data.purchasePrice\n"
        )
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "X(segment).path-review.md"
            p.write_text(md, encoding="utf-8")
            entries, input_path, source = parse_path_review(p)
        by_leaf = {e["leaf"]: e for e in entries}
        self.assertEqual(by_leaf["firstName"]["chosen"], "account.data.firstName")
        self.assertEqual(by_leaf["purchasePrice"]["scope"], "loop: Item")
        self.assertEqual(str(input_path), "/tmp/X(segment).docx")
        self.assertEqual(source, "X(segment).docx")


class TestLeg0ApplyPathMap(unittest.TestCase):
    def test_apply_preserves_occurrence_symbol(self):
        import tempfile
        data = {"fields": [
            {"leaf": "firstName", "chosen": "account.data.firstName"},
            {"leaf": "itemTypeCode", "chosen": "item.data.itemTypeCode"},
            {"leaf": "unresolved", "chosen": ""},
        ]}
        html = "<p>Dear {firstName}. Items {+itemTypeCode}. Ref {unresolved}.</p>"
        with tempfile.TemporaryDirectory() as d:
            pm = Path(d) / "X.path-map.yaml"
            pm.write_text(yaml.dump(data), encoding="utf-8")
            out = apply_path_map(html, pm)
        self.assertIn("{account.data.firstName}", out)
        self.assertIn("{+item.data.itemTypeCode}", out)  # occurrence symbol kept
        self.assertIn("{unresolved}", out)  # empty chosen left untouched


if __name__ == "__main__":
    unittest.main()
