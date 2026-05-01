# cdt-flat — custom data type used as a scalar field reference

## Purpose

Proves that `extract_paths.py` flips `custom_data_types: true` when a
`customDataTypes/<Name>/config.json` parses, and that a data-extension
field typed as a non-iterable CDT (`"type": "Address"` — no quantifier)
emits a single registry entry with `custom_type_ref: <Name>` — **without**
recursive expansion of the CDT's own fields. The mapping-suggester
refuses to emit a `high` match for any placeholder whose resolution
depends on walking the CDT.

This is the scalar counterpart to `nested-iterables/` (which covers the
iterable `+`/`*` CDT-reference shape). Between the two fixtures the full
CDT-reference contract is exercised in both scalar and iterable forms.

## `CONFIG_COVERAGE.md` rows covered

§3.4 — Custom data types:

- **Row 15** — Custom data type (flat) — directly exercised. Address
  CDT with 3 scalar data fields (`street`, `city`, `postalCode`); no
  self-reference. `detect_features()` detects it via
  `_iter_subdir_configs(customDataTypes)` parsing at least one
  `config.json` under `customDataTypes/` and flips
  `custom_data_types: true`.
- **Row 16** — CDT references another CDT — NOT directly exercised
  here (Address doesn't reference any other CDT). This row still
  points at `cdt-flat/` because the detection + refusal machinery is
  identical to row 15; a dedicated fixture for chain-referencing can
  be added later without blocking row 16's refusal contract.

## `feature_support` flags expected

| Flag | Expected | Why |
|---|---|---|
| `custom_data_types` | `true` | `customDataTypes/Address/config.json` parses (3 scalar data fields). |
| `nested_iterables` | `false` | `dwellingAddress.type = "Address"` — no `+` / `*` suffix, so the data-extension is not iterable. Nested-iterable status requires BOTH iterable quantifier AND non-primitive base type. |
| `recursive_cdts` | `false` | Address does not reference itself in its own `data` map. |
| `array_data_extensions` | `false` | No data-extension type ends in `+` or `*`. |
| `auto_elements` | `false` | No `!` anywhere. |
| `jurisdictional_scopes` | `false` | No `qualification` / `appliesTo` / `exclusive`. |
| `peril_based` | `false` | No `perils/` directory. |
| `multi_product` | `false` | One product subdir (`Homeowner/`). |
| `coverage_terms` | `false` | No coverages at all. |
| `default_option_prefix` | `false` | Requires `coverage_terms` first. |

`custom_data_types` is a **refusal flag** per `CONFIG_COVERAGE.md` §4;
the shape probe emits exactly one §7 Unrecognised inputs row
(`feature_support.custom_data_types`), and the `dwelling_address`
loop field is downgraded to `low` + `needs-skill-update`.

## Behaviour proven

1. **CDT is detected by structural scan, not by file presence alone.**
   `detect_features()` runs `_iter_subdir_configs` which requires
   `<name>/config.json` to parse — not just the directory to exist.
   An empty or malformed `customDataTypes/` tree would keep the flag
   `false`. This is the canonical regression for
   `CONFIG_COVERAGE.md` §3.4's "structural inspection, not file
   presence" rule.
2. **CDT fields are NOT emitted as addressable paths.** The registry
   carries `$policyholder.data.dwellingAddress` as a single entry
   with `custom_type_ref: Address`, `iterable: false`,
   `quantifier: ''`. It does NOT carry
   `$policyholder.data.dwellingAddress.street`,
   `.city`, or `.postalCode`. Any placeholder targeting a CDT
   sub-field has **no registry match** and Rule 2 step 5 would fire
   (`low` + `supply-from-plugin`) except that the refusal rule
   takes precedence and routes it to `needs-skill-update`.
3. **Unaffected entries stay `high`.** `policy_number` (system),
   `policyholders` (iterable loop head), and
   `policyholders.full_name` (plain scalar exposure field) all
   resolve to `high` — proving refusal is scoped per-entry by
   `custom_type_ref` presence, not per-run.
4. **Refusal-row wording is canonical.** §7 row reads exactly:
   `needs-skill-update: custom_data_types is true but SKILL has no
   rule; extend or refuse` — the wording mandated by SKILL.md
   Step 2a's "Feature-support refusal rule" bullet. Agents
   regression-diff this fixture to catch drift in the rule
   wording.

## Inputs

- `socotra-config/products/Homeowner/config.json` — `contents:
  ["Policyholder+"]`, no charges, no policy data fields. The `+`
  makes Policyholder iterable so a `policyholders` loop in the
  mapping has a matching entry in the registry's `iterables:`
  index.
- `socotra-config/exposures/Policyholder/config.json` — 2 data
  fields (`fullName: string`, `dwellingAddress: Address`), no
  contents (no coverages).
- `socotra-config/customDataTypes/Address/config.json` — 3 scalar
  data fields (`street`, `city`, `postalCode`).
- `mapping.yaml` — 1 variable (`policy_number`), 1 loop
  (`policyholders`) with 2 fields (`full_name` plain-scalar,
  `dwelling_address` CDT-reference).

## Goldens

- `golden/path-registry.yaml` — 19 total addressable paths (8 system
  + 9 account + 0 policy + 2 exposure fields — fullName and
  dwellingAddress); 1 iterable (Policyholder);
  `feature_support.custom_data_types: true`, every other flag
  `false`.
- `golden/suggested.yaml` — 3 `high` (policy_number, policyholders,
  policyholders.full_name), 0 `medium`, 1 `low`
  (policyholders.dwelling_address with `needs-skill-update`).
- `golden/review.md` — 1 blocker (`policyholders.dwelling_address`),
  0 assumptions, 0 cross-scope warnings, 3 done items, 1 §7 row
  (`feature_support.custom_data_types`).
