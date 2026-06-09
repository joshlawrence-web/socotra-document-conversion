# Velocity Converter — Claude instructions

**Repository:** [github.com/joshlawrence-web/socotra-document-conversion](https://github.com/joshlawrence-web/socotra-document-conversion)

## Converting Word/PDF documents to Velocity templates (Leg 0)

When the user provides a `.docx` or `.pdf` file, run Leg 0 (then optionally full pipeline).

**Leg 0 only** (convert doc → raw HTML + extract fields + conditional form):
```
python3 scripts/agent.py --yes "RUN_PIPELINE leg0 input=<path.docx|path.pdf> output=samples/output"
```

**Full customer flow** (doc → HTML → suggested paths → final template):
```
python3 scripts/agent.py --yes "RUN_PIPELINE leg0+leg2+leg3 input=<path.docx|path.pdf> registry=registry/path-registry.yaml output=samples/output"
```

**After customer returns the filled conditional form:**
```
python3 scripts/leg0_ingest.py --parse-conditional-form samples/output/<stem>/<stem>.conditional-form.md --output-dir samples/output/<stem>/
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
- `<stem>.fields.yaml` — extracted fields (human-editable)
- `<stem>.mapping.yaml` — leg2-compatible mapping
- `<stem>.conditional-form.md` — customer-facing conditional form (send to customer)
- `<stem>.conditional-registry.yaml` — written after customer returns the form

---

## Converting HTML files to Velocity templates

When the user asks to convert HTML files, run the full pipeline. No explanation needed — just do it.

**Steps:**
1. List `samples/input/` to find available `.html` files
2. If ambiguous which files, ask. If they said "all" or "my files", run all of them.
3. Run from repo root: `python3 scripts/agent.py --yes "RUN_PIPELINE leg1+leg2+leg3 input=<path> registry=registry/path-registry.yaml output=samples/output"`
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
python3 scripts/agent.py --yes "RUN_PIPELINE leg1 input=<path> output=samples/output"
```

**Leg 2 only** (suggest paths for an existing mapping):
```
python3 scripts/agent.py --yes "RUN_PIPELINE leg2 mode=terse mapping=<path> registry=registry/path-registry.yaml"
```

**Leg 2+3** (suggest paths + write final template, starting from an existing mapping — use after leg0 + parsing the conditional form):
```
python3 scripts/agent.py --yes "RUN_PIPELINE leg2+leg3 mapping=<path> registry=registry/path-registry.yaml"
```

**Leg 3 only** (finalise an existing `.suggested.yaml` into a `.final.vm`):
```
python3 scripts/agent.py --yes "RUN_PIPELINE leg3 suggested=<path>"
```

**Leg 3 high-confidence only** (substitute only `confidence: high` tokens; medium/low stay as `$TBD_*` and appear in a "Deferred" section of the report — use when fuzzy matches need human review before going live):
```
python3 scripts/agent.py --yes "RUN_PIPELINE leg3 suggested=<path> high_only=true"
```

**Full pipeline high-confidence only** (same as above but runs from HTML):
```
python3 scripts/agent.py --yes "RUN_PIPELINE leg1+leg2+leg3 input=<path> registry=registry/path-registry.yaml output=samples/output high_only=true"
```

**Trigger phrases for high-only mode** (use judgment):
- "only fill the high confidence fields"
- "skip the fuzzy matches"
- "don't substitute medium/low confidence"
- "I want to review the medium confidence first"

**Leg 1+2 only** (HTML → suggested paths, no final write — useful when many tokens are unresolved and need human review first):
```
python3 scripts/agent.py --yes "RUN_PIPELINE leg1+leg2 input=<path> registry=registry/path-registry.yaml output=samples/output"
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

**Leg 4** (`.suggested.yaml` → Java plugin + report):
```
python3 scripts/leg4_generate_plugin.py \
  --suggested samples/output/<stem>/<stem>.suggested.yaml \
  --customer-jar build/customer-config.jar \
  --datamodel-jar build/core-datamodel-v1.7.61.jar \
  --compile-check
```

Output lands in `samples/output/<stem>/`:
- `{Product}DocumentDataSnapshotPluginImpl.java` — deploy to `socotra-config/plugins/java/` manually.
- `<stem>.plugin-report.md` — path validation + compile result.

**Additive mode** — if `{Product}DocumentDataSnapshotPluginImpl.java` already exists in the output dir, Leg 4 automatically adds only the missing keys (never removes existing ones). A `.java.bak` backup is written before modification. The plugin report includes an "Additive update summary" section.

**Multi-form** — pass multiple `--suggested` paths or call `run_leg4(suggested=[...])` from `agent_tools.py`. Each form is processed sequentially; additive mode activates after the first.

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
python3 scripts/agent.py --yes "RUN_PIPELINE list_paths registry=registry/path-registry.yaml"
```

**Write to file:**
```
python3 scripts/agent.py --yes "RUN_PIPELINE list_paths registry=registry/path-registry.yaml out=samples/output/field-catalog.md"
```

**Direct script:**
```
python3 scripts/list_paths.py [--registry registry/path-registry.yaml] [--out <path>]
```

Output: grouped Markdown — System → Account → Policy Custom Fields → Policy Charges → Per-Exposure (system/custom/coverages/charges) → DataFetcher Paths.

---

## MCP server (Claude Code)

The pipeline is also exposed as an MCP server (`mcp_server.py`). Run `python3 install.py`
once to register it with Claude Code — then you can convert HTML from any project directory
without keeping this repo open. See [README.md](README.md) § "Using with Claude Code".

This CLAUDE.md covers the **in-repo script workflow** when working directly in a clone.
