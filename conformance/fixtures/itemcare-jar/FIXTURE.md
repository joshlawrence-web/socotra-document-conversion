# itemcare-jar — SDK-grounded confidence (schema 2.0) regression

## Purpose

The **only** fixture that exercises Leg 2's root-aware, **SDK-grounded**
confidence (`.suggested.yaml` schema **2.0**, Leg2-root-aware-confidence plan)
end-to-end. Unlike every other fixture, it is backed by the **real `ItemCare`
config** (a copy of the repo's `socotra-config/`) so its registry paths line up
with the **compiled JARs** in `build/` — `customer-config.jar` +
`core-datamodel-v*.jar`. Confidence here is decided by `javap` against those
JARs, not by the config-only registry (plan **D1**).

This is the fixture that would have caught the original bug: a strong
name-match (`policyNumber`) that the registry rated `high` but that does **not
exist** on the rendering root `ItemCareSegment` (it lives on a sibling
`Policy`). Under 2.0 that is a `low` / `sibling_only` blocker.

## Why it is special among the fixtures

Synthetic fixtures (`minimal`, `multi-product`, …) describe products that were
never compiled, so there is no JAR to introspect. Per **D1** a 2.0 run on them
would (correctly) fail loud. They therefore keep **registry-only** goldens
(`golden/path-registry.yaml`) and their 1.x `suggested`/`review` goldens were
retired (see plan §13 / history 2026-06-03). `itemcare-jar` is the single place
the full SDK-grounded path is regression-tested.

## How the runner drives it

The presence of **`leg2.json`** opts this fixture in. `run-conformance.py`:

1. runs `extract_paths.py` → `actual/path-registry.yaml`, diffs vs golden;
2. sees `leg2.json` and runs `leg2_fill_mapping.py --mode terse` against the
   frozen `golden/path-registry.yaml` + the `build/*.jar` set, writing
   `actual/suggested.yaml` + `actual/review.md`;
3. diffs both against the 2.0 goldens (volatile uuids/timestamps/sha/paths
   normalised).

Requires the compiled ItemCare JARs in `build/`. If they are absent the run
fails loud (by design — D1).

## Rendering root

Declared in the mapping `source: itemcare-jar(segment).html` →
`segment` → `com.socotra.deployment.customer.ItemCareSegment`
(request `ItemCareRequest`). Single primary root.

## Behaviour proven (per `(placeholder × segment)`)

| Placeholder | Candidate | sdk_status | Confidence | Proves |
|---|---|---|---|---|
| `$TBD_LOCATOR` | `$data.locator` | `verified` | **high** | strong name-match **+** `locator()` on `ItemCareSegment` stays `high` |
| `$TBD_POLICY_NUMBER` | `$data.policyNumber` | `sibling_only` | **low** | the original bug — exists on `Policy.policyNumber()`, not the root → demoted to a `supply-from-plugin` blocker |
| `$TBD_POLICYHOLDER_NAME` | `$data.account.data.name` (fuzzy) | `not_found` | **low** | fuzzy match the JAR can't confirm → blocker |
| `$TBD_EFFECTIVE_START_DATE` | (none) | `skipped` | **low** | no registry candidate at all |
| loop `items` | `$data.items` | `verified` | **high** | `items()` on `ItemCareSegment` |
| `goods_category_code` | `$item.data.goodsCategoryCode` | `verified` | **high** | **element-type resolution**: `items()` → `Collection<ItemPolicy>` → `goodsCategoryCode()` on `ItemPolicy` |

The "JAR can only demote" rule (plan §6.3) is visible across the table: name
strength sets the ceiling, the JAR can only lower it.

## Inputs

- `socotra-config/` — copy of the repo's real `ItemCare` product config
  (regenerate with `cp -R socotra-config conformance/fixtures/itemcare-jar/socotra-config`).
- `mapping.yaml` — 4 variables + 1 loop (1 field); `source` carries the
  `(segment)` root; all `data_source` blank.
- `leg2.json` — opt-in marker (`{"mode": "terse"}`).

## Goldens

- `golden/path-registry.yaml` — 148 paths, 1 iterable (`Item`).
- `golden/suggested.yaml` — schema **2.0**: top-level `rendering_roots`,
  per-entry `candidate` + per-root `verdicts`. 2 `high`, 3 `low` (1
  `sibling_only`, 1 `not_found`, 1 `skipped`).
- `golden/review.md` — schema 2.0 per-root rendering; 3 blockers, 2 done.

## Regenerating the goldens

```
python3 scripts/leg2_fill_mapping.py \
  --mapping  conformance/fixtures/itemcare-jar/mapping.yaml \
  --registry conformance/fixtures/itemcare-jar/golden/path-registry.yaml \
  --out      conformance/fixtures/itemcare-jar/actual/suggested.yaml \
  --review-out conformance/fixtures/itemcare-jar/actual/review.md \
  --mode terse
python3 conformance/run-conformance.py --only itemcare-jar          # confirm diff intent
python3 conformance/run-conformance.py --only itemcare-jar --update-goldens
```
