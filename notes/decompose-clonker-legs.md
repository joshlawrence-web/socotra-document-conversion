# Improvement note — decompose the clonker legs along their natural seams

**Status:** idea — not started (2026-06-18)
**Owner:** Josh
**Effort:** large (do last; one seam at a time)
**Context:** four modules absorbed multiple concerns as the pipeline grew. They work,
but each mixes 2–3 jobs, which makes them hard to read and risky to change. The CODEMAP
already exposes clean cut lines — this note records the best ones.

> Do [retire-legacy-conditional-form](retire-legacy-conditional-form.md) and
> [dedup-shared-registry-and-markup](dedup-shared-registry-and-markup.md) **first** —
> they shrink these files before we carve them, so we don't split code we're about to
> delete or share.

## Current sizes

| Module | Lines |
|---|---|
| `leg4_generate_plugin.py` | 2,141 |
| `leg2_fill_mapping.py` | 1,674 |
| `leg0_ingest.py` | 1,461 |
| `convert.py` (Leg 1) | 1,358 |

## Seam 1 — Leg 4: pull out additive-merge (best first cut)

`_parse_existing_plugin_keys` (`:767`), `parse_plugin_keys` (`:774`), `_diff_keys`
(`:898`), `_append_to_plugin` (`:923`) form a self-contained "merge a new form into an
existing `.java`" concern (~250–300 lines incl. conditional-id renumber). Extract to
`plugin_merge.py`; what's left in `leg4` is just codegen. Clearest, lowest-coupling cut.

## Seam 2 — Leg 0: pull out the conditional round-trip

`write_variants_csv` (`:835`), `write_conditional_blocks` (`:899`), `load_conditional_blocks`
(`:925`), `parse_variants_csv_to_blocks` (`:1050`), `write_conditional_registry` (`:1129`)
are a distinct "conditional forms I/O" module. Extract to `conditional_forms.py`; what's
left in `leg0_ingest.py` is genuinely "ingest a document → HTML + fields + loops."
(Pairs naturally with retiring the legacy form parser first.)

## Seam 3 — Leg 2: split matching from verdicts

Two interleaved layers:
- **Candidate derivation** (root-independent): `derive_variable_candidate` (`:604`),
  `match_token`, `build_registry_index`.
- **Per-root verdicts** (JAR probe + grade): `variable_verdict_for_root` (`:877`),
  `loop_root_verdict_for_root` (`:1210`), `loop_field_verdict_for_root` (`:1240`).

Separate into "what could this token mean" vs "is it real against root X." Higher
coupling than seams 1–2 — do it only if Leg 2 is still painful after the dedup work.

## Leg 1 (`convert.py`)

Mostly addressed by the shared `markup.py` extraction (see the dedup note). Re-measure
after that lands before deciding on a further split.

## Principles

- One seam per PR, each behind the green suite (444 tests). Never split two at once.
- Extract *modules*, not just functions — the win is a smaller surface to reason about,
  not line-count theater.
- If a seam doesn't reduce coupling (just moves lines), skip it.
