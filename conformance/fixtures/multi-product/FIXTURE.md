# multi-product — two products in the same config tree

## Purpose

Proves that `extract_paths.py` flips `multi_product: true` when
`products/` has more than one subdirectory, that the extractor
deterministically picks the alphabetically-first product and silently
drops the rest, and that the mapping-suggester refuses to emit a
`high` match for any placeholder whose resolution would require the
non-selected product's registry.

This is the canonical regression for the cross-product miss described
in `CONFIG_COVERAGE.md` row 20 — without `multi_product` detection, a
multi-product config would silently match against only one product's
paths, making every cross-product placeholder look like a
plain-no-registry-match (Rule 2 step 5 / supply-from-plugin) rather
than the structural gap it actually is.

## `CONFIG_COVERAGE.md` rows covered

§3.5 — Product-structure variants:

- **Row 20** — Multi-product config tree — directly exercised. Two
  product subdirectories (`AutoLine/` and `HomeLine/`);
  `detect_features()` flips `multi_product: true` via
  `len([d for d in products/ if d.is_dir()]) > 1`.

## `feature_support` flags expected

| Flag | Expected | Why |
|---|---|---|
| `multi_product` | `true` | `products/` has two subdirs (`AutoLine/`, `HomeLine/`). |
| `nested_iterables` | `false` | No data-extension type ending in `+` / `*` with a non-primitive base. |
| `custom_data_types` | `false` | No `customDataTypes/` directory. |
| `recursive_cdts` | `false` | No CDTs at all. |
| `array_data_extensions` | `false` | No data-extension type ends in `+` / `*`. |
| `auto_elements` | `false` | No `!` anywhere. |
| `jurisdictional_scopes` | `false` | No `qualification` / `appliesTo` / `exclusive`. |
| `peril_based` | `false` | No `perils/` directory. |
| `coverage_terms` | `false` | No coverages at all. |
| `default_option_prefix` | `false` | Requires `coverage_terms` first. |

`multi_product` is a **refusal flag** per `CONFIG_COVERAGE.md` §4;
the shape probe emits exactly one §7 Unrecognised inputs row
(`feature_support.multi_product`), and any cross-product placeholder
is downgraded to `low` + `needs-skill-update`.

## Behaviour proven

1. **Multi-product detection is count-based, not name-based.**
   `detect_features()` counts subdirectories of `products/`. Every
   directory counts regardless of name — two empty product dirs
   would still flip the flag.
2. **Deterministic product selection.** `build_registry()` sorts
   product subdirectories by name and picks the first. `AutoLine/`
   sorts before `HomeLine/` (`A` < `H`) so the registry reports
   `meta.product: AutoLine` on every run, regardless of the host
   filesystem's `iterdir()` order. This was not true before session
   C3 — the sort was added in C3 to make multi-product fixtures
   reproducible across OSes.
3. **Non-selected products are silently dropped.** `HomeLine/`'s
   `contents: ["Dwelling+"]` never reaches the registry: no Dwelling
   iterable, no Dwelling exposure fields, no HomeLine policy data
   fields. From the registry's perspective, HomeLine does not
   exist. The refusal flag is the only signal that the drop
   happened.
4. **Selected-product matches stay high.** `policy_number` (system),
   `vehicles` (AutoLine's Vehicle+ iterable), and `vehicles.vin`
   (Vehicle exposure field) all resolve to `high`. The
   `multi_product` refusal does NOT blanket-downgrade every match
   in a multi-product registry — it only affects placeholders whose
   resolution depends on the non-selected product's registry.
5. **Cross-product placeholders are downgraded.** `roof_material`
   (a name that would plausibly match HomeLine's Dwelling or a
   HomeLine-specific policy field if HomeLine were selected) has
   no candidate in the AutoLine registry. Rule 2 step 5 would
   normally fire (`low` + `supply-from-plugin`), but the refusal
   rule takes precedence → `low` + `needs-skill-update:
   multi_product refusal` with the flag-level §7 row.
6. **Refusal-row wording is canonical.** §7 row reads exactly:
   `needs-skill-update: multi_product is true but SKILL has no
   rule; extend or refuse` — the wording mandated by SKILL.md
   Step 2a's "Feature-support refusal rule" bullet.

## Inputs

- `socotra-config/products/AutoLine/config.json` —
  `contents: ["Vehicle+"]`, no charges, no policy data fields.
  Selected by `build_registry()` (first alphabetically).
- `socotra-config/products/HomeLine/config.json` —
  `contents: ["Dwelling+"]`. Silently dropped by the extractor;
  only contributes to the `multi_product` flag flip.
- `socotra-config/exposures/Vehicle/config.json` — 1 data field
  (`vin: string`). Used by AutoLine.
- **No** `exposures/Dwelling/` directory — HomeLine's `Dwelling+`
  content token references an exposure that is not present in the
  shared `exposures/` tree. Deliberate: if `Dwelling/` existed
  under `exposures/`, `extract_paths.py`'s fallback scan
  ("exposures not in contents default to no-suffix quantifier")
  would pick it up into AutoLine's registry with `quantifier: ''`,
  polluting the cross-product regression by making HomeLine-shaped
  placeholders partially matchable. The refusal fires cleanly
  only when the cross-product placeholder has no registry
  candidate at all.
- `mapping.yaml` — 2 variables (`policy_number`, `roof_material`),
  1 loop (`vehicles`) with 1 field (`vin`).

## Goldens

- `golden/path-registry.yaml` — 18 total addressable paths (8
  system + 9 account + 0 policy + 1 exposure field — Vehicle.vin);
  1 iterable (Vehicle+); `feature_support.multi_product: true`,
  every other flag `false`.
- `golden/suggested.yaml` — 3 `high` (`policy_number`, `vehicles`,
  `vehicles.vin`), 0 `medium`, 1 `low` (`roof_material` with
  `needs-skill-update: multi_product refusal`).
- `golden/review.md` — 1 blocker (`roof_material`), 0 assumptions,
  0 cross-scope warnings, 3 done items, 1 §7 row
  (`feature_support.multi_product`).
