# Leg 2 — Scripted Matching Engine

**Status:** COMPLETE — executed 2026-04-28; post-plan regression fix same session (see Stage 5)
**Goal:** Move all deterministic matching work out of the AI skill and into `leg2_fill_mapping.py`. The AI skill becomes a thin review-and-narrative layer that runs the script, then acts only on the ambiguous cases the script flags.

---

## Problem

The current pipeline has two problems that make Leg 2 slow and heavyweight:

1. **`leg2_fill_mapping.py` has a hardcoded `specials` dict** — a CommercialAuto-specific lookup table of ~30 field names wired to hardcoded paths. New products with different field names fall through to a generic flat-index match, then fail silently. The script is not a general-purpose registry-driven matcher.

2. **The AI skill (`mapping-suggester/SKILL.md`) IS the matching engine** — it reads 4 companion files, runs Rules 1–6 manually, and writes all three output artifacts itself. For a 4-field document this cost ~the same tokens as a 40-field document because the ceremony is fixed overhead. For a 4-field doc this is overkill.

## Solution

Split responsibilities cleanly:

| Responsibility | Owner after this plan |
|---|---|
| Exact / case-insensitive / terminology / fuzzy name matching | `leg2_fill_mapping.py` (script) |
| Scope checking (Rule 2) | script |
| Confidence grading (Rule 3) | script |
| Optional-element / auto-element notes (Rules 4–5) | script |
| Charge disambiguation (Rule 6) | script |
| Feature flag shape probe | script |
| Full review.md (all 7 sections) | script |
| JSONL telemetry | script (already via emit_telemetry.py) |
| Narrative reasoning for blockers | AI skill (review layer only) |
| skill-lessons.yaml updates | AI skill |
| Confirming / overriding suggestions | human + AI skill |

The AI skill's new job: **run the script, read the output, add narrative depth to medium/low items, update lessons.**

---

## What already exists

`scripts/leg2_fill_mapping.py` already has:
- Registry indexing (`index_registry`, `exposure_field_index`, `iterables_by_iterator`)
- Provenance stamping (run_id, SHA hashes, registry config gate)
- Delta mode (merge confirmed entries)
- Basic review.md writer (summary-only stub — needs extension)
- JSONL telemetry via `emit_telemetry.py`

What it is missing:
- Generic name-match rules (exact → case-insensitive → terminology → fuzzy) against display_names
- `terminology.yaml` integration
- Scope checking using `context.loop` / `context.loop_hint`
- Rules 4–6 (optional-element guard, auto-element note, charge disambiguation)
- Feature flag shape probe and refusal
- Full review.md sections §3–§7

The `specials` dict is the CommercialAuto workaround that bypasses all of the above. It must be replaced, not patched.

---

## Stages

```
Stage 1: Audit & spec         ← define exactly what each Rule requires in code
Stage 2: Generic matcher      ← implement Rules 1–6 in leg2_fill_mapping.py
Stage 3: Full review.md       ← extend _write_review_md to emit all 7 sections
Stage 4: SKILL.md as reviewer ← update mapping-suggester to run script first
Stage 5: Conformance tests    ← verify no regressions on existing fixtures
```

Stages 1 and 2 are the core; stages 3–5 are the integration layer.

---

## Definition of done

- [x] `leg2_fill_mapping.py` produces correct suggested.yaml + full review.md for Simple-form, Additional-form, and all conformance fixtures without a `specials` lookup
- [x] `mapping-suggester/SKILL.md` flow is: run script → read output → add narrative → update lessons
- [x] AI token cost for a simple doc drops by ~60–70% (no companion file reads, no manual matching)
- [x] All conformance fixtures still pass (12/12 after regression fix — see Stage 5)
- [x] `specials` dict removed entirely; generic registry-driven matcher in its place
