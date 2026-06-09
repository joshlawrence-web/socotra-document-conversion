# History — Leg 2 + Leg 4 DataFetcher Plan

Append-only. One entry per work session.

---

## 2026-06-04 — Plan created

Initial plan written from research session exploring DataFetcher capabilities and
lifecycle constraints. Key findings recorded in §2 of the plan. Decisions N1–N5
are open; no code written yet.

## 2026-06-04 — N1 and N2 decided

N1: literal Java expression string for `datafetcher_arg` (e.g. `"quote.locator()"`).
N2: explicit `datafetcher_key` in registry (e.g. `pricing`, not auto-derived `quotePricing`).
N3–N5 still open.

## 2026-06-04 — DF1–DF6 implemented

**N3 decided:** null guard in Java (already in plan) — confirmed as `try/catch + if (!=null)` pattern.  
**N4 decided:** option (a) with option (b) fallback — JAR probe attempted first via `_method_return_type` against `DataFetcher` interface; if return type not resolvable, falls back to `medium` confidence (`sdk_status: trusted`).  
**N5 decided:** DF-BLOCK enforced at registry load time (`build_registry_index` raises `ValueError`). Lifecycle violations enforced at match time in `_datafetcher_verdict`.

**DF2 — sdk_introspect.py:**
- Added `DATAFETCHER_INTERFACE = "com.socotra.deployment.DataFetcher"`.
- Added `_ANY_METHOD_RE` pattern and `_method_return_type(classpath, fqcn, method_name)` — matches any method by name regardless of arg count.
- Added `datafetcher_return_type(classpath, method_name)` — calls above + `_unwrap_type`.

**DF1 — Registry schema + validation:**
- `_collect_entries` now walks `datafetcher_paths` section.
- `_validate_datafetcher_entry` validates required fields, DF-BLOCK, and velocity/key prefix match.
- `build_registry_index` raises `ValueError` on invalid entries at load time.
- `datafetcher_arg` supports both string (single root) and dict (per-root) format.

**DF3 — Leg 2 lifecycle gate:**
- Added `_DF_BLOCKED_METHODS`, `_DF_LIFECYCLE_MESSAGES` constants.
- Added `_datafetcher_verdict(candidate, rid, classpath)` helper with full lifecycle gate + N4 JAR probe logic.
- `variable_verdict_for_root` calls `_datafetcher_verdict` early, bypassing direct-path JAR probing for DataFetcher candidates.
- `sdk_status: lifecycle_violation` returned for invalid root × method combinations.

**DF4 — Candidate propagation:**
- `derive_variable_candidate` propagates `source`, `datafetcher_method`, `datafetcher_arg`, `datafetcher_key` from registry entry to candidate dict.
- `annotate_mapping` writes all DataFetcher fields into the `candidate` block in `.suggested.yaml`.

**DF5 — Leg 4 data-driven codegen:**
- Added `_collect_datafetcher_calls(suggested, root_id, classpath, skip_keys)` — collects unique DataFetcher keys from confirmed (high/medium) candidates, skips legacy-handled keys.
- Added `_generate_datafetcher_extras(calls)` — null-guarded `try/catch + renderingData.put` blocks (8-space indent).
- Added `_generate_dynamic_imports(all_calls)` — emits `import` lines for resolved return FQCNs.
- `JAVA_TEMPLATE` now has `%(quote_datafetcher_extras)s`, `%(policy_datafetcher_extras)s`, `%(dynamic_imports)s` placeholders.
- Legacy pricing computation block PRESERVED (backward compat). `_LEGACY_PRICING_KEYS = {"pricing"}` skips the pricing key from data-driven extras in the quote handler.
- `render_java` accepts `quote_df_calls` and `policy_df_calls`; `main()` collects these before `_flatten_to_segment_root`.
- All existing tests pass; `javac --compile-check` still PASS.

**DF6 — Registry starter entries:**
- Added `datafetcher_paths` section to `registry/path-registry.yaml`.
- Entries: `quotePremiumTotal`, `quoteOtherTotal`, `quoteTotalBillable` (quote only, `getQuotePricing`), `accountName` (quote+segment, `getAccount`, dict arg), `termChargesTotal` (segment, `getTermCharges`).
- `getPolicy`/`policyNumber` entries deferred — segment handler already puts `policy` in renderingData directly; DataFetcher call would be redundant.

**Review writer (DF3):**
- Added "Lifecycle violations" section above "Blockers" in `.review.md` — shows `sdk_status: lifecycle_violation` pairs in their own table, separate from other low-confidence blockers.

**End-to-end smoke test results:**
- Registry loads cleanly; 5 DataFetcher entries indexed.
- Leg 2 on `Simple-form(quote)` sample: `accountName` gets `medium`/`trusted` (JAR probe fallback); no lifecycle violations on quote root.
- Leg 4 on new suggested: `account` DataFetcher extra emitted after legacy pricing puts; compile PASS.
- Backward compat: Leg 4 on old suggested.yaml (no DataFetcher entries) → unchanged output; compile PASS.

**Open:**
- N4 option (a) will activate automatically once real `DataFetcher` JARs are available; no code change needed.
- `accountName` conflict with `account_paths` section (same field name, different velocity path) — may cause ambiguity if both entries match in a future run. Monitor and deduplicate if needed.
- `termChargesTotal` uses `$data.termCharges` as velocity (no sub-field); may need refinement once term charge schema is known.
