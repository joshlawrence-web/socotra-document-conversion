# Demo runbook — build a back-to-front demo without tripping

**Audience:** an agent asked to "create a demo" / "run a doc through end to end."
Goal: a `.docx` → a **validated** `.final.vm` (no plugin). Two scripts do the
orchestration and the done-gate so you cannot misorder the legs or declare
success on a template that renders to nothing.

> **Do not improvise the leg sequence or hand-write a validator.** Use the two
> scripts below. They exist because each of these steps was gotten wrong before.

---

## The three commands

```bash
# 1. Author or place a source doc in workspace/inbox/<stem>(segment|quote).docx
#    (see "Authoring a clean source doc" below). Then:
python3 tools/run_demo.py intake "workspace/inbox/<stem>.docx"

# 2.  HUMAN-JUDGEMENT STEP — fill the two files in workspace/action-needed/:
#       <stem>.path-review.csv  → confirm each `final` accessor (already pre-filled
#                                 with the registry's top pick; fix if wrong)
#       <stem>.variants.csv     → write each `when` (condition DSL — see
#                                 docs/writing-conditions.md). Segment docs use
#                                 policy.* accessors; quote docs use quote.*.

# 3. Finalize — runs apply → ingest → parse → Leg 2+3 → VALIDATE, in order:
python3 tools/run_demo.py finalize "<stem>"
```

`finalize` ends by running `tools/validate_demo.py`. **PASS = done. MISMATCH =
not done** — fix the cause and re-run `finalize`. Never hand-declare success.

You can run the gate alone any time:
```bash
python3 tools/validate_demo.py "<stem>"
```

---

## The traps this kit removes (why it exists)

1. **renderingData shape** — the #1 trap. The registry stores paths *root-relative*
   (`$data.policyNumber`, `$data.data.x`); the template needs the entity key the
   plugin `.put()`s. A **segment** doc splits across two keys — system →
   `$data.policy.*`, custom → `$data.segment.data.*`, loop → `$data.segment.items`.
   A **quote** doc puts everything on `$data.quote.*`. The gate fails on any bare
   `$data.data.*` or `$data.<systemField>`. Full rule:
   [RenderingDataConfigRelated.md](RenderingDataConfigRelated.md) § "rendering-root entity key".

2. **Leg order** — the correct sequence is apply Leg -1 → Leg 0 ingest **with the
   path-map** → parse the variants CSV → Leg 2+3. Skipping the path-map or the
   parse-variants step leaves `$doc.condN` / wrong paths. `finalize` enforces it.

3. **variants.csv preservation** — re-running Leg 0 ingest keeps your filled
   `variants.csv` (it warns, doesn't clobber). Don't re-fill it after ingest.

4. **No done-gate** — previously success was declared by eyeballing the `.vm`,
   which missed the renderingData bug. `validate_demo.py` is now mandatory and
   checks doc-coverage + shape + leftover markers.

5. **No plugin needed** — a demo template doesn't need Leg 4. Conditional prose
   lives in the `variants.csv` / `conditional-registry.yaml`; the `.vm` only
   references `${data.condN}`. Add Leg 4 only if explicitly asked.

---

## Authoring a clean source doc

To make a doc that passes cleanly (the demo's step 1), mirror
`workspace/inbox/ZenCoverProtectionLetter(segment).docx` (built by a small
python-docx script — copy that pattern):

- **Filename suffix decides the rendering root:** `(segment)` or `(quote)`. Required.
- **Plain fields** = bare leaves so Leg -1 does real work: `{firstName}`,
  `{policyNumber}`, `{contractTermEndDate}`. They resolve to registry accessors.
- **A loop:** wrap a table's data row in `[Item]` / `[/Item]` marker rows; put bare
  leaves inside (`{itemTypeCode}`, `{purchasePrice}`) — they resolve to `$item.data.*`.
- **Conditionals:** wrap whole sentences in `[[ ... ]]` (binary show/hide). Keep the
  condition document-scoped (policy/quote/account fields, never per-item `item.*`).
- **Stay clean:** avoid charges (`$data.charges.*`) and DataFetcher totals in the
  body unless needed — they have known Leg-2 resolution quirks. Account, policy
  system + custom fields, and an item loop are the reliable demo surface.

Then: `python3 tools/run_demo.py intake "..."` and follow the prompts.
