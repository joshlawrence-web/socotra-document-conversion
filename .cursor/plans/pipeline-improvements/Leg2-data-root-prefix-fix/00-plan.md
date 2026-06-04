# Leg 2 — Fix `$data.<root>` Path Prefix for Rendering Roots

**Status:** Ready  
**Created:** 2026-06-03  
**Predecessor:** [Leg4-renderingData-alignment](../Leg4-renderingData-alignment/00-plan.md) — introduced the wrong assumption  

---

## Problem

`leg2_fill_mapping.py` generates `$quote.productName` but Socotra's Velocity renderer
exposes **all** `renderingData` keys under `$data`. The correct path is `$data.quote.productName`.

**Confirmed by live renderer error:**
```
Variable $quote has not been set
```

**Confirmed by live renderingData payload:**
```json
{
  "renderingData": {
    "quote": { "productName": "ZenCover", "quoteNumber": "DG-00000082", ... },
    "productType": "ZenCover",
    "pricing": { ... }
  }
}
```
→ `$data.quote.productName`, `$data.productType`, `$data.pricing.totalBillable`

**Root cause — `leg2_fill_mapping.py:47–50`:**
```python
_ROOT_VEL_PREFIX: dict[str, str] = {
    "quote": "$quote",      # WRONG — should be "$data.quote"
    "segment": "$segment",  # WRONG — should be "$data.segment"
}
```
The previous Leg4-renderingData-alignment plan assumed templates use `$quote.*` as
bare roots (matching the internal CommercialAuto demo plugin). The actual renderer
wraps everything under `$data`, regardless of plugin shape. That plan's assumption was wrong.

---

## What does NOT need to change

- `_reprefix(path, new_prefix)` — already works correctly. With `new_prefix="$data.quote"` and
  `path="$data.productName"` it returns `"$data.quote.productName"`. ✓
- `classify_path(... root_prefix=rp)` — strips `root_prefix` from the front; works fine with
  `"$data.quote"` as prefix. ✓
- `jar_candidate(... root_prefix=rp)` — builds path as `f"{root_prefix}.{method_name}"`; correct
  with `"$data.quote"`. ✓
- `registry/path-registry.yaml` — already uses `$data.*` throughout; note already says root is `$data`. ✓
- Leg 4 (`leg4_generate_plugin.py`) — reads `data_source` verbatim from the suggested YAML;
  once Leg 2 is fixed and YAML regenerated, Leg 4 output is automatically correct. ✓

---

## Task list

### T1 — Fix `_ROOT_VEL_PREFIX` in `leg2_fill_mapping.py`

**File:** `scripts/leg2_fill_mapping.py:47–50`

```python
# Before
_ROOT_VEL_PREFIX: dict[str, str] = {
    "quote": "$quote",
    "segment": "$segment",
}

# After
_ROOT_VEL_PREFIX: dict[str, str] = {
    "quote": "$data.quote",
    "segment": "$data.segment",
}
```

### T2 — Fix `_SIBLING_ROOT` in `leg2_fill_mapping.py`

**File:** `scripts/leg2_fill_mapping.py:52–56`

Sibling roots are accessed the same way — they live in `renderingData` under a named key,
so the template accesses them via `$data.<key>.*`.

```python
# Before
_SIBLING_ROOT: dict[str, str] = {
    "policy": "$policy",
    "transaction": "$transaction",
    "account": "$account",
}

# After
_SIBLING_ROOT: dict[str, str] = {
    "policy": "$data.policy",
    "transaction": "$data.transaction",
    "account": "$data.account",
}
```

Also update the docstring on `_sibling_data_source` at line ~73:
```python
# Before
"""Convert a sibling hint like 'Policy.policyNumber()' → '$policy.policyNumber'."""

# After
"""Convert a sibling hint like 'Policy.policyNumber()' → '$data.policy.policyNumber'."""
```

### T3 — Re-run pipeline for `Simple-form(quote)`

The existing `Simple-form(quote).suggested.yaml` and `Simple-form(quote).final.vm` have
wrong paths. Delete them and re-run legs 1+2+3:

```bash
rm samples/output/Simple-form\(quote\)/Simple-form\(quote\).suggested.yaml
rm samples/output/Simple-form\(quote\)/Simple-form\(quote\).final.vm
python3 scripts/agent.py --yes "RUN_PIPELINE leg1+leg2+leg3 input=samples/input/Simple-form(quote).html registry=registry/path-registry.yaml output=samples/output"
```

**Expected result in regenerated `.final.vm`:**
- `$data.quote.productName` (was `$quote.productName`)
- `$data.quote.quoteNumber` (was `$quote.quoteNumber`)
- `$data.quote.startTime` (was `$quote.startTime`)

### T4 — Verify with Leg 4

Re-run Leg 4 on the regenerated suggested YAML to confirm plugin report reflects correct paths:

```bash
python3 scripts/leg4_generate_plugin.py \
  --suggested samples/output/Simple-form\(quote\)/Simple-form\(quote\).suggested.yaml \
  --customer-jar build/customer-config.jar \
  --datamodel-jar build/core-datamodel-v1.7.61.jar \
  --compile-check
```

Check `Simple-form(quote).plugin-report.md` — all `data_source` entries should now show `$data.quote.*`.

### T5 — Mark predecessor plan superseded

Append a note to `.cursor/plans/pipeline-improvements/Leg4-renderingData-alignment/00-plan.md`
under a new `## Superseded assumption` section:

> **2026-06-03 — Wrong assumption corrected.** This plan assumed templates reference named roots
> as bare `$quote.*`/`$segment.*` variables. Confirmed via live renderer: all renderingData keys
> are exposed under `$data`, so templates must use `$data.quote.*` etc. Fixed in plan
> [Leg2-data-root-prefix-fix](../Leg2-data-root-prefix-fix/00-plan.md).

---

## Acceptance criteria

- [ ] `Simple-form(quote).final.vm` contains `$data.quote.productName`, not `$quote.productName`
- [ ] `Simple-form(quote).suggested.yaml` verdicts show `data_source: $data.quote.*`
- [ ] Leg 4 plugin report shows no `$quote.*` paths
- [ ] No other `.final.vm` files in `samples/output/` contain bare `$quote.*` or `$segment.*` tokens
