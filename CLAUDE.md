# Velocity Converter — Claude instructions

**Repository:** [github.com/joshlawrence-web/socotra-document-conversion](https://github.com/joshlawrence-web/socotra-document-conversion)

## Architecture overview

This tool is a **five-leg document pipeline** for authoring Socotra Velocity templates.
The hot-swap loop: author a document (Word/PDF or HTML) → run the pipeline → deploy
the generated `.final.vm` (and optionally the `SnapshotPlugin.java`) to `socotra-config/`
without redeploying the entire product config JAR.

| Leg | Script | Input → Output |
|-----|--------|----------------|
| -1 | `legminus1_resolve_paths.py` | doc with bare `{leaf}` → `.path-review.csv` (customer-fill) + canonical `.path-review.md`, `.path-map.yaml`, `.path-changes.md`, `.resolved.<ext>` |
| 0 | `leg0_ingest.py` | `.docx`/`.pdf` → `.raw.html`, `.variants.csv` (+ `.conditional-blocks.yaml` sidecar) |
| 1 | `convert.py` | `.html` → `.mapping.yaml` |
| 2 | `leg2_fill_mapping.py` | `.mapping.yaml` → `.mapping.yaml` (enriched), `.review.md` |
| 3 | `leg3_substitute.py` | `.mapping.yaml` → `.final.vm` |
| 4 | `leg4_generate_plugin.py` | `.mapping.yaml` → `SnapshotPlugin.java` |

> Full data-flow diagram: [docs/pipeline-dataflow.md](docs/pipeline-dataflow.md)

> **📖 Read these first — orient before acting.** Before changing, debugging, or explaining
> anything in this repo, skim these three (they're short and save scanning the source):
> 1. [docs/pipeline-dataflow.md](docs/pipeline-dataflow.md) — end-to-end artifact flow + the
>    **human-in-the-loop view** (which moments need a person vs. are automated)
> 2. [docs/leg-internals.md](docs/leg-internals.md) — each leg's internal control flow + invariants
> 3. [docs/CODEMAP.md](docs/CODEMAP.md) — symbol → line index; jump straight to a function instead
>    of scanning a 1,000–2,000-line module
>
> Always consult the code map / leg internals **before reading a leg's source**.

### Workspace layout (the user-interaction space)

All authoring lives under `workspace/`, split into three demo-readable buckets:

```
workspace/
  inbox/           source docs you feed the pipeline (.docx/.pdf/.html)
  action-needed/   FLAT — the files a human must hand-edit before continuing:
                     <stem>.variants.csv          (fill the `when` for every
                                                    conditional block — binary,
                                                    template, and N-way variant)
                     <stem>.path-review.csv       (Leg -1: fill the `final`
                                                    accessor column; suggested
                                                    column lists candidates)
  output/<stem>/   per-stem machine artifacts (.mapping.yaml, .final.vm, reports,
                   .conditional-blocks.yaml sidecar, .java, the canonical
                   .path-review.md, …)
```

The legs always pass the per-stem **machine** dir (`workspace/output/<stem>`) as
`--output-dir`; the two human-fill files are routed to `workspace/action-needed/`
automatically (see `velocity_converter/workspace.py`). `inbox/` is tracked;
`output/` and `action-needed/` are generated (gitignored). Tests use the same
split under `tests/pipeline/`.

---

## Front door: one-shot intake (Leg -1 suggest + Leg 0 scan)

> **🟢 Asked to "create a demo" / "run a doc back-to-front"? Use the runbook, not raw legs:**
> **[docs/demo-runbook.md](docs/demo-runbook.md)**. Two commands — `python3
> tools/run_demo.py intake <doc>` then `… finalize <stem>` — enforce the leg order
> and end on the mandatory done-gate `python3 tools/validate_demo.py <stem>` (doc
> coverage + renderingData shape). PASS = done; MISMATCH = not done. Do **not**
> hand-declare success or hand-roll a validator.

When the customer hands over a `.docx`/`.pdf` and you want to give them **everything to
fill in one package**, run `intake`. It runs Leg -1 *suggest* and Leg 0 *scan* back to
back on the same document and produces both human-fill files at once:

```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE intake input=<path.docx|path.pdf> registry=registry/path-registry.yaml output=workspace/output"
```

Hand-fill files (both land in `workspace/action-needed/`):
- `<stem>.path-review.csv` — confirm/fix each accessor in the `final` column; the
  `suggested` column lists the registry candidates (Leg -1)
- `<stem>.variants.csv` — the single conditional fill file: one `when` per binary/
  template block, plus the rows for any N-way `[[$token]]` block (Leg 0)

…plus the canonical `<stem>.path-review.md` and the machine map/audit
(`<stem>.path-map.yaml`, `<stem>.path-changes.md`) in `workspace/output/<stem>/`. This collapses the two previously-separate human touchpoints
(path-review after Leg -1, then the conditional form after Leg 0) into a single up-front
handoff. The scan runs **without** the path-map (path-review isn't filled yet, and the
CSV shows the author's bare `{field}` syntax regardless — harmless).

`intake` requires `.docx`/`.pdf` (the scan needs the document); `.html` is rejected. After
the customer returns the files, continue with `legminus1_apply`, then the full `leg0`
ingest with `--path-map` (it writes the `.conditional-blocks.yaml` sidecar the parse needs),
then `--parse-variants-csv`, then Leg 2+3+4.

**Trigger phrases — intake** (not exhaustive — use judgment):
- "prep the intake package" / "get everything the customer needs to fill"
- "front-load the customer questions" / "one package for the customer"
- "run intake" / "start the customer intake"

---

## Resolving bare field names to accessor paths (Leg -1)

Authors should not have to know the exact accessor path. Leg -1 lets them write a
**bare leaf** (`{firstName}`) and resolves it to the full accessor
(`account.data.firstName`) against the registry, producing a **human-validated
artifact before Leg 0**. It is **registry-only** — no compiled SDK is consulted,
so a "resolved" leaf is registry-matched, not JAR-verified (Leg 2 still verifies
paths against the rendering root downstream).

**Trigger phrases — Leg -1** (not exhaustive — use judgment):
- "resolve the field names" / "map my fields to accessors"
- "I wrote plain field names, what are the real paths"
- "run leg -1" / "leg minus 1"
- "the author doesn't know the accessor paths"

**Step 1 — suggest** (doc → editable review + machine map + before/after audit):
```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE legminus1 input=<path.docx|.pdf|.html> registry=registry/path-registry.yaml output=workspace/output"
```

**Step 2 — the human fills** `workspace/action-needed/<stem>.path-review.csv`: three
columns — `field` (the bare `{leaf}`), `suggested` (registry candidate accessors,
one per line in the cell, top pick first), and `final` (the single accessor to use,
pre-filled with the top pick). Ambiguous leaves (multiple registry candidates in the
same scope, e.g. `{premium}` across coverages) list every candidate in `suggested`;
unmatched leaves have a blank `final` for the human to type. The canonical
`<stem>.path-review.md` (in `output/<stem>/`) is the system record — the CSV's `final`
column is folded onto its `Final:` lines on apply.

**Step 3 — apply** (fold the filled CSV onto the canonical review → final map +
before/after audit + resolved doc copy):
```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE legminus1_apply review=workspace/action-needed/<stem>.path-review.csv"
```
*(`review=` also accepts the canonical `<stem>.path-review.md` directly, for an
operator editing the `Final:` lines in place instead of the CSV.)*

**Then feed Leg 0** — pass the validated map; the source doc is never modified:
```
python3 -m velocity_converter.leg0_ingest --input <path.docx|.pdf> --path-map workspace/output/<stem>/<stem>.path-map.yaml --output-dir workspace/output/<stem>
```
(Or run Leg 0 on the `<stem>.resolved.docx` directly — it carries the full
accessors baked in.)

**Loop scope is resolved automatically** — a `{leaf}` inside `[Item]…[/Item]`
markers is matched against that exposure's fields (so `{purchasePrice}` → 
`item.data.purchasePrice`), while the same leaf at document level matches
policy/quote scope. A leaf used both inside and outside a loop is treated as
document-level (mirrors Leg 0's loop-field rule).

**Artifacts:**
- `workspace/action-needed/<stem>.path-review.csv` — **editable (human-fill)**; three
  columns (`field` / `suggested` / `final`), fill the `final` accessor
- `workspace/output/<stem>/<stem>.path-review.md` — canonical system copy (one block per
  leaf); the CSV's `final` column is folded onto its `Final:` lines on apply
- `workspace/output/<stem>/<stem>.path-map.yaml` — machine map (`leaf → chosen accessor`) consumed by Leg 0
- `workspace/output/<stem>/<stem>.path-changes.md` — before/after audit, one row per field, with
  suggested-vs-human-override provenance (the traceability anchor)
- `workspace/output/<stem>/<stem>.resolved.<ext>` — (apply mode) doc copy with full accessors; PDF input
  yields a resolved `.html` instead with a warning

**Known limits:** charge accessors (`charges.premium.amount`) surface as candidates
but are not keys in Leg 0's registry lookup — Leg 2 owns charge resolution. DOCX
placeholders split across Word runs are flattened into the first run on rewrite;
any placeholder not found in the source is reported, not silently dropped.

---

## Converting Word/PDF documents to Velocity templates (Leg 0)

When the user provides a `.docx` or `.pdf` file, run Leg 0 (then optionally full pipeline).

**Leg 0 only** (convert doc → raw HTML + extract fields + variants CSV + sidecar):
```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg0 input=<path.docx|path.pdf> output=workspace/output"
```

**Leg 0 scan** (front-load the customer handoff — emit ONLY the human-fill file,
the single `<stem>.variants.csv` covering every conditional block, with **no** machine
artifacts). Use this to hand the customer their CSV to fill while the full ingest is
deferred; pair it with Leg -1 *suggest* to deliver `path-review.csv` + `variants.csv` as
one up-front package:
```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg0_scan input=<path.docx|path.pdf> output=workspace/output"
```
The scan runs the same parse as the full ingest, so the CSV it writes is byte-identical
to the full ingest's. Run the full `leg0` (or `leg0+leg2+leg3`) afterwards to produce the
machine artifacts — including the `.conditional-blocks.yaml` sidecar the parse step needs
— it re-parses (deterministic, cheap) and re-writes the same CSV.

**Trigger phrases — Leg 0 scan** (not exhaustive — use judgment):
- "send the customer the conditional form"
- "what does the customer need to fill in"
- "prep the intake package" / "front-load the customer questions"
- "just give me the forms, not the full conversion"
- "run leg 0 scan"

**Full customer flow** (doc → HTML → suggested paths → final template):
```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg0+leg2+leg3 input=<path.docx|path.pdf> registry=registry/path-registry.yaml output=workspace/output"
```

**After customer returns the filled variants CSV** (parse it + the machine sidecar →
conditional-registry; the full Leg 0 ingest must have run first to write the sidecar):
```
python3 -m velocity_converter.leg0_ingest --parse-variants-csv workspace/action-needed/<stem>.variants.csv --output-dir workspace/output/<stem>/
```
*(Legacy: an in-flight `<stem>.conditional-form.md` can still be parsed with
`--parse-conditional-form …`; new documents use `--parse-variants-csv`.)*

**Trigger phrases — Leg 0** (not exhaustive — use judgment):
- "convert my Word document"
- "convert my PDF"
- "process my docx"
- "ingest this document"
- "run leg 0"

**Trigger phrases — full customer flow** (not exhaustive — use judgment):
- "convert my Word file to a velocity template"
- "process the customer document end to end"
- "run leg 0 through leg 3"

**Trigger phrases — parse variants CSV** (not exhaustive — use judgment):
- "the customer returned the conditional form" / "the customer returned the variants CSV"
- "parse the conditional form" / "parse the variants CSV"
- "generate the conditional registry"

**Output lands in** `workspace/output/<stem>/` (machine artifacts):
- `<stem>.raw.html` — raw converted HTML (pre-annotation)
- `<stem>.annotated.html` — HTML with `{field}` → `$TBD_field`, `[[cond]]` → `$doc.condN`
- `<stem>.mapping.yaml` — leg2-compatible mapping (enriched in-place by Leg 2)
- `<stem>.conditional-blocks.yaml` — machine sidecar (block metadata) the parse step reads
- `<stem>.conditional-registry.yaml` — written after the customer returns the variants CSV

…and the **human-fill** file lands in `workspace/action-needed/` (flat):
- `<stem>.variants.csv` — the single customer-facing fill file for every conditional block
  (binary `[[text]]` → fill the `when`, text pre-filled; template/loop block → fill the
  `when` only; N-way `[[$token]]` → rows + a default). Send this to the customer.

**Occurrence symbols** — a `{field}` placeholder may declare its occurrence with a
prefix: `{field}` required (default), `{$field}` optional, `{+field}` one or more,
`{*field}` zero or more (mirrors registry quantifiers). The symbol is recorded as
`occurrence:` in the `.mapping.yaml` and stripped from the `$TBD_*` token. Leg 4
enforces it in the generated plugin: required/one_or_more fields get null/empty guards
that throw `IllegalStateException` when data is missing — see the "Occurrence guards"
section of the plugin report. The template carries no null-safety logic.

**Loop sections** — wrap a repeating region in `[Name]` … `[/Name]` markers, where
`Name` exactly matches a registry iterable name (e.g. `[Item]` … `[/Item]` for the
items array). Markers may be standalone paragraphs or table rows (other cells empty) —
a marker row around a table's data row repeats just that row, keeping the header once.
Leg 0 replaces the markers with a `#foreach ($item in $TBD_Item)` / `#end` scaffold,
moves the enclosed `{field}` placeholders into the loop's `fields` list in the
`.mapping.yaml`, and Leg 2+3 resolve the scaffold to the registry's real directive
(e.g. `#foreach ($item in $data.items)`). Unmatched markers stay as literal text with
a stderr warning.

**Loop inside a conditional** — a loop section fully inside a top-level `[[...]]`
block flips that block to `render: template`: the block's content (loop included)
stays in the `.vm` wrapped in `#if($data.condN)`…`#end`, and the plugin puts `condN`
as a **Boolean** instead of a baked string (an exception to the "plugin owns
conditional text" rule). In the variants-only flow the block becomes a `when`-only
`variants.csv` row (the customer fills only the condition; the section wording stays
in the document); the `render: template` flag travels in the `.conditional-blocks.yaml`
sidecar → conditional-registry → Leg 4. Refused with a warning (markers left literal):
a loop *crossing* a block boundary, or inside a *nested* block. A conditional fully
inside a loop is allowed but warned — conditions are document-scoped, so it renders
identically for every item. **One genuinely-unsupported edge** (documented, not
handled): an N-way `[[$token]]` block whose variants each carry their *own* loop —
loop bodies can't live in a CSV `text` cell and `render: template` is binary show/hide,
not N-way.

**Conditions use the condition DSL** — every block's `when` (binary, template, and
variant) is parsed by `condition_dsl`. Use `present`/`absent` for null checks (NOT
`!= null`), `==`/`!=`/`<`/`>`/`in` for comparisons. Conditions are document-scoped, so
they reference quote/account/policy(segment) accessors — never per-exposure `item.*`
(rejected at document scope, since there is no single item local).

**Nested `[[$label]]` inside a variant's text** — a variant's `text` cell may embed
`[[$other]]`, where `other` is another placeholder (row) in the same `variants.csv`.
Parse peels `[[$x]]` → `$doc.x`; a referenced placeholder that has no document marker of
its own is **synthesized** as a nested-only block; Leg 4 composes its value into the
referrer's plugin string (`" + other + "`), topo-ordering the label's local first. The
nested label never appears in the template — it lives only inside the parent's plugin
value. Validated at parse (raises, no half-valid registry): a missing referent, a
self-reference, a reference cycle, and a scope clash (a nested label must share its
referrer's scope, or be unconditional). This is the **sheet-native** way to express a
conditional-inside-a-conditional — authoring the nesting in the docx body is not
required (and not the supported path for CSV-driven labels).

> **The two customer-fill files in `action-needed/` — how they relate:**
> [docs/variants-and-path-review.md](docs/variants-and-path-review.md) explains how
> `<stem>.path-review.csv` (plain body fields, Leg -1) and `<stem>.variants.csv`
> (conditional blocks, Leg 0) divide the document and share the same fields (with a
> story + diagram). Read it when explaining the intake package to a customer.

---

## MANDATORY pre-flight before Leg 2, 3, or 4 (after a Leg 0 run)

**ALWAYS run this check before executing Leg 2, Leg 3, or Leg 4 when the source was a Leg 0 run.**

1. Check if `workspace/output/<stem>/<stem>.conditional-registry.yaml` exists.
2. Check if `workspace/action-needed/<stem>.variants.csv` exists.
3. If the **registry does NOT exist** and the **variants CSV DOES exist** → parse it first, then proceed (the full Leg 0 ingest must have written the `.conditional-blocks.yaml` sidecar):

```
python3 -m velocity_converter.leg0_ingest --parse-variants-csv workspace/action-needed/<stem>.variants.csv --output-dir workspace/output/<stem>/
```

*(Legacy in-flight forms: if instead a `<stem>.conditional-form.md` exists, parse it with `--parse-conditional-form …`.)*

4. Only after the registry is written (or confirmed to already exist) → run the requested downstream legs.

**Do not skip this step.** The plugin will be empty and the template will have unresolved `$doc.condN` placeholders if the registry is missing. The user should not have to tell you to do this — it is always required.

---

## renderingData shape — the template-path rule (READ before any demo)

**renderingData shape is the contract that makes a generated template actually render.**
The registry stores velocities **root-relative** (`$data.policyNumber`, `$data.data.x`,
`$data.items`) — but `$data` at render time is the Map the `DocumentDataSnapshotPlugin`
builds, and it `.put()`s the rendering-root entity under a **named key**. A bare
`$data.<field>` or `$data.data.<field>` in a `.final.vm` points at a key that doesn't
exist and renders to nothing. Every rendering-root-entity field must carry its entity key.

**The key = the field's verified Java local** (so the template mirrors the plugin):

| Doc root | Field kind | Correct template path |
|---|---|---|
| `(quote)` | system + custom | `$data.quote.<f>` / `$data.quote.data.<f>` |
| `(segment)` | **system** (core Policy) | `$data.policy.<f>` |
| `(segment)` | **custom** (typed Segment) | `$data.segment.data.<f>` |
| `(segment)` | **loop list / exposure** | `$data.segment.items`, then `$item.data.<f>` |
| any | account / DataFetcher | `$data.account.data.<f>` *(own key — unchanged)* |

A `(segment)` doc **splits across two keys**: system fields → `$data.policy.*`, custom
data + exposures → `$data.segment.*`. A `(quote)` doc keeps everything on `$data.quote.*`.

The splice lives in `agent_tools.render_root_velocity()` (Leg 0 pre-fill) and
`leg2_fill_mapping._reprefix()` (Leg 2 JAR verdict). Full explanation + the chain:
[docs/RenderingDataConfigRelated.md](docs/RenderingDataConfigRelated.md).

**Demo checklist — after Leg 3, before declaring a template done, grep the `.final.vm`:**
- ❌ No bare `$data.data.` (missing the `$data.segment.` / `$data.quote.` key).
- ❌ No bare `$data.<systemField>` (e.g. `$data.policyNumber`) — must be `$data.policy.<f>`
  (segment) or `$data.quote.<f>` (quote).
- ✅ Every resolved field is under `$data.policy` / `$data.segment` / `$data.quote` /
  `$data.account`; every loop is `#foreach ($item in $data.<root>.items)`.

If any bare path slips through, the resolution is wrong — fix the data_source, don't ship it.

---

## Converting HTML files to Velocity templates

When the user asks to convert HTML files, run the full pipeline. No explanation needed — just do it.

**Steps:**
1. List `workspace/inbox/` to find available `.html` files
2. If ambiguous which files, ask. If they said "all" or "my files", run all of them.
3. Run from repo root: `python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg1+leg2+leg3 input=<path> registry=registry/path-registry.yaml output=workspace/output"`
4. Report what was written. Tell the user to check `<stem>.leg3-report.md` for any unresolved tokens.

**Trigger phrases** (not exhaustive — use judgment):
- "convert my files"
- "convert X to velocity"
- "run the pipeline"
- "process my HTML"
- "generate the templates"
- "finalise the template"
- "write the final vm"
- "run leg 3"

**Leg 1 only** (HTML → `.vm` + `.mapping.yaml`, no path suggestions):
```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg1 input=<path> output=workspace/output"
```

**Leg 2 only** (suggest paths for an existing mapping):
```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg2 mapping=<path> registry=registry/path-registry.yaml"
```

**Leg 2+3** (suggest paths + write final template, starting from an existing mapping — use after leg0 + parsing the variants CSV):
```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg2+leg3 mapping=<path> registry=registry/path-registry.yaml"
```

**Leg 3 only** (finalise an existing `.mapping.yaml` into a `.final.vm`):
```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg3 suggested=<path.mapping.yaml>"
```

**Leg 1+2 only** (HTML → suggested paths, no final write — useful when many tokens are unresolved and need human review first):
```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg1+leg2 input=<path> registry=registry/path-registry.yaml output=workspace/output"
```

**Output lands in** `workspace/output/<stem>/`:
- Check `<stem>.leg3-report.md` first — it shows what resolved and what still needs work.
- `<stem>.final.vm` is the production template.
- `<stem>.review.md` (from Leg 2) is the path-confidence breakdown.

## Generating the DocumentDataSnapshotPlugin (Leg 4)

**Trigger phrases** (not exhaustive — use judgment):
- "generate the plugin"
- "build the snapshot plugin"
- "run leg 4"
- "create the DocumentDataSnapshotPlugin"
- "wire up renderingData"
- "update the plugin with the new form"
- "add the new document to the plugin"
- "run leg 4 for multiple forms"
- "add the second form to the plugin"

**Leg 4** (`.mapping.yaml` → Java plugin + report):
```
python3 -m velocity_converter.leg4_generate_plugin \
  --suggested workspace/output/<stem>/<stem>.mapping.yaml \
  --customer-jar build/customer-config.jar \
  --datamodel-jar build/core-datamodel-v1.7.61.jar \
  --compile-check
```

Output lands in `workspace/output/<stem>/`:
- `{Product}DocumentDataSnapshotPluginImpl.java` — deploy to `socotra-config/plugins/java/` manually.
- `<stem>.plugin-report.md` — path validation + compile result.

**Additive mode** — if `{Product}DocumentDataSnapshotPluginImpl.java` already exists in the output dir, Leg 4 automatically adds only the missing keys (never removes existing ones). A `.java.bak` backup is written before modification. The plugin report includes an "Additive update summary" section.

**Fields inside conditional blocks** — `{field}` placeholders inside `[[...]]` blocks are concatenated into the plugin's conditional strings as Java accessors (e.g. `Objects.toString(segment.data().discountAmount(), "")`); the template only outputs `${data.condN}`. Supported: quote system fields (quote overload), policy system + custom fields (policy overload — custom fields resolve on the segment type). **Leg 4 hard-fails** if a field inside a block has no `data_source` — run Leg 2 first. Per-exposure (`item.*`), account, and DataFetcher-sourced fields are not wired: they get a `// TODO` comment and a WARN row in the plugin report's "Field tokens inside conditional blocks" section.

**Multi-form** — pass multiple `--suggested` paths (each pointing to a `.mapping.yaml`), use `RUN_PIPELINE leg4 suggested=[a.mapping.yaml, b.mapping.yaml]`, or call `run_leg4(suggested=[...])` from `agent_tools.py`. All forms are merged into **one** plugin: it lands in the first form's directory (override with `--output-dir`). The first form writes it fresh — or updates it additively if the `.java` already exists — and every subsequent form is merged additively (conditional ids renumber past the existing high-water mark). Each form still gets its own `.plugin-report.md` in its own directory.

Supported plugin flows:
1. **Fresh, multiple forms** — no existing `.java`: pass all forms in one run → one combined plugin.
2. **Additive, single form** — `.java` exists in the output dir: the new form's missing keys are appended.
3. **Additive, multiple forms** — `.java` exists: pass all new forms in one run; each is appended in sequence.

(Removing a form from the plugin is **not** supported — that requires conditional-number state tracking.)

**Pipeline integration** (`RUN_PIPELINE leg4`) is wired into `agent.py`.

---

## Listing available Velocity paths (Path Catalog)

When the user wants to know what fields/paths are available in a template, render the path catalog from the registry.

**Trigger phrases** (not exhaustive — use judgment):
- "what fields can I use"
- "list available paths"
- "show me the field catalog"
- "what data is available in the template"
- "export the path registry"

**Print to stdout:**
```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE list_paths registry=registry/path-registry.yaml"
```

**Write to file:**
```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE list_paths registry=registry/path-registry.yaml out=workspace/output/field-catalog.md"
```

**Direct script:**
```
python3 -m velocity_converter.list_paths [--registry registry/path-registry.yaml] [--out <path>]
```

Output: grouped Markdown — System → Account → Policy Custom Fields → Policy Charges → Per-Exposure (system/custom/coverages/charges) → DataFetcher Paths.

---

## Running the pipeline test suite

When the user asks to validate pipeline changes, run the automated test suite.

**Trigger phrases** (not exhaustive — use judgment):
- "run the test pipeline"
- "test my changes"
- "validate the pipeline"
- "run the tests"
- "check the pipeline still works"

**Run all fixtures (automated, no pauses):**
```
python3 tests/pipeline/run_test_pipeline.py --auto
```

**Run a single fixture:**
```
python3 tests/pipeline/run_test_pipeline.py --auto --only "TestItemCert(segment)"
```

**Interactive mode** (pauses so you can hand-fill conditions — simulates real customer flow):
```
python3 tests/pipeline/run_test_pipeline.py
```

**Regenerate DOCX fixtures** (run this if fixtures are missing or after changing `generate_test_fixtures.py`):
```
python3 tools/generate_test_fixtures.py
```

**Render preview against a live tenant** (opt-in — requires `.env.ai-documents` at the repo
root copied from `.env.ai-documents.example`, and the generated SnapshotPlugin already deployed
to the tenant; fixtures whose reference type has no `AI_DOCUMENTS_REFERENCE_<TYPE>` locator are
skipped):
```
python3 tests/pipeline/run_test_pipeline.py --auto --render-preview
```

Output lands in `tests/pipeline/output/<stem>/`. Exit code is non-zero on failure.

**What is tested:** Leg 0 → variants.csv fill (built from `condition_seeds.yaml`) →
`--parse-variants-csv` → Leg 2+3 → Leg 4 (single combined plugin) across nine fixtures:
`TestQuoteSummary(quote)`, `TestItemCert(segment)`, `TestRenewalNotice(segment)`,
`TestItemsSchedule(segment)` (loops over the items array via `[Item]`/`[/Item]` markers),
`TestGiftSchedule(segment)` (an `[Item]` loop inside a `[[conditional]]` → `render: template`
block — the variants-only template-as-`when`-only-row guard),
`TestStateDisclosure(segment)` (an N-way `[[$token]]` variant block),
`TestVariantThenBinary(segment)` (a `[[$token]]` variant block immediately followed by a binary
`[[…]]` block — regression guard for the variant-then-binary parse fix, now one CSV path), and
`TestVariantBareLeaf(segment)` (a `[[$token]]` block whose variant text uses a **bare leaf**
`{discountAmount}` — exercises Leg 4's variant-text leaf resolution / "Decision B"), and
`TestNestedVariantLabel(segment)` (a `[[$token]]` block whose variant text embeds a **nested
`[[$label]]` reference** to a second, document-marker-less placeholder — exercises the
nested-ref peel + block synthesis + topo-ordered plugin composition).

**Adding a new fixture** (four-step checklist):
1. Add a builder function to `tools/generate_test_fixtures.py` and append it to `FIXTURES`.
2. Add the filename to `ALL_FIXTURES` in `tests/pipeline/run_test_pipeline.py`.
3. Add condition seeds for its blocks in `tests/pipeline/condition_seeds.yaml`.
4. Run `python3 tools/generate_test_fixtures.py` to write the DOCX.

> Full details: [tests/pipeline/README.md](tests/pipeline/README.md)

---

## Ad-hoc rendering preview (live tenant)

When the user wants to see how a generated `.final.vm` actually renders against real
tenant data — without conducting a transaction — use the ad-hoc rendering endpoint
(`POST {API_URL}document/{tenantLocator}/documents/render`, Socotra Documents API).
All request fields travel as multipart form-data, including the template source and
an inline `documentConfig` JSON (self-sufficient — no deployed document config needed).

**Trigger phrases** (not exhaustive — use judgment):
- "preview the template"
- "render the template against the tenant"
- "do an ad-hoc render"
- "test the template on a real quote/policy"
- "rendering preview"

**One-off preview:**
```
python3 -m velocity_converter.render_preview \
  --template workspace/output/<stem>/<stem>.final.vm \
  --reference-type quote --reference-locator <locator> \
  --out workspace/output/<stem>/<stem>.preview.pdf --open
```

Add `--open` to pop the saved PDF straight into the OS viewer (a one-click "test
render" for demos), or `--reveal` to select it in Finder/Explorer. Both require
`--out`. The call prints a short progress trace (endpoint, response size) to stderr
so you can watch the API round-trip. It renders against the **already-deployed**
plugin — there is no deploy step here.

Requires:
1. The generated `DocumentDataSnapshotPlugin` **deployed to the tenant first** — the
   renderer executes it to build `$data` (conditionals included).
2. `.env.ai-documents` at the repo root (copy `.env.ai-documents.example`; gitignored)
   with `AI_DOCUMENTS_API_URL`, `AI_DOCUMENTS_TENANT_LOCATOR`, `AI_DOCUMENTS_PAT`
   (JWT or PAT with the `documents` group's `render-external` permission). Process env
   vars with the same names override the file.

As part of the test suite, use `--render-preview` (see the test-suite section above).

---

## MCP server (Claude Code)

The pipeline is also exposed as an MCP server (`mcp_server.py`). Run `python3 install.py`
once to register it with Claude Code — then you can convert HTML from any project directory
without keeping this repo open. See [README.md](README.md) § "Using with Claude Code".

This CLAUDE.md covers the **in-repo script workflow** when working directly in a clone.

---

## Historical plans

Implementation plans that drove past work were removed from the tree to avoid stale
context. They are preserved in git history at the tag `plans-archive`. Recover with:
`git checkout plans-archive -- .cursor/plans`. Do not treat old plan documents as
current requirements.
