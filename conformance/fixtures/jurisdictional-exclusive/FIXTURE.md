# jurisdictional-exclusive — coverage with `exclusive` + `appliesTo`

## Purpose

Proves that `extract_paths.py`'s `jurisdictional_scopes` detection
fires on the `exclusive` and `appliesTo` keys, not just the
`qualification` key covered by the sibling `jurisdictional/` fixture.
`detect_features()` at line 455 of `extract_paths.py` uses
`any(k in cov_cfg for k in ("qualification", "appliesTo", "exclusive"))`
— any one of the three keys flips the flag, and the fixture pair
regression-covers two different branches of the same `any(...)`.

This fixture was authored in session C3 as the substitution for the
originally-planned `peril-based/` fixture. Per the C3 handoff block
in [PIPELINE_EVOLUTION_PLAN.md](../../../.cursor/plans/pipeline-improvements/CompletedPlans/alpha-beta-plan/PIPELINE_EVOLUTION_PLAN.md), the peril-based pattern could not
be confirmed in the mirrored Socotra docs
(`~/socotra-buddy/resources/derived/` has exactly one hit for
"peril", and that hit uses the word conversationally to describe
coverages like comprehensive and collision — NOT to describe a
`perils/<Name>/config.json` directory layout). The handoff
explicitly permits swapping `peril-based/` for a second
jurisdictional variant when the corpus citation comes up empty; this
fixture is that swap. `peril_based` remains in the refusal flag
vocabulary (the detection code is already present at
`extract_paths.py` lines 417–419) but has no fixture coverage in
this session — see `CONFIG_COVERAGE.md` row 18 and the C3 handoff
for the trail.

## `CONFIG_COVERAGE.md` rows covered

§3.5 — Product-structure variants:

- **Row 19** — Jurisdictional qualifier on coverage — partial
  (companion-to `jurisdictional/`). This fixture exercises the
  `exclusive` + `appliesTo` branches of the detection; the
  sibling exercises the `qualification` branch. Both flip the
  same flag and route through the same refusal contract — the
  split across two fixtures is purely a regression-coverage
  concern for the three distinct keys.

## `feature_support` flags expected

| Flag | Expected | Why |
|---|---|---|
| `jurisdictional_scopes` | `true` | `coverages/Umbrella/config.json` carries both `exclusive: true` AND `appliesTo: ["claim"]`. |
| `nested_iterables` | `false` | No data-extension type ending in `+` / `*` with a non-primitive base. |
| `custom_data_types` | `false` | No `customDataTypes/` directory. |
| `recursive_cdts` | `false` | No CDTs at all. |
| `array_data_extensions` | `false` | No data-extension type ends in `+` / `*`. |
| `auto_elements` | `false` | No `!` anywhere. |
| `peril_based` | `false` | No `perils/` directory. |
| `multi_product` | `false` | One product subdir (`SpecialAuto/`). |
| `coverage_terms` | `false` | Umbrella has no `coverageTerms` array. |
| `default_option_prefix` | `false` | Requires `coverage_terms` first. |

`jurisdictional_scopes` is a **refusal flag** per
`CONFIG_COVERAGE.md` §4; the shape probe emits exactly one §7
Unrecognised inputs row (`feature_support.jurisdictional_scopes`),
and the `umbrella_limit` loop field is downgraded to `low` +
`needs-skill-update`.

## Behaviour proven

1. **`exclusive: true` alone would flip the flag.** The fixture
   includes both keys on purpose — one coverage carrying both
   proves `any(...)` short-circuits correctly and that multiple
   jurisdictional keys on a single coverage do NOT multi-count
   (one §7 row, not two). Dropping either key and re-running
   `extract_paths.py` against this fixture would still emit
   `jurisdictional_scopes: true`.
2. **Single §7 row despite two contributing keys.** The shape
   probe surfaces one Unrecognised-inputs row per `true` flag, not
   per underlying config key that contributed. This is the same
   convention C2's `nested-iterables/` fixture proved in reverse
   (three flags from one field → three §7 rows); here one flag
   from two keys → one §7 row.
3. **Non-jurisdictional placeholders stay high.** `policy_number`,
   `vehicles`, and `vehicles.vin` resolve to `high`. The refusal
   is scoped to the placeholder whose path traverses the
   jurisdictional coverage, not the whole run.
4. **Refusal-row wording matches the sibling fixture.** Both
   jurisdictional fixtures emit the identical §7 row wording:
   `needs-skill-update: jurisdictional_scopes is true but SKILL
   has no rule; extend or refuse`. The wording is per-flag, not
   per-key — agents regression-diff both fixtures to catch drift.

## Inputs

- `socotra-config/products/SpecialAuto/config.json` —
  `contents: ["Vehicle+"]`, no charges, no policy data fields.
- `socotra-config/exposures/Vehicle/config.json` —
  `contents: ["Umbrella"]`, 1 data field (`vin: string`).
- `socotra-config/coverages/Umbrella/config.json` —
  `exclusive: true`, `appliesTo: ["claim"]`, 1 data field
  (`limit: int`). No `qualification` key (that branch is covered
  by the sibling `jurisdictional/` fixture).
- `mapping.yaml` — 1 variable (`policy_number`), 1 loop
  (`vehicles`) with 2 fields (`vin` plain-exposure-field,
  `umbrella_limit` jurisdictional-coverage-field).

## Goldens

- `golden/path-registry.yaml` — 19 total addressable paths (8
  system + 9 account + 0 policy + 1 exposure field + 1 coverage
  field); 1 iterable (Vehicle+); 1 coverage (Umbrella with 1
  field); `feature_support.jurisdictional_scopes: true`, every
  other flag `false`.
- `golden/suggested.yaml` — 3 `high` (`policy_number`, `vehicles`,
  `vehicles.vin`), 0 `medium`, 1 `low` (`vehicles.umbrella_limit`
  with `needs-skill-update: jurisdictional_scopes refusal`).
- `golden/review.md` — 1 blocker (`vehicles.umbrella_limit`), 0
  assumptions, 0 cross-scope warnings, 3 done items, 1 §7 row
  (`feature_support.jurisdictional_scopes`).
