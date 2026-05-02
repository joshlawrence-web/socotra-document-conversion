<!-- leg3_schema_version: 1.0 -->

# Leg 3 Substitution Report — Policy-summary

| | |
|---|---|
| **Status** | PARTIAL — 10 of 14 resolved, 4 need attention |
| **Source template** | `Policy-summary.vm` |
| **Mapping used** | `Policy-summary.suggested.yaml` |
| **Output template** | `Policy-summary.final.vm` |
| **Mode** | standard |
| **Generated** | 2026-05-02T12:03:06Z |

---

## Resolved (10)

These tokens have been substituted in the output template.

| Type | Placeholder | Label | Velocity Path | Confidence |
|---|---|---|---|---|
| variable | `$TBD_contractId` | Contract Reference | `$data.data.contractId` | high |
| variable | `$TBD_policyNumber` | Policy Number | `$data.policyNumber` | high |
| variable | `$TBD_productName` | Product | `$data.productName` | high |
| variable | `$TBD_policyStartTime` | Policy Start | `$data.policyStartTime` | high |
| variable | `$TBD_policyEndTime` | Policy End | `$data.policyEndTime` | high |
| variable | `$TBD_channelCode` | Channel | `$data.data.channelCode` | high |
| variable | `$TBD_paymentMethodCode` | Payment Method | `$data.data.paymentMethodCode` | high |
| variable | `$TBD_coolingOffPeriod` | Cooling-Off Period | `$data.data.coolingOffPeriod` | high |
| variable | `$TBD_accountEmail` | Email | `$data.account.data.email` | high |
| loop | `$TBD_items` | — | `$data.items` | high |

---

## Unresolved (4)

These tokens remain as `$TBD_*` in the output template.
For each one: find the correct Velocity path, update `Policy-summary.suggested.yaml`,
then re-run Leg 3.

### `$TBD_accountName`

| | |
|---|---|
| **Label** | "Name" |
| **Source line** | 20 |
| **Type** | variable |
| **Action needed** | `supply-from-plugin` |
| **Leg 2 note** | no registry match for accountName |

> This path does not exist in the registry. A plugin (DocumentDataSnapshotPlugin or equivalent) must supply it as a scalar — e.g. `$data.data.myField`. Add the field in your Socotra config, regenerate the registry, re-run Leg 2, then re-run Leg 3.

```yaml
# In Policy-summary.suggested.yaml — fill in data_source, then re-run Leg 3
- name: accountName
  placeholder: $TBD_accountName
  data_source: ""   # <-- replace with the correct Velocity path
```

### `$TBD_totalPremium`

| | |
|---|---|
| **Label** | "Premium" |
| **Source line** | 24 |
| **Type** | variable |
| **Action needed** | `restructure-template` |
| **Leg 2 note** | registry candidate `$item.Accessories.data.premium` requires scope `#foreach ($item in $data.items)` but no loop signal in Leg 1 output |

> A registry path exists but this variable needs to be inside a `#foreach` block. Add the foreach wrapper in the source HTML, re-run Leg 1, then Leg 2, then Leg 3.

```yaml
# In Policy-summary.suggested.yaml — fill in data_source, then re-run Leg 3
- name: totalPremium
  placeholder: $TBD_totalPremium
  data_source: ""   # <-- replace with the correct Velocity path
```

### `$TBD_totalTax`

| | |
|---|---|
| **Label** | "Tax" |
| **Source line** | 25 |
| **Type** | variable |
| **Action needed** | `supply-from-plugin` |
| **Leg 2 note** | no registry match for totalTax |

> This path does not exist in the registry. A plugin (DocumentDataSnapshotPlugin or equivalent) must supply it as a scalar — e.g. `$data.data.myField`. Add the field in your Socotra config, regenerate the registry, re-run Leg 2, then re-run Leg 3.

```yaml
# In Policy-summary.suggested.yaml — fill in data_source, then re-run Leg 3
- name: totalTax
  placeholder: $TBD_totalTax
  data_source: ""   # <-- replace with the correct Velocity path
```

### `$TBD_coverExclusions`

| | |
|---|---|
| **Label** | "Cover Exclusions" |
| **Source line** | 56 |
| **Type** | loop |
| **Action needed** | `supply-from-plugin` |
| **Leg 2 note** | loop `coverExclusions` has no matching iterable in registry |

> This path does not exist in the registry. A plugin (DocumentDataSnapshotPlugin or equivalent) must supply it as a scalar — e.g. `$data.data.myField`. Add the field in your Socotra config, regenerate the registry, re-run Leg 2, then re-run Leg 3.

```yaml
# In Policy-summary.suggested.yaml — fill in data_source, then re-run Leg 3
- name: coverExclusions
  placeholder: $TBD_coverExclusions
  data_source: ""   # <-- replace with the correct Velocity path
```

---

## Next steps

1. Fill in `data_source` for each **Unresolved** token in `Policy-summary.suggested.yaml`
2. Re-run Leg 3:
   ```
   RUN_PIPELINE leg3 suggested=samples/output/Policy-summary/Policy-summary.suggested.yaml
   ```
3. If the path doesn't exist in the registry yet:
   - Add the field to your Socotra config
   - Regenerate the registry: `python3 .cursor/skills/mapping-suggester/scripts/extract_paths.py`
   - Re-run Leg 2 to update the suggested mapping
   - Then re-run Leg 3

