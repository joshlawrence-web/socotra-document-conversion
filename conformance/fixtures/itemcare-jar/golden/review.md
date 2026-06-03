<!-- schema_version: 2.0 -->

# Mapping review — suggested

- Run id: `49b2b991-8986-4a47-9ef7-0d04452fc5cd`
- Mode: **terse**
- Source mapping: `conformance/fixtures/itemcare-jar/mapping.yaml`
- Suggested output: `conformance/fixtures/itemcare-jar/golden/suggested.yaml`
- Path registry: `conformance/fixtures/itemcare-jar/golden/path-registry.yaml`
- Product: **ItemCare**
- Rendering roots: `segment` (primary)
- Generated at: 2026-06-03T09:40:48Z
- Inputs: mapping sha256 `65a0c09c42522d9d…`, registry sha256 `893e6663286078d4…`
- Registry lineage: generated `2026-06-03T09:40:06.316465+00:00`, config_dir `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverter1stLeg/conformance/fixtures/itemcare-jar/socotra-config`
- Registry config check: **skipped_no_config_dir** (verified=no)
- Schema: 2.0 (mapping 1.0, registry 1.1)

> Confidence is graded per **(placeholder × rendering root)**, grounded in the compiled JARs. A field can be `high` on one root and a blocker on another.

---

## Summary (per rendering root)

- Variables: 4  ·  Loops: 1

| Root | Primary | high | medium | low |
|---|---|---|---|---|
| `segment` | yes | 2 | 0 | 3 |

### Next-action breakdown (primary root: `segment`)

| next-action | Count |
|---|---|
| pick-one | 0 |
| supply-from-plugin | 3 |
| restructure-template | 0 |
| confirm-assumption | 0 |
| delete-from-template | 0 |

---

## Blockers (low confidence, per root)

| Placeholder | Line | Root | sdk_status | next-action |
|---|---|---|---|---|
| `$TBD_POLICY_NUMBER` | 11 | `segment` | sibling_only | supply-from-plugin |
| `$TBD_POLICYHOLDER_NAME` | 12 | `segment` | not_found | supply-from-plugin |
| `$TBD_EFFECTIVE_START_DATE` | 13 | `segment` | skipped | supply-from-plugin |

---

## Assumptions to confirm (medium confidence, per root)

No assumptions to confirm.

---

## Cross-scope warnings

No cross-scope warnings.

---

## Done (high confidence, per root)

<details>
<summary><strong>2</strong> high-confidence (placeholder × root) verdict(s)</summary>

- `$TBD_LOCATOR` · `segment` → `$data.locator`
- `$TBD_items` · `segment` → `$data.items`

</details>

---

## Unrecognised inputs

| Source | Key | Seen on | Next-action |
|---|---|---|---|
| registry | `feature_support.nested_iterables` | all variables | needs-skill-update: refusal flag `nested_iterables` is true; affected entries may need manual handling |
| registry | `feature_support.array_data_extensions`` | all variables | needs-skill-update: partial-support flag `array_data_extensions` is true; verify coverage |

