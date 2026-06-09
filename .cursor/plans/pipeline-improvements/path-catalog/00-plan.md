# Path Catalog — Field Reference for Document Authors

**Status:** Ready  
**Created:** 2026-06-09  
**History:** [history.md](./history.md) (append-only)

---

## START HERE (implementing agent)

This plan adds a **`list_paths` pipeline command** that renders `registry/path-registry.yaml`
into a human-readable Markdown field catalog. The audience is a document author writing
a `.docx` or HTML template who needs to know what Velocity paths they can use.

**Read in this order:**

1. This file — §2 (decisions), §3 (task list)
2. `registry/path-registry.yaml` — the data source (schema_version 1.1)
3. `scripts/agent_tools.py` — `run_leg*()` pattern to follow for `run_list_paths()`
4. `scripts/agent.py` — dispatch block to add `list_paths` to

---

## 1. Background

`registry/path-registry.yaml` is the authoritative source of all Velocity paths available
in a rendered document. It covers:

| Section key | Category tags | Description |
|------------|---------------|-------------|
| `system_paths` | `system` | `$data.locator`, `$data.policyNumber`, etc. |
| `account_paths` | `account` | `$data.account.data.*` — policyholder fields |
| `policy_data` | `policy_data` | `$data.data.*` — product custom fields |
| `policy_charges` | `fee/premium/tax/nonFinancial` | `$data.charges.<name>.amount` |
| `exposures[*].system_fields` | `exposure_system` | `$item.locator`, `$item.name` |
| `exposures[*].fields` | `exposure_data` | `$item.data.*` — exposure custom fields |
| `exposures[*].coverages[*].fields` | `coverage_data` | `$item.<Coverage>.data.*` |
| `exposures[*].coverages[*].charges` | `coverage_charge` | per-coverage charge amounts |
| `datafetcher_paths` | `datafetcher` | `$data.pricing.*`, `$data.account.*` via DataFetcherFactory |

Document authors currently have no way to discover these paths without reading raw YAML.
The catalog fixes that.

---

## 2. Decisions

| # | Topic | Decision |
|---|-------|----------|
| D1 | Source | Always `registry/path-registry.yaml` — not JARs directly. The registry is already human-curated and carries display names and cardinality. |
| D2 | Output format | Markdown — renders in GitHub, can be pasted into Confluence, and is already the format for other pipeline reports. |
| D3 | Grouping order | System → Account → Policy Custom Fields → Policy Charges → Per-Exposure (each exposure: system fields → custom fields → coverages → coverage charges) → DataFetcher. Mirrors the natural "outer to inner" reading of a policy document. |
| D4 | Datafetcher entries | Show under a dedicated **DataFetcher Paths** section with a `valid_roots` column (quote-only vs. all roots). Do not deduplicate against `account_paths` — they are distinct data sources. Note both the velocity path and the datafetcher method. |
| D5 | Cardinality display | Use symbols: `required` → (blank), `optional` → `?`, `list` → `+`. Match the `quantifier` field in the registry. |
| D6 | Foreach scope | For all iterable-scoped paths (exposure/coverage), show the `#foreach` line as a "Scope" column so authors know the wrapping loop required. |
| D7 | Enum options | If a field has `options:`, add a "Values" column listing the allowed values (truncate at 5 with "…" if longer). |
| D8 | CLI invocation | `python3 scripts/list_paths.py [--registry <path>] [--out <path>]`. Defaults: registry = `registry/path-registry.yaml`, stdout if no `--out`. |
| D9 | Pipeline wiring | `RUN_PIPELINE list_paths registry=<path>` dispatched in `agent.py` → `run_list_paths()` in `agent_tools.py`. Returns the Markdown string; agent writes it to stdout or an output path. |
| D10 | No JAR dependency | `list_paths.py` must work without compiled JARs — pure registry read. Authors running without a build env need this. |

---

## 3. Task list

Check boxes when done; append a handoff to [history.md](./history.md).

---

### T1 — `scripts/list_paths.py` — core renderer

**Goal:** Standalone script that reads the registry and outputs grouped Markdown.

**Output structure:**

```markdown
# ZenCover — Available Velocity Paths

> Generated from registry/path-registry.yaml

## System Fields
| Field | Path | Type | Required |
|-------|------|------|----------|
| Policy number | `$data.policyNumber` | string | ✓ |
...

## Account Fields (Policyholder)
| Field | Path | Type | Required |
...

## Policy Custom Fields
| Field | Path | Type | Required | Values |
...

## Policy Charges
| Charge | Amount path | Object path |
...

## Item Fields
> Loop: `#foreach ($item in $data.items)`

### System
| Field | Path | Type |
...

### Custom Data
| Field | Path | Type | Required | Values |
...

### Coverage: AccidentalDamage
> Guard: `#if($item.AccidentalDamage)`
| Field | Path | Type | Required |
...

### Coverage Charges: AccidentalDamage
| Charge | Path |
...

## DataFetcher Paths
| Field | Path | Type | Valid roots | Fetcher method |
...
```

**Implementation notes:**
- Load YAML with `yaml.safe_load`
- Walk `system_paths`, `account_paths`, `policy_data`, `policy_charges`, `exposures`, `datafetcher_paths` in order
- For `exposures`: one `##` header per exposure (e.g. `## Item Fields`), then subsections for system/fields/coverages
- For coverages: `### Coverage: {name}` followed by coverage fields; if coverage has charges, add `### Coverage Charges: {name}`
- `cardinality_symbol(entry)`: `zero_or_one` → `?`, `one_or_more` → `+`, else blank
- `options_cell(entry)`: join first 5 options with `, `; append `…` if more

**Files:**
- `scripts/list_paths.py` — new file

**Definition of done:**
- Running against `registry/path-registry.yaml` produces valid Markdown with all 8 section types present
- No JAR required
- `--out` flag writes to file; default prints to stdout

---

### T2 — Wire into `agent_tools.py`

**Goal:** Add `run_list_paths(registry_path, out_path=None) -> str` function.

```python
def run_list_paths(registry_path: str, out_path: str | None = None) -> str:
    """Render path catalog Markdown from the registry."""
    # calls list_paths.render_catalog(registry_path)
    # writes to out_path if given, else returns string
```

**Files:**
- `scripts/agent_tools.py`

---

### T3 — Wire into `agent.py` dispatch

**Goal:** Add `list_paths` case to the `RUN_PIPELINE` dispatch block.

Accepted args: `registry=<path>`, `out=<path>` (optional).

```
python3 scripts/agent.py --yes "RUN_PIPELINE list_paths registry=registry/path-registry.yaml"
python3 scripts/agent.py --yes "RUN_PIPELINE list_paths registry=registry/path-registry.yaml out=samples/output/field-catalog.md"
```

**Files:**
- `scripts/agent.py`

---

### T4 — CLAUDE.md trigger phrases

**Goal:** Add trigger phrases and commands for the new pipeline step.

**Trigger phrases to add:**
- "what fields can I use"
- "list available paths"
- "show me the field catalog"
- "what data is available in the template"
- "export the path registry"

**Command to document:**
```
python3 scripts/agent.py --yes "RUN_PIPELINE list_paths registry=registry/path-registry.yaml"
```

**Files:**
- `CLAUDE.md`

---

## 4. Recommended order

1. **T1** — build the renderer standalone first; verify output quality before wiring
2. **T2** — wrap in `agent_tools.py`
3. **T3** — add dispatch to `agent.py`
4. **T4** — CLAUDE.md (last — after command syntax is confirmed)

---

## 5. Example output (excerpt)

```markdown
# ZenCover — Available Velocity Paths

> Generated from `registry/path-registry.yaml` · 2026-06-09

## System Fields
| Field | Path | Type | Required |
|-------|------|------|----------|
| Policy/quote locator | `$data.locator` | string | ✓ |
| Policy number | `$data.policyNumber` | string | ✓ |
| Policy start (epoch ms) | `$data.policyStartTime` | datetime | ✓ |

## Account Fields (Policyholder)
| Field | Path | Type | Required |
|-------|------|------|----------|
| Account First Name | `$data.account.data.firstName` | string | ✓ |
| Email | `$data.account.data.email` | string | ✓ |

## DataFetcher Paths
| Field | Path | Type | Valid roots | Fetcher method |
|-------|------|------|-------------|----------------|
| Total Premium | `$data.pricing.premiumTotal` | string | quote | `getQuotePricing` |
| Account First Name | `$data.account.data.firstName` | string | quote, segment | `getAccount` |
```

---

## 6. Repo signposting

| Path | Role |
|------|------|
| `registry/path-registry.yaml` | Data source — all paths, display names, cardinality |
| `scripts/list_paths.py` | **New** — catalog renderer |
| `scripts/agent_tools.py` | Add `run_list_paths()` |
| `scripts/agent.py` | Add `list_paths` dispatch |
| `CLAUDE.md` | Add trigger phrases |
