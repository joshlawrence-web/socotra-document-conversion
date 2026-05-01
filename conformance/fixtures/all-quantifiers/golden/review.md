<!-- schema_version: 1.1 -->

# Mapping review — suggested

- Run id: `156f26ad-d0ad-41a4-9af1-f7f5e2e66a72`
- Mode: **terse**
- Source mapping: `conformance/fixtures/all-quantifiers/mapping.yaml`
- Suggested output: `conformance/fixtures/all-quantifiers/actual/suggested.yaml`
- Path registry: `conformance/fixtures/all-quantifiers/actual/path-registry.yaml`
- Product: **Multi**
- Generated at: 2026-05-01T14:21:42Z
- Inputs: mapping sha256 `0d99e946554631e3…`, registry sha256 `bbb5fc1e8dab8129…`
- Registry lineage: generated `2026-05-01T14:20:40.965803+00:00`, config_dir `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverter1stLeg/conformance/fixtures/all-quantifiers/socotra-config`
- Registry config check: **skipped_no_config_dir** (verified=no)
- Schema: 1.1 (mapping 1.0, registry 1.1)

---

## State summary

- `run_id`: `156f26ad-d0ad-41a4-9af1-f7f5e2e66a72`
- `registry_config_check`: skipped_no_config_dir

## Summary

| Metric | Count |
|---|---|
| Variables (total) | 2 |
| Loops (total) | 2 |
| high | 4 |
| medium | 0 |
| low | 0 |

### Next-action breakdown

| next-action | Count |
|---|---|
| pick-one | 0 |
| supply-from-plugin | 0 |
| restructure-template | 0 |
| confirm-assumption | 0 |
| delete-from-template | 0 |

### High confidence

| Type | Count |
|---|---|
| Loops | 2 |
| Fields | 2 |

**Loop names**

| Name | Velocity Path |
|---|---|
| `$TBD_vehicles` | `$data.vehicles` |
| `$TBD_drivers` | `$data.drivers` |

**Field names**

| Name | Velocity Path |
|---|---|
| `$TBD_policy_ref` | `$data.data.policyRef` |
| `$TBD_ref_number` | `$data.data.refNumber` |

---

## Blockers

No blockers.

---

## Assumptions to confirm

No assumptions to confirm.

---

## Cross-scope warnings

No cross-scope warnings.

---

## Done

<details>
<summary><strong>4</strong> high-confidence mapping(s)</summary>

- `$TBD_policy_ref` → `$data.data.policyRef`
- `$TBD_ref_number` → `$data.data.refNumber`
- `$TBD_vehicles` → `$data.vehicles`
- `$TBD_drivers` → `$data.drivers`

</details>

---

## Unrecognised inputs

No unrecognised inputs.

