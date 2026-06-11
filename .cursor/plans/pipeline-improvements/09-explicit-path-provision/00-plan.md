# Plan 09 — Explicit Path Provision at Docx/PDF Stage

## Motivation

Plan 08 established that Leg 2 will never overwrite a `data_source` that is already populated, and stripped all heuristic matching fallbacks so every path must be explicitly provided. This created a two-phase authoring model: users pick paths from `field-catalog.md`, write them into their source document as `{account.data.firstName}`, and Leg 2 merely validates and wires the explicit selection. The problem is that neither Leg 0 (`leg0_ingest.py`) nor Leg 1 (`convert.py`) participates in this contract yet — both discard any structural information in a placeholder and always write `data_source: ""`. The authoring intent expressed in `{account.data.firstName}` is lost at ingest time, forcing a human to re-enter the exact same path into the mapping YAML by hand. Plan 09 closes that gap by teaching Leg 0 and Leg 1 to detect dotted-path placeholders, resolve each against the registry's `velocity:` values, and write the resolved path into `data_source` before Leg 2 ever runs.

## Design Decisions

### 1. Lookup strategy: flat velocity-map over full-path suffix matching

The registry `velocity:` values, stripped of their `$data.` prefix, are exactly the strings a user would write in a placeholder: `account.data.firstName`, `data.coolingOffPeriod`, `locator`, `quoteNumber`, etc. Exposure-scoped and coverage-scoped paths use a different iterator root (`$item.data.purchaseDate` → user writes `item.data.purchaseDate`). Rather than building a category-aware prefix-stripping parser, the cleanest and most robust lookup is a single flat map keyed by the path as it appears after removing the leading `$` sigil:

```
"data.account.data.firstName" → "$data.account.data.firstName"
"item.data.purchaseDate"      → "$item.data.purchaseDate"
"data.locator"                → "$data.locator"
```

A two-pass lookup is used:

- **Pass 1 (exact suffix):** strip `$` from every `velocity:` value and build a map. Try the placeholder text as a literal key.
- **Pass 2 (accessor shorthand):** build a secondary map where each key is the accessor form shown by `list_paths.py` to users (e.g. `account.data.firstName` → `$data.account.data.firstName`). Try the placeholder text against this map.

If Pass 1 and Pass 2 both match, Pass 1 wins. If neither matches, fall through to the unresolved handler.

The flat map is built once per registry load and shared across all tokens in the same run.

### 2. Detection heuristic: dotted path vs bare label

A placeholder is treated as an explicit path candidate if and only if its name contains at least one dot. Bare single-word identifiers (e.g. `{FirstName}`, `{vin}`) remain with `data_source: ""` and are left to Leg 2 matching as before.

In `leg0_ingest.py`, `_FIELD_RE` must be widened from `r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}"` to `r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}"` so that `{account.data.firstName}` is captured as a single token rather than matching only `{account}` and leaving `.data.firstName}` as literal text.

In `convert.py`, `VAR_RE` already captures dotted names inside double-braces (`{{account.data.firstName}}`), so no regex change is needed — the dot-presence check is enough to gate the lookup path.

### 3. Unresolved handling: sentinel value + per-file warning block

If a dotted placeholder is not found in the registry after both lookup passes:

- `data_source` is written as `UNRESOLVED:<original_placeholder_name>` (e.g. `UNRESOLVED:account.data.unknownField`)
- The script prints a warning to stderr listing every unresolved token
- In `convert.py`, unresolved tokens are also appended to `mapping.warnings`

Leg 2 skips entries with non-empty `data_source`, so `UNRESOLVED:*` values are preserved through. A follow-on plan should add a Leg 3 guard that rejects entries where `data_source` starts with `UNRESOLVED:`.

### 4. Shared helper vs inline

A shared helper `resolve_dotted_path(name: str, lookup: dict) -> str | None` placed in `scripts/agent_tools.py` avoids duplication. A second helper `build_velocity_lookup(registry_path: Path) -> dict[str, str]` does the one-time flat map construction. Both helpers live in `agent_tools.py`; callers handle sentinel writing and warning emission themselves.

### 5. Leg 0 regex extension

`_FIELD_RE` widens to capture dots. `_normalise_for_leg2` currently hardcodes `"data_source": ""`; it must forward `f.get("data_source", "")` from the fields list entry instead.

### 6. No changes to Leg 2, 3, 4

The Plan 08 `data_source` preservation hook in Leg 2 already handles non-empty `data_source` correctly. No changes needed downstream.

---

## Scope

| File | Change |
|------|--------|
| `scripts/agent_tools.py` | Add `build_velocity_lookup(registry_path)` and `resolve_dotted_path(name, lookup)` |
| `scripts/leg0_ingest.py` | (1) Widen `_FIELD_RE` to capture dots. (2) In `extract_fields()`, detect dotted names, call lookup, write resolved value or `UNRESOLVED:*` sentinel into `data_source`. (3) Accept optional `registry_path` param in `extract_fields` and propagate from `main()`. (4) Fix `_normalise_for_leg2` to forward `data_source` from fields list. (5) Print unresolved-token warnings to stderr. |
| `scripts/convert.py` | (1) In `_record_var`, detect dotted names and call `resolve_dotted_path`; write result or `UNRESOLVED:*` sentinel. (2) Append unresolved tokens to `mapping.warnings`. (3) Pass pre-loaded lookup dict through `convert()` → `rewrite_vars_in_subtree` → `_record_var`. (4) In batch mode, build lookup once. |

## What is NOT changing

- `registry/path-registry.yaml` — read-only; never written by any leg
- `scripts/leg2_fill_mapping.py` — Plan 08 `data_source` hook already in place
- `scripts/leg3_substitute.py`, `scripts/leg4_generate_plugin.py` — no change (follow-on plan: Leg 3 guard for `UNRESOLVED:*`)
- `scripts/list_paths.py` — no change; remains the authoritative catalog for authoring
- Conditional block extraction — no change; uses `[[...]]` syntax, not `{...}`

---

## Implementation Tasks

### Task 1 — `agent_tools.py`: add registry lookup helpers

1. Add `build_velocity_lookup(registry_path: Path) -> dict`:
   - Load YAML with `yaml.safe_load`.
   - Collect every `velocity:` value from `system_paths`, `quote_paths`, `account_paths`, `policy_data`, and `fields` lists inside `exposures[*].system_fields`, `exposures[*].fields`, `exposures[*].coverages[*].fields`.
   - For each `velocity` string `v`: add `v.lstrip("$") → v` (Pass 1), and add accessor shorthand form → v (Pass 2) — strip `$data.` prefix, then strip category prefixes (`account.data.`, `policy.data.`, etc.) to match what `list_paths.py` shows users.
   - Return combined map.

2. Add `resolve_dotted_path(name: str, lookup: dict) -> str | None`:
   - Return `lookup.get(name)`. One line.

### Task 2 — `leg0_ingest.py`: extend regex and wire lookup

1. Change `_FIELD_RE` from `r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}"` to `r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}"`.
2. Add optional `registry_path: Path | None = None` to `extract_fields`. When provided and name contains a dot, resolve and set `data_source` to velocity string or `UNRESOLVED:<name>`.
3. Collect unresolved names; print single `WARNING: unresolved dotted placeholders: ...` to stderr.
4. In `_normalise_for_leg2`, change `"data_source": ""` to `"data_source": f.get("data_source", "")`.
5. In `main()`, find the registry path (use ancestor search similar to `convert.py`) and pass into `extract_fields`.

### Task 3 — `convert.py`: wire lookup into `_record_var`

1. Import or inline `build_velocity_lookup` and `resolve_dotted_path` from `scripts/agent_tools.py` (use `sys.path` insert so `convert.py` can reach `scripts/`).
2. Add optional `velocity_lookup: dict | None = None` to `_record_var`. When name contains a dot and lookup provided, resolve and write `data_source`.
3. Pass lookup through call chain: `convert()` calls `build_velocity_lookup` at registry-load time, passes dict to `rewrite_vars_in_subtree` → `_record_var`.
4. Append `UNRESOLVED:*` entries in `mapping.variables` and loop fields to `mapping.warnings` after all rewriting.
5. In batch mode, build lookup once and pass into each `convert()` call.

### Task 4 — Validation

1. Use a docx fixture with: (a) bare token `{FirstName}`, (b) resolved dotted `{account.data.firstName}`, (c) unresolved dotted `{account.data.unknownField}`.
2. Run Leg 0; inspect mapping: bare → `data_source: ""`, resolved → `data_source: $data.account.data.firstName`, unresolved → `data_source: UNRESOLVED:account.data.unknownField` + stderr warning.
3. Run Leg 2 on the output; confirm resolved and unresolved entries are both skipped (preserved as-is), bare token proceeds through normal Leg 2 matching.
4. Repeat for `convert.py` using HTML with `{{account.data.firstName}}` syntax.
