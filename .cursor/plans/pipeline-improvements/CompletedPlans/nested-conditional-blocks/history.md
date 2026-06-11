# History — Nested Conditional Block Extraction

Append-only. One entry per work session.

---

## 2026-06-05 — Plan created + fully implemented

### Context

`COND_BLOCK_RE = r'\[([^\[\]\n]{4,})\]'` excluded nested brackets by design — the `[^\[\]]`
char class meant any `[outer [inner] text]` pattern silently failed: only the innermost `[inner]`
matched; the outer wrapper was never extracted. Real insurance rider documents contain multi-level
nested optional clauses (e.g. `[, and (2) such Insured has not, [within the last [2-10] years] prior to...]`).

This plan was created as a direct follow-on to the completed `conditional-blocks` plan, which
established the single-pass extraction and `$doc.condN` substitution mechanism.

### Key insight

Because `COND_BLOCK_RE` already matches only the innermost brackets (by design), wrapping the
existing body in a `while True` loop is sufficient — each iteration peels one nesting layer,
innermost-first. After all passes, a `_link_cond_parents()` post-processing step scans each
block's `source_text` for `$doc.condN` refs left by prior passes to wire parent/child
relationships and compute depth.

### Summary

**Leg 1 changes (`convert.py`):**
- `extract_conditional_blocks()` — replaced single `for` loop with `while True` / `changed`
  flag pattern; terminates when a full pass finds no new matches. Each appended block now
  carries `parent_id: None` and `depth: 0` (defaults overwritten by `_link_cond_parents`).
- Added `_COND_REF_RE = re.compile(r'\$doc\.cond(\d+)')` module-level constant.
- Added `_link_cond_parents(blocks)` — scans each block's `source_text` for `$doc.condN`
  refs to assign `parent_id`, then walks the parent chain to compute `depth`. Called at the
  end of `extract_conditional_blocks()`.
- `write_conditional_registry()` — extended CSV header and rows to include `parent_id` and
  `depth` columns (between `source_text` and `conditions`).
- `write_conditional_ref_html()` — changed from annotating original HTML to annotating
  `.vm` text (original HTML doesn't contain `$doc.condN` refs, so depth ≥ 1 blocks would
  silently fail to annotate). Signature changed from `(original_html, ...)` to `(vm_text, ...)`.
  Replaces tokens in reverse-ID order to avoid `cond1` matching inside `cond10`. Wraps output
  in `<html><body><pre>...</pre></body></html>`. Adds `title="id=N depth=D"` to `<sup>`.
- Call site in `convert()` updated: `html` → `vm_text` (already in scope).

**Leg 4 changes (`leg4_generate_plugin.py`):**
- `load_conditional_registry()` — reads `parent_id` and `depth` from CSV rows; handles empty
  string gracefully (returns `None`/`0`).
- `render_conditional_puts()` — TODO stubs for child blocks now include
  `— child of condN, guard inside parent if-block` note in the comment.
- `write_report()` conditional blocks table — header extended to
  `| id | depth | parent_id | source_text | conditions | status |`; rows include the new columns.

### Files touched
- `.cursor/skills/html-to-velocity/scripts/convert.py` (T1–T5)
- `scripts/leg4_generate_plugin.py` (T6–T8)

### Verification

```bash
# Step 1 — flat regression (parent_id/depth columns empty/0)
python3 scripts/agent.py --yes "RUN_PIPELINE leg1 input=samples/input/Simple-form(quote).html output=samples/output"
# → conditional-registry.csv: new columns present, blank for flat doc
# → conditional-ref.html: renders .vm with <sup title="id=1 depth=0">1</sup>

# Step 2 — 3-level nested doc
# Created samples/input/nested-test(quote).html:
#   <p>[outer [middle [inner text] rest of middle] rest of outer]</p>
python3 scripts/agent.py --yes "RUN_PIPELINE leg1+leg2 input=samples/input/nested-test(quote).html registry=registry/path-registry.yaml output=samples/output"
# → CSV:
#   1,inner text,2,2,,,
#   2,middle $doc.cond1 rest of middle,3,1,,,
#   3,outer $doc.cond2 rest of outer,,0,,,

# Step 3 — Leg 4 TODO stubs include parent notes
python3 scripts/leg4_generate_plugin.py --suggested "samples/output/nested-test(quote)/nested-test(quote).suggested.yaml"
# → Java: cond1 TODO: "— child of cond2, guard inside parent if-block"
#         cond2 TODO: "— child of cond3, guard inside parent if-block"
#         cond3 TODO: no parent note (root block)
# → plugin-report.md: depth/parent_id columns in conditional blocks table
```

### Open items / next
- No automated test for the N-pass loop or `_link_cond_parents`; covered only by the
  end-to-end verification above.
- `write_conditional_ref_html` now shows `$doc.condN` refs inside parent blocks' `<sup>` titles
  only as plain text — a future enhancement could make child refs clickable anchors.
- Leg 4 Java rendering doesn't yet generate nested `if` blocks (parent wraps child); that
  requires human-filled conditions in the CSV first, then a separate rendering pass.

---

<!-- Template for future entries:

## YYYY-MM-DD — Short title

### Summary
- bullet

### Files touched
- path

### Verification
- command

-->
