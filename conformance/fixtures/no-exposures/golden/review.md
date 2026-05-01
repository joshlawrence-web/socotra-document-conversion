<!-- schema_version: 1.1 -->

# Mapping review — no-exposures

- Source mapping: `conformance/fixtures/no-exposures/mapping.yaml`
- Suggested output: `conformance/fixtures/no-exposures/golden/suggested.yaml`
- Path registry: `conformance/fixtures/no-exposures/golden/path-registry.yaml`
- Product: **Mono** (Pure Data Monoline)
- Generated at: 2026-04-22T14:00:00+00:00
- Schema: 1.1 (mapping 1.0, registry 1.1)

---

## Summary

| Metric | Count |
|---|---|
| Variables (total) | 3 |
| Loops (total) | 0 |
| Loop fields (total) | 0 |
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

---

## Blockers

No blockers.

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

- `policy_ref` → `$data.data.policyRef`
- `submitted_at` → `$data.data.submittedAt`
- `account_name` → `$data.account.data.name`

</details>

---

## Unrecognised inputs

No unrecognised inputs.
