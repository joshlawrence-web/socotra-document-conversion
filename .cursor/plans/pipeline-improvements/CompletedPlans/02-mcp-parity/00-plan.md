# MCP Parity — Leg 0 + Leg 4 + list_paths Tools

**Status:** Done
**Completed:** 2026-06-09
**When done:** set `Status: Done`, add `Completed:` date, move folder to `CompletedPlans/` (§6).
**Created:** 2026-06-09
**Item:** Plan-for-plans #2

## START HERE (implementing agent)

Add three missing MCP tools to `mcp_server.py`: `ingest_document` (Leg 0), `generate_snapshot_plugin` (Leg 4), and `list_velocity_paths` (list_paths). The existing four tools cover only Legs 1–3.

**Read in this order:**
1. This file — §2 (decisions), §3 (task list)
2. `mcp_server.py` — existing 4-tool structure (lines 1–240); follow the `_resolve()` / `_run()` / `_artifact_summary()` patterns
3. `scripts/agent_tools.py` — `run_leg0()`, `run_leg4()`, `run_list_paths()` — the backing functions to call
4. `scripts/leg0_ingest.py` — CLI flags to mirror
5. `scripts/leg4_generate_plugin.py` — CLI flags to mirror

---

## 1. Background

`mcp_server.py` exposes four MCP tools registered via `@mcp.tool()`:

| Tool name | Leg | Script |
|-----------|-----|--------|
| `convert_html_to_velocity` | 1 | `convert.py` |
| `extract_velocity_tokens` | 1 | `convert.py` |
| `suggest_velocity_paths` | 2 | `leg2_fill_mapping.py` |
| `write_final_template` | 3 | `leg3_substitute.py` |

Missing:
- **Leg 0** (`leg0_ingest.py`) — ingest `.docx`/`.pdf` → `.raw.html`, `.conditional-form.md`
- **Leg 4** (`leg4_generate_plugin.py`) — generate `SnapshotPlugin.java`
- **list_paths** (`list_paths.py`) — render path catalog Markdown

Without these, Claude Code users running via MCP (not in-repo) cannot start from a Word doc or generate the plugin.

---

## 2. Decisions

| # | Topic | Decision |
|---|-------|----------|
| D1 | Tool naming | `ingest_document`, `generate_snapshot_plugin`, `list_velocity_paths`. Snake-case, verb-first, matches existing tool naming style. |
| D2 | Implementation pattern | Each tool calls the corresponding `run_*()` function from `agent_tools.py` rather than shelling out directly. Consistent with how the in-repo `agent.py` works. |
| D3 | `ingest_document` inputs | `input_path: str`, `output_dir: str = "samples/output"`. Returns artifact summary (same pattern as existing tools). |
| D4 | `generate_snapshot_plugin` inputs | `suggested_path: str`, `customer_jar: str`, `datamodel_jar: str`, `compile_check: bool = True`. Optional `existing_plugin_path: str` for explicit additive target (default: auto-detect from output dir). |
| D5 | `list_velocity_paths` inputs | `registry_path: str = "registry/path-registry.yaml"`, `out_path: str \| None = None`. Returns Markdown string when `out_path` is None; writes to file and returns summary when given. |
| D6 | Error handling | Mirror existing tools: return a plain-text error string starting with `ERROR:` on failure. No exceptions propagate to MCP caller. |
| D7 | `install.py` | No changes needed — `install.py` registers the whole server; new tools are auto-discovered at startup. |
| D8 | README.md MCP section | Update the "How to use it" examples to include all three new tools with natural-language prompts. |

---

## 3. Task list

### T1 — `ingest_document` MCP tool

**Goal:** Expose Leg 0 via MCP.

```python
@mcp.tool()
def ingest_document(
    input_path: str,
    output_dir: str = "samples/output",
) -> str:
    """Ingest a Word (.docx) or PDF document into raw HTML and a conditional form.

    Returns a summary of artifacts written under output_dir/<stem>/.
    Equivalent to: python3 scripts/leg0_ingest.py --input <input_path> --output-dir <output_dir>
    """
```

**Artifact summary should list:**
- `<stem>.raw.html`
- `<stem>.annotated.html`
- `<stem>.fields.yaml`
- `<stem>.mapping.yaml`
- `<stem>.conditional-form.md`

**Files:** `mcp_server.py`

---

### T2 — `generate_snapshot_plugin` MCP tool

**Goal:** Expose Leg 4 via MCP.

```python
@mcp.tool()
def generate_snapshot_plugin(
    suggested_path: str,
    customer_jar: str,
    datamodel_jar: str,
    compile_check: bool = True,
    existing_plugin_path: str | None = None,
) -> str:
    """Generate (or additively update) a DocumentDataSnapshotPluginImpl.java from a .suggested.yaml.

    If the plugin already exists in the output directory, runs in additive mode
    (adds missing keys without removing existing ones, writes a .java.bak first).
    Returns a summary of the plugin report.
    """
```

**Files:** `mcp_server.py`

---

### T3 — `list_velocity_paths` MCP tool

**Goal:** Expose list_paths via MCP.

```python
@mcp.tool()
def list_velocity_paths(
    registry_path: str = "registry/path-registry.yaml",
    out_path: str | None = None,
) -> str:
    """Render a Markdown catalog of all available Velocity paths for this product.

    If out_path is given, writes the catalog to that file and returns a summary.
    Otherwise returns the full Markdown string (suitable for Claude to read and answer questions about).
    """
```

**Files:** `mcp_server.py`

---

### T4 — README MCP usage examples

**Goal:** Update the "How to use it" section in README.md with natural-language prompts for the new tools.

Add examples:
```
ingest my Word document at /path/to/policy-form.docx
list what Velocity paths I can use in my template
generate the snapshot plugin from samples/output/ZenCover/ZenCover.suggested.yaml
```

**Files:** `README.md`

---

### T5 — Smoke test

**Goal:** Verify all 7 tools are discoverable by MCP at startup.

```bash
python3 -c "
import mcp_server  # noqa
print([t.name for t in mcp_server.mcp._tools.values()])
"
# Expected: 7 tools including ingest_document, generate_snapshot_plugin, list_velocity_paths
```

Add this as a regression test.

**Files:** `tests/regression/test_mcp_tools.py` (new)

---

## 4. Definition of done

```bash
# Smoke test — all 7 tools present
python3 -c "import mcp_server; print(len(mcp_server.mcp._tools))"  # → 7

# Functional test — list_paths works via MCP
python3 -c "
from mcp_server import list_velocity_paths
result = list_velocity_paths()
assert '## System Fields' in result
print('OK')
"
```

| Check | Expected |
|-------|----------|
| 7 tools discoverable at startup | ✓ |
| `ingest_document` calls `run_leg0()` (not shell) | ✓ |
| `generate_snapshot_plugin` calls `run_leg4()` | ✓ |
| `list_velocity_paths()` returns valid Markdown | ✓ |
| Error returns `ERROR:` prefix (no exception) | ✓ |
| README MCP section updated | ✓ |

---

## 5. Files touched

| File | Change |
|------|--------|
| `mcp_server.py` | Add 3 new `@mcp.tool()` functions |
| `README.md` | Add MCP usage examples for new tools |
| `tests/regression/test_mcp_tools.py` | **New** — smoke test |

---

## 6. Self-certification (completing agent — required)

When every item in §4 Definition of done is satisfied:

1. Edit this file: change `**Status:** Open` → `**Status:** Done` and add `**Completed:** <date>`.
2. Move this folder: `mv .cursor/plans/pipeline-improvements/02-mcp-parity/ .cursor/plans/pipeline-improvements/CompletedPlans/`
3. Commit both changes with your implementation (or in a follow-up commit).

**Do not skip this step.** Plans left "Open" after completion create false signals about remaining work.
