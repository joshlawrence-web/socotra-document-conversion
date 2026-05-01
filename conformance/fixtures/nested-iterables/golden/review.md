<!-- schema_version: 1.1 -->

# Mapping review — nested-iterables

- Source mapping: `conformance/fixtures/nested-iterables/mapping.yaml`
- Suggested output: `conformance/fixtures/nested-iterables/golden/suggested.yaml`
- Path registry: `conformance/fixtures/nested-iterables/golden/path-registry.yaml`
- Product: **FleetPlus** (Fleet Plus)
- Generated at: 2026-04-22T14:00:00+00:00
- Schema: 1.1 (mapping 1.0, registry 1.1)

---

## Summary

| Metric | Count |
|---|---|
| Variables (total) | 1 |
| Loops (total) | 1 |
| Loop fields (total) | 2 |
| high | 3 |
| medium | 0 |
| low (variables + loops) | 0 |

### Next-action breakdown (variables + loop heads)

| next-action | Count |
|---|---|
| `pick-one` | 0 |
| `supply-from-plugin` | 0 |
| `restructure-template` | 0 |
| `confirm-assumption` | 0 |
| `delete-from-template` | 0 |

Loop fields inherit their parent loop's next-action (when any); the
one low loop field (`owners`) carries a `needs-skill-update:` action
surfaced in §7 (the refusal-rule path) rather than in this
variable/loop-head table.

---

## Blockers

1 item must be resolved before Leg 3 can run. Ordered by source line
(template top-to-bottom).

### `vehicles.owners`  _(line 14)_

- **parent_tag:** `li`
- **nearest_label:** "Owners"
- **loop:** `vehicles`
- **next-action:** `needs-skill-update: nested_iterables / custom_data_types / array_data_extensions refusal`
- **suggested resolution:** Registry candidate
  `$vehicle.data.owners` exists with `custom_type_ref: Owner`,
  `iterable: true`, `quantifier: '+'`, but the match depends on three
  refusal flags (`nested_iterables`, `custom_data_types`,
  `array_data_extensions`) that are all `true` in this fixture's
  registry. The suggester has no CDT-aware scope-walker today — the
  path is listed but cannot be emitted as a `high` match until the
  SKILL gains rules for walking Owner's own data map and for pushing
  a second `#foreach` onto `requires_scope`. Until then, treat as a
  blocker; see §7 for the three flag-level rows.

---

## Assumptions to confirm

No assumptions to confirm.

---

## Cross-scope warnings

| Placeholder | Matched path | Requires scope | Fix |
|---|---|---|---|

No cross-scope warnings.

---

## Done

<details>
<summary><strong>3</strong> high-confidence mappings</summary>

- `policy_number` → `$data.policyNumber`
- `vehicles` → `$data.vehicles`
- `vehicles.vin` → `$vehicle.data.vin`

</details>

---

## Unrecognised inputs

These keys were preserved in `nested-iterables.suggested.yaml` but the
suggester did not use them. Extend the skill's recognised-signal
vocabulary (see SKILL.md) or remove the key from Leg 1 before promoting
it to a contract.

| Source | Key | Seen on | Next-action |
|---|---|---|---|
| registry | `feature_support.array_data_extensions` | top-level (value: true) | `needs-skill-update: array_data_extensions is true but SKILL has no rule; extend or refuse` |
| registry | `feature_support.custom_data_types` | top-level (value: true) | `needs-skill-update: custom_data_types is true but SKILL has no rule; extend or refuse` |
| registry | `feature_support.nested_iterables` | top-level (value: true) | `needs-skill-update: nested_iterables is true but SKILL has no rule; extend or refuse` |
