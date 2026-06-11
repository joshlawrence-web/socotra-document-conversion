# Quote Paths Registry — Automated `quote_paths` Generation

**Status:** Ready
**When done:** set `Status: Done`, add `Completed:` date, move folder to `CompletedPlans/` (§7).
**Created:** 2026-06-09  
**History:** [history.md](./history.md) (append-only)

---

## START HERE (implementing agent)

This plan automates the `quote_paths` section of `registry/path-registry.yaml`.
The section was hand-edited as part of the path-catalog work — that is fragile
and must be replaced by a repeatable build step before the registry can be
regenerated cleanly.

**Read in this order:**

1. This file — §2 (decisions), §3 (task list)
2. `registry/sdk-schema-index.yaml` — already-generated output from `build_schema_index.py`;
   contains `ZenCoverQuote` and every other reachable type at depth 3
3. `scripts/build_schema_index.py` — the upstream script; understand its output contract
4. `scripts/sdk_introspect.py` — `_zero_arg_methods`, `_unwrap_type`, `roots_for_product` —
   the introspection layer the new script will reuse
5. `registry/path-registry.yaml` — understand the `quote_paths` shape being produced

---

## 1. Background

`registry/path-registry.yaml` is hand-maintained for most sections, but the
`quote_paths` section is purely derived from the SDK: every public zero-arg
accessor on `ZenCoverQuote` that isn't a Java utility method is a callable
field when the document operation is `quote`.

Current state (after path-catalog work):
- `quote_paths` was hand-added to `path-registry.yaml` — 19 entries, sourced
  manually by reading `sdk-schema-index.yaml`.
- No script exists to regenerate or validate it.
- Any `build_schema_index.py` re-run + manual registry rewrite will lose it.

Target state:
```
build_schema_index.py  →  registry/sdk-schema-index.yaml   (already exists)
build_quote_paths.py   →  reads sdk-schema-index.yaml
                          writes/replaces quote_paths in path-registry.yaml
```

`build_quote_paths.py` must work **without JARs** (reads the pre-built index),
so authors and CI can run it without a compiled build environment.

---

## 2. Decisions

| # | Topic | Decision |
|---|-------|----------|
| D1 | Source | Read `registry/sdk-schema-index.yaml` (pre-built). No JAR dependency. |
| D2 | Root type | `{Product}Quote` entry in the index (e.g. `ZenCoverQuote`). Product read from `registry/path-registry.yaml` `meta.product`. |
| D3 | Exclusion list | Drop well-known Java utility methods: `hashCode`, `toString`, `type`, `anonymizeData`, `toBuilder`, `builder`, `element`. Also drop any field whose return type is a collection, map, or non-navigable Java type (i.e. `_unwrap_type` returns `None` AND the return type isn't `String`/`Optional<String>`/`BigDecimal` etc. — see §4). |
| D4 | Dedup against system_paths | Fields already present in `system_paths` by `velocity` value are skipped (e.g. `$data.locator`, `$data.productName`, `$data.currency`). |
| D5 | Type mapping | Map Java return types to registry `type`/`quantifier`/`cardinality` using a lookup table (see §4). |
| D6 | Output | **Patch** `quote_paths` in `path-registry.yaml` in-place; all other sections are preserved unchanged. Write is atomic (write to `.tmp`, rename). |
| D7 | Idempotent | Running twice with unchanged JARs produces identical YAML. Field order follows the index key order (alpha, since `yaml.dump` sorts by default). |
| D8 | CLI | `python3 scripts/build_quote_paths.py [--schema-index <path>] [--registry <path>]`. Both default to standard paths. |
| D9 | Pipeline wiring | `RUN_PIPELINE build_quote_paths` dispatched in `agent.py` → `run_build_quote_paths()` in `agent_tools.py`. |
| D10 | CLAUDE.md | Add trigger phrases + command to CLAUDE.md after wiring confirmed. |
| D11 | Manual edits | The hand-added `quote_paths` block in `path-registry.yaml` is the correct target shape — use it as a reference/test fixture, then have the script produce the same output. After the script is verified, the manual block is the correct output (just now generated). |

---

## 3. Task list

Check boxes when done; append a handoff to [history.md](./history.md).

---

### T1 — `scripts/build_quote_paths.py` — core script

**Goal:** Read `sdk-schema-index.yaml`, extract `{Product}Quote` fields, patch
`quote_paths` into `path-registry.yaml`.

**Algorithm:**

```
1. Load sdk-schema-index.yaml
2. Read product from path-registry.yaml meta.product
3. Find entry "{Product}Quote" (e.g. "ZenCoverQuote")
4. Load existing system_paths velocities as a set (for dedup, D4)
5. For each field in ZenCoverQuote.fields:
   a. Skip if in EXCLUDED_METHODS (D3)
   b. Map return_type → (type, base_type, quantifier, cardinality) via TYPE_MAP (§4)
   c. Skip if return_type maps to None (collection, map, un-navigable, D3)
   d. Skip if "$data.<field>" already in system_paths velocity set (D4)
   e. Build registry entry dict
6. Sort entries by field name (alpha, for idempotency D7)
7. Patch path-registry.yaml: replace quote_paths block with new entries
8. Atomic write (write temp file → rename, D6)
```

**Type mapping table (§4 — `TYPE_MAP`):**

| Java return type pattern | registry `type` | `base_type` | `quantifier` | `cardinality` |
|--------------------------|-----------------|-------------|--------------|---------------|
| `java.lang.String` | `string` | `string` | `''` | `exactly_one` |
| `Optional<java.lang.String>` | `string?` | `string` | `'?'` | `zero_or_one` |
| `java.time.Instant` | `datetime` | `datetime` | `''` | `exactly_one` |
| `Optional<java.time.Instant>` | `datetime?` | `datetime` | `'?'` | `zero_or_one` |
| `java.time.LocalDate` | `date` | `date` | `''` | `exactly_one` |
| `Optional<java.time.LocalDate>` | `date?` | `date` | `'?'` | `zero_or_one` |
| `java.math.BigDecimal` | `decimal` | `decimal` | `''` | `exactly_one` |
| `Optional<java.math.BigDecimal>` | `decimal?` | `decimal` | `'?'` | `zero_or_one` |
| `int` / `java.lang.Integer` | `int` | `int` | `''` | `exactly_one` |
| `Optional<java.lang.Integer>` | `int?` | `int` | `'?'` | `zero_or_one` |
| `java.lang.Boolean` / `boolean` | `boolean` | `boolean` | `''` | `exactly_one` |
| `Optional<java.lang.Boolean>` | `boolean?` | `boolean` | `'?'` | `zero_or_one` |
| `com.socotra.platform.tools.ULID` | `string` | `string` | `''` | `exactly_one` |
| `Optional<com.socotra.platform.tools.ULID>` | `string?` | `string` | `'?'` | `zero_or_one` |
| `Optional<java.util.UUID>` | `string?` | `string` | `'?'` | `zero_or_one` |
| Any `com.socotra.coremodel.*` (non-Optional) | `string` | `string` | `''` | `exactly_one` |
| Any `Optional<com.socotra.coremodel.*>` | `string?` | `string` | `'?'` | `zero_or_one` |
| Any `Optional<com.socotra.deployment.*>` | `string?` | `string` | `'?'` | `zero_or_one` |
| `Collection<*>` / `Map<*>` / `java.util.List<*>` | — skip — | — | — | — |
| Everything else | — skip — | — | — | — |

Display name: title-case the camelCase field name (e.g. `quoteNumber` → `Quote Number`).
Velocity: `$data.<fieldName>`.
Category: `quote_system`.
`iterable: false`, `requires_scope: []`.

**Files:**
- `scripts/build_quote_paths.py` — new file

**Definition of done:**
- Running against the current `sdk-schema-index.yaml` + `path-registry.yaml` produces
  a `quote_paths` block whose field names and types match the hand-added block exactly
  (use that as ground truth — see D11).
- Running twice is idempotent.
- No JAR needed.

---

### T2 — Wire into `agent_tools.py`

**Goal:** Add `run_build_quote_paths(schema_index, registry) -> dict`.

```python
def run_build_quote_paths(
    schema_index: str = "registry/sdk-schema-index.yaml",
    registry: str = "registry/path-registry.yaml",
) -> dict:
    """Regenerate quote_paths in path-registry.yaml from sdk-schema-index.yaml."""
    # calls build_quote_paths.patch_registry(schema_index, registry)
    # returns {"ok": True, "artifacts": [registry]}
```

**Files:**
- `scripts/agent_tools.py`

---

### T3 — Wire into `agent.py` dispatch

**Goal:** Add `build_quote_paths` case to `RUN_PIPELINE` dispatch.

Accepted args: `schema_index=<path>` (optional), `registry=<path>` (optional).

```
python3 scripts/agent.py --yes "RUN_PIPELINE build_quote_paths"
python3 scripts/agent.py --yes "RUN_PIPELINE build_quote_paths registry=registry/path-registry.yaml"
```

**Files:**
- `scripts/agent.py`

---

### T4 — CLAUDE.md trigger phrases

**Trigger phrases to add:**
- "regenerate the quote paths"
- "rebuild the registry quote section"
- "update quote fields from the SDK"
- "run build quote paths"

**Command to document:**
```
python3 scripts/agent.py --yes "RUN_PIPELINE build_quote_paths"
```

**Files:**
- `CLAUDE.md`

---

## 4. Recommended order

1. **T1** — implement and verify output matches hand-added block exactly
2. **T2** — wrap in `agent_tools.py`
3. **T3** — add dispatch to `agent.py`
4. **T4** — CLAUDE.md (last, after command syntax confirmed)

---

## 5. Repo signposting

| Path | Role |
|------|------|
| `registry/sdk-schema-index.yaml` | Source — pre-built from JARs by `build_schema_index.py` |
| `registry/path-registry.yaml` | Target — `quote_paths` section patched in-place |
| `scripts/build_quote_paths.py` | **New** — derives and patches `quote_paths` |
| `scripts/build_schema_index.py` | Upstream step — run first if JARs have changed |
| `scripts/agent_tools.py` | Add `run_build_quote_paths()` |
| `scripts/agent.py` | Add `build_quote_paths` dispatch |
| `CLAUDE.md` | Add trigger phrases |

---

## 6. Dependency chain

```
[JARs change]
    → python3 scripts/build_schema_index.py   → registry/sdk-schema-index.yaml
    → python3 scripts/build_quote_paths.py    → registry/path-registry.yaml (quote_paths patched)
    → python3 scripts/list_paths.py           → field catalog rendered
```

All three steps are independent CLIs that can be run individually or chained.
`build_quote_paths.py` is the missing link between the JAR-derived index and the
human-readable registry.

---

## 7. Self-certification (completing agent — required)

When every item in §4 Definition of done is satisfied:

1. Edit this file: change `**Status:** Ready` → `**Status:** Done` and add `**Completed:** <date>`.
2. Move this folder: `mv .cursor/plans/pipeline-improvements/quote-paths-registry/ .cursor/plans/pipeline-improvements/CompletedPlans/`
3. Commit both changes with your implementation (or in a follow-up commit).

**Do not skip this step.** Plans left open after completion create false signals about remaining work.
