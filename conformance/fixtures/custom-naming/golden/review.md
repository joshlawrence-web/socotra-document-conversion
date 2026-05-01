<!-- schema_version: 1.1 -->

# Mapping review — suggested

- Run id: `87491548-dd5c-4d59-9735-2ec1e40320a9`
- Mode: **terse**
- Source mapping: `conformance/fixtures/custom-naming/mapping.yaml`
- Suggested output: `conformance/fixtures/custom-naming/actual/suggested.yaml`
- Path registry: `conformance/fixtures/custom-naming/actual/path-registry.yaml`
- Product: **DeepSeaFleet**
- Generated at: 2026-05-01T14:21:43Z
- Inputs: mapping sha256 `5bc5e0b7fa7f7d8e…`, registry sha256 `9cdb3ca67ab4a7c1…`
- Registry lineage: generated `2026-05-01T14:20:41.827383+00:00`, config_dir `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverter1stLeg/conformance/fixtures/custom-naming/socotra-config`
- Registry config check: **skipped_no_config_dir** (verified=no)
- Schema: 1.1 (mapping 1.0, registry 1.1)

---

## State summary

- `run_id`: `87491548-dd5c-4d59-9735-2ec1e40320a9`
- `registry_config_check`: skipped_no_config_dir

## Summary

| Metric | Count |
|---|---|
| Variables (total) | 1 |
| Loops (total) | 1 |
| high | 2 |
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
| Loops | 1 |
| Fields | 1 |

**Loop names**

| Name | Velocity Path |
|---|---|
| `$TBD_octopuses` | `$data.octopus` |

**Field names**

| Name | Velocity Path |
|---|---|
| `$TBD_policy_number` | `$data.policyNumber` |

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
<summary><strong>2</strong> high-confidence mapping(s)</summary>

- `$TBD_policy_number` → `$data.policyNumber`
- `$TBD_octopuses` → `$data.octopus`

</details>

---

## Unrecognised inputs

No unrecognised inputs.

