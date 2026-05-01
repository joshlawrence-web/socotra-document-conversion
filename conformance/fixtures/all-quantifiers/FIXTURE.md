# all-quantifiers — every Socotra quantifier suffix

## Purpose

Verifies that `extract_paths.py` correctly encodes **every Socotra
quantifier suffix** (`''`, `!`, `?`, `+`, `*`) on `contents` tokens
(product → exposure, exposure → coverage) and on data-extension `type`
strings. Also exercises the two matching rules that key off
quantifiers: Rule 4 (optional-element `#if` guard) and Rule 5
(auto-element note).

Deliberately contains **no** custom data types, jurisdictional
qualifiers, peril-based structures, coverage terms, or iterable
data-extensions. Those live in their own fixtures (`cdt-flat/`,
`jurisdictional/`, `peril-based/`, `coverage-terms/`,
`nested-iterables/` — all pending in later Phase C sessions).

## `CONFIG_COVERAGE.md` rows covered

§3.1 — Quantifiers on exposure `contents`:

- **Row 1** — `Vehicle+` on product `contents` (one-or-more, iterable).
- **Row 2** — `Driver*` on product `contents` (any, iterable).
- **Row 3** — `Addon?` on product `contents` (zero-or-one, not
  iterable). Registry shape only; not exercised by a placeholder.
- **Row 4** — `SpecialUnit!` on product `contents` (exactly-one
  auto-created, flips `auto_elements`). Registry shape only.
- **Row 5** — `Policyholder` (no suffix) on product `contents`
  (exactly-one, not iterable). Registry shape only.

§3.2 — Quantifiers on coverage `contents`:

- **Row 6** — `MedPay?` on Vehicle `contents` — zero-or-one coverage.
  Exercised by `medpay_limit` placeholder: Rule 4 adds the
  `#if($vehicle.MedPay)` guard note to `reasoning` without
  downgrading confidence.
- **Row 7** — `Comp!` on Vehicle `contents` — auto-created coverage,
  flips `auto_elements`. Exercised by `comp_limit` placeholder:
  Rule 5 adds the auto-element note to `reasoning`.
- **Row 8** — `Coll` (no suffix) on Vehicle `contents` — exactly-one
  coverage. Exercised by `coll_deductible` placeholder (high, no
  Rule 4/5 note).

§3.3 — Quantifiers on data-extension `type`:

- **Row 11** — `type: "string?"` on the product's `refNumber`
  data field — zero-or-one scalar. Exercised by `ref_number`
  placeholder: Rule 4 adds the `#if($data.data.refNumber)` guard
  note to `reasoning`.

## `feature_support` flags expected

| Flag | Expected | Why |
|---|---|---|
| `auto_elements` | `true` | `SpecialUnit!` (product contents) and `Comp!` (Vehicle contents) each carry `!`. |
| `nested_iterables` | `false` | No data-extension `type` ends in `<CDT>+` or `<CDT>*`. |
| `custom_data_types` | `false` | No `customDataTypes/` directory. |
| `recursive_cdts` | `false` | No CDTs at all. |
| `jurisdictional_scopes` | `false` | No `qualification` / `appliesTo` / `exclusive` keys. |
| `peril_based` | `false` | No `perils/` directory. |
| `multi_product` | `false` | One product subdir (`Multi/`). |
| `coverage_terms` | `false` | No coverage has a `coverageTerms` key. |
| `default_option_prefix` | `false` | Requires `coverage_terms` first. |
| `array_data_extensions` | `false` | `string?` is zero-or-one, not `+`/`*`. No data-extension type ends in `+` or `*`. |

`auto_elements` being `true` does **not** trigger the feature-support
refusal rule — `auto_elements` is on the SKILL's rule-supported flag
whitelist (Rule 5 handles it). No `needs-skill-update:` row appears in
`review.md §7`.

## Behaviour proven

1. **Quantifier round-trip through the registry.** Every exposure
   quantifier and every coverage quantifier survives
   `build_registry()` intact: `quantifier`, `cardinality`, and
   `iterable` fields on each exposure / coverage match the source
   contents token. Data-extension `type` strings carrying `?` are
   preserved as-is (no rewrite).
2. **Iterables index.** Only `Vehicle+` and `Driver*` end up in
   `iterables:`. `Addon?`, `SpecialUnit!`, and `Policyholder` are
   emitted under `exposures:` but NOT in `iterables:`. The registry
   therefore cannot offer them as loop `data_source` candidates —
   Rule 1 would reject them.
3. **Rule 1 — iterable loop match.** The two `loops` entries
   (`vehicles`, `drivers`) both resolve to `$data.vehicles` /
   `$data.drivers` with high confidence; suggester copies
   `list_velocity`, `iterator`, `foreach` verbatim from the
   iterables index and stamps `iterator_velocity` / `foreach` onto
   the suggested YAML.
4. **Rule 2 — scope satisfied.** Every `loop_field` under `vehicles`
   and `drivers` is matched at `high` because `context.loop`
   (`vehicles` or `drivers`) satisfies the candidate's
   `requires_scope`.
5. **Rule 4 — optional-element guard.** Fires twice: once on the
   policy-data field `ref_number` (type `string?`) and once on the
   coverage-field `medpay_limit` (MedPay quantifier `?`). Both
   items stay `high`; the `#if(...)` guard is appended to
   `reasoning` only.
6. **Rule 5 — auto-element note.** Fires once on `comp_limit` (Comp
   quantifier `!`). Item stays `high`; the "auto-created on
   validation; always present" sentence is appended to
   `reasoning`.
7. **Feature-support refusal contract.** `auto_elements: true` does
   NOT produce a `needs-skill-update:` row in `review.md §7`. This
   is the canonical regression check for the rule-supported
   whitelist documented in SKILL.md Step 2a and in
   `CONFIG_COVERAGE.md` §4.

## Inputs

- `socotra-config/products/Multi/config.json` —
  `contents: ["Vehicle+", "Driver*", "Addon?", "SpecialUnit!", "Policyholder"]`,
  2 policy-data fields (`policyRef` string, `refNumber` string?),
  no charges.
- `socotra-config/exposures/{Vehicle,Driver,Addon,SpecialUnit,Policyholder}/config.json` —
  Vehicle carries `contents: ["Coll", "MedPay?", "Comp!"]`. The other
  four exposures are scalar-field-only, no coverages.
- `socotra-config/coverages/{Coll,MedPay,Comp}/config.json` — one
  data field each (`deductible` / `limit` / `limit`).
- `mapping.yaml` — 2 top-level variables (`policy_ref`, `ref_number`),
  2 loops (`vehicles` with 4 fields, `drivers` with 1 field).

## Goldens

- `golden/path-registry.yaml` — 28 paths total; iterables: 2
  (Vehicle+, Driver*); exposures: 5; coverages on Vehicle: 3 (Coll,
  MedPay?, Comp!); `feature_support.auto_elements: true`, every
  other flag `false`.
- `golden/suggested.yaml` — 9 high (2 variables + 2 loops + 5 loop
  fields), 0 medium, 0 low; Rule 4 note on 2 entries, Rule 5 note
  on 1 entry.
- `golden/review.md` — 0 blockers, 0 assumptions, 0 cross-scope
  warnings, 9 done items, 0 unrecognised inputs.
