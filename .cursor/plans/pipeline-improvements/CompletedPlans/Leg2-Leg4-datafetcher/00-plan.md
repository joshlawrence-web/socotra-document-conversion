# Leg 2 + Leg 4 — DataFetcher-Aware Path Selection

**Status:** Complete (2026-06-04)  
**Created:** 2026-06-04  
**Predecessor:** [Leg4-plugin-enrichment](../Leg4-plugin-enrichment/00-plan.md) (P4.1–P4.6)  
**History:** [history.md](./history.md) (append-only)

---

## START HERE (implementing agent)

This plan teaches Leg 2 about DataFetcher-sourced paths — fields that cannot be
reached by navigating the rendering root object directly, but CAN be populated
in `renderingData` by calling `DataFetcherFactory.get().<method>()` inside the
snapshot plugin. Leg 4 then becomes data-driven instead of hardcoding a single
`getQuotePricing` call.

**Read in this order:**

1. This file — §2 (context), §3 (locked decisions), §4 (new decisions), §5 (task list)
2. `scripts/sdk_introspect.py` — JAR probing; DataFetcher probing goes here
3. `scripts/leg2_fill_mapping.py` — `variable_verdict_for_root()` is the main change site
4. `scripts/leg4_generate_plugin.py` — `JAVA_TEMPLATE` is the main change site
5. `registry/path-registry.yaml` — registry schema to extend
6. `samples/output/Simple-form(quote)/` — pilot input for quote root
7. `samples/output/Simple-form/` — pilot input for segment root

**Do not** remove or alter the existing direct-path flow (registry entries with no
`source` field). DataFetcher support is additive.

---

## 2. Background

### The problem

`DataFetcherFactory.get()` gives plugins access to entity data that is not
directly navigable from the rendering root object:

- **Quote root** — the quote object has no `pricing()` method; premium totals
  require `getQuotePricing(quote.locator())`.
- **Segment root** — the segment request has no `policyNumber()` at the top
  level; `getPolicy(transaction.policyLocator()).policyNumber()` is needed.
- **Segment root (MTA)** — term charges across all prior transactions require
  `getTermCharges(policy.latestTermLocator())`.

Today, Leg 2 cannot suggest any of these paths — they don't exist as methods on
the rendering root type, so JAR probing returns `not_found` and the fields land
as `$TBD_*` in the final template. Leg 4 hardcodes a single `getQuotePricing`
call in the quote handler regardless of what the mapping contains.

### The mechanism

DataFetcher data enters `renderingData` under a string key chosen by the plugin.
The Velocity template then accesses it as `$data.<key>.<field>`. For example:

```java
// Plugin puts this:
renderingData.put("pricing", DataFetcherFactory.get().getQuotePricing(quote.locator()));

// Template accesses:
$data.pricing.premiumTotal
```

Leg 2 needs to know:
1. That `$data.pricing.premiumTotal` is a DataFetcher-sourced path (not direct).
2. Which DataFetcher method populates the `pricing` key.
3. Whether that method is valid for the current rendering root (lifecycle gate).

Leg 4 needs to:
1. Detect which DataFetcher keys are actually used in the confirmed mapping.
2. Emit exactly those DataFetcher calls (deduplicated by key).
3. Not emit DataFetcher calls for keys that no confirmed field uses.

### Lifecycle constraint — the central rule

The DataFetcher interface has no lifecycle enforcement at compile time. A call to
`getPolicy()` in a quote handler compiles fine but returns null (no policy exists
at quote stage). The lifecycle gate must be enforced by Leg 2 using `valid_roots`
annotations in the registry.

**Authoritative lifecycle table:**

| DataFetcher method        | Quote root | Segment root                         |
|---------------------------|------------|--------------------------------------|
| `getAccount()`            | ✅          | ✅                                    |
| `getQuotePricing()`       | ✅          | ❌ no quote locator on segment request |
| `getQuoteUnderwritingFlags()` | ✅      | ❌                                    |
| `getPolicy()`             | ❌ no policy yet | ✅                              |
| `getTransaction()`        | ❌          | ✅                                    |
| `getTransactionPricing()` | ❌          | ✅                                    |
| `getTermCharges()`        | ❌ no term  | ✅ (includes MTA prior transactions)  |
| `getTermSubsegmentSummaries()` | ❌    | ✅                                    |
| `getSegmentDocuments()`   | ❌          | ✅                                    |
| `getInvoice()` (prior)    | ❌          | ⚠️ prior invoices exist; current MTA invoice not yet generated; locator navigation required |
| `getQuote()` (any root)   | 🚫 blocked  | 🚫 blocked (collision — same entity as rendering root, different Java type) |
| `getSegment()` (segment root) | —     | 🚫 blocked (collision — same entity as rendering root, different Java type) |

Invoice root is **out of scope** for this plan (deferred — sdk_introspect D5 still open).

---

## 3. Locked decisions carried forward

Do not reverse without a new design decision entry.

| # | Topic | Decision |
|---|--------|----------|
| D3 | `renderingData` shape | Full platform object is still put in `renderingData` (e.g. `renderingData.put("quote", quote)`). DataFetcher keys are additional entries alongside it, not replacements. |
| D5 | Invoice root | Deferred. No DataFetcher work for invoice until D5 is resolved. |
| D7 | Compile truth | `build/customer-config.jar` + newest `build/core-datamodel-v*.jar` |
| D8 | Confidence demotion | SDK truth can only demote, never promote. A lifecycle violation always produces `low` confidence regardless of name-match step. |
| DF-BLOCK | Collision guard | `getQuote()`, `getSegment()`, `getPolicy()` (on their respective roots) are blocked from registry entries — they return the same entity as the rendering root but as a less-specific type, silently overwriting the product-specific object in `renderingData`. |

---

## 4. New decisions needed

Fill in before implementing the affected task.

| # | Topic | Decision |
|---|--------|----------|
| N1 | `datafetcher_arg` syntax | **Decided: literal Java expression string** — e.g. `"quote.locator()"`, `"request.transaction().policyLocator()"`. Zero-maintenance; any new traversal works immediately. Typos caught by `--compile-check` in Leg 4. |
| N2 | `datafetcher_key` derivation | **Decided: explicit `datafetcher_key` in registry** — e.g. `pricing` not `quotePricing`. Keeps `$data.pricing.*` matching Socotra docs examples and existing Leg 4 output. Prevents ambiguity when multiple pricing methods exist (quote vs transaction). |
| N3 | Null guard strategy | DataFetcher calls can return null (e.g. `getQuotePricing()` before rating runs). Leg 4 emits null-guarded puts; Leg 3 / template side deferred to separate plan (user noted a Leg 1 idea). For now: emit null guard in Java, no `#if` in the template. |
| N4 | JAR verification for DataFetcher return types | When a registry entry has `source: datafetcher`, what does Leg 2 probe? Options: (a) probe `DataFetcher` interface in JAR for the method return type, then `classify_path` against that type; (b) trust the registry velocity path and skip JAR probing for DataFetcher paths. Option (a) gives verified confidence; option (b) is simpler but all DataFetcher matches cap at `medium`. |
| N5 | Blocked method enforcement | Where is the DF-BLOCK list enforced — in the registry linter (refuse to load entries), in Leg 2 at match time, or both? |

---

## 5. Task list

Check boxes when done; append a handoff to [history.md](./history.md).

---

### DF1 — Registry schema: add DataFetcher fields

Extend `registry/path-registry.yaml` schema with four new optional fields per entry.
Entries without `source` are treated as `source: direct` (current behaviour unchanged).

**New fields:**

```yaml
- field: quotePremiumTotal
  display_name: Total Premium
  velocity: $data.pricing.premiumTotal      # velocity path as seen by the template
  source: datafetcher                        # NEW — marks this as DataFetcher-sourced
  datafetcher_method: getQuotePricing        # NEW — method name on DataFetcher interface
  datafetcher_arg: "quote.locator()"         # NEW — Java expression for the argument (decision N1)
  datafetcher_key: pricing                   # NEW — renderingData key (decision N2)
  valid_roots: [quote]                       # NEW — lifecycle constraint
```

**Validation rules to add to registry loader:**

- `source: datafetcher` requires `datafetcher_method`, `datafetcher_arg`,
  `datafetcher_key`, and `valid_roots`.
- `datafetcher_method` must not be in the DF-BLOCK list for any root in `valid_roots`.
- `velocity` must start with `$data.<datafetcher_key>.` (catches key/path mismatches early).

**Files:**
- `registry/path-registry.yaml` — add DataFetcher entries (see §6 for starter set)
- `scripts/leg2_fill_mapping.py` — `_collect_entries()` already walks the registry;
  no structural change needed there, but add validation at load time.

**Definition of done:**
- Registry loads without error with DataFetcher entries present.
- Malformed entries (missing required fields, blocked method, key/path mismatch) raise
  a clear error at load time, not silently at match time.

---

### DF2 — sdk_introspect.py: DataFetcher return type probe

Add a function that resolves the return type of a named DataFetcher method by
probing the `com.socotra.deployment.DataFetcher` interface in the JAR.

**New function:**

```python
def datafetcher_return_type(classpath: str, method_name: str) -> str | None:
    """Return the FQCN of the type returned by DataFetcher.<method_name>().
    Returns None if the method is not found or return type is not navigable."""
```

This uses the existing `_zero_arg_methods(classpath, "com.socotra.deployment.DataFetcher")`
infrastructure — no new subprocess calls needed.

**Files:**
- `scripts/sdk_introspect.py` — new `datafetcher_return_type()` function

**Decision needed:** N4 (whether to use this for JAR verification or skip it).

**Definition of done:**
- `datafetcher_return_type(classpath, "getQuotePricing")` returns
  `"com.socotra.coremodel.QuotePricing"` (or equivalent from javap output).
- `datafetcher_return_type(classpath, "nonExistent")` returns `None`.

---

### DF3 — Leg 2: lifecycle gate in `variable_verdict_for_root()`

This is the core Leg 2 change. When a matched registry entry has `source: datafetcher`,
apply the lifecycle check before any JAR probing.

**Logic at `variable_verdict_for_root()` entry (after decision N4):**

```
if candidate has source=datafetcher:
    if current root.id not in entry.valid_roots:
        → confidence: low
        → sdk_status: lifecycle_violation
        → reasoning: "<method>() is not available on <root> root — <reason from table>"
        → return early, skip JAR probing
    else:
        if N4=option(a): probe DataFetcher return type, then classify sub-path
        if N4=option(b): mark sdk_status: trusted, confidence: medium (cap)
```

**Reasoning messages for lifecycle violations (use verbatim):**

| Violation | Message |
|-----------|---------|
| `getPolicy()` on quote | `getPolicy() is not available on quote root — no policy exists at quote stage; next-action: supply-from-plugin` |
| `getTermCharges()` on quote | `getTermCharges() is not available on quote root — no term exists at quote stage; next-action: supply-from-plugin` |
| `getQuotePricing()` on segment | `getQuotePricing() is not available on segment root — no quote locator on segment request; next-action: supply-from-plugin` |
| `getTransaction()` on quote | `getTransaction() is not available on quote root — no transaction at quote stage; next-action: supply-from-plugin` |

**Files:**
- `scripts/leg2_fill_mapping.py` — `variable_verdict_for_root()`, `derive_variable_candidate()`
- `scripts/leg2_review_writer.py` — surface `lifecycle_violation` as a distinct review category
  (separate from `not_found` — it's a known method, wrong context)

**Definition of done:**
- A registry entry for `getQuotePricing` on a `(segment)` document gets `confidence: low`
  and `sdk_status: lifecycle_violation` in the `.suggested.yaml`.
- The same entry on a `(quote)` document gets `confidence: high` (if N4=option(a) and
  JAR verifies the sub-path) or `confidence: medium` (if N4=option(b)).
- Review `.md` shows lifecycle violations in a dedicated section.

---

### DF4 — Leg 2: `derive_variable_candidate()` — DataFetcher candidate path

When a registry match has `source: datafetcher`, the candidate path in the
`.suggested.yaml` should include the DataFetcher context so Leg 4 can read it.

**Extend the `candidate` block** in the suggested YAML output:

```yaml
candidate:
  path: $data.pricing.premiumTotal
  match_step: exact
  registry_field: quotePremiumTotal
  source: datafetcher                    # propagated from registry
  datafetcher_method: getQuotePricing
  datafetcher_arg: "quote.locator()"
  datafetcher_key: pricing
```

This block is already written to the YAML by `annotate_mapping()`; the new fields
ride alongside the existing ones with no schema version bump required (additive).

**Files:**
- `scripts/leg2_fill_mapping.py` — `derive_variable_candidate()`, `annotate_mapping()`

**Definition of done:**
- `.suggested.yaml` for a quote document includes `source: datafetcher` in the
  candidate block for matched DataFetcher entries.
- Leg 4 can read `candidate.datafetcher_method` without any changes to YAML parsing.

---

### DF5 — Leg 4: data-driven DataFetcher codegen

Replace the hardcoded `getQuotePricing` call in `JAVA_TEMPLATE` with codegen
driven by the DataFetcher entries present in the confirmed mapping.

**Algorithm:**

1. Walk all variables in the `.suggested.yaml`.
2. Collect entries where `candidate.source == "datafetcher"` AND
   `verdict[root].confidence` is `high` or `medium` (i.e. confirmed, not lifecycle violation).
3. Deduplicate by `datafetcher_key` — one DataFetcher call and one `renderingData.put()`
   per unique key, regardless of how many fields reference that key.
4. For each unique key, emit:
   ```java
   <ReturnType> <key> = null;
   try {
       <key> = DataFetcherFactory.get().<method>(<arg>);
   } catch (Exception e) {
       log.warn("Could not fetch <key> for locator={}", <locator_expr>, e);
   }
   if (<key> != null) {
       renderingData.put("<key>", <key>);
   }
   ```
5. Add required imports for each DataFetcher return type used.

**Remove:** The hardcoded `QuotePricing pricing = null; try { ... getQuotePricing ... }`
block from `JAVA_TEMPLATE`. It is replaced by the data-driven output above.

**Preserve:** The full-object puts (`renderingData.put("quote", quote)` etc.) from D3.
DataFetcher puts are emitted after the full-object puts.

**Files:**
- `scripts/leg4_generate_plugin.py` — `JAVA_TEMPLATE` and the codegen function that
  renders it; add a `_collect_datafetcher_calls(suggested)` helper.

**Decision needed:** N1 (arg syntax — determines how `datafetcher_arg` is embedded
in generated Java), N3 (null guard shape).

**Definition of done:**
- Pilot run on `Simple-form(quote).suggested.yaml` with `getQuotePricing` entries
  produces Java that fetches pricing and puts it in `renderingData["pricing"]`.
- No `getQuotePricing` call appears when no pricing field is in the mapping.
- Java compiles cleanly (`--compile-check` passes).

---

### DF6 — Populate registry: starter DataFetcher entries

Add the first batch of DataFetcher-sourced entries to `registry/path-registry.yaml`
for the ZenCover product. Use the pilot template fields as the guide — add only
entries where a real template field needs them.

**Starter set (confirm against actual template placeholders before adding):**

| Field | Method | Key | Valid roots |
|-------|--------|-----|-------------|
| `quotePremiumTotal` | `getQuotePricing` | `pricing` | `[quote]` |
| `quoteOtherTotal` | `getQuotePricing` | `pricing` | `[quote]` |
| `quoteTotalBillable` | `getQuotePricing` | `pricing` | `[quote]` |
| `accountName` | `getAccount` | `account` | `[quote, segment]` |
| `accountLocator` | `getAccount` | `account` | `[quote, segment]` |
| `policyNumber` | `getPolicy` | `policy` | `[segment]` |
| `policyEffectiveDate` | `getPolicy` | `policy` | `[segment]` |
| `termCharges` | `getTermCharges` | `termCharges` | `[segment]` |

**Files:**
- `registry/path-registry.yaml` — new entries under appropriate sections

**Definition of done:**
- Each entry resolves to `confidence: high` on its valid root(s) in a Leg 2 run.
- Each entry resolves to `confidence: low` + `sdk_status: lifecycle_violation` on
  an invalid root.

---

## 6. Recommended order

1. **N1, N2** — resolve decisions before touching code (30 min design session)
2. **DF1** — registry schema + validation (foundation; everything else reads from it)
3. **DF2** — sdk_introspect probe (depends on N4 decision; can be deferred if N4=option(b))
4. **DF3** — Leg 2 lifecycle gate (core correctness; do before DF4)
5. **DF4** — Leg 2 candidate propagation (extends DF3 output into YAML)
6. **DF5** — Leg 4 data-driven codegen (reads what DF4 writes)
7. **DF6** — populate registry (validates the full end-to-end with real data)

DF2 can be skipped initially if N4=option(b) is chosen — all DataFetcher matches
cap at `medium` but the pipeline works end-to-end. Upgrade to option(a) later.

---

## 7. Repo signposting

| Path | Role |
|------|------|
| `scripts/sdk_introspect.py` | Add `datafetcher_return_type()` (DF2) |
| `scripts/leg2_fill_mapping.py` | Lifecycle gate (DF3), candidate propagation (DF4) |
| `scripts/leg2_review_writer.py` | Surface `lifecycle_violation` in review output (DF3) |
| `scripts/leg4_generate_plugin.py` | Data-driven DataFetcher codegen (DF5) |
| `registry/path-registry.yaml` | New DataFetcher entries (DF1, DF6) |
| `build/core-datamodel-v1.7.61.jar` | DataFetcher interface — probe in DF2 |
| `build/customer-config.jar` | Request types — unchanged |
| `samples/output/Simple-form(quote)/` | Pilot for quote root end-to-end test |
| `samples/output/Simple-form/` | Pilot for segment root end-to-end test |
