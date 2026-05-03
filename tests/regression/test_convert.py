"""Unit tests for html-to-velocity/scripts/convert.py."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
CONVERT_SCRIPTS = REPO / ".cursor" / "skills" / "html-to-velocity" / "scripts"
sys.path.insert(0, str(CONVERT_SCRIPTS))

from bs4 import BeautifulSoup, NavigableString, Tag  # noqa: E402

from convert import (  # noqa: E402
    Mapping,
    _clean_label,
    _collect_mustache_tokens,
    _find_innermost_pair,
    _inside_foreach,
    _match_loop_hint,
    _record_var,
    block_parent,
    nearest_column_header,
    nearest_heading,
    nearest_label,
    process_all_mustache_loops,
    rewrite_vars_in_string,
    rewrite_vars_in_subtree,
    singularize,
    slugify,
    wrap_conditionals,
)


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------------------
# Pure string helpers
# ---------------------------------------------------------------------------


class TestSingularize(unittest.TestCase):
    def test_simple_s(self) -> None:
        self.assertEqual(singularize("items"), "item")
        self.assertEqual(singularize("vehicles"), "vehicle")
        self.assertEqual(singularize("coverages"), "coverage")

    def test_ies_to_y(self) -> None:
        self.assertEqual(singularize("activities"), "activity")
        self.assertEqual(singularize("policies"), "policy")

    def test_ses_xes_drops_e(self) -> None:
        self.assertEqual(singularize("losses"), "loss")
        self.assertEqual(singularize("boxes"), "box")

    def test_double_s_unchanged(self) -> None:
        # "class" ends in ss → falls through to _item suffix
        self.assertEqual(singularize("class"), "class_item")

    def test_short_s_unchanged(self) -> None:
        # single char "s" → len not > 1? Actually len("s") = 1 so falls through
        self.assertEqual(singularize("s"), "s_item")

    def test_no_s_gets_item_suffix(self) -> None:
        self.assertEqual(singularize("datum"), "datum_item")

    def test_case_preserved(self) -> None:
        # singularize works on the original case
        self.assertEqual(singularize("Items"), "Item")
        self.assertEqual(singularize("Vehicles"), "Vehicle")


class TestSlugify(unittest.TestCase):
    def test_spaces_become_underscores(self) -> None:
        self.assertEqual(slugify("Policy Number"), "policy_number")

    def test_special_chars_removed(self) -> None:
        self.assertEqual(slugify("hello-world!"), "hello_world")

    def test_empty_string(self) -> None:
        self.assertEqual(slugify(""), "")

    def test_leading_trailing_stripped(self) -> None:
        self.assertEqual(slugify("  hello  "), "hello")

    def test_already_clean(self) -> None:
        self.assertEqual(slugify("policy_number"), "policy_number")


class TestCleanLabel(unittest.TestCase):
    def test_strips_trailing_colon(self) -> None:
        from convert import _clean_label
        self.assertEqual(_clean_label("Policy Number:"), "Policy Number")

    def test_empty_returns_empty(self) -> None:
        from convert import _clean_label
        self.assertEqual(_clean_label(""), "")
        self.assertEqual(_clean_label("   "), "")

    def test_rejects_tbd(self) -> None:
        from convert import _clean_label
        self.assertEqual(_clean_label("TBD_FIELD"), "")

    def test_rejects_dollar(self) -> None:
        from convert import _clean_label
        self.assertEqual(_clean_label("$data.policyNumber"), "")

    def test_rejects_mustache(self) -> None:
        from convert import _clean_label
        self.assertEqual(_clean_label("{{POLICY_NUMBER}}"), "")

    def test_truncates_at_80(self) -> None:
        from convert import _clean_label
        long = "A" * 90
        self.assertEqual(len(_clean_label(long)), 80)

    def test_normal_label_preserved(self) -> None:
        from convert import _clean_label
        self.assertEqual(_clean_label("Effective Date"), "Effective Date")


class TestMatchLoopHint(unittest.TestCase):
    def _iterables(self) -> list[dict]:
        return [
            {"name": "Vehicle", "prefix": "vehicle_", "keys": {"vehicle"}},
            {"name": "Driver", "prefix": "driver_", "keys": {"driver"}},
        ]

    def test_prefix_match(self) -> None:
        self.assertEqual(_match_loop_hint("vehicle_make", self._iterables()), "Vehicle")
        self.assertEqual(_match_loop_hint("driver_name", self._iterables()), "Driver")

    def test_no_match(self) -> None:
        self.assertIsNone(_match_loop_hint("policy_number", self._iterables()))

    def test_empty_var_name(self) -> None:
        self.assertIsNone(_match_loop_hint("", self._iterables()))

    def test_empty_iterables(self) -> None:
        self.assertIsNone(_match_loop_hint("vehicle_make", []))

    def test_partial_prefix_no_match(self) -> None:
        # "vehicle" without underscore should NOT match "vehicle_make" prefix rule
        self.assertIsNone(_match_loop_hint("vehicleSpeed", self._iterables()))

    def test_longer_prefix_wins(self) -> None:
        iterables = [
            {"name": "VehicleDriver", "prefix": "vehicle_driver_", "keys": set()},
            {"name": "Vehicle", "prefix": "vehicle_", "keys": set()},
        ]
        # "vehicle_driver_name" matches both; longer prefix should win if sorted
        result = _match_loop_hint("vehicle_driver_name", iterables)
        self.assertEqual(result, "VehicleDriver")


class TestRewriteVarsInString(unittest.TestCase):
    def test_basic_substitution(self) -> None:
        found: list = []
        result = rewrite_vars_in_string("Hello {{POLICY_NUMBER}}", "$TBD_", found)
        self.assertEqual(result, "Hello $TBD_POLICY_NUMBER")
        self.assertEqual(found, [("POLICY_NUMBER", "$TBD_POLICY_NUMBER")])

    def test_multiple_vars(self) -> None:
        found: list = []
        result = rewrite_vars_in_string("{{A}} and {{B}}", "$TBD_", found)
        self.assertEqual(result, "$TBD_A and $TBD_B")
        self.assertEqual(len(found), 2)

    def test_loop_prefix(self) -> None:
        found: list = []
        result = rewrite_vars_in_string("{{ITEM_NAME}}", "$item.TBD_", found)
        self.assertEqual(result, "$item.TBD_ITEM_NAME")

    def test_no_vars(self) -> None:
        found: list = []
        result = rewrite_vars_in_string("plain text", "$TBD_", found)
        self.assertEqual(result, "plain text")
        self.assertEqual(found, [])

    def test_whitespace_inside_braces_ok(self) -> None:
        found: list = []
        result = rewrite_vars_in_string("{{ FIELD }}", "$TBD_", found)
        self.assertEqual(result, "$TBD_FIELD")


# ---------------------------------------------------------------------------
# BeautifulSoup-dependent helpers
# ---------------------------------------------------------------------------


class TestNearestLabel(unittest.TestCase):
    def test_previous_sibling_text(self) -> None:
        soup = _soup("<p>Policy Number: <span>{{POLICY_NUMBER}}</span></p>")
        span = soup.find("span")
        self.assertIn("Policy Number", nearest_label(span))

    def test_no_label_returns_empty(self) -> None:
        soup = _soup("<p><span>{{POLICY_NUMBER}}</span></p>")
        span = soup.find("span")
        # No preceding text — should return ""
        self.assertEqual(nearest_label(span), "")

    def test_rejects_tbd_as_label(self) -> None:
        soup = _soup("<p>$TBD_OTHER <span>{{FIELD}}</span></p>")
        span = soup.find("span")
        self.assertEqual(nearest_label(span), "")


class TestNearestHeading(unittest.TestCase):
    def test_finds_preceding_heading(self) -> None:
        soup = _soup("<h2>Vehicle Info</h2><p>{{VEHICLE_MAKE}}</p>")
        p = soup.find("p")
        self.assertEqual(nearest_heading(p), "Vehicle Info")

    def test_no_heading_returns_empty(self) -> None:
        soup = _soup("<p>{{FIELD}}</p>")
        p = soup.find("p")
        self.assertEqual(nearest_heading(p), "")


class TestNearestColumnHeader(unittest.TestCase):
    HTML = """
    <table>
      <thead><tr><th>Name</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td id="td1">{{FIELD1}}</td><td id="td2">{{FIELD2}}</td></tr>
      </tbody>
    </table>
    """

    def test_first_column(self) -> None:
        soup = _soup(self.HTML)
        td = soup.find("td", id="td1")
        self.assertEqual(nearest_column_header(td), "Name")

    def test_second_column(self) -> None:
        soup = _soup(self.HTML)
        td = soup.find("td", id="td2")
        self.assertEqual(nearest_column_header(td), "Value")

    def test_non_td_returns_empty(self) -> None:
        soup = _soup("<p>hello</p>")
        p = soup.find("p")
        self.assertEqual(nearest_column_header(p), "")


class TestBlockParent(unittest.TestCase):
    def test_finds_p(self) -> None:
        soup = _soup("<p>$TBD_FIELD</p>")
        text = list(soup.find("p").children)[0]
        self.assertEqual(block_parent(text).name, "p")

    def test_finds_li(self) -> None:
        soup = _soup("<ul><li>$TBD_FIELD</li></ul>")
        text = list(soup.find("li").children)[0]
        self.assertEqual(block_parent(text).name, "li")

    def test_none_for_no_block_ancestor(self) -> None:
        soup = _soup("<html><body>$TBD_FIELD</body></html>")
        text = list(soup.find("body").children)[0]
        # body is not in BLOCK_TAGS
        self.assertIsNone(block_parent(text))


class TestInsideForeach(unittest.TestCase):
    def test_detects_foreach_sibling(self) -> None:
        soup = _soup("<div></div>")
        div = soup.find("div")
        div.insert_before(NavigableString("\n#foreach ($x in $data.xs)\n"))
        self.assertTrue(_inside_foreach(div))

    def test_no_foreach(self) -> None:
        soup = _soup("<p>hello</p>")
        p = soup.find("p")
        self.assertFalse(_inside_foreach(p))


# ---------------------------------------------------------------------------
# Loop token parsing
# ---------------------------------------------------------------------------


class TestCollectMustacheTokens(unittest.TestCase):
    def test_finds_opener_and_closer(self) -> None:
        soup = _soup("<p>[items] hello [/items]</p>")
        tokens = _collect_mustache_tokens(soup)
        self.assertEqual(len(tokens), 2)
        openers = [t for t in tokens if t["kind"] == ""]
        closers = [t for t in tokens if t["kind"] == "/"]
        self.assertEqual(len(openers), 1)
        self.assertEqual(len(closers), 1)
        self.assertEqual(openers[0]["name"], "items")
        self.assertEqual(closers[0]["name"], "items")

    def test_no_tokens(self) -> None:
        soup = _soup("<p>plain text</p>")
        self.assertEqual(_collect_mustache_tokens(soup), [])

    def test_multiple_loops(self) -> None:
        soup = _soup("<p>[a][/a][b][/b]</p>")
        tokens = _collect_mustache_tokens(soup)
        names = [t["name"] for t in tokens]
        self.assertIn("a", names)
        self.assertIn("b", names)


class TestFindInnermostPair(unittest.TestCase):
    def test_finds_simple_pair(self) -> None:
        soup = _soup("<p>[items] content [/items]</p>")
        pair = _find_innermost_pair(soup)
        self.assertIsNotNone(pair)
        self.assertEqual(pair[0]["name"], "items")
        self.assertEqual(pair[1]["name"], "items")

    def test_finds_innermost_in_nested(self) -> None:
        soup = _soup("<p>[outer] [inner] x [/inner] [/outer]</p>")
        pair = _find_innermost_pair(soup)
        self.assertIsNotNone(pair)
        self.assertEqual(pair[0]["name"], "inner")

    def test_no_pair_returns_none(self) -> None:
        soup = _soup("<p>plain text</p>")
        self.assertIsNone(_find_innermost_pair(soup))

    def test_unclosed_loop_returns_none(self) -> None:
        soup = _soup("<p>[items] unclosed</p>")
        self.assertIsNone(_find_innermost_pair(soup))


# ---------------------------------------------------------------------------
# Loop processing integration
# ---------------------------------------------------------------------------


class TestProcessAllMustacheLoops(unittest.TestCase):
    def test_simple_loop_converted(self) -> None:
        soup = _soup("<p>[items]{{ITEM_NAME}}[/items]</p>")
        mapping = Mapping(source="test.html")
        process_all_mustache_loops(soup, mapping)
        vm = str(soup)
        self.assertIn("#foreach", vm)
        self.assertIn("$TBD_items", vm)
        self.assertIn("#end", vm)
        self.assertIn("$item.TBD_ITEM_NAME", vm)

    def test_loop_recorded_in_mapping(self) -> None:
        soup = _soup("<p>[vehicles]{{VEHICLE_MAKE}}[/vehicles]</p>")
        mapping = Mapping(source="test.html")
        process_all_mustache_loops(soup, mapping)
        self.assertEqual(len(mapping.loops), 1)
        loop = mapping.loops[0]
        self.assertEqual(loop["name"], "vehicles")
        self.assertEqual(len(loop["fields"]), 1)
        self.assertEqual(loop["fields"][0]["name"], "VEHICLE_MAKE")

    def test_loop_field_has_loop_context(self) -> None:
        soup = _soup("<p>[items]{{ITEM_DESC}}[/items]</p>")
        mapping = Mapping(source="test.html")
        process_all_mustache_loops(soup, mapping)
        field = mapping.loops[0]["fields"][0]
        self.assertEqual(field["context"].get("loop"), "items")

    def test_nested_loops_both_converted(self) -> None:
        soup = _soup("<p>[outer]{{OUTER_FIELD}}[inner]{{INNER_FIELD}}[/inner][/outer]</p>")
        mapping = Mapping(source="test.html")
        process_all_mustache_loops(soup, mapping)
        self.assertEqual(len(mapping.loops), 2)
        loop_names = {L["name"] for L in mapping.loops}
        self.assertIn("outer", loop_names)
        self.assertIn("inner", loop_names)

    def test_no_loops_mapping_empty(self) -> None:
        soup = _soup("<p>{{POLICY_NUMBER}}</p>")
        mapping = Mapping(source="test.html")
        process_all_mustache_loops(soup, mapping)
        self.assertEqual(mapping.loops, [])

    def test_mismatched_loop_produces_warning(self) -> None:
        # opener in one parent, closer in another — should warn
        soup = _soup("<p>[items]</p><p>[/items]</p>")
        mapping = Mapping(source="test.html")
        process_all_mustache_loops(soup, mapping)
        self.assertTrue(any("items" in w for w in mapping.warnings))

    def test_iterator_name_is_singular(self) -> None:
        soup = _soup("<p>[drivers]{{DRIVER_NAME}}[/drivers]</p>")
        mapping = Mapping(source="test.html")
        process_all_mustache_loops(soup, mapping)
        vm = str(soup)
        self.assertIn("$driver", vm)


# ---------------------------------------------------------------------------
# rewrite_vars_in_subtree
# ---------------------------------------------------------------------------


class TestRewriteVarsInSubtree(unittest.TestCase):
    def test_rewrites_vars_in_tree(self) -> None:
        soup = _soup("<p>{{POLICY_NUMBER}}</p>")
        mapping = Mapping(source="test.html")
        rewrite_vars_in_subtree(soup, prefix="$TBD_", mapping=mapping, in_loop=False)
        self.assertIn("$TBD_POLICY_NUMBER", str(soup))
        self.assertEqual(len(mapping.variables), 1)
        self.assertEqual(mapping.variables[0]["name"], "POLICY_NUMBER")

    def test_deduplicates_vars(self) -> None:
        soup = _soup("<p>{{FIELD}} and {{FIELD}}</p>")
        mapping = Mapping(source="test.html")
        rewrite_vars_in_subtree(soup, prefix="$TBD_", mapping=mapping, in_loop=False)
        self.assertEqual(len(mapping.variables), 1)

    def test_loop_vars_go_to_fields_not_variables(self) -> None:
        soup = _soup("<p>{{ITEM_NAME}}</p>")
        mapping = Mapping(source="test.html")
        loop_fields: list = []
        rewrite_vars_in_subtree(
            soup, prefix="$item.TBD_", mapping=mapping,
            in_loop=True, loop_fields=loop_fields, loop_name="items"
        )
        self.assertEqual(len(mapping.variables), 0)
        self.assertEqual(len(loop_fields), 1)
        self.assertEqual(loop_fields[0]["context"].get("loop"), "items")


# ---------------------------------------------------------------------------
# wrap_conditionals
# ---------------------------------------------------------------------------


class TestWrapConditionals(unittest.TestCase):
    def test_wraps_single_tbd(self) -> None:
        soup = _soup("<p>Amount: $TBD_AMOUNT</p>")
        mapping = Mapping(source="test.html")
        wrap_conditionals(soup, mapping)
        vm = str(soup)
        self.assertIn("#if($TBD_AMOUNT)", vm)
        self.assertIn("#end", vm)

    def test_multiple_tbds_uses_and(self) -> None:
        soup = _soup("<p>$TBD_A and $TBD_B</p>")
        mapping = Mapping(source="test.html")
        wrap_conditionals(soup, mapping)
        vm = str(soup)
        self.assertIn("$TBD_A and $TBD_B", vm)
        self.assertIn("#if", vm)

    def test_loop_scoped_tokens_not_wrapped(self) -> None:
        soup = _soup("<p>$item.TBD_ITEM_NAME</p>")
        mapping = Mapping(source="test.html")
        wrap_conditionals(soup, mapping)
        vm = str(soup)
        self.assertNotIn("#if", vm)

    def test_already_inside_foreach_not_double_wrapped(self) -> None:
        soup = _soup("<div></div>")
        div = soup.find("div")
        div.insert_before(NavigableString("\n#foreach ($x in $data.xs)\n"))
        div.string = "$TBD_FIELD"
        mapping = Mapping(source="test.html")
        wrap_conditionals(soup, mapping)
        vm = str(soup)
        self.assertNotIn("#if", vm)

    def test_each_block_wrapped_once(self) -> None:
        soup = _soup("<p>$TBD_A</p><p>$TBD_B</p>")
        mapping = Mapping(source="test.html")
        wrap_conditionals(soup, mapping)
        vm = str(soup)
        self.assertEqual(vm.count("#if"), 2)
        self.assertEqual(vm.count("#end"), 2)


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


class TestConvertInvariants(unittest.TestCase):
    def test_no_mustache_tokens_remain_after_processing(self) -> None:
        html = "<p>[items]{{ITEM_NAME}}[/items]</p><p>{{POLICY_NUMBER}}</p>"
        soup = _soup(html)
        mapping = Mapping(source="test.html")
        process_all_mustache_loops(soup, mapping)
        rewrite_vars_in_subtree(soup, prefix="$TBD_", mapping=mapping, in_loop=False)
        remaining = _collect_mustache_tokens(soup)
        self.assertEqual(remaining, [], f"Unconverted tokens: {remaining}")

    def test_every_loop_has_name_and_fields_key(self) -> None:
        soup = _soup("<p>[items]{{A}}{{B}}[/items]</p>")
        mapping = Mapping(source="test.html")
        process_all_mustache_loops(soup, mapping)
        for loop in mapping.loops:
            self.assertIn("name", loop)
            self.assertIn("fields", loop)

    def test_every_variable_has_name_and_placeholder(self) -> None:
        soup = _soup("<p>{{POLICY_NUMBER}} {{EFFECTIVE_DATE}}</p>")
        mapping = Mapping(source="test.html")
        rewrite_vars_in_subtree(soup, prefix="$TBD_", mapping=mapping, in_loop=False)
        for v in mapping.variables:
            self.assertIn("name", v)
            self.assertIn("placeholder", v)
            self.assertTrue(v["placeholder"].startswith("$TBD_"))


if __name__ == "__main__":
    unittest.main()
