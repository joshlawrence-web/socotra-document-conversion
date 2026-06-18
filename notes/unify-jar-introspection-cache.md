# Improvement note — unify JAR introspection on the cached schema index

**Status:** idea — not started (2026-06-18)
**Owner:** Josh
**Effort:** small–medium
**Context:** the slowest thing the pipeline does is shell out to `javap` to introspect
the SDK JARs. Leg 2 was already moved onto a precomputed cache; Leg 4 wasn't. Right now
they take two different routes to the same answer.

## Current state

- **Leg 2** consumes a cached `sdk-schema-index.yaml` via `load_schema_index`
  (`leg2_fill_mapping.py:480`) — no live `javap` on the hot path. ✅
- **Leg 4** still introspects **live**: `sdk_introspect._javap` (`sdk_introspect.py:75`)
  via `subprocess`, walked by `validate_path` (`:228`). Every path is a fresh javap shell.
- The cache is produced by `build_schema_index.py` → `sdk-schema-index.yaml`
  (`build_schema_index.py:34`, `sdk_introspect.build_schema_index:337`).

## The improvement

Route Leg 4's path validation through the same cached schema index Leg 2 uses, falling
back to live `javap` only when the index is absent or the path isn't covered (depth >
index `max_depth`). One source of truth for "does this path exist," and Leg 4 stops
paying per-path javap cost.

Open question to settle when this becomes a plan: the schema index has a fixed
`max_depth` (3) — Leg 4 validates some deep accessor chains, so the fallback path must
stay correct for those. Measure how often Leg 4 exceeds the cached depth before
committing to the cache as primary.

## Why it matters

- Faster Leg 4 (and the test suite, which runs Leg 4 with `--compile-check`).
- One introspection contract instead of two — a fix to path-walking logic lands once.
- Makes re-running verification cheap (re-read YAML vs re-shell javap), which helps the
  decomposition work where we'll re-run legs a lot.

## Risk

Medium-low: the fallback must preserve today's correctness for deep/uncached paths.
Keep live `javap` as the backstop; don't delete it. Guard with the existing Leg 4
regression + compile-check tests.

## Relationship to other notes

Independent of the dedup/decompose notes — can be done any time. Naturally pairs with
[decompose-clonker-legs](decompose-clonker-legs.md) seam 1 (Leg 4), since both touch
Leg 4's internals.
