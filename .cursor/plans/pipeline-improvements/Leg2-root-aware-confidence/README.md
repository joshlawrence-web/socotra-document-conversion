# Leg 2 — Root-aware, SDK-grounded confidence

**Agents: start here.**

| Read first | Purpose |
|------------|---------|
| [problem.md](./problem.md) | The bug + reproducible `javap` evidence (`policyNumber` rated `high` but absent on `ItemCareSegment`). |
| [00-plan.md](./00-plan.md) | Locked decisions, `.suggested.yaml` **2.0** schema, task list, definition of done, §14 downstream spec. |
| [history.md](./history.md) | Session log — append when you change this area. |

## Status

| Phase | Scope | Status |
|-------|-------|--------|
| **0** | Planning (decisions D1–D10) | **Complete** (2026-06-03) |
| **1** | Core Leg 2 — SDK-grounded per-root verdicts | **Complete** (2026-06-03) |
| **2** | Docs, telemetry, conformance (`itemcare-jar`) | **Complete** (2026-06-03) |
| **3** | Downstream harmonisation (Legs 1/3/4, delta mode) | **Partial** — Leg 3 + Leg 4 consume 2.0 (2026-06-03); Leg 1 §14.1 + sibling lifting deferred |

**Overall: COMPLETE for in-scope work.** Do not re-implement unless fixing a regression or the user explicitly reopens scope.

**One-line summary:** Leg 2 grades confidence per **(placeholder × rendering root)** by
introspecting `build/*.jar` via `scripts/sdk_introspect.py`. The root is declared in the
filename: `Simple-form(segment).html`. Output is `.suggested.yaml` **schema 2.0**.

### Verification (should pass today)

```bash
python3 scripts/leg2_fill_mapping.py \
  --mapping  samples/output/Simple-form/Simple-form.mapping.yaml \
  --registry registry/path-registry.yaml \
  --customer-jar build/customer-config.jar \
  --datamodel-jar build/core-datamodel-v1.7.61.jar \
  --out      samples/output/Simple-form/Simple-form.suggested.yaml \
  --mode terse

python3 conformance/run-conformance.py
# → 13/13 PASS (itemcare-jar = registry+suggested+review; rest = registry-only)
```

**Acceptance (met):** `POLICY_NUMBER` is **not** `high` on the segment root
(`sibling_only` + `Policy.policyNumber()` hint); segment-resident fields (e.g. `LOCATOR`)
still rate `high` / `verified`.

### What remains (out of this plan)

| Item | Where | Notes |
|------|-------|-------|
| Leg 1 filename → `rendering_roots:` in `.mapping.yaml` | [00-plan §14.1](./00-plan.md) | Spec only |
| Leg 3 primary-root substitution for `.final.vm` | [00-plan §14.2](./00-plan.md) | **Done** — `_flatten_to_primary_root` normalises 2.0 verdicts |
| Leg 4 v2.0 consumption (segment root) | [00-plan §14.3](./00-plan.md) | **Done** — `_flatten_to_segment_root` normalises 2.0 verdicts; sibling lifting still deferred |
| `--mode delta` for schema 2.0 | D10 / P3.4 | Blocked cleanly; port deferred |

### Locked decisions (00-plan §3)

- **D1** JARs are the SDK authority; registry stays the name→candidate source only.
- **D2** Rendering root declared in filename brackets — no inference.
- **D3** Shared `scripts/sdk_introspect.py` used by Leg 2 + Leg 4.
- **D4** `.suggested.yaml` **MAJOR bump → 2.0** with per-root verdicts.
- **D5** Invoice root out of the first cut.
- **D6** Downstream Leg 1/3/4 changes are **described, not built** (§14).
- **D10** Delta mode out of the first cut — blocked for 2.0.

**Do not** expand scope beyond [00-plan §3](./00-plan.md) without user approval.
