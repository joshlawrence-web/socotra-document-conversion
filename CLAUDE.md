# Velocity Converter — Claude instructions

**Repository:** [github.com/joshlawrence-web/socotra-document-conversion](https://github.com/joshlawrence-web/socotra-document-conversion)

## Architecture overview

This tool is a **five-leg document pipeline** for authoring Socotra Velocity templates.
The hot-swap loop: author a document (Word/PDF or HTML) → run the pipeline → deploy
the generated `.final.vm` (and optionally the `SnapshotPlugin.java`) to `socotra-config/`
without redeploying the entire product config JAR.

| Leg | Script | Input → Output |
|-----|--------|----------------|
| 0 | `leg0_ingest.py` | `.docx`/`.pdf` → `.raw.html`, `.conditional-form.md` |
| 1 | `convert.py` | `.html` → `.mapping.yaml` |
| 2 | `leg2_fill_mapping.py` | `.mapping.yaml` → `.mapping.yaml` (enriched), `.review.md` |
| 3 | `leg3_substitute.py` | `.mapping.yaml` → `.final.vm` |
| 4 | `leg4_generate_plugin.py` | `.mapping.yaml` → `SnapshotPlugin.java` |

> Full data-flow diagram: [docs/pipeline-dataflow.md](docs/pipeline-dataflow.md)

---

## Converting Word/PDF documents to Velocity templates (Leg 0)

When the user provides a `.docx` or `.pdf` file, run Leg 0 (then optionally full pipeline).

**Leg 0 only** (convert doc → raw HTML + extract fields + conditional form):
```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg0 input=<path.docx|path.pdf> output=samples/output"
```

**Full customer flow** (doc → HTML → suggested paths → final template):
```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg0+leg2+leg3 input=<path.docx|path.pdf> registry=registry/path-registry.yaml output=samples/output"
```

**After customer returns the filled conditional form:**
```
python3 -m velocity_converter.leg0_ingest --parse-conditional-form samples/output/<stem>/<stem>.conditional-form.md --output-dir samples/output/<stem>/
```

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

**Trigger phrases — parse conditional form** (not exhaustive — use judgment):
- "the customer returned the conditional form"
- "parse the conditional form"
- "generate the conditional registry"

**Output lands in** `samples/output/<stem>/`:
- `<stem>.raw.html` — raw converted HTML (pre-annotation)
- `<stem>.annotated.html` — HTML with `{field}` → `$TBD_field`, `[[cond]]` → `$doc.condN`
- `<stem>.mapping.yaml` — leg2-compatible mapping (enriched in-place by Leg 2)
- `<stem>.conditional-form.md` — customer-facing conditional form (send to customer)
- `<stem>.conditional-registry.yaml` — written after customer returns the form

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
conditional text" rule). The flag flows conditional-form → conditional-registry
(`render: template`) → Leg 4. Refused with a warning (markers left literal): a loop
*crossing* a block boundary, or inside a *nested* block. A conditional fully inside
a loop is allowed but warned — conditions are document-scoped, so it renders
identically for every item.

---

## MANDATORY pre-flight before Leg 2, 3, or 4 (after a Leg 0 run)

**ALWAYS run this check before executing Leg 2, Leg 3, or Leg 4 when the source was a Leg 0 run.**

1. Check if `samples/output/<stem>/<stem>.conditional-registry.yaml` exists.
2. Check if `samples/output/<stem>/<stem>.conditional-form.md` exists.
3. If the **registry does NOT exist** and the **form DOES exist** → parse the conditional form first, then proceed:

```
python3 -m velocity_converter.leg0_ingest --parse-conditional-form samples/output/<stem>/<stem>.conditional-form.md --output-dir samples/output/<stem>/
```

4. Only after the registry is written (or confirmed to already exist) → run the requested downstream legs.

**Do not skip this step.** The plugin will be empty and the template will have unresolved `$doc.condN` placeholders if the registry is missing. The user should not have to tell you to do this — it is always required.

---

## Converting HTML files to Velocity templates

When the user asks to convert HTML files, run the full pipeline. No explanation needed — just do it.

**Steps:**
1. List `samples/input/` to find available `.html` files
2. If ambiguous which files, ask. If they said "all" or "my files", run all of them.
3. Run from repo root: `python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg1+leg2+leg3 input=<path> registry=registry/path-registry.yaml output=samples/output"`
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
python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg1 input=<path> output=samples/output"
```

**Leg 2 only** (suggest paths for an existing mapping):
```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg2 mapping=<path> registry=registry/path-registry.yaml"
```

**Leg 2+3** (suggest paths + write final template, starting from an existing mapping — use after leg0 + parsing the conditional form):
```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg2+leg3 mapping=<path> registry=registry/path-registry.yaml"
```

**Leg 3 only** (finalise an existing `.mapping.yaml` into a `.final.vm`):
```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg3 suggested=<path.mapping.yaml>"
```

**Leg 1+2 only** (HTML → suggested paths, no final write — useful when many tokens are unresolved and need human review first):
```
python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg1+leg2 input=<path> registry=registry/path-registry.yaml output=samples/output"
```

**Output lands in** `samples/output/<stem>/`:
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
  --suggested samples/output/<stem>/<stem>.mapping.yaml \
  --customer-jar build/customer-config.jar \
  --datamodel-jar build/core-datamodel-v1.7.61.jar \
  --compile-check
```

Output lands in `samples/output/<stem>/`:
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
python3 -m velocity_converter.agent --yes "RUN_PIPELINE list_paths registry=registry/path-registry.yaml out=samples/output/field-catalog.md"
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

Output lands in `tests/pipeline/output/<stem>/`. Exit code is non-zero on failure.

**What is tested:** Leg 0 → conditional-form fill → parse → Leg 2+3 → Leg 4 (single combined plugin)
across five fixtures: `TestQuoteSummary(quote)`, `TestItemCert(segment)`, `TestRenewalNotice(segment)`,
`TestItemsSchedule(segment)` (loops over the items array via `[Item]`/`[/Item]` markers),
`TestGiftSchedule(segment)` (an `[Item]` loop inside a `[[conditional]]` → `render: template` block).

**Adding a new fixture** (four-step checklist):
1. Add a builder function to `tools/generate_test_fixtures.py` and append it to `FIXTURES`.
2. Add the filename to `ALL_FIXTURES` in `tests/pipeline/run_test_pipeline.py`.
3. Add condition seeds for its blocks in `tests/pipeline/condition_seeds.yaml`.
4. Run `python3 tools/generate_test_fixtures.py` to write the DOCX.

> Full details: [tests/pipeline/README.md](tests/pipeline/README.md)

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
