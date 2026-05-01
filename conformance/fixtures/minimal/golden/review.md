<!-- schema_version: 1.1 -->

# Mapping review — suggested

- Run id: `937750e8-f675-43c8-bc33-4f3aec9450d2`
- Mode: **terse**
- Source mapping: `conformance/fixtures/minimal/mapping.yaml`
- Suggested output: `conformance/fixtures/minimal/actual/suggested.yaml`
- Path registry: `conformance/fixtures/minimal/actual/path-registry.yaml`
- Product: **Mono**
- Generated at: 2026-05-01T14:21:42Z
- Inputs: mapping sha256 `95c459aca67235bf…`, registry sha256 `cc5e1fd9c0437260…`
- Registry lineage: generated `2026-05-01T14:20:42.654406+00:00`, config_dir `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverter1stLeg/conformance/fixtures/minimal/socotra-config`
- Registry config check: **skipped_no_config_dir** (verified=no)
- Schema: 1.1 (mapping 1.0, registry 1.1)

---

## State summary

- `run_id`: `937750e8-f675-43c8-bc33-4f3aec9450d2`
- `registry_config_check`: skipped_no_config_dir

## Summary

| Metric | Count |
|---|---|
| Variables (total) | 3 |
| Loops (total) | 0 |
| high | 2 |
| medium | 0 |
| low | 1 |

### Next-action breakdown

| next-action | Count |
|---|---|
| pick-one | 0 |
| supply-from-plugin | 0 |
| restructure-template | 1 |
| confirm-assumption | 0 |
| delete-from-template | 0 |

### High confidence

| Type | Count |
|---|---|
| Loops | 0 |
| Fields | 2 |

**Field names**

| Name | Velocity Path |
|---|---|
| `$TBD_policy_ref` | `$data.data.policyRef` |
| `$TBD_account_name` | `$data.account.data.name` |

### Low confidence

| Type | Count |
|---|---|
| Loops | 0 |
| Fields | 1 |

**Field names**

| Name | Velocity Path |
|---|---|
| `$TBD_vehicle_vin` | `—` |

---

## Blockers

| Placeholder | Line | next-action |
|---|---|---|
| `$TBD_vehicle_vin` | 12 | restructure-template |

---

## Assumptions to confirm

No assumptions to confirm.

---

## Cross-scope warnings

| Placeholder | Matched path | Requires scope | Fix |
|---|---|---|---|
| `$TBD_vehicle_vin` | `$vehicle.data.vin` | `#foreach ($vehicle in $data.vehicles)` | restructure-template |

---

## Done

<details>
<summary><strong>2</strong> high-confidence mapping(s)</summary>

- `$TBD_policy_ref` → `$data.data.policyRef`
- `$TBD_account_name` → `$data.account.data.name`

</details>

---

## Unrecognised inputs

No unrecognised inputs.

