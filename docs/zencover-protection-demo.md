# The ZenCover Protection Letter — a back-to-front walkthrough

**Audience:** anyone demoing the pipeline end to end on a real segment document.
This is the exact path we ran for `ZenCoverProtectionLetter(segment).docx` — a
Word letter with plain `{field}` markers and two conditional notices — turned into
a live-rendered template **without a plugin**. The `tools/zencover_demo.py` UI
walks these same eight steps, each one running the real pipeline script.

> The document is a `(segment)` letter: system fields resolve under `$data.policy.*`,
> custom fields + the items loop under `$data.segment.*`. That split is the whole
> reason renderingData shape matters — the stepper's last checks grep for it.

---

## The document

`ZenCoverProtectionLetter(segment).docx` — a protection-confirmation letter:

- **Plain body fields** (`{firstName}`, `{policyNumber}`, `{contractTermEndDate}`, …)
  and an items table wrapped in `[Item]`…`[/Item]` loop markers
  (`{itemTypeCode}`, `{purchaseDate}`, `{purchasePrice}`, `{serialNumber}`).
- **Two conditional notices** authored as named `[[$token]]` variant blocks (the
  repo-preferred form — a named token, not an opaque `[[sentence]]`):
  - `[[$discountNote]]` → shown text "you have a discount"
  - `[[$coolingOffNote]]` → shown text "you have a cooling off period of
    {coolingOffPeriod} days" — the `{coolingOffPeriod}` leaf lives **only inside that
    notice text**, which is why it needs a Leg -1 pass 2.

The scan emits a **2-row stub per token** — a conditioned row (fill `when` + the shown
text) plus a blank default row (matches nothing → shows nothing). Ten plain fields,
one variant-text leaf, two conditional blocks.

---

## The eight steps

### 1. Intake (with suggestions)

```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE intake \
  input=workspace/inbox/ZenCoverProtectionLetter(segment).docx \
  registry=registry/path-registry.yaml output=workspace/output"
```

Runs Leg -1 (suggest) + Leg 0 (scan) back to back → the two customer-fill files in
`workspace/action-needed/`:

- `…path-review.csv` — the ten plain fields, `suggested`/`final` **pre-filled** with
  the registry's top pick (accept or override).
- `…variants.csv` — the two conditional blocks, `when` blank, `text` pre-filled.

### 2. Fill the conditions + notice text

The only genuine hand-fill. Each `[[$token]]` block's **conditioned row** gets a `when`
(condition DSL — `present`/`absent`, document-scoped `policy.*` accessors for a segment
doc) and its **shown text**; the blank default row is left alone (shows nothing):

| placeholder | when | text |
|---|---|---|
| `discountNote` | `policy.data.discountAmount present` | you have a discount |
| `discountNote` | *(blank default)* | |
| `coolingOffNote` | `policy.data.coolingOffPeriod present` | you have a cooling off period of {coolingOffPeriod} days |
| `coolingOffNote` | *(blank default)* | |

### 3. Fold in the variant-text leaf (Leg -1 pass 2)

`{coolingOffPeriod}` sits inside the notice text — pass 1 (the body scan) never saw it,
and it only exists now that step 2 filled the text. Point Leg -1 at the filled
variants.csv to append it, with a registry suggestion:

```
python3 -m velocity_converter.legminus1_resolve_paths \
  --input workspace/inbox/ZenCoverProtectionLetter(segment).docx \
  --registry registry/path-registry.yaml --output-dir workspace/output \
  --variants-csv "workspace/action-needed/ZenCoverProtectionLetter(segment).variants.csv"
```

`{coolingOffPeriod}` is appended to `path-review.csv` → `policy.data.coolingOffPeriod`.

### 4. Resolve & ingest

```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE legminus1_apply \
  review=workspace/action-needed/ZenCoverProtectionLetter(segment).path-review.csv"
python3 -m velocity_converter.leg0_ingest \
  --input workspace/inbox/ZenCoverProtectionLetter(segment).docx \
  --path-map workspace/output/.../ZenCoverProtectionLetter(segment).path-map.yaml \
  --output-dir workspace/output/ZenCoverProtectionLetter(segment)
```

Apply folds the finals into the `path-map.yaml`; the full ingest bakes full accessors
into the `.mapping.yaml`. The filled `variants.csv` is snapshotted/restored across the
re-ingest so answers aren't clobbered.

### 5. Parse the variants CSV → conditional registry

```
python3 -m velocity_converter.leg0_ingest \
  --parse-variants-csv "workspace/action-needed/ZenCoverProtectionLetter(segment).variants.csv" \
  --output-dir workspace/output/ZenCoverProtectionLetter(segment)
```

### 6. Generate the template (Leg 2+3, no plugin)

```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg2+leg3 \
  mapping=workspace/output/.../ZenCoverProtectionLetter(segment).mapping.yaml \
  registry=registry/path-registry.yaml"
```

Writes `…final.vm`. System field → `$data.policy.policyNumber`; segment custom →
`$data.segment.data.*`; items loop → `#foreach ($item in $data.segment.items)`. The two
notices come out as `${data.discountNote}` / `${data.coolingOffNote}` — keys a **plugin**
would fill.

### 7. Inline the conditional text

No plugin in this demo, so those keys would render blank. Rewrite them into real
`#if` blocks so the template is self-sufficient:

```velocity
#if($data.segment.data.discountAmount)<p>you have a discount</p>#end
#if($data.segment.data.coolingOffPeriod)<p>you have a cooling off period of $data.segment.data.coolingOffPeriod days</p>#end
```

> This edits the generated `.final.vm` in place. Re-running Leg 3 resets it to the
> `${data.…}` form — the permanent home for that text is a Leg 4 plugin.

### 8. Render preview (live tenant)

```
python3 -m velocity_converter.render_preview \
  --template workspace/output/.../ZenCoverProtectionLetter(segment).final.vm \
  --reference-type segment --reference-locator <AI_DOCUMENTS_REFERENCE_SEGMENT> \
  --out workspace/output/.../ZenCoverProtectionLetter(segment).preview.pdf --open
```

Renders against the **already-deployed** SnapshotPlugin (it supplies `$data`); needs
`.env.ai-documents` at the repo root. PDF pops open in the OS viewer.

---

## Done-gate

Before calling it done, grep the `.final.vm`: **no** bare `$data.data.` and **no** bare
`$data.<systemField>`. Every field under `$data.policy` / `$data.segment` / `$data.account`,
every loop `#foreach ($item in $data.segment.items)`. If a bare path slips through, the
resolution is wrong — fix the data_source, don't ship it.
