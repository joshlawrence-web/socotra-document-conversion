<!-- schema_version: 1.1 -->

# Mapping review — suggested

- Run id: `f1cc7da3-3931-4a0f-a5f1-76604756301f`
- Mode: **terse**
- Source mapping: `conformance/fixtures/itemcare-simple/mapping.yaml`
- Suggested output: `conformance/fixtures/itemcare-simple/actual/suggested.yaml`
- Path registry: `conformance/fixtures/itemcare-simple/actual/path-registry.yaml`
- Product: **SimpleItemCare**
- Generated at: 2026-05-01T14:21:42Z
- Inputs: mapping sha256 `66825ed74bb3c5d3…`, registry sha256 `7b2882f395dd30ec…`
- Registry lineage: generated `2026-05-01T14:20:42.046420+00:00`, config_dir `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverter1stLeg/conformance/fixtures/itemcare-simple/socotra-config`
- Registry config check: **skipped_no_config_dir** (verified=no)
- Schema: 1.1 (mapping 1.0, registry 1.1)

---

## State summary

- `run_id`: `f1cc7da3-3931-4a0f-a5f1-76604756301f`
- `registry_config_check`: skipped_no_config_dir

## Summary

| Metric | Count |
|---|---|
| Variables (total) | 4 |
| Loops (total) | 1 |
| high | 3 |
| medium | 1 |
| low | 1 |

### Next-action breakdown

| next-action | Count |
|---|---|
| pick-one | 0 |
| supply-from-plugin | 0 |
| restructure-template | 1 |
| confirm-assumption | 1 |
| delete-from-template | 0 |

### High confidence

| Type | Count |
|---|---|
| Loops | 1 |
| Fields | 2 |

**Loop names**

| Name | Velocity Path |
|---|---|
| `$TBD_items` | `$data.items` |

**Field names**

| Name | Velocity Path |
|---|---|
| `$TBD_POLICY_NUMBER` | `$data.policyNumber` |
| `$item.TBD_SERIAL_NUMBER` | `$item.data.serialNumber` |

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
| Fields | 1 |

**Field names**

| Name | Velocity Path |
|---|---|
| `$TBD_SCOPE_VIOLATION` | `—` |

---

## Blockers

| Placeholder | Line | next-action |
|---|---|---|
| `$TBD_SCOPE_VIOLATION` | 20 | restructure-template |

---

## Assumptions to confirm

1 assumption(s) to confirm — see .suggested.yaml

---

## Cross-scope warnings

| Placeholder | Matched path | Requires scope | Fix |
|---|---|---|---|
| `$TBD_SCOPE_VIOLATION` | `$item.data.serialNumber` | `#foreach ($item in $data.items)` | restructure-template |

---

## Done

<details>
<summary><strong>3</strong> high-confidence mapping(s)</summary>

- `$TBD_POLICY_NUMBER` → `$data.policyNumber`
- `$item.TBD_SERIAL_NUMBER` → `$item.data.serialNumber`
- `$TBD_items` → `$data.items`

</details>

---

## Unrecognised inputs

No unrecognised inputs.

