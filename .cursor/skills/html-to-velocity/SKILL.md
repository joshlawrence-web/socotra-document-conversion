---
name: html-to-velocity
description: Convert an HTML mockup (with `{{name}}` placeholders and optional `*loopname*` loop markers) into a Socotra-flavored Velocity template plus a YAML variable mapping file for later manual data-source assignment. Use this whenever the user wants to turn an HTML document, mockup, or draft template into a Velocity (.vm) template, prep a Socotra document template, scaffold placeholder variables, or produce a mapping file for a human to fill in. Trigger on phrases like "convert this HTML to a velocity template", "turn this mockup into a Socotra template", "generate the template and mapping file", or any reference to an .html file that needs to become a template with loops and variables — even when the user doesn't explicitly say "velocity".
---

# html-to-velocity

## For demos and team use: go through `pipeline-orchestrator`

This is an internal pipeline tool. If the user's message does **not** contain `RUN_PIPELINE`
(case-insensitive), **do not run the conversion**. Instead print:

```
For demos and production runs, please use the pipeline-orchestrator skill.

Quick start:
  RUN_PIPELINE leg1 input=samples/input/your-file.html output=samples/output

  RUN_PIPELINE leg1+leg2 input=samples/input/your-file.html registry=registry/path-registry.yaml output=samples/output

See .cursor/skills/pipeline-orchestrator/SKILL.md for the full invocation format.
```

Then stop. If the user is asking a question about what this skill does, explain it (see
"If a user asks what this skill does" below) but do not run.

If `RUN_PIPELINE` IS present in the message, continue with normal execution below.

---

## What this skill does

Given one HTML input file, produce three outputs inside a per-document subfolder:

1. **`<stem>.vm`** — the Velocity template, written in the Socotra dialect (`$data.*`, `#if`, `#foreach`, `#end`). Every placeholder is emitted as `$TBD_<name>` so it's immediately obvious which fields still need a real data source.
2. **`<stem>.mapping.yaml`** — a human-friendly YAML file listing every variable and loop, with context (nearest label/heading, line number, type, placeholder). Each entry has an empty `data_source:` field for a human to fill in during the manual mapping step.
3. **`README.md`** — an artifact guide describing every file the pipeline produces for this document (written once; not overwritten on re-runs).

The Velocity template is **not expected to render as-is** — it's an intermediate artifact. A follow-up skill will rewrite the `$TBD_*` placeholders to real `$data.*` paths once the mapping YAML has been filled in by a human.

## If a user asks what this skill does

When a user asks something like "what does this skill do?", "what is html-to-velocity?", "explain this to me", or "how does this work?", respond with the following:

---

**html-to-velocity** is Leg 1 of a three-step pipeline that turns an HTML document mockup into a live Socotra document template.

You give it an HTML file where the dynamic fields are marked with `{{double-curly-brace}}` placeholders and repeating sections are tagged with `*loopname*` markers. The skill converts that into two files:

- **`<stem>.vm`** — a Velocity template in Socotra's format (`$data.*`, `#foreach`, `#if`). Every field that still needs a real data path is written as `$TBD_fieldname` so nothing is silently wrong.
- **`<stem>.mapping.yaml`** — a catalogue of every placeholder and loop, with context about where each one appears in the HTML (nearest label, line number, parent element). Every `data_source:` field is blank — filling those in is the next step.

It also generates a `README.md` in the output folder that explains all the files produced across the full pipeline.

**What it does not do:** it never guesses at real `$data.*` paths. That requires product-specific knowledge handled by the next skill (Leg 2, mapping-suggester).

**What comes next:**
1. Review `<stem>.report.md` for any warnings about the HTML structure.
2. Run the **mapping-suggester** skill to get path suggestions for every `$TBD_*` placeholder.
3. After you confirm the suggestions, run **Leg 3 (Substitution Writer)** to produce the final renderable template.

---

## When to use

- The user hands over an HTML file and wants it turned into a Velocity template.
- The user mentions "Socotra document template", "renderingData", or "$data.*".
- The user wants placeholder variables scaffolded so a human can later map them to real data fields.
- The user asks for a "variable mapping file" or "YAML mapping" alongside a template.

## Inputs

A single HTML file. Conventions the user is expected to follow in the source:

- **Variables:** `{{varname}}` inside text content or attribute values. Names should be `[a-zA-Z_][a-zA-Z0-9_]*`.
- **Explicit loop markers:** `*loopname*` as text inside (or directly before) the container that should repeat — e.g. a `<tbody>` that holds one template `<tr>`, or a `<ul>` with one template `<li>`. The marker itself is stripped from the output.
- **Implicit loops:** a container with two or more siblings of the same tag (e.g. two `<tr>` rows, three `<li>` items, three `<div class="card">` items) will be **auto-detected** as a loop. Only the first child is kept as the template; others are discarded with a note in the YAML.

## Outputs

All outputs are written to `Samples/Output/<stem>/` (or to `<output-dir>/<stem>/` if `--output-dir` is specified). The skill creates the subdirectory automatically if it does not exist.

- `<stem>.vm` — the Velocity template
- `<stem>.mapping.yaml` — the variable mapping file
- `README.md` — artifact guide for this document (written on first run; skipped if the file already exists)

## How to run

The conversion is done by a bundled Python script. Invoke it from the skill directory or anywhere on disk:

```bash
python3 <skill-path>/scripts/convert.py <path-to-input.html> [--output-dir <dir>] [--no-conditionals] [--registry <path>]
```

### CLI flags

- `--output-dir <dir>` — write outputs to `<dir>/<stem>/` instead of `Samples/Output/<stem>/`. The `/<stem>/` subfolder is appended automatically.
- `--no-conditionals` — suppress `#if($TBD_*)` wrapping around variable-bearing blocks.
- `--auto-detect-loops` — also convert sibling-repetition loops (off by default — Mustache-only is safer).
- `--registry <path>` — explicit path to the registry YAML. Drives the `context.loop_hint` tagging described below. If omitted, the script walks the input file's directory and its ancestors looking for `registry/path-registry.yaml` then `path-registry.yaml`; if none is found, loop hints are not emitted (graceful degrade).
- `--batch <file1> [file2 ...]` — process multiple HTML files in a single invocation.
  `--output-dir` is treated as the parent directory; each file writes to `<output-dir>/<stem>/`.
  The registry file (if provided or auto-located) is loaded once and shared across all inputs.
  Incompatible with the single-file positional argument — use one or the other.

If `beautifulsoup4` or `pyyaml` aren't installed, install them first:

```bash
pip install beautifulsoup4 pyyaml --break-system-packages
```

The script is self-contained — it does not need to be imported. Call it as a subprocess and then read the two output files back.

### Batch example (all files in a folder)

```bash
python3 .cursor/skills/html-to-velocity/scripts/convert.py \
    --batch samples/input/*.html \
    --output-dir samples/output \
    --registry registry/path-registry.yaml
```

Each input file `<stem>.html` produces `samples/output/<stem>/<stem>.vm`, `<stem>.mapping.yaml`, and `<stem>.report.md`. The registry is read once for the entire batch. Terminal output prints one summary line per file, then a combined count:

```
✓ claim-form           → samples/output/claim-form/  (12 vars, 3 loops)
✓ renewal-notice       → samples/output/renewal-notice/  (8 vars, 1 loop)
Batch complete: 2 files, 20 vars, 4 loops
```

## Conversion rules

### 1. Variables

Each `{{name}}` token becomes `$TBD_<name>`. If the token appears inside a loop template (see below), it becomes `$<iterator>.TBD_<name>` instead, scoped to the loop iterator.

Every placeholder is emitted with the `$TBD_` prefix — never bare `$data.*` — so that missing mappings stand out visually and downstream tooling (or a grep for `TBD_`) can catch them.

### 2. Explicit loops (`*loopname*`)

When a `*loopname*` marker appears in text:

1. Walk up from the marker to the nearest loop-friendly container (`tbody`, `ul`, `ol`, `table`, `section`, or a `div` with multiple same-tagged children).
2. Keep the **first tag child** of that container as the loop template.
3. Discard any sibling copies (they're just mockup filler).
4. Remove the `*loopname*` text.
5. Replace `{{x}}` inside the template with `$<singular>.TBD_x`, where `<singular>` is derived from the loop name (e.g. `insureds` → `insured`, `policies` → `policy`). If no clean singular can be derived, fall back to `<loopname>_item`.
6. Insert Velocity directives around the template:

   ```
   #foreach ($insured in $TBD_insureds)
     <tr> ... </tr>
   #end
   ```

### 3. Auto-detected loops

For any container (`tbody`, `ul`, `ol`, `table`, `section`, `div`) whose direct tag children are all the same tag and number ≥ 2, treat as a loop candidate **unless** the container is already explicitly marked. Pick a loop name by this priority:

1. Nearest preceding `<h1>`–`<h6>` text, slugified and pluralized if needed
2. The container's `class` attribute, slugified
3. `items` (last resort)

Then apply the same transform as for explicit loops. Record in the YAML that the loop was auto-detected so the reviewer can confirm or rename it.

### 4. Nested loops

Loops inside loops are supported. The script processes loops **deepest first**, so an inner loop's template is transformed before the outer loop sees it. Inner loops pick up their own iterator; variables scoped to the inner iterator reference `$<inner>.TBD_x`.

### 5. Conditional wrapping (`#if`)

For variables that are **not** inside a loop, wrap the nearest block-level ancestor (`<p>`, `<li>`, `<tr>`, `<h1>`–`<h6>`, `<div>`) with `#if($TBD_<var>)` / `#end`. If the block contains multiple variables, wrap with `#if($TBD_v1 && $TBD_v2)` so the whole block only renders when all its inputs are set — mirroring the style of the Socotra reference template.

Pass `--no-conditionals` to suppress this behaviour when the HTML is structured such that every block is mandatory.

### 6. Loop context (`context.loop`) and loop hints (`context.loop_hint`)

The mapping YAML carries two keys that describe a variable's relationship to a Socotra iterable (an exposure like `Vehicle+` / `Driver+`, or a data-extension array). Both are additive — the rest of the `context` object is unchanged.

**`context.loop`** is set on every loop field (a variable that lives inside a detected `{{#name}}...{{/name}}` block or an auto-detected sibling-repetition loop). The value is the loop's name as it appears in the template (the Mustache section name or the derived auto-detect name, e.g. `other_parties`, `witnesses`, `damaged_items`). Loop fields are already nested under their loop's `fields:` list in the YAML; `context.loop` just makes the membership explicit so downstream tooling (Leg 2) can reason about scope satisfaction uniformly without walking YAML nesting.

**`context.loop_hint`** is emitted on top-level (non-loop) variables whose name signals they probably belong inside a Socotra iterable's scope but are NOT wrapped in a detected loop block in the current template. The value is the canonical iterable `name` from `path-registry.yaml` (e.g. `Vehicle`, `Driver`). Leg 2's mapping suggester treats `loop_hint` as a reasoning aid, not a scope proof — variables with a `loop_hint` that don't also live under a matching `#foreach` are flagged as scope violations with a `next_action: restructure-template` recommendation.

**The heuristic (current):** name-prefix only. For each iterable in the registry, its lowercase `name` + `_` (e.g. `vehicle_`, `driver_`) is used as a prefix pattern. A top-level variable whose lowercased name starts with that prefix gets `loop_hint: <IterableName>`. This deliberately stays conservative:

- ✓ `vehicle_year`, `vehicle_make`, `vehicle_model`, `vehicle_vin`, `vehicle_registration` → `loop_hint: Vehicle`
- ✓ `driver_first_name`, `driver_last_name`, `driver_license_number` → `loop_hint: Driver`
- ✗ `estimated_damage` (under an "Insured vehicle" heading but no iterable prefix in the name) → no `loop_hint`

If the template uses a name that doesn't carry an iterable prefix even though the field semantically belongs inside an iterable (e.g. a variable literally named `year` sitting under an "Insured vehicle" heading), the current heuristic will NOT tag it. The human reviewer catches these cases via the Leg 2 `.review.md` — Leg 1 prefers honest "I don't know" gaps over noisy false-positive hints.

**Future heading-based fallback (not implemented — flagged for revisit):** if real samples surface variables that need loop-hinting but lack a prefix, the heuristic can grow a heading-match fallback. That fallback must respect the disambiguation rules in the synonym table below so it doesn't generate false positives for claim-level fields (e.g. `estimated_damage` under "Insured vehicle").

#### Iterable synonyms (documentation — not consumed by the script)

This table records which heading/label phrases a human reviewer should understand as referring to each iterable. It is NOT read by `convert.py`; it exists so reviewers can audit the heuristic's behavior and extend it cleanly. The script consumes iterables directly from `path-registry.yaml`'s top-level `iterables:` list — only the canonical `name` (e.g. `Vehicle`) and derived prefix (e.g. `vehicle_`) drive matching today.

| Iterable | Canonical `name` | Prefix used (current) | Heading phrases that imply this iterable (for future fallback / human review) |
|---|---|---|---|
| Vehicle | `Vehicle` | `vehicle_` | "Insured vehicle", "Vehicle", "Vehicles", "Car", "Auto", "Unit" |
| Driver | `Driver` | `driver_` | "Driver", "Drivers", "Insured driver", "Named driver", "Operator" |

If you add a new iterable to the product config (e.g. a `Driver+` data-extension array under Vehicle), regenerate `path-registry.yaml` and add a row to this table so reviewers know which headings to expect.

## YAML mapping schema

The mapping file is designed to be edited by a human. Every
`<stem>.mapping.yaml` carries `schema_version: '1.0'` as its very
first key — this is the pipeline-wide artifact contract documented in
`SCHEMA.md` at the repo root (MAJOR / MINOR compatibility rules apply).
Downstream tools (the mapping suggester) refuse to run against a
MAJOR they do not support. Top-level structure:

```yaml
schema_version: '1.0'
source: sample-policy.html
generated_at: 2026-04-20T12:00:00Z
variables:
  - name: policyNumber
    placeholder: $TBD_policyNumber
    type: variable
    context:
      nearest_label: "Reference"
      parent_tag: strong
      line: 23
    data_source: ""   # human fills in e.g. $data.policyNumber
  - name: vehicle_year
    placeholder: $TBD_vehicle_year
    type: variable
    context:
      nearest_label: "Insured vehicle"
      parent_tag: p
      line: 90
      loop_hint: Vehicle     # Phase 4 — name starts with `vehicle_`; Leg 2 will flag scope violation
    data_source: ""

loops:
  - name: insureds
    placeholder: $TBD_insureds
    iterator: $insured
    container: tbody
    detection: explicit      # or: auto
    context:
      nearest_heading: "Insureds"
      line: 31
    data_source: ""           # human fills in e.g. $data.insureds
    fields:
      - name: lastName
        placeholder: $insured.TBD_lastName
        context:
          column_header: "Name"
          line: 34
          loop: insureds      # Phase 4 — explicit loop membership
        data_source: ""       # human fills in e.g. $insured.data.lastName
      - name: location
        placeholder: $insured.TBD_location
        context:
          column_header: "Location"
          line: 35
          loop: insureds
        data_source: ""
```

Rules:

- Loop fields are nested **under** their loop so the file structure mirrors the template.
- `context` should be brief and specific enough that a human can locate the field in the original HTML without opening the browser: nearest label, column header, or parent tag are all fair game.
- `line:` is the sourceline in the input HTML where the token was found (BeautifulSoup `sourceline`).
- `context.loop` (loop fields): explicit name of the Mustache section / auto-detected loop the field lives inside. Always present on loop fields; redundant with the YAML nesting but kept so Leg 2 can treat scope satisfaction uniformly.
- `context.loop_hint` (top-level variables only): canonical iterable `name` from `path-registry.yaml`, emitted when the variable's lowercase name starts with `<iterable_name>_`. Absent when no iterable prefix matches or when no registry is available. Leg 2 treats `loop_hint` as a reasoning aid, not scope satisfaction.
- `data_source:` is always emitted empty — this is the field the human fills in during the downstream mapping step.

## Example

See `examples/sample-policy.html`, `examples/sample-policy.vm`, and `examples/sample-policy.mapping.yaml` for a worked example against a Socotra-style policy summary document.

## Output folder and README

After the conversion rules have been applied and before writing any file:

1. **Derive `stem`** from the input filename by stripping the extension (e.g. `claim-form.html` → `claim-form`).
2. **Create `Samples/Output/<stem>/`** (or `<output-dir>/<stem>/`) if it does not already exist.
3. **Write `<stem>.vm`** and **`<stem>.mapping.yaml`** into that subfolder.
4. **Write `README.md`** into that subfolder — but only if the file does not already exist there. The README content is fixed (see template below). Never overwrite an existing README on re-runs.

### README template

The `README.md` written into `Samples/Output/<stem>/` must use the following content, substituting the actual `<stem>` value throughout:

```markdown
# <stem> — pipeline outputs

This folder contains all artifacts produced by the HTML → Velocity pipeline
for `<stem>.html`. Files are generated by two skills run in sequence.

## Leg 1 — html-to-velocity

| File | What it is |
|---|---|
| `<stem>.vm` | Velocity template. Every unfilled placeholder is `$TBD_*`. Not renderable yet — run Leg 2 then Leg 3 to resolve the placeholders. |
| `<stem>.mapping.yaml` | Variable catalogue. One entry per placeholder with context (label, line, parent tag). `data_source:` fields are blank — Leg 2 fills them. |
| `<stem>.report.md` | Sanity report. Lists cross-scope name reuse and unlabeled variables found during conversion. Review before running Leg 2. |

## Leg 2 — mapping-suggester

| File | What it is |
|---|---|
| `<stem>.suggested.yaml` | Suggested mapping. A copy of `mapping.yaml` with `data_source`, `confidence`, and `reasoning` filled in by the suggester. **Intermediate artifact — human must review and confirm before Leg 3.** |
| `<stem>.review.md` | Human review report. Sections: blockers (low confidence), assumptions to confirm (medium), cross-scope warnings, and done (high confidence). **Start here after Leg 2 runs.** |
| `<stem>.suggester-log.jsonl` | Append-only telemetry. One JSON record per placeholder per run, plus a run summary. Observational — no downstream pipeline step reads it yet; used for future skill-lesson promotion. |

## What to do next

1. Read `<stem>.report.md` — fix any cross-scope or unlabeled issues in the HTML before proceeding.
2. Run the **mapping-suggester** skill on `<stem>.mapping.yaml`.
3. Open `<stem>.review.md` — resolve every blocker and confirm every assumption.
4. Edit `<stem>.suggested.yaml` to apply your decisions, then save it as `<stem>.mapping.yaml`.
5. Run **Leg 3 (Substitution Writer)** to produce the final renderable `.vm`.
```

## Errors and edge cases

- **Empty `data_source:` values** are expected — they are the signal to the downstream mapping skill that work remains.
- **Unmatched loop markers** (`*name*` with no plausible container nearby) are left in the output and noted in the YAML under `warnings:`.
- **Auto-detected loops with low confidence** (e.g. only 2 identical siblings with no heading) are still emitted but flagged `detection: auto` in the YAML so the human can confirm.
- **Variables with duplicate names** are deduplicated in the YAML — they appear once but their occurrences are tracked in `context.occurrences`.

## Design notes

This skill is intentionally dumb about data semantics. It produces `$TBD_*` placeholders rather than guessing at `$data.*` paths because the real data paths depend on product-specific snapshot plugins at Socotra — guessing wrong is worse than forcing a human pass. The YAML mapping file is where intent is captured.
