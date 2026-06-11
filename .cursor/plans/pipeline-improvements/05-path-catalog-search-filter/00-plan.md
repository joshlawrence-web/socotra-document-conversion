# Path Catalog Search / Filter

**Status:** Open
**When done:** set `Status: Done`, add `Completed:` date, move folder to `CompletedPlans/` (§6).
**Created:** 2026-06-09
**Item:** Plan-for-plans #5

## START HERE (implementing agent)

Add `--filter`, `--search`, and `--section` flags to `scripts/list_paths.py` so a document author can quickly find specific fields without scanning the full catalog.

**Read in this order:**
1. This file — §2 (decisions), §3 (task list)
2. `scripts/list_paths.py` — `render_catalog()` (line 90), `main()` (line 214) — the current CLI and renderer
3. `scripts/agent_tools.py` — `run_list_paths()` (line 638) — the agent wrapper to extend
4. `scripts/agent.py` — `list_paths` dispatch block — add new kwargs

---

## 1. Background

`list_paths.py` currently renders the full path catalog for the product — a Markdown table for every section. Useful for onboarding but unwieldy when a template author needs to answer "what's the path for policy number?" or "show me all coverage fields for AccidentalDamage."

The full catalog for ZenCover is ~200 lines. `--filter` / `--search` / `--section` make it usable for point lookups without leaving the terminal or opening the YAML.

---

## 2. Decisions

| # | Topic | Decision |
|---|-------|----------|
| D1 | `--filter` | Case-insensitive substring match on `display_name` and `velocity_path`. Applies across all sections. Shows only matching rows; section headers suppressed if all rows filtered out. |
| D2 | `--search` | Alias for `--filter` (same behaviour). Allows natural usage: `list_paths --search firstName`. |
| D3 | `--section` | Show only the named section(s). Valid names: `system`, `account`, `policy`, `charges`, `items`, `datafetcher`. Multiple values comma-separated. Case-insensitive. |
| D4 | Combined flags | `--filter` and `--section` can combine: `--section coverage --filter deductible` shows deductible fields in coverage sections only. |
| D5 | `--count` | Print a summary line at the end: `N paths shown (M total)`. Always shown when filtering is active; suppress otherwise. |
| D6 | No-match output | If no paths match, print: `No paths matched "<query>". Run without --filter to see all paths.` and exit 0. |
| D7 | Pipeline integration | Extend `run_list_paths(filter=None, section=None)` in `agent_tools.py`. Extend the `list_paths` dispatch in `agent.py` to accept `filter=` and `section=` kwargs. |
| D8 | MCP integration | Extend the `list_velocity_paths` MCP tool (plan #2) to accept `filter: str \| None` and `section: str \| None` parameters. |
| D9 | No UI, no external deps | Pure Python string filtering, no regex complexity. `str.lower()` contains-check. |

---

## 3. Task list

### T1 — `filter_catalog()` function in `list_paths.py`

**Goal:** Add a filter function that operates on the rendered section data (before Markdown generation), not on the output string.

```python
def filter_catalog(
    sections: list[dict],     # internal section representation
    filter_str: str | None,   # substring match on name/path
    section_names: list[str] | None,  # restrict to these section keys
) -> list[dict]:
    """Return a filtered copy of sections.
    Each section dict has: key, title, rows: list[{name, path, ...}]
    Empty sections (all rows filtered) are dropped.
    """
```

Refactor `render_catalog()` to:
1. Build a `sections` list (internal repr)
2. Call `filter_catalog()`
3. Render filtered sections to Markdown

**Files:** `scripts/list_paths.py`

---

### T2 — CLI flags in `main()`

**Goal:** Add `--filter` / `--search`, `--section`, `--count` to `argparse`.

```
python3 scripts/list_paths.py --filter "firstName"
python3 scripts/list_paths.py --search "policy number"
python3 scripts/list_paths.py --section account,system
python3 scripts/list_paths.py --section coverage --filter deductible
python3 scripts/list_paths.py --filter "premium" --count
```

**Files:** `scripts/list_paths.py`

---

### T3 — Extend `run_list_paths()` in `agent_tools.py`

**Goal:** Accept and pass through filter/section kwargs.

```python
def run_list_paths(
    registry_path: str,
    out_path: str | None = None,
    filter_str: str | None = None,
    section: str | None = None,
) -> str:
```

**Files:** `scripts/agent_tools.py`

---

### T4 — Extend `list_paths` dispatch in `agent.py`

**Goal:** Accept `filter=` and `section=` in `RUN_PIPELINE list_paths` invocations.

```
RUN_PIPELINE list_paths registry=registry/path-registry.yaml filter=firstName
RUN_PIPELINE list_paths registry=registry/path-registry.yaml section=account,system
```

**Files:** `scripts/agent.py`

---

### T5 — Extend MCP tool (if plan #2 complete) or stub

**Goal:** Add `filter` and `section` params to `list_velocity_paths` in `mcp_server.py`.

If plan #2 is not yet merged, add a `# TODO: plan #2` comment at the right place and skip this task.

**Files:** `mcp_server.py`

---

### T6 — Tests

**Goal:** Unit tests for `filter_catalog()`.

Test cases:
- `test_no_filter_returns_all_sections` — identity when filter=None, section=None
- `test_filter_substring_match` — "firstName" matches Account row, not System rows
- `test_filter_case_insensitive` — "firstname" matches same as "firstName"
- `test_section_filter` — `section=["account"]` returns only account section
- `test_combined_filter_and_section` — `filter="deductible"` + `section=["items"]`
- `test_no_match_returns_empty_list` — filter="xyzzy" → empty sections list
- `test_count_line_in_markdown` — when filter active, output ends with count line

**Files:** `tests/regression/test_list_paths_filter.py` (new)

---

## 4. Definition of done

```bash
# Filter by field name
python3 scripts/list_paths.py --filter "firstName"
# → shows only rows whose name/path contains "firstName"

# Section filter
python3 scripts/list_paths.py --section account

# Combined
python3 scripts/list_paths.py --section items --filter deductible

# Via pipeline
python3 scripts/agent.py --yes "RUN_PIPELINE list_paths registry=registry/path-registry.yaml filter=policyNumber"
```

| Check | Expected |
|-------|----------|
| `--filter firstName` returns fewer rows than no filter | ✓ |
| `--section system` returns only System section | ✓ |
| Combined filter + section works correctly | ✓ |
| No-match case prints helpful message, exits 0 | ✓ |
| `--out` still works with filter active | ✓ |
| All T6 tests pass | ✓ |
| Existing `render_catalog()` output unchanged when no filter given | ✓ |

---

## 5. Files touched

| File | Change |
|------|--------|
| `scripts/list_paths.py` | Add `filter_catalog()`; add CLI flags; refactor `render_catalog()` |
| `scripts/agent_tools.py` | Extend `run_list_paths()` signature |
| `scripts/agent.py` | Accept `filter=` / `section=` in `list_paths` dispatch |
| `mcp_server.py` | Extend `list_velocity_paths` params (if plan #2 merged) |
| `tests/regression/test_list_paths_filter.py` | **New** |

---

## 6. Self-certification (completing agent — required)

When every item in §4 Definition of done is satisfied:

1. Edit this file: change `**Status:** Open` → `**Status:** Done` and add `**Completed:** <date>`.
2. Move this folder: `mv .cursor/plans/pipeline-improvements/05-path-catalog-search-filter/ .cursor/plans/pipeline-improvements/CompletedPlans/`
3. Commit both changes with your implementation (or in a follow-up commit).

**Do not skip this step.** Plans left "Open" after completion create false signals about remaining work.
