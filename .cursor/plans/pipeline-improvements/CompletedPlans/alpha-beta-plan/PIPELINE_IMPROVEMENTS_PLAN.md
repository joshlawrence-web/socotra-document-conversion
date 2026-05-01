# Pipeline Improvements Plan — HTML → Velocity (Leg 2 focus)

**Audience:** AI agents (or humans) executing this plan without further context.
**Status:** All phases (1–5) landed 2026-04-22. Plan fully executed.
**Owner:** Mapping Suggester (Leg 2) pipeline.
**Repo root:** `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverter1stLeg`
(all paths below are relative to this root unless marked absolute).

---

## Phase status / handoff (updated 2026-04-22)

### Done — Phase 1 (§2)

`extract_paths.py` was rewritten and `path-registry.yaml` regenerated.
New registry shape — **Phase 3+ agents must read the current
`path-registry.yaml` before doing anything**:

- Top-level `iterables:` list: one entry per foreach-able element with
  `name` / `display_name` / `kind` (`exposure` today; room for
  `data_extension_array` later) / `list_velocity` / `iterator` (already
  prefixed with `$`) / `foreach` / `quantifier` / `cardinality`.
  Currently holds `Vehicle` and `Driver`.
- Every entry (system, account, policy_data, policy_charges, exposures,
  exposure fields/system_fields, coverages, coverage fields, charges)
  carries `requires_scope`: an ordered list (outermost first) of
  `{iterator, foreach}` dicts. System/account/policy-data/policy-charges
  are `[]`.
- Every scalar / coverage / exposure entry carries `quantifier`,
  `cardinality`, `iterable`, and (for data-extension entries) `base_type`.
- The `optional: true/false` key on coverages is **gone** — replaced by
  `quantifier: '?'` + `cardinality: zero_or_one`.
- Exposures now also carry `raw_contents` (the unparsed product `contents`
  array) for downstream tooling.
- Fields whose `base_type` is not a Socotra primitive (`string`, `text`,
  `int`, `number`, `decimal`, `boolean`, `date`, `datetime`, `binary`)
  carry a `custom_type_ref: <TypeName>` flag. **Recursive expansion of
  custom data types into nested `requires_scope` entries is intentionally
  deferred** — there is no custom-typed field in the current
  CommercialAuto config so the pass would be untestable. If a future
  config grows one (e.g. `"drivers": { "type": "Driver+" }` on Vehicle),
  extend `extract_data_fields` to recurse with an appended scope step and
  emit a matching `iterables:` entry of `kind: data_extension_array`.
  The scaffolding already threads `outer_scope` through
  `extract_exposure` for this purpose.

### Done — Phase 2 (§3)

`.cursor/skills/mapping-suggester/SKILL.md` was rewritten. Changes:

- New "Quantifier semantics" section (after Inputs) with the suffix table
  and the loop-only-on-iterable rule.
- "Matching strategy" rewritten as Rules 1–6 (loop match → iterable;
  scope inheritance; confidence; `?` guard; `!` auto-note; charge
  disambiguation). The old "Coverage loops" paragraph was folded into
  Rule 1.
- New "Ambiguity bubble-up" section with the closed next-action
  vocabulary (`pick-one`, `supply-from-plugin`, `restructure-template`,
  `delete-from-template`, `confirm-assumption`). Every `low` and
  `medium` item must carry exactly one.
- The `available_coverages` example was updated from `optional: …` to
  `quantifier:` + `cardinality:` keys. `description:` frontmatter is
  unchanged.

### Done — Phase 3 (§4)

`.cursor/skills/mapping-suggester/SKILL.md` and
`Samples/Output/claim-form.*` were updated. Changes:

- New top-level section **"Review file format (`<stem>.review.md`)"**
  in SKILL.md (sits between "Output format" and "How to run"). Defines
  all six sections — Header, Summary, Blockers, Assumptions to confirm,
  Cross-scope warnings, Done — with literal worked-example snippets.
  The "Done" section uses an HTML `<details>/<summary>` block so
  high-confidence items render collapsed.
- New "Step 4b — Write the review file" added to "How to run" between
  existing Step 4 and Step 5. Step 5 now prints the literal terminal
  summary block from §4.3 (ending with the `>>> ... <<<` line).
- "Output format" intro rewritten to note that every run emits BOTH
  `<stem>.suggested.yaml` AND `<stem>.review.md`, even with zero
  blockers.
- "After output" rewritten to direct the user to `.review.md` first.
- End-to-end run executed on `Samples/Output/claim-form.mapping.yaml`;
  both files written:
  - `Samples/Output/claim-form.suggested.yaml` (overwrites the
    pre-Phase-2 baseline — expected per the original handoff note).
  - `Samples/Output/claim-form.review.md` (new).
- Final tallies match §4.4 exactly:
  - 37 variables, 4 loops, 23 loop fields.
  - high = 2 (`policy_number`, `policyholder_name`).
  - medium = 6 (claimant contact/address block, all
    `confirm-assumption: claimant == policyholder`).
  - low = 33 (29 variables + 4 loop heads).
  - Cross-scope warnings = 7 (`vehicle_year/make/model/vin`,
    `driver_first_name/last_name/license_number`).

### Done — Phase 4 (§5)

`.cursor/skills/html-to-velocity/scripts/convert.py`,
`.cursor/skills/html-to-velocity/SKILL.md`, and
`.cursor/skills/mapping-suggester/SKILL.md` were updated. Changes:

- `convert.py` gained a `load_iterables()` helper that reads
  `path-registry.yaml`'s top-level `iterables:` list, a new
  `--registry <path>` CLI flag (with ancestor-directory auto-search
  fallback and graceful degrade when no registry is found), a
  `loop_name` parameter threaded through `_record_var`,
  `rewrite_vars_in_subtree`, and both Mustache/auto-detected loop
  processors, and a new `annotate_loop_hints()` post-pass.
- Every **loop field** now carries an explicit `context.loop: <name>`
  alongside its existing YAML nesting. This removes Leg 2's need to
  walk YAML structure to determine scope.
- Every **top-level variable** whose lowercased name starts with a
  registered iterable prefix (`vehicle_`, `driver_`, …) now carries
  `context.loop_hint: <IterableName>`. Heuristic is name-prefix only
  (by explicit user direction: keeps `estimated_damage` and other
  claim-level fields under shared iterable headings correctly
  untagged). Heading-based fallback is documented but deferred.
- `html-to-velocity/SKILL.md` documents both keys, the heuristic,
  the `--registry` flag, and a reviewer-facing synonym table (Vehicle
  ↔ "Insured vehicle" / "Car" / …; Driver ↔ "Named driver" / …). The
  synonym table is documentation — the script consumes iterables
  directly from `path-registry.yaml`.
- `mapping-suggester/SKILL.md` Rule 2 was rewritten with an explicit
  5-step algorithm: `context.loop` **satisfies** a `requires_scope`
  step; `context.loop_hint` **does not** — it lets Rule 2 cite a
  concrete candidate path in `reasoning` and pair with
  `next_action: restructure-template`, while the item stays `low`.
  Rule 2 also explicitly forbids using `loop_hint` alone to justify a
  scoped `data_source`.
- Re-ran Leg 1 on all four sample HTMLs
  (`Samples/Input/*.html` → `Samples/Output/*`). Output diffs vs. the
  pre-Phase-4 baseline (snapshotted to `Samples/Output.pre-phase4/`)
  contain only `loop:` / `loop_hint:` additions plus the
  `generated_at` timestamp — no other keys added, renamed, or
  removed; the four `.vm` and `.report.md` files are byte-identical.
- Loop-hint tallies: claim-form 9 (5 Vehicle + 4 Driver) on the
  "Insured vehicle" block (`estimated_damage` correctly absent);
  renewal-notice 10 (4 Vehicle + 6 Driver); quote-application 1
  (`vehicle_subtotal`); policy-template 0 (all vehicle/driver
  variables are already inside proper `{{#vehicles}}` /
  `{{#drivers}}` blocks — 49 loop-field `context.loop` entries
  instead). At least one sample picks up new keys ⇒ §5.2 acceptance
  met.

### Done — Phase 5 (§6)

Full regression run executed across all four samples. Outputs written
to `Samples/Output/<stem>.suggested.yaml` + `Samples/Output/<stem>.review.md`
for each of `claim-form`, `policy-template`, `quote-application`,
`renewal-notice`. Summary:

| Sample              | Variables | Loops | high | medium | low | Blockers | Assumptions | Scope violations |
|---------------------|----------:|------:|-----:|-------:|----:|---------:|------------:|-----------------:|
| `claim-form`        |        41 |     0 |    2 |      6 |  33 |       33 |           6 |                7 |
| `policy-template`   |        38 |     4 |    5 |      3 |  30 |       30 |           3 |                0 |
| `quote-application` |        56 |     0 |    1 |      9 |  46 |       46 |           9 |                7 |
| `renewal-notice`    |        39 |     0 |    1 |      3 |  35 |       35 |           3 |                7 |

**Claim-form regression check (§6.2 / §6.3):** `diff` of the
`(name, confidence, data_source)` triples between
`Samples/Output.pre-phase4/claim-form.suggested.yaml` and the current
`Samples/Output/claim-form.suggested.yaml` is **empty** — no
`data_source` value regressed or silently upgraded. Only `reasoning`
prose changed, now explicitly citing `context.loop_hint` and Rule 2
step 3 for the seven cross-scope items (`vehicle_year`, `vehicle_make`,
`vehicle_model`, `vehicle_vin`, `driver_first_name`, `driver_last_name`,
`driver_license_number`). Blocker / assumption / scope-violation
counts match §6.3 targets exactly (33 / 6 / 7). `policy_number` and
`policyholder_name` stay `high`, unchanged. Other three samples were
net-new outputs (no pre-phase4 `.suggested.yaml` baseline).

**Phase 4 loop-hint flow-through (Rule 2 step 3 vs step 5):**

| Sample              | loop_hints in input           | Rule 2 step 3 (restructure-template) | loop_hint-only → supply-from-plugin |
|---------------------|-------------------------------|-------------------------------------:|------------------------------------:|
| `claim-form`        | 9 (5 Vehicle + 4 Driver)      |                                    7 |                                   2 |
| `renewal-notice`    | 10 (4 Vehicle + 6 Driver)     |                                    7 |                                   3 |
| `quote-application` | 1 (`vehicle_subtotal`)        |                                    0 |                                   1 |
| `policy-template`   | 0 (loops detected directly)   |                                  n/a |                                 n/a |

`quote-application` additionally picks up 7 scope violations from
Rule 2 step 4 (scoped registry candidate, no loop / loop_hint signal
from Leg 1 — template restructure needed).

**Guardrail audit:**

- No `$data.get("…")` method-call syntax emitted anywhere.
- No invented registry paths — every suggested `$...` value exists in
  `path-registry.yaml` verbatim, or is explicitly `supply-from-plugin`.
- Every medium/low item carries exactly one next-action from the
  closed vocabulary (`pick-one` / `supply-from-plugin` /
  `restructure-template` / `delete-from-template` /
  `confirm-assumption`).
- Every run emitted the literal `>>> Open <stem>.review.md … <<<`
  terminal line (see per-sample summaries in the Phase 5 execution
  transcript).
- `vehicle_registration`, `driver_license_state`,
  `claimant_signature_name` all stay `low` + `supply-from-plugin` as
  required.

**Acceptance criteria for Phase 5 (§6.4) — all met:**

- [x] All four samples produce `.suggested.yaml` + `.review.md`
      without errors.
- [x] Claim-form expected outcomes (§6.3) all met.
- [x] No `data_source` regressed (silent high → medium/low without a
      reasoning upgrade).
- [x] Terminal output for every sample ends with the `>>> ... <<<`
      review-prompt line.

### Plan closeout

All phases (§2 Phase 1 through §6 Phase 5) are complete. The Leg 2
pipeline now emits per-sample `.suggested.yaml` + `.review.md` pairs
with quantifier-aware scope inheritance, the full Rule 1–6 matching
strategy including the Rule 2 five-step scope algorithm, the closed
next-action vocabulary, and a human-readable review artifact. The
out-of-scope items from §10 (Leg 3 rewrite, HTML markup-convention
changes, non-CommercialAuto support, runtime rendering, UI) remain
out of scope and are the natural follow-ups if this pipeline is
carried forward.

**Pipeline state snapshot (post-Phase-5, 2026-04-22):**

- `path-registry.yaml` — current (Phase 1 shape; 2 iterables: Vehicle,
  Driver). Don't hand-edit — regenerate via
  `python3 .cursor/skills/mapping-suggester/scripts/extract_paths.py --config-dir socotra-config`.
- `.cursor/skills/mapping-suggester/SKILL.md` — current (Rules 1–6 with
  the Phase 4 Rule 2 rewrite, Ambiguity bubble-up, review-file format,
  Step 4b, Step 5).
- `.cursor/skills/html-to-velocity/SKILL.md` + `scripts/convert.py` —
  current (Phase 4: `--registry` flag, iterable loader,
  `context.loop` on every loop field, `context.loop_hint` on top-level
  variables via name-prefix match).
- `Samples/Output/*.mapping.yaml` — all four samples reflect the
  Phase 4 Leg 1 run. Loop-hint tallies: claim-form 9 /
  policy-template 0 / quote-application 1 / renewal-notice 10.
  Loop-field `context.loop` tallies: 23 / 49 / 0 / 0.
- `Samples/Output/<stem>.suggested.yaml` + `<stem>.review.md` — all
  four pairs now exist (Phase 5). Final tallies captured in the
  "Done — Phase 5 (§6)" summary above.
- `Samples/Output.pre-phase4/` — snapshot of pre-Phase-4 output files
  (taken at the start of Phase 4). Preserved as the regression
  baseline for future refactors. Don't modify this directory.

**How the pipeline now reasons about scope (post-Phase-5 reference):**

- **`context.loop` on loop fields → Rule 2 step 2 (scope satisfied).**
  When a loop field is matched to a scoped registry entry whose
  `requires_scope[0].iterator` corresponds to the loop's iterable,
  the match is accepted. Example: a field with `context.loop: drivers`
  matched to a registry entry with `requires_scope: [{iterator:
  '$driver', ...}]` → scope satisfied → high confidence (if name
  matches too).
- **`context.loop_hint` on top-level variables → Rule 2 step 3
  (scope violated but iterable known).** Concrete candidate path goes
  into `reasoning`; item stays `low` + `restructure-template`.
- **Neither key + scoped candidate → Rule 2 step 4.** Candidate cited,
  but `reasoning` says "no scope signal from Leg 1".
- **No candidate at all → Rule 2 step 5 → `supply-from-plugin`.**

**If you are re-running the pipeline end-to-end (future refactors):**

1. Regenerate `path-registry.yaml` with
   `python3 .cursor/skills/mapping-suggester/scripts/extract_paths.py --config-dir socotra-config`.
2. Re-run Leg 1 on the four samples in `Samples/Input/*.html` to
   refresh `Samples/Output/*.mapping.yaml` / `*.vm` / `*.report.md`.
3. Re-run Leg 2 (this skill) on each of the four `.mapping.yaml`
   files; emit `.suggested.yaml` + `.review.md` per sample and print
   the literal summary block from §4.3 (ending with the `>>> ... <<<`
   line).
4. Diff the new `.suggested.yaml` triples
   (`name`, `confidence`, `data_source`) against
   `Samples/Output.pre-phase4/claim-form.suggested.yaml` and the
   current (post-Phase-5) `.suggested.yaml` files. Any difference is a
   regression candidate — investigate before accepting.

**Post-run guardrails (carry forward):**

- Never invent next-action codes. Vocabulary is fixed: `pick-one` /
  `supply-from-plugin` / `restructure-template` /
  `delete-from-template` / `confirm-assumption`.
- `claim-form` `high`-confidence values (`policy_number`,
  `policyholder_name`) must stay `high` across re-runs. Any
  regression means something in Leg 1 or Leg 2 broke.
- `vehicle_registration`, `driver_license_state` stay
  `supply-from-plugin` — registry has no such fields, and loop hints
  cannot invent registry entries. Proper fix is to extend the
  CommercialAuto config.
- `claimant_signature_name` stays `low` + `supply-from-plugin`
  (preserves the §4.4 target of 33 low blockers for claim-form).

---

## 0. Context (read before doing anything)

The three-leg pipeline:

1. **Leg 1 — `html-to-velocity`** — converts an HTML mockup with `{{name}}` and
   `*loopname*` markers into a `.vm` template full of `$TBD_*` placeholders and
   a `.mapping.yaml` catalogue of every placeholder with context.
2. **Leg 2 — `mapping-suggester`** (this plan's focus) — reads the mapping
   YAML plus `path-registry.yaml` (produced by `extract_paths.py`) and fills in
   each `data_source` with a registry-valid Velocity path.
3. **Leg 3 — `substitution-writer`** — rewrites the `.vm` once a human has
   reviewed and confirmed the mapping.

A test run against `Samples/Output/claim-form.mapping.yaml` surfaced two
structural weaknesses:

- **(a) Ambiguity handling is too quiet.** Low/medium confidence items are
  written to the output YAML and easy to miss. The user has to read all 540
  lines to find the 33 items that need their attention.
- **(b) Scope inheritance isn't modelled.** The Socotra quantifier system
  (`+`, `*`, `?`, `!`, no-suffix) determines whether an element is iterable,
  and by extension **every field under a `+`/`*` element inherits the
  requirement to live inside a matching `#foreach`**. The current registry
  silently implies this by only emitting `list_velocity` on exposures, but the
  skill's matching strategy doesn't reason about it.

Reference docs in the local Socotra Buddy corpus:

- Quantifier rules: `~/socotra-buddy/resources/derived/125949463fad41f0.md`
- Validation semantics: `~/socotra-buddy/resources/derived/0fb37d4535c7267b.md`

---

## 1. Guiding principles (apply to every phase)

1. **Ambiguity is a first-class output.** Anything below `high` confidence
   must be surfaced to the user in a dedicated review artifact, not buried in
   a YAML file. Every low/medium item must carry a **next-action** (pick from
   N candidates / supply from plugin / restructure template / delete).
2. **Scope inheritance is transitive.** If parent element `E` is iterable
   (`+` or `*`), every field, coverage, sub-element, and grandchild of `E`
   inherits the constraint "only accessible inside `#foreach` over `E`'s
   list_velocity". This rule cascades — nested iterables compound their
   required scope (outer foreach + inner foreach).
3. **The registry is the single source of truth.** The suggester must never
   invent a path. If the registry doesn't list it, it doesn't exist.
4. **One file at a time, end to end.** Run each phase to completion on all
   four sample documents (`claim-form`, `policy-template`, `quote-application`,
   `renewal-notice`) before moving to the next phase. Regressions are easier
   to catch with full-suite diffs than with partial ones.
5. **Preserve existing YAML keys.** Every output is a superset of its input.
   Never drop, rename, or reorder existing keys.

---

## 2. Phase 1 — Enrich `path-registry.yaml` with quantifier + scope metadata

**File to edit:** `.cursor/skills/mapping-suggester/scripts/extract_paths.py`
**File produced:** `path-registry.yaml` (regenerated at repo root)
**No changes to the skill logic yet.**

### 2.1 Add a single source-of-truth parser for quantifier suffixes

At the top of `extract_paths.py`, add:

```python
QUANTIFIER_SUFFIXES = ("!", "?", "+", "*")

QUANTIFIER_CARDINALITY = {
    "":  "exactly_one",
    "!": "exactly_one_auto",
    "?": "zero_or_one",
    "+": "one_or_more",
    "*": "any",
}

ITERABLE_QUANTIFIERS = {"+", "*"}

def parse_quantified_token(token: str) -> tuple[str, str]:
    """
    Split a contents-array token like 'Vehicle+', 'MedPay?', 'Coll' or
    'collision!' into (name, quantifier).
    Returns ('', '') for an empty token.
    """
    if not token:
        return ("", "")
    if token[-1] in QUANTIFIER_SUFFIXES:
        return (token[:-1], token[-1])
    return (token, "")
```

Replace every ad-hoc `rstrip("?")` / `rstrip("+?")` in the file with
`parse_quantified_token`. There are currently two places:

- `extract_exposure` — `raw_contents = cfg.get("contents", []); coverage_names = [c.rstrip("?") for c in raw_contents]`
- `build_registry` — `exposure_names = [c.rstrip("+?") for c in raw_contents]`

Both must preserve the parsed quantifier alongside the name so it can be
emitted later.

### 2.2 Detect array-typed data-extension fields

A data-extension type string may carry a quantifier, e.g.:

```json
"drivers": { "type": "Driver+" }
"coverageAddOns": { "type": "string*" }
"Notes": { "type": "binary?" }
"middleName": { "type": "string?" }
```

In `extract_data_fields`, parse the type with `parse_quantified_token`:

```python
base_type, type_q = parse_quantified_token(field_type)
entry["base_type"]       = base_type
entry["quantifier"]      = type_q
entry["cardinality"]     = QUANTIFIER_CARDINALITY[type_q]
entry["iterable"]        = type_q in ITERABLE_QUANTIFIERS
```

If `iterable` is true and the base type matches a known custom data type or
exposure (not a primitive like `string`/`int`/`date`/`binary`/`datetime`),
emit **two** entries for that field:

- An `iterable_collection` entry with `list_velocity`, `foreach`, `iterator`
  derived from the field name (mirroring exposure logic — lower-case first
  char, keep the plural if already there, else add `s`).
- A nested group of field entries under that iterator prefix (same logic as
  `extract_exposure` but recursive on the referenced custom type).

For primitive array types (`string+`, `int*`, `binary?`) the field is a
simple array/optional scalar — emit `iterable: true` but don't try to build
nested paths.

### 2.3 Propagate scope requirement to every derived path

Every entry in `exposures[].fields`, `exposures[].system_fields`,
`exposures[].coverages[]`, `exposures[].coverages[].fields`, and
`exposures[].coverages[].charges[]` MUST get a new key:

```yaml
requires_scope:
  - foreach: '#foreach ($vehicle in $data.vehicles)'
    iterator: '$vehicle'
```

This is a list of scopes that must be active (in order, outermost to
innermost) for the `velocity` path to be valid. For top-level system /
account / policy-data / policy-charge entries, emit `requires_scope: []`.

If nested iterables exist (e.g. a `Driver+` data-extension on Vehicle), the
child entries' `requires_scope` list contains **both** the outer Vehicle
foreach and the inner drivers foreach.

### 2.4 Emit quantifier on every `contents`-derived entry

Every exposure entry and every coverage entry must carry:

```yaml
quantifier: '+'            # the literal suffix or '' for none
cardinality: one_or_more   # from QUANTIFIER_CARDINALITY
iterable: true             # quantifier in ITERABLE_QUANTIFIERS
```

Drop the existing `optional: true/false` key on coverages; replace it with
the quantifier fields above. (`optional` was a fuzzy proxy for `quantifier:
'?'` — the new fields are more precise and `optional` becomes
`quantifier == '?'`.)

### 2.5 Add a registry-level summary of iterables

At the top of `path-registry.yaml`, after `meta`, emit:

```yaml
iterables:
  - name: Vehicle
    kind: exposure
    list_velocity: $data.vehicles
    iterator: $vehicle
    foreach: '#foreach ($vehicle in $data.vehicles)'
    quantifier: '+'
  - name: Driver
    kind: exposure
    list_velocity: $data.drivers
    iterator: $driver
    foreach: '#foreach ($driver in $data.drivers)'
    quantifier: '+'
  # ...and any data-extension arrays, e.g.:
  # - name: notes
  #   kind: data_extension_array
  #   parent_scope: '$vehicle'
  #   list_velocity: $vehicle.data.notes
  #   iterator: $note
  #   foreach: '#foreach ($note in $vehicle.data.notes)'
  #   quantifier: '*'
```

This gives the suggester a fast index when matching template loops without
walking every exposure.

### 2.6 Acceptance criteria for Phase 1

- [x] `path-registry.yaml` regenerates without errors:
      `python3 .cursor/skills/mapping-suggester/scripts/extract_paths.py --config-dir socotra-config`
- [x] `iterables:` top-level section present with at least the Vehicle and
      Driver exposures.
- [x] Every exposure has `quantifier: '+'`, `cardinality: one_or_more`,
      `iterable: true`.
- [x] Every coverage has `quantifier` + `cardinality` + `iterable` keys; the
      `optional` key has been removed.
- [x] Coll / Comp / Liability report `quantifier: ''`, `cardinality:
      exactly_one`, `iterable: false`.
- [x] MedPay / Umbi / Umpd report `quantifier: '?'`, `cardinality:
      zero_or_one`, `iterable: false`.
- [x] Every `fields` / `coverages[].fields` entry has a non-empty
      `requires_scope` list containing the parent exposure's foreach.
- [x] System / account / policy-data / policy-charge entries all have
      `requires_scope: []`.
- [x] No existing key has been removed or renamed (except `optional`, which
      is explicitly superseded — call this out in the commit message).

---

## 3. Phase 2 — Upgrade the `mapping-suggester` SKILL matching logic

**File to edit:** `.cursor/skills/mapping-suggester/SKILL.md`
**No code changes in this phase — this is pure prompt / rules.**

### 3.1 Add a new section "Quantifier semantics" after the introduction

Insert a table identical to the one in
`~/socotra-buddy/resources/derived/125949463fad41f0.md`:

| Suffix | Meaning | Iterable? |
|---|---|---|
| *(none)* | Exactly one required | No |
| `!` | Exactly one, auto-created | No |
| `?` | Zero or one | No (needs `#if` guard) |
| `+` | One or more | **Yes** |
| `*` | Any number | **Yes** |

With a lead paragraph that sets the rule:
"The quantifier determines whether a given path is loopable. Only elements
with `quantifier: '+'` or `'*'` can be the `data_source` of a `loops` entry.
Singular elements (`''`, `'!'`, `'?'`) can only be referenced directly."

### 3.2 Rewrite the "Matching strategy" section

Replace the current "Variables / Loops / Coverage loops" subsections with
the following rules in priority order:

**Rule 1 — Loop matches demand an iterable.**
When mapping a `loops` entry:
- Check `iterables:` at the top of the registry.
- Match loop `name` against each iterable's `name` / derived plural / any
  synonyms via `display_name`.
- Only set `data_source` if a match is found on an entry with
  `iterable: true`. Otherwise leave blank, `confidence: low`, and note
  "no iterable element in the registry; data must come from a plugin or
  external snapshot".

**Rule 2 — Scope inheritance is transitive.**
When mapping a `variables` entry:
- If the candidate registry entry has a non-empty `requires_scope`, check
  whether the mapping YAML's `context.loop` (emitted by Leg 1) puts the
  variable inside the matching `#foreach`.
- If yes: accept the match, confidence determined by Rule 3 below.
- If no: **never set `data_source` to a scoped path**, even if the name
  matches exactly. Set `confidence: low`, record the candidate path in
  `reasoning` with the note "requires loop scope `<foreach>`; template
  must be restructured to wrap this block in a matching `#foreach`, or a
  plugin must supply a flattened scalar field on `$data.data.*`".
- Nested iterables require **all** scopes in `requires_scope` to be
  active simultaneously.

**Rule 3 — Confidence levels.**

| Level | When to use |
|---|---|
| `high` | `name` or `display_name` matches unambiguously **and** scope requirements (if any) are satisfied by the template's current loop context. |
| `medium` | Plausible label/name match but semantic ambiguity (e.g. `claimant_phone` → account phone under the assumption claimant == policyholder). Also use when multiple registry entries are equally plausible — list all of them in `reasoning`. |
| `low` | No match, or a match exists but scope is wrong, or the name is ambiguous across multiple scopes. Always leave `data_source: ''`. |

**Rule 4 — Optional-element guard.**
When the matched path sits on an element with `quantifier: '?'`, append to
`reasoning`: "requires `#if(<parent>.<Child>)` guard before access (element
is zero-or-one)". This applies to MedPay, Umbi, Umpd and any optional
coverage term.

**Rule 5 — Auto-element note.**
When the matched path sits on an element with `quantifier: '!'`, append to
`reasoning`: "element is auto-created on validation; always present". No
guard needed.

**Rule 6 — Charge path disambiguation.**
(Keep the existing rule from the current SKILL.md — `velocity_amount` vs
`velocity_object` — unchanged.)

### 3.3 Add an "Ambiguity bubble-up" section

After "Confidence levels", add a section with this contract:

> Every low-confidence item MUST carry a **next-action** in its `reasoning`
> field, chosen from this closed vocabulary:
>
> - `pick-one: <path1> | <path2> | ...` — registry has multiple plausible
>   matches; the human must choose.
> - `supply-from-plugin: <suggested plugin field shape>` — no registry
>   entry exists; the template wants data that must be computed by a
>   plugin (e.g. claim-domain fields, loss-vehicle flattening).
> - `restructure-template: <describe>` — a registry entry exists but
>   its scope doesn't match the template structure; the template must be
>   rewritten (typically wrap a block in `#foreach` with an `#if`
>   selector).
> - `delete-from-template: <reason>` — the field has no business purpose
>   in this document (very rare; use sparingly).
> - `confirm-assumption: <assumption>` — the match is reasonable if a
>   named assumption holds (e.g. "claimant == policyholder"). The user
>   must confirm before proceeding.

Exactly one next-action per low or medium item. High-confidence items do
not need a next-action.

### 3.4 Acceptance criteria for Phase 2

- [x] New "Quantifier semantics" section present and references the local
      corpus file.
- [x] Matching strategy rewritten with Rules 1–6.
- [x] Ambiguity bubble-up section present with the closed vocabulary.
- [x] No conflicting guidance left over from the previous version (search
      for `optional: true` and any reference to coverage-loop matching by
      name alone — remove or update).
- [x] `SKILL.md` still parses as valid Markdown.
- [x] `description:` frontmatter unchanged.

---

## 4. Phase 3 — Add a companion review artifact

**Files produced per run:**
- `<stem>.suggested.yaml` (existing — enriched)
- `<stem>.review.md` (**new**)

### 4.1 Define `<stem>.review.md` format

Plain Markdown, human-readable, no YAML. Sections in order:

1. **Header** — source file, timestamp, product, registry path.
2. **Summary counts** — total variables / loops with a breakdown by
   confidence and by next-action.
3. **Blockers** — items that will break Leg 3 substitution if not resolved
   (all `low`, any `medium` with `next_action: confirm-assumption` that
   hasn't been acknowledged). For each blocker:
   - Heading: `### <placeholder name>` (line number in the original
     template file in parentheses).
   - Context: `parent_tag`, `nearest_label`, `loop` (if any).
   - Candidate paths (if `pick-one`): bulleted list.
   - Next-action: one of the closed-vocabulary codes from §3.3.
   - Suggested resolution (prose, 1–2 sentences).
4. **Assumptions to confirm** — every `confirm-assumption` medium item in
   one list; the user ticks them off.
5. **Cross-scope warnings** — every variable flagged with `Rule 2` scope
   violation.
6. **Done** — items at `high` confidence (collapsed, just a count and
   optionally an expandable list for QA).

### 4.2 Update SKILL.md to emit the review file

Add a new "Step 4b — Write the review file" step to the "How to run"
section, between the existing Step 4 (write `.suggested.yaml`) and Step 5
(print summary). The agent writes both files in the same pass through the
data so they stay in sync.

### 4.3 Enhance the terminal summary

Replace the existing Step 5 summary with:

```
Suggested mapping written: Samples/Output/<stem>.suggested.yaml
Review report written:     Samples/Output/<stem>.review.md

Totals: <N> variables, <M> loops
  high:   <x>   medium: <y>   low: <z>

Blockers requiring review: <count>
Assumptions to confirm:    <count>
Scope violations:          <count>

>>> Open <stem>.review.md to resolve the blockers before running Leg 3. <<<
```

The last line must be emitted literally with the stars — it's the prompt
an agent uses to notice the file exists.

### 4.4 Acceptance criteria for Phase 3

- [x] SKILL.md documents the `.review.md` format with a full worked
      example.
- [x] Sample run on `claim-form.mapping.yaml` produces both files.
- [x] `.review.md` lists the 33 low-confidence items under "Blockers"
      with the correct next-action for each.
- [x] `.review.md` lists the 6 medium-confidence claimant-address items
      under "Assumptions to confirm" (`claimant == policyholder`).
- [x] Terminal output ends with the `>>> ... <<<` line.

---

## 5. Phase 4 — Leg 1 hint improvements (small, low-risk)

**File to edit:** `.cursor/skills/html-to-velocity/SKILL.md` (and the
helper scripts under `.cursor/skills/html-to-velocity/scripts/` if any).

### 5.1 Always emit `loop:` context for loop-scoped variables

The current `claim-form.mapping.yaml` has no `loop:` key on any variable,
including the ones under "Insured vehicle" that clearly should be inside a
vehicles loop if the template were well-formed. Leg 1 should:

- When a placeholder sits under a detected `*loopname*` or `{{#each}}`
  block, set `context.loop: <loopname>`.
- When a placeholder sits under a heading/section whose text matches a
  known iterable name (`Insured vehicle` / `Drivers` / `Vehicles`) but is
  NOT inside a detected loop block, emit a new key
  `context.loop_hint: <detected_name>` with a comment that says "Leg 2
  should flag this as scope-violation candidate".

This lets Phase 2's Rule 2 fire correctly on the CommercialAuto claim
form's `vehicle_*` / `driver_*` fields.

### 5.2 Acceptance criteria for Phase 4

- [x] Rerun Leg 1 on all four sample HTMLs. At least one new mapping
      YAML should pick up `context.loop` or `context.loop_hint` on
      previously-bare variables.
- [x] No existing `context.*` keys are removed.

---

## 6. Phase 5 — Validation & regression

### 6.0 Fixture suite regression (Phase C gate)

**Run this before §6.1.** `conformance/run-conformance.py` must go green before
any sample-based regeneration or diff work starts. The fixtures are
adversarial — every row in `CONFIG_COVERAGE.md` whose "In fixture?"
column is populated points at a directory under `conformance/fixtures/`, and
the suite catches `extract_paths.py` or suggester-contract regressions
long before the four sample documents would surface them.

```bash
python3 conformance/run-conformance.py
```

Runner contract (summarised from `conformance/run-conformance.py` docstring and
`conformance/README.md` — read those for the full version):

- **What it automates per fixture (deterministic, no agent required):**
  deletes any stale `<fixture>/actual/path-registry.yaml`, re-runs
  `extract_paths.py` on `<fixture>/socotra-config/`, canonicalises
  actual + golden registries (strips volatile fields listed in
  `IGNORED_REGISTRY_PATHS`), and diffs them.
- **What it automates when an agent has left suggester outputs:** if
  `<fixture>/actual/suggested.yaml` and/or `<fixture>/actual/review.md`
  exist, they are diffed against `<fixture>/golden/suggested.yaml` /
  `golden/review.md` with the same canonicalisation rules (volatile
  keys stripped from the suggested YAML; the review `Generated-at`
  bullet and a couple of schema-bullet date fragments normalised in
  the text diff).
- **What it never does:** invoke the mapping-suggester skill. That is
  an agent step — `run-conformance.py` just diffs whatever an agent has
  left in `actual/`. If `actual/suggested.yaml` is absent the runner
  reports `skipped` for the suggested + review artifacts, which is the
  expected state for every fixture whose goldens were authored by
  direct rule-application (9 of 11 fixtures today — see the §4.3
  deviation tracked in `PIPELINE_EVOLUTION_PLAN.md` Done-C4 block).
- **`--update-goldens`** rewrites goldens from `actual/` after an agent
  has verified the diffs by eye. Refuses to overwrite a golden whose
  actual counterpart is missing (guards against zeroing out frozen
  artifacts).

Exit codes and what "pass" means:

- **`0` — every fixture passed.** For the deterministic registry leg
  this means the canonicalised actual registry is byte-identical to
  the golden. For the agent-driven suggested + review legs, `pass`
  means the canonicalised actual matches the golden; `skipped` means
  no `actual/` file exists (and counts as pass for exit-code
  purposes — the runner does not fail on skipped legs).
- **`1` — one or more fixtures produced a diff.** Unified diff prints
  to stdout; fix the regression or re-author the golden with
  `--update-goldens` after verifying the diff is intentional.
- **`2` — runner invocation / configuration error** (missing
  `extract_paths.py`, malformed fixture tree, pyyaml not installed).

Today's expected output: **11 fixtures, all PASS**, with `minimal/` +
`all-quantifiers/` reporting `registry=pass suggested=pass review=pass`
and the other 9 fixtures reporting `registry=pass suggested=skipped
review=skipped`. Any deviation (a new fixture failing registry, an
existing fixture flipping from pass to skipped, or vice-versa) is a
regression to investigate before proceeding to §6.1.

### 6.1 Regenerate baselines

```bash
# Phase 1 regenerated this already; confirm.
python3 .cursor/skills/mapping-suggester/scripts/extract_paths.py --config-dir socotra-config

# Re-run Leg 1 on all four samples (after Phase 4) to refresh the inputs.
# (Use whatever Leg 1 invocation is current.)

# Run the upgraded suggester on each sample.
# Expected outputs:
#   Samples/Output/<stem>.suggested.yaml
#   Samples/Output/<stem>.review.md
```

### 6.2 Diff check vs. pre-change outputs

Keep the current `Samples/Output/claim-form.suggested.yaml` as a baseline.
After the upgrade, compare:

- Every `data_source` value that was `high` before must remain `high`
  and produce the same path.
- Every `data_source` that was `medium` before must produce **either**
  the same path at `medium` (with an `assumption` in `reasoning`) **or**
  be downgraded to `low` (if new scope rules disqualify it) — never
  upgraded without explicit review.
- Every `data_source` that was `low` before should remain `low` unless
  new quantifier-aware reasoning finds a valid match (in which case the
  upgrade must be explicitly justified in `reasoning`).

### 6.3 Expected claim-form outcomes after all phases

Use this as the acceptance test for the full plan:

- `vehicle_year`, `vehicle_make`, `vehicle_model`, `vehicle_vin`,
  `driver_first_name`, `driver_last_name`, `driver_license_number` — still
  `low`, but `reasoning` now cites `requires_scope` explicitly and lists
  `next_action: restructure-template` with a concrete "wrap in `#foreach
  ($vehicle in $data.vehicles)` and add `#if` selector" suggestion.
- `other_parties`, `witnesses`, `injuries`, `damaged_items` loops — still
  `low`, reasoning now references the iterables index and cites
  `next_action: supply-from-plugin`.
- Claimant contact block — still `medium`, reasoning now carries
  `next_action: confirm-assumption: claimant == policyholder`.
- `policy_number`, `policyholder_name` — still `high`, unchanged.
- `.review.md` blockers list matches the diff above.

### 6.4 Acceptance criteria for Phase 5

- [x] `conformance/run-conformance.py` exits `0` (every fixture passes, per
      §6.0) **before** any sample-based regeneration in §6.1 runs.
      (Wired in by session C5 of `PIPELINE_EVOLUTION_PLAN.md`; 11/11
      fixtures pass as of 2026-04-22.)
- [x] All four samples produce `.suggested.yaml` + `.review.md` without
      errors.
- [x] Claim-form expected outcomes above all met.
- [x] No `data_source` value has regressed in quality (no silent
      high → medium/low without a reasoning upgrade). Diff of
      `(name, confidence, data_source)` triples between
      `Samples/Output.pre-phase4/claim-form.suggested.yaml` and current
      is empty.
- [x] Terminal output for every sample ends with the `>>> ... <<<`
      review-prompt line.

---

## 7. Hard constraints (do NOT violate)

- **Do not commit to git** unless the user explicitly asks.
- **Do not fetch from the public web** — the Socotra corpus at
  `~/socotra-buddy/` is the only source for platform rules. If an answer
  isn't there, ask the user.
- **Do not invent registry paths.** If a rule requires a path and none
  exists in the registry, the correct answer is always `next_action:
  supply-from-plugin` or `restructure-template`, not synthesis.
- **Do not use method-call Velocity syntax** (`$data.get("policyNumber")`)
  in suggestions — always dot notation (`$data.policyNumber`).
- **Do not skip the `.review.md` artifact** even when there are zero
  blockers; emit it with "No blockers" and the high-confidence list. The
  downstream convention expects the file to exist.
- **Do not modify sample input files** (`Samples/*.html`,
  `Samples/Output/*.mapping.yaml`) unless you are running Leg 1 to
  regenerate them under Phase 4.
- **Do not introduce new dependencies** in `extract_paths.py` beyond
  `pyyaml`. Stay on the Python standard library otherwise.

---

## 8. Stop and ask the user when

- A Socotra config feature appears that isn't in the quantifier doc
  (`~/socotra-buddy/resources/derived/125949463fad41f0.md`) — e.g. a
  nested `contents` pattern you haven't seen before, or a custom data
  type that references itself.
- A registry regeneration changes more than one `high`-confidence
  mapping in the existing sample outputs. That's a signal something
  regressed; stop and show the diff before proceeding.
- Leg 1 outputs change shape (new keys, renamed keys). Phase 2's
  matching rules depend on the current shape; coordinate with the Leg 1
  author before adapting.
- Any ambiguity you can't resolve with the closed next-action vocabulary
  in §3.3. Add a new code with the user's sign-off; don't invent one
  silently.

---

## 9. Execution order (one pass)

1. Phase 1 (§2) — extract_paths.py + regenerate registry.
2. Phase 2 (§3) — SKILL.md matching rules.
3. Phase 3 (§4) — SKILL.md review-file output + terminal summary.
4. Phase 4 (§5) — Leg 1 loop hints (optional but recommended).
5. Phase 5 (§6) — regression run on all four samples.

Each phase has its own acceptance-criteria checklist. Do not advance to
the next phase until every box in the current phase is ticked.

---

## 10. Out of scope (explicitly)

- Rewriting Leg 3 (substitution writer). Scope-inheritance-aware
  substitution is a separate plan.
- Changing the HTML markup conventions Leg 1 recognises
  (`{{var}}`, `*loop*`, etc.).
- Supporting non-CommercialAuto products. Everything here must stay
  generic across any `socotra-config/` layout, but only CommercialAuto
  is test-bench here.
- Changing the way `.vm` files are rendered at runtime — pure tooling
  work only.
- Adding a UI. `.review.md` is the human interface.
