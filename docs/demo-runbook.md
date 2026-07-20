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
   parse-variants step leaves `$doc.<token>` / wrong paths. `finalize` enforces it.

3. **variants.csv preservation** — re-running Leg 0 ingest keeps your filled
   `variants.csv` (it warns, doesn't clobber). Don't re-fill it after ingest.

4. **No done-gate** — previously success was declared by eyeballing the `.vm`,
   which missed the renderingData bug. `validate_demo.py` is now mandatory and
   checks doc-coverage + shape + leftover markers.

5. **No plugin needed** — a demo template doesn't need Leg 4. Conditional prose
   lives in the `variants.csv` / `conditional-registry.yaml`; the `.vm` only
   references `${data.<token>}`. Add Leg 4 only if explicitly asked.

---

## Authoring a clean source doc

To make a doc that passes cleanly (the demo's step 1), mirror
`workspace/inbox/ZenCoverProtectionLetter(segment).docx` (built by a small
python-docx script — copy that pattern):

- **Filename suffix decides the rendering root:** `(segment)` or `(quote)`. Required.
- **Plain fields** = bare leaves so Leg -1 does real work: `{firstName}`,
  `{policyNumber}`, `{contractTermEndDate}`. They resolve to registry accessors.
- **A loop:** wrap a table's data row in `[Item/]` (opener, trailing slash) / `[/Item]`
  (closer) marker rows; put bare leaves inside (`{itemTypeCode}`, `{purchasePrice}`) —
  they resolve to `$item.data.*`. Leave the loop's `when` row blank in `variants.csv`
  for a plain, always-shown loop.
- **Conditionals:** every conditional block **must** be a named token —
  `[[$discountNote]]`. A bare `[[whole sentence]]` block is now a **hard error** at
  Leg 0 (it lists every offender and writes nothing) — there's no more auto-naming to
  fall back on. The wording lives in the `variants.csv` `text` column (col 3), and the
  block's name shows up identically in the doc *and* the `variants.csv` `placeholder`
  column, so the two line up at a glance. Keep the condition document-scoped
  (policy/quote/account fields, never per-item `item.*`). A bare leaf inside a variant's
  `text` (e.g. `{discountAmount}`) is pulled into `path-review.csv` by Leg -1's Pass 2
  and resolved there — author it as a bare leaf, not a full accessor.
- **Stay clean:** avoid charges (`$data.charges.*`) and DataFetcher totals in the
  body unless needed — they have known Leg-2 resolution quirks. Account, policy
  system + custom fields, and an item loop are the reliable demo surface.

Then: `python3 tools/run_demo.py intake "..."` and follow the prompts.

## Preview it against a live tenant — where each request variable comes from

After `finalize` writes the `.final.vm`, render it with
`python3 -m velocity_converter.render_preview`. The request is
`POST {API_URL}document/{tenant}/documents/render`, multipart/form-data. This is the
"where do I get X" lookup for every variable that request needs:

| Request variable | Where to get it |
|---|---|
| API base URL | `AI_DOCUMENTS_API_URL` in `.env.ai-documents` (repo root) |
| Tenant locator (URL path) | `AI_DOCUMENTS_TENANT_LOCATOR` in `.env.ai-documents` |
| `Authorization: Bearer` token | `AI_DOCUMENTS_PAT` in `.env.ai-documents` — PAT/JWT with the `documents` group's `render-external` permission |
| `referenceType` (`--reference-type`) | the stem suffix: `(segment)` → `segment`, `(quote)` → `quote` |
| `referenceLocator` (`--reference-locator`) | `AI_DOCUMENTS_REFERENCE_<TYPE>` in `.env.ai-documents` (e.g. `_SEGMENT`, `_QUOTE`) — the live entity to render against |
| `template` (file part) | `--template` → `workspace/output/<stem>/<stem>.final.vm` |
| `templateFormat` | fixed `velocity` (default) |
| `documentConfig` | inline default baked into `render_preview.py` — self-sufficient, no deployed doc config needed |

Copy `.env.ai-documents.example` → `.env.ai-documents` and fill it (gitignored); a process
env var of the same name overrides the file. **The one-off CLI takes `--reference-type` and
`--reference-locator` explicitly** — it does NOT auto-read `AI_DOCUMENTS_REFERENCE_<TYPE>`
(only the test suite's `--render-preview` does), so pull the locator from the env yourself:

```bash
LOC=$(grep '^AI_DOCUMENTS_REFERENCE_SEGMENT=' .env.ai-documents | cut -d= -f2- | tr -d '"'\'' \r')
python3 -m velocity_converter.render_preview \
  --template "workspace/output/<stem>/<stem>.final.vm" \
  --reference-type segment --reference-locator "$LOC" \
  --out "workspace/output/<stem>/<stem>.preview.pdf" --open
```

It renders against the **already-deployed** SnapshotPlugin (no deploy step here). Full
reference: CLAUDE.md § "Ad-hoc rendering preview (live tenant)".
