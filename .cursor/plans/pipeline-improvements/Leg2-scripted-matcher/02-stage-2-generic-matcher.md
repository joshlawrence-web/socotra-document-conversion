# Stage 2 — Generic Registry Matcher

**Status:** COMPLETE (with post-plan regression fix — see Stage 5)
**Depends on:** Stage 1 (spec agreed)
**Output:** Refactored `scripts/leg2_fill_mapping.py` with Rules 1–6 implemented generically

---

## Overview

Replace the `specials` dict and hardcoded loop logic with a self-contained matching engine driven by the registry and (optionally) `terminology.yaml`. The script must produce correct output for **any** product whose registry follows the `path-registry.yaml` schema — not just CommercialAuto.

---

## Task 2.1 — Implement `match_name_in_registry`

New function in `leg2_fill_mapping.py` (or a new `leg2_matcher.py` module):

```python
def match_name_in_registry(
    name: str,
    label: str | None,
    registry_index: RegistryIndex,
    terminology: TerminologyMap | None,
) -> MatchResult:
```

Where `RegistryIndex` is a prebuilt lookup containing:
- `by_field`: `{field_lower: [RegistryEntry]}` — all entries, scope-aware
- `by_display_name`: `{display_name_lower: [RegistryEntry]}`
- `iterables_by_name`: `{name_lower: IterableEntry}`
- `iterables_by_plural`: `{plural_lower: IterableEntry}` (e.g. "vehicles" → Vehicle)

Steps in order (stop at first unambiguous hit):

1. **Exact** — `name == entry.field` OR `label == entry.display_name`
2. **Case-insensitive** — fold both sides, same comparisons
3. **Terminology** — check synonyms.fields alias lists; check display_name_aliases
4. **Fuzzy** — snake_case ↔ camelCase transform; obvious plural collapse

Ambiguity handling:
- If 2+ entries match at the same step with different scopes: emit all as candidates, confidence `medium`, next_action `pick-one`
- If 2+ entries match at the same step within the same scope: prefer the more specific one (deeper path wins); if still tied, emit `pick-one`

### Confidence from match step

| Match step | Scope | Confidence |
|---|---|---|
| Exact | satisfied or not required | high |
| Case-insensitive | satisfied or not required | high |
| Terminology | satisfied or not required | high |
| Fuzzy (unambiguous) | satisfied or not required | medium (confirm-assumption) |
| Any step | violated (loop_hint) | low (restructure-template) |
| Any step | violated (no hint) | low (restructure-template) |
| No match | — | low (supply-from-plugin) |

---

## Task 2.2 — Implement `check_scope`

```python
def check_scope(
    entry: RegistryEntry,
    context: dict,
) -> Literal["not_required", "satisfied", "violated_with_hint", "violated_no_hint"]:
```

- `not_required` → `entry.requires_scope == []`
- `satisfied` → `context["loop"]` matches the outermost `requires_scope` step iterator (and any inner steps for nested loops)
- `violated_with_hint` → `context.get("loop_hint")` matches the outermost step but `loop` does not
- `violated_no_hint` → scope required but neither `loop` nor `loop_hint` satisfies it

---

## Task 2.3 — Apply Rules 4–6 as post-match notes

After a match is found and scope is checked, append notes to `reasoning`:

**Rule 4 (optional-element guard):**
```python
if entry.quantifier == "?":
    reasoning += f" requires #if({entry.velocity}) guard before access (element is zero-or-one)"
```

**Rule 5 (auto-element note):**
```python
if entry.quantifier == "!":
    reasoning += " element is auto-created on validation; always present (no #if guard needed)"
```

**Rule 6 (charge disambiguation):**
When the matched entry is a charge (`velocity_amount` / `velocity_object`):
- If label contains "amount", "premium", "fee", "tax", or the context is currency-formatted → use `velocity_amount`
- Otherwise leave as `velocity_object` with a note

---

## Task 2.4 — Replace `suggest_loop_root` and `suggest_loop_field` with generic versions

**`suggest_loop_root`:** Look up loop name in `iterables_by_name` + `iterables_by_plural` using the 4-step name-match precedence. Return `list_velocity`, `iterator`, `foreach`, `available_coverages` from the registry. No hardcoded product names.

**`suggest_loop_field`:** For a loop field, find its parent exposure from `iterables_by_iterator`, then look up the field name in that exposure's `fields` list using the same 4-step name-match.

---

## Task 2.5 — Load `terminology.yaml`

Add `--terminology <path>` flag to `leg2_fill_mapping.py` (mirrors SKILL.md Step 0c resolution order):
1. `--terminology <path>` if given
2. Repo-root `terminology.yaml`
3. Sibling of registry file

Parse `synonyms.exposures`, `synonyms.coverages`, `synonyms.fields`, `display_name_aliases`. Validate canonicals against registry at load time; unknown canonicals are dropped and logged.

---

## Task 2.6 — Add feature flag shape probe

Emit warnings (to stderr or a `warnings:` list in the output) for refusal flags:

```python
REFUSAL_FLAGS = {
    "nested_iterables", "custom_data_types", "recursive_cdts",
    "jurisdictional_scopes", "peril_based", "multi_product",
    "coverage_terms", "default_option_prefix",
}
PARTIAL_FLAGS = {"array_data_extensions"}

for flag, val in reg.get("feature_support", {}).items():
    if val and flag in REFUSAL_FLAGS:
        # Surface in review.md §7 + downgrade affected entries
    if val and flag in PARTIAL_FLAGS:
        # Surface in §7 only (no downgrade)
```

The downgrade rule: any entry whose match depends on a feature controlled by a refusal flag → force to `low` + `needs-skill-update` (do not remove the match, just lower confidence and note the flag).

---

## Task 2.7 — Remove (or isolate) the `specials` dict

**Preferred:** delete `specials` entirely once the generic matcher handles all cases correctly.

**Fallback if needed:** rename to `product_overrides` and make it an optional per-product file (e.g. `registry/overrides.yaml`) that the user can provide for cases the generic rules can't resolve. This keeps the script generic while letting product teams encode known exceptions explicitly.

---

## Acceptance criteria

- [x] `leg2_fill_mapping.py` produces correct output with no `specials` lookups
- [x] `POLICY_NUMBER` → `$data.policyNumber` high (case-insensitive display_name hit)
- [x] `POLICYHOLDER_NAME` → `$data.account.data.name` medium/confirm-assumption (fuzzy)
- [~] `EFFECTIVE_START_DATE` → pick-one medium (two candidates) — **actual:** low/supply-from-plugin (field does not exist in the current ItemCare test registry; criteria were written against a CommercialAuto registry that was not the active fixture)
- [~] `INSURANCE_PRODUCT` → `$data.productName` medium/confirm-assumption — **actual:** low/supply-from-plugin (same reason as above)
- [x] Script produces same output for existing fixtures as before (no regression — after post-plan fix; see Stage 5)
- [x] `terminology.yaml` synonym lookup works end-to-end (`custom-naming` fixture passes)
- [x] Feature flag refusal warnings appear in output (`nested_iterables: true` surfaces in §7)

## Execution notes

New functions added: `_collect_entries`, `build_registry_index`, `check_scope`, `_step1_exact`, `_step2_ci`, `_step3_terminology`, `_step4_fuzzy`, `match_name`, `_quantifier_note`, `_charge_path`, `suggest_variable`, `suggest_loop_root`, `suggest_loop_field`. Legacy functions `index_registry`, `exposure_field_index`, `iterables_by_iterator` kept as stubs since `emit_telemetry.py` imports them. `ruleset_id` changed from `commercial_auto_heuristic_v1` to `generic_registry_v2`.

The two acceptance criteria marked `[~]` reflect a spec mismatch: the expected field names (`EFFECTIVE_START_DATE`, `INSURANCE_PRODUCT`) exist in CommercialAuto but not in the ItemCare registry that was the active test target. The generic matcher correctly returned low/supply-from-plugin for both — this is the right answer for a registry that does not contain those fields.

`coverage_terms` was initially left in `REFUSAL_FLAGS` as a planned non-implementation. This caused a regression discovered in Stage 5 (see that file). The fix (`_match_coverage_field` generic prefix decomposition) was applied post-plan and `coverage_terms` was removed from `REFUSAL_FLAGS`.
