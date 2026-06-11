# Plan — Strict Exact Matching (Leg 2 Hardening)

## Motivation

The existing Leg 2 matching engine had multiple heuristic fallback steps: exact → ci (case-insensitive) → terminology (synonym expansion) → fuzzy. This created unpredictable, hard-to-audit results where a token could match a path it was never intended to reference.

The goal is to narrow the pipeline to a single valid match mode: **exact**. Paths must be explicitly provided by the user from the field catalog (`field-catalog.md`) — a generated "menu" of all valid velocity paths. The pipeline's job is to validate and wire those explicit selections, not to guess.

## Design decisions

- **Field catalog as the authoritative menu.** The `list_paths` command generates a human-readable catalog of all `velocity` paths in the registry. Users pick from this catalog explicitly when authoring documents.
- **`field:` key is the match target.** Registry entries have a `field:` (camelCase) and a `velocity:` ($data.* path). Leg 2 matches token names against `field:` — exact only.
- **Explicit `data_source` is preserved.** If a mapping entry already has `data_source` populated (explicit path provided upstream), Leg 2 skips matching entirely for that entry. Never overwrites an explicit selection.
- **`path-registry.yaml` still used for context.** Loop hierarchy, `requires_scope`, `foreach`, `list_velocity`, and coverage manifests are still read from the registry — just the *matching* step is stripped of fallbacks.

## Scope

| File | Change |
|------|--------|
| `scripts/leg2_fill_mapping.py` | Strip ci/terminology steps from `match_token()`; update `confidence_grade()`; strip ci/plural/terminology from `suggest_loop_root()`; preserve explicit `data_source` in enrichment loop |

Leg 1 (`convert.py`) — no change required at this stage. The mechanism for providing explicit paths at the docx/PDF stage is a future work item.

## What was NOT changed

- `suggest_loop_field()` — loop field matching (coverage field decomposition) was not changed in this pass; it uses prefix decomposition against the registry, not name-based heuristics.
- `terminology.yaml` — file remains; loader remains. Terminology is no longer consulted for matching but the infrastructure is intact for potential future use outside matching.
- Leg 1 output format — `data_source: ""` is still written for all new tokens. Explicit path provision at the docx stage is a planned but unimplemented next step.
