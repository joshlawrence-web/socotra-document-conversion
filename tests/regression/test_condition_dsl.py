"""Regression tests — condition DSL (parse / validate / Java codegen).

Covers: round-trip parse of every operator, and/or joins, mixed-join rejection,
literal typing; registry-backed validation (path-exists, scope rejection,
type-mismatch); and generated-Java assertions (Objects.equals not ==, null
stepping, compareTo for ordering, List.of for `in`, present/absent).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pytest

from velocity_converter.condition_dsl import (
    ConditionError,
    ast_from_dict,
    ast_to_dict,
    condition_to_java,
    parse_condition,
    parse_variants_csv,
    validate_condition,
)

# Minimal registry: a quote string field, a policy custom string field, a policy
# custom decimal field, and a policy custom boolean field.
REGISTRY = {
    "quote_paths": [
        {"velocity": "$data.quoteNumber", "category": "quote_system", "base_type": "string"},
    ],
    "policy_data": [
        {"velocity": "$data.data.state", "category": "policy_data", "base_type": "string"},
        {"velocity": "$data.data.premium", "category": "policy_data", "base_type": "decimal"},
        {"velocity": "$data.data.hasRider", "category": "policy_data", "base_type": "boolean"},
    ],
    "system_paths": [
        {"velocity": "$data.policyNumber", "category": "system", "base_type": "string"},
    ],
}


class TestParse(unittest.TestCase):
    def test_simple_equality(self):
        ast = parse_condition('policy.data.state == "CA"')
        self.assertEqual(len(ast.comparisons), 1)
        c = ast.comparisons[0]
        self.assertEqual((c.path, c.op, c.value), ("policy.data.state", "==", "CA"))

    def test_all_value_ops(self):
        for op in ("==", "!=", ">", ">=", "<", "<="):
            ast = parse_condition(f"policy.data.premium {op} 500")
            self.assertEqual(ast.comparisons[0].op, op)
            self.assertEqual(ast.comparisons[0].value, 500)

    def test_present_absent(self):
        for op in ("present", "absent"):
            ast = parse_condition(f"quote.quoteNumber {op}")
            self.assertEqual(ast.comparisons[0].op, op)
            self.assertIsNone(ast.comparisons[0].value)

    def test_in_list(self):
        ast = parse_condition('policy.data.state in ["CA", "NY", "TX"]')
        self.assertEqual(ast.comparisons[0].op, "in")
        self.assertEqual(ast.comparisons[0].value, ["CA", "NY", "TX"])

    def test_and_join(self):
        ast = parse_condition('policy.data.state == "CA" and policy.data.premium > 500')
        self.assertEqual(ast.join, "AND")
        self.assertEqual(len(ast.comparisons), 2)

    def test_or_join(self):
        ast = parse_condition('policy.data.state == "CA" or policy.data.state == "NY"')
        self.assertEqual(ast.join, "OR")

    def test_boolean_literal(self):
        ast = parse_condition("policy.data.hasRider == true")
        self.assertIs(ast.comparisons[0].value, True)

    def test_float_literal(self):
        ast = parse_condition("policy.data.premium >= 3.5")
        self.assertEqual(ast.comparisons[0].value, 3.5)

    def test_mixed_join_rejected(self):
        with self.assertRaises(ConditionError):
            parse_condition('a.b == "x" and c.d == "y" or e.f == "z"')

    def test_empty_rejected(self):
        with self.assertRaises(ConditionError):
            parse_condition("   ")

    def test_missing_operand_rejected(self):
        with self.assertRaises(ConditionError):
            parse_condition("policy.data.state ==")

    def test_bare_identifier_rejected(self):
        with self.assertRaises(ConditionError):
            parse_condition("quoteNumber != notALiteral")

    def test_empty_in_list_rejected(self):
        with self.assertRaises(ConditionError):
            parse_condition("policy.data.state in []")

    def test_null_literal_rewritten_to_present_absent(self):
        # Forgiving parse: `x != null` ≡ `x present`, `x == null` ≡ `x absent`.
        ast = parse_condition("quote.quoteNumber != null")
        self.assertEqual(ast.comparisons[0].op, "present")
        ast = parse_condition("policy.data.state == null")
        self.assertEqual(ast.comparisons[0].op, "absent")
        # Within an and-join too.
        ast = parse_condition("quote.a != null and quote.b == null")
        self.assertEqual([c.op for c in ast.comparisons], ["present", "absent"])
        # A quoted "null" stays a string literal (not a null check).
        ast = parse_condition('policy.data.state == "null"')
        self.assertEqual(ast.comparisons[0].op, "==")
        self.assertEqual(ast.comparisons[0].value, "null")


class TestValidate(unittest.TestCase):
    def test_valid_policy_condition(self):
        ast = parse_condition('policy.data.state == "CA"')
        self.assertEqual(validate_condition(ast, REGISTRY, "policy"), [])

    def test_unknown_path(self):
        ast = parse_condition('policy.data.nope == "CA"')
        errs = validate_condition(ast, REGISTRY, "policy")
        self.assertTrue(any("not found" in e for e in errs))

    def test_quote_field_in_policy_block(self):
        ast = parse_condition('quote.quoteNumber == "Q1"')
        errs = validate_condition(ast, REGISTRY, "policy")
        self.assertTrue(any("policy-scoped" in e or "not valid in a policy" in e for e in errs))

    def test_string_op_on_number(self):
        ast = parse_condition('policy.data.premium == "high"')
        errs = validate_condition(ast, REGISTRY, "policy")
        self.assertTrue(any("non-numeric" in e for e in errs))

    def test_ordering_on_string(self):
        ast = parse_condition('policy.data.state > 5')
        errs = validate_condition(ast, REGISTRY, "policy")
        self.assertTrue(any("ordering operator" in e for e in errs))

    def test_quote_condition_valid_in_quote_scope(self):
        ast = parse_condition('quote.quoteNumber present')
        self.assertEqual(validate_condition(ast, REGISTRY, "quote"), [])

    def test_quote_data_custom_field_valid_in_quote_scope(self):
        # Gap 4: quote custom fields (stored as policy_data) are addressable as
        # quote.data.<f> in a quote-scoped block via the full accessor.
        ast = parse_condition('quote.data.premium > 5')
        self.assertEqual(validate_condition(ast, REGISTRY, "quote"), [])

    def test_quote_data_alias_rejected_in_policy_scope(self):
        # The quote.* alias is usable only at quote scope; a policy doc keeps
        # using policy.data.<f> (root check rejects the quote root first).
        ast = parse_condition('quote.data.premium > 5')
        errs = validate_condition(ast, REGISTRY, "policy")
        self.assertTrue(any("policy-scoped" in e or "not valid in a policy" in e for e in errs))


class TestCodegen(unittest.TestCase):
    def test_equality_uses_objects_equals_not_refeq(self):
        java = condition_to_java(parse_condition('policy.data.state == "CA"'), "policy")
        self.assertIn("Objects.equals(", java)
        self.assertNotIn('() == "CA"', java)  # no reference equality
        self.assertIn('"CA"', java)
        # policy.data.* must be rewritten to the segment local.
        self.assertIn("segment", java)
        self.assertNotIn("policy.data()", java)

    def test_equality_is_null_safe(self):
        java = condition_to_java(parse_condition('policy.data.state == "CA"'), "policy")
        self.assertIn("== null", java)

    def test_inequality_negates(self):
        java = condition_to_java(parse_condition('policy.data.state != "CA"'), "policy")
        self.assertTrue(java.strip().startswith("!("))

    def test_ordering_uses_compareto(self):
        java = condition_to_java(parse_condition("policy.data.premium > 500"), "policy")
        self.assertIn("compareTo(", java)
        self.assertIn("BigDecimal", java)
        self.assertIn("> 0", java)

    def test_present_absent(self):
        self.assertIn("!= null", condition_to_java(parse_condition("quote.quoteNumber present"), "quote"))
        self.assertIn("== null", condition_to_java(parse_condition("quote.quoteNumber absent"), "quote"))

    def test_in_uses_list_of_contains(self):
        java = condition_to_java(parse_condition('policy.data.state in ["CA", "NY"]'), "policy")
        self.assertIn("List.of(", java)
        self.assertIn(".contains(", java)
        self.assertIn('"CA"', java)
        self.assertIn('"NY"', java)

    def test_and_join_codegen(self):
        java = condition_to_java(
            parse_condition('policy.data.state == "CA" and policy.data.premium > 500'), "policy"
        )
        self.assertIn(" && ", java)

    def test_or_join_codegen(self):
        java = condition_to_java(
            parse_condition('policy.data.state == "CA" or policy.data.state == "NY"'), "policy"
        )
        self.assertIn(" || ", java)

    def test_quote_scope_no_rewrite(self):
        java = condition_to_java(parse_condition('quote.quoteNumber == "Q1"'), "quote")
        self.assertIn("quote.quoteNumber()", java)
        self.assertNotIn("segment", java)

    def test_boolean_equality(self):
        java = condition_to_java(parse_condition("policy.data.hasRider == true"), "policy")
        self.assertIn("Objects.equals(", java)
        self.assertIn("true", java)


class TestSerialisation(unittest.TestCase):
    def test_single_comparison_roundtrip(self):
        ast = parse_condition('policy.data.state == "CA"')
        d = ast_to_dict(ast)
        self.assertEqual(d["path"], "policy.data.state")
        self.assertEqual(d["op"], "==")
        self.assertEqual(d["value"], "CA")
        back = ast_from_dict(d)
        self.assertEqual(back.comparisons[0].path, "policy.data.state")

    def test_multi_comparison_roundtrip(self):
        ast = parse_condition('policy.data.state == "CA" and policy.data.premium > 500')
        d = ast_to_dict(ast)
        self.assertEqual(d["join"], "AND")
        self.assertEqual(len(d["comparisons"]), 2)
        back = ast_from_dict(d)
        self.assertEqual(len(back.comparisons), 2)
        self.assertEqual(back.join, "AND")

    def test_from_dict_falls_back_to_raw(self):
        back = ast_from_dict({"raw": 'policy.data.state == "NY"'})
        self.assertEqual(back.comparisons[0].value, "NY")


def _write_csv(text: str) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".variants.csv", delete=False, encoding="utf-8")
    f.write(text)
    f.close()
    return Path(f.name)


class TestVariantsCsv(unittest.TestCase):
    def test_basic_parse_with_default(self):
        path = _write_csv(
            "placeholder,when,text\n"
            'stateClause,"state == ""CA""","California text"\n'
            'stateClause,"state == ""NY""","New York text"\n'
            "stateClause,,Default text\n"
        )
        res = parse_variants_csv(path, REGISTRY)
        self.assertEqual(res.errors, [])
        ph = res.placeholders["stateClause"]
        self.assertEqual(len(ph["variants"]), 2)
        self.assertEqual(ph["default"], "Default text")
        self.assertEqual(ph["scope"], "policy")
        # Bare leaf 'state' resolved to the full accessor.
        self.assertEqual(ph["variants"][0]["when"]["path"], "policy.data.state")

    def test_bare_leaf_resolves_to_rendering_root_scope(self):
        # A custom field (stored policy_data) used as a bare leaf must resolve to
        # the document's rendering-root scope: quote.data.<f> in a (quote) doc,
        # policy.data.<f> in a (segment/policy) doc. Regression for the condition
        # landing in the wrong plugin overload (disclosureClause demo bug).
        csv_text = (
            "placeholder,when,text\n"
            'clause,"state == ""CA""","CA text"\n'
            "clause,,Default text\n"
        )
        quote_res = parse_variants_csv(_write_csv(csv_text), REGISTRY, doc_scope="quote")
        self.assertEqual(quote_res.errors, [])
        self.assertEqual(quote_res.placeholders["clause"]["scope"], "quote")
        self.assertEqual(
            quote_res.placeholders["clause"]["variants"][0]["when"]["path"],
            "quote.data.state",
        )

        policy_res = parse_variants_csv(_write_csv(csv_text), REGISTRY, doc_scope="policy")
        self.assertEqual(policy_res.errors, [])
        self.assertEqual(policy_res.placeholders["clause"]["scope"], "policy")
        self.assertEqual(
            policy_res.placeholders["clause"]["variants"][0]["when"]["path"],
            "policy.data.state",
        )

    def test_bare_leaf_default_scope_blind_without_rendering_root(self):
        # Backward compat: with no doc_scope the resolution stays scope-blind and
        # a custom-field leaf keeps resolving to its policy.data home.
        res = parse_variants_csv(
            _write_csv(
                "placeholder,when,text\n"
                'clause,"state == ""CA""","CA text"\n'
                "clause,,Default text\n"
            ),
            REGISTRY,
        )
        self.assertEqual(res.errors, [])
        self.assertEqual(res.placeholders["clause"]["scope"], "policy")
        self.assertEqual(
            res.placeholders["clause"]["variants"][0]["when"]["path"], "policy.data.state"
        )

    def test_single_row_no_default_is_binary(self):
        # One conditioned row + no default = binary show/hide (valid). Implicit
        # empty default → render the text when the condition holds, else nothing.
        path = _write_csv(
            "placeholder,when,text\n"
            'stateClause,"state == ""CA""","California text"\n'
        )
        res = parse_variants_csv(path, REGISTRY)
        self.assertEqual(res.errors, [])
        ph = res.placeholders["stateClause"]
        self.assertEqual(len(ph["variants"]), 1)
        self.assertEqual(ph["default"], "")

    def test_multi_variant_missing_default_flagged(self):
        # ≥2 conditioned rows with no default is still flagged — a genuine N-way
        # block needs an explicit fallback so it can't silently render empty.
        path = _write_csv(
            "placeholder,when,text\n"
            'stateClause,"state == ""CA""","California text"\n'
            'stateClause,"state == ""NY""","New York text"\n'
        )
        res = parse_variants_csv(path, REGISTRY)
        self.assertTrue(any("no default row" in e for e in res.errors))

    def test_multiple_defaults_flagged(self):
        path = _write_csv(
            "placeholder,when,text\n"
            'stateClause,"state == ""CA""",CA\n'
            "stateClause,,d1\n"
            "stateClause,*,d2\n"
        )
        res = parse_variants_csv(path, REGISTRY)
        self.assertTrue(any("default rows" in e for e in res.errors))

    def test_bad_condition_flagged(self):
        path = _write_csv(
            "placeholder,when,text\n"
            "stateClause,this is not a condition,x\n"
            "stateClause,,d\n"
        )
        res = parse_variants_csv(path, REGISTRY)
        self.assertTrue(any("bad condition" in e for e in res.errors))

    def test_comment_lines_and_bom(self):
        path = _write_csv(
            "﻿# instructions: fill rows\n"
            "placeholder,when,text\n"
            'stateClause,"state == ""CA""",CA\n'
            "stateClause,else,d\n"
        )
        res = parse_variants_csv(path, REGISTRY)
        self.assertEqual(res.errors, [])
        self.assertEqual(res.placeholders["stateClause"]["default"], "d")

    def test_validation_error_surfaced(self):
        # premium is decimal; comparing == to a string must surface.
        path = _write_csv(
            "placeholder,when,text\n"
            'rateClause,"premium == ""high""",x\n'
            "rateClause,,d\n"
        )
        res = parse_variants_csv(path, REGISTRY)
        self.assertTrue(any("non-numeric" in e for e in res.errors))


_REPO = Path(__file__).resolve().parents[2]
_CUSTOMER_JAR = _REPO / "build" / "customer-config.jar"
_DATAMODEL_JARS = [
    j for j in sorted((_REPO / "build").glob("core-datamodel-v*.jar"))
    if "sources" not in j.name and "javadoc" not in j.name
] if (_REPO / "build").is_dir() else []
_HAVE_JARS = _CUSTOMER_JAR.is_file() and bool(_DATAMODEL_JARS)


@pytest.mark.jar
@unittest.skipUnless(_HAVE_JARS, "SDK jars not present under build/")
class TestJarAsAuthority(unittest.TestCase):
    """A fully-qualified path missing from the curated registry is accepted when a
    jar is supplied and it resolves against the real model; rejected without a jar
    (the registry is a curated/sometimes-stale subset, the jar is the truth)."""

    @classmethod
    def setUpClass(cls):
        cls.classpath = f"{_CUSTOMER_JAR}:{_DATAMODEL_JARS[0]}"

    # quote.endTime is a real ZenCoverQuote accessor but is NOT in REGISTRY above.
    _CSV = (
        "placeholder,when,text\n"
        "endClause,quote.endTime present,Ends {endTime}\n"
    )

    def test_registry_missing_path_rejected_without_jar(self):
        res = parse_variants_csv(_write_csv(self._CSV), REGISTRY)
        self.assertTrue(any("not a known accessor" in e for e in res.errors))

    def test_registry_missing_path_accepted_with_jar(self):
        res = parse_variants_csv(
            _write_csv(self._CSV), REGISTRY,
            classpath=self.classpath, product="ZenCover",
        )
        self.assertEqual(res.errors, [])
        ph = res.placeholders["endClause"]
        self.assertEqual(ph["scope"], "quote")
        self.assertEqual(ph["variants"][0]["when"]["path"], "quote.endTime")

    def test_bogus_path_still_rejected_with_jar(self):
        res = parse_variants_csv(
            _write_csv("placeholder,when,text\nx,quote.totallyBogusXyz present,t\n"),
            REGISTRY, classpath=self.classpath, product="ZenCover",
        )
        self.assertTrue(res.errors)


if __name__ == "__main__":
    unittest.main()
