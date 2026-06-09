# Leg 0 — Field Extraction + Pipeline Wiring

**Status:** Complete  
**Created:** 2026-06-08  
**Predecessor:** [Leg0-document-ingestion](../Leg0-document-ingestion/00-plan.md)  
**History:** [history.md](./history.md) (append-only)

---

## START HERE (implementing agent)

This plan extends `scripts/leg0_ingest.py` (created in the predecessor plan) with:

1. **Field extraction** — find all `{field_name}` tokens in the raw HTML → emit a
   pre-populated fields YAML that feeds Leg 2 directly
2. **Conditional extraction** — find all `[[conditional text]]` blocks → emit a
   human-readable conditional form for the customer to fill in
3. **Pipeline wiring** — wire `leg0_ingest.py` into `agent_tools.py` and `agent.py`
   so `RUN_PIPELINE leg0+leg2+leg3` is a valid invocation

**Read in this order:**

1. This file — §2 (decisions), §3 (task list)
2. `scripts/leg0_ingest.py` — output of Plan 2 (`.raw.html` writer)
3. `scripts/leg2_fill_mapping.py` — understand the `.mapping.yaml` input format Leg 2 expects
4. `.cursor/skills/html-to-velocity/scripts/convert.py` — `extract_conditional_blocks()` — see
   how Leg 1 currently handles `[single bracket]` blocks (this plan uses `[[double bracket]]`)
5. `scripts/agent_tools.py` — `run_leg1()`, `run_leg2()` — understand the pipeline contract
6. `scripts/agent.py` — `RUN_PIPELINE` dispatch — understand how to add `leg0`

**Do not** modify Leg 1 or Leg 2 internals — wire to their existing interfaces only.

---

## 1. Background

### Customer-facing conventions (standardised)

| Notation | Meaning | Who resolves it |
|---|---|---|
| `{field_name}` | Data field — a Socotra SDK path will be suggested | Pipeline (Leg 2) |
| `[[conditional text]]` | Conditional text block — customer specifies the trigger condition | Customer (fills conditional form) |

These are **inline, in the customer's Word/PDF**. No separate table, no external markup.

### Two outputs handed back to the customer

1. **Fields YAML** (`<stem>.fields.yaml`) — list of extracted `{field_name}` tokens,
   formatted as a pre-populated Leg 2 input. Customer does not need to edit this.

2. **Conditional form** (`<stem>.conditional-form.md`) — numbered list of extracted
   `[[...]]` blocks with a blank line for the customer to fill in the triggering
   Socotra condition. Customer fills this in and returns it.

### What feeds into the pipeline

| Leg 0 output | Fed into |
|---|---|
| `{stem}.raw.html` | Leg 1 (existing path, unchanged) |
| `{stem}.fields.yaml` | Leg 2 — pre-populated mapping, skips LLM field discovery |
| Filled `{stem}.conditional-form.md` | Parsed back into `{stem}.conditional-registry.yaml` → Leg 4 |

---

## 2. Decisions

| # | Topic | Decision |
|---|--------|----------|
| E1 | `{field_name}` regex | `\{([a-zA-Z_][a-zA-Z0-9_]*)\}` — single curly braces, valid identifier chars only. Excludes `{}` (empty), `{123}` (starts with digit), `{{ }}` (double-brace Velocity syntax). |
| E2 | `[[conditional]]` regex | `\[\[(.+?)\]\]` — non-greedy, no newlines. Double square brackets only. Single `[...]` brackets are left untouched (natural document text). |
| E3 | Fields YAML format | Matches the `variables:` schema in `.mapping.yaml`. Each entry: `name`, `token` (e.g. `$TBD_field_name`), `data_source: ""`, `confidence: ""`. Leg 2 reads this as a pre-seeded mapping and fills in paths. |
| E4 | Conditional form format | Markdown. Numbered blocks, source text quoted, blank `Condition:` line for customer. One file per form. Customer fills in the `Condition:` field and returns the file. |
| E5 | Conditional form → registry | A separate parser `_parse_conditional_form(md_path)` reads the filled-in form and emits `{stem}.conditional-registry.yaml`. This is a distinct step — run after the customer returns the form. |
| E6 | HTML annotation | Replace `{field_name}` in the `.raw.html` with `$TBD_field_name` and `[[cond text]]` with `$doc.condN` tokens. Write the annotated file as `{stem}.annotated.html`. This becomes the Leg 1 / Leg 3 input. |
| E7 | Duplicate field names | Deduplicate — same `{field_name}` appearing multiple times emits one entry in the fields YAML. Track all occurrences in a `locations` comment field for reference. |
| E8 | Pipeline invocation | `RUN_PIPELINE leg0 input=<path>` runs ingestion + extraction only (Plans 2 + 3). `RUN_PIPELINE leg0+leg2+leg3` runs the full pre-pipeline customer flow through to final template. |

---

## 3. Task list

Check boxes when done; append a handoff to [history.md](./history.md).

---

### E-T1 — Field extraction from raw HTML

**Goal:** Implement `extract_fields(html: str) -> list[dict]` in `scripts/leg0_ingest.py`.

- Apply regex `E1` to the HTML text (strip HTML tags first with BeautifulSoup `.get_text()`)
- Deduplicate by field name (decision E7)
- Return list of `{name, token, data_source, confidence}` dicts

Also implement `annotate_fields(html: str, fields: list[dict]) -> str` — replaces each
`{field_name}` in the HTML with `$TBD_field_name` (the Velocity token Leg 3 expects).

**Files:**
- `scripts/leg0_ingest.py` — two new functions

**Definition of done:**
- Given HTML containing `{policy_number}` and `{insured_name}`, returns two-entry list
- Annotated HTML contains `$TBD_policy_number`, `$TBD_insured_name`

---

### E-T2 — Conditional block extraction from raw HTML

**Goal:** Implement `extract_conditionals(html: str) -> list[dict]` in `scripts/leg0_ingest.py`.

- Apply regex `E2` to HTML text
- Assign sequential IDs starting at 1 (local to this form)
- Return list of `{id, source_text}` dicts

Also implement `annotate_conditionals(html: str, blocks: list[dict]) -> str` — replaces
each `[[text]]` in the HTML with `$doc.condN` (the token Leg 3 / Leg 4 expects).

**Files:**
- `scripts/leg0_ingest.py` — two new functions

**Definition of done:**
- Given HTML with `[[This coverage applies in CA]]`, returns `{id: 1, source_text: "This coverage applies in CA"}`
- Annotated HTML contains `$doc.cond1`

---

### E-T3 — Write fields YAML

**Goal:** Implement `write_fields_yaml(fields: list[dict], output_path: Path) -> None`.

Output format (must match what `leg2_fill_mapping.py` reads as pre-seeded input):

```yaml
# leg0 extracted fields — review before running leg2
product: ""
variables:
  - name: policy_number
    token: $TBD_policy_number
    data_source: ""
    confidence: ""
  - name: insured_name
    token: $TBD_insured_name
    data_source: ""
    confidence: ""
```

**Files:**
- `scripts/leg0_ingest.py`

**Decision needed before implementing:** Confirm with `leg2_fill_mapping.py` the exact
field names it expects in a pre-seeded mapping file. If the format differs, add a
`_normalise_for_leg2()` step.

---

### E-T4 — Write conditional form (customer-facing)

**Goal:** Implement `write_conditional_form(blocks: list[dict], output_path: Path) -> None`.

Output format:

```markdown
# Conditional Text Review — {stem}

For each block below, fill in the Socotra condition that determines when this text appears.
Use Socotra field paths (e.g. `segment.state() == "CA"` or `quote.fieldName() != null`).
Return this file to your implementation contact when complete.

---

## Block 1

> This coverage applies to CA residents only.

Condition: 

---

## Block 2

> Includes roadside assistance for covered vehicles.

Condition: 

---
```

**Files:**
- `scripts/leg0_ingest.py`

---

### E-T5 — Parse filled conditional form → `conditional-registry.yaml`

**Goal:** Implement `parse_conditional_form(md_path: Path) -> list[dict]` and
`write_conditional_registry(blocks: list[dict], output_path: Path) -> None`.

Reads the customer-returned markdown form. Extracts:
- Block ID (from `## Block N` heading)
- Source text (from blockquote `>`)
- Condition (from `Condition:` line — everything after the colon, stripped)

Writes `{stem}.conditional-registry.yaml` in the format `load_conditional_registry()` in
`leg4_generate_plugin.py` expects:

```yaml
- id: 1
  source_text: "This coverage applies to CA residents only."
  conditions:
    - 'segment.state().equals("CA")'
  operator: AND
```

**Files:**
- `scripts/leg0_ingest.py` — parser + writer

**CLI flag:** `leg0_ingest.py --parse-conditional-form <filled-form.md> --output-dir <dir>`
(separate invocation from conversion — runs after customer returns the form)

---

### E-T6 — Wire into `agent_tools.py`

**Goal:** Add `run_leg0(input_path, output_dir)` to `scripts/agent_tools.py`.

- Calls `leg0_ingest.py` via `subprocess.run`
- Returns `{ok, returncode, stderr, artifacts: [raw_html, annotated_html, fields_yaml, conditional_form]}`
- Follows the same pattern as `run_leg1()`, `run_leg2()`, etc.

**Files:**
- `scripts/agent_tools.py`

---

### E-T7 — Wire into `agent.py` dispatch

**Goal:** Add `leg0` as a valid leg in `RUN_PIPELINE` dispatch.

Supported invocations:
- `RUN_PIPELINE leg0 input=<path> output=<dir>` — conversion + extraction only
- `RUN_PIPELINE leg0+leg2+leg3 input=<path> registry=<path> output=<dir>` — full customer flow

For `leg0+leg2+leg3`: Leg 0 output (annotated HTML + fields YAML) feeds Leg 2's
pre-seeded mapping input. Leg 2 suggests SDK paths. Leg 3 substitutes.

**Files:**
- `scripts/agent.py`

---

### E-T8 — CLAUDE.md trigger phrases

**Goal:** Add Leg 0 trigger phrases and customer workflow to `CLAUDE.md`.

Include:
- Trigger phrases for `RUN_PIPELINE leg0`
- Trigger phrases for `RUN_PIPELINE leg0+leg2+leg3`
- Instruction for `--parse-conditional-form` step (after customer returns the form)

**Files:**
- `CLAUDE.md`

---

## 4. Recommended order

1. **E-T1** — field extraction (foundation)
2. **E-T2** — conditional extraction
3. **E-T3** — fields YAML writer (confirm format against leg2 first)
4. **E-T4** — conditional form writer
5. **E-T5** — conditional form parser
6. **E-T6** — agent_tools wiring
7. **E-T7** — agent.py dispatch
8. **E-T8** — CLAUDE.md

---

## 5. Repo signposting

| Path | Role |
|------|------|
| `scripts/leg0_ingest.py` | Extend with extraction functions (Plan 2 creates the base) |
| `scripts/leg2_fill_mapping.py` | Read to confirm pre-seeded mapping format (before E-T3) |
| `scripts/agent_tools.py` | Add `run_leg0()` |
| `scripts/agent.py` | Add `leg0` to `RUN_PIPELINE` dispatch |
| `scripts/leg4_generate_plugin.py` | `load_conditional_registry()` — confirm YAML format before E-T5 |
| `CLAUDE.md` | Add Leg 0 trigger phrases |

---

## 6. Customer flow summary (for documentation)

```
Customer provides:  policy-form.docx (with {field} and [[conditional]] markup)
                         ↓
leg0 runs:          policy-form.raw.html        (pipeline input)
                    policy-form.annotated.html  (Leg 1 / Leg 3 input)
                    policy-form.fields.yaml     (Leg 2 pre-seeded input)
                    policy-form.conditional-form.md  (→ customer)
                         ↓
Customer fills in:  policy-form.conditional-form.md (conditions per block)
                         ↓
leg0 --parse-conditional-form:
                    policy-form.conditional-registry.yaml  (→ Leg 4)
                         ↓
Pipeline runs:      leg2 → leg3 → leg4
```
