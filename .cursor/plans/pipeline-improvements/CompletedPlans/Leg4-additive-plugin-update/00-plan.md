# Leg 4 — Additive Plugin Update

**Status:** Complete  
**Created:** 2026-06-08  
**Predecessor:** [Leg4-plugin-enrichment](../Leg4-plugin-enrichment/00-plan.md)  
**History:** [history.md](./history.md) (append-only)

---

## START HERE (implementing agent)

This plan adds an **additive coverage check** to Leg 4. When a product already has a
`{Product}DocumentDataSnapshotPluginImpl.java`, running Leg 4 again with a new form's
`.suggested.yaml` should:

1. Read the existing plugin and determine what `renderingData` keys it already provides
2. Determine what keys the new form requires
3. Add **only the missing keys** — never remove or modify existing puts
4. Report what was already present vs what was added

**Read in this order:**

1. This file — §2 (decisions), §3 (task list)
2. `scripts/leg4_generate_plugin.py` — current implementation (parse + codegen)
3. `scripts/agent_tools.py` — `run_leg4()` — the caller to extend
4. `scripts/agent.py` — invocation dispatch

**Do not** change the generate-from-scratch path. When no existing plugin is found,
behaviour is identical to today.

---

## 1. Background

Currently Leg 4 always generates a fresh Java file from scratch. If the file already
exists it is silently overwritten. This is safe for a single form but destructive when
a second form is processed — the first form's custom puts are lost.

The additive path fixes this: the existing plugin is the source of truth for what's
already wired. The new `.suggested.yaml` is the source of truth for what's needed next.

---

## 2. Decisions

| # | Topic | Decision |
|---|--------|----------|
| A1 | Existing plugin discovery | Auto-discover by convention: `{out_dir}/{Product}DocumentDataSnapshotPluginImpl.java`. No extra flag needed — if the file exists, additive mode activates. |
| A2 | Key extraction from Java | Regex: `renderingData\.put\("([^"]+)"` — extract all string-literal keys. Handles both generated and hand-edited plugins. |
| A3 | Required keys from `.suggested.yaml` | Variables with any `data_source` + all conditional block IDs (`condN`). Confidence level does not gate inclusion — every variable with a path needs a put. |
| A4 | Which `dataSnapshot()` method to append to | Quote variables → quote overload. Policy/segment variables → policy overload. Conditional puts → **both** overloads (conditionals are document-scoped, not request-scoped). |
| A5 | Condition ID assignment | New form's conditional blocks are local IDs (1, 2, 3…). Read high-water mark from existing plugin (`max(condN)` in existing puts). Offset: `global_id = high_water + local_id`. |
| A6 | Backup before modification | Write `{class_name}.java.bak` before appending. Never modify without backup. |
| A7 | No conflict resolution | If a key already exists in the plugin, skip it unconditionally. No confidence comparison. |
| A8 | Batch / multiple forms | `--suggested` accepts a list. Process sequentially. Each form reads the plugin state left by the previous one. |

---

## 3. Task list

Check boxes when done; append a handoff to [history.md](./history.md).

---

### A-T1 — Parse existing plugin for provided keys

**Goal:** Implement `_parse_existing_plugin_keys(java_path: Path) -> set[str]`.

Uses `A2` regex to extract all `renderingData.put("key", ...)` string literal keys from
the existing Java file. Returns an empty set if the file does not exist.

Also implement `_parse_existing_cond_high_water(java_path: Path) -> int` — finds the
highest `condN` key present (e.g. `cond50` → 50). Returns 0 if none found.

**Files:**
- `scripts/leg4_generate_plugin.py` — two new helper functions

**Definition of done:**
- Given `Simple-form`'s existing Java, function returns the correct set of keys
- `_parse_existing_cond_high_water` returns correct integer

---

### A-T2 — Compute required keys from `.suggested.yaml`

**Goal:** Implement `_required_keys(suggested: dict) -> dict[str, str]` — returns
`{key: root_id}` for all variables that have a `data_source` path, using per-root
verdicts (schema 2.0) or flat fields (schema 1.x). Also appends conditional keys
using local IDs (not yet offset — offset happens in A-T3).

**Files:**
- `scripts/leg4_generate_plugin.py` — new helper

**Definition of done:**
- Returns correct keys for `Simple-form.suggested.yaml`

---

### A-T3 — Diff + offset conditional IDs

**Goal:** Implement `_diff_keys(required, existing_keys, cond_high_water)`.

- Variables: `missing = required.keys() - existing_keys`
- Conditionals: offset local IDs by `cond_high_water`. `cond1` (local) → `cond51` (global) if high water is 50.
- Returns `(missing_vars, missing_conds_with_global_ids)`

**Files:**
- `scripts/leg4_generate_plugin.py` — new helper

---

### A-T4 — Append missing puts to existing Java

**Goal:** Implement `_append_to_plugin(java_path: Path, missing_vars, missing_conds)`.

1. Write backup (`java_path.with_suffix('.java.bak')`)
2. Read existing Java text
3. Find the closing `}` of each `dataSnapshot()` overload — insert new puts just before it
4. For conditional puts, append to both overloads
5. Write modified Java back

**Insertion pattern:** Find `return DocumentDataSnapshot.builder()` within each overload
and insert new `renderingData.put(...)` lines immediately before it.

**Files:**
- `scripts/leg4_generate_plugin.py` — new helper

**Definition of done:**
- Round-trip test: existing plugin + new `.suggested.yaml` → only new keys appear
- Existing keys unchanged
- `.java.bak` written before modification

---

### A-T5 — Wire into `main()` and `agent_tools.py`

**Goal:** Update `main()` in `leg4_generate_plugin.py`:

- After computing `out_dir` and `class_name`, check if `{out_dir}/{class_name}.java` exists
- If exists: run additive path (A-T1 → A-T4)
- If not: run existing generate-from-scratch path (unchanged)

Update `run_leg4()` in `agent_tools.py`:
- Accept `suggested` as a list (multiple forms)
- Loop: call leg4 for each, passing same `out_dir` so each run reads the prior state

**Files:**
- `scripts/leg4_generate_plugin.py` — `main()` branching
- `scripts/agent_tools.py` — multi-form loop

---

### A-T6 — Update report for additive mode

**Goal:** When running in additive mode, the report (`<stem>.plugin-report.md`) should
include a new section:

```
## Additive update summary
| | |
|---|---|
| Keys already present | 42 |
| Keys added this run | 7 |
| Conditional high water before | 50 |
| New conditional IDs assigned | 51–53 |
```

**Files:**
- `scripts/leg4_generate_plugin.py` — `write_report()` extension

---

### A-T7 — CLAUDE.md trigger phrases

**Goal:** Add trigger phrases for additive / multi-form invocation to `CLAUDE.md`.

Examples:
- "update the plugin with the new form"
- "add the new document to the plugin"
- "run leg 4 for multiple forms"

**Files:**
- `CLAUDE.md`

---

## 4. Recommended order

1. **A-T1** — parse existing plugin (foundation for everything else)
2. **A-T2** — required keys from YAML
3. **A-T3** — diff + offset
4. **A-T4** — append to Java (highest risk — test carefully)
5. **A-T5** — wire into main + agent_tools
6. **A-T6** — report update
7. **A-T7** — CLAUDE.md

---

## 5. Repo signposting

| Path | Role |
|------|------|
| `scripts/leg4_generate_plugin.py` | Main script — extend with additive path |
| `scripts/agent_tools.py` | `run_leg4()` — extend for multi-form |
| `scripts/agent.py` | Invocation dispatch |
| `samples/output/Simple-form/Simple-form.suggested.yaml` | Pilot input (form 1) |
| `samples/output/heart-circulatory(quote)/` | Second form — use as additive test case |
| `CLAUDE.md` | Trigger phrases |
