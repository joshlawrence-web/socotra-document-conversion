# coverage-terms — `coverageTerms` + `*default` option prefix refusal

## Purpose

Proves that `extract_paths.py` flips both `coverage_terms: true` and
`default_option_prefix: true` when any coverage config carries a
non-empty `coverageTerms: [...]` array whose options include at least
one entry prefixed with `*`, and that the extractor **emits a `terms`
entry per coverage term** (`$<iter>.<Cov>.<term>.value`) alongside the
coverage's `data` fields.

> **Updated 2026-06-29.** The extractor previously dropped `coverageTerms`
> (registry had zero term paths); it now reads them — see
> `CONFIG_COVERAGE.md` row 9. The `feature_support` flags below and the
> coverage `data`-field behaviour are unchanged. The suggested/review
> narrative further down (the `flood_deductible` refusal) describes the
> **mapping-suggester skill**, which the conformance runner does not
> execute and whose goldens are not committed; that narrative predates this
> change and should be re-derived when the suggester is next run against
> this fixture (the registry now offers `$dwelling.Flood.deductible.value`
> as a candidate, so the refusal — if any — now hinges on
> `default_option_prefix`, not a missing registry path).

This is the canonical regression for `CONFIG_COVERAGE.md` rows 9 + 10.

## `CONFIG_COVERAGE.md` rows covered

§3.2 — Quantifiers on coverage `contents`:

- **Row 9** — Coverage with `coverageTerms: [...]` — directly
  exercised via `Flood`'s single term (`deductible`). Flips
  `coverage_terms: true`.
- **Row 10** — Coverage term with default-option prefix `*value` —
  directly exercised via the same term's options list
  (`["250", "*500", "1000"]`). Flips `default_option_prefix: true`
  as a dependent flag (only meaningful when `coverage_terms` is
  also true).

## `feature_support` flags expected

| Flag | Expected | Why |
|---|---|---|
| `coverage_terms` | `true` | `coverages/Flood/config.json` carries a non-empty `coverageTerms: [...]` array (one term: `deductible`). |
| `default_option_prefix` | `true` | The `deductible` term's `options` list contains `"*500"` (a leading `*` marks the default option). |
| `nested_iterables` | `false` | No data-extension type ending in `+` / `*` with a non-primitive base. |
| `custom_data_types` | `false` | No `customDataTypes/` directory. |
| `recursive_cdts` | `false` | No CDTs at all. |
| `array_data_extensions` | `false` | No data-extension type ends in `+` / `*`. |
| `auto_elements` | `false` | No `!` anywhere. |
| `jurisdictional_scopes` | `false` | No `qualification` / `appliesTo` / `exclusive` keys. |
| `peril_based` | `false` | No `perils/` directory. |
| `multi_product` | `false` | One product subdir (`FloodProtection/`). |

`coverage_terms` and `default_option_prefix` are both **refusal flags**
per `CONFIG_COVERAGE.md` §4. The shape probe emits two §7
Unrecognised inputs rows (alphabetical:
`feature_support.coverage_terms`,
`feature_support.default_option_prefix`), and the
`dwellings.flood_deductible` loop field (the only placeholder whose
name suggests a coverage-term lookup) is downgraded to `low` +
`needs-skill-update`.

## Behaviour proven

1. **Presence of a non-empty `coverageTerms` list flips the flag.**
   `detect_features()` inspects every coverage config for a
   `coverageTerms` key whose value is a non-empty list. An empty list
   or a missing key leaves the flag `false`. The fixture proves the
   positive case.
2. **`default_option_prefix` is a dependent flag.** It only fires
   when `coverage_terms` is also `true` *and* at least one option
   string starts with `*` (scanned in `detect_features()`). The
   fixture's `"*500"` option is the canonical trigger.
3. **Extractor emits term paths.** `extract_coverage_terms()` reads
   each `coverageTerms` entry and emits a `terms` row on the coverage
   block — the `Flood` block in the golden registry now carries the
   `deductible` term (`field: deductible`,
   `velocity: $dwelling.Flood.deductible.value`,
   `options: ["250", "*500", "1000"]`) alongside its one `data` field
   (`effectiveDate`). This realises `CONFIG_COVERAGE.md` row 9's "In
   registry today?" column: `yes`.
4. **Coverage `data` fields still resolve cleanly.** The
   `flood_effective_date` placeholder matches
   `$dwelling.Flood.data.effectiveDate` at `high`. The refusal is
   scoped: only placeholders whose resolution plausibly depends on
   a term lookup are downgraded. `data`-map fields on the same
   coverage are unaffected.
5. **Missing-registry-candidate placeholder refuses, does not
   supply-from-plugin.** `dwellings.flood_deductible` has no
   registry candidate — Rule 2 step 5 (no match, no loop_hint)
   would normally fire with `low` + `supply-from-plugin`. Because
   `coverage_terms: true` AND the placeholder's name prefix
   matches a coverage AND the term exists in the coverage config
   (just not in the registry), the refusal rule supersedes: `low`
   + `needs-skill-update: coverage_terms / default_option_prefix
   refusal`. This matches the `multi_product` precedent where
   `roof_material` refuses rather than supplies-from-plugin.
6. **Two flags, two §7 rows.** Each refusal flag surfaces its own
   row in `.review.md` §7 (one per flag, alphabetical order),
   mirroring the `nested-iterables/` convention where three flags
   produce three rows. The affected placeholder's `needs-skill-update`
   text enumerates both flags in the next-action.
7. **Refusal-row wording is canonical.** §7 rows read exactly:
   `needs-skill-update: coverage_terms is true but SKILL has no
   rule; extend or refuse` and
   `needs-skill-update: default_option_prefix is true but SKILL has
   no rule; extend or refuse` — the wording mandated by SKILL.md
   Step 2a's "Feature-support refusal rule" bullet.

## Inputs

- `socotra-config/products/FloodProtection/config.json` —
  `contents: ["Dwelling+"]`, no charges, no policy data.
- `socotra-config/exposures/Dwelling/config.json` —
  `contents: ["Flood"]`, 1 data field (`address: string`).
- `socotra-config/coverages/Flood/config.json` — 1 `data` field
  (`effectiveDate: datetime`), 1 `coverageTerms` entry
  (`deductible` with options `["250", "*500", "1000"]`). The term's
  `*500` default prefix is the minimal trigger for
  `default_option_prefix`.
- `mapping.yaml` — 1 variable (`policy_number`), 1 loop
  (`dwellings`) with 3 fields
  (`address` plain-exposure-field,
  `flood_effective_date` coverage-data-field,
  `flood_deductible` coverage-term refusal).

## Goldens

- `golden/path-registry.yaml` — 20 total addressable paths (8
  system + 9 account + 0 policy + 1 exposure field + 1 coverage
  field + 1 coverage term); 1 iterable (Dwelling+); 1 coverage (Flood
  with 1 data field + 1 term — `deductible`);
  `feature_support.coverage_terms: true`,
  `feature_support.default_option_prefix: true`, every other flag
  `false`.
- `golden/suggested.yaml` — 4 `high` (`policy_number`, `dwellings`,
  `dwellings.address`, `dwellings.flood_effective_date`), 0
  `medium`, 1 `low` (`dwellings.flood_deductible` with
  `needs-skill-update: coverage_terms / default_option_prefix
  refusal`).
- `golden/review.md` — 1 blocker
  (`dwellings.flood_deductible`), 0 assumptions, 0 cross-scope
  warnings, 4 done items, 2 §7 rows
  (alphabetical: `feature_support.coverage_terms`,
  `feature_support.default_option_prefix`).
