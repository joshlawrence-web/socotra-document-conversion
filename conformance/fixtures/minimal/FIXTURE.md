# minimal — baseline sanity fixture

## Purpose

Exercises the **smallest viable product config** the pipeline is expected
to handle: one product, one exposure (no-suffix), no coverages, one
policy-data field and one exposure-data field. This fixture is the
canary — if `extract_paths.py` stops emitting a stable registry or the
suggester stops producing deterministic output on this config, every
richer fixture is also broken.

## `CONFIG_COVERAGE.md` rows covered

- **Row 5** (§3.1) — Exposure no-suffix (`Vehicle` on the product's
  `contents`, quantifier `''`, iterable `false`). Verifies the registry
  still emits the exposure under `exposures:` and still threads a
  `requires_scope` through its fields even though it is not in the
  top-level `iterables:` index.
- **Row 25** (§3.7) — Account-type variation (indirect). The fixture
  has no `accounts/` directory yet the registry emits the hard-coded
  9-row `account_paths` block; this is the current gap documented in
  row 25 and serves as the canonical regression marker for the day
  the extractor learns to walk `accounts/<Type>/config.json` for
  real.

## `feature_support` flags expected

Every flag `false`. `minimal/` deliberately contains no `!`, `?`, `+`,
or `*` suffixes anywhere, no `coverageTerms`, no `customDataTypes/`,
no `perils/`, only one product subdir, and no `qualification` /
`appliesTo` / `exclusive` keys. Any flag flipping to `true` on this
fixture indicates `detect_features()` has gained a false positive.

## Behaviour proven

1. Policy-data field (`policyRef`) resolves to `$data.data.policyRef`
   with `confidence: high` via exact display-name match on
   `nearest_label`. No scope issues.
2. Account field (`name`) resolves to `$data.account.data.name` with
   `confidence: high` — exercises the hard-coded `account_paths` block.
3. A no-suffix exposure field (`vin`) still carries
   `requires_scope: [#foreach ($vehicle in $data.vehicles)]` in the
   registry, and the suggester correctly refuses to match it when the
   mapping has no `context.loop` / `context.loop_hint` signal. Rule 2
   step 4 applies: `confidence: low`,
   `next_action: restructure-template`. This is the canonical proof
   that no-suffix and `+` exposures share the same scope contract in
   the registry.

## Inputs

- `socotra-config/products/Mono/config.json` — one product, 1 policy
  field (`policyRef`), `contents: ["Vehicle"]`, no charges.
- `socotra-config/exposures/Vehicle/config.json` — no coverages,
  1 data field (`vin`).
- `mapping.yaml` — 3 variables (`policy_ref`, `account_name`,
  `vehicle_vin`), 0 loops. All three `data_source` fields blank.

## Goldens

- `golden/path-registry.yaml` — 19 paths (8 system + 9 account + 1
  policy + 1 exposure field), 0 iterables, 10 feature flags all
  `false`.
- `golden/suggested.yaml` — 2 `high`, 1 `low`; 1
  `restructure-template` next-action.
- `golden/review.md` — matches the counts above; one blocker,
  `Unrecognised inputs` renders "No unrecognised inputs.".
