<!-- leg3_schema_version: 1.0 -->

# Leg 3 Substitution Report — Additional-form

| | |
|---|---|
| **Status** | PARTIAL — 2 of 4 resolved, 2 need attention |
| **Source template** | `Additional-form.vm` |
| **Mapping used** | `Additional-form.suggested.yaml` |
| **Output template** | `Additional-form.final.vm` |
| **Generated** | 2026-05-01T15:27:47Z |

---

## Resolved (2)

These tokens have been substituted in the output template.

| Type | Placeholder | Label | Velocity Path | Confidence |
|---|---|---|---|---|
| variable | `$TBD_POLICY_NUMBER` | Policy Number | `$data.policyNumber` | high |
| variable | `$TBD_POLICYHOLDER_NAME` | Policyholder | `$data.account.data.name` | medium |

---

## Unresolved (2)

These tokens remain as `$TBD_*` in the output template.
For each one: find the correct Velocity path, update `Additional-form.suggested.yaml`,
then re-run Leg 3.

### `$TBD_INSURANCE_PRODUCT`

| | |
|---|---|
| **Label** | "Insurance Product" |
| **Source line** | 10 |
| **Type** | variable |
| **Action needed** | `supply-from-plugin` |
| **Leg 2 note** | no registry match for insuranceProduct |

> This path does not exist in the registry. A plugin (DocumentDataSnapshotPlugin or equivalent) must supply it as a scalar — e.g. `$data.data.myField`. Add the field in your Socotra config, regenerate the registry, re-run Leg 2, then re-run Leg 3.

```yaml
# In Additional-form.suggested.yaml — fill in data_source, then re-run Leg 3
- name: INSURANCE_PRODUCT
  placeholder: $TBD_INSURANCE_PRODUCT
  data_source: ""   # <-- replace with the correct Velocity path
```

### `$TBD_EFFECTIVE_START_DATE`

| | |
|---|---|
| **Label** | "Effective Start Date" |
| **Source line** | 13 |
| **Type** | variable |
| **Action needed** | `supply-from-plugin` |
| **Leg 2 note** | no registry match for effectiveStartDate |

> This path does not exist in the registry. A plugin (DocumentDataSnapshotPlugin or equivalent) must supply it as a scalar — e.g. `$data.data.myField`. Add the field in your Socotra config, regenerate the registry, re-run Leg 2, then re-run Leg 3.

```yaml
# In Additional-form.suggested.yaml — fill in data_source, then re-run Leg 3
- name: EFFECTIVE_START_DATE
  placeholder: $TBD_EFFECTIVE_START_DATE
  data_source: ""   # <-- replace with the correct Velocity path
```

---

## Next steps

1. Fill in `data_source` for each **Unresolved** token in `Additional-form.suggested.yaml`
2. Re-run Leg 3:
   ```
   RUN_PIPELINE leg3 suggested=samples/output/Additional-form/Additional-form.suggested.yaml
   ```
3. If the path doesn't exist in the registry yet:
   - Add the field to your Socotra config
   - Regenerate the registry: `python3 .cursor/skills/mapping-suggester/scripts/extract_paths.py`
   - Re-run Leg 2 to update the suggested mapping
   - Then re-run Leg 3

