"""Regression tests — Leg 3 $TBD_ token substitution.

Focus: the `_TBD_TOKEN_RE` match boundary. A placeholder path is
`TBD_<seg>(.<seg>)*` and never ends in a dot, so a sentence-ending period
that immediately follows a token must NOT be swallowed into the token — doing
so makes the captured string miss the substitution map and leak `$TBD_*` into
the rendered template (observed live as Velocity error 216041
"Variable $TBD_quote has not been set"). No JARs required.
"""

from __future__ import annotations

import unittest

from velocity_converter.leg3_substitute import (
    _strip_unregistered_guards,
    _substitute_tokens,
    _to_quiet_ref,
    _TBD_TOKEN_RE,
    build_foreach_map,
    build_substitution_map,
    process_vm,
)

_SMAP = {
    "$TBD_account.data.firstName": "$data.account.data.firstName",
    "$TBD_account.data.lastName": "$data.account.data.lastName",
    "$TBD_quote.data.discountType": "$data.quote.data.discountType",
    "$TBD_account.data.email": "$data.account.data.email",
    "$TBD_Item": "$data.quote.items",
}


class TestTbdTokenBoundary(unittest.TestCase):
    def test_trailing_period_not_swallowed(self):
        # The live failure: token ends a sentence.
        line = "<p>Your discount type on file is $TBD_quote.data.discountType.</p>"
        self.assertEqual(
            _substitute_tokens(line, _SMAP),
            "<p>Your discount type on file is $data.quote.data.discountType.</p>",
        )

    def test_dotted_token_then_period(self):
        line = "Loyalty ref $TBD_account.data.email."
        self.assertEqual(_substitute_tokens(line, _SMAP), "Loyalty ref $data.account.data.email.")

    def test_bare_token_then_period(self):
        line = "loop=$TBD_Item."
        self.assertEqual(_substitute_tokens(line, _SMAP), "loop=$data.quote.items.")

    def test_comma_space_and_eol_still_work(self):
        # firstName/lastName worked before the fix because they are followed by
        # a comma and a space, not a period — guard against a regression there.
        line = "Dear $TBD_account.data.firstName $TBD_account.data.lastName,"
        self.assertEqual(
            _substitute_tokens(line, _SMAP),
            "Dear $data.account.data.firstName $data.account.data.lastName,",
        )
        self.assertEqual(
            _substitute_tokens("end $TBD_account.data.email", _SMAP),
            "end $data.account.data.email",
        )

    def test_regex_match_excludes_trailing_dot(self):
        m = _TBD_TOKEN_RE.search("is $TBD_quote.data.discountType.")
        self.assertEqual(m.group(0), "$TBD_quote.data.discountType")

    def test_unresolved_token_preserved(self):
        # DD-2: a token absent from the map is left untouched (not blanked).
        line = "ref $TBD_unknown.field."
        self.assertEqual(_substitute_tokens(line, _SMAP), line)

    def test_process_vm_end_to_end(self):
        vm = (
            "<p>Your discount type on file is $TBD_quote.data.discountType.</p>\n"
            "<p>Your loyalty reference is $TBD_account.data.email.</p>\n"
        )
        out = process_vm(vm, _SMAP, {})
        self.assertNotIn("$TBD_", out)
        self.assertIn("$data.quote.data.discountType.", out)
        self.assertIn("$data.account.data.email.", out)


class TestOptionalQuietRef(unittest.TestCase):
    """Optional ({$x}) fields must render null-safe; required ({x}) stay bare."""

    def test_to_quiet_ref_forms(self):
        self.assertEqual(_to_quiet_ref("$data.quote.data.discountType"), "$!{data.quote.data.discountType}")
        self.assertEqual(_to_quiet_ref("${data.x}"), "$!{data.x}")
        self.assertEqual(_to_quiet_ref("$!{data.x}"), "$!{data.x}")   # idempotent
        self.assertEqual(_to_quiet_ref("literal"), "literal")          # non-ref passthrough

    def test_optional_wrapped_required_bare(self):
        suggested = {
            "variables": [
                {"placeholder": "$TBD_quote.data.discountType",
                 "data_source": "$data.quote.data.discountType", "occurrence": "optional"},
                {"placeholder": "$TBD_account.data.email",
                 "data_source": "$data.account.data.email", "occurrence": "required"},
                {"placeholder": "$TBD_account.data.firstName",
                 "data_source": "$data.account.data.firstName"},  # default occurrence == required
            ],
        }
        smap = build_substitution_map(suggested)
        self.assertEqual(smap["$TBD_quote.data.discountType"], "$!{data.quote.data.discountType}")
        self.assertEqual(smap["$TBD_account.data.email"], "$data.account.data.email")
        self.assertEqual(smap["$TBD_account.data.firstName"], "$data.account.data.firstName")

    def test_unresolved_optional_not_wrapped(self):
        # An empty/unresolved data_source must stay empty, not become "$!{}".
        suggested = {"variables": [
            {"placeholder": "$TBD_x", "data_source": "UNRESOLVED:x", "occurrence": "optional"},
        ]}
        self.assertEqual(build_substitution_map(suggested)["$TBD_x"], "")


class TestForeachCollection(unittest.TestCase):
    """A loop's #foreach must iterate the verified per-root `data_source`
    (the list the plugin populates on the rendering-root object), NOT the
    registry-default unprefixed collection stored in `foreach`. The default
    (`$data.items`) iterates nothing because renderingData has no top-level
    `items` key — observed live as an empty loop in the rendered document.
    """

    @staticmethod
    def _loop(foreach: str, data_source: str) -> dict:
        return {"loops": [{
            "placeholder": "$TBD_Item",
            "iterator": "$item",
            "foreach": foreach,
            # schema 2.0: verdict carries the root-correct accessor
            "verdicts": {"quote": {"data_source": data_source}},
            "fields": [],
        }],
            "rendering_roots": [{"id": "quote", "primary": True}]}

    def test_quote_root_uses_verdict_collection(self):
        fmap = build_foreach_map(
            self._loop("#foreach ($item in $data.items)", "$data.quote.items"))
        self.assertEqual(fmap["$TBD_Item"], "#foreach ($item in $data.quote.items)")

    def test_segment_root_uses_verdict_collection(self):
        loop = self._loop("#foreach ($item in $data.items)", "$data.segment.items")
        loop["rendering_roots"] = [{"id": "segment", "primary": True}]
        loop["loops"][0]["verdicts"] = {"segment": {"data_source": "$data.segment.items"}}
        fmap = build_foreach_map(loop)
        self.assertEqual(fmap["$TBD_Item"], "#foreach ($item in $data.segment.items)")

    def test_iterator_name_preserved(self):
        fmap = build_foreach_map(
            self._loop("#foreach ($thing in $data.items)", "$data.quote.items"))
        self.assertEqual(fmap["$TBD_Item"], "#foreach ($thing in $data.quote.items)")

    def test_empty_data_source_omitted(self):
        # No verified collection → the loop is not added to the foreach map
        # (Leg 3 leaves the $TBD_ scaffold for human review, per DD-2).
        fmap = build_foreach_map(self._loop("#foreach ($item in $data.items)", ""))
        self.assertNotIn("$TBD_Item", fmap)

    def test_schema_1x_flat_data_source(self):
        # Flat (schema 1.x) loops carry data_source directly, no verdicts.
        loop = {"loops": [{
            "placeholder": "$TBD_Item",
            "foreach": "#foreach ($item in $data.items)",
            "data_source": "$data.quote.items",
        }]}
        fmap = build_foreach_map(loop)
        self.assertEqual(fmap["$TBD_Item"], "#foreach ($item in $data.quote.items)")


class TestOptionalCoverageGuard(unittest.TestCase):
    """A loop field reached through an OPTIONAL coverage (zero_or_one /
    zero_or_more) must be wrapped in an `#if($item.Coverage)…#end` guard. The
    strict renderer aborts (error 216041) the moment it calls `.data` on a null
    coverage, and a quiet ref `$!{…}` does NOT prevent that null navigation.
    A mandatory coverage (exactly_one / `!`) needs no guard.
    """

    @staticmethod
    def _loop(coverages: list[dict]) -> dict:
        return {"loops": [{
            "placeholder": "$TBD_Item",
            "data_source": "$data.quote.items",
            "available_coverages": coverages,
            "fields": [
                {"placeholder": "$TBD_item.data.purchasePrice",
                 "data_source": "$item.data.purchasePrice"},
                {"placeholder": "$TBD_item.AccidentalDamage.data.labourCovered",
                 "data_source": "$item.AccidentalDamage.data.labourCovered"},
            ],
        }]}

    def test_optional_coverage_field_guarded(self):
        smap = build_substitution_map(self._loop(
            [{"name": "AccidentalDamage", "velocity": "$item.AccidentalDamage",
              "quantifier": "?", "cardinality": "zero_or_one"}]))
        self.assertEqual(
            smap["$TBD_item.AccidentalDamage.data.labourCovered"],
            "#if($item.AccidentalDamage)$item.AccidentalDamage.data.labourCovered#end")
        # A plain item field is never guarded.
        self.assertEqual(smap["$TBD_item.data.purchasePrice"], "$item.data.purchasePrice")

    def test_mandatory_coverage_field_also_guarded(self):
        # Every coverage hop is guarded regardless of quantifier: live tenant
        # data can lack an exactly_one_auto coverage (unrated quote, config
        # drift) and the strict renderer 500s on a null hop (error 216041).
        smap = build_substitution_map(self._loop(
            [{"name": "AccidentalDamage", "velocity": "$item.AccidentalDamage",
              "quantifier": "!", "cardinality": "exactly_one_auto"}]))
        self.assertEqual(
            smap["$TBD_item.AccidentalDamage.data.labourCovered"],
            "#if($item.AccidentalDamage)$item.AccidentalDamage.data.labourCovered#end")

    def test_no_coverage_metadata_not_guarded(self):
        # Defensive: missing available_coverages must not crash or guard.
        loop = self._loop([])
        del loop["loops"][0]["available_coverages"]
        smap = build_substitution_map(loop)
        self.assertEqual(
            smap["$TBD_item.AccidentalDamage.data.labourCovered"],
            "$item.AccidentalDamage.data.labourCovered")


class TestStripUnregisteredGuards(unittest.TestCase):
    # Leg 0 emits directives HTML-wrapped, so the guard/#end are not alone on
    # their line. Before the fix, fullmatch missed them and phase 0 rewrote
    # #if($doc.Item) -> #if($data.Item) (a boolean nothing sets), so an
    # unconditional loop rendered nothing.
    _HTML = (
        '<span>#if($doc.Item)\n'
        '#foreach ($item in $x)</span>\n'
        '<span>body</span>\n'
        '<span>#end\n'   # closes #foreach -> keep
        '#end</span>\n'  # closes guard -> strip #end, keep </span>
    )

    def test_html_wrapped_unregistered_guard_stripped(self):
        out = _strip_unregistered_guards(self._HTML, cond_map={})
        self.assertNotIn("#if(", out)
        self.assertIn("#foreach ($item in $x)", out)
        self.assertEqual(out.count("#end"), 1)  # only the #foreach's #end remains
        self.assertIn("</span>", out.splitlines()[-1])  # guard's #end line keeps its markup

    def test_registered_guard_preserved_and_balanced(self):
        out = _strip_unregistered_guards(self._HTML, cond_map={"$doc.Item": "${data.Item}"})
        self.assertIn("#if($doc.Item)", out)  # phase 0 rewrites the token later
        self.assertEqual(out.count("#end"), 2)

    def test_standalone_guard_still_stripped(self):
        plain = "#if($doc.Foo)\n#foreach ($i in $y)\nx\n#end\n#end\n"
        out = _strip_unregistered_guards(plain, cond_map={})
        self.assertNotIn("#if(", out)
        self.assertEqual(out.count("#end"), 1)


if __name__ == "__main__":
    unittest.main()
