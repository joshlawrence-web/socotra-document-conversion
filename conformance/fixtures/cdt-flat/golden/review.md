<!-- schema_version: 1.1 -->

# Mapping review — cdt-flat

- Source mapping: `conformance/fixtures/cdt-flat/mapping.yaml`
- Suggested output: `conformance/fixtures/cdt-flat/golden/suggested.yaml`
- Path registry: `conformance/fixtures/cdt-flat/golden/path-registry.yaml`
- Product: **Homeowner** (Homeowner)
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
one low loop field (`dwelling_address`) carries a `needs-skill-update:`
action surfaced in §7 (the refusal-rule path) rather than in this
variable/loop-head table.

---

## Blockers

1 item must be resolved before Leg 3 can run. Ordered by source line
(template top-to-bottom).

### `policyholders.dwelling_address`  _(line 14)_

- **parent_tag:** `li`
- **nearest_label:** "Dwelling address"
- **loop:** `policyholders`
- **next-action:** `needs-skill-update: custom_data_types refusal`
- **suggested resolution:** Registry candidate
  `$policyholder.data.dwellingAddress` exists with `custom_type_ref:
  Address`, but the suggester has no rule for walking CDT
  sub-fields. The path references a complex object; templates
  typically want scalar renderings
  (`$policyholder.data.dwellingAddress.street`,
  `$policyholder.data.dwellingAddress.city`, …). Until the skill
  gains CDT-awareness, either supply a plugin that flattens the
  address into scalars (e.g. `$data.data.dwellingAddressLine1`) or
  wait for a v1.x skill update. See §7 for the flag-level row.

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
- `policyholders` → `$data.policyholders`
- `policyholders.full_name` → `$policyholder.data.fullName`

</details>

---

## Unrecognised inputs

These keys were preserved in `cdt-flat.suggested.yaml` but the
suggester did not use them. Extend the skill's recognised-signal
vocabulary (see SKILL.md) or remove the key from Leg 1 before promoting
it to a contract.

| Source | Key | Seen on | Next-action |
|---|---|---|---|
| registry | `feature_support.custom_data_types` | top-level (value: true) | `needs-skill-update: custom_data_types is true but SKILL has no rule; extend or refuse` |
