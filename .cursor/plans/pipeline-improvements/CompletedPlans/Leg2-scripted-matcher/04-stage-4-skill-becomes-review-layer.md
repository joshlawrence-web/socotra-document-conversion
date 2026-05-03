# Stage 4 — SKILL.md Becomes a Review Layer

**Status:** COMPLETE
**Depends on:** Stages 2 and 3 complete (script produces correct suggested.yaml + full review.md)
**Output:** Updated `mapping-suggester/SKILL.md` with a new, lighter flow

---

## Overview

The AI skill's job changes from "matching engine + report writer" to "script runner + reviewer of hard cases + narrative author."

The 4 companion files (`SKILL-matching.md`, `SKILL-output-formats.md`, `SKILL-full-mode.md`, `SKILL-lessons.md`) are no longer read on every run. They become reference docs consulted only when the AI needs to understand a specific rule the script surfaced.

---

## Task 4.1 — Rewrite the SKILL.md "How to run" section

New flow (replaces the 5-step sequence):

### Pre-Step — Mode selection
Unchanged: ask user for mode if not in invocation.

### Step 0 — Run the script

```bash
python3 scripts/leg2_fill_mapping.py \
    --mapping <stem>.mapping.yaml \
    --registry registry/path-registry.yaml \
    --out Samples/Output/<stem>/<stem>.suggested.yaml \
    --review-out Samples/Output/<stem>/<stem>.review.md \
    --telemetry-log Samples/Output/<stem>/<stem>.suggester-log.jsonl \
    --mode <mode> \
    [--terminology terminology.yaml]
```

The script handles: version checks, shape probe, Rules 1–6, feature flag surfacing, all three output artifacts.

If the script exits non-zero (MAJOR mismatch, missing required files): print the error and stop.

### Step 1 — Read the script's output

Read `<stem>.suggested.yaml` and `<stem>.review.md`. Do NOT re-derive suggestions from scratch.

### Step 2 — Review medium/low items (full mode only)

For each `low` item: verify the `next_action` is correct, add a narrative paragraph to §3 of the review file explaining WHY this blocks Leg 3.

For each `medium` + `confirm-assumption` item: verify the assumption is reasonable, add a sentence if context from the mapping (label, parent_tag) supports a better explanation.

In **terse** mode: skip narrative additions. Just read and report.

### Step 3 — Update `skill-lessons.yaml`

Unchanged from current Step 4d.

### Step 4 — Print terminal summary

Same terminal summary block as before, using counts from the script-generated review.md.

---

## Task 4.2 — Remove / demote lazy-loaded companion files

After this stage:

| File | New status |
|---|---|
| `SKILL-matching.md` | Reference only — not read during normal runs; consulted if the AI needs to understand a rule |
| `SKILL-output-formats.md` | Reference only — script handles all formatting |
| `SKILL-full-mode.md` | Still read in full mode for narrative depth guidance on §3/§5/§6 |
| `SKILL-lessons.md` | Still read for Step 3 (lessons update) |

Add a note at the top of `SKILL-matching.md` and `SKILL-output-formats.md`:

```
> NOTE (post-Stage-4): the script (leg2_fill_mapping.py) implements these rules.
> This file is the authoritative spec — read it when debugging script behavior,
> not during normal AI-skill runs.
```

---

## Task 4.3 — Update the mode-selection prompt

Add a note that `full` mode now means "script runs + AI adds narrative depth" rather than "AI does full matching." The token cost difference between full and terse is now only the narrative paragraphs, not the matching work.

---

## Task 4.4 — Update the skill description metadata

The `description:` in the SKILL.md frontmatter should reflect the new flow so the agent picker loads the skill at the right time.

---

## Acceptance criteria

- [x] Running the skill in `terse` mode produces correct output: run script → read output → print summary
- [x] `full` mode adds narrative only (does not redo matching)
- [x] `SKILL-matching.md` and `SKILL-output-formats.md` both have reference-only headers
- [x] Token cost substantially reduced: no companion file reads, no manual matching steps
- [x] skill-lessons.yaml update step preserved in Step 3

## Execution notes

`SKILL.md` "How to run" section fully replaced with 4-step script-first flow (Pre-Step mode menu → Step 0 run script → Step 1 read output → Step 2 narrative for full mode only → Step 3 update lessons → Step 4 print summary). Description frontmatter updated to mention script-first flow and ~60% token reduction. Both `SKILL-matching.md` and `SKILL-output-formats.md` received the reference-only NOTE block at the top. `SKILL-full-mode.md` and `SKILL-lessons.md` unchanged — still consumed in full mode and Step 3 respectively.
