# nested-iterables — data-extension array of a custom data type

## Purpose

Proves that `extract_paths.py` correctly flips **three refusal flags
simultaneously** when an exposure carries a data-extension field whose
type is a quantified CDT reference (`"owners": { "type": "Owner+" }`),
and that the mapping-suggester refuses to match any placeholder whose
resolution depends on walking the CDT.

This is the canonical fixture for the intersection of `nested_iterables`,
`custom_data_types`, and `array_data_extensions` — a shape that
`extract_paths.py` deliberately flattens today (the CDT's own data map
is NOT emitted as addressable paths, only the top-level `owners`
reference is).

## `CONFIG_COVERAGE.md` rows covered

§3.3 — Quantifiers on data-extension `type`:

- **Row 12** — `"type": "string+"` class — not directly exercised here
  (the `+` is on `Owner`, a CDT, not on a primitive), but the registry
  emission path and the `array_data_extensions: true` flag are the
  same. `nested-iterables/` is the authoritative fixture for this row.
- **Row 13** — `"type": "int*"` class — not directly exercised but same
  code path as row 12.
- **Row 14** — `"type": "Driver+"` class (data-extension array of a
  custom data type). Directly exercised by Vehicle.owners = Owner+.
  Registry emits `$vehicle.data.owners` with `custom_type_ref: Owner`,
  `iterable: true`, `quantifier: '+'`; **no recursive walk of the
  Owner CDT's own `firstName` / `lastName` fields**. Flips both
  `nested_iterables` and `array_data_extensions`.

§3.4 — Custom data types:

- **Row 15** — Flat CDT (`customDataTypes/Owner/config.json` with
  scalar `data` fields `firstName` and `lastName`). Detected by
  `detect_features()` via `_iter_subdir_configs(customDataTypes)`.
  Flips `custom_data_types`. Note: `cdt-flat/` covers this row in a
  scalar-CDT reference pattern (`Address` as a field type); this
  fixture covers it in an iterable-CDT reference pattern (`Owner+`
  as a field type). The two fixtures together prove the flag fires
  in both reference shapes.

## `feature_support` flags expected

| Flag | Expected | Why |
|---|---|---|
| `nested_iterables` | `true` | Vehicle.owners has `type: "Owner+"` — a data-extension whose quantifier is iterable (`+`) AND whose base type is a non-primitive CDT (`Owner`). This is the exact definition of a nested iterable. |
| `custom_data_types` | `true` | `customDataTypes/Owner/config.json` parses. |
| `array_data_extensions` | `true` | `owners` has quantifier `+` on a data-extension type. |
| `recursive_cdts` | `false` | Owner does not reference itself. |
| `auto_elements` | `false` | No `!` anywhere. |
| `jurisdictional_scopes` | `false` | No `qualification` / `appliesTo` / `exclusive`. |
| `peril_based` | `false` | No `perils/` directory. |
| `multi_product` | `false` | One product subdir (`FleetPlus/`). |
| `coverage_terms` | `false` | No coverage (no `contents` list under Vehicle, no `coverages/` directory). |
| `default_option_prefix` | `false` | Requires `coverage_terms` first. |

All three `true` flags are refusal flags by the whitelist in
`CONFIG_COVERAGE.md` §4 (the one partially-whitelisted flag,
`array_data_extensions`, still triggers a refusal row per SKILL.md
Step 2a because no dedicated scope-walker exists for the flattened
array entries).

## Behaviour proven

1. **CDT expansion is structurally flat.** `extract_paths.py` emits
   the single entry `$vehicle.data.owners` under Vehicle.fields. It
   does NOT emit `$vehicle.data.owners[*].firstName` or any other
   nested path. The `custom_type_ref: Owner` marker is the only
   handle a future CDT-walker has to climb from the reference to the
   CDT's own data map.
2. **Iterables index excludes data-extension arrays.** The registry's
   top-level `iterables:` index carries only Vehicle (from
   `contents: ["Vehicle+"]`). `owners` is iterable in spirit
   (quantifier `+`), but it does NOT appear in `iterables:` — only
   top-level exposures do. This is the canonical proof that Rule 1
   (loop match) would reject `owners` as a loop target.
3. **Refusal rule — per-variable downgrade.** The `owners` loop field
   matches by name + display_name + scope, but the candidate entry's
   `custom_type_ref` + `iterable: true` make the match depend on two
   refusal flags. Per `CONFIG_COVERAGE.md` §4, confidence drops to
   `low` and `next_action` is `needs-skill-update:` (extending the
   bubble-up vocabulary into the variable/loop slot, as the refusal
   rule explicitly authorises — see the "Feature-support refusal
   rule" bullet in SKILL.md Step 2a).
4. **Refusal rule — §7 flag-level rows.** The shape probe emits one
   §7 Unrecognised inputs row per `true` refusal flag, alphabetised
   (`array_data_extensions`, `custom_data_types`, `nested_iterables`).
   Every row's Next-action is exactly
   `needs-skill-update: <flag> is true but SKILL has no rule;
   extend or refuse` — the canonical wording from SKILL.md Step 2a's
   refusal-rule bullet.
5. **Unaffected entries stay `high`.** The `policy_number` variable,
   the `vehicles` loop, and the `vehicles.vin` loop field all
   resolve to `high` because their registry candidates do NOT carry
   a `custom_type_ref` and do NOT depend on a refusal flag. This is
   the canonical regression check that refusal is scoped per-entry,
   not per-run.

## Inputs

- `socotra-config/products/FleetPlus/config.json` — `contents:
  ["Vehicle+"]`, no charges, no policy data fields.
- `socotra-config/exposures/Vehicle/config.json` — 2 data fields
  (`vin: string`, `owners: Owner+`), no contents (no coverages).
- `socotra-config/customDataTypes/Owner/config.json` — `displayName:
  Owner`, 2 scalar data fields (`firstName`, `lastName`).
- `mapping.yaml` — 1 top-level variable (`policy_number`), 1 loop
  (`vehicles`) with 2 fields (`vin`, `owners`).

## Goldens

- `golden/path-registry.yaml` — 19 total addressable paths (8 system
  + 9 account + 0 policy + 2 exposure fields — vin and owners); 1
  iterable (Vehicle); `feature_support.nested_iterables: true`,
  `custom_data_types: true`, `array_data_extensions: true`, every
  other flag `false`.
- `golden/suggested.yaml` — 3 `high` (policy_number, vehicles,
  vehicles.vin), 0 `medium`, 1 `low` (vehicles.owners with
  `needs-skill-update`).
- `golden/review.md` — 1 blocker (`vehicles.owners`), 0 assumptions,
  0 cross-scope warnings, 3 done items, 3 §7 rows (one per true
  refusal flag).
