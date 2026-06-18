# Improvement note — retire the legacy `--parse-conditional-form` path

**Status:** idea — not started (2026-06-18)
**Owner:** Josh
**Effort:** small (deletion, low risk — suite stays green to prove it)
**Context:** the variants-only migration (shipped 2026-06-17) made `variants.csv` +
`conditional-blocks.yaml` the single conditional-text flow. The old
`conditional-form.md` flow was *kept behind a flag* for in-flight forms. There are no
in-flight forms anymore — this is now pure dead weight.

## What's still there

| Location | What |
|---|---|
| `leg0_ingest.py:943` | `parse_conditional_form()` — the legacy parser |
| `leg0_ingest.py:1284` | `--parse-conditional-form` CLI arg |
| `leg0_ingest.py:1351` | dispatch branch that calls it |
| `leg0_ingest.py:15-35` | module docstring describing the legacy mode |
| `leg0_ingest.py:1013` | `.conditional-form.md` stem-stripping |
| `models.py:400` | docstring reference to the legacy parser |
| `CLAUDE.md` (several) | "Legacy:" callouts in the Leg 0 sections |

## The work

1. Delete `parse_conditional_form` + the CLI arg + the dispatch branch.
2. Strip the legacy mentions from the `leg0_ingest.py` docstrings and `models.py`.
3. Remove the "Legacy:" lines from CLAUDE.md (and AGENTS.md if mirrored).
4. Grep tests for any deliberate legacy-path guard — if one exists, delete it (the
   handoff note that scoped the migration said `parse_conditional_form` "may remain
   as the documented legacy path"; that allowance expires here).
5. Run `pytest tests/regression/ -q` + `run_test_pipeline.py --auto` — both must stay
   green, which *is* the proof the path was dead.

## Why first

Smallest, safest win, and it shrinks `leg0_ingest.py` (1,461 lines) before any of the
heavier decomposition work — see [decompose-clonker-legs](decompose-clonker-legs.md).
Do this before splitting Leg 0 so we don't carve up code we're about to delete.

## Risk

Near zero. If anything still calls the legacy flag, the suite or a grep catches it.
Reversible via git.
