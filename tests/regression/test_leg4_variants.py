"""Regression tests — Leg 4 N-way variant codegen (the 50-state feature).

Covers: if/else-if chain via the DSL, default else, named put key, per-variant
field wiring (system + custom), unsupported field → TODO, default-row field
wiring, scope-blocked empty put, and the render:template + variants hard error.
"""

from __future__ import annotations

import unittest

from velocity_converter.leg4_generate_plugin import render_conditional_puts

# field_lookup entries the variant text can reference.
FL = {
    "policy.data.discountType": {
        "data_source": "$data.data.discountType", "scope": "policy",
        "java_expr": 'Objects.toString(segment.data().discountType(), "")',
        "unsupported_reason": "",
    },
    "quote.quoteNumber": {
        "data_source": "$data.quoteNumber", "scope": "quote",
        "java_expr": 'Objects.toString(quote.quoteNumber(), "")',
        "unsupported_reason": "",
    },
    "item.data.vin": {  # per-exposure → unsupported
        "data_source": "$data.items.data.vin", "scope": None, "java_expr": "",
        "unsupported_reason": "per-exposure (loop) field — conditional puts are document-scoped",
    },
}


def _block(scope="policy", default="Default text.", variants=None):
    return {
        "id": 1, "key": "stateClause", "placeholder": "stateClause", "variant": True,
        "scope": scope, "source_text": "$stateClause",
        "variants": variants if variants is not None else [
            {"when": {"path": "policy.data.state", "op": "==", "value": "CA",
                      "raw": 'state == "CA"'}, "text": "California text."},
            {"when": {"path": "policy.data.state", "op": "==", "value": "NY",
                      "raw": 'state == "NY"'}, "text": "New York text."},
        ],
        "default": default,
    }


class TestVariantCodegen(unittest.TestCase):
    def test_if_elseif_chain_and_default(self):
        java = render_conditional_puts([_block()], scope="policy", field_lookup=FL)
        self.assertIn('String stateClause = "";', java)
        self.assertIn("if (", java)
        self.assertIn("} else if (", java)
        self.assertIn("} else {", java)
        self.assertIn('renderingData.put("stateClause", stateClause);', java)
        # First match wins → CA before NY.
        self.assertLess(java.index('"CA"'), java.index('"NY"'))

    def test_uses_objects_equals_not_refeq(self):
        java = render_conditional_puts([_block()], scope="policy", field_lookup=FL)
        self.assertIn("Objects.equals(", java)
        self.assertNotIn('() == "CA"', java)

    def test_custom_field_wired_in_variant_text(self):
        b = _block(variants=[
            {"when": {"path": "policy.data.state", "op": "==", "value": "CA", "raw": 'state == "CA"'},
             "text": "CA discount {policy.data.discountType} applies."},
        ])
        java = render_conditional_puts([b], scope="policy", field_lookup=FL)
        self.assertIn('" + Objects.toString(segment.data().discountType(), "") + "', java)

    def test_field_wired_in_default_row(self):
        b = _block(default="Default {policy.data.discountType}.")
        java = render_conditional_puts([b], scope="policy", field_lookup=FL)
        # default else body concatenates the accessor
        tail = java[java.index("} else {"):]
        self.assertIn("Objects.toString(segment.data().discountType()", tail)

    def test_unsupported_field_todo_and_literal(self):
        b = _block(variants=[
            {"when": {"path": "policy.data.state", "op": "==", "value": "CA", "raw": 'state == "CA"'},
             "text": "VIN {item.data.vin} here."},
        ])
        java = render_conditional_puts([b], scope="policy", field_lookup=FL)
        self.assertIn("// TODO: field item.data.vin not wired", java)
        # Unwired token stays literal in the baked string (machine $TBD_ form),
        # exactly as the binary path leaves it.
        self.assertIn("$TBD_item.data.vin", java)

    def test_scope_blocked_empty_put(self):
        java = render_conditional_puts([_block(scope="policy")], scope="quote", field_lookup=FL)
        self.assertIn('renderingData.put("stateClause", "");', java)
        self.assertNotIn("else if", java)

    def test_template_plus_variants_hard_error(self):
        b = _block()
        b["render"] = "template"
        with self.assertRaises(ValueError):
            render_conditional_puts([b], scope="policy", field_lookup=FL)


class TestBinaryFieldRegression(unittest.TestCase):
    """§1a named-key switch must not change binary field-in-conditional baking."""

    def test_binary_block_still_bakes_field_concat(self):
        b = {
            "id": 1, "source_text": "Your quote $TBD_quote.quoteNumber is ready.",
            "conditions": ["quote.quoteNumber present"], "operator": "AND",
        }
        java = render_conditional_puts([b], scope="quote", field_lookup=FL)
        # Binary block: still keyed cond1, still concatenates the accessor.
        self.assertIn('String cond1 = "";', java)
        self.assertIn('renderingData.put("cond1", cond1);', java)
        self.assertIn('" + Objects.toString(quote.quoteNumber(), "") + "', java)
        self.assertNotIn("$TBD_", java)


if __name__ == "__main__":
    unittest.main()
