# Roleplay transcript — RPCoverageMatrix(segment)

Tomás, an underwriting analyst at ZenCover, wants a **coverage matrix document**:
a table with one row per coverage each item carries, showing item type, coverage
name, and labour coverage flag, plus a closing paragraph that appears only when
Breakdown coverage is present on any item.

## Stage 0 — Discover

**Tomás:** "I need a coverage matrix. Show me what coverages each item has, and then a note about Breakdown at the end."

**Agent:** That's a `[Coverage/]` plugin-list loop (one row per item × coverage
present, iterating the plugin-built `$data.coverages`) and a doc-level `[Breakdown?]`
coverage-presence region. The coverage loop fields are declared in the registry
(name, displayName, itemTypeCode, labourCovered, partsCovered) — pick the ones
you need. For the Breakdown closing paragraph, a doc-level `[Breakdown?]` region
renders automatically when any item carries Breakdown; you don't need to fill
anything in the variants.csv.

Filename must end `(segment)`.

## Stage 1 — Author (with two read-back catches)

Tomás's v1 draft:
- Table header: Item, Coverage Type, Premium
- `[Coverage/]` loop in the table with `{coverage.itemTypeCode}`, `{coverage.displayName}`, `{coverage.premium}`
- `[/Coverage]` closer
- Closing paragraph: `[Breakdown]` (no `?`) … text … `[/Breakdown]`

**Agent (read-back):** Two issues:

1. **`{coverage.premium}`** — the Coverage loop doesn't have a `premium` field. Available
   fields are: `name`, `displayName`, `itemTypeCode`, `labourCovered`, `partsCovered`.
   Choose one of those.

2. **`[Breakdown]` marker** — missing the `?` that marks it as a coverage-presence
   region. Should be `[Breakdown?]` to render only when Breakdown is present.

Tomás fixes both. Read-back now matches intent:
- Table: Item, Coverage Type, Labour Covered
- `[Coverage/]` with correct fields
- `[Breakdown?]` … text … `[/Breakdown]`

## Stage 2 — Path-fill + Discover the Limitation

Tomás runs intake:

```bash
python3 tools/run_demo.py intake "workspace/inbox/RPCoverageMatrix(segment).docx"
```

Output: 5 fields (account.data.firstName, account.data.lastName, coverage.itemTypeCode,
coverage.displayName, coverage.labourCovered). The account fields are resolved; the
coverage fields are unmatched (Leg -1 doesn't know about plugin-lists).

**Agent (CSV critique):** The coverage fields are tricky. Leg -1 doesn't understand
plugin-list fields, so they come back unmatched. You have two options:

1. **Escape hatch to CLAUDE.md** — run the raw pipeline (Leg 0 directly, skipping Leg -1's
   path-review), which knows about plugin-lists.
2. **Workaround** — leave the coverage field finals blank, see if Leg 0 auto-resolves them.

Tomás tries the workaround first (leave finals blank). Re-running finalize:

```bash
python3 tools/run_demo.py finalize "RPCoverageMatrix(segment)"
```

**Result:** Rejected — finalize requires every path-review field to have a `final` value.

**Agent:** The workaround didn't work. The guided flow's path-review step is a
**hard blocker for plugin-lists**. This is a known limitation: Leg -1 doesn't
recognize plugin-list fields, so it can't resolve them, and finalize won't proceed
without them.

Per AGENTS.md, this is an escape-hatch moment. I'm switching to the raw pipeline
(CLAUDE.md mode) to finish your document. The three wrapper commands don't support
plugin-lists; the raw legs do.

## Stage 3 — Finalize via CLAUDE.md (raw pipeline)

**Agent:** Running Leg 0 directly (without path-review), then Leg 2+3:

```bash
python3 -m velocity_converter.leg0_ingest --input workspace/inbox/RPCoverageMatrix(segment).docx --output-dir workspace/output/RPCoverageMatrix(segment)
python3 -m velocity_converter.agent --yes 'RUN_PIPELINE leg2+leg3 mapping=workspace/output/RPCoverageMatrix(segment)/RPCoverageMatrix(segment).mapping.yaml registry=registry/path-registry.yaml output=workspace/output'
```

Both completed without error. The mapping was auto-populated by Leg 2 with the
plugin-list field spec from the registry.

## Stage 4 — Done-gate

```bash
python3 tools/validate_demo.py "RPCoverageMatrix(segment)"
```

```
ran 45 checks on workspace/output/RPCoverageMatrix(segment)/RPCoverageMatrix(segment).final.vm
PASS — template matches the document and renderingData shape is correct.
```

**PASS on the escape-hatch path** (the guided flow hit a limitation, then switched
to raw pipeline, and validation passed).

Generated template excerpt (`RPCoverageMatrix(segment).final.vm`):

```velocity
<p class="paragraph-Standard">Dear $data.account.data.firstName $data.account.data.lastName,</p>
...
#foreach ($coverage in $data.coverages)
<tr>
<p class="paragraph-Standard">$!{coverage.itemTypeCode}</p>
<p class="paragraph-Standard">$!{coverage.displayName}</p>
<p class="paragraph-Standard">$!{coverage.labourCovered}</p>
</tr>
#end
...
#if($data.Breakdown)
<p class="paragraph-Standard">Your policy includes Breakdown coverage, which protects against mechanical and electrical failures.</p>
#end
```

All renderingData shape rules satisfied:
- ✓ `$data.account.data.firstName` — account key used
- ✓ `#foreach ($coverage in $data.coverages)` — plugin-list loop (the generated
  plugin builds this top-level key; correct syntax)
- ✓ `#if($data.Breakdown)` — doc-level coverage-presence region (automatic Boolean,
  true when any item carries Breakdown; no customer fill needed)

## Key findings

1. **Guided flow doesn't support plugin-lists** — the three wrapper commands encode
   a Leg -1 → Leg 0 → Leg 2+3 order. Leg -1 can't resolve plugin-list fields
   (e.g. `{coverage.itemTypeCode}`), so finalize blocks on blank finals. This is a
   **design limitation**, not a bug — plugin-lists are "advanced" per AGENTS.md.

2. **Escape hatch works** — switching to the raw pipeline (Leg 0 directly without
   path-review, then Leg 2+3) solves it. The raw pipeline recognizes plugin-lists
   from the registry spec and resolves them automatically.

3. **Doc-level coverage-presence regions are automatic** — `[Breakdown?]` at document
   level requires no customer fill in variants.csv. The pipeline detects it,
   classifies it as "registry coverage, document scope," and Leg 4 generates a Boolean
   (true when any item carries the coverage). This behavior is documented and working.

4. **Template-patterns skill should be invoked at Stage 0** — when a user says
   "row per coverage," the agent should immediately invoke template-patterns
   to explain `[Coverage/]` and its path-review implications. Skipping this led
   to discovering the limitation mid-flow.

## Rework summary

- Read-back: 2 catches (field name + marker syntax), fixed before intake
- Escape hatch: 1 (path-review limitation → raw pipeline)
- Validator: 1 pass on first finalize attempt (after escape)
- Total rework loops: 1 (Stage 1 read-back)
