# cdt-recursive — self-referential custom data type

## Purpose

Proves that `extract_paths.py` flips `recursive_cdts: true` when a CDT
contains a field whose base-type equals the CDT's own name, *and* that
this flag is surfaced **in addition to** `custom_data_types: true`
(never instead of). Proves the mapping-suggester emits TWO `§7
Unrecognised inputs` rows — one per refusal flag — when both are true
on the same run, and that the affected loop field is downgraded to
`low` + `needs-skill-update` per `CONFIG_COVERAGE.md` §4.

This is the third and final C2 nested-shape fixture. Together with
`nested-iterables/` (iterable data-extension of a CDT) and `cdt-flat/`
(scalar reference to a flat CDT), it completes the current refusal
contract for all three CDT/nested-iterable axes.

## `CONFIG_COVERAGE.md` rows covered

§3.4 — Custom data types:

- **Row 15** — Custom data type (flat) — transitively exercised
  (Address parses as a CDT, which is what flips
  `custom_data_types: true`).
- **Row 17** — CDT recursive (self-reference) — directly exercised.
  Address contains `subAddress: Address?`; `detect_features()` walks
  every CDT's `data` map and flips `recursive_cdts: true` when it
  finds a field whose base-type (after quantifier stripping) equals
  the CDT's own name.

## `feature_support` flags expected

| Flag | Expected | Why |
|---|---|---|
| `custom_data_types` | `true` | `customDataTypes/Address/config.json` parses (3 data fields). |
| `recursive_cdts` | `true` | `Address.subAddress.type = "Address?"` → `parse_quantified_token("Address?") == ("Address", "?")`, and `"Address" == cdt_name` matches line 435 of `extract_paths.py`. Quantifier `?` does NOT prevent detection — only the base-type identity matters. |
| `nested_iterables` | `false` | `dwellingAddress.type = "Address"` has no quantifier; `subAddress.type = "Address?"` has `?` (not iterable). Nested-iterable status requires BOTH iterable quantifier (`+` / `*`) AND non-primitive base type. |
| `array_data_extensions` | `false` | No data-extension type uses `+` or `*`. |
| `auto_elements` | `false` | No `!` anywhere. |
| `jurisdictional_scopes` | `false` | No `qualification` / `appliesTo` / `exclusive`. |
| `peril_based` | `false` | No `perils/` directory. |
| `multi_product` | `false` | One product subdir (`Chain/`). |
| `coverage_terms` | `false` | No coverages at all. |
| `default_option_prefix` | `false` | Requires `coverage_terms` first. |

Both `custom_data_types` and `recursive_cdts` are **refusal flags**
per `CONFIG_COVERAGE.md` §4; the shape probe emits exactly TWO §7
Unrecognised inputs rows (alphabetized: `custom_data_types` before
`recursive_cdts`), and the `dwelling_address` loop field carries one
combined `needs-skill-update` downgrade.

## Behaviour proven

1. **Detection sees through quantifiers.** `subAddress.type =
   "Address?"` still flips `recursive_cdts` because
   `parse_quantified_token` strips the `?` before equality-checking
   against the CDT name. A CDT that self-references through any
   quantifier (`?`, `+`, `*`, or none) triggers the flag — the
   canonical regression for `extract_paths.py` line 435.
2. **`recursive_cdts` implies `custom_data_types`.** Logically a CDT
   must parse for `recursive_cdts` to possibly be true, so the two
   flags co-fire. The fixture explicitly asserts both rows show up in
   `review.md` §7 (one is not a substitute for the other; the
   refusal rule enumerates each flag independently).
3. **Combined refusal message.** The loop field's `reasoning` names
   both flags and the `blocker` entry's
   `next-action` header reads `needs-skill-update:
   custom_data_types + recursive_cdts refusal`. This regression-tests
   SKILL.md's "when multiple refusal flags affect the same field,
   attribute both" rule (implicit in Step 2a — every flag surfaces
   independently in §7).
4. **CDT sub-fields still NOT emitted.** Same contract as `cdt-flat/`
   — the registry carries `$policyholder.data.dwellingAddress` with
   `custom_type_ref: Address` but does NOT emit
   `$policyholder.data.dwellingAddress.street`,
   `.city`, or `.subAddress`. Recursion depth is zero by
   construction; a future skill extension must ADD the walker AND
   the termination rule in the same PR.
5. **Refusal is per-field, not per-run.** `policy_number`,
   `policyholders`, and `policyholders.full_name` stay `high` —
   proving that the mere presence of two refusal flags does not
   poison unrelated high-confidence matches.

## Inputs

- `socotra-config/products/Chain/config.json` — `contents:
  ["Policyholder+"]`, no charges, no policy data fields.
- `socotra-config/exposures/Policyholder/config.json` — 2 data
  fields (`fullName: string`, `dwellingAddress: Address`), no
  contents.
- `socotra-config/customDataTypes/Address/config.json` — 3 data
  fields (`street: string`, `city: string`,
  `subAddress: Address?`). The `?` quantifier on a self-reference
  makes the recursion optional at each level — the canonical shape
  for linked-list-like CDTs (Socotra Buddy corpus row 17 example).
- `mapping.yaml` — 1 variable (`policy_number`), 1 loop
  (`policyholders`) with 2 fields (`full_name` plain-scalar,
  `dwelling_address` CDT-reference).

## Goldens

- `golden/path-registry.yaml` — 19 total addressable paths
  (identical shape to `cdt-flat/`); `feature_support.custom_data_types:
  true` AND `feature_support.recursive_cdts: true`, every other flag
  `false`.
- `golden/suggested.yaml` — 3 `high` (policy_number, policyholders,
  policyholders.full_name), 0 `medium`, 1 `low`
  (policyholders.dwelling_address with combined
  custom_data_types + recursive_cdts refusal).
- `golden/review.md` — 1 blocker (`policyholders.dwelling_address`),
  0 assumptions, 0 cross-scope warnings, 3 done items, 2 §7 rows
  (`feature_support.custom_data_types`, then
  `feature_support.recursive_cdts`, alphabetical).
