"""Regression tests — occurrence symbols in {field} placeholders.

Covers: leg0 prefix parsing ({$x} optional, {x} required, {+x} one or more,
{*x} zero or more), mapping propagation + model validation, and leg4
occurrence-guard codegen (fresh + report rows). No JARs required.
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent

from velocity_converter.leg0_ingest import (  # noqa: E402
    _braces_to_tbd,
    _normalise_for_leg2,
    annotate_fields,
    extract_fields,
)
from velocity_converter.leg4_generate_plugin import (  # noqa: E402
    _build_cond_field_lookup,
    occurrence_report_rows,
    render_java,
    render_occurrence_guards,
)
from velocity_converter.models import OCCURRENCE_SYMBOLS, MappingVariable  # noqa: E402

VEL_TO_CAT = {
    "$data.quoteNumber": "quote_system",
    "$data.data.discountAmount": "policy_data",
    "$data.data.riders": "policy_data",
    "$data.account.data.firstName": "account",
}


def _html(*fields: str) -> str:
    body = " ".join("<p>" + f + "</p>" for f in fields)
    return f"<html><body>{body}</body></html>"


class TestOccurrenceSymbolTable(unittest.TestCase):

    def test_all_four_symbols(self):
        self.assertEqual(
            OCCURRENCE_SYMBOLS,
            {"": "required", "$": "optional", "+": "one_or_more", "*": "zero_or_more"},
        )


class TestExtractFieldsOccurrence(unittest.TestCase):

    def test_bare_is_required(self):
        fields = extract_fields(_html("{policyHolder}"))
        self.assertEqual(fields[0]["occurrence"], "required")

    def test_dollar_is_optional(self):
        fields = extract_fields(_html("{$policyHolder}"))
        self.assertEqual(fields[0]["occurrence"], "optional")

    def test_plus_is_one_or_more(self):
        fields = extract_fields(_html("{+drivers}"))
        self.assertEqual(fields[0]["occurrence"], "one_or_more")

    def test_star_is_zero_or_more(self):
        fields = extract_fields(_html("{*endorsements}"))
        self.assertEqual(fields[0]["occurrence"], "zero_or_more")

    def test_token_never_carries_symbol(self):
        for ph in ("{$x}", "{+x}", "{*x}", "{x}"):
            fields = extract_fields(_html(ph))
            self.assertEqual(fields[0]["token"], "$TBD_x", ph)
            self.assertEqual(fields[0]["name"], "x", ph)

    def test_prefixed_dotted_name(self):
        fields = extract_fields(_html("{$account.data.firstName}"))
        self.assertEqual(fields[0]["name"], "account.data.firstName")
        self.assertEqual(fields[0]["occurrence"], "optional")

    def test_conflicting_symbols_first_wins(self):
        fields = extract_fields(_html("{+drivers}", "{drivers}"))
        by_name = {f["name"]: f for f in fields}
        self.assertEqual(by_name["drivers"]["occurrence"], "one_or_more")
        self.assertEqual(len(fields), 1)

    def test_repeated_same_symbol_no_conflict(self):
        fields = extract_fields(_html("{$x}", "{$x}"))
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]["occurrence"], "optional")


class TestAnnotateFieldsOccurrence(unittest.TestCase):

    def test_prefixed_placeholders_annotated(self):
        html = _html("{$a}", "{+b}", "{*c}", "{d}")
        fields = extract_fields(html)
        out = annotate_fields(html, fields)
        for tok in ("$TBD_a", "$TBD_b", "$TBD_c", "$TBD_d"):
            self.assertIn(tok, out)
        for ph in ("{$a}", "{+b}", "{*c}", "{d}"):
            self.assertNotIn(ph, out)

    def test_unknown_field_left_alone(self):
        out = annotate_fields("<p>{a} {b}</p>", [{"name": "a", "token": "$TBD_a"}])
        self.assertEqual(out, "<p>$TBD_a {b}</p>")


class TestBracesToTbdOccurrence(unittest.TestCase):

    def test_prefix_accepted_and_dropped(self):
        self.assertEqual(_braces_to_tbd("x {$a} {+b} {*c} y"), "x $TBD_a $TBD_b $TBD_c y")


class TestMappingPropagation(unittest.TestCase):

    def test_normalise_carries_occurrence(self):
        fields = extract_fields(_html("{$a}", "{+b}", "{c}"))
        doc = _normalise_for_leg2(fields, "src.html")
        occ = {v["name"]: v["occurrence"] for v in doc["variables"]}
        self.assertEqual(occ, {"a": "optional", "b": "one_or_more", "c": "required"})

    def test_model_defaults_to_required(self):
        v = MappingVariable.model_validate({"name": "x"})
        self.assertEqual(v.occurrence, "required")

    def test_model_rejects_unknown_occurrence(self):
        with self.assertRaises(Exception):
            MappingVariable.model_validate({"name": "x", "occurrence": "sometimes"})


def _vars(**occ_by_name):
    """Build suggested variables wired to known categories."""
    ds = {
        "quoteNumber": "$data.quoteNumber",
        "policy.data.discountAmount": "$data.data.discountAmount",
        "policy.data.riders": "$data.data.riders",
        "account.data.firstName": "$data.account.data.firstName",
        "unresolvedField": "",
    }
    return [
        {"name": n, "placeholder": f"$TBD_{n}", "data_source": ds[n], "occurrence": o}
        for n, o in occ_by_name.items()
    ]


def _lookup(variables):
    return _build_cond_field_lookup({"variables": variables}, VEL_TO_CAT)


class TestRenderOccurrenceGuards(unittest.TestCase):

    def test_required_policy_field_guarded_stepwise(self):
        variables = _vars(**{"policy.data.discountAmount": "required"})
        java = render_occurrence_guards(variables, _lookup(variables), scope="policy")
        self.assertIn("// occurrence-guard: policy.data.discountAmount (required)", java)
        self.assertIn(
            "if (segment == null || segment.data() == null "
            "|| segment.data().discountAmount() == null)",
            java,
        )
        self.assertIn("throw new IllegalStateException(", java)
        self.assertIn('missingRequired.add("policy.data.discountAmount (required)");', java)

    def test_one_or_more_without_jar_falls_back_to_null_check(self):
        # No classpath → final_ret unknown → null check only (single value
        # still satisfies one_or_more).
        variables = _vars(**{"policy.data.riders": "one_or_more"})
        java = render_occurrence_guards(variables, _lookup(variables), scope="policy")
        self.assertIn("// occurrence-guard: policy.data.riders (one_or_more)", java)
        self.assertNotIn(".isEmpty())", java.split("missingRequired.isEmpty")[0])

    def test_one_or_more_list_return_adds_isempty(self):
        variables = _vars(**{"policy.data.riders": "one_or_more"})
        lookup = _lookup(variables)
        lookup["policy.data.riders"]["guard"]["final_ret"] = "java.util.List<java.lang.String>"
        java = render_occurrence_guards(variables, lookup, scope="policy")
        self.assertIn("segment.data().riders().isEmpty()", java)

    def test_optional_and_zero_or_more_not_guarded(self):
        variables = _vars(**{
            "policy.data.discountAmount": "optional",
            "policy.data.riders": "zero_or_more",
        })
        java = render_occurrence_guards(variables, _lookup(variables), scope="policy")
        self.assertEqual(java, "")

    def test_scope_split(self):
        variables = _vars(**{
            "quoteNumber": "required",
            "policy.data.discountAmount": "required",
        })
        lookup = _lookup(variables)
        quote_java = render_occurrence_guards(variables, lookup, scope="quote")
        policy_java = render_occurrence_guards(variables, lookup, scope="policy")
        self.assertIn("quote.quoteNumber()", quote_java)
        self.assertNotIn("segment.", quote_java)
        self.assertIn("segment.data().discountAmount()", policy_java)
        self.assertNotIn("quote.quoteNumber()", policy_java)

    def test_unwirable_and_unresolved_fields_skipped(self):
        variables = _vars(**{
            "account.data.firstName": "required",   # category not wireable
            "unresolvedField": "required",          # no data_source
        })
        java = render_occurrence_guards(variables, _lookup(variables), scope="policy")
        self.assertEqual(java, "")

    def test_skip_names_dedupes_for_additive_mode(self):
        variables = _vars(**{"policy.data.discountAmount": "required"})
        java = render_occurrence_guards(
            variables, _lookup(variables), scope="policy",
            skip_names={"policy.data.discountAmount"},
        )
        self.assertEqual(java, "")

    def test_custom_list_var_used_throughout(self):
        variables = _vars(**{"policy.data.discountAmount": "required"})
        java = render_occurrence_guards(
            variables, _lookup(variables), scope="policy", list_var="missingRequired2",
        )
        self.assertIn("java.util.List<String> missingRequired2 =", java)
        self.assertIn("missingRequired2.add(", java)
        self.assertIn("missingRequired2.isEmpty()", java)
        self.assertNotIn("missingRequired.", java)


class TestRenderJavaGuards(unittest.TestCase):

    def test_guards_emitted_in_both_overloads(self):
        variables = _vars(**{
            "quoteNumber": "required",
            "policy.data.discountAmount": "one_or_more",
        })
        java = render_java(
            "TestProduct", "x.mapping.yaml",
            field_lookup=_lookup(variables), variables=variables,
        )
        self.assertIn("// occurrence-guard: quoteNumber (required)", java)
        self.assertIn("// occurrence-guard: policy.data.discountAmount (one_or_more)", java)
        # One guard block (declaration + throw) per overload.
        self.assertEqual(java.count("java.util.List<String> missingRequired ="), 2)
        self.assertEqual(java.count("throw new IllegalStateException("), 2)

    def test_no_occurrence_no_guard_block(self):
        variables = _vars(**{"policy.data.discountAmount": "optional"})
        java = render_java(
            "TestProduct", "x.mapping.yaml",
            field_lookup=_lookup(variables), variables=variables,
        )
        self.assertNotIn("occurrence-guard", java)
        self.assertNotIn("missingRequired", java)


class TestOccurrenceReportRows(unittest.TestCase):

    def test_statuses(self):
        variables = _vars(**{
            "quoteNumber": "required",
            "policy.data.riders": "one_or_more",
            "policy.data.discountAmount": "optional",
            "account.data.firstName": "required",
            "unresolvedField": "required",
        })
        rows = occurrence_report_rows(variables, _lookup(variables))
        by_name = {r["name"]: r["status"] for r in rows}
        self.assertEqual(by_name["quoteNumber"], "guarded (quote)")
        self.assertEqual(by_name["policy.data.riders"], "guarded (policy)")
        self.assertEqual(by_name["policy.data.discountAmount"], "no guard needed (optional)")
        self.assertTrue(by_name["account.data.firstName"].startswith("WARN: no guard —"))
        self.assertEqual(
            by_name["unresolvedField"], "WARN: no guard — unresolved data_source"
        )


if __name__ == "__main__":
    raise SystemExit(unittest.main())
