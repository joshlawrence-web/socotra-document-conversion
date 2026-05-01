<!-- schema_version: 1.1 -->

# Mapping review — coverage-terms

- Source mapping: `conformance/fixtures/coverage-terms/mapping.yaml`
- Suggested output: `conformance/fixtures/coverage-terms/golden/suggested.yaml`
- Path registry: `conformance/fixtures/coverage-terms/golden/path-registry.yaml`
- Product: **FloodProtection** (Flood Protection)
- Generated at: 2026-04-22T14:00:00+00:00
- Schema: 1.1 (mapping 1.0, registry 1.1)

---

## Summary

| Metric | Count |
|---|---|
| Variables (total) | 1 |
| Loops (total) | 1 |
| Loop fields (total) | 3 |
| high | 4 |
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
one low loop field (`flood_deductible`) carries a
`needs-skill-update:` action surfaced in §7 (the refusal-rule path)
rather than in this variable/loop-head table.

---

## Blockers

1 item must be resolved before Leg 3 can run. Ordered by source line
(template top-to-bottom).

### `dwellings.flood_deductible`  _(line 16)_

- **parent_tag:** `li`
- **nearest_label:** "Flood deductible"
- **loop:** `dwellings`
- **next-action:** `needs-skill-update: coverage_terms / default_option_prefix refusal`
- **suggested resolution:** No registry entry matches
  `flood_deductible` in the Flood coverage. The coverage's
  `config.json` declares a `coverageTerms` entry named `deductible`
  (options `["250", "*500", "1000"]`, with `*500` as the default),
  but the extractor does not read `coverageTerms` at all
  (`extract_paths.py` emits only each coverage's `data` map).
  `feature_support.coverage_terms` is `true` and
  `feature_support.default_option_prefix` is `true` — both refusal
  flags fire. Until the skill gains a term-aware walker (which
  would also emit the `*`-prefixed default option), either supply
  the deductible via a plugin-flattened field (e.g.
  `$data.data.floodDeductible` scoped to the selected term option),
  or wait for a v1.x skill update that extends `extract_paths.py`
  to traverse `coverageTerms`. See §7 for the flag-level rows.

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
<summary><strong>4</strong> high-confidence mappings</summary>

- `policy_number` → `$data.policyNumber`
- `dwellings` → `$data.dwellings`
- `dwellings.address` → `$dwelling.data.address`
- `dwellings.flood_effective_date` → `$dwelling.Flood.data.effectiveDate`

</details>

---

## Unrecognised inputs

These keys were preserved in `coverage-terms.suggested.yaml` but the
suggester did not use them. Extend the skill's recognised-signal
vocabulary (see SKILL.md) or remove the key from Leg 1 before promoting
it to a contract.

| Source | Key | Seen on | Next-action |
|---|---|---|---|
| registry | `feature_support.coverage_terms` | top-level (value: true) | `needs-skill-update: coverage_terms is true but SKILL has no rule; extend or refuse` |
| registry | `feature_support.default_option_prefix` | top-level (value: true) | `needs-skill-update: default_option_prefix is true but SKILL has no rule; extend or refuse` |
