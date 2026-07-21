---
name: template-patterns
description: Route a template-authoring goal to the correct marker/method during the guided authoring flow (AGENTS.md). Use when the user wants — a row per coverage ("show each coverage with its limit"), rows/sections that appear only when a coverage is present ("only if they bought Breakdown"), a different paragraph per state (N-way), a conditional inside a conditional, a field mentioned inside conditional wording, an optional field, or to copy a table from another Word document. Covers [Name?] regions, [Coverage/] plugin-lists, nested [[$label]], variant-text fields, occurrence symbols, and splice_docx_table.
---

# Template patterns — goal → marker router

You are in the guided authoring flow (AGENTS.md rules still apply: user types the
markers in Word, user fills the CSVs, done = validate PASS). This skill covers
the patterns beyond the basic cheat-sheet. Route by goal:

| User goal | Pattern | Section |
|---|---|---|
| "a table row per covered item" | `[Item/]` … `[/Item]` loop — **markers as rows *inside* the table, not standalone around it, or the header repeats per item** | (basic — cheat-sheet) |
| "a row per coverage, with its limit/terms" | `[Coverage/]` plugin-list loop | §1 |
| "show these rows only if the coverage is present" | `[Name?]` … `[/Name]` region | §2 |
| "different paragraph per state / N options" | N-way `[[$token]]` block | §3 |
| "mention a field inside the conditional wording" | bare `{leaf}` in the `text` cell | §4 |
| "a conditional inside a conditional" | nested `[[$label]]` in the `text` cell | §5 |
| "this field might be empty / is optional" | occurrence symbols `{$f}` `{+f}` `{*f}` | §6 |
| "copy this table from another document" | `tools/splice_docx_table.py` | §7 |

## §1 — Row per coverage: `[Coverage/]` plugin-list loop

No real collection of coverages exists on any entity — the plugin builds one.
The user wraps the table's data row in `[Coverage/]` … `[/Coverage]` (same
placement rules as `[Item/]`) and — **exception to the plain-leaves rule** —
writes fields dotted on the iterator: `{coverage.name}`, `{coverage.limit}`.
The registry declares the entry fields (iterable `kind: plugin_list`); Leg 2
resolves them; the template iterates `$data.coverages` (its own top-level key —
valid, the generated plugin puts it).

- One row renders per (item × coverage present).
- Known limit: per-coverage **premium/charge amounts are not supported** — steer
  the user away from a premium column.
- The `.final.vm` validates through the normal `finalize` gate, but **live
  rendering needs the Leg 4 plugin** generated and deployed (the demo flow skips
  Leg 4 by default — offer it only if they want a live preview).

## §2 — Conditional rows: `[Name?]` … `[/Name]` regions

`[[$token]]` text lives in CSV cells, so it can never carry table rows. A
`[Name?]` region keeps rows/paragraphs in the document and guards them. Marker
placement: standalone paragraph or its own table row (other cells empty). Four
shapes, resolved automatically by where the marker sits and what `Name` is:

1. **Inside an `[Item/]` loop, `Name` = a coverage** (e.g. `[AccidentalDamage?]`
   rows inside `[Item/]`) → per-item coverage presence. **Nothing to fill** — no
   variants.csv row, no plugin key.
2. **Inside a loop, any other `Name`** → per-item *value* condition: a
   `when`-only variants.csv row whose paths must root at the iterator
   (`item.Breakdown.data.labourCovered == "true"`; blank = always). This is the
   one place `item.*` is legal in a condition.
3. **Document level, `Name` = a coverage** → renders when **any** item carries
   the coverage. Nothing to fill.
4. **Document level, any other `Name`** → a plain `when`-only variants.csv row,
   like a loop's (blank = always).

Fields that hop through a coverage (`{item.Breakdown.labourRate}`-style) are
auto-guarded per cell by the pipeline — the user doesn't add anything.

## §3 — N-way blocks

One `[[$token]]` in the doc, **many conditioned rows** in variants.csv (first
match wins) + exactly one default row last. Never have the user create 50
separate tokens for a per-state paragraph — one token, one row per state.
Unsupported edge: N-way variants that each contain their *own loop* — loops
can't live in a CSV text cell.

## §4 — Fields inside variant text

A bare `{leaf}` typed in a variants.csv `text` cell is fine. `finalize` folds
any net-new leaf into path-review.csv with registry suggestions and **stops**
for the user to confirm the new `final` rows, then they re-run finalize. Don't
hand-run any leg for this — the wrapper does it.

## §5 — Nested conditionals

A variant's `text` cell may embed `[[$other]]`, where `other` is another row in
the same variants.csv — no document marker needed for the nested label. Rules
enforced at parse: referent must exist, no self-reference or cycles, and the
nested label must share the referrer's scope (or be unconditional).

## §6 — Occurrence symbols

`{field}` required (default) · `{$field}` optional · `{+field}` one-or-more ·
`{*field}` zero-or-more. Required/one-or-more get hard null-guards in the
generated plugin (missing data = render error by design). If a blank render is
acceptable, mark it `{$field}`; if the document is meaningless without it, leave
it required.

## §7 — Copying a table between Word documents

Never copy table XML by hand — the host document's defaults silently restyle it
(row heights double, fonts swap). If Word-native copy-paste isn't enough (or
you're asked to do it), use the splicer, then **re-run intake**:

```
python3 tools/splice_docx_table.py --source <src.docx> --table-contains "<unique text>" \
  --target <dst.docx> [--before-text "<anchor>"] [--heading "<bold title>"]
```

Rejects images/lists/hyperlinks/footnotes; modifies the target in place (git is
the undo).
