---
name: mapping-suggester
description: >
  Given a Leg 1 `.mapping.yaml` (with blank `data_source` fields) and a
  `registry/path-registry.yaml` produced by `extract_paths.py`, runs
  `scripts/leg2_fill_mapping.py` to suggest real Socotra Velocity paths for
  every `$TBD_*` variable and loop.  The script handles all deterministic
  matching (Rules 1-6) and writes the full `.suggested.yaml` + `.review.md`
  + `.suggester-log.jsonl`.  The AI then reads the script output and adds
  narrative depth to blockers/assumptions in `full` mode, then updates
  `skill-lessons.yaml`.  Use whenever the user wants to map TBD placeholders
  to real Socotra paths, fill in a mapping file, or generate path suggestions
  from a config.  Trigger on phrases like "suggest paths", "fill in the
  mapping", "map the TBD variables", "run the suggester", or any reference
  to a `.mapping.yaml` file that needs its `data_source` fields populated.
---

# mapping-suggester

## For demos and team use: go through `pipeline-orchestrator`

This is an internal pipeline tool. If the user's message does **not** contain `RUN_PIPELINE`
(case-insensitive), **do not run the suggester**. Instead print:

```
For demos and production runs, please use the pipeline-orchestrator skill.

Quick start:
  RUN_PIPELINE leg2 mode=terse mapping=samples/output/<stem>/<stem>.mapping.yaml registry=registry/path-registry.yaml

  RUN_PIPELINE leg2 mode=batch mapping=[samples/output/a/a.mapping.yaml, samples/output/b/b.mapping.yaml] registry=registry/path-registry.yaml

See .cursor/skills/pipeline-orchestrator/SKILL.md for the full invocation format.
```

Then stop. Questions about what this skill does are fine to answer — just don't execute.

If `RUN_PIPELINE` IS present in the message, continue with normal execution below.

---

## What this skill does

Leg 2 of the HTML → Velocity pipeline. Takes the two artifacts from upstream:

1. **`<stem>.mapping.yaml`** — produced by `html-to-velocity` (Leg 1). Contains
   every `$TBD_*` variable and loop with context (nearest label, parent tag,
   line number). All `data_source:` fields are blank.

2. **`registry/path-registry.yaml`** (or explicit `--registry` path) — produced by `extract_paths.py`. The authoritative
   flat catalogue of every valid Velocity path derived from the product's
   `socotra-config/`. This is the **only** source of truth for valid paths.
   Never suggest a path that is not in the registry.

Outputs:

- **`<stem>.suggested.yaml`** — a copy of the mapping YAML with every
  `data_source:` field pre-filled with the best matching path from the registry,
  plus `confidence` (high / medium / low) and `reasoning` for each suggestion.
  Fields the skill cannot match with confidence are left blank with
  `confidence: low` and a note explaining why.

The `.suggested.yaml` is an intermediate artifact for human review. The human
edits, confirms, or overrides each suggestion before the substitution step.

---

## Run modes

Resolve the active mode from the user's invocation before doing anything else.
If a mode keyword is present in the invocation, use it immediately and skip the
mode-selection prompt. If **no** keyword is present, **ask the user to pick a
mode** (see "Pre-Step — Mode selection" in "How to run" below) before
proceeding.

| Mode | Trigger keywords | Description |
|---|---|---|
| `full` | "full", "verbose" | Verbose reasoning, full shape probe, full review.md prose. Best for first runs and unfamiliar documents. |
| `terse` | "terse", "quick pass", "quick run" | Abbreviated outputs. Single-line reasoning, table-only review.md, one-line shape probe. ~50% fewer output tokens. |
| `batch` | "batch", "run on all files", or multiple `.mapping.yaml` paths given | Read the registry file once; process each mapping file sequentially in `terse` sub-mode; print a combined terminal summary. ~60% fewer total tokens for 4-doc runs. |
| `delta` | "delta", "re-run", "refresh", "only unconfirmed" | Skip entries whose `data_source` is already non-empty and does not contain `$TBD_`. Merge new suggestions into the existing `.suggested.yaml`. Report `N skipped, M suggested` in terminal summary. |

Mode-specific behavior overrides are listed in each step below where they apply.
A `batch` run runs `terse` automatically for every document in the batch.

---

## Inputs

| Artifact | How to obtain |
|---|---|
| `<stem>.mapping.yaml` | Run the `html-to-velocity` skill on your HTML file |
| `registry/path-registry.yaml` | Run `python3 .cursor/skills/mapping-suggester/scripts/extract_paths.py --config-dir <socotra-config/>` (default output; or pass `--output`). |
| `terminology.yaml` (optional, Phase E) | Repo root first, then sibling of the registry file (e.g. `registry/terminology.yaml`), or `--terminology <path>`. See `SCHEMA.md` → "Artifact: `terminology.yaml`". When absent, skip synonym lookup silently. |

Both mapping and registry files must be present before running this
skill; `terminology.yaml` is optional.

---

## Recognised context signals (v1.0 contract)

The mapping YAML carries a small, closed vocabulary of keys that the
suggester knows how to reason about. Anything else is **preserved but
unused** — keys pass through the pipeline verbatim and are listed under
"Unrecognised inputs" in `.review.md`.

| Key | Type | Meaning |
|---|---|---|
| `name` | string | Placeholder identifier (matches `field` in registry) |
| `placeholder` | string | Full `$TBD_*` token |
| `type` | enum | `variable` / `loop` / `loop_field` |
| `context.parent_tag` | string | HTML parent element |
| `context.nearest_label` | string | Closest label / heading text |
| `context.line` | int | Line number in source HTML |
| `context.loop` | string? | Enclosing loop name, if inside a `#foreach` |
| `context.loop_hint` | string? | Detected-but-not-wrapped loop name |
| `context.column_header` | string? | Table column header (for `<td>` context) |
| `context.container` | string? | Container element (`ul`, `tbody`, etc.) |
| `context.detection` | enum? | How Leg 1 detected this (`mustache`, `liquid`, `heuristic`) |

Any other keys are preserved but unused. The suggester MUST NOT drop
them. When encountered, they are reported under "Unrecognised inputs"
in the `.review.md` file with `next_action: needs-skill-update`.

See `SCHEMA.md` at the repo root for the full artifact contract,
including the compatibility rules (MAJOR / MINOR) that govern when this
vocabulary is allowed to grow.

---

## Quantifier semantics

Socotra uses a single-character suffix on `contents` tokens and
data-extension `type` strings to declare the cardinality of an element.
The same convention appears on the registry entries this skill consumes.

| Suffix | Meaning | Iterable? |
|---|---|---|
| *(none)* | Exactly one required | No |
| `!` | Exactly one, auto-created on validation | No |
| `?` | Zero or one | No (needs `#if` guard) |
| `+` | One or more | **Yes** |
| `*` | Any number | **Yes** |

The quantifier determines whether a given path is loopable. **Only elements
with `quantifier: '+'` or `'*'` can be the `data_source` of a `loops`
entry.** Singular elements (`''`, `'!'`, `'?'`) can only be referenced
directly.

Reference (local Socotra Buddy corpus):
`~/socotra-buddy/resources/derived/125949463fad41f0.md`.

---

## Modular companion files

| File | Status | When to read |
|---|---|---|
| `SKILL-matching.md` | **Reference only** (post-Stage-4) | Consult when debugging script behavior; NOT read during normal runs |
| `SKILL-output-formats.md` | **Reference only** (post-Stage-4) | Consult to understand the artifact format; script handles all formatting |
| `SKILL-full-mode.md` | Active — read in `full` mode | Before Step 2 in full mode, for narrative depth guidance on §3/§5/§6 |
| `SKILL-lessons.md` | Active — read at Step 3 | `skill-lessons.yaml` Phase D ledger write procedure |

> **Post-Stage-4 note:** `SKILL-matching.md` and `SKILL-output-formats.md` are the
> authoritative spec for the rules the script implements.  Read them when debugging
> script behavior, not during normal AI-skill runs.

---

## How to run

### Pre-Step — Mode selection (runs before everything else)

Before doing anything else, check whether the user's invocation contains
a mode keyword (see "Run modes" above). If it does, lock in that mode.
If **no mode keyword is present**, ask the user to choose one:

```
Which mode would you like to run?

  1  full   — Script runs + AI adds narrative depth to blockers/assumptions.
              Best for unfamiliar documents. Token cost: script matching + AI
              narrative paragraphs only (~60% lower than old full mode).

  2  terse  — Script runs + AI reads and reports. No narrative additions.
              Fastest. Use when you just need the suggested paths quickly.

  3  delta  — Re-run only. Skips confirmed entries; merges into existing
              .suggested.yaml.

  4  batch  — Multi-file. Processes several .mapping.yaml files in one go.

Reply with a number (1–4) or the mode name.
```

Wait for a valid mode; re-ask if ambiguous.  **Mode selection is mandatory.**

When mode is **`full`**, read `SKILL-full-mode.md` **now** for narrative
depth guidance.  For `terse`, `delta`, `batch`: do not read it.

---

### Step 0 — Run the script

Run `scripts/leg2_fill_mapping.py` to produce all three output artifacts:

```bash
python3 scripts/leg2_fill_mapping.py \
    --mapping <stem>.mapping.yaml \
    --registry registry/path-registry.yaml \
    --out Samples/Output/<stem>/<stem>.suggested.yaml \
    --review-out Samples/Output/<stem>/<stem>.review.md \
    --telemetry-log Samples/Output/<stem>/<stem>.suggester-log.jsonl \
    --mode <mode> \
    [--terminology terminology.yaml] \
    [--base-suggested <prior.suggested.yaml>]
```

The script handles: version checks, shape probe, Rules 1–6, feature flag
surfacing, provenance stamping, delta merge, and all three output artifacts.

If the script exits non-zero: print the error to the user and stop.  Do
**not** attempt to re-run the matching manually.

**`batch` mode:** invoke the script once per mapping file, then proceed
to Step 1 for each stem sequentially.

---

### Step 1 — Read the script's output

Read `<stem>.suggested.yaml` and `<stem>.review.md` produced by Step 0.

**Do NOT re-derive suggestions from scratch.**  The script's output is
authoritative.  Also locate `skill-lessons.yaml` at the repo root (optional).

---

### Step 2 — Review medium/low items (`full` mode only)

**`terse` / `delta` / `batch`:** skip this step.  Jump to Step 3.

**`full` mode** (read `SKILL-full-mode.md` if not already in context):

For each **`low`** item in §3 (Blockers): verify `next_action` is correct;
append a 1–3 sentence narrative paragraph explaining WHY this blocks Leg 3.

For each **`medium` + `confirm-assumption`** item in §4: add one sentence
if label/context gives stronger evidence for the assumption.

Do not change `data_source`, `confidence`, or `reasoning` — owned by script.

---

### Step 3 — Update `skill-lessons.yaml` (when the file exists)

If absent, skip silently.  Follow **`SKILL-lessons.md`** § "Step 4d procedure":
bump `seen_count` / `last_seen` / `observed_in` on matched lessons; append
new `observed` rows for unmatched patterns.  Never flip `status`, author
`candidate_promotion`, or edit `pattern` / `current_rule`.

---

### Step 4 — Print the terminal summary

```
Suggested mapping written: Samples/Output/<stem>/<stem>.suggested.yaml
Review report written:     Samples/Output/<stem>/<stem>.review.md
Telemetry appended:        Samples/Output/<stem>/<stem>.suggester-log.jsonl (run_id <uuid>)
Lessons updated:           skill-lessons.yaml (<N> bumped, <M> new) | (absent — skipped)
Terminology layer:         terminology.yaml (tenant <tenant>, <S> synonyms, <T> matched) | (absent — skipped)

Totals: <N> variables, <M> loops
  high:   <x>   medium: <y>   low: <z>

Blockers requiring review: <count>
Assumptions to confirm:    <count>
Scope violations:          <count>

>>> Open Samples/Output/<stem>/<stem>.review.md to resolve the blockers before running Leg 3. <<<
```

Counts come from the script-generated review.md Summary table.

**`terse` override:**
```
Mode:     terse
Document: <stem>
Stats:    <high> high / <medium> medium / <low> low
Blockers: <N> (see <stem>.review.md)
Output:   <stem>.suggested.yaml  <stem>.review.md  <stem>.suggester-log.jsonl
```

**`batch` override:**
```
Batch complete — <N> documents processed
          high: <total>  medium: <total>  low: <total>
       blockers: <total> across all docs
```

---

## Important constraints

- **Only use paths from the registry.** Never suggest a path you've inferred
  from documentation, training data, or guesswork.
- **Preserve all existing YAML keys.** The `.suggested.yaml` is a superset of
  the input — add `data_source`, `confidence`, and `reasoning` but keep
  every original key intact.
- **Cross-scope variables are a warning.** If the same `name` appears in
  multiple loops (flagged in the Leg 1 report), note this in `reasoning` and
  set confidence to `medium` at best.
- **One file at a time.** This skill processes one `.mapping.yaml` at a time.
  For multiple documents, run it once per file.
- **Charge paths need context.** In the registry, each charge exposes both a
  `velocity_object` (e.g. `$data.charges.GoodDriverDiscount`) and a
  `velocity_amount` (e.g. `$data.charges.GoodDriverDiscount.amount`). If a
  variable appears to be a charge *amount*, use the `velocity_amount` form
  (i.e. the path ending in `.amount`) and note this in `reasoning`. Only use
  the `velocity_object` form if the template is iterating the charge itself.
- **Do not auto-promote lessons** (Phase D). Agents may append
  `observed` rows and bump `seen_count` / `last_seen` / `observed_in`
  only. Never flip `status`, author `candidate_promotion`, or edit
  `pattern` / `current_rule` on existing rows. Violation is a test
  failure. Full contract: `SKILL-lessons.md`.
- **Do not merge multiple terminology files** (Phase E). Exactly one
  `terminology.yaml` per run — `--terminology` flag wins over the
  sibling default. Never union two synonym maps. Never synthesise a
  synonym not in a loaded file. Violation is a test failure. See
  `../../plans/pipeline-improvements/CompletedPlans/alpha-beta-plan/PIPELINE_EVOLUTION_PLAN.md` §6.3 / §7.

---

## Lesson workflow (Phase D)

The mapping-suggester keeps a repo-level lessons ledger at
`skill-lessons.yaml`. Patterns observed across runs accumulate there
so a human reviewer can decide whether to promote them into first-class
matching rules.

**State machine:** `observed` → `proposed` → `promoted` (or `rejected`).
Agents may only write new `observed` rows or bump `seen_count` /
`last_seen` / `observed_in` on existing rows. Only humans may flip
`status` or author `candidate_promotion`.

**Seeded matchers** (v1.0 — applied in Step 0b when `status: promoted`):
none are promoted yet; the two seed lessons (`claimant-eq-policyholder`,
`vehicle-scope-violation`) are `observed` only.

**Review threshold:** when a lesson's `seen_count >= 3` with
`status: observed`, surface a one-line note in `.review.md` §7
reminding the reviewer to consider promotion.

Full contract (state machine, division of responsibility, matcher
definitions, Step 4d write procedure): see
**`SKILL-lessons.md`** in this directory.

---

## File output location

Save all three output files (`<stem>.suggested.yaml`, `<stem>.review.md`,
`<stem>.suggester-log.jsonl`) inside `Samples/Output/<stem>/` — the same
per-document subfolder that Leg 1 created. Create the subfolder if absent
(Leg 1 normally creates it, but Leg 2 must handle the case where it was
deleted or skipped). If the user has a different project output folder
convention (e.g. `OUTPUTS/<project>/`), save to `<project>/<stem>/` and
confirm with the user.

---

## After output

Tell the user:
1. The paths to `Samples/Output/<stem>/<stem>.suggested.yaml`,
   `Samples/Output/<stem>/<stem>.review.md`, and
   `Samples/Output/<stem>/<stem>.suggester-log.jsonl` (plus the `run_id`
   of this run — useful if they want to `grep` the log for just this
   invocation).
2. How many were high / medium / low confidence.
3. Direct them to open `.review.md` first — it contains the blockers,
   assumptions to confirm, and scope warnings in priority order.
4. Once they've reviewed the blockers (edited `.suggested.yaml` or
   restructured the template), the next step is the Substitution Writer
   skill (Leg 3), which rewrites the `.vm` using the confirmed paths.
5. The log file accumulates across runs — tell the user the run they
   just executed is one of `<N>` runs in the log, and that the log is
   observational (no downstream pipeline step reads it yet; it seeds
   future skill-lessons promotion.
6. `skill-lessons.yaml` status — whether the ledger was present, which
   lessons bumped their `seen_count` this run (and the resulting
   values), whether any new observation rows were appended, and
   whether any row has reached the `seen_count >= 3` review
   threshold (see "Lesson workflow (Phase D)"). If the ledger was
   absent, say so — the user may want to seed it following
   `../../plans/pipeline-improvements/CompletedPlans/alpha-beta-plan/PIPELINE_EVOLUTION_PLAN.md` §5.2 before the next run.
7. `terminology.yaml` status — whether a per-tenant synonym layer was
   loaded (and from which path), how many aliases it carried after
   dropping unknown canonicals, and how many placeholders this run
   resolved via synonym lookup (step 3 of the name-match precedence in
   `SKILL-matching.md`).
   If the file was absent, say so — the user may want to seed it
   following `../../plans/pipeline-improvements/CompletedPlans/alpha-beta-plan/PIPELINE_EVOLUTION_PLAN.md` §6 before the next run. If
   `--terminology <path>` shadowed a sibling file, note the shadowing
   explicitly so the reviewer can confirm the single-file contract.
