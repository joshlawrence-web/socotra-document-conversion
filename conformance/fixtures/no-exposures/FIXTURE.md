# no-exposures — monoline product with zero exposures

## Purpose

Exercises a product whose `contents` list is **empty** and whose
config tree has **no `exposures/` directory** at all. Every piece of
data lives on the policy (`$data.data.*`) or the account
(`$data.account.data.*`) — there is nothing to loop over. This is the
canonical regression for the absence-of-exposure case: it proves that
`extract_paths.py` emits a stable registry (empty `iterables:`, empty
`exposures:`, still-populated `system_paths` / `account_paths` /
`policy_data`) and that the mapping-suggester handles variables-only
mappings cleanly.

This fixture is the flip-side of `all-quantifiers/`: where
`all-quantifiers/` stresses every quantifier suffix, `no-exposures/`
proves the pipeline does not **assume** any quantifier exists.

## `CONFIG_COVERAGE.md` rows covered

§3.1 — Quantifiers on exposure `contents`:

- **Row 5** — Exposure no-suffix — the canonical regression for the
  absence-of-exposure case (complementing `minimal/`'s no-suffix
  `Vehicle` coverage). Proves that `build_registry()` does not
  fabricate an exposure when `contents: []` and no `exposures/`
  directory exists.

§3.5 — Product-structure variants:

- **Row 21** — Non-`$data` root object (plugin-supplied
  `renderingData`) — partial / indirect. The fixture keeps the `$data`
  root but stresses the "everything flat on the policy" shape that a
  plugin-flattened template would mirror. No dedicated
  `feature_support` flag exists for this row (per §3.5's Notes cell);
  treat as satisfied-by-proxy and revisit when a future B2 decision
  carves out a flag.

§3.7 — Account-type variation:

- **Row 25** — Account type variation — indirect. Same gap as
  `minimal/` exposes (hard-coded 9-row `account_paths` block,
  independent of `accounts/` contents). `no-exposures/` leans harder
  on the account paths than `minimal/` does because there is no
  exposure-side data to draw from, so `account_name` is the only
  way to prove accounts still resolve when exposures are absent.

## `feature_support` flags expected

Every flag `false`. `no-exposures/` deliberately contains no `!`,
`?`, `+`, or `*` suffixes anywhere, no `coverageTerms`, no
`customDataTypes/`, no `perils/`, only one product subdir, and no
`qualification` / `appliesTo` / `exclusive` keys. Any flag flipping
to `true` on this fixture indicates `detect_features()` has gained
a false positive — specifically one that misfires when the config
has no exposures.

## Behaviour proven

1. **Registry emits cleanly with zero exposures.**
   `build_registry()` produces `iterables: []` and `exposures: []`
   (both empty lists, not missing keys) when `product.contents: []`
   and no `exposures/` directory exists. System paths (8), account
   paths (9), and policy-data fields (2) still emit as usual. The
   `meta.note` block remains unchanged — the "Exposure lists" /
   "Exposure fields" phrasing in the note is a reference, not a
   requirement that exposures actually exist.
2. **Variables-only mapping is fully resolvable.** Every placeholder
   in the mapping matches a non-iterable registry entry with
   `requires_scope: []`. The suggester never needs to consult
   `iterables:` and never fires Rule 2's scope-inheritance logic.
   All three matches are `high`, zero blockers.
3. **Policy-data scalars round-trip.** `policy_ref` and
   `submitted_at` match the two fields declared under
   `products/Mono/config.json` `data:` map, emitted as
   `$data.data.policyRef` and `$data.data.submittedAt`. This is the
   canonical regression for the `policy_data` extraction path.
4. **Account paths resolve without any exposure context.**
   `account_name` matches the hard-coded `$data.account.data.name`
   entry — proves the account-path block does not silently depend on
   the presence of exposures (a previous assumption worth
   regression-locking).
5. **No `feature_support` flags fire on absence.** Every flag stays
   `false`. The empty `contents:` list in particular must not flip
   `multi_product` (`multi_product` counts product subdirs, not
   product contents), `coverage_terms` (no coverages at all), or
   `peril_based` (no `perils/` directory). This fixture complements
   `minimal/` by exercising the "no contents at all" branch.
6. **No `Unrecognised inputs` row.** The `.review.md` §7 section
   renders "No unrecognised inputs." — every registry top-level
   section is recognised, every mapping context key is recognised,
   and every `feature_support` flag is `false`.

## Inputs

- `socotra-config/products/Mono/config.json` —
  `contents: []`, `charges: []`, 2 policy-data fields
  (`policyRef: string`, `submittedAt: datetime`).
- No `socotra-config/exposures/` directory.
- No `socotra-config/coverages/` directory.
- No `socotra-config/customDataTypes/` directory.
- No `socotra-config/perils/` directory.
- `mapping.yaml` — 3 variables
  (`policy_ref`, `submitted_at`, `account_name`), 0 loops. All three
  `data_source` fields blank.

## Goldens

- `golden/path-registry.yaml` — 19 addressable paths (8 system + 9
  account + 2 policy + 0 exposure + 0 coverage); 0 iterables; 0
  exposures; `feature_support` — all 10 flags `false`.
- `golden/suggested.yaml` — 3 `high`, 0 `medium`, 0 `low`; 0
  next-actions; every variable resolves cleanly.
- `golden/review.md` — 0 blockers, 0 assumptions, 0 cross-scope
  warnings, 3 done items, 0 unrecognised-inputs rows.
