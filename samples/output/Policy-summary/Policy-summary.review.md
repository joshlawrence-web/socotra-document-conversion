<!-- schema_version: 1.1 -->

# Mapping review — Policy-summary

- Run id: `d6470e71-9293-414b-a41f-697347b4b448`
- Mode: **terse**
- Source mapping: `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverter1stLeg/samples/output/Policy-summary/Policy-summary.mapping.yaml`
- Suggested output: `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverter1stLeg/samples/output/Policy-summary/Policy-summary.suggested.yaml`
- Path registry: `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverter1stLeg/registry/path-registry.yaml`
- Product: **ItemCare**
- Generated at: 2026-05-02T12:03:06Z
- Inputs: mapping sha256 `441c182286c5cad5…`, registry sha256 `c4f3dbf3f05e8e8b…`
- Registry lineage: generated `2026-04-26T09:00:01.657127+00:00`, config_dir `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverter1stLeg/socotra-config`
- Registry config check: **skipped_no_config_dir** (verified=no)
- Schema: 1.1 (mapping 1.0, registry 1.1)

---

## State summary

- `run_id`: `d6470e71-9293-414b-a41f-697347b4b448`
- `registry_config_check`: skipped_no_config_dir

## Summary

| Metric | Count |
|---|---|
| Variables (total) | 12 |
| Loops (total) | 2 |
| high | 10 |
| medium | 0 |
| low | 4 |

### Next-action breakdown

| next-action | Count |
|---|---|
| pick-one | 0 |
| supply-from-plugin | 3 |
| restructure-template | 1 |
| confirm-assumption | 0 |
| delete-from-template | 0 |

### High confidence

| Type | Count |
|---|---|
| Loops | 1 |
| Fields | 9 |

**Loop names**

| Name | Velocity Path |
|---|---|
| `$TBD_items` | `$data.items` |

**Field names**

| Name | Velocity Path |
|---|---|
| `$TBD_contractId` | `$data.data.contractId` |
| `$TBD_policyNumber` | `$data.policyNumber` |
| `$TBD_productName` | `$data.productName` |
| `$TBD_policyStartTime` | `$data.policyStartTime` |
| `$TBD_policyEndTime` | `$data.policyEndTime` |
| `$TBD_channelCode` | `$data.data.channelCode` |
| `$TBD_paymentMethodCode` | `$data.data.paymentMethodCode` |
| `$TBD_coolingOffPeriod` | `$data.data.coolingOffPeriod` |
| `$TBD_accountEmail` | `$data.account.data.email` |

### Low confidence

| Type | Count |
|---|---|
| Loops | 1 |
| Fields | 3 |

**Loop names**

| Name | Velocity Path |
|---|---|
| `$TBD_coverExclusions` | `—` |

**Field names**

| Name | Velocity Path |
|---|---|
| `$TBD_accountName` | `—` |
| `$TBD_totalPremium` | `—` |
| `$TBD_totalTax` | `—` |

---

## Blockers

| Placeholder | Line | next-action |
|---|---|---|
| `$TBD_accountName` | 20 | supply-from-plugin |
| `$TBD_totalPremium` | 24 | restructure-template |
| `$TBD_totalTax` | 25 | supply-from-plugin |
| `$TBD_coverExclusions` | 56 | supply-from-plugin |

---

## Assumptions to confirm

No assumptions to confirm.

---

## Cross-scope warnings

| Placeholder | Matched path | Requires scope | Fix |
|---|---|---|---|
| `$TBD_totalPremium` | `$item.Accessories.data.premium` | `#foreach ($item in $data.items)` | restructure-template |

---

## Done

<details>
<summary><strong>10</strong> high-confidence mapping(s)</summary>

- `$TBD_contractId` → `$data.data.contractId`
- `$TBD_policyNumber` → `$data.policyNumber`
- `$TBD_productName` → `$data.productName`
- `$TBD_policyStartTime` → `$data.policyStartTime`
- `$TBD_policyEndTime` → `$data.policyEndTime`
- `$TBD_channelCode` → `$data.data.channelCode`
- `$TBD_paymentMethodCode` → `$data.data.paymentMethodCode`
- `$TBD_coolingOffPeriod` → `$data.data.coolingOffPeriod`
- `$TBD_accountEmail` → `$data.account.data.email`
- `$TBD_items` → `$data.items`

</details>

---

## Unrecognised inputs

| Source | Key | Seen on | Next-action |
|---|---|---|---|
| registry | `feature_support.nested_iterables` | all variables | needs-skill-update: refusal flag `nested_iterables` is true; affected entries may need manual handling |
| registry | `feature_support.array_data_extensions` | all variables | needs-skill-update: partial-support flag `array_data_extensions` is true; verify coverage |

