# Stale Regression Test Cleanup

**Status:** Done
**Completed:** 2026-06-11
**Created:** 2026-06-11
**Item:** 7 regression failures — all stale tests asserting behavior that was intentionally removed/renamed. No production code changes required.

## START HERE (implementing agent)

`python3 -m pytest tests/regression/ -q` currently reports **7 failed, 219 passed**.
Every failure is a test that encodes an old contract; the code is correct and ahead of
the tests. Fix the tests only — do NOT change `scripts/leg2_fill_mapping.py` or
`scripts/leg4_generate_plugin.py` to make tests pass.

**Read in this order:**
1. This file — §1 (root causes), §2 (task list)
2. `tests/regression/test_leg2_advanced.py` — `TestSuggestLoopRoot` (line ~62),
   `TestInvariants.test_high_confidence_loop_root_always_has_data_source_and_iterator` (line ~171)
3. `scripts/leg2_fill_mapping.py` — `suggest_loop_root()` (line ~828) — the NEW exact-only contract
4. `tests/regression/test_leg4_report.py` — lines 38–41 and 73–78
5. `scripts/leg4_generate_plugin.py` — `write_report()` — the CURRENT section titles

---

## 1. Root causes

### Cluster A — `test_leg2_advanced.py` (5 failures)

Plan `08-strict-exact-matching` deliberately removed the case-insensitive, plural, and
terminology/synonym fallbacks from `suggest_loop_root` (see the comment at
`scripts/leg2_fill_mapping.py:848` — "Exact name match only — no ci/terminology
fallbacks"; docstring: match_step is `exact|none`). Paths must be explicitly chosen from
the field catalog; the pipeline validates, it does not guess.

| Test | Asserts (old) | Actual (new) |
|------|---------------|--------------|
| `TestSuggestLoopRoot::test_plural_match` | `"Items"` → step `ci` | step `none` |
| `TestSuggestLoopRoot::test_ci_match` | `"item"` → step `ci` | step `none` |
| `TestSuggestLoopRoot::test_terminology_match` | `"Widget"` (synonym) → step `terminology` | step `none` |
| `TestInvariants::test_high_confidence_loop_root_always_has_data_source_and_iterator` | subtests `"Items"`, `"item"` → step in `(exact, ci)` | step `none` |

### Cluster B — `test_leg4_report.py` (2 failures)

File is **untracked** (never committed) and was written against plugin-report section
titles from commit `0bb6e2b`. `write_report` later renamed them:

| Test | Asserts (old title) | Current title |
|------|---------------------|---------------|
| `test_report_has_key_count` | `High-confidence paths` | `## Resolved paths (validated against {Product}Segment or {Product}Quote)` |
| `test_report_unresolved_shows_ignored` | `## Ignored` | `## Unresolved — no data_source` |

Semantics also changed: the section no longer means "medium/low confidence ignored";
it means "empty `data_source`, regardless of confidence".

---

## 2. Task list

| # | Task | File |
|---|------|------|
| T1 | Convert `test_plural_match`, `test_ci_match`, `test_terminology_match` into strict-matching assertions: each input (`"Items"`, `"item"`, `"Widget"`+terminology) → `step == "none"`, `ds == ""`, reason contains `supply-from-plugin` (mirror the existing `test_no_match_returns_low`). Rename them accordingly (e.g. `test_plural_does_not_match_strict`). Do NOT just delete — the strict behavior deserves coverage. | `tests/regression/test_leg2_advanced.py` |
| T2 | In `test_high_confidence_loop_root_always_has_data_source_and_iterator`, trim the subtest loop from `("Item", "Items", "item")` to `("Item",)` and change `assertIn(step, ("exact", "ci"))` → `assertEqual(step, "exact")`. | `tests/regression/test_leg2_advanced.py` |
| T3 | Update assertion `"High-confidence paths"` → `"## Resolved paths"`. | `tests/regression/test_leg4_report.py` (line ~41) |
| T4 | Rename `test_report_unresolved_shows_ignored` → `test_report_unresolved_section_lists_empty_data_source`; update assertion `"## Ignored"` → `"## Unresolved"`; fix the stale comment ("Medium/low confidence variables appear in the Ignored section" → variables with empty `data_source` appear in the Unresolved section). | `tests/regression/test_leg4_report.py` (lines ~73–78) |
| T5 | Run `python3 -m pytest tests/regression/ -q` — expect **0 failed** (~226 passed incl. subtests). Then run `python3 tests/pipeline/run_test_pipeline.py --auto` — expect all PASS (guards against accidental script edits). | — |
| T6 | `test_leg4_report.py` is untracked — stage it together with these fixes so the suite's green state is reproducible from a clean checkout. | git |

---

## 3. Acceptance criteria

1. `tests/regression/` fully green; no test deleted without a strict-matching replacement (T1).
2. No changes under `scripts/` — this is a test-only cleanup.
3. Pipeline suite (`run_test_pipeline.py --auto`) still passes.
4. `test_leg4_report.py` tracked in git alongside the fixes.
