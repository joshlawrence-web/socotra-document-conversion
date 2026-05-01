<!-- schema_version: 1.1 -->

# Mapping review — Simple-form

- Run id: `788839ff-e8f4-4a7a-ae87-2a1b387a14f7`
- Mode: **terse**
- Source mapping: `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverter1stLeg/samples/output/Simple-form/Simple-form.mapping.yaml`
- Suggested output: `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverter1stLeg/samples/output/Simple-form/Simple-form.suggested.yaml`
- Path registry: `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverter1stLeg/registry/path-registry.yaml`
- Product: **ItemCare**
- Generated at: 2026-05-01T16:22:27Z
- Inputs: mapping sha256 `48e75da72e432228…`, registry sha256 `c4f3dbf3f05e8e8b…`
- Registry lineage: generated `2026-04-26T09:00:01.657127+00:00`, config_dir `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverter1stLeg/socotra-config`
- Registry config check: **skipped_no_config_dir** (verified=no)
- Schema: 1.1 (mapping 1.0, registry 1.1)

---

## State summary

- `run_id`: `788839ff-e8f4-4a7a-ae87-2a1b387a14f7`
- `registry_config_check`: skipped_no_config_dir

## Summary

| Metric | Count |
|---|---|
| Variables (total) | 4 |
| Loops (total) | 0 |
| high | 1 |
| medium | 1 |
| low | 2 |

### Next-action breakdown

| next-action | Count |
|---|---|
| pick-one | 0 |
| supply-from-plugin | 2 |
| restructure-template | 0 |
| confirm-assumption | 1 |
| delete-from-template | 0 |

### High confidence

| Type | Count |
|---|---|
| Loops | 0 |
| Fields | 1 |

**Field names**

| Name | Velocity Path |
|---|---|
| `$TBD_POLICY_NUMBER` | `$data.policyNumber` |

### Medium confidence

| Type | Count |
|---|---|
| Loops | 0 |
| Fields | 1 |

**Field names**

| Name | Velocity Path |
|---|---|
| `$TBD_POLICYHOLDER_NAME` | `$data.account.data.name` |

### Low confidence

| Type | Count |
|---|---|
| Loops | 0 |
| Fields | 2 |

**Field names**

| Name | Velocity Path |
|---|---|
| `$TBD_INSURANCE_PRODUCT` | `—` |
| `$TBD_EFFECTIVE_START_DATE` | `—` |

---

## Blockers

| Placeholder | Line | next-action |
|---|---|---|
| `$TBD_INSURANCE_PRODUCT` | 10 | supply-from-plugin |
| `$TBD_EFFECTIVE_START_DATE` | 13 | supply-from-plugin |

---

## Assumptions to confirm

1 assumption(s) to confirm — see .suggested.yaml

---

## Cross-scope warnings

No cross-scope warnings.

---

## Done

<details>
<summary><strong>1</strong> high-confidence mapping(s)</summary>

- `$TBD_POLICY_NUMBER` → `$data.policyNumber`

</details>

---

## Unrecognised inputs

| Source | Key | Seen on | Next-action |
|---|---|---|---|
| registry | `feature_support.nested_iterables` | all variables | needs-skill-update: refusal flag `nested_iterables` is true; affected entries may need manual handling |
| registry | `feature_support.array_data_extensions` | all variables | needs-skill-update: partial-support flag `array_data_extensions` is true; verify coverage |

