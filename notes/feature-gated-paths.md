# Feature-gated paths — root cause & fix

## Symptom
ZenCover runs with `feature_support.jurisdictional_scopes: false`, yet the
pipeline green-lit `$data.quote.jurisdiction` and produced a template that
renders null live. `jurisdiction()` exists on the Quote type in the SDK JAR but
is never populated when jurisdictional scopes are off. Bad assumption:
"method exists in the JAR ⇒ field is renderable."

## Root cause (two findings)
1. **Logic gap (Leg 2).** `leg2_fill_mapping` verifies a path against the SDK
   schema index and marks it `verified` if the method exists. It had no notion
   of *feature availability*. The existing `REFUSAL_FLAGS`/`PARTIAL_FLAGS` only
   fire when a flag is **true** (config uses an unsupported shape); they don't
   cover the inverse — a flag that is **false** gating a field that still
   compiles.
2. **Registry/generator staleness (hot-swap caveat).** The checked-in
   `registry/path-registry.yaml` has a `quote_system` category (19 entries:
   jurisdiction, region, timezone, …) that the in-tree
   `velocity_converter/extract_paths.py` **cannot produce** — regenerating from
   the live `socotra-config` yields 0 `quote_system` entries. The registry was
   emitted by a newer extractor that is not in the tree. Every downstream leg
   references `quote_system`, so the registry is the de-facto source of truth
   and the in-tree generator is behind it.
   **Do not blind-regenerate the registry** — it would silently delete the
   whole `quote_system` block. Restoring the quote_system extraction logic is a
   separate task.

`detect_features` correctly reports `jurisdictional_scopes: false` — the flag
was never wrong.

## Fix
- **Leg 2 (primary).** `apply_feature_gate()` demotes any verdict that
  auto-filled a path gated by a disabled feature: `sdk_status: feature_gated`,
  confidence `low`, `data_source` cleared (so Leg 3 treats it as an unresolved
  token instead of substituting a null-rendering path). Driven by the registry
  entry's `requires_feature` tag (authoritative), falling back to the platform
  map `FEATURE_AVAILABILITY_GATES` for legacy/untagged registries. Surfaced in
  `.review.md` under "Feature-gated paths (disabled feature_support)".
- **Extractor (mechanism).** `FEATURE_GATED_FIELDS` + `_tag_feature_gates()`
  emit `requires_feature` on any gated path, so a regenerated registry is
  self-describing. Currently a no-op here (the in-tree extractor doesn't emit
  the geo fields); becomes live once quote_system extraction is restored.
- The on-disk `jurisdiction` entry was tagged `requires_feature:
  jurisdictional_scopes` directly so the gate is live now.

Scope decision: only `jurisdiction` is gated (confirmed). `region`/`timezone`
are the same Optional<String> geo triplet but were left ungated pending
confirmation that they're populated solely by jurisdictional scopes.

## Related (not fixed)
- `quantifier: '?'` (optional) vs the hard occurrence guard Leg 4 emits: a bare
  `{jurisdiction}` placeholder defaults to *required* in Leg 0, overriding the
  registry. Separate occurrence-defaulting issue.
