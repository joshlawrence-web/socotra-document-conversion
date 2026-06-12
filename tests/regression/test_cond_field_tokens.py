"""Regression tests — field tokens inside conditional blocks (plan 10).

Covers: leg4 accessor concat + scope split + unsupported flagging, leg0 form
display round-trip, leg3 delegated-to-plugin split. No JARs required.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent

from velocity_converter.leg0_ingest import (  # noqa: E402
    _braces_to_tbd,
    _tbd_to_braces,
    parse_conditional_form,
    write_conditional_form,
)
from velocity_converter.leg3_substitute import split_delegated  # noqa: E402
from velocity_converter.leg4_generate_plugin import (  # noqa: E402
    _analyse_cond_fields,
    _build_cond_field_lookup,
    _find_field_tokens,
    _source_text_to_java,
    render_conditional_puts,
    render_java,
)

VEL_TO_CAT = {
    "$data.quoteNumber": "quote_system",
    "$data.policyNumber": "system",
    "$data.data.discountAmount": "policy_data",
    "$data.data.discountType": "policy_data",
    "$data.account.data.firstName": "account",
    "$data.data.noSuchField": "policy_data",
}

SUGGESTED = {
    "variables": [
        {"name": "quoteNumber", "placeholder": "$TBD_quoteNumber",
         "data_source": "$data.quoteNumber"},
        {"name": "policy.data.discountAmount", "placeholder": "$TBD_policy.data.discountAmount",
         "data_source": "$data.data.discountAmount"},
        {"name": "policy.data.discountType", "placeholder": "$TBD_policy.data.discountType",
         "data_source": "$data.data.discountType"},
        {"name": "account.data.firstName", "placeholder": "$TBD_account.data.firstName",
         "data_source": "$data.account.data.firstName"},
        {"name": "unresolvedField", "placeholder": "$TBD_unresolvedField",
         "data_source": ""},
        {"name": "fetchedThing", "placeholder": "$TBD_fetchedThing",
         "data_source": "$data.fetchedThing.value",
         "candidate": {"source": "datafetcher", "datafetcher_key": "fetchedThing"}},
    ],
    "loops": [
        {"name": "items", "fields": [
            {"name": "item.data.serialNumber", "data_source": "$item.data.serialNumber"},
        ]},
    ],
}


def _lookup():
    return _build_cond_field_lookup(SUGGESTED, VEL_TO_CAT)


def _block(bid, source_text, conditions=None):
    return {
        "id": bid,
        "source_text": source_text,
        "conditions": conditions if conditions is not None else ["policy.data.discountAmount != null"],
        "operator": "AND",
        "parent_id": None,
        "depth": 0,
    }


class TestFieldTokenFinder(unittest.TestCase):

    KNOWN = {"policy.data.discountAmount", "policy.data", "quoteNumber"}

    def test_longest_match_wins(self):
        spans = _find_field_tokens("x $TBD_policy.data.discountAmount y", self.KNOWN)
        self.assertEqual([s[2] for s in spans], ["policy.data.discountAmount"])

    def test_sentence_punctuation_not_swallowed(self):
        text = "effective $TBD_quoteNumber."
        spans = _find_field_tokens(text, self.KNOWN)
        self.assertEqual(spans, [(10, 10 + len("$TBD_quoteNumber"), "quoteNumber")])

    def test_unknown_name_fallback_strips_trailing_dots(self):
        spans = _find_field_tokens("see $TBD_mystery. End", set())
        self.assertEqual([s[2] for s in spans], ["mystery"])

    def test_known_name_requires_word_boundary(self):
        # $TBD_quoteNumbers must not match known name quoteNumber
        spans = _find_field_tokens("x $TBD_quoteNumbers y", {"quoteNumber"})
        self.assertEqual([s[2] for s in spans], ["quoteNumbers"])


class TestSourceTextToJava(unittest.TestCase):

    EXPRS = {
        "quoteNumber": 'Objects.toString(quote.quoteNumber(), "")',
        "policy.data.discountAmount": 'Objects.toString(segment.data().discountAmount(), "")',
    }

    def test_field_concat(self):
        out = _source_text_to_java("A discount of $TBD_policy.data.discountAmount applies.", self.EXPRS)
        self.assertEqual(
            out,
            '"A discount of " + Objects.toString(segment.data().discountAmount(), "") + " applies."',
        )

    def test_mixed_cond_ref_and_field(self):
        out = _source_text_to_java("x $doc.cond2 y $TBD_quoteNumber z", self.EXPRS)
        self.assertEqual(
            out,
            '"x " + cond2 + " y " + Objects.toString(quote.quoteNumber(), "") + " z"',
        )

    def test_unlisted_field_stays_literal(self):
        out = _source_text_to_java("keep $TBD_other literal", self.EXPRS)
        self.assertIn("$TBD_other", out)

    def test_no_field_exprs_unchanged_behaviour(self):
        out = _source_text_to_java("plain $doc.cond3 text")
        self.assertEqual(out, '"plain " + cond3 + " text"')


class TestFieldLookup(unittest.TestCase):

    def test_scopes_and_exprs(self):
        lk = _lookup()
        self.assertEqual(lk["quoteNumber"]["scope"], "quote")
        self.assertEqual(lk["quoteNumber"]["java_expr"], 'Objects.toString(quote.quoteNumber(), "")')
        self.assertEqual(lk["policy.data.discountAmount"]["scope"], "policy")
        # Custom policy fields live on the segment type in Java
        self.assertEqual(
            lk["policy.data.discountAmount"]["java_expr"],
            'Objects.toString(segment.data().discountAmount(), "")',
        )

    def test_quote_rooted_velocity_paths(self):
        suggested = {"variables": [
            {"name": "quote.quoteNumber", "data_source": "$data.quote.quoteNumber"},
            {"name": "quote.data.coolingOffPeriod", "data_source": "$data.quote.data.coolingOffPeriod"},
        ]}
        lk = _build_cond_field_lookup(suggested, {
            "$data.quote.quoteNumber": "quote_system",
            "$data.quote.data.coolingOffPeriod": "quote_data",
        })
        self.assertEqual(lk["quote.quoteNumber"]["scope"], "quote")
        self.assertEqual(
            lk["quote.quoteNumber"]["java_expr"],
            'Objects.toString(quote.quoteNumber(), "")',
        )
        self.assertEqual(lk["quote.data.coolingOffPeriod"]["scope"], "quote")
        self.assertEqual(
            lk["quote.data.coolingOffPeriod"]["java_expr"],
            'Objects.toString(quote.data().coolingOffPeriod(), "")',
        )

    def test_account_unsupported(self):
        lk = _lookup()
        self.assertIn("account", lk["account.data.firstName"]["unsupported_reason"])

    def test_datafetcher_deferred(self):
        lk = _lookup()
        self.assertIn("DataFetcher", lk["fetchedThing"]["unsupported_reason"])

    def test_loop_field_unsupported(self):
        lk = _lookup()
        self.assertIn("per-exposure", lk["item.data.serialNumber"]["unsupported_reason"])

    def test_unresolved_has_empty_data_source(self):
        lk = _lookup()
        self.assertEqual(lk["unresolvedField"]["data_source"], "")
        self.assertEqual(lk["unresolvedField"]["unsupported_reason"], "")


class TestAnalyseCondFields(unittest.TestCase):

    def test_unresolved_detected_with_block_id(self):
        blocks = [_block(2, "needs $TBD_unresolvedField here")]
        unresolved, unsupported, mixed = _analyse_cond_fields(blocks, _lookup())
        self.assertEqual(unresolved, [{"block_id": 2, "name": "unresolvedField"}])
        self.assertEqual(unsupported, [])
        self.assertEqual(mixed, [])

    def test_unknown_name_counts_as_unresolved(self):
        blocks = [_block(1, "ghost $TBD_notInMapping token")]
        unresolved, _, _ = _analyse_cond_fields(blocks, _lookup())
        self.assertEqual(unresolved, [{"block_id": 1, "name": "notInMapping"}])

    def test_unsupported_detected(self):
        blocks = [_block(3, "hi $TBD_account.data.firstName")]
        unresolved, unsupported, _ = _analyse_cond_fields(blocks, _lookup())
        self.assertEqual(unresolved, [])
        self.assertEqual(unsupported[0]["block_id"], 3)
        self.assertEqual(unsupported[0]["name"], "account.data.firstName")

    def test_mixed_scope_flagged(self):
        blocks = [_block(4, "$TBD_quoteNumber and $TBD_policy.data.discountAmount")]
        _, _, mixed = _analyse_cond_fields(blocks, _lookup())
        self.assertEqual(mixed, [4])


class TestRenderConditionalPuts(unittest.TestCase):

    def test_policy_field_wired_in_policy_scope(self):
        blocks = [_block(1, "A discount of $TBD_policy.data.discountAmount applies.")]
        out = render_conditional_puts(blocks, scope="policy", field_lookup=_lookup())
        self.assertIn(
            'cond1 = "A discount of " + Objects.toString(segment.data().discountAmount(), "") + " applies.";',
            out,
        )
        # Condition root is rewritten too: policy.data.* lives on the segment
        self.assertIn("if (segment.data().discountAmount() != null)", out)
        self.assertNotIn("$TBD_", out)

    def test_policy_condition_empty_put_in_quote_scope(self):
        blocks = [_block(1, "static text")]
        out = render_conditional_puts(blocks, scope="quote", field_lookup=_lookup())
        self.assertIn('renderingData.put("cond1", "");', out)
        self.assertIn("policy-scoped condition(s)", out)

    def test_policy_field_empty_put_in_quote_scope(self):
        # Quote-rooted condition, but the FIELD is policy-scoped → field rule blocks it.
        blocks = [_block(1, "A discount of $TBD_policy.data.discountAmount applies.",
                         conditions=["quote.quoteNumber != null"])]
        out = render_conditional_puts(blocks, scope="quote", field_lookup=_lookup())
        self.assertIn('renderingData.put("cond1", "");', out)
        self.assertIn("policy-scoped field(s)", out)
        self.assertNotIn("Objects.toString", out)

    def test_quote_field_empty_put_in_policy_scope(self):
        blocks = [_block(1, "ref $TBD_quoteNumber here", conditions=["policy.data.x != null"])]
        out = render_conditional_puts(blocks, scope="policy", field_lookup=_lookup())
        self.assertIn('renderingData.put("cond1", "");', out)
        self.assertIn("quote-scoped field(s)", out)

    def test_unsupported_field_todo_and_literal_kept(self):
        blocks = [_block(1, "hi $TBD_account.data.firstName!")]
        out = render_conditional_puts(blocks, scope="policy", field_lookup=_lookup())
        self.assertIn("TODO: field account.data.firstName not wired", out)
        self.assertIn("$TBD_account.data.firstName", out)

    def test_no_lookup_unchanged_behaviour(self):
        blocks = [_block(1, "static text only")]
        out = render_conditional_puts(blocks, scope="policy")
        self.assertIn('cond1 = "static text only";', out)

    def test_additive_offset_ids_survive_field_concat(self):
        # Additive mode renumbers blocks past the existing high-water mark (D11).
        blocks = [_block(51, "A discount of $TBD_policy.data.discountAmount applies.")]
        out = render_conditional_puts(blocks, scope="policy", field_lookup=_lookup())
        self.assertIn("String cond51", out)
        self.assertIn('renderingData.put("cond51", cond51);', out)
        self.assertIn("Objects.toString(segment.data().discountAmount()", out)


class TestObjectsImport(unittest.TestCase):

    def test_import_added_when_field_wired(self):
        blocks = [_block(1, "A discount of $TBD_policy.data.discountAmount applies.")]
        java = render_java("TestProduct", "x.mapping.yaml", cond_blocks=blocks, field_lookup=_lookup())
        self.assertIn("import java.util.Objects;", java)

    def test_import_absent_without_fields(self):
        blocks = [_block(1, "static text only")]
        java = render_java("TestProduct", "x.mapping.yaml", cond_blocks=blocks, field_lookup=_lookup())
        self.assertNotIn("import java.util.Objects;", java)


_CUSTOMER_JAR = REPO / "build" / "customer-config.jar"
_DATAMODEL_JARS = sorted((REPO / "build").glob("core-datamodel-v*.jar")) if (REPO / "build").is_dir() else []
_HAVE_JARS = _CUSTOMER_JAR.is_file() and any(
    j.name.endswith(".jar") and "sources" not in j.name and "javadoc" not in j.name
    for j in _DATAMODEL_JARS
)


@pytest.mark.jar
@unittest.skipUnless(_HAVE_JARS, "SDK jars not present under build/")
class TestJarVerifiedWiring(unittest.TestCase):
    """javap-backed wiring: Optional unwrap + chain misses (needs build/ jars)."""

    @classmethod
    def setUpClass(cls):
        dm = next(j for j in _DATAMODEL_JARS if "sources" not in j.name and "javadoc" not in j.name)
        cls.classpath = f"{_CUSTOMER_JAR}:{dm}"

    def _lk(self, suggested):
        return _build_cond_field_lookup(suggested, VEL_TO_CAT,
                                        classpath=self.classpath, product="ZenCover")

    def test_optional_return_unwrapped(self):
        lk = self._lk({"variables": [
            {"name": "quoteNumber", "data_source": "$data.quoteNumber"},
        ]})
        self.assertEqual(
            lk["quoteNumber"]["java_expr"],
            'quote.quoteNumber().map(Object::toString).orElse("")',
        )

    def test_plain_return_wrapped_in_objects_tostring(self):
        lk = self._lk({"variables": [
            {"name": "policy.data.discountAmount", "data_source": "$data.data.discountAmount"},
        ]})
        self.assertEqual(
            lk["policy.data.discountAmount"]["java_expr"],
            'Objects.toString(segment.data().discountAmount(), "")',
        )

    def test_chain_miss_flagged_unsupported(self):
        lk = self._lk({"variables": [
            {"name": "policy.data.noSuchField", "data_source": "$data.data.noSuchField"},
        ]})
        self.assertIn(
            "path does not resolve in Java",
            lk["policy.data.noSuchField"]["unsupported_reason"],
        )


class TestLeg0FormRoundTrip(unittest.TestCase):

    def test_tbd_to_braces_trailing_dot(self):
        self.assertEqual(_tbd_to_braces("effective $TBD_startDate."), "effective {startDate}.")

    def test_braces_to_tbd(self):
        self.assertEqual(_braces_to_tbd("a {policy.data.x} b"), "a $TBD_policy.data.x b")

    def test_braces_to_tbd_noop_on_tbd_form(self):
        self.assertEqual(_braces_to_tbd("a $TBD_policy.data.x b"), "a $TBD_policy.data.x b")

    def test_form_shows_braces_and_parse_restores_tbd(self):
        import tempfile
        blocks = [{"id": 1,
                   "source_text": "A discount of $TBD_policy.data.discountAmount applies."}]
        with tempfile.TemporaryDirectory() as td:
            form = Path(td) / "x.conditional-form.md"
            write_conditional_form(blocks, "x", form)
            text = form.read_text(encoding="utf-8")
            self.assertIn("{policy.data.discountAmount}", text)
            self.assertNotIn("$TBD_", text)

            text = text.replace("Condition: ", "Condition: policy.data.discountAmount != null")
            form.write_text(text, encoding="utf-8")
            parsed = parse_conditional_form(form)
            self.assertEqual(
                parsed[0]["source_text"],
                "A discount of $TBD_policy.data.discountAmount applies.",
            )
            self.assertEqual(parsed[0]["conditions"], ["policy.data.discountAmount != null"])

    def test_old_tbd_format_form_still_parses(self):
        import tempfile
        old_form = (
            "# Conditional Text Review — x\n\n---\n\n## Block 1\n\n"
            "> legacy $TBD_policy.data.discountType text\n\n"
            "Condition: policy.data.discountType != null\n"
        )
        with tempfile.TemporaryDirectory() as td:
            form = Path(td) / "x.conditional-form.md"
            form.write_text(old_form, encoding="utf-8")
            parsed = parse_conditional_form(form)
            self.assertEqual(
                parsed[0]["source_text"],
                "legacy $TBD_policy.data.discountType text",
            )


class TestLeg3SplitDelegated(unittest.TestCase):

    VM = (
        "Hello $TBD_account.data.firstName!\n"
        "[[Discount $TBD_policy.data.discountAmount applies]]$doc.cond1\n"
    )

    def _entries(self):
        return [
            {"placeholder": "$TBD_account.data.firstName", "data_source": "$data.account.data.firstName"},
            {"placeholder": "$TBD_policy.data.discountAmount", "data_source": "$data.data.discountAmount"},
        ]

    def test_token_only_inside_block_is_delegated(self):
        kept, delegated = split_delegated(self.VM, self._entries())
        self.assertEqual([v["placeholder"] for v in kept], ["$TBD_account.data.firstName"])
        self.assertEqual([v["placeholder"] for v in delegated], ["$TBD_policy.data.discountAmount"])
        self.assertEqual(delegated[0]["_cond_ids"], ["1"])

    def test_token_inside_and_outside_is_kept(self):
        vm = self.VM + "Also outside: $TBD_policy.data.discountAmount\n"
        kept, delegated = split_delegated(vm, self._entries())
        self.assertEqual(delegated, [])
        self.assertEqual(len(kept), 2)

    def test_prefix_placeholder_not_matched(self):
        entries = [{"placeholder": "$TBD_policy.data", "data_source": "$x"}]
        kept, delegated = split_delegated(self.VM, entries)
        # $TBD_policy.data only occurs as a prefix of a longer token → no real
        # occurrence → kept (never falsely delegated).
        self.assertEqual(delegated, [])
        self.assertEqual(len(kept), 1)

    def test_nested_block_innermost_cond_id(self):
        vm = "[[outer [[inner $TBD_quoteNumber]]$doc.cond2 rest]]$doc.cond1\n"
        entries = [{"placeholder": "$TBD_quoteNumber", "data_source": "$data.quoteNumber"}]
        _, delegated = split_delegated(vm, entries)
        self.assertEqual(delegated[0]["_cond_ids"], ["2"])


if __name__ == "__main__":
    unittest.main()
