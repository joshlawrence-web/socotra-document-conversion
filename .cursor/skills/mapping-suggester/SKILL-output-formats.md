# mapping-suggester — Output formats (reference only, post-Stage-4)

> **NOTE (post-Stage-4):** `scripts/leg2_fill_mapping.py` handles all output formatting.
> This file is the authoritative spec — read it when debugging script behavior,
> not during normal AI-skill runs.

Read this file at **Step 4** of the old `SKILL.md` flow, or when debugging the script.
The AI skill no longer reads this file on every run.

---

Read this file before writing any disk
artifacts (`.suggested.yaml`, `.review.md`, `.suggester-log.jsonl`).

For **`full`** mode review prose beyond the terse minimum, also read
`SKILL-full-mode.md` at Step 4b.

---

## Output format

Every run produces **three** artifacts side by side:

1. `<stem>.suggested.yaml` — the machine-readable mapping (shown below).
2. `<stem>.review.md` — the human-readable review report (see "Review
   file format" below).
3. `<stem>.suggester-log.jsonl` — per-run telemetry (JSON Lines). One
   object per `variables` / `loops` entry (`kind: placeholder`), plus
   exactly one `kind: summary` object at the end of each run. The file
   is **append-only** across runs — every invocation adds a fresh batch
   of placeholder records plus its own summary record; earlier records
   are never rewritten. See "Telemetry file format" below and
   `SCHEMA.md` for the artifact contract; the JSON Schema lives at
   `conformance/schemas/suggester-log.schema.json`.

All three files must be written on every run, even when there are zero
blockers. Downstream tooling expects both `.review.md` and
`.suggester-log.jsonl` to exist. The absence of the log file is a bug,
not a feature — a boring, fully-high-confidence run is still a signal
that the current rules cover the current inputs.

```yaml
# <stem>.suggested.yaml
# Suggested mapping — review and confirm each data_source before running the
# substitution step. Edit any data_source value, then save as <stem>.mapping.yaml.

schema_version: '1.0'
input_mapping_version: '1.0'
input_registry_version: '1.0'
source: policy-template.html
generated_at: '...'
path_registry: path-registry.yaml
product: CommercialAuto

variables:
  - name: policyNumber
    placeholder: $TBD_policyNumber
    type: variable
    context:
      parent_tag: p
      nearest_label: "Policy Number"
      line: 23
    data_source: $data.policyNumber   # ← suggested
    confidence: high
    reasoning: >
      "policyNumber" + nearest_label "Policy Number" maps directly to the
      system path $data.policyNumber (Socotra's policy identifier).

  - name: unknownField
    placeholder: $TBD_unknownField
    type: variable
    context:
      parent_tag: span
      nearest_label: ''
      line: 89
    data_source: ''   # ← no suggestion
    confidence: low
    reasoning: >
      No label context and "unknownField" does not match any field name or
      display name in the registry. Human must identify the correct path.

loops:
  - name: vehicles
    placeholder: $TBD_vehicles
    type: loop
    context:
      nearest_heading: Vehicles
      line: 40
    data_source: $data.vehicles   # ← suggested
    iterator: vehicle
    foreach: '#foreach ($vehicle in $data.vehicles)'
    confidence: high
    reasoning: >
      Loop name "vehicles" exactly matches the Vehicle exposure list path
      ($data.vehicles) with iterator $vehicle.
    available_coverages:
      - name: Liability
        velocity: $vehicle.Liability
        quantifier: ''
        cardinality: exactly_one
      - name: MedPay
        velocity: $vehicle.MedPay
        quantifier: '?'
        cardinality: zero_or_one
      # … additional coverages listed verbatim from the registry
```

---

## Telemetry file format (`<stem>.suggester-log.jsonl`)

One JSON object per line. The file is append-only across runs — every
invocation adds a fresh batch of `kind: placeholder` records (one per
`variables` entry, then one per `loops` entry, in the same order as
they appear in the mapping YAML), terminated by exactly one
`kind: summary` record. Multiple runs accumulate in the same file;
records are never rewritten.

The authoritative contract is the JSON Schema at
`conformance/schemas/suggester-log.schema.json`. Key rules:

- Every record carries `ts` (UTC timestamp with `Z` suffix) and `run_id`
  (UUID). All records from a single run share the same `run_id`; a new
  UUID is generated per invocation.
- `placeholder` records mirror the mapping YAML entry verbatim (`name`,
  `placeholder`, `type`, `context`), plus the suggester's decision:
  `chosen_match` (the Velocity path, or `null`), `confidence`
  (`high|medium|low`), `next_action` (closed vocabulary — `pick-one`,
  `supply-from-plugin`, `restructure-template`, `delete-from-template`,
  `confirm-assumption`, `needs-skill-update`, or `null` on `high`
  rows that need no follow-up), `rejected_candidates` (registry paths
  considered but rejected, each with a machine-readable reason),
  and `unknown_context_keys` (context keys on this placeholder not in
  the v1.0 recognised vocabulary).
- The `summary` record holds per-run totals: `totals.{variables,loops}`,
  `confidence_counts.{high,medium,low}`, `next_actions` (count per
  action code), `dead_registry_paths` (registry entries that matched
  zero placeholders), `hot_registry_paths` (registry entries that
  matched two or more — candidates for terminology promotion), and
  `unknown_context_keys_seen` (union across all placeholder records
  in this run).
- `rejected_candidates` reasons come from the closed set
  `scope_violation | quantifier_mismatch | cardinality_mismatch |
  type_mismatch | display_name_mismatch | charge_form_mismatch |
  feature_refused | ambiguous_tiebreak | no_label_context | other`.
  If the rejection reason doesn't fit one of the first nine, use
  `other` and explain in `reasoning` on the corresponding
  `.review.md` entry.

See `conformance/schemas/suggester-log.schema.json` for the full JSON Schema
and a worked example. The log is observational — nothing downstream of
Leg 2 consumes it yet; it exists so Phase D skill-lessons promotion (a
future session) can compare patterns across runs.

---

## Review file format (`<stem>.review.md`)

Plain Markdown, human-readable, no YAML. Emit every run, even with zero
blockers (use "No blockers" in that section and the high-confidence list
in "Done"). Sections in this exact order:

### 1. Header

The file must begin with an HTML comment carrying the schema version so
downstream tooling can parse compatibility without loading the body.
Emit exactly this line, then a blank line, then the Markdown header:

```
<!-- schema_version: 1.1 -->

# Mapping review — <stem>

- Source mapping: Samples/Output/<stem>/<stem>.mapping.yaml
- Suggested output: Samples/Output/<stem>/<stem>.suggested.yaml
- Path registry:  path-registry.yaml
- Product:        <product name from registry meta>
- Generated at:   <ISO-8601 timestamp>
- Schema:         1.1 (mapping 1.0, registry 1.1)
```

The `Schema:` bullet shows the suggester's own supported version first,
then the versions actually read from `<stem>.mapping.yaml` and
`path-registry.yaml`. If Step 0 recorded a MINOR mismatch, reflect the
higher observed MINOR here — the Unrecognised inputs section below
will tell the reviewer which keys got passed through.

### 2. Summary counts

Totals for variables and loops, with a confidence breakdown and a
next-action breakdown. Example:

```
## Summary

| Metric | Count |
|---|---|
| Variables (total) | 37 |
| Loops (total) | 4 |
| high | 2 |
| medium | 6 |
| low | 33 |

### Next-action breakdown

| next-action | Count |
|---|---|
| pick-one | 0 |
| supply-from-plugin | 26 |
| restructure-template | 7 |
| confirm-assumption | 6 |
| delete-from-template | 0 |
```

### 2b. Per-confidence breakdown

Subsections of the Summary section, rendered as `###` headings so they stay
visually grouped with the counts table. One subsection per confidence level
that has at least one entry (skip levels with zero entries entirely).

Each subsection contains:
1. A count table — rows for Loops and Fields.
2. A **Loop names** table (Name | Velocity Path) if any loops at this level.
3. A **Field names** table (Name | Velocity Path) if any variables at this level.

`Name` column uses the placeholder string (e.g. `$TBD_policyNumber`).
`Velocity Path` uses the `data_source` value, or `—` when none was suggested.

Example (high confidence only, with one loop and two fields):

```
### High confidence

| Type | Count |
|---|---|
| Loops | 1 |
| Fields | 2 |

**Loop names**

| Name | Velocity Path |
|---|---|
| `$TBD_vehicles` | `$data.vehicles` |

**Field names**

| Name | Velocity Path |
|---|---|
| `$TBD_policyNumber` | `$data.policyNumber` |
| `$TBD_accountName` | `$data.account.data.name` |
```

### 3. Blockers

Items that will break Leg 3 substitution if not resolved. Include:

- every `low` item (variables and loops);
- every `low` loop's fields (nested under the loop heading);
- any `low` `confirm-assumption` item.

`medium` items go to the "Assumptions to confirm" section below, not
here. Order blockers by source `line` ascending (template top-to-bottom).

Each blocker renders as:

```
### <placeholder name>  _(line <N>)_

- **parent_tag:** `<tag>`
- **nearest_label:** "<label>"
- **loop:** `<loop name or —>`
- **candidates:** _(only when next-action is `pick-one`)_
  - `<path1>` — <why>
  - `<path2>` — <why>
- **next-action:** `<code>: <arg>`
- **suggested resolution:** <1–2 sentence prose>
```

### 4. Assumptions to confirm

Every `medium` + `confirm-assumption` item. Render as a GFM task-list
checklist (`- [ ] …`). Group by assumption text; list every affected
placeholder under it as a sub-bullet with the suggested path.

### 5. Cross-scope warnings

Every variable where Rule 2 found a name match but scope was wrong
(template is missing the required `#foreach`). Render as:

```
## Cross-scope warnings

| Placeholder | Matched path | Requires scope | Fix |
|---|---|---|---|
| `vehicle_year` | `$vehicle.data.year` | `#foreach ($vehicle in $data.vehicles)` | restructure-template |
| `driver_first_name` | `$driver.data.firstName` | `#foreach ($driver in $data.drivers)` | restructure-template |
```

Always render the table header even when empty (print "No cross-scope
warnings." on the next line instead of the table body).

### 6. Done

High-confidence items, collapsed. Use an HTML `<details>` block so the
rendered Markdown shows a one-line count with an expandable list for QA:

```
## Done

<details>
<summary><strong>2</strong> high-confidence mappings</summary>

- `policy_number` → `$data.policyNumber`
- `policyholder_name` → `$data.account.data.name`

</details>
```

### 7. Unrecognised inputs

Every key the shape probe flagged as "unrecognised" lands here, with
exactly one next-action (`needs-skill-update: <describe>`) per row.
Always render this section — print "No unrecognised inputs." when empty.

A four-column Markdown table with columns: **Source** (`mapping` or
`registry`), **Key** (dotted path for mapping context keys; bare section
name for registry top-level keys), **Seen on** (list of
`<placeholder> (line N)` occurrences, truncated to 5 with "… and N
more"), **Next-action** (always `needs-skill-update: <sentence>`).

If Step 0 recorded a MINOR mismatch, prepend one line above the table:
> Input MINOR version `<x>` exceeds the suggester's supported MINOR `<y>`; some keys below may simply be new in `<x>`.

---

## Building `suggester-log.jsonl` (Step 4c contract)

In the same in-memory pass as the YAML / review, build the
`<stem>.suggester-log.jsonl` records and **append** them to the existing
log file at `Samples/Output/<stem>/<stem>.suggester-log.jsonl` (or create
if absent). The authoritative contract is
`conformance/schemas/suggester-log.schema.json`.

Rules:

1. Generate a single fresh UUID per invocation (`uuid.uuid4()` style —
   lowercase with hyphens). Every record from this run carries that
   `run_id`.
2. Use a single UTC timestamp for the whole run (sampled at the start
   of Step 3) on every record, formatted as
   `YYYY-MM-DDTHH:MM:SSZ`. The shared `ts` makes grep-by-run trivial.
3. Write one `kind: placeholder` record per `variables` entry (in file
   order), then one per `loops` entry, then exactly one `kind: summary`
   record. Do **not** interleave summary records.
4. Each record is a single JSON object on a single line — no pretty
   printing. Use compact JSON (no extra whitespace inside objects or
   arrays). End every record with a trailing newline.
5. The file is append-only. If it already exists, open in append mode;
   never rewrite, reorder, or delete earlier lines. Runs accumulate.
6. Populate `rejected_candidates` from candidates actually considered
   during matching — registry paths that matched on name but were
   rejected for a concrete reason (scope, quantifier, type, etc.).
   Leave the array empty `[]` when no rejections applied (common on
   fully-confident matches and on `no-label-context` rejections where
   nothing in the registry was inspected). Use the closed reason
   vocabulary (see "Telemetry file format" above).
7. `chosen_match` is the `data_source` string from the suggested YAML
   (store the exact path you wrote); `null` when `data_source` is
   empty.
8. `next_action` is the same code used in the `.review.md` ambiguity
   bubble-up (`pick-one`, `supply-from-plugin`, `restructure-template`,
   `delete-from-template`, `confirm-assumption`, `needs-skill-update`),
   or `null` on high-confidence rows that need no follow-up.
9. `unknown_context_keys` lists every key on that placeholder's
   `context` block not in the v1.0 recognised vocabulary (same set the
   Step 2a shape probe reports as "Unrecognised").
10. Summary aggregates:
    - `confidence_counts` sums across all placeholder records.
    - `next_actions` counts per code; omit codes with zero occurrences.
    - `dead_registry_paths` = registry entries that did NOT appear as
      `chosen_match` on any placeholder this run. Cap output at 50
      entries for readability when the registry is large; sort
      lexicographically.
    - `hot_registry_paths` = registry entries that appear as
      `chosen_match` on ≥ 2 placeholders this run (candidates for
      terminology promotion). Sort lexicographically.
    - `unknown_context_keys_seen` = union of every placeholder's
      `unknown_context_keys`, sorted.

**Never skip the log.** If Step 0 halts on a MAJOR mismatch, no log is
written (nothing ran). If matching completed, the log is mandatory —
even a 1-variable, 0-loop, fully-`high` run must produce a placeholder
record + a summary record.

**Helper script (optional).** For runs where per-candidate rejection
reasons do not need to be captured, the agent MAY author the JSONL by
invoking the derivation helper instead of hand-building records:

```bash
python3 .cursor/skills/mapping-suggester/scripts/emit_telemetry.py \
    --suggested Samples/Output/<stem>/<stem>.suggested.yaml \
    --registry path-registry.yaml \
    --log Samples/Output/<stem>/<stem>.suggester-log.jsonl
```

The helper generates a fresh UUID + timestamp, derives one run's worth
of records from the already-written suggested YAML + registry, and
appends them to the log. `rejected_candidates` comes out empty on this
path — when the agent has live rejection data in-memory, author the
JSONL directly instead of using the helper. The helper's JSON output
has been validated against `conformance/schemas/suggester-log.schema.json`.
