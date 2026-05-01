<!-- schema_version: 1.1 -->

# Mapping review — jurisdictional-exclusive

- Source mapping: `conformance/fixtures/jurisdictional-exclusive/mapping.yaml`
- Suggested output: `conformance/fixtures/jurisdictional-exclusive/golden/suggested.yaml`
- Path registry: `conformance/fixtures/jurisdictional-exclusive/golden/path-registry.yaml`
- Product: **SpecialAuto** (Special Auto)
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
one low loop field (`umbrella_limit`) carries a
`needs-skill-update:` action surfaced in §7 (the refusal-rule path)
rather than in this variable/loop-head table.

---

## Blockers

1 item must be resolved before Leg 3 can run. Ordered by source line
(template top-to-bottom).

### `vehicles.umbrella_limit`  _(line 14)_

- **parent_tag:** `li`
- **nearest_label:** "Umbrella limit"
- **loop:** `vehicles`
- **next-action:** `needs-skill-update: jurisdictional_scopes refusal`
- **suggested resolution:** Registry candidate
  `$vehicle.Umbrella.data.limit` exists, but the Umbrella coverage
  carries `exclusive: true` AND `appliesTo: ["claim"]`
  (`feature_support.jurisdictional_scopes: true`). The extractor
  does not translate `qualification` / `appliesTo` / `exclusive`
  into a `requires_scope` guard, and the suggester has no Rule 7
  yet for jurisdiction-conditioned or document-type-conditioned
  paths — a `#if($vehicle.Umbrella)` guard tests for attachment,
  not for the exclusive or appliesTo predicates. Until the skill
  gains a qualification-aware walker, either supply the umbrella
  limit via a plugin-flattened field scoped to the correct
  jurisdiction + document type, or wait for a v1.x skill update.
  See §7 for the flag-level row.

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

These keys were preserved in `jurisdictional-exclusive.suggested.yaml`
but the suggester did not use them. Extend the skill's
recognised-signal vocabulary (see SKILL.md) or remove the key from
Leg 1 before promoting it to a contract.

| Source | Key | Seen on | Next-action |
|---|---|---|---|
| registry | `feature_support.jurisdictional_scopes` | top-level (value: true) | `needs-skill-update: jurisdictional_scopes is true but SKILL has no rule; extend or refuse` |
