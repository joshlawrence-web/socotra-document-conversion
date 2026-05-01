# Agent A — Stage 1A Handoff

**Status: COMPLETE**
**Date completed:** 2026-04-23
**File changed:** `.cursor/skills/mapping-suggester/SKILL.md`

---

## What was done

All 7 changes specified in `01-stage-1A-leg2-run-modes.md` have been applied
to `.cursor/skills/mapping-suggester/SKILL.md`. The changes are **additive
only** — no existing rule text was removed or reordered.

### Changes applied (in order)

| # | Location in SKILL.md | What was added |
|---|---|---|
| 1 | After line 41 (`---` closing "What this skill does"), before `## If a user asks` | New `## Run modes` section with mode vocabulary table |
| 2 | End of Step 2a shape probe rules, before `### Step 3` | `terse` single-line shape probe override |
| 3 | End of Step 3 matching rules, before `### Step 4` | `terse` reasoning format override (single-line quoted string) |
| 4 | End of Step 4b review file rules, before `### Step 4c` | `terse` review.md content override (table-only, no prose) |
| 5 | End of Step 4 YAML-writing rules, before `### Step 4b` | `batch` multi-doc loop with once-per-batch registry load |
| 6 | Same insertion point as Change 5 (appended after batch block) | `delta` pre-filter that skips already-confirmed entries |
| 7 | After existing Step 5 `terminology.yaml` absent note, before `---` | `terse` 5-line condensed summary + `batch` combined summary |

### Verification

Grep anchors confirmed present after edits:

- `## Run modes` → line 43
- `` **`terse` override:** `` (shape probe) → line 976
- `**`terse` reasoning format:**` → line 987
- `` **`batch` mode:** `` (loop) → line 1014
- `` **`delta` mode:** `` (pre-filter) → line 1028
- `` **`terse` override:** `` (review) → line 1049
- `` **`terse` override:** `` (terminal) → line 1229
- `` **`batch` override:** `` (terminal) → line 1238

---

## Acceptance criteria check

- [x] `## Run modes` section exists between "What this skill does" and "If a user asks what this skill does"
- [x] Step 2a contains a `terse` override block
- [x] Step 3 contains a `terse` reasoning format block
- [x] Step 4 contains `batch` and `delta` override blocks
- [x] Step 4b contains a `terse` override block
- [x] Step 5 contains `terse` and `batch` override blocks
- [x] No existing rule text was removed or reordered — all overrides are additive
- [x] All added text is valid markdown (no broken tables, no unclosed code fences)

---

## Files NOT touched

- `.cursor/skills/html-to-velocity/SKILL.md` — Agent B's file
- `.cursor/skills/html-to-velocity/scripts/convert.py` — Agent B's file
- Any sample inputs/outputs — Agent C's domain

---

## For Agent B (Stage 1B)

Agent B works in **complete parallel** with Agent A. Agent A's changes have
no overlap with Agent B's files. No coordination needed before Stage 2.

Agent B's task file: `.cursor/plans/pipeline-improvements/02-stage-1B-leg1-batch.md`

Agent B's files to edit:
- `.cursor/skills/html-to-velocity/scripts/convert.py` — add `--batch` flag
- `.cursor/skills/html-to-velocity/SKILL.md` — document `--batch` under `## How to run`

---

## For Agent C (Stage 2 — Validation)

**Do not start until both Agent A and Agent B have written their handoff docs.**

Agent C's task file: `.cursor/plans/pipeline-improvements/03-stage-2-validation.md`

### Pre-flight checks Agent C should run

1. Confirm `## Run modes` heading exists in `mapping-suggester/SKILL.md`:
   ```bash
   grep -n "## Run modes" .cursor/skills/mapping-suggester/SKILL.md
   ```
   Expected: one match near line 43.

2. Confirm `--batch` flag appears in `convert.py --help` output:
   ```bash
   python3 .cursor/skills/html-to-velocity/scripts/convert.py --help
   ```
   Expected: `--batch FILE [FILE ...]` listed.

3. Confirm 4 sample `.mapping.yaml` files exist under `samples/output/<stem>/`.

### What Agent C validates (from Stage 2 plan)

- Test 1: Leg 1 batch mode (`--batch` on 4 HTML files, registry loaded once)
- Test 2: Leg 2 terse mode (single `.mapping.yaml`, terse invocation)
- Test 3: Leg 2 batch mode (4 `.mapping.yaml` files, `path-registry.yaml` read once)
- Test 4: Schema compliance (`.suggested.yaml` has `schema_version: '1.0'`, required keys, single-line `reasoning` in terse mode)
- Test 5: Leg 1 backward compatibility (single-file invocation unchanged)

### Known constraint update for Agent C

The `## Important constraints` section in `mapping-suggester/SKILL.md` still
contains the line:

> **One file at a time.** This skill processes one `.mapping.yaml` at a time.
> For multiple documents, run it once per file.

This constraint predates the run-modes addition. In `batch` mode, the new
`## Run modes` section and Step 4 `batch` override take precedence. Agent C
should note this as a documentation debt but **must not** edit the
`mapping-suggester/SKILL.md` — if a fix is needed, flag it for a follow-up
Agent A pass. The batch override block is explicit and self-consistent; the
old single-file constraint applies only in `full` and `terse` single-doc mode.
