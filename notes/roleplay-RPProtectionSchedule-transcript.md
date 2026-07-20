# Roleplay transcript — RPProtectionSchedule(segment)

Marcus (ZenCover ops lead) wants a protection schedule: one row per covered item
(item type + purchase price) plus rows that only show when the item has
Breakdown coverage **and** labour is actually covered.

## Stage 0 — Discover

**Marcus:** "I need a schedule doc — list of what's covered, one line per item,
and then only show the labour bit if they actually get labour cover."

**Agent:** That's a loop (`[Item/]` … `[/Item]`) for the item rows, and for the
"only if labour cover" bit — since it depends on a *value* on the coverage
(not just whether they bought Breakdown at all), that's the `[Name?]`
per-item-value-region shape from the template-patterns skill (§2, shape 2),
not the plain coverage-presence shape. Concretely:

- Item row (inside `[Item/]`): `{itemTypeCode}` and `{purchasePrice}` — plain
  leaves, resolved in loop scope automatically.
- A `[LabourCoverRow?]` … `[/LabourCoverRow]` region *inside* the loop, right
  after the item row, holding the labour-only sentence + a coverage-hop field
  (`{item.Breakdown.data.manufacturerLabourGuaranteeEndDate}`).
- `LabourCoverRow` isn't a registry coverage name, so it needs a `variants.csv`
  `when` row — a per-item condition rooted at `item.Breakdown.data...`. You
  don't need to separately check "do they have Breakdown" — any field that
  hops through a coverage is auto-guarded per cell, so testing the labour
  value alone is enough.

Filename must end `(segment)` — save to
`workspace/inbox/RPProtectionSchedule(segment).docx`.

## Stage 1 — Author (with one read-back catch)

Marcus's v1 draft table: header row, `[Item]` opener (no trailing slash), item
row, `[LabourCoverRow?]` … `[/LabourCoverRow]`, `[/Item]`.

**Agent (read-back):** "Reading back what I see: a loop around the item row
opened with `[Item]` — that's missing the trailing slash that marks it as a
loop opener (`[Item/]`), so as written it'll be treated as literal text, not a
loop. Everything else — the `[LabourCoverRow?]`/`[/LabourCoverRow]` region,
the fields — looks right. Fix the opener and I'll re-read."

Marcus fixes it to `[Item/]`. Read-back now matches intent. Intake run:

```
python3 tools/run_demo.py intake "workspace/inbox/RPProtectionSchedule(segment).docx"
```

Output: 5 fields, 5/5 resolved (no ambiguity — `account.data.firstName/lastName`,
`item.data.itemTypeCode`, `item.data.purchasePrice`,
`item.Breakdown.data.manufacturerLabourGuaranteeEndDate`); variants.csv has two
placeholders: `Item` (loop, when-only) and `LabourCoverRow` (region, when-only).

## Stage 2 — Human fill (with a caught mistake)

`path-review.csv` came back fully pre-resolved (no ambiguous leaves) — nothing
for Marcus to fix there.

`variants.csv` — Marcus's first pass at `LabourCoverRow`:

```
LabourCoverRow,Breakdown.data.labourCovered != null,
```

**Agent:** "Two things on that row. First, `!= null` isn't valid DSL — use
`present`/`absent` for null checks. But actually neither is quite what you
want here: `labourCovered` is a string field with options `'true'`/`'false'`
(it's not a real presence flag, it's a yes/no answer), so what you want is a
*value* check, not a null check. Second — this region sits inside the
`[Item/]` loop, so the condition has to root at the loop iterator: `item.`,
not the bare `Breakdown...`. Put it as:

```
item.Breakdown.data.labourCovered == "true"
```

Note the quotes — `labourCovered` is a string enum ('true'/'false'), not a
real boolean, so a bare `== true` would be comparing a string field to a
boolean literal."

Marcus updates the row:

```
LabourCoverRow,"item.Breakdown.data.labourCovered == ""true""",
```

`Item`'s `when` stays blank (always render — correct, it's an unconditional
loop).

## Stage 3 — Finalize

```
python3 tools/run_demo.py finalize "RPProtectionSchedule(segment)"
```

Ran clean end to end: path-map apply (5/5 leaves rewritten) → Leg 0 ingest →
parse variants.csv → Leg 2+3 → 45-check validate.

## Stage 4 — Done-gate

```
python3 tools/validate_demo.py "RPProtectionSchedule(segment)"
```

```
ran 45 checks on workspace/output/RPProtectionSchedule(segment)/RPProtectionSchedule(segment).final.vm
PASS — template matches the document and renderingData shape is correct.
```

**PASS on the first finalize attempt** (the docx typo and the CSV condition
mistake were both caught and fixed before finalize ran, per the Stage-1/Stage-2
"free to iterate before the pipeline runs" design).

Generated template excerpt (`RPProtectionSchedule(segment).final.vm`):

```
#foreach ($item in $data.segment.items)
...
<p class="paragraph-Standard">$item.data.itemTypeCode</p>
...
<p class="paragraph-Standard">$item.data.purchasePrice</p>
...
#if(($item.Breakdown && $item.Breakdown.data && $item.Breakdown.data.labourCovered == "true"))
...
<p class="paragraph-Standard">#if($item.Breakdown)$item.Breakdown.data.manufacturerLabourGuaranteeEndDate#end</p>
```

The per-item value condition compiled correctly (null-safe `&&` chain, string
comparison preserved), and the coverage-hop field inside the region got its
own independent `#if($item.Breakdown)` cell guard — exactly as the
template-patterns skill promised, with nothing extra for Marcus to write.
