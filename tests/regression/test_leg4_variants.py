"""Regression tests — Leg 4 N-way variant codegen (the 50-state feature).

Covers: if/else-if chain via the DSL, default else, named put key, per-variant
field wiring (system + custom), unsupported field → TODO, default-row field
wiring, scope-blocked empty put, and the render:template Boolean put (a template
block carries its single `when` as a one-entry variants payload — no longer an
error under variants-only).
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

    def test_default_only_variant_unconditional(self):
        # A default-only variant (no conditioned rows) renders its text
        # unconditionally — no if-chain and no dangling `} else {`.
        b = _block(scope="", variants=[], default="Always shown.")
        java = render_conditional_puts([b], scope="quote", field_lookup=FL)
        self.assertIn('String stateClause = "";', java)
        self.assertIn('stateClause = "Always shown.";', java)
        self.assertNotIn("} else {", java)
        self.assertNotIn("if (", java)
        self.assertIn('renderingData.put("stateClause", stateClause);', java)

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

    def test_template_block_puts_boolean(self):
        # Variants-only: a render:template block carries its single `when` as a
        # one-entry variants payload. It is no longer an error — the block routes
        # to _render_template_put, which emits a single Boolean put (no String/
        # if-chain, no throw); the section wording stays in the template.
        b = _block(variants=[
            {"when": {"path": "policy.data.state", "op": "==", "value": "CA",
                      "raw": 'state == "CA"'}, "text": ""},
        ])
        b["render"] = "template"
        java = render_conditional_puts([b], scope="policy", field_lookup=FL)
        # Single Boolean put driven by the `when` AST (null-guarded accessor).
        self.assertIn('renderingData.put("stateClause", Objects.equals(', java)
        self.assertIn('segment.data().state()', java)
        self.assertIn('"CA"));', java)
        # No N-way String accumulator or if/else-if chain for a template block.
        self.assertNotIn('String stateClause', java)
        self.assertNotIn("} else if (", java)

    def test_template_block_out_of_scope_puts_false(self):
        # A policy-scoped template block in the quote overload puts false (never "").
        b = _block(scope="policy", variants=[
            {"when": {"path": "policy.data.state", "op": "==", "value": "CA",
                      "raw": 'state == "CA"'}, "text": ""},
        ])
        b["render"] = "template"
        java = render_conditional_puts([b], scope="quote", field_lookup=FL)
        self.assertIn('renderingData.put("stateClause", false);', java)


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
