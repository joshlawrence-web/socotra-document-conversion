<!-- schema_version: 1.1 -->

# Mapping review — jurisdictional

- Source mapping: `conformance/fixtures/jurisdictional/mapping.yaml`
- Suggested output: `conformance/fixtures/jurisdictional/golden/suggested.yaml`
- Path registry: `conformance/fixtures/jurisdictional/golden/path-registry.yaml`
- Product: **SingleState** (Single State Auto)
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
one low loop field (`collision_deductible`) carries a
`needs-skill-update:` action surfaced in §7 (the refusal-rule path)
rather than in this variable/loop-head table.

---

## Blockers

1 item must be resolved before Leg 3 can run. Ordered by source line
(template top-to-bottom).

### `vehicles.collision_deductible`  _(line 14)_

- **parent_tag:** `li`
- **nearest_label:** "Collision deductible"
- **loop:** `vehicles`
- **next-action:** `needs-skill-update: jurisdictional_scopes refusal`
- **suggested resolution:** Registry candidate
  `$vehicle.Collision.data.deductible` exists, but the Collision
  coverage carries a `qualification` key
  (`feature_support.jurisdictional_scopes: true`). The extractor
  does not translate `qualification` / `appliesTo` / `exclusive`
  into a `requires_scope` guard, and the suggester has no Rule 7
  yet for jurisdiction-conditioned paths — a `#if($vehicle.Collision)`
  guard alone is insufficient because the coverage's applicability
  depends on the policy's jurisdiction, not just the exposure's
  selection. Until the skill gains a qualification-aware walker,
  either supply the deductible via a plugin-flattened field
  (`$data.data.collisionDeductible` scoped to the jurisdiction the
  template is for), or wait for a v1.x skill update. See §7 for
  the flag-level row.

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

These keys were preserved in `jurisdictional.suggested.yaml` but the
suggester did not use them. Extend the skill's recognised-signal
vocabulary (see SKILL.md) or remove the key from Leg 1 before promoting
it to a contract.

| Source | Key | Seen on | Next-action |
|---|---|---|---|
| registry | `feature_support.jurisdictional_scopes` | top-level (value: true) | `needs-skill-update: jurisdictional_scopes is true but SKILL has no rule; extend or refuse` |
