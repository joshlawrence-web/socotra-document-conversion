# Pipeline Data-Flow — Leg 0–4

End-to-end view of every file artifact and human touchpoint in the Velocity Converter pipeline.

> This doc covers the flow *between* legs. For what happens *inside* a leg, see
> [leg-internals.md](leg-internals.md); to jump to a specific function, see [CODEMAP.md](CODEMAP.md).

```mermaid
flowchart LR
  %% ── Inputs ──────────────────────────────────────────
  DOC["Word / PDF\n(.docx / .pdf)"]
  HTML[".html mockup"]

  %% ── Pipeline legs ───────────────────────────────────
  LegM1["Leg -1\nlegminus1_resolve_paths.py"]
  Leg0["Leg 0\nleg0_ingest.py"]
  Leg1["Leg 1\nconvert.py"]
  Leg2["Leg 2\nleg2_fill_mapping.py"]
  Leg3["Leg 3\nleg3_substitute.py"]
  Leg4["Leg 4\nleg4_generate_plugin.py"]

  %% ── Registry (shared input to Leg 2) ────────────────
  REGISTRY[("registry/\npath-registry.yaml\n+ sdk-schema-index.yaml")]

  %% ── Leg -1 artifacts (optional pre-stage) ───────────
  PREVIEW[/".path-review.md\nedit Final: lines"/]
  PATHMAP[".path-map.yaml\nleaf → accessor"]
  PATHCHANGES[/".path-changes.md\nbefore/after audit"/]
  RESOLVED[".resolved doc\naccessors baked in"]

  %% ── Leg 0 artifacts ─────────────────────────────────
  RAW[".raw.html\n(extracted, unmodified)"]
  ANN[".annotated.html\n(fields + conditionals tagged)"]
  L0MAP[".mapping.yaml\n(TBD placeholders)"]
  FORM[/".conditional-form.md\nsend to customer"/]
  VARCSV[/".variants.csv\nN-way variant blocks\nfill in Excel"/]
  CONDREG[".conditional-registry.yaml\n(parsed from filled form)"]

  %% ── Leg 1 artifact ───────────────────────────────────
  L1MAP[".mapping.yaml\n(TBD placeholders)"]

  %% ── Leg 2 artifacts ─────────────────────────────────
  ENRICHED[".mapping.yaml\n(path suggestions added)"]
  REVIEW[/".review.md\noptional human review"/]

  %% ── Leg 3 artifacts ─────────────────────────────────
  FINALVM[".final.vm\nproduction template"]
  L3RPT[/".leg3-report.md\ncheck unresolved tokens"/]

  %% ── Leg 4 artifacts ─────────────────────────────────
  JAVA["SnapshotPlugin.java\n(renderingData wiring)"]
  L4RPT[/".plugin-report.md\nvalidate paths + compile"/]

  %% ── Deploy target ────────────────────────────────────
  DEPLOY[("socotra-config/\nhot-swap deploy")]

  %% ── Flow ─────────────────────────────────────────────

  DOC -.->|"legminus1\n(optional, bare {leaf})"| LegM1
  HTML -.->|"legminus1\n(optional)"| LegM1
  LegM1 --> PREVIEW
  PREVIEW -->|"legminus1_apply\nafter human edits Final:"| PATHMAP
  PREVIEW --> PATHCHANGES
  PREVIEW --> RESOLVED
  PATHMAP -.->|"--path-map"| Leg0
  RESOLVED -.->|"or ingest directly"| Leg0

  %% ── Leg 0 scan (front-loaded human-fill files only) ──
  Scan["Leg 0 --scan\n(intake: shares _parse_document)"]
  DOC -.->|"leg0_scan / intake\n(forms up front)"| Scan
  Scan --> FORM
  Scan -->|"only if a [[$token]]\nvariant block exists"| VARCSV

  DOC -->|"leg0"| Leg0
  Leg0 --> RAW
  Leg0 --> ANN
  Leg0 --> L0MAP
  Leg0 --> FORM
  Leg0 -->|"only if a [[$token]]\nvariant block exists"| VARCSV
  FORM -->|"parse-conditional-form\nafter customer fills"| CONDREG
  VARCSV -->|"sibling CSV merged\nat parse time"| CONDREG

  HTML -->|"leg1"| Leg1
  Leg1 --> L1MAP

  L0MAP -->|"leg0+leg2+leg3"| Leg2
  L1MAP -->|"leg1+leg2+leg3"| Leg2
  CONDREG -.->|"if exists"| Leg2
  REGISTRY --> Leg2

  Leg2 --> ENRICHED
  Leg2 --> REVIEW

  ENRICHED -->|"leg3"| Leg3
  ENRICHED -->|"leg4"| Leg4

  Leg3 --> FINALVM
  Leg3 --> L3RPT

  Leg4 --> JAVA
  Leg4 --> L4RPT

  FINALVM -->|"manual deploy"| DEPLOY
  JAVA -->|"manual deploy"| DEPLOY
```

**Shape key:**
- Rectangle `[text]` — pipeline script or pipeline-managed artifact
- Parallelogram `[/text/]` — human touchpoint (requires action or review)
- Cylinder `[(text)]` — persistent store (registry or deploy target)
- Dashed arrow `-.->` — optional / conditional input

---

## Human-in-the-loop view

The same pipeline, emphasising **where a person acts**. Most legs are fully automated
(blue); the value of the pipeline is that it isolates the few moments a human is actually
needed — confirming accessor paths, answering conditional questions, QA-ing the output, and
deploying.

```mermaid
flowchart TD
  classDef machine fill:#e3f2fd,stroke:#1976d2,color:#0d47a1;
  classDef human fill:#fff3e0,stroke:#e65100,color:#bf360c,stroke-width:3px;
  classDef review fill:#fffde7,stroke:#f9a825,color:#f57f17,stroke-width:1px,stroke-dasharray:5 3;
  classDef deploy fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20,stroke-width:3px;

  IN(["📄 Author's source doc\n(Word / PDF / HTML)"]):::machine

  INTAKE["INTAKE (one front door)\nLeg -1 suggest + Leg 0 --scan"]:::machine
  LM1["Leg -1\nresolve bare {leaf} → accessor"]:::machine
  H1["🙋 EDIT .path-review.md\nconfirm / fix each Final: accessor"]:::human

  L0["Leg 0\ningest doc → HTML + mapping"]:::machine
  L1["Leg 1\nconvert HTML mockup → mapping"]:::machine
  H2["🙋 FILL .conditional-form.md\nanswer each conditional block"]:::human
  H3["🙋 FILL .variants.csv\nN-way variant rows (if present)"]:::human
  PARSE["Leg 0 --parse-conditional-form\n→ conditional-registry.yaml"]:::machine

  L2["Leg 2\nsuggest + grade accessor paths"]:::machine
  R1["👀 REVIEW .review.md\nresolve low / medium confidence"]:::review

  L3["Leg 3\nwrite .final.vm template"]:::machine
  R2["👀 CHECK .leg3-report.md\nany unresolved $TBD_* ?"]:::review

  L4["Leg 4\ngenerate SnapshotPlugin .java"]:::machine
  R3["👀 CHECK .plugin-report.md\npaths validated + compiles ?"]:::review

  DEP["🚀 MANUALLY DEPLOY\n.final.vm + .java → socotra-config/"]:::deploy

  IN -.->|"optional, bare {leaf}"| LM1
  LM1 --> H1
  IN -.->|"intake (bundle all\nhand-fill files up front)"| INTAKE
  INTAKE --> H1
  INTAKE --> H2
  INTAKE -.->|"if [[$variant]] block"| H3
  H1 -.->|"legminus1_apply"| L0
  IN --> L0
  IN --> L1
  L0 --> H2
  L0 -.->|"if [[$variant]] block"| H3
  H3 --> H2
  H2 -.->|"parse"| PARSE
  PARSE --> L2
  L1 --> L2
  L2 --> R1
  R1 --> L3
  L2 --> L4
  L3 --> R2
  L4 --> R3
  R2 --> DEP
  R3 --> DEP
```

**Legend:**
- 🙋 **orange, bold** — a *required* human edit; the pipeline cannot continue correctly until it's done
- 👀 *yellow, dashed* — an *optional but recommended* review / QA gate (proceed once it's clean)
- 🚀 **green** — the final manual action: deploy the two generated files (hot-swap, no JAR rebuild)
- ▢ blue — a fully automated leg (no human needed)

The two **required** human moments are answering the conditional form (`.conditional-form.md`,
plus `.variants.csv` for N-way blocks) and — only when the author wrote bare leaves —
confirming accessors in `.path-review.md`. Everything else is automated or advisory.

**Intake** (`RUN_PIPELINE intake`, or `leg0_scan` on its own) bundles these required edits
into one up-front handoff: it runs Leg -1 *suggest* + Leg 0 `--scan` to emit all three
hand-fill files (`.path-review.md`, `.conditional-form.md`, `.variants.csv`) at once,
deferring the machine artifacts to the later full ingest. This collapses the two otherwise
separate interruptions (path-review after Leg -1, the form after Leg 0) into a single moment.

---

## Walk-through

### Optional first step: resolving bare field names (Leg -1 path)

When the author wrote bare leaves (`{firstName}`) instead of full accessors, Leg -1
(`legminus1_resolve_paths.py`) runs *before* Leg 0. **Suggest mode** reads the doc
(`.docx`/`.pdf`/`.html`) and emits `.path-review.md` — one block per leaf with a suggested
accessor and editable `Final:` line — plus a machine `.path-map.yaml`. A human edits the
`Final:` lines; **apply mode** (`legminus1_apply`) parses the corrected review into the final
`.path-map.yaml`, a `.path-changes.md` before/after audit, and a `.resolved` doc copy with
accessors baked in. Leg 0 then runs either with `--path-map <…>.path-map.yaml` (source doc
unchanged) or directly on the `.resolved` doc. Leg -1 is **registry-only** — paths are
registry-matched, not JAR-verified; Leg 2 still verifies them against the rendering root.

### Starting from a Word or PDF document (Leg 0 path)

Leg 0 (`leg0_ingest.py`) converts a `.docx` or `.pdf` into four artifacts: `.raw.html` (the
unmodified extracted HTML), `.annotated.html` (HTML with `{field}` placeholders replaced by
`$TBD_field` tokens and conditional blocks tagged as `$doc.condN`), `.mapping.yaml` (the
Leg 2 input, pre-populated with TBD placeholders), and `.conditional-form.md` (a
Markdown questionnaire listing every detected conditional block, to be filled in by the
customer or document owner). The form displays field placeholders in the author's
`{field}` syntax; parsing converts them back to canonical `$TBD_field` tokens in the
registry (both forms parse).

**Front-loading the customer handoff (`leg0 --scan`).** The two human-fill files —
`.conditional-form.md` and (when a `[[$token]]` block exists) `.variants.csv` — depend
only on the document's *markup* (the `[[…]]` blocks and `[Name]` loops), not on the
registry, path resolution, or the mapping. Scan mode runs the same document parse but
writes *only* those two files, deferring `.raw.html`/`.annotated.html`/`.mapping.yaml`
to a later full ingest. This lets you hand the customer their forms up front — ideally
bundled with Leg -1's `.path-review.md` so all the hand-fill files arrive in one package
instead of two interruptions. The forms scan writes are byte-identical to the full
ingest's (shared parse); the later full ingest re-parses (deterministic, cheap) and
re-emits them. Note: scan still requires the doc-to-text conversion, so it runs at the
*front* of Leg 0, not before it — the block set can't be known without parsing the doc.

A conditional block may contain `{field}` placeholders. Because the Leg 4 plugin owns
conditional text (the template only outputs `${data.condN}`), those fields are resolved
**in Java**: Leg 4 concatenates the field's accessor into the conditional string
(quote system fields in the quote overload; policy system/custom fields in the policy
overload, custom fields via the segment type). Leg 3 reports such tokens as
"Delegated to plugin" rather than template-resolved. Leg 4 hard-fails if a field inside
a block has no `data_source` (run Leg 2 first); per-exposure, account, and
DataFetcher-sourced fields are TODO-flagged in the plugin report instead of wired.

**N-way variant blocks (the 50-state feature).** Instead of a binary present/absent
block, an author can write a single token — `[[$disclosureClause]]` — to mean "pick one of
N text variants by data at render time" (e.g. a different disclosure per state). The token
name becomes the block's stable join key end-to-end (`$doc.<token>` → `${data.<token>}` →
`put("<token>", …)`), replacing the positional `condN` for that block. For each such token
Leg 0 also writes a pre-filled `.variants.csv` stub (`placeholder, when, text` — row order
is priority, a blank/`*`/`else` `when` is the default row). The customer fills it in Excel
("Save As → CSV UTF-8"). At `--parse-conditional-form` time the sibling CSV is auto-detected
and normalised: each `when` is parsed by the condition DSL (`condition_dsl.py`), bare leaf
names resolve to full accessors against the registry, and the variants/default/scope merge
into the block in `.conditional-registry.yaml`. A validation error (bad condition, missing
default, mixed scope, type mismatch) is reported and the registry is **not** written. Leg 4
then emits an `if`/`else if`/`else` chain (first match wins, `Objects.equals`/`compareTo`,
null-safe) selecting the variant text — field placeholders inside each variant are wired the
same way as binary blocks.

When the conditional form is returned, run `leg0_ingest.py --parse-conditional-form` to
produce `.conditional-registry.yaml`. Leg 2 reads this registry automatically if it exists
alongside the mapping file. If the conditional form is skipped, Leg 2 still runs — the
`$doc.condN` placeholders in the template will remain unresolved until the registry is
provided.

### Starting from an HTML mockup (Leg 1 path)

Leg 1 (`convert.py`) reads an HTML file annotated with `{{variable_name}}` placeholders
and `*loop_name*` markers and produces `.mapping.yaml` with TBD placeholders and an
auto-detected `.conditional-registry.yaml` derived from the HTML structure. This path
is used when the document owner is comfortable editing HTML directly instead of Word.

### Path-matching and review (Leg 2)

Leg 2 (`leg2_fill_mapping.py`) reads the `.mapping.yaml` together with
`registry/path-registry.yaml` and (if present) `sdk-schema-index.yaml`. It queries the
registry for every `$TBD_*` token, scores candidates by semantic similarity and
confidence, then writes the suggestions back into the `.mapping.yaml` in-place. It also
emits `.review.md` — a human-readable confidence breakdown grouped by high / medium /
low. Review this file before running Leg 3 if any medium or low confidence matches exist.

### Template finalisation (Leg 3)

Leg 3 (`leg3_substitute.py`) reads the enriched `.mapping.yaml` and produces the final
`.final.vm` Velocity template by substituting all resolved `$TBD_*` tokens with their
confirmed Socotra paths. Any tokens that could not be resolved remain as `$TBD_*` in the
output and are listed in `.leg3-report.md`.

### Plugin generation (Leg 4)

Leg 4 (`leg4_generate_plugin.py`) branches off the same `.mapping.yaml` used by Leg 3 —
not off `.final.vm`. It reads every resolved path in the mapping and generates a
compile-correct `{Product}DocumentDataSnapshotPluginImpl.java` that populates
`renderingData` at document snapshot time. If a Java file already exists in the output
directory, Leg 4 runs in additive mode: it only adds missing keys and never removes
existing ones. The `.plugin-report.md` shows which paths were validated against the
customer JARs and whether the compile check passed.

### Deploying to Socotra

Both `.final.vm` and `SnapshotPlugin.java` are deployed manually to `socotra-config/`.
The `.vm` file goes under the `documents/` tree; the Java file goes under
`plugins/java/`. Deploy only these two files — no product config JAR rebuild is needed.
This is the hot-swap loop: author → pipeline → deploy `.vm` + `.java` → done.
