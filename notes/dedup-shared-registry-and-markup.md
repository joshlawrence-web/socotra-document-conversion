# Improvement note — collapse duplicated registry-index + markup parsing

**Status:** idea — not started (2026-06-18)
**Owner:** Josh
**Effort:** medium (extract + reroute callers; behavior-preserving)
**Context:** the pipeline grew leg-by-leg, and three legs each grew their own copy of
two foundational helpers. They've drifted independently — a bug fixed in one isn't
fixed in the others, and a reader has to learn three near-identical implementations.

## Duplication #1 — "index the registry for lookup" (3 implementations)

| Function | File:line | Used by |
|---|---|---|
| `build_registry_index` | `leg2_fill_mapping.py:252` | Leg 2 token matching |
| `build_candidate_index` | `registry_match.py:56` | Leg -1 leaf resolution |
| `build_registry_index` | `condition_dsl.py:302` | condition DSL leaf → accessor |

(Note: `extract_paths.build_registry` *builds* the registry and
`agent_tools.build_velocity_lookup` is a flat velocity-path map — different jobs, leave
them. The three above all answer the same question: "given a leaf/field name, what are
the candidate accessors?")

**Direction:** one `registry_index.py` with a single indexer that returns a structure
rich enough for all three callers (candidates grouped by scope + display-name aliases).
Reroute the three callers; delete the duplicates.

## Duplication #2 — loop/marker parsing (3 implementations)

| Function | File:line | Markup it parses |
|---|---|---|
| `_collect_mustache_tokens` | `convert.py:435` | Leg 1 HTML `[name]…[/name]` loop markers |
| `extract_loops` | `leg0_ingest.py:610` | Leg 0 `[Name]…[/Name]` → `#foreach` scaffold |
| `_loop_spans` / `_loop_for_position` | `legminus1_resolve_paths.py:90/103` | Leg -1 loop-scope of a `{leaf}` |

`[Name]…[/Name]` (loops) and `[[…]]` (conditionals) are **one grammar**. It's parsed
against a DOM in Leg 1 and against raw text in Legs 0/-1, which is why they diverged —
but the marker syntax + nesting rules are identical.

**Direction:** a `markup.py` that owns the grammar (find marker spans, pair openers/
closers, report nesting + unmatched). DOM vs text stays at the edges (tokenize input →
shared span logic → leg-specific rewrite). Hardest of the two; do it second.

## Why it matters

- A marker-parsing bug fixed once instead of three times.
- Shrinks all three host modules (`convert.py` 1,358 / `leg0_ingest.py` 1,461 /
  `legminus1` 637) for free, ahead of [decompose-clonker-legs](decompose-clonker-legs.md).
- New legs import the shared piece instead of copy-pasting a fourth variant.

## Risk / approach

Behavior-preserving refactor — guarded by the existing regression suite (444 tests).
Do #1 (registry index) first: smaller surface, clearer contract. Land each extraction
as its own commit so a regression bisects cleanly.
