# RenewalLetter Roleplay Transcript

**Setup:** Two sub-agents conversing through an orchestrator relay. Neither agent
could read the full project context — this simulates a human who has only read the
user-facing handout.
- **Leo (USER):** retention specialist at ZenCover, non-technical, zero pipeline
  knowledge. Authored the `.docx` and filled the CSVs himself (python-docx / edits).
- **Facilitator (AGENT):** guided-authoring facilitator, **fenced to read ONLY**
  `AGENTS.md`, `.claude/skills/template-patterns/SKILL.md`,
  `.claude/skills/template-lite/SKILL.md` (plus its own run outputs). Ran the pipeline
  wrapper commands.
- **Orchestrator:** ferried every turn verbatim; independently re-verified the docx,
  CSVs, and final template at each artifact boundary.

**Date:** 2026-07-21
**Goal:** A reusable renewal confirmation letter (segment) — greeting, policy number,
renewal (cover-start) date, a per-gadget list, a warm thank-you, and a conditional
loyalty-discount line.

---

## STAGE 0 — Discovery

**AGENT:** Introduced the flow; asked what Leo wanted to build; noted renewal/policy
letters are `segment`.

**USER (Leo):** Renewal "you're all set for another year" letter. Greet by first name,
show policy number and renewal date up top, warm tone. "A bit more further down" held
back. Confirmed segment.

**AGENT:** Mapped the three top fields to bare markers — `{firstName}`,
`{policyNumber}`, `{expectedRenewalDate}` — and asked which date Leo actually meant.
Invited the rest.

**USER (Leo):** Clarified he means the day the renewed cover *starts*. Then revealed
the full picture: (1) list every insured gadget, one line each; (2) a thank-you that
reads differently by how long they've been a customer; (3) a discount line only when
they got a loyalty discount, never an awkward "£0". Flagged he wasn't sure tenure was
stored.

**AGENT:** Steered each part:
- Date → `{policyStartTime}` (first day of renewed cover).
- Gadget list → `[Item/]` … `[/Item]` loop around a one-row table.
- Discount → named conditional block `[[$discountNote]]`, wording + rule filled in a
  spreadsheet.
- **Tenure → honest reality check:** no "customer since" / tier / renewal-count field
  is visible in what ZenCover stores; branching needs a stored value. Recommended
  shipping one warm thank-you for everyone now, adding the tenure branch later once a
  field exists (a product-config change, out of scope for the document flow).

**USER (Leo):** Gadget row = item type + purchase date (drop serial/price). Accepted the
tenure recommendation — genuinely no backing field, so park it. Kept the discount
conditional. Approved the plan.

---

## STAGE 1 — Authoring

**AGENT:** Gave the exact doc content: greeting paragraphs with the three markers, a
table with the loop markers, `[[$discountNote]]`, a plain warm thank-you, sign-off.
Filename `RenewalLetter(segment).docx` → `workspace/inbox/`. **The spec placed
`[Item/]` / `[/Item]` on their own lines *around* the table.**

**USER (Leo):** Built the docx with python-docx exactly as specified and verified it on
disk. *(Orchestrator confirmed: 2-col table, markers as standalone paragraphs around
it.)*

**AGENT:** Read the docx back, confirmed markers, ran **intake**. All 5 fields resolved
with correct top picks; `variants.csv` had the discount block (2 rows) + the Item loop
(1 blank when-row).

---

## STAGE 2 — Human-fill

**AGENT:** Walked Leo through both files. Gave exact `variants.csv` values.

**USER (Leo):** Confirmed `path-review.csv` (5 paths correct, no edit). Filled
`variants.csv`: discountNote row → `when: discountAmount present`,
`text: and this year you saved £{discountAmount} with your loyalty discount`; fallback
row blank; Item row blank. *(Orchestrator confirmed the CSV contents.)*

---

## STAGE 3 — Finalize

**AGENT:** Ran finalize; it **paused (pass 2)** for `{discountAmount}` — the variant-text
leaf — added to `path-review.csv` with pick `policy.data.discountAmount`. Explained,
recommended leaving as-is, stopped.

**USER (Leo):** Eyeballed the new bottom row, confirmed `policy.data.discountAmount`, saved.

**AGENT:** Re-ran finalize to completion; ran the **done-gate: PASS, 49 checks.**

---

## STAGE 3.5 — Layout rework (the real finding)

**AGENT (reading back the generated template):** Flagged a layout defect the validator
does not catch: because the loop markers sat as standalone paragraphs *around the whole
table*, Leg 0 wrapped the entire `<table>` — header included — in `#foreach`, so the
"Gadget | Purchased" header repeats once per gadget. Recommended moving the markers
*inside* the table as their own rows (marker row → data row → marker row), which repeats
only the data row and keeps the header once.

*(Orchestrator confirmed the defect in the generated `.final.vm`: `#foreach` wrapped the
full table including the header row.)*

**USER (Leo):** Took the fix ("a header repeating three times would've looked amateur").
Rebuilt the docx as a 4-row table: header / `[Item/]` row / data row / `[/Item]` row.
*(Orchestrator confirmed 4 rows, no standalone marker paragraphs.)*

**AGENT:** Re-ran intake → finalize (filled CSVs preserved; the identical
`{discountAmount}` pass-2 pick auto-confirmed) → done-gate. Read back the loop region:
header now **outside** `#foreach`, only the data row between `#foreach`/`#end`, one
`<table>`.

---

## STAGE 4 — Validation (done-gate)

```
ran 49 checks on workspace/output/RenewalLetter(segment)/RenewalLetter(segment).final.vm
PASS — template matches the document and renderingData shape is correct.
```

**Orchestrator re-verification (independent):**
- Header row lines 56–59 **outside** the `#foreach` (line 61) → renders once. ✓
- Only the data row (`$item.data.itemTypeCode` / `$item.data.purchaseDate`) between
  `#foreach` and `#end` (67); one `</table>` (68). ✓
- Fields keyed correctly: `$data.account.data.firstName`, `$data.policy.policyNumber`,
  `$data.policy.policyStartTime`, loop over `$data.segment.items`, `${data.discountNote}`. ✓
- Shape grep: no bare `$data.data.` / bare system fields. ✓
- Validator: PASS, 49 checks. ✓

**AGENT (honest close):** Flagged that the guided flow does **not** generate the Leg 4
plugin, so `${data.discountNote}` renders blank until a plugin is generated + deployed
(a separate, config-dependent step) — parked, not pushed. This matches the documented
guided-flow scope fence (authoring only).

---

## Outcome

**PASS (49 checks), 1 rework loop (table layout).**

**Patterns exercised:**
- Bare `{leaf}` fields — segment system (`policyNumber`, `policyStartTime`), account
  (`firstName`), and per-item (`itemTypeCode`, `purchaseDate`).
- `[Item/]` … `[/Item]` loop over the items array — in **both** the wrong standalone-
  around-table form and the correct marker-row-inside-table form.
- Binary `[[$token]]` conditional block (`discountNote`) with a blank default fallback.
- Bare `{leaf}` inside variant text (`{discountAmount}` → Leg -1 pass-2 append + confirm).
- Tenure branch correctly **declined** — no backing field, parked as a config change.

**Protocol adherence:** CLEAN. Three wrapper commands only (intake / finalize /
validate), CSVs user-filled, no hand-edited artifacts, escape hatch not needed. The
facilitator honestly parked both the tenure branch (no field) and the plugin (config-
dependent) rather than overreaching — consistent with the guided-flow scope fence.

**Findings / friction:**
1. **Loop-around-a-table is a header-duplication trap the validator misses.** The
   facilitator's own Stage-1 spec placed `[Item/]`/`[/Item]` as standalone paragraphs
   around the table; Leg 0 wrapped the whole table (header included) in `#foreach`, so
   the header repeats per item. The done-gate **PASSes** (data is correct; layout is not
   checked). It was caught only by the facilitator eyeballing the generated `.final.vm`.
   **Root cause:** AGENTS.md / template-patterns present "standalone paragraph **or**
   table row" as equivalent placements for loop markers, without warning that for a
   *table* the standalone-around-table form repeats the header. Docs should state: to
   repeat only a table's data row, the markers **must** be their own rows *inside* the
   table. (CLAUDE.md already says this — "a marker row around a table's data row repeats
   just that row, keeping the header once" — but that nuance is not in the fenced
   handout the facilitator could read.)
2. Tenure discovery worked well — the facilitator, with no registry access, correctly
   reasoned it couldn't invent a stored field and recommended parking it. Good honest UX.
3. Pass-2 variant-text leaf detection + auto-carry on re-run worked exactly as
   documented (no re-fill, identical pick auto-confirmed).

**Files produced:**
- `workspace/inbox/RenewalLetter(segment).docx` — source (rebuilt with in-table markers)
- `workspace/output/RenewalLetter(segment)/RenewalLetter(segment).final.vm` — template ✓ PASS
- `workspace/action-needed/RenewalLetter(segment).path-review.csv` — 6 fields (5 + discountAmount)
- `workspace/action-needed/RenewalLetter(segment).variants.csv` — discount block + Item loop
