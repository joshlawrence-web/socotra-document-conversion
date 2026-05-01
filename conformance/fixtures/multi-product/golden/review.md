<!-- schema_version: 1.1 -->

# Mapping review — multi-product

- Source mapping: `conformance/fixtures/multi-product/mapping.yaml`
- Suggested output: `conformance/fixtures/multi-product/golden/suggested.yaml`
- Path registry: `conformance/fixtures/multi-product/golden/path-registry.yaml`
- Product: **AutoLine** (Auto Line)
- Generated at: 2026-04-22T14:00:00+00:00
- Schema: 1.1 (mapping 1.0, registry 1.1)

---

## Summary

| Metric | Count |
|---|---|
| Variables (total) | 2 |
| Loops (total) | 1 |
| Loop fields (total) | 1 |
| high | 3 |
| medium | 0 |
| low (variables + loops) | 1 |

### Next-action breakdown (variables + loop heads)

| next-action | Count |
|---|---|
| `pick-one` | 0 |
| `supply-from-plugin` | 0 |
| `restructure-template` | 0 |
| `confirm-assumption` | 0 |
| `delete-from-template` | 0 |

The one low variable (`roof_material`) carries a `needs-skill-update:`
action surfaced in §7 (the refusal-rule path) rather than in this
variable/loop-head table.

---

## Blockers

1 item must be resolved before Leg 3 can run. Ordered by source line
(template top-to-bottom).

### `roof_material`  _(line 8)_

- **parent_tag:** `p`
- **nearest_label:** "Roof material"
- **loop:** —
- **next-action:** `needs-skill-update: multi_product refusal`
- **suggested resolution:** No registry entry matches
  `roof_material` in AutoLine's registry. `feature_support.multi_product`
  is `true` (the config tree has two product subdirectories —
  `AutoLine/` and `HomeLine/` — and `extract_paths.py` picked the
  alphabetically-first one, silently dropping the rest). Until the
  suggester gains multi-product awareness (e.g. a `--product
  <name>` argument, or a merged-registry mode), cross-product
  placeholders cannot be resolved. Either wait for a v1.x skill
  update, or rerun Leg 1 + Leg 2 against the HomeLine-only config
  subtree (if `roof_material` is in fact a HomeLine field). See §7
  for the flag-level row.

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

These keys were preserved in `multi-product.suggested.yaml` but the
suggester did not use them. Extend the skill's recognised-signal
vocabulary (see SKILL.md) or remove the key from Leg 1 before promoting
it to a contract.

| Source | Key | Seen on | Next-action |
|---|---|---|---|
| registry | `feature_support.multi_product` | top-level (value: true) | `needs-skill-update: multi_product is true but SKILL has no rule; extend or refuse` |
