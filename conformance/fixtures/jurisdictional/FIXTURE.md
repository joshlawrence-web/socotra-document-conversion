# jurisdictional — coverage with a `qualification` key

## Purpose

Proves that `extract_paths.py` flips `jurisdictional_scopes: true`
when any coverage config carries a `qualification` key, and that the
mapping-suggester refuses to emit a `high` match for any placeholder
whose resolution depends on walking into the jurisdiction-conditioned
coverage — even when a registry candidate exists for the requested
field path.

This is the canonical regression for `CONFIG_COVERAGE.md` row 19:
without `jurisdictional_scopes` detection, a jurisdictional coverage
looks shape-identical to an ordinary coverage — Rule 4's
`#if($vehicle.Coverage)` guard is NOT sufficient to express the
jurisdiction predicate, so emitting a `high` match would silently
render the field in every jurisdiction.

## `CONFIG_COVERAGE.md` rows covered

§3.5 — Product-structure variants:

- **Row 19** — Jurisdictional qualifier on coverage — directly
  exercised via the `qualification` key. The companion
  `jurisdictional-exclusive/` fixture exercises the `exclusive` /
  `appliesTo` variants (the other two keys recognised by
  `detect_features()` — any one of the three flips the same flag).

## `feature_support` flags expected

| Flag | Expected | Why |
|---|---|---|
| `jurisdictional_scopes` | `true` | `coverages/Collision/config.json` carries a `qualification` key. |
| `nested_iterables` | `false` | No data-extension type ending in `+` / `*` with a non-primitive base. |
| `custom_data_types` | `false` | No `customDataTypes/` directory. |
| `recursive_cdts` | `false` | No CDTs at all. |
| `array_data_extensions` | `false` | No data-extension type ends in `+` / `*`. |
| `auto_elements` | `false` | No `!` anywhere. |
| `peril_based` | `false` | No `perils/` directory. |
| `multi_product` | `false` | One product subdir (`SingleState/`). |
| `coverage_terms` | `false` | Collision has no `coverageTerms` array. |
| `default_option_prefix` | `false` | Requires `coverage_terms` first. |

`jurisdictional_scopes` is a **refusal flag** per
`CONFIG_COVERAGE.md` §4; the shape probe emits exactly one §7
Unrecognised inputs row
(`feature_support.jurisdictional_scopes`), and the
`collision_deductible` loop field (the only placeholder that touches
the jurisdictional coverage) is downgraded to `low` +
`needs-skill-update`.

## Behaviour proven

1. **`qualification` on a coverage is enough to flip the flag.**
   `detect_features()` scans every coverage's config for
   `qualification` / `appliesTo` / `exclusive` (line 455 of
   `extract_paths.py`). A `qualification` object of **any** shape
   (the fixture uses `{ "jurisdiction": "CA" }`) fires the flag —
   the contents of the object are not inspected; only the key
   presence is checked.
2. **Non-jurisdictional placeholders stay high.** `policy_number`
   (system path), `vehicles` (Vehicle+ iterable), and
   `vehicles.vin` (plain Vehicle exposure field) all resolve to
   `high`. The refusal is scoped to the specific placeholder whose
   path traverses the jurisdictional coverage, not the whole run.
3. **Coverage-field match surfaces despite the refusal.** The
   registry still emits `$vehicle.Collision.data.deductible` as a
   normal coverage field — `extract_paths.py` does not suppress
   entries based on the flag. The refusal is a suggester-side
   contract: SKILL.md Step 2a downgrades the match to `low` +
   `needs-skill-update` rather than dropping it or emitting `high`.
   This matches the `CONFIG_COVERAGE.md` §4 rule: "If the registry
   happens to emit a matchable shape … set `confidence: low` and
   pair with `next_action: needs-skill-update` — do not silently
   emit a `high` match."
4. **Refusal-row wording is canonical.** §7 row reads exactly:
   `needs-skill-update: jurisdictional_scopes is true but SKILL
   has no rule; extend or refuse` — the wording mandated by
   SKILL.md Step 2a's "Feature-support refusal rule" bullet.
5. **Rule 4 is insufficient on its own.** The Collision coverage is
   no-suffix (exactly-one) in Vehicle's `contents`, so Rule 4 would
   ordinarily emit no `#if` guard. Even if Collision were
   optional, `#if($vehicle.Collision)` tests for the coverage's
   attachment but says nothing about jurisdiction. The refusal
   flag is how the suggester communicates that Rule 4 alone cannot
   express the qualification predicate.

## Inputs

- `socotra-config/products/SingleState/config.json` —
  `contents: ["Vehicle+"]`, no charges, no policy data fields, no
  product-level `qualification` (the flag flip comes from the
  coverage, not the product).
- `socotra-config/exposures/Vehicle/config.json` —
  `contents: ["Collision"]`, 1 data field (`vin: string`).
- `socotra-config/coverages/Collision/config.json` —
  `qualification: { jurisdiction: "CA" }`, 1 data field
  (`deductible: int`). The `qualification` object shape is
  illustrative only; `detect_features()` is key-presence-based.
- `mapping.yaml` — 1 variable (`policy_number`), 1 loop
  (`vehicles`) with 2 fields (`vin` plain-exposure-field,
  `collision_deductible` jurisdictional-coverage-field).

## Goldens

- `golden/path-registry.yaml` — 19 total addressable paths (8
  system + 9 account + 0 policy + 1 exposure field + 1 coverage
  field); 1 iterable (Vehicle+); 1 coverage (Collision with 1
  field); `feature_support.jurisdictional_scopes: true`, every
  other flag `false`.
- `golden/suggested.yaml` — 3 `high` (`policy_number`, `vehicles`,
  `vehicles.vin`), 0 `medium`, 1 `low`
  (`vehicles.collision_deductible` with `needs-skill-update:
  jurisdictional_scopes refusal`).
- `golden/review.md` — 1 blocker
  (`vehicles.collision_deductible`), 0 assumptions, 0 cross-scope
  warnings, 3 done items, 1 §7 row
  (`feature_support.jurisdictional_scopes`).
