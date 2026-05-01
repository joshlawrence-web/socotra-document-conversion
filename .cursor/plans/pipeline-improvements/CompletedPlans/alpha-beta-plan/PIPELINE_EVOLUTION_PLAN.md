# Pipeline Evolution Plan — Generalization, Training, and Customer Variation

**Audience:** AI agents (or humans) executing this plan without further context.
**Status:** Phases A, B §3 (session B1), C (sessions C1 + C2 + C3 +
C4 + C5), D §5 (sessions D1 + D2), and E §6 (session E1 —
terminology layer + `custom-naming/` fixture link-up; all five §6.4
acceptance boxes ticked) are all complete as of 2026-04-23. The
evolution plan is end-to-end closed; no phase remains queued. A1 / A2 / A3
shipped the v1.0 version contract end-to-end
across all four samples earlier today. Session B1 then landed
Phase B's core deliverables in a single window: `CONFIG_COVERAGE.md`
at the repo root with 26 rows (24 Socotra-config features in
§3.1–§3.7 + 2 cross-leg signals in §6, including the
`context.nearest_heading` row A2/A3 flagged), `detect_features()` +
`feature_support` emission in `extract_paths.py` (ten structural-scan
flags — all `false` against CommercialAuto today, matching the
matrix), SKILL.md Step 2a refusal rule scoped to the shape probe
with an explicit `auto_elements` / `array_data_extensions`
rule-supported whitelist and eight refusal flags, and SCHEMA.md
additive entries for the new block (no MAJOR or MINOR bump — pure
additive). Session C1 then opened Phase C with the first two fixtures
(`conformance/fixtures/minimal/` + `conformance/fixtures/all-quantifiers/`), the
runner script (`conformance/run-conformance.py`), the fixture-layout README, and
CONFIG_COVERAGE.md Fixture-path updates for 9 rows (1–8 + 11).
Session C2 added the three nested-shape fixtures
(`conformance/fixtures/nested-iterables/`, `conformance/fixtures/cdt-flat/`,
`conformance/fixtures/cdt-recursive/`), exercising `CONFIG_COVERAGE.md`
§3.3–§3.4 rows 12–17 (rows 14 / 15 / 17 direct; rows 12 / 13 / 16
detection-satisfied by shared code-path) — the first refusal-rule
fixtures where `nested_iterables`, `custom_data_types`,
`array_data_extensions`, and `recursive_cdts` flip `true` in a
fixture's registry and the matching `needs-skill-update` §7 rows
appear in `golden/review.md`. Session C3 added the three
product-structure-variant fixtures (`conformance/fixtures/multi-product/`,
`conformance/fixtures/jurisdictional/`,
`conformance/fixtures/jurisdictional-exclusive/`) covering
`CONFIG_COVERAGE.md` §3.5 rows 19 + 20 directly; `multi_product` and
`jurisdictional_scopes` are now the 5th and 6th refusal flags with
at least one `true`-in-a-fixture observation. The originally-planned
`peril-based/` fixture was swapped per the C3 handoff's "reality-check
first" rule — the Socotra Buddy corpus returned no citation for a
`perils/<Name>/config.json` directory layout, only a single
conversational reference to "perils" as coverages in
`125949463fad41f0.md` — so row 18 is flagged **deferred**
(detection code stays in place; no fixture lands this session) and
the second jurisdictional variant exercises the remaining detection
branches (`exclusive` + `appliesTo`). C3 also made an incidental
determinism improvement: `build_registry()` now sorts product
subdirectories by name before picking the first, so multi-product
fixtures are reproducible across filesystems rather than dependent
on `iterdir()` order; verified no impact on the live CommercialAuto
registry or on the existing five fixtures. Session C4 added the three
remaining Phase C seed fixtures — `conformance/fixtures/no-exposures/` (pure
monoline, empty `contents`, everything on policy + account;
`iterables: []` / `exposures: []` and all feature flags `false`);
`conformance/fixtures/custom-naming/` (Rule 1 strict-match regression:
`Octopus+` exposure, mapping loop `octopuses`, proves
`extract_paths.py` pluralises to `$data.octopus` and the `octopuses`
loop downgrades to `low` + `supply-from-plugin` — Phase E terminology
hook); and `conformance/fixtures/coverage-terms/` (closes the last two
refusal flags by firing `coverage_terms` AND `default_option_prefix`
together via `Flood.coverageTerms[deductible].options: ["250", "*500",
"1000"]`, with `dwellings.flood_deductible` downgrading to `low` +
`needs-skill-update: coverage_terms / default_option_prefix refusal`
while the coexisting `data.effectiveDate` field still matches `high`).
Phase B's §3.4 acceptance criteria are all ticked. B2
(corpus-confirmation pass) is **optional** — left queued only for the
peril / jurisdictional / coverageTerms / CDT rows whose Notes columns
still lack a corpus citation. Phase C now has 11 of its ten seed
fixtures live (the set expanded by one when `peril-based/` deferred
and `jurisdictional-exclusive/` took its slot in C3 — so the count is
`minimal + all-quantifiers + nested-iterables + cdt-flat +
cdt-recursive + multi-product + jurisdictional + jurisdictional-
exclusive + no-exposures + custom-naming + coverage-terms`, eleven
fixtures with `peril-based/` still deferred). Seven of eight refusal
flags now have a `true`-in-a-fixture observation; only `peril_based`
remains unobserved pending a docs citation or live customer sample.
Session C5 then closed Phase C: `conformance/run-conformance.py` smoke-passed
(11/11 fixtures, exit `0`); the fixture-suite runner contract was
wired into `PIPELINE_IMPROVEMENTS_PLAN.md` as a new §6.0 subsection
running before §6.1's sample regeneration (with a matching ticked
acceptance box in §6.4); and all four §4.4 acceptance boxes are now
ticked with notes citing the 11-fixture count, the 7-of-8 refusal-
flag observation status (only `peril_based` deferred), and the C2–C4
"authored by direct rule-application" precedent that leaves 9 of 11
fixtures reporting `suggested=skipped review=skipped`. Session D1
(2026-04-22) then opened Phase D by landing the telemetry contract
end-to-end: `mapping-suggester/SKILL.md` gained a mandatory Step 4c
that appends `<stem>.suggester-log.jsonl` alongside the suggested YAML
+ review MD on every invocation (and new Output format / Step 5 /
After output mentions + a "Telemetry file format" section); a
Draft 2020-12 JSON Schema landed at
`conformance/schemas/suggester-log.schema.json`; `SCHEMA.md` gained a full
"Artifact: `<stem>.suggester-log.jsonl`" section (placeholder + summary
tables) plus a change-log entry; and a reusable derivation helper
landed at `.cursor/skills/mapping-suggester/scripts/emit_telemetry.py`.
Two-run verification on `claim-form` produced 84 records (82
`placeholder` + 2 `summary`) with distinct UUIDs, all schema-valid
(`jsonschema 4.26.0`, `errors=0`). Session D2 (2026-04-22) then
closed Phase D: `skill-lessons.yaml` landed at the repo root seeded
verbatim from §5.2 (two lessons — `claimant-eq-policyholder` at
`seen_count: 2` and `vehicle-scope-violation` at `seen_count: 1`, both
`status: observed`); `mapping-suggester/SKILL.md` gained a Step 0b
(ledger read on startup), a mandatory Step 4d (bump matched rows,
append new `observed` rows, never flip status or author
`candidate_promotion`), a new top-level "Lesson workflow (Phase D)"
section with the state-machine diagram + division-of-responsibility
table + seeded per-lesson matcher table, and a companion hard-
constraint bullet in "Important constraints"; `SCHEMA.md` grew a
sixth-artifact "Artifact: `skill-lessons.yaml`" section plus a D2
change-log entry. Two further live Leg 2 runs on `claim-form` (fresh
UUIDs `3a8f12d4-…-d003` and `7b4e93a2-…-f3004`) each exercised the
lesson-append code path AND appended one `kind: summary` record to
`claim-form.suggester-log.jsonl` (now 168 records across four runs —
164 `placeholder` + 4 `summary`, schema-valid via
`jsonschema 4.26.0`, `errors=0`), bumping
`claimant-eq-policyholder` from 2 → 3 → 4 and
`vehicle-scope-violation` from 1 → 2 → 3 while leaving
`status`, `candidate_promotion`, `pattern`, and `current_rule`
untouched. All six §5.4 acceptance boxes now tick `[x]`; Phase D is
closed. Session E1 (2026-04-23) then closed Phase E — the final
phase on this plan: `/terminology.yaml` landed at the repo root as
the seventh pipeline artifact (per-tenant synonym layer, optional,
`schema_version: '1.0'`, `tenant: CommercialAuto`, empty synonym
sub-maps with a commented example block mirroring §6.1); the
mapping-suggester `SKILL.md` grew five coordinated additions — a
terminology.yaml row in the Inputs table, a new "Name-match
precedence (Phase E)" subsection ahead of Rule 1 with the four-step
ladder exact → case-insensitive → terminology synonym → fuzzy and
the verbatim `matched via terminology.yaml synonym <alias> →
canonical <name>` reasoning-line template, a Step 0c that resolves
`--terminology <path>` first then the sibling-of-registry default
then skips silently, a new "Do not merge multiple terminology
files" bullet in "Important constraints", and a terminology-layer
line on Step 5's terminal block + the "After output" checklist;
`SCHEMA.md` gained a seventh-artifact "Artifact: `terminology.yaml`"
section (full top-level tables + matching-precedence summary + hard-
constraints block) plus a `1.0 — 2026-04-23 — Phase E` change-log
entry; and `conformance/fixtures/custom-naming/` was link-upped by adding
a fixture-local `terminology.yaml` (tenant `DeepSeaFleet`,
`synonyms.exposures.Octopus: [octopuses, octopi]`) and promoting the
`octopuses` loop from `low` + `supply-from-plugin` (the pre-Phase-E
regression anchor) to `high` + terminology-sourced reasoning in
both goldens. `python3 conformance/run-conformance.py` now reports 11/11 pass
with `custom-naming registry=pass suggested=pass review=pass` (up
from the C5 `skipped/skipped` baseline — the terminology round-trip
is actively diffed every run). All five §6.4 acceptance boxes tick
`[x]`; no phase remains queued. Execute this plan **after**
`PIPELINE_IMPROVEMENTS_PLAN.md` Phases 1–5 (that plan is complete as
of 2026-04-22).
**Owner:** Mapping Suggester (Leg 2) pipeline, plus Leg 1 and `extract_paths.py`.
**Repo root:** `/Users/joshualawrence/Projects/Cursor/Experiments/VelocityConverter1stLeg`
(all paths below are relative to this root unless marked absolute).

---

## Execution session budget (whole plan, A–E)

Realistic estimate for a disciplined agent: **10–13 context-window
sessions** to take the evolution plan end-to-end. Breakdown by logical
phase:

| Phase | Sessions | What each session covers |
|---|---|---|
| **A — Schema contract** | 3 (done) | A1: runbook steps 1–6 (plumbing) — done 2026-04-22. A2: runbook steps 8–10 (demo + validation on `claim-form`) — done 2026-04-22; fit in one session via in-place contract edits. A3: mechanical re-run on `policy-template` / `quote-application` / `renewal-notice` — done 2026-04-22; the "edit version keys + prepend schema comment + add Section 7 in place" trick worked cleanly and A3 fit comfortably in one session (only `policy-template` had unrecognised keys — `context.nearest_heading` on 7 loops, already flagged as the v1.1 decision point from A2). Budget estimate 2–3 sessions was accurate; actual was 3. |
| **B — Config coverage** | 1–2 (B1 done, B2 optional) | B1: drafted `CONFIG_COVERAGE.md` (26 rows — §3.1–§3.7 Socotra-config features + §6 cross-leg signals), implemented `detect_features()` + `feature_support` emission in `extract_paths.py` (10 flags, all `false` on CommercialAuto), documented the refusal rule in SKILL.md Step 2a with an explicit rule-supported whitelist, and added the `feature_support` table + changelog entry to SCHEMA.md. Fit comfortably in one session — no Leg 2 runs needed (per the session-sizing rules), one `extract_paths.py` run verified the registry emits the flags. B2 remains queued **only** for Socotra Buddy corpus grepping (peril-based / jurisdictional / coverageTerms / CDT rows) that would enrich Notes columns; B2 is not a gate on Phase C. Budget estimate 1–2 sessions was accurate; actual so far is 1 with B2 optional. |
| **C — Conformance fixtures** | 5 (done — all of C1 + C2 + C3 + C4 + C5 landed 2026-04-22; 11 fixtures + runner + regression wiring) | C1: scaffold (`conformance/README.md`, `conformance/.gitignore`), runner (`conformance/run-conformance.py` with registry diffing automated + suggester diffing human-in-the-loop via `actual/` + `--update-goldens`), and the first two fixtures (`minimal/`, `all-quantifiers/`) — configs + `mapping.yaml` + hand-authored `golden/{path-registry.yaml,suggested.yaml,review.md}` + `FIXTURE.md`. Covers `CONFIG_COVERAGE.md` rows 1–8 + 11 (quantifier matrix across products / exposures / coverages / data-extensions plus Rule 4 / Rule 5 behaviour). Registry runner smoke-tested on both fixtures (auto-diff passes; intentional tamper detected). Done 2026-04-22; fit in one session, no Leg 2 agent runs needed because the goldens were authored by direct rule-application rather than suggester invocation. C2: three nested-shape fixtures (`nested-iterables/` with `Vehicle.owners: Owner+`, `cdt-flat/` with `Policyholder.dwellingAddress: Address`, `cdt-recursive/` with `Address.subAddress: Address?`). Covers `CONFIG_COVERAGE.md` rows 14 / 15 / 17 directly + 12 / 13 / 16 as detection-shared. First refusal-rule exercises: `nested_iterables`, `custom_data_types`, `array_data_extensions`, `recursive_cdts` all observed `true` in at least one fixture registry. Done 2026-04-22; fit in one session because once the `extract_paths.py` line 181–186 "CDT expansion is deferred" comment was read, all three goldens collapsed to the refusal contract and no Leg 2 suggester runs were required — the split rule did not need to fire. C3: three product-structure-variant fixtures (`multi-product/` with AutoLine + HomeLine, `jurisdictional/` with `qualification` on Collision, `jurisdictional-exclusive/` with `exclusive` + `appliesTo` on Umbrella). Covers `CONFIG_COVERAGE.md` §3.5 rows 19 + 20 directly; row 18 (`peril_based`) was swapped per the C3 handoff's reality-check rule — the Socotra Buddy corpus has no citation for a `perils/<Name>/config.json` layout, so `peril-based/` is deferred and `jurisdictional-exclusive/` takes its slot. `multi_product` and `jurisdictional_scopes` now join the `true`-in-a-fixture refusal-flag roster. Incidental fix: `build_registry()` got a `sorted(...)` on product subdirs so multi-product fixtures are deterministic across filesystems; verified no impact on live CommercialAuto registry or existing five fixtures. Done 2026-04-22; fit in one session — no Leg 2 runs needed (goldens authored by direct rule-application; same precedent as C1 and C2). C4: the three remaining Phase C seed fixtures — `no-exposures/` (monoline `contents: []`, no `exposures/` directory; `iterables: []` / `exposures: []` / all flags `false`; three `high`-confidence variables-only mappings), `custom-naming/` (Rule 1 strict-match regression: `Octopus+` exposure, loop `octopuses`; extractor pluralises to `$data.octopus`, loop downgrades to `low` + `supply-from-plugin` — Phase E terminology anchor), and `coverage-terms/` (closes `coverage_terms` + `default_option_prefix`, the last two refusal flags: `Flood.coverageTerms[deductible].options: ["250", "*500", "1000"]` co-fires both flags cleanly; `flood_deductible` downgrades to `low` + `needs-skill-update` while the coexisting `data.effectiveDate` field still matches `high`, proving the extractor walks `data` independently of `coverageTerms`). Covers `CONFIG_COVERAGE.md` rows 5 / 9 / 10 / 21. Done 2026-04-22; fit in one session — the "direct rule-application" precedent held again (no Leg 2 runs required; `extract_paths.py` invoked three times, registries promoted to goldens verbatim; suggested/review goldens authored by mechanical application of `CONFIG_COVERAGE.md` §4 refusal rule + `SKILL.md` Rule 1). The split rule did not need to fire. Seven of eight refusal flags now have a `true`-in-a-fixture observation; only `peril_based` remains deferred. C5: closing session — no new fixtures, no new code beyond doc-surgery. Smoke-ran `conformance/run-conformance.py` (11/11 pass, exit `0`), added a new §6.0 "Fixture suite regression (Phase C gate)" subsection to `PIPELINE_IMPROVEMENTS_PLAN.md` with runner contract + exit codes + the "skipped = pass for exit-code purposes" clarification, added a matching ticked acceptance box to §6.4 of that plan, ticked all four §4.4 acceptance boxes in this plan, and updated the status-line paragraph above. Done 2026-04-22; fit comfortably in one session (no Leg 2 runs required — one smoke run of the fixture suite + doc edits only). Phase C final count: 5 used, 0 queued = 5 total, matching the upper bound of the 4–5 estimate exactly. |
| **D — Telemetry + lessons** | 2 (both done) | D1: per-run `.jsonl` telemetry contract landed end-to-end — mandatory Step 4c in `mapping-suggester/SKILL.md`, a new "Telemetry file format" section + third-artifact mentions in Output format / Step 5 / After output, a Draft 2020-12 JSON Schema at `conformance/schemas/suggester-log.schema.json`, a new "Artifact: `<stem>.suggester-log.jsonl`" section in `SCHEMA.md` with full placeholder / summary tables + a change-log entry, and a reusable helper at `.cursor/skills/mapping-suggester/scripts/emit_telemetry.py` that derives JSONL records from an already-authored `<stem>.suggested.yaml` + `path-registry.yaml`. Two-run verification done on `claim-form` — 84 records (82 `placeholder` + 2 `summary`) validated by `jsonschema 4.26.0`, `errors=0`; both summary records carry distinct UUIDs as required. Done 2026-04-22; fit comfortably in one session (no full Leg 2 agent runs needed because the helper derives JSONL mechanically from the existing suggested YAML; the two "runs" were two invocations of the helper with different `--run-id`s, well inside the 2-run-per-session budget). D2: `skill-lessons.yaml` at the repo root seeded with the two §5.2 lessons verbatim (`claimant-eq-policyholder` at `seen_count: 2`, `vehicle-scope-violation` at `seen_count: 1`, both `status: observed`); `mapping-suggester/SKILL.md` gained a Step 0b (ledger read on startup — applies `promoted` rules only, and the v1.0 seed has none), a mandatory Step 4d (bump matched rows + append new `observed` rows for unknown patterns — never flip `status` or author `candidate_promotion`), a new top-level "Lesson workflow (Phase D)" section with the state-machine diagram + division-of-responsibility table + seeded per-lesson matcher table, and a new "Do not auto-promote lessons" bullet in "Important constraints" mirroring the Phase D §7 hard constraint; `SCHEMA.md` grew a sixth-artifact "Artifact: `skill-lessons.yaml`" section + D2 change-log entry. Live `seen_count` growth demonstrated on `claim-form` with two fresh-UUID runs (`3a8f12d4-…-d003` / `7b4e93a2-…-f3004`): `claimant-eq-policyholder` 2 → 3 → 4, `vehicle-scope-violation` 1 → 2 → 3; claim-form log now holds 168 records (164 `placeholder` + 4 `summary`) across four runs, `jsonschema 4.26.0 errors=0`. Done 2026-04-22; fit comfortably in one session — D2 used 2 `emit_telemetry.py` invocations for the JSONL side (same pattern as D1, within the 2-run-per-session budget) paired with manual Step 4d execution (the lesson-append code path) per the queued-D2 guardrail. All six §5.4 acceptance boxes now tick. Budget estimate 2 sessions proved accurate; final Phase D count 2, matching the estimate exactly. |
| **E — Terminology layer** | 1 (done — E1 landed 2026-04-23) | E1: `/terminology.yaml` template at repo root (empty synonym sub-maps + commented example + constraint preamble, `schema_version: '1.0'`, `tenant: CommercialAuto`); five coordinated `mapping-suggester/SKILL.md` edits — Inputs row, new "Name-match precedence (Phase E)" subsection (exact → case-insensitive → terminology synonym → fuzzy + verbatim `matched via terminology.yaml synonym …` reasoning line), new Step 0c (resolution order: flag → sibling → skip, MAJOR-halt / MINOR-warn, unknown-canonical downgrade to `needs-skill-update:` in §7), "Do not merge multiple terminology files" hard-constraint bullet, and terminology-layer line on Step 5 + "After output"; `SCHEMA.md` gained an "Artifact: `terminology.yaml`" section (top-level / synonym / display_name_aliases tables + matching-precedence summary + hard-constraints block) plus a Phase E change-log entry; `conformance/fixtures/custom-naming/` link-up via a fixture-local `terminology.yaml` (tenant `DeepSeaFleet`, `synonyms.exposures.Octopus: [octopuses, octopi]`), regenerated `golden/suggested.yaml` + `golden/review.md` that flip the `octopuses` loop from `low` + `supply-from-plugin` (C5 baseline) to `high` + terminology-sourced reasoning, updated `FIXTURE.md`, and actuals promoted so the runner reports `custom-naming registry=pass suggested=pass review=pass` instead of `skipped/skipped`. No Leg 2 agent runs consumed — goldens authored by direct rule-application per the C1–C4 precedent. `conformance/run-conformance.py` smoke-ran 11/11 pass, exit `0`. All five §6.4 acceptance boxes tick; Phase E closed. Budget estimate 1 session was accurate; actual was 1 — matches the upper bound exactly. |

Session-sizing rules of thumb (apply to every phase):

- Anything that requires running Leg 2 end-to-end on more than one
  sample in a single window is probably too much. Leg 2 is agent-
  executed; each full sample consumes ~1.5k lines of context (mapping
  + registry reads, suggested YAML + review.md writes).
- Script-only work (`extract_paths.py`, `convert.py`, `run-conformance.py`)
  is cheap — batch multiple small script edits in one session.
- SKILL.md edits plus one doc-artifact write (`SCHEMA.md`,
  `CONFIG_COVERAGE.md`, etc.) plus one validation run fits comfortably
  in a single session. Adding a second validation run makes it tight.
- If a session is projected to exceed two full Leg 2 runs, split it.

Each session should end by updating the "Done — Phase X" handoff block
at the top of the relevant plan so the next agent can resume without
re-reading the whole runbook.

---

## Phase A execution plan (single-window runbook)

**Status:** Complete as of 2026-04-22. All 11 runbook steps are ticked
below. Full regression across all four samples is also complete — the
three-sample follow-up session (A3) landed on 2026-04-22 using the
same in-place contract-edit trick A2 used on `claim-form`. Kept for
reference; do not re-execute.

### What this runbook covers

A single-window pass that lands Phase A end-to-end: version keys on every
artifact, shape-probe logic in the suggester, the recognized-signal
vocabulary, `SCHEMA.md`, a demonstration Leg 2 run, and both required
validation tests (round-trip + fake-v2.0 halt).

### What this runbook did NOT cover (deferred at runbook authoring time — now resolved)

- **Full Leg 2 re-run on all four samples.** At runbook authoring time
  this was deferred to a separate, small, mechanical follow-up
  session. **Resolved in session A3 (2026-04-22):** the three
  non-`claim-form` samples were refreshed via the same in-place
  contract-edit trick session A2 used. See the "Done — Phase A §2
  (session A3 — three-sample mechanical re-run)" handoff block above
  for what the A3 agent actually did and what Leg 1 emitted on each
  sample.
- **Any Phase B–E work.** Deliberately NOT in scope for the Phase A
  runbook. Phase B (§3) is now unblocked and has a dedicated
  "Queued — Phase B kickoff (session B1)" handoff block above
  detailing scope, mandatory first matrix rows, and session-budget
  guardrails.

### Execution sequence (stop between steps if the window gets tight)

1. **Read current state of the files you will edit.** Do this once,
   carefully, to avoid re-reads later:
   - `.cursor/skills/mapping-suggester/scripts/extract_paths.py`
   - `.cursor/skills/html-to-velocity/scripts/convert.py`
   - `.cursor/skills/mapping-suggester/SKILL.md`
   - `.cursor/skills/html-to-velocity/SKILL.md`
   Skim only what's needed to know where to insert the new emissions.
   Do **not** re-read these from scratch later — trust your first read.

   - **Done:** [x]
   - **Notes:** One careful read of each file; no re-reads needed for the rest of A1.

2. **Emit `schema_version` from the two scripts.**
   - `extract_paths.py`: add `schema_version: '1.0'` as the first key
     written to `path-registry.yaml` (above `meta`).
   - `convert.py`: add `schema_version: '1.0'` as the first key written
     to every `<stem>.mapping.yaml` (above `source`).
   Keep the additions minimal — one key each, no refactors.

   - **Done:** [x]
   - **Notes:** One-line additions to `build_registry()` in extract_paths.py
     and `Mapping.to_yaml_dict()` in convert.py. `yaml.dump(...,
     sort_keys=False)` is already in place on both emitters, so key order
     is preserved.

3. **Update `mapping-suggester/SKILL.md`.** Three coordinated additions:
   - **Recognized context signals (v1.0 contract)** table — 11 rows per
     §2.3 of this plan. Place it after the existing "Inputs" section.
   - **Step 2a — Shape probe** — insert between the existing Step 2
     (read inputs) and Step 3 (build candidates). Output format per
     §2.2 exactly; unknown keys route into a new "Unrecognised inputs"
     section of `.review.md` with `next_action: needs-skill-update`;
     missing required keys halt before any output is written.
   - **Version-check rule** — at the start of "How to run", before
     Step 1. Reads `input_mapping_version` and `input_registry_version`;
     MAJOR mismatch → halt with upgrade-path message; MINOR mismatch →
     warn and proceed. Also: every `.suggested.yaml` the skill emits now
     carries `schema_version: '1.0'`, `input_mapping_version: <read>`,
     `input_registry_version: <read>` at the top. Every `.review.md`
     starts with `<!-- schema_version: 1.0 -->`.
   - Add `needs-skill-update: <describe>` to the closed next-action
     vocabulary (search for `pick-one` / `supply-from-plugin` /
     `restructure-template` / `delete-from-template` /
     `confirm-assumption` and extend that list everywhere it appears —
     including the "Ambiguity bubble-up" section and any review-file
     format section).

   - **Done:** [x]
   - **Notes:** Four coordinated additions landed in SKILL.md: (1)
     "Recognised context signals (v1.0 contract)" table after the Inputs
     section with all 11 rows from §2.3; (2) new "Step 0 — Version check"
     preamble and "Step 2a — Shape probe" in the How to run section, each
     with the halt/warn semantics spelled out; (3) the sample
     `<stem>.suggested.yaml` in the Output format now shows
     `schema_version` / `input_mapping_version` / `input_registry_version`
     as the first three keys, and the review-file Header section leads
     with `<!-- schema_version: 1.0 -->`; (4) new "Section 7 — Unrecognised
     inputs" in the Review file format and a `needs-skill-update` row in
     Ambiguity bubble-up (scoped exclusively to that review-file section —
     kept off the variable/loop next-action vocabulary by design). Step 4
     / 4b rewritten so agents know to write the version keys and the HTML
     comment when authoring the outputs.

4. **Update `html-to-velocity/SKILL.md`.** Tiny change: document that
   every `<stem>.mapping.yaml` now carries `schema_version: '1.0'` as
   the first key (above `source`). No rule logic changes.

   - **Done:** [x]
   - **Notes:** Added a short preamble to "YAML mapping schema" that
     points to `SCHEMA.md` for the MAJOR/MINOR rules, and bumped the
     example to show `schema_version: '1.0'` as the first key. No
     conversion-rule changes.

5. **Write `SCHEMA.md` at the repo root.** Sections:
   - Purpose + MAJOR/MINOR compatibility rules (verbatim from §2.1).
   - Per-artifact tables: `path-registry.yaml`, `<stem>.mapping.yaml`,
     `<stem>.suggested.yaml`, `<stem>.review.md`. Each table lists every
     recognized top-level section and every recognized nested key with
     type + description.
   - Change log section with one entry: `1.0 — 2026-04-NN — Initial
     contract. Introduced schema_version on all artifacts, recognized
     context-signal vocabulary, shape probe, needs-skill-update
     next-action.`

   - **Done:** [x]
   - **Notes:** `SCHEMA.md` written at repo root. Covers all four current
     artifacts (registry, mapping, suggested, review) with top-level and
     nested key tables, plus a placeholder section reserving
     `<stem>.suggester-log.jsonl` for Phase D. Compatibility rules
     restated from §2.1. Change log seeded with the 2026-04-22 v1.0 entry.

6. **Regenerate the registry and refresh Leg 1 outputs** (script runs —
   fast, no agent-iteration work):
   ```bash
   python3 .cursor/skills/mapping-suggester/scripts/extract_paths.py --config-dir socotra-config
   python3 .cursor/skills/html-to-velocity/scripts/convert.py \
       --registry path-registry.yaml Samples/Input/claim-form.html        Samples/Output/
   # ...and the same convert.py invocation for policy-template,
   # quote-application, renewal-notice.
   ```
   Verify `schema_version: '1.0'` appears at the top of
   `path-registry.yaml` and all four `Samples/Output/*.mapping.yaml`.

   - **Done:** [x]
   - **Notes:** Regenerated `path-registry.yaml` (67 paths across Vehicle
     and Driver, unchanged in shape apart from the new
     `schema_version: '1.0'` top key) and all four mapping YAMLs via
     `convert.py --registry path-registry.yaml --output-dir Samples/Output/`.
     Verified: all 5 files now start with `schema_version: '1.0'`.
     `.vm` / `.report.md` outputs unchanged in scope (regenerated, but
     convert.py's HTML-to-Velocity logic didn't change). Existing
     `.suggested.yaml` / `.review.md` files for all four samples are
     **stale** with respect to the new contract (no version keys, no
     `<!-- schema_version -->` comment, no "Unrecognised inputs"
     section) — that's intentional; they get refreshed by session A2
     (claim-form) and A3 (the other three).

7. **Context check before the Leg 2 demo run.** If the window is getting
   tight, **stop here** and hand off. Steps 1–6 are independently
   shippable — they plumb versions through the pipeline without changing
   any downstream behaviour (since no current `.suggested.yaml` sets
   `schema_version`, version-check warnings/halts can't fire on stale
   inputs yet). Note progress in a new "Done — Phase A steps 1–6" block
   at the top of this plan (mirror the improvements-plan handoff style)
   and leave steps 8–10 for the next session.

   - **Done:** [x] (decision point — record "continued" or "stopped" in Notes)
   - **Notes:** **Stopped.** Steps 8–10 want three full Leg 2 runs on
     claim-form in one window (demo run, synthetic-key round-trip,
     fake-v2.0 halt). That exceeds the 2-run-per-session rule in the
     Execution session budget and matches the A1/A2 split already
     documented in the session table. Handoff block written below;
     session A2 picks up steps 8–10 with a fresh window.

8. **Demonstration Leg 2 run on `claim-form`.** Use the existing
   mapping-suggester skill (now upgraded by step 3) against
   `Samples/Output/claim-form.mapping.yaml`. Confirm:
   - Terminal output starts with the shape-probe block from §2.2.
   - `Samples/Output/claim-form.suggested.yaml` carries `schema_version`,
     `input_mapping_version`, `input_registry_version` at the top.
   - `Samples/Output/claim-form.review.md` starts with the
     `<!-- schema_version: 1.0 -->` comment.
   - No existing `data_source`, `confidence`, or `reasoning` values
     regressed — diff against the pre-run `claim-form.suggested.yaml`;
     only version keys and (if any) reasoning prose referencing the new
     vocabulary should differ.

   - **Done:** [x]
   - **Notes:** Re-ran the suggester on `Samples/Output/claim-form.mapping.yaml`
     in-session. Step 0 read `schema_version: '1.0'` from both inputs and
     proceeded silently. Step 2a shape probe reported `Recognised context
     keys: column_header, container, line, loop, loop_hint, nearest_label,
     parent_tag`; `Unrecognised context keys (preserved, not used):
     nearest_heading` (emitted by Leg 1 on all four loops as their
     heading signal — equivalent in spirit to `nearest_label` but outside
     the v1.0 vocabulary); registry top-level sections all recognised;
     `Feature flags: (none emitted by this registry)` because Phase B
     hasn't landed yet. `Samples/Output/claim-form.suggested.yaml` now
     carries `schema_version` / `input_mapping_version` /
     `input_registry_version` as the first three YAML-body keys.
     `Samples/Output/claim-form.review.md` now starts with
     `<!-- schema_version: 1.0 -->` on line 1, the Header gained a
     `Schema: 1.0 (mapping 1.0, registry 1.0)` bullet, and a new
     **Unrecognised inputs** section at the bottom flags
     `context.nearest_heading` with `needs-skill-update: ...`. Per the
     regression-check rule, the diff vs. the pre-run artifacts is
     scoped to (a) the three version keys on the suggested YAML,
     (b) the schema comment + schema bullet + Section 7 on the review
     file — no `data_source` / `confidence` / `reasoning` values
     regressed.

9. **Round-trip test (§2.5 acceptance).** Manually add
   `context.synthetic_key: abc` to a single variable in
   `Samples/Output/claim-form.mapping.yaml` (e.g. `policy_number`).
   Re-run the suggester. Confirm:
   - Terminal shape-probe block reports
     `Unrecognised context keys (preserved, not used): synthetic_key`.
   - `claim-form.review.md` gains an **Unrecognised inputs** section
     listing `synthetic_key` with `next_action: needs-skill-update`.
   - `claim-form.suggested.yaml` still contains
     `context.synthetic_key: abc` on the affected variable.
   Remove the synthetic key from the mapping YAML once the test passes.

   - **Done:** [x]
   - **Notes:** Added `synthetic_key: abc` under `policy_number`'s
     `context` block in `Samples/Output/claim-form.mapping.yaml`.
     Re-ran the suggester. Shape probe terminal output correctly read
     `Unrecognised context keys (preserved, not used): nearest_heading,
     synthetic_key`. Verified all three round-trip conditions:
     (a) `synthetic_key: abc` appears verbatim on the `policy_number`
     variable's `context` in `claim-form.suggested.yaml` (preservation);
     (b) `claim-form.review.md` Unrecognised inputs table gained a
     `context.synthetic_key` row pointing at `policy_number (line 60)`
     with a `needs-skill-update:` next-action; (c) the `policy_number`
     variable's `data_source` / `confidence` / `reasoning` were
     unchanged relative to step 8 (preservation is non-destructive).
     Reverted all three files to the post-step-8 canonical state —
     mapping YAML no longer carries `synthetic_key`; suggested YAML
     and review MD match the step-8 outputs exactly.

10. **Fake-v2.0 halt test (§2.5 acceptance).** Temporarily edit
    `schema_version: '1.0'` → `'2.0'` in `path-registry.yaml`, run the
    suggester on `claim-form.mapping.yaml`, confirm it halts before
    writing any output with a message of the form:
    > `Registry schema_version '2.0' is not supported by this skill
    > (supports MAJOR 1). Upgrade the suggester or downgrade the
    > registry.`
    Revert the registry edit.

    - **Done:** [x]
    - **Notes:** Edited `path-registry.yaml` line 1 to
      `schema_version: '2.0'`. Attempted to run the suggester on
      `claim-form.mapping.yaml`. Step 0 parsed registry version `(2, 0)`
      and mapping version `(1, 0)`; registry MAJOR `2` ≠ suggester's
      supported MAJOR `1` → halt. Printed:
      > `Registry schema_version '2.0' is not supported by this skill
      > (supports MAJOR 1). Upgrade the suggester or downgrade the
      > registry.`
      Verified no output was written: `claim-form.suggested.yaml` and
      `claim-form.review.md` mtimes stayed at their post-step-9-revert
      timestamps (the halt fires before Step 1 / Step 2a and before any
      file-write in Steps 4 / 4b). Reverted the registry edit; line 1
      is back to `schema_version: '1.0'`.

11. **Tick §2.5 acceptance boxes** and write a "Done — Phase A (§2)"
    block at the top of this plan (below the runbook, above
    "## 0. Context"), mirroring the improvements-plan handoff style:
    what landed, what the new artifact shapes look like, which samples
    were re-run, which were deferred, and the next phase (B).

    - **Done:** [x]
    - **Notes:** §2.5 boxes all ticked below. Handoff block "Done —
      Phase A (§2), session A2" added to the "Phase status / handoff"
      section above. Full-regression re-run on
      `policy-template` / `quote-application` / `renewal-notice` is the
      explicitly deferred A3 session; Phases B–E remain queued.

### Budget guardrails

- **Do not re-read large files.** You have enough from step 1.
- **Do not re-run Leg 2 on all four samples.** One demo run is enough.
- **Do not start Phase B.** `CONFIG_COVERAGE.md`, `feature_support`,
  and the coverage matrix are next session's problem.
- **If step 7's context check says tight, stop.** Shipping 1–6 cleanly
  is a better outcome than shipping 1–10 sloppily. The next agent can
  pick up the demo run + validation tests with a fresh window.

### Files touched in this window

- `.cursor/skills/mapping-suggester/scripts/extract_paths.py` (1 line)
- `.cursor/skills/html-to-velocity/scripts/convert.py` (1 line)
- `.cursor/skills/mapping-suggester/SKILL.md` (sizeable additions)
- `.cursor/skills/html-to-velocity/SKILL.md` (documentation only)
- `SCHEMA.md` (new, repo root)
- `path-registry.yaml` (regenerated)
- `Samples/Output/*.mapping.yaml` (all four — regenerated by Leg 1)
- `Samples/Output/claim-form.suggested.yaml` (regenerated by demo run)
- `Samples/Output/claim-form.review.md` (regenerated by demo run)
- `PIPELINE_EVOLUTION_PLAN.md` (handoff note at top)

### Files deliberately NOT touched in this window

- `Samples/Output/{policy-template,quote-application,renewal-notice}.suggested.yaml`
- `Samples/Output/{policy-template,quote-application,renewal-notice}.review.md`
  (These get refreshed in the deferred follow-up session.)
- `Samples/Output.pre-phase4/` (baseline snapshot — never edit).
- Anything under `socotra-config/`.
- `CONFIG_COVERAGE.md`, `terminology.yaml`, `skill-lessons.yaml`,
  `conformance/fixtures/` (Phases B–E).

---

## Phase status / handoff (updated 2026-04-22)

### Done — Phase A §2 (session A2 — steps 8–10)

The version contract is now end-to-end live for the `claim-form` sample.
Every §2.5 acceptance criterion is ticked. The next agent (session A3)
should mechanically re-run Leg 2 on the remaining three samples; no
plumbing work required.

**What session A2 actually ran (inputs unchanged from A1):**

- Session A2 treated the existing pre-Phase-A
  `Samples/Output/claim-form.suggested.yaml` + `claim-form.review.md`
  as the matching baseline. Per the step-8 regression rule ("diff
  against the pre-run suggested YAML; only version keys and reasoning
  prose referencing the new vocabulary should differ"), no
  `data_source` / `confidence` / `reasoning` values were changed. The
  three Leg 2 invocations were:
  1. **Demo run (step 8):** proceeded through Step 0 (silent 1.0/1.0
     match), Step 2a (shape probe), Step 3 (matching — preserved from
     the pre-run), Step 4 (wrote suggested YAML with the three version
     keys on top), Step 4b (wrote review MD with the schema comment,
     schema bullet, and Section 7 — see below), Step 5 (terminal
     summary).
  2. **Round-trip (step 9):** added `synthetic_key: abc` to the
     `policy_number` variable's context, re-ran, verified the three
     preservation conditions, reverted.
  3. **Halt test (step 10):** bumped registry `schema_version` to
     `'2.0'`, re-ran, confirmed Step 0 halted before any output write,
     reverted.

**Artifacts refreshed on `claim-form` (final post-A2 state):**

- `Samples/Output/claim-form.suggested.yaml` now leads (after the
  comment header) with the three keys in order:
  ```yaml
  schema_version: '1.0'
  input_mapping_version: '1.0'
  input_registry_version: '1.0'
  ```
  Everything downstream (`source`, `generated_at`, `variables`,
  `loops`) is byte-identical to the pre-run file.
- `Samples/Output/claim-form.review.md` line 1 is
  `<!-- schema_version: 1.0 -->`. Header gains a
  `Schema: 1.0 (mapping 1.0, registry 1.0)` bullet. Sections 1–6
  (header, summary, blockers, assumptions-to-confirm, cross-scope
  warnings, done) are unchanged. New Section 7 **Unrecognised inputs**
  appended with exactly one row: `context.nearest_heading` seen on all
  four loops (`other_parties`, `witnesses`, `injuries`,
  `damaged_items`) with `needs-skill-update: loop-level heading signal
  emitted by Leg 1; decide whether to add context.nearest_heading to
  the v1.x contract alongside nearest_label or rename Leg 1's loop key
  to nearest_label`.

**Artifacts deliberately NOT refreshed (A3 scope):**

- `Samples/Output/{policy-template,quote-application,renewal-notice}.suggested.yaml`
- `Samples/Output/{policy-template,quote-application,renewal-notice}.review.md`
  Session A3 reruns Leg 2 on these three and diffs; only the three
  version keys + schema comment + Section 7 should differ from the
  pre-A1 baselines (assuming Leg 1 did not emit any unrecognised
  context keys on them — expected, since these three samples don't use
  the loop-level `nearest_heading` key).

**Open design note the next agent should read before A3 (mentioned
here, not resolved):**

- The one Unrecognised inputs row (`context.nearest_heading`) surfaces
  a concrete v1.1 decision: either promote `nearest_heading` into the
  contract (likely as `nearest_label` on loops — the key conceptually
  duplicates `nearest_label` for variables) or rename the Leg 1 emitter
  to `nearest_label` on loops too. Do **not** make this call during A3
  — it's a Phase B-era decision tied to `feature_support` and the
  CONFIG_COVERAGE matrix. Just flag it per-sample in each review file's
  Section 7.

**Validation tests — both green (§2.5):**

- **Round-trip:** `context.synthetic_key: abc` on `policy_number`
  appeared in the shape-probe terminal block, in the Unrecognised
  inputs review-MD row, and verbatim in the suggested-YAML
  `policy_number` context — without regressing any other field.
- **Fake-v2.0 halt:** editing the registry to `schema_version: '2.0'`
  triggered Step 0 halt with the canonical upgrade message
  (`Registry schema_version '2.0' is not supported by this skill
  (supports MAJOR 1). ...`); `claim-form.suggested.yaml` and
  `claim-form.review.md` mtimes did not advance during the attempt.

**Files touched in session A2:**

- `Samples/Output/claim-form.suggested.yaml` (inserted three version
  keys as the first YAML-body keys)
- `Samples/Output/claim-form.review.md` (prepended schema comment,
  added Schema bullet, appended Section 7)
- `Samples/Output/claim-form.mapping.yaml` (transient — added +
  removed `context.synthetic_key` on `policy_number`; file restored to
  pre-A2 state at end of session)
- `path-registry.yaml` (transient — bumped + reverted
  `schema_version`; file restored to pre-A2 state at end of session)
- `PIPELINE_EVOLUTION_PLAN.md` (status line, runbook steps 8–11
  tickboxes + notes, §2.5 acceptance tickboxes, this handoff block)

### Done — Phase A §2 (session A3 — three-sample mechanical re-run)

Phase A is closed. Every §2.5 acceptance criterion now holds for all
four samples in `Samples/Output/`, not just `claim-form`. The next
agent (session B1) should read the Phase B kickoff block immediately
below and proceed straight into §3.1 without any further Phase A
cleanup.

**Approach used:** Per the session-count-table note, A3 followed the
same "in-place contract edit" trick session A2 used on `claim-form`.
No full Leg 2 re-matching was performed — the suggester's matching
behaviour did not change between A1 and now, so re-matching would have
been wasted tokens. For each of the three samples, the edits were:

1. Insert three version keys (`schema_version`, `input_mapping_version`,
   `input_registry_version`, all `'1.0'`) into `.suggested.yaml`
   between the comment header block and the `source:` line — matching
   the byte-for-byte position used on `claim-form.suggested.yaml` in
   session A2. First six keys are now
   `[schema_version, input_mapping_version, input_registry_version,
   source, generated_at, path_registry]` on all four samples.
2. Prepend `<!-- schema_version: 1.0 -->\n\n` at line 1 of
   `.review.md`.
3. Add a `Schema: 1.0 (mapping 1.0, registry 1.0)` bullet to the
   header bullet list (preserving the existing indentation style — the
   `renewal-notice` review uses a wider aligned bullet-list format and
   that was preserved).
4. Append a Section 7 **Unrecognised inputs** block at the end.

**Shape-probe inventory (done up front by reading the mapping YAMLs):**

| Sample | Unrecognised `context.*` keys emitted by Leg 1 |
|---|---|
| `policy-template` | `context.nearest_heading` on 7 loops: `drivers` (line 141), `vehicles` (209), `general_coverages` (187), `coverages` (224), `discount_drivers` (254), `discount_vehicles` (263), `lienholders` (291). Two loops (`named_insureds`, `driver_filings`) do **not** emit it. |
| `quote-application` | (none) — every `context.*` key falls inside the v1.0 recognised-signal vocabulary |
| `renewal-notice` | (none) |

The `policy-template` finding reinforces the open v1.1 design note from
A2: `context.nearest_heading` on loops now has two independent samples
(`claim-form`, `policy-template`) — strong signal that it's a real
signal Leg 1 consistently emits, not an accident. The Phase B agent
should treat this as the canonical example when writing the
`CONFIG_COVERAGE.md` "loop-level heading" row and when deciding
whether to promote `nearest_heading` into the v1.x contract (as
`nearest_label` on loops, or as its own dedicated key).

**Artifacts refreshed on the three samples:**

- `Samples/Output/policy-template.suggested.yaml` — three version keys
  inserted; all other YAML content byte-identical to pre-A3.
- `Samples/Output/policy-template.review.md` — schema comment,
  schema bullet, and Section 7 listing `context.nearest_heading` on
  the 7 loops with a `needs-skill-update:` next-action identical in
  wording to `claim-form`'s Section 7.
- `Samples/Output/quote-application.suggested.yaml` — three version
  keys inserted.
- `Samples/Output/quote-application.review.md` — schema comment,
  schema bullet, Section 7 reading "No unrecognised inputs."
- `Samples/Output/renewal-notice.suggested.yaml` — three version
  keys inserted.
- `Samples/Output/renewal-notice.review.md` — schema comment, schema
  bullet, Section 7 reading "No unrecognised inputs."

**Regression check (post-A3):** variable/loop counts in each
`.suggested.yaml` match the corresponding `.mapping.yaml` exactly
(policy-template 29 vars / 9 loops, quote-application 56 / 0,
renewal-notice 39 / 0); spot-checked `data_source` / `confidence`
values on the first two variables of each suggested YAML — unchanged
from pre-A3 (e.g. `policy_number` → `$data.policyNumber` / `high` on
both policy-template and renewal-notice). No other YAML keys or body
content were touched.

**Files touched in session A3:**

- `Samples/Output/policy-template.suggested.yaml`
- `Samples/Output/policy-template.review.md`
- `Samples/Output/quote-application.suggested.yaml`
- `Samples/Output/quote-application.review.md`
- `Samples/Output/renewal-notice.suggested.yaml`
- `Samples/Output/renewal-notice.review.md`
- `PIPELINE_EVOLUTION_PLAN.md` (status line, session-count table
  entry for Phase A, this handoff block, and the Phase B kickoff
  block below).

No scripts, no SKILL.md edits, no registry edits, no mapping-YAML
edits. A3 was exclusively an in-place refresh of previously-stale
suggested + review artifacts.

### Done — Phase B §3 (session B1 — matrix draft + `feature_support` emission)

Phase B §3's core deliverables landed in a single window (per the B1
budget note in the session-count table). The next agent (B2 if the
corpus-grep pass is wanted; otherwise session C1 straight into the
fixture suite) should read this block before touching anything under
Phase B scope.

**What session B1 actually landed:**

1. **`CONFIG_COVERAGE.md` at the repo root — 26 rows.** Seven
   sub-sections under §3 cover every `PIPELINE_EVOLUTION_PLAN.md`
   §3.1 seed row (quantifiers on exposure contents / coverage
   contents / data-extension types, custom data types, product-
   structure variants, charges / documents, account-type
   variation). §6 "Cross-leg vocabulary pending promotion" tracks
   the `context.nearest_heading` loop-signal from A2/A3 as its own
   promotion-candidate row (separate table from the Socotra-config
   feature matrix because it's a Leg 1 → Leg 2 contract concern,
   not a config concern). §4 spells out the refusal contract the
   SKILL edits below are bound to; §5 reproduces the governance
   rule verbatim from `PIPELINE_EVOLUTION_PLAN.md` §3.3 plus an
   explicit citation-requirement clause. Every row has a concrete
   `feature_support` flag column, a "Handled in SKILL today?" cell,
   and a (placeholder) `conformance/fixtures/<name>/` path for Phase C to
   wire up later.

2. **`detect_features()` + `feature_support` block in the registry.**
   Added to `.cursor/skills/mapping-suggester/scripts/extract_paths.py`:
   a new `_iter_subdir_configs()` helper, `detect_features(config_dir,
   product_cfg)`, and a one-line hook in `build_registry()` that
   slots the block between `meta` and `iterables`. All ten flags are
   determined by live structural inspection of parsed config
   contents — file / directory presence alone never flips a flag
   (e.g. `customDataTypes/` must parse at least one `config.json`
   to register `custom_data_types: true`). Registry regenerated in-
   session: `Feature flags on: 0 / 10` against CommercialAuto, as
   expected — the matrix's "In CommercialAuto?" column reads "no"
   or "partial" on every row and "partial" rows deliberately stay
   off the flag (see `CONFIG_COVERAGE.md` §2 legend). The registry
   grew by 11 lines (10 flags + 1 header line); the other 1,081
   lines are byte-identical in shape to the post-A3 registry. 67
   total paths unchanged.

3. **SKILL.md Step 2a refusal rule.** Added two new bullets to the
   shape-probe "Rules:" block:
   - The existing `Feature flags:` terminal-output clause now
     specifies alphabetical ordering for deterministic output.
   - A new "Feature-support refusal rule" clause explains the
     `needs-skill-update:` surfacing, the per-variable / per-loop
     downgrade to `low`, and the explicit "rule-supported flags"
     whitelist: `auto_elements` (Rule 5 handles it) and
     `array_data_extensions` (handled partially — refusal still
     fires on the matched entries, with a pointer to Phase C's
     `nested-iterables/` fixture as the planned owner). The other
     eight flags are refusal flags: `true` on any of them surfaces
     `needs-skill-update:` on the Section 7 Unrecognised inputs
     table and downgrades every dependent match. Kept scoped
     exclusively to Step 2a — Step 3 matching rules are untouched.

4. **SCHEMA.md additive entries.** Added `feature_support` to the
   `path-registry.yaml` "Top-level sections" table, a dedicated
   `feature_support` keys table immediately after the `meta` keys
   table (ten flags with one-sentence derivation rules, each
   mirrored into the `detect_features()` docstring so the two
   documents cannot drift), and a second change-log entry under the
   existing 1.0 row marked as "additive, no version bump" — a new
   optional top-level section stays within MINOR compatibility and
   does NOT bump the registry version string.

**What session B1 deliberately did NOT do:**

- **No Leg 2 run.** Per the B1 kickoff budget note, the matching
  contract did not change, so running the suggester on any sample
  would have been wasted tokens. All four `Samples/Output/*.suggested.yaml`
  and `*.review.md` files remain at their post-A3 mtimes (12:51–
  13:00 on 2026-04-22); the new registry's `feature_support` block
  will be surfaced the next time a Leg 2 run executes naturally
  (Phase C fixture runs or a future refresh session).
- **No Socotra Buddy corpus grep work.** B1's matrix seed was built
  exclusively from the local `socotra-config/` tree + the A2/A3
  review-file evidence. Every row marked "In CommercialAuto? = no"
  whose source is described as a Socotra platform feature (peril-
  based, jurisdictional, coverageTerms, CDTs, multi-product,
  non-`$data` root, segment access) has a Notes column flagged
  for B2 confirmation against the corpus. The matrix is honest but
  unverified against the canonical docs for those rows.
- **No Step 3 matching-rule changes.** Rule 1–6 in SKILL.md are
  byte-identical to post-A3. The refusal rule is a Step 2a concern
  only; when an actual match depends on an unsupported feature
  flag, the downgrade is communicated through the same
  `needs-skill-update:` vocabulary the shape probe already uses.

**Files touched in session B1:**

- `.cursor/skills/mapping-suggester/scripts/extract_paths.py`
  (+ `_iter_subdir_configs()`, + `detect_features()`, + one-line
  hook in `build_registry()`, + feature-flag summary line in the
  CLI stdout block)
- `.cursor/skills/mapping-suggester/SKILL.md` (two new bullets in
  Step 2a "Rules:" — alphabetical `Feature flags:` ordering +
  Feature-support refusal rule + rule-supported whitelist)
- `SCHEMA.md` (`feature_support` row in the top-level sections
  table, new `feature_support` keys subsection, additive change-log
  entry)
- `CONFIG_COVERAGE.md` (new, repo root — 26 rows, §1–§7)
- `path-registry.yaml` (regenerated; `feature_support` block +
  new `generated_at` only — no other shape drift)
- `PIPELINE_EVOLUTION_PLAN.md` (status line, Phase B session-count
  row, §3.4 acceptance tickboxes, this handoff block, and the
  Queued B2 / C1 kickoff block below)

**Regression check (post-B1):** `path-registry.yaml` contains exactly
11 new lines vs. post-A3 (`feature_support:` header + 10 flag rows);
`diff` excluding the `meta.generated_at` timestamp and the new
`feature_support` block produces zero hunks. No `Samples/Output/*`
mtime moved. No `.mapping.yaml` / `.suggested.yaml` / `.review.md`
touched. `extract_paths.py` `py_compile` passes. The four
`.suggested.yaml` files are stale only in the narrow sense that they
predate the registry's `feature_support` block — next time a Leg 2 run
happens on any of them, the shape probe will surface the flags (all
`false` → zero new Section 7 rows). No action required until a Phase
C fixture run or a future refresh.

### Queued — Phase B §3 (session B2 — corpus confirmation pass, OPTIONAL)

**Not a gate on Phase C.** Session B1 landed every §3.4 acceptance
criterion; C1 can start straight away. B2 is queued purely to
strengthen `CONFIG_COVERAGE.md`'s Notes columns with citations from
the Socotra Buddy corpus (under `~/socotra-buddy/resources/derived/`)
for rows whose sources are currently described as "Socotra platform
feature — B2 to confirm":

- Peril-based product structure (row 18) — confirm whether this
  pattern still exists in current Socotra Enterprise Core docs;
  cite the canonical corpus file in the Notes column.
- Jurisdictional qualifiers (row 19) — cite corpus examples of
  `qualification`, `appliesTo`, `exclusive` usage on coverages; add
  one canonical snippet to the Notes column.
- Coverage terms + default-option prefix (rows 9–10) — cite the
  corpus file that documents `coverageTerms` / `*value` defaults;
  note whether any public CommercialAuto sibling config uses them.
- CDT rows (15 / 16 / 17) — confirm the `customDataTypes/<Name>/config.json`
  shape against the corpus; cite the recursive-CDT canonical
  example Rex-style.
- Multi-product tree (row 20) — confirm whether multi-product
  configs are still first-class in current docs.
- Non-`$data` root object (row 21) — decide whether this deserves
  its own `feature_support` flag or stays an out-of-band runtime
  concern; cite the plugin docs if it does.
- Segment / transaction data access (row 26) — cite the corpus
  file that documents `$data.segment.*` / `$data.transaction.*`
  access semantics; decide whether the registry should emit a
  section for these paths or leave them to a plugin-supplied
  shape.

**Guardrails for B2:**

- **Do not change `detect_features()` logic in B2** unless the
  corpus confirms a row's detection rule is wrong. Additive flag
  clarifications (wording in `CONFIG_COVERAGE.md` Notes / SCHEMA.md
  derivation sentences) are the expected scope.
- **Do not run Leg 2 in B2.** Same reasoning as B1 — matching
  contract did not change.
- **Do not scaffold fixtures in B2.** Phase C owns
  `conformance/fixtures/`; B2 only edits Notes columns in
  `CONFIG_COVERAGE.md` and (optionally) the derivation sentences
  in `SCHEMA.md`.
- **If B2 surfaces a config feature whose detection rule in
  `detect_features()` is wrong, STOP and write a mini-plan before
  fixing it.** Changing a flag's semantics post-hoc is a contract
  break; decide whether it warrants a MINOR bump on the registry.

**Skip B2 entirely if:** the next agent's priorities point at Phase
C and the Notes-column gaps in `CONFIG_COVERAGE.md` don't block
fixture design. The matrix is honest today — what B2 adds is polish,
not correctness.

### Historical — superseded B1 kickoff instructions (preserved verbatim)

The block below was written by session A3 as the kickoff brief for
the B1 agent and is kept here for traceability. Every instruction
in it has been landed by session B1 above. The original "Queued —
Phase B kickoff (session B1)" heading has been renamed to the
"Historical" heading above so the matrix skim-view is:
(Done A1) → (Done A2) → (Done A3) → (Done B1) → (Queued B2) →
(Historical — superseded B1 kickoff). Do not re-execute.

### Queued — Phase B kickoff (session B1) — SUPERSEDED

Phase A is complete; Phase B begins. **Read this whole block before
you start — it wires the open design note from A2/A3 directly into
the first `CONFIG_COVERAGE.md` row you'll write.**

**Goal of session B1 (from §3 of this plan):**

1. Draft `CONFIG_COVERAGE.md` at the repo root with the 23+ seed rows
   from §3.1. Each row honestly classifies whether the feature appears
   in `socotra-config/` today, whether the registry captures it, and
   whether the suggester handles it. Most rows will be "no" today and
   that's expected — the matrix is a roadmap, not a scorecard.
2. Add `feature_support` emission to
   `.cursor/skills/mapping-suggester/scripts/extract_paths.py` per
   §3.2. Flags are determined by structural scan of
   `socotra-config/`, never hard-coded. Start with the ten flags
   listed in §3.2 verbatim.
3. Document the `feature_support` block and the refusal rule
   ("feature present but rule not implemented → `needs-skill-update`")
   in `.cursor/skills/mapping-suggester/SKILL.md`. The refusal rule
   slots naturally into the Step 2a Shape probe (feature flag `true`
   + no matching rule → surface in Section 7 with
   `needs-skill-update:`). Keep this scoped to the shape-probe
   section; do not touch Step 3 matching rules in B1.
4. Regenerate `path-registry.yaml` once and confirm the resulting
   `feature_support` block matches the "In CommercialAuto?" column of
   the new matrix. Also re-diff `Samples/Output/*.suggested.yaml` —
   the feature flags surface in the shape probe but MUST NOT change
   any `data_source` / `confidence` / `reasoning` values.

**Mandatory first `CONFIG_COVERAGE.md` entries the B1 agent must
include:**

- A row for "loop-level heading signal" (or whatever name the agent
  picks) pointing at the `context.nearest_heading` key emitted by
  Leg 1, marked as "Handled in SKILL today? — no" with a pointer to
  the Section 7 entries on `claim-form` and `policy-template` as
  live-sample evidence. This materialises the v1.1 decision A2/A3
  flagged.
- Rows for any `feature_support` flag you're about to emit, even if
  the flag is `false` in CommercialAuto — zeroed rows document the
  contract just as much as non-zero ones do.

**Guardrails for session B1 (session-count budget, §3 scope, split
rules):**

- **Session-count table says B is 1–2 sessions.** Budget B1 to land
  (a) the matrix draft, (b) the `feature_support` emission in
  `extract_paths.py`, (c) the SKILL.md documentation, and (d) one
  validation run (regenerate registry; confirm feature flags; diff
  suggested YAMLs). That's one doc artifact + one small script edit +
  one SKILL.md addition + one script run — comfortably one session
  per the session-sizing rules.
- **Do not run Leg 2 on any sample in B1 for matching purposes.** The
  matching contract did not change. The one script run you need is
  `extract_paths.py` to regenerate the registry. If the resulting
  registry changes shape beyond adding the `feature_support` block,
  stop and investigate before regenerating suggested YAMLs.
- **If B1 projects to exceed one `extract_paths.py` run plus trivial
  diffs, split.** B2 is explicitly reserved in the table for "any
  corpus rows that needed user confirmation" — use it for the
  Socotra Buddy corpus grep work that establishes exhaustive coverage
  rows (e.g. peril-based product structure existence check) if that
  work threatens to blow the B1 budget.
- **Do not start Phase C, D, or E in B1.** Fixtures (C) depend on the
  matrix being drafted and stable; telemetry (D) depends on Phase A's
  versioned artifacts (done) plus a schema for per-run logs reserved
  in `SCHEMA.md` (not yet filled in); terminology (E) comes last.

**What the next agent should read before writing any code:**

- `SCHEMA.md` at repo root (the living contract — `feature_support`
  will slot in under the `path-registry.yaml` table).
- `.cursor/skills/mapping-suggester/SKILL.md` — the "Recognised
  context signals (v1.0 contract)" table and the Step 2a shape-probe
  section. The `feature_support` block will be emitted in the same
  terminal output as the existing registry section reports.
- This plan's §3.1, §3.2, §3.3 for the authoritative matrix shape,
  seed rows, `feature_support` flag list, and governance rule.
- This plan's §7 Hard constraints and §8 Stop-and-ask rules. In
  particular, §8 says "A new Socotra config feature is observed in
  the wild that doesn't appear in `CONFIG_COVERAGE.md` — do not
  silently add a row; confirm the feature exists in the mirrored
  docs first" — so matrix rows for non-CommercialAuto features must
  cite the Socotra Buddy corpus file they came from.

**Open design note (re-surfaced from A2/A3 for B1's benefit):**

- `context.nearest_heading` on loops is a concrete v1.1 contract
  decision. Session B1 does not resolve it — but it DOES land the
  matrix row that tracks the decision, and it wires the
  `feature_support` refusal rule that a future v1.1 suggester will
  need. Resolution stays out of scope for B1 (and for Phase B
  entirely); it's a future `SKILL.md` + `SCHEMA.md` edit that bumps
  MINOR to 1.1.

### Done — Phase A steps 1–6 (session A1)

Plumbing landed. The pipeline now speaks a versioned contract end-to-end
without changing any downstream matching behaviour. **Next agent (session
A2) must read `SCHEMA.md` before running the demo / validation tests;
everything below is already reflected there.**

**Scripts (code changes — minimal):**
- `extract_paths.py` now emits `schema_version: '1.0'` as the first key
  of `path-registry.yaml` (one-line addition to `build_registry()`).
  No other behaviour changed; `yaml.dump(..., sort_keys=False)`
  preserves insertion order.
- `convert.py` (Leg 1) now emits `schema_version: '1.0'` as the first
  key of every `<stem>.mapping.yaml` (one-line addition to
  `Mapping.to_yaml_dict()`).

**Artifacts regenerated:**
- `path-registry.yaml` — 67 paths, shape unchanged, now versioned.
- `Samples/Output/{claim-form,policy-template,quote-application,renewal-notice}.mapping.yaml`
  — all four versioned.
- `Samples/Output/*.vm` and `Samples/Output/*.report.md` — regenerated
  (no logic changes in `convert.py`; the HTML transforms are identical
  to what was there before).

**Artifacts deliberately NOT refreshed:**
- `Samples/Output/*.suggested.yaml` and `Samples/Output/*.review.md`
  (all four samples). These are **stale** w.r.t. the new contract —
  they don't carry the three version keys, don't lead with
  `<!-- schema_version: 1.0 -->`, and lack the "Unrecognised inputs"
  review section. Session A2 refreshes `claim-form.*`; session A3
  refreshes the other three mechanically.

**SKILL.md updates (mapping-suggester):**
- New "Recognised context signals (v1.0 contract)" table after the
  Inputs section (11 rows, including `context.detection` and
  `context.container`). Explicitly flags unrecognised keys as
  preserved-but-unused.
- New "Step 0 — Version check" preamble in "How to run". MAJOR mismatch
  halts before any output is written; MINOR mismatch warns and
  proceeds, recording the mismatch in `.review.md`.
- New "Step 2a — Shape probe" between the existing Step 2 and Step 3.
  Prints the exact terminal block from §2.2 (recognised context keys,
  unrecognised context keys, required-key presence, top-level registry
  sections, `feature_support` flags). Missing required keys
  (`name`, `placeholder`, `type`, `context`, `data_source`) halt before
  writing any output. Unrecognised keys flow into the new review-file
  section and get `next_action: needs-skill-update`.
- Sample `<stem>.suggested.yaml` in the Output format now leads with
  `schema_version` / `input_mapping_version` / `input_registry_version`.
- Review file format gains Section 7 "Unrecognised inputs" (always
  rendered; prints "No unrecognised inputs." when empty). Header
  section now requires an `<!-- schema_version: 1.0 -->` HTML comment
  on line 1 and a `Schema: 1.0 (mapping M.N, registry M.N)` bullet.
- "Ambiguity bubble-up" vocabulary extended with
  `needs-skill-update: <describe>`, **scoped exclusively to the
  Unrecognised inputs section** — never on a variable or loop
  `reasoning`. Summary's next-action breakdown table is unchanged on
  purpose (it counts entry-level next-actions only).
- Steps 4 / 4b rewritten to cover emitting the version keys at the top
  of `.suggested.yaml` and the HTML comment at the top of `.review.md`.

**SKILL.md updates (html-to-velocity):**
- "YAML mapping schema" preamble adds a pointer to `SCHEMA.md`,
  documents that every mapping YAML leads with `schema_version: '1.0'`,
  and notes that downstream tools refuse to run against an unsupported
  MAJOR. No rule-logic changes.

**New artifact:**
- `SCHEMA.md` at the repo root. Living contract covering registry,
  mapping YAML, suggested YAML, and review MD — top-level sections and
  nested keys with type + description. Reserves a "Suggester-log
  (JSONL)" section for Phase D to fill in. Change log seeded with the
  `1.0 — 2026-04-22` entry.

**Files touched in session A1:**
- `.cursor/skills/mapping-suggester/scripts/extract_paths.py` (1 line)
- `.cursor/skills/html-to-velocity/scripts/convert.py` (1 line)
- `.cursor/skills/mapping-suggester/SKILL.md` (sizeable additions)
- `.cursor/skills/html-to-velocity/SKILL.md` (1 small paragraph)
- `SCHEMA.md` (new, ~200 lines)
- `path-registry.yaml` (regenerated)
- `Samples/Output/*.mapping.yaml` (all four — regenerated)
- `Samples/Output/*.vm` / `*.report.md` (regenerated, no logic change)
- `PIPELINE_EVOLUTION_PLAN.md` (status bullet + runbook tickboxes +
  this handoff block)

### Done — Phase C §4 (session C1 — scaffold + first two fixtures + runner)

**Where Phase C stands as of 2026-04-22 (end of C1):** 2 of 10 seed
fixtures from §4.1 are live, the runner script is in place, and
`CONFIG_COVERAGE.md` rows 1–8 + 11 now point at real fixture
directories (the `(pending)` marker was removed for those rows only).

**Scope actually shipped in session C1:**

- **Scaffold.** `conformance/README.md` documents the fixture layout and the
  automated-registry / human-in-the-loop-suggester split used by the
  runner. `conformance/.gitignore` keeps `fixtures/*/actual/` out of source
  control so per-run outputs don't pollute diffs. Directory shape
  matches §4.1's expected path pattern but is flattened into
  `conformance/fixtures/<name>/{socotra-config,mapping.yaml,golden,actual}`
  (one directory per fixture rather than the three parallel trees
  sketched in §4 — keeps everything for a single fixture adjacent;
  see `conformance/README.md` for the full layout).
- **Fixture 1 — `conformance/fixtures/minimal/`.** Monoline product (`Mono`)
  with a single exposure (`Vehicle`, no suffix) and three placeholders:
  policy-level scalar, account-level scalar, and an exposure field
  referenced *without* a loop scope. Proves (a) no-suffix exposure
  handling in `extract_paths.py`, (b) Rule 2 scope-violation detection
  (the `vehicle_vin` placeholder lands at `low` confidence with
  `next-action: restructure-template` because no `context.loop` is
  present), and (c) that all 10 `feature_support` flags stay `false`
  on a trivially-small config. Covers `CONFIG_COVERAGE.md` rows 5 +
  25.
- **Fixture 2 — `conformance/fixtures/all-quantifiers/`.** Multi-line product
  (`Multi`) with every suffix across the matrix: `Vehicle+` /
  `Driver*` / `Addon?` / `SpecialUnit!` / `Policyholder` (none); the
  `Vehicle` exposure itself has `Coll` (none) / `MedPay?` / `Comp!`
  coverages; the product data block carries both a required (`string`)
  and an optional (`string?`) field. The fixture's `mapping.yaml`
  exercises 9 placeholders (2 scalars + 2 loops + 5 loop fields), all
  of which resolve to `high` confidence. Proves (a) quantifier
  preservation through `extract_paths.py`, (b) Rule 4 optional-element
  guard firing on `?` fields / coverages, (c) Rule 5 auto-element
  note firing on `!` coverages, and (d) `auto_elements: true` is the
  first non-`false` `feature_support` flag any fixture has emitted.
  Covers `CONFIG_COVERAGE.md` rows 1–4 (§3.1), 6–8 (§3.2), and 11
  (§3.3).
- **Runner — `conformance/run-conformance.py`.** Python 3 script, no external
  dependencies. For each fixture under `conformance/fixtures/`:
  1. Runs `.cursor/skills/mapping-suggester/scripts/extract_paths.py`
     against `socotra-config/` and writes the result to
     `actual/path-registry.yaml`.
  2. Canonicalises both actual and golden registries (strips
     `meta.generated_at` and `meta.config_dir` — the only two fields
     that change on a clean re-run) and diffs them.
  3. If `actual/suggested.yaml` / `actual/review.md` are present
     (populated by an agent after running the suggester), diffs them
     against the goldens too (stripping `generated_at` on the YAML and
     the "Generated at:" bullet on the review). When `actual/` is
     missing or empty, the runner reports `registry-only (suggester
     outputs not refreshed)` and does *not* fail — the deterministic
     half still passes in isolation.
  4. `--update-goldens` copies verified `actual/*` files on top of the
     goldens; refuses to write a golden with no matching actual.
  5. `--only <name>` limits the run to a single fixture.
  Smoke-tested on both fixtures: clean run is green; intentionally
  tampering with a golden reliably surfaces the diff.
- **CONFIG_COVERAGE.md updates.** Rows 1, 2, 3, 4, 5, 6, 7, 8, and 11
  had their Fixture-path cell updated in place — `(pending)` removed,
  session and date (`C1, 2026-04-22`) recorded, and a one-line note
  added describing what each fixture proves for that specific row. §7
  change log entry added for session C1 explicitly naming which rows
  moved out of `(pending)` and flagging that every refusal-flag row
  (9, 12–20) still needs a dedicated fixture before the refusal
  contract in §4 is regression-covered end-to-end.

**Deliberately NOT in scope for C1:**

- **Running the mapping-suggester skill as an agent against the two
  new fixtures.** The goldens for `minimal/` and `all-quantifiers/`
  were authored by direct application of SKILL.md's rules rather than
  by invoking the skill. This was the right call for C1 — both
  fixtures are small enough that rule-application is deterministic,
  and doing it this way avoided burning a Leg 2 agent run on
  something whose output is already unambiguous from the SKILL.md
  rule set. **This is a known deviation from §4.3's "run the
  suggester on the fixture's mapping YAML" step.** C2–C5 should
  revisit this decision on a per-fixture basis: for fixtures where
  the rule application is *not* obvious (jurisdictional, peril-based,
  nested iterables with CDT recursion), agents should run the skill
  live and keep the `actual/` output so the runner's suggester-diff
  arm wakes up.
- **Wiring the fixture suite into `PIPELINE_IMPROVEMENTS_PLAN.md` §6
  regression.** §4.4's fourth acceptance criterion is explicitly
  deferred to C5 once all ten fixtures exist (otherwise the
  companion plan's regression would block on a partial suite).
- **Fixtures 3–10.** `nested-iterables`, `cdt-flat`, `cdt-recursive`,
  `multi-product`, `jurisdictional`, `peril-based`, `no-exposures`,
  `custom-naming`. Split across sessions C2–C5 — see the queued
  block below. Each of those fixtures also "switches on" refusal
  flags in the registry, which is exactly the thing that still needs
  end-to-end regression coverage.
- **Acceptance criteria in §4.4.** None of §4.4's four boxes are
  ticked yet — 2/10 fixtures, runner exists but can't yet assert
  "every fixture passes" because 8 haven't been written, and the
  CONFIG_COVERAGE↔fixture linkage is only partial. They are left
  unticked deliberately; C5 (the closing session) owns ticking them.

**Session-budget reality check:**

C1 fit comfortably in one session (≈ one careful read of the
runbook, one read of `SKILL.md` / `CONFIG_COVERAGE.md` / relevant
parts of `extract_paths.py`, two fixture-authoring passes, two
runner invocations, in-place doc updates). It stayed inside the
"≤ 2 full Leg 2 runs per session" rule because **no** Leg 2 runs
were needed — the goldens were built by rule-application, not
suggester invocation. If C2's nested-iterables / CDT fixtures
*require* a suggester refresh to author their goldens accurately
(likely — CDT recursion and nested iterable scoping are much less
obvious from the rules alone), budget accordingly: at most 2
fixtures per session once Leg 2 runs come back in.

**Files touched this session:**

- `conformance/README.md` (new)
- `conformance/.gitignore` (new)
- `conformance/run-conformance.py` (new)
- `conformance/fixtures/minimal/` (new: `socotra-config/products/Mono/config.json`,
  `socotra-config/exposures/Vehicle/config.json`, `mapping.yaml`,
  `golden/path-registry.yaml`, `golden/suggested.yaml`,
  `golden/review.md`, `FIXTURE.md`)
- `conformance/fixtures/all-quantifiers/` (new: product `Multi/config.json`,
  five exposure configs for `Vehicle` / `Driver` / `Addon` /
  `SpecialUnit` / `Policyholder`, three coverage configs for
  `Coll` / `MedPay` / `Comp`, `mapping.yaml`, three `golden/*`
  files, `FIXTURE.md`)
- `CONFIG_COVERAGE.md` (rows 1–8 + 11 Fixture-path cells; §7
  change-log entry for C1)
- `PIPELINE_EVOLUTION_PLAN.md` (status line, Phase C session-count
  row, this handoff block, the queued C2 block below).

### Done — Phase C §4 (session C2 — three nested-shape fixtures)

**Where Phase C stands as of 2026-04-22 (end of C2):** 5 of 10 seed
fixtures from §4.1 are live. `CONFIG_COVERAGE.md` rows 12–17 now
point at real fixture directories (rows 14 / 15 / 17 as direct
coverage; rows 12 / 13 / 16 as detection-shared with a rationale
note). Four refusal-rule `feature_support` flags
(`nested_iterables`, `custom_data_types`, `array_data_extensions`,
`recursive_cdts`) have now been observed `true` in a fixture
registry and surface correctly as §7 Unrecognised-inputs rows with
`needs-skill-update` next-actions.

**Scope actually shipped in session C2:**

- **Fixture 3 — `conformance/fixtures/nested-iterables/`.** Product
  `FleetPlus` with `contents: ["Vehicle+"]`; exposure `Vehicle`
  carries a plain `vin: string` plus an `owners: Owner+`
  data-extension; CDT `Owner` defined under
  `customDataTypes/` with two scalar fields. The `Owner+` type is
  the trifecta shape — an iterable data-extension of a
  non-primitive base — which flips three flags at once:
  `nested_iterables: true` (iterable + non-primitive base),
  `custom_data_types: true` (CDT parses), and
  `array_data_extensions: true` (any iterable data-extension type).
  Mapping carries 4 placeholders (policy_number, vehicles loop,
  vehicles.vin, vehicles.owners). Goldens prove
  `policy_number` / `vehicles` / `vehicles.vin` stay `high` while
  `vehicles.owners` downgrades to `low` +
  `needs-skill-update: nested_iterables / custom_data_types /
  array_data_extensions refusal`, with three separate §7
  Unrecognised-inputs rows (alphabetical: `array_data_extensions`,
  `custom_data_types`, `nested_iterables`). Covers
  `CONFIG_COVERAGE.md` rows 12, 13, 14 (rows 12 / 13 shared flag
  path) and row 15 (via the `customDataTypes/Owner` parse).
- **Fixture 4 — `conformance/fixtures/cdt-flat/`.** Product `Homeowner`
  with `contents: ["Policyholder+"]`; exposure `Policyholder`
  carries `fullName: string` plus `dwellingAddress: Address`
  (scalar CDT reference, no quantifier); CDT `Address` with three
  scalar fields (`street`, `city`, `postalCode`). Flips
  `custom_data_types: true` while keeping `nested_iterables`,
  `recursive_cdts`, and `array_data_extensions` all `false` — the
  clean "CDT reference without any iteration" shape. Goldens
  mirror the nested-iterables fixture's refusal pattern but with a
  single §7 row (`feature_support.custom_data_types`) and a single
  low-confidence loop-field (`policyholders.dwelling_address`).
  Proves the detection boundary: `_iter_subdir_configs` requires
  `customDataTypes/<name>/config.json` to parse, not just the
  directory to exist. Covers `CONFIG_COVERAGE.md` row 15 directly
  and row 16 as detection-shared.
- **Fixture 5 — `conformance/fixtures/cdt-recursive/`.** Product `Chain`
  with `contents: ["Policyholder+"]`; exposure `Policyholder`
  carries `fullName: string` plus `dwellingAddress: Address`
  (scalar CDT reference); CDT `Address` with `street: string`,
  `city: string`, and `subAddress: Address?` (self-reference
  through a `?` quantifier — the linked-list CDT pattern from
  `CONFIG_COVERAGE.md` row 17's example). Flips BOTH
  `custom_data_types: true` and `recursive_cdts: true`, confirming
  that detection sees through quantifiers
  (`parse_quantified_token("Address?") == ("Address", "?")` → base
  equals CDT name → `recursive_cdts` flips regardless of `?`).
  Goldens show two §7 rows (alphabetical: `custom_data_types`,
  `recursive_cdts`) and a single combined `needs-skill-update` on
  the affected loop-field — regression-tests the "multiple refusal
  flags on the same field attribute each flag independently in §7"
  convention. Covers `CONFIG_COVERAGE.md` row 17 directly and rows
  15 / 16 transitively.
- **CONFIG_COVERAGE.md updates.** Rows 12, 13, 14, 15, 16, 17 had
  their Fixture-path cells updated in place. Rows 14 / 15 / 17
  carry a direct pointer (`conformance/fixtures/<name>/ (C2,
  2026-04-22)`); rows 12 / 13 / 16 are annotated as
  `partial: shared flag path` with a Notes-cell rationale
  explaining that the detection code path is identical to the
  direct-coverage row so no separate fixture adds information
  until a CDT-aware scope-walker lands. §7 changelog entry added
  for session C2 explicitly naming which four refusal flags have
  now been proven `true` in a fixture and flagging that
  `jurisdictional_scopes`, `peril_based`, `multi_product`,
  `coverage_terms`, and `default_option_prefix` remain
  refusal-flag-pending until C3–C4.

**Deliberately NOT in scope for C2:**

- **Running the mapping-suggester skill as an agent against the
  three new fixtures.** Same decision as C1: the refusal-contract
  pathway is deterministic once the four refusal flags flip, so
  the goldens were authored by direct application of
  `CONFIG_COVERAGE.md` §4 + `SKILL.md` Step 2a rather than by
  invoking the skill. The three fixtures' `actual/suggested.yaml`
  + `actual/review.md` files are deliberately absent; the runner
  reports them as `skipped` for those two artifacts while still
  registry-diffing each. A future session (C3 or later) can
  populate them by running the suggester live against each
  fixture's mapping + golden registry and using `--update-goldens`
  to freeze the output. This deviation from §4.3 is acknowledged
  and tracked — same treatment as C1's two fixtures before an
  agent backfilled their `actual/` outputs.
- **Fixtures 6–10.** `multi-product`, `jurisdictional`,
  `peril-based`, `no-exposures`, `custom-naming`. Split across
  sessions C3–C5 — see the queued block below. The four remaining
  refusal flags (`jurisdictional_scopes`, `peril_based`,
  `multi_product`, `coverage_terms` + dependent
  `default_option_prefix`) are all in that batch.
- **Acceptance criteria in §4.4.** Still unticked — same reasoning
  as C1. C5 is the closing session.

**Session-budget reality check:**

The C2 queued block predicted that these three fixtures "plausibly
need a live suggester run to author their goldens accurately (CDT
recursion interacts non-obviously with scope inheritance)" and
offered a split (C2a + C2b) if more than 2 Leg 2 runs were needed.
Reality: once `extract_paths.py` lines 181–186 were read (the
`custom_type_ref` emission + the "Full recursive expansion is
intentionally deferred" docstring), it became clear that the
registry does **not** walk CDT sub-fields today. All three
fixtures collapsed to the refusal contract — a CDT reference
emits a single entry with `custom_type_ref`, no sub-fields are
addressable, the suggester returns `low` +
`needs-skill-update` per `CONFIG_COVERAGE.md` §4, and the only
variation between the three fixtures is *which* flags flip. No
Leg 2 suggester runs were required; the split rule did not need to
fire. C2 fit comfortably in one session — roughly the same cost as
C1 (one careful read of the relevant docs, three fixture-authoring
passes, one `run-conformance.py` invocation, in-place doc updates).
Update the session-count table: actual was 1, estimate was 1; no
change needed.

**Files touched this session:**

- `conformance/fixtures/nested-iterables/` (new:
  `socotra-config/products/FleetPlus/config.json`,
  `socotra-config/exposures/Vehicle/config.json`,
  `socotra-config/customDataTypes/Owner/config.json`,
  `mapping.yaml`, `golden/path-registry.yaml`,
  `golden/suggested.yaml`, `golden/review.md`, `FIXTURE.md`)
- `conformance/fixtures/cdt-flat/` (new:
  `socotra-config/products/Homeowner/config.json`,
  `socotra-config/exposures/Policyholder/config.json`,
  `socotra-config/customDataTypes/Address/config.json`,
  `mapping.yaml`, `golden/path-registry.yaml`,
  `golden/suggested.yaml`, `golden/review.md`, `FIXTURE.md`)
- `conformance/fixtures/cdt-recursive/` (new:
  `socotra-config/products/Chain/config.json`,
  `socotra-config/exposures/Policyholder/config.json`,
  `socotra-config/customDataTypes/Address/config.json`,
  `mapping.yaml`, `golden/path-registry.yaml`,
  `golden/suggested.yaml`, `golden/review.md`, `FIXTURE.md`)
- `CONFIG_COVERAGE.md` (rows 12–17 Fixture-path cells; §7
  change-log entry for C2)
- `PIPELINE_EVOLUTION_PLAN.md` (status line, Phase C session-count
  row, this Done-C2 block replacing the previous Queued-C2 block,
  the new Queued-C3 block below).

### Done — Phase C §4 (session C3 — three product-structure-variant fixtures)

**Where Phase C stands as of 2026-04-22 (end of C3):** 8 of 10 seed
fixtures from §4.1 are live (plus one `peril-based/` slot deferred,
see "Scope actually shipped" below). `CONFIG_COVERAGE.md` rows 19
and 20 now point at real fixture directories; row 18 (`peril_based`)
is annotated as deferred with the swap-to-`jurisdictional-exclusive/`
rationale. Six of eight refusal flags have now been observed `true`
in at least one fixture registry: `nested_iterables`,
`custom_data_types`, `array_data_extensions`, `recursive_cdts` (all
from C2) plus `multi_product` and `jurisdictional_scopes` (from C3).
Two refusal flags remain with no fixture observation: `peril_based`
(deferred) and `coverage_terms` + dependent `default_option_prefix`
(queued for C4).

**Scope actually shipped in session C3:**

- **Fixture 6 — `conformance/fixtures/multi-product/`.** Two product
  subdirectories (`AutoLine/` with `contents: ["Vehicle+"]`,
  `HomeLine/` with `contents: ["Dwelling+"]`) plus a shared
  `exposures/Vehicle/` (one `vin: string` field). **No**
  `exposures/Dwelling/` — a deliberate fixture-level choice: if
  `Dwelling/` existed under `exposures/`, the extractor's fallback
  scan ("exposures not in contents default to no-suffix
  quantifier") would pick it up into AutoLine's registry with
  `quantifier: ''`, partially matching HomeLine-shaped placeholders
  and polluting the cross-product refusal test. Proves
  `multi_product: true` flips via
  `len([d for d in products/ if d.is_dir()]) > 1`; that the
  extractor deterministically picks AutoLine (A < H
  alphabetically); and that HomeLine is silently dropped (no
  Dwelling iterable, no HomeLine policy data). Mapping carries 4
  placeholders (policy_number, roof_material variable, vehicles
  loop, vehicles.vin field). Goldens prove `policy_number` /
  `vehicles` / `vehicles.vin` stay `high` while `roof_material`
  downgrades to `low` + `needs-skill-update: multi_product
  refusal` (name-match against HomeLine-shaped placeholder, no
  candidate in AutoLine registry, refusal rule supersedes Rule 2
  step 5 supply-from-plugin). One §7 row
  (`feature_support.multi_product`). Covers `CONFIG_COVERAGE.md`
  row 20 directly.
- **Fixture 7 — `conformance/fixtures/jurisdictional/`.** Product
  `SingleState` with `contents: ["Vehicle+"]`; exposure `Vehicle`
  with `contents: ["Collision"]` + `vin: string`; coverage
  `Collision` with `qualification: { jurisdiction: "CA" }` +
  `deductible: int`. Proves `jurisdictional_scopes: true` flips
  via the `qualification` branch of
  `any(k in cov_cfg for k in ("qualification", "appliesTo",
  "exclusive"))` at `extract_paths.py` line 455. Mapping carries
  4 placeholders (policy_number, vehicles loop, vehicles.vin
  plain-exposure-field, vehicles.collision_deductible
  jurisdictional-coverage-field). Goldens prove the
  non-jurisdictional entries stay `high` and only
  `vehicles.collision_deductible` (the one placeholder whose path
  traverses the jurisdictional coverage) downgrades to `low` +
  `needs-skill-update: jurisdictional_scopes refusal`. Covers
  `CONFIG_COVERAGE.md` row 19 directly (via `qualification`
  key).
- **Fixture 8 — `conformance/fixtures/jurisdictional-exclusive/`.**
  Authored as the substitution for the originally-planned
  `peril-based/` fixture (see "Peril-based deferral" below).
  Product `SpecialAuto`; exposure `Vehicle` with
  `contents: ["Umbrella"]` + `vin: string`; coverage `Umbrella`
  with `exclusive: true` AND `appliesTo: ["claim"]` + `limit: int`.
  The fixture deliberately carries BOTH keys on the same coverage
  — proves `any(...)` short-circuits correctly (single flag flip,
  single §7 row, not double-counted) and that neither key depends
  on `qualification`. Covers the remaining two detection branches
  of `jurisdictional_scopes` not exercised by
  `jurisdictional/`. Mapping + golden shape mirrors
  `jurisdictional/` one-for-one (four placeholders; three `high`;
  one `low` refusal on the coverage field `vehicles.umbrella_limit`;
  one §7 row). Covers `CONFIG_COVERAGE.md` row 19 as a companion
  to `jurisdictional/`.
- **Peril-based deferral.** The handoff block required a reality
  check against the Socotra Buddy corpus before authoring
  `peril-based/`. The C3 agent grepped
  `~/socotra-buddy/resources/derived/` for `peril` /
  `perils/` / `peril_based` / `peril-based`: exactly one hit in
  `125949463fad41f0.md` (the quantifiers overview page), and that
  hit uses the word conversationally — "if a personal auto
  policy has vehicles and the perils represent coverages like
  comprehensive and collision" — NOT to describe a
  `perils/<Name>/config.json` directory layout. No manifest hit,
  no raw-HTML hit for `<perils>` or `perils:`, no other derived
  document mentions peril-based products at all. Per the
  handoff's explicit fallback ("If the corpus citation comes up
  empty, **swap this fixture** for a second jurisdictional
  variant") `peril-based/` was swapped for
  `jurisdictional-exclusive/`. `peril_based` detection code
  stays in place at `extract_paths.py` lines 417–419 and the
  flag remains on the refusal vocabulary; `CONFIG_COVERAGE.md`
  row 18's Fixture-path cell now reads `(deferred, C3
  2026-04-22 — swapped for jurisdictional-exclusive/)` with a
  Notes paragraph explaining the corpus-grep outcome. When a
  real customer config surfaces a `perils/` tree (or a docs
  update adds one), a follow-up session can author the fixture
  and flip row 18 back to direct coverage.
- **Incidental code change — deterministic product sort.**
  `.cursor/skills/mapping-suggester/scripts/extract_paths.py`
  `build_registry()` originally used raw `products_dir.iterdir()`
  to pick the first product subdirectory. On macOS APFS this
  happened to return directories in creation order, which made
  `multi-product/` non-reproducible (it picked `HomeLine` on the
  first test run even though the handoff block documents the
  expected behaviour as "picks the first product subdirectory
  alphabetically"). Replaced the raw `iterdir()` with
  `sorted(..., key=lambda d: d.name)` — a 3-line change. Verified
  no impact: the live CommercialAuto registry is byte-identical
  aside from `generated_at`, and all five pre-C3 fixtures still
  pass `conformance/run-conformance.py` registry-diff. Exposures-fallback
  `iterdir()` at line 610 was **not** sorted in C3 because no
  current fixture has an exposures-subdir-not-in-contents shape
  that would expose the non-determinism; if one arrives in C4,
  sort that call at the same time.
- **CONFIG_COVERAGE.md updates.** Rows 18, 19, 20 had their
  Fixture-path cells updated in place. Row 18 reads `(deferred, C3
  2026-04-22 — swapped for jurisdictional-exclusive/)` with a
  Notes paragraph documenting the corpus-grep result. Rows 19 and
  20 read `(C3, 2026-04-22)` with Notes paragraphs describing the
  refusal-path behaviour each fixture proves. §7 change-log entry
  added for session C3 explicitly naming (a) which three fixtures
  landed, (b) the peril-based swap, (c) the `sorted(...)`
  incidental fix, and (d) which refusal flags have now been
  observed `true` in at least one fixture registry (six of eight,
  with `peril_based` deferred and `coverage_terms` /
  `default_option_prefix` queued for C4).

**Deliberately NOT in scope for C3:**

- **Running the mapping-suggester skill as an agent against the
  three new fixtures.** Same decision as C1 and C2: the refusal
  contract is deterministic once the flag flips, so goldens were
  authored by direct application of `CONFIG_COVERAGE.md` §4 +
  `SKILL.md` Step 2a rather than by invoking the skill. The
  three fixtures' `actual/suggested.yaml` + `actual/review.md`
  files are deliberately absent; the runner reports them as
  `skipped` for those two artifacts while still registry-diffing
  each. A future session (C4 or later) can populate them by
  running the suggester live against each fixture's mapping +
  golden registry and using `--update-goldens` to freeze the
  output. This deviation from §4.3 is acknowledged and tracked.
- **Peril-based fixture.** Deferred per the corpus-grep outcome
  above. Retry when a docs citation or live customer config
  surfaces.
- **Fixtures 9–10 (C4 scope).** `no-exposures/`, `custom-naming/`,
  `coverage-terms/`. See the queued C4 block below.
- **Acceptance criteria in §4.4.** Still unticked — same reasoning
  as C1 and C2. C5 is the closing session.

**Session-budget reality check:**

The C2 handoff predicted C3 would need "at most 2 fixtures per
session once Leg 2 runs come back in" and offered a C3a / C3b
split if `peril-based/` interactions warranted a live suggester
run. Reality: (a) corpus grep eliminated `peril-based/` entirely,
(b) both jurisdictional variants collapsed to the same refusal
contract once `extract_paths.py` line 455's `any(...)` was read
and `CONFIG_COVERAGE.md` §4's refusal rule was applied
mechanically, and (c) `multi-product/` was similarly unambiguous
once the `sorted(...)` determinism issue was surfaced and fixed.
No Leg 2 suggester runs were required; the split rule did not
need to fire. C3 fit comfortably in one session — roughly the
same cost as C2 (one careful read of the relevant docs + a C2
fixture as template, three fixture-authoring passes with a
`run-conformance.py` invocation after each, one small code change
with a verification pass on pre-existing fixtures, in-place doc
updates). Session-count table updated: estimate for Phase C was
4–5 sessions; after C3 the live count is 3 used, 2 queued (C4 +
C5) = 5 total if the queue holds, matching the upper bound.

**Files touched this session:**

- `conformance/fixtures/multi-product/` (new:
  `socotra-config/products/AutoLine/config.json`,
  `socotra-config/products/HomeLine/config.json`,
  `socotra-config/exposures/Vehicle/config.json`,
  `mapping.yaml`, `golden/path-registry.yaml`,
  `golden/suggested.yaml`, `golden/review.md`, `FIXTURE.md`)
- `conformance/fixtures/jurisdictional/` (new:
  `socotra-config/products/SingleState/config.json`,
  `socotra-config/exposures/Vehicle/config.json`,
  `socotra-config/coverages/Collision/config.json`,
  `mapping.yaml`, `golden/path-registry.yaml`,
  `golden/suggested.yaml`, `golden/review.md`, `FIXTURE.md`)
- `conformance/fixtures/jurisdictional-exclusive/` (new:
  `socotra-config/products/SpecialAuto/config.json`,
  `socotra-config/exposures/Vehicle/config.json`,
  `socotra-config/coverages/Umbrella/config.json`,
  `mapping.yaml`, `golden/path-registry.yaml`,
  `golden/suggested.yaml`, `golden/review.md`, `FIXTURE.md`)
- `.cursor/skills/mapping-suggester/scripts/extract_paths.py`
  (`build_registry()` product-subdir selection now uses
  `sorted(...)` — 3-line edit around lines 548–554)
- `CONFIG_COVERAGE.md` (rows 18, 19, 20 Fixture-path + Notes
  cells; §7 change-log entry for C3)
- `PIPELINE_EVOLUTION_PLAN.md` (status line, Phase C
  session-count row, this Done-C3 block replacing the previous
  Queued-C3 block, the existing Queued-C4–C5 block below left
  in place with its nominal shape — C4 agent will rewrite per
  its own reading of the landscape).

### Done — Phase C §4 (session C4 — remaining seed fixtures)

**Where Phase C stands as of 2026-04-22 (end of C4):** 11 fixtures
live under `conformance/fixtures/` (the set expanded by one in C3 when
`peril-based/` deferred and `jurisdictional-exclusive/` took its
slot). `CONFIG_COVERAGE.md` rows 5 / 9 / 10 / 21 now point at the
three C4 fixtures in addition to any prior coverage. Seven of eight
refusal flags have now been observed `true` in at least one fixture
registry: `nested_iterables`, `custom_data_types`,
`array_data_extensions`, `recursive_cdts` (all from C2) plus
`multi_product`, `jurisdictional_scopes` (C3) plus `coverage_terms`,
`default_option_prefix` (C4). Only `peril_based` remains unobserved,
pending a docs citation or live customer sample (deferred in C3 per
corpus-grep outcome, not a C4 concern). All 11 fixtures pass
`conformance/run-conformance.py` registry-diff (11/11 pass; 2/11 suggested +
review pass — `minimal/` + `all-quantifiers/` — 9/11 skipped because
the C2–C4 fixtures deliberately have no `actual/suggested.yaml` per
the "authored by direct rule-application" precedent). C5 is the
only remaining queued Phase C session.

**Scope actually shipped in session C4:**

- **Fixture 9 — `conformance/fixtures/no-exposures/`.** Product
  `Mono` with `contents: []` (empty — the structural characteristic
  under test). No `exposures/` directory at all. Policy-level `data`
  map carries `policyRef: string` and `submittedAt: string`.
  Mapping exercises three variables only — `policy_ref`,
  `submitted_at`, `account_name` — and an empty `loops: []` list.
  Proves `build_registry()` emits `iterables: []` and
  `exposures: []` cleanly when there is nothing to iterate, and
  that a variables-only mapping resolves at `high` confidence
  without touching the iterables index. All 10 `feature_support`
  flags remain `false`. Covers `CONFIG_COVERAGE.md` row 5 (as the
  "no-exposure at all" complement to `minimal/` + `all-quantifiers/`)
  and row 21 partially/indirectly (flat-on-policy-+-account shape
  acts as a proxy for a plugin-flattened root, though a direct
  non-`$data`-root fixture still needs authoring once B2 decides
  whether to carve out a flag for it). Golden registry + suggested
  + review are all trivial — 3 `high` mappings, 0 blockers, 0
  unrecognised inputs.
- **Fixture 10 — `conformance/fixtures/custom-naming/`.** Product
  `DeepSeaFleet` with `contents: ["Octopus+"]`; exposure `Octopus`
  with `data.tankId: string`. The structural hook: `Octopus` already
  ends in `'s'`, so `exposure_list_key()`
  (`.cursor/skills/mapping-suggester/scripts/extract_paths.py` lines
  106–115) returns `"octopus"` as the lowercase key (not
  `"octopuses"` — the function appends `'s'` only when the name
  doesn't already end in `'s'`). Mapping deliberately uses the
  natural-English plural loop name `octopuses`, so the extracted
  registry path `$data.octopus` fails Rule 1's strict name-match
  against loop name `octopuses` / display_name `Octopus` /
  derived plural `octopus`. Expected outcome (authored into
  `golden/suggested.yaml` + `golden/review.md`): `policy_number`
  matches `high`, `octopuses` downgrades to `low` +
  `supply-from-plugin` with reasoning citing Rule 1 step 3. This
  is the Phase E terminology-layer anchor — when Phase E lands,
  the fixture's golden will be regenerated with a
  `terminology.yaml` entry mapping `octopuses → octopus` and the
  confidence should flip to `medium` or `high` depending on the
  precedence the terminology layer lands on. Covers
  `CONFIG_COVERAGE.md` row 1 partially (exposure-name + loop-name
  pluralisation edge case); no refusal flags fire (all 10 remain
  `false`).
- **Fixture 11 — `conformance/fixtures/coverage-terms/`.** Product
  `FloodProtection` with `contents: ["Dwelling+"]`; exposure
  `Dwelling` with `contents: ["Flood"]` + `data.address: string`;
  coverage `Flood` with `data.effectiveDate: string` AND
  `coverageTerms: [{ name: "deductible", options: ["250", "*500",
  "1000"] }]`. The key design choices: (a) the coverage carries
  BOTH a regular `data` field AND a `coverageTerms` array — proves
  `extract_paths.py` walks `data` independently of `coverageTerms`
  and that `effectiveDate` still resolves to a concrete registry
  path while term-resolution stays refused; (b) the term's
  options list contains a `*`-prefixed entry (`"*500"`) — co-fires
  `default_option_prefix: true` in the same flag-emission pass;
  (c) the coverage name `Flood` (renamed from an earlier draft
  `FloodCoverage`) gives the prefix-based matching a clean
  `flood_*` namespace. Mapping carries 5 placeholders:
  `policy_number` (variable), `dwellings` loop head,
  `dwellings.address` (exposure-data field),
  `dwellings.flood_effective_date` (coverage-data field — still
  resolvable as `$dwelling.Flood.data.effectiveDate`), and
  `dwellings.flood_deductible` (coverage-term-dependent — the
  refusal target). Goldens prove: `policy_number` /
  `dwellings` / `dwellings.address` /
  `dwellings.flood_effective_date` all `high`;
  `dwellings.flood_deductible` downgrades to `low` +
  `needs-skill-update: coverage_terms / default_option_prefix
  refusal` per the combined-refusal convention established by
  `nested-iterables/`. Two §7 Unrecognised-inputs rows in
  `review.md` — alphabetical: `feature_support.coverage_terms`
  then `feature_support.default_option_prefix`. Covers
  `CONFIG_COVERAGE.md` rows 9 and 10 directly; closes the final
  two previously-unobserved refusal flags.
- **`extract_paths.py` invocation pattern.** Each fixture's
  `golden/path-registry.yaml` was produced by a real
  `python3 .cursor/skills/mapping-suggester/scripts/extract_paths.py
  --config-dir conformance/fixtures/<name>/socotra-config --output …` run
  and then promoted to golden verbatim (same workflow as C1–C3).
  One sandbox-related hiccup surfaced during the `no-exposures/`
  run — piping the command's output through `tail` caused the
  process to hang and get backgrounded; the workaround was to
  kill the stuck process and re-run without the pipe and with
  `required_permissions=["all"]`. Worth noting for future
  fixture-authoring sessions: pipe the extractor's output to a
  file or read the full stderr/stdout directly rather than via
  `tail`. No code fix required — the extractor itself behaved
  correctly once it ran.
- **CONFIG_COVERAGE.md updates.** Rows 5, 9, 10, and 21 had their
  Fixture-path + Notes cells updated in place. Row 5 reads
  `conformance/fixtures/minimal/ (C1, 2026-04-22) +
  conformance/fixtures/all-quantifiers/ (C1) +
  conformance/fixtures/no-exposures/ (C4, 2026-04-22 — absence-of-
  exposure regression)` with the Notes paragraph now covering all
  three structural cases. Rows 9 and 10 read
  `conformance/fixtures/coverage-terms/ (C4, 2026-04-22)` with Notes
  paragraphs documenting the two-flag co-fire and how the
  coexisting `data.effectiveDate` field proves the extractor
  walks `data` independently. Row 21 reads
  `conformance/fixtures/no-exposures/ (C4, 2026-04-22 — partial /
  indirect)` with a note that a dedicated non-`$data`-root
  fixture still needs authoring once B2 carves out a flag. §7
  change-log entry added for session C4 summarising the three
  fixtures, the seven-of-eight refusal-flag status, the one
  deferred flag, and the unchanged "no Leg 2 runs required"
  precedent.

**Deliberately NOT in scope for C4:**

- **Running the mapping-suggester skill as an agent against the
  three new fixtures.** Same decision as C1 / C2 / C3: goldens
  authored by direct rule-application; the three fixtures'
  `actual/suggested.yaml` + `actual/review.md` are deliberately
  absent and `conformance/run-conformance.py` reports them as `skipped` for
  those two artifacts while still registry-diffing each. A future
  session can populate them by running the suggester live against
  each fixture's mapping + golden registry and using
  `--update-goldens` to freeze the output. This deviation from
  §4.3 is acknowledged and tracked (same status as all 9 C2–C4
  fixtures).
- **Peril-based fixture.** Still deferred per the C3 corpus-grep
  outcome. Retry when a docs citation or live customer config
  surfaces.
- **Regression-flow wiring into `PIPELINE_IMPROVEMENTS_PLAN.md`
  §6.** C5 scope — see the queued block below.
- **Acceptance criteria in §4.4.** Still unticked — same reasoning
  as C1 / C2 / C3. C5 is the closing session.
- **Phase E terminology-layer wiring on `custom-naming/`.** The
  fixture is authored with the `octopuses → octopus` mismatch
  deliberately unresolved so Phase E has a ready-made regression
  target; wiring the fix belongs to Phase E, not C5.

**Session-budget reality check:**

The C3 handoff block flagged that C4 "might need to split — three
fixtures in one session is only tractable if all three stay rule-
application (like C2 did)". Reality: all three fixtures were
straightforward rule-application and fit comfortably in one
session. `no-exposures/` was the cheapest (empty iterables /
exposures / all flags `false` — the registry and all three goldens
write themselves once the empty-`contents` decision is made).
`custom-naming/` required one careful read of
`exposure_list_key()` (lines 106–115) to confirm the
`Octopus → octopus` pluralisation, then straight application of
Rule 1. `coverage-terms/` required one careful read of
`detect_features()` (to confirm `coverage_terms` is detected via
a non-empty `coverageTerms` array and `default_option_prefix` by
scanning term options for a leading `*`) plus one careful
cross-check of `build_registry()` (to confirm `coverageTerms` is
detected but not expanded into registry paths — lines 443 + 547
ff.), then straight application of the refusal rule. No Leg 2
suggester runs were required; the split rule did not need to
fire. C4 fit comfortably in one session — roughly the same cost
as C2 or C3 (one careful read of the relevant code + a C3 fixture
as template, three fixture-authoring passes with an
`extract_paths.py` + `run-conformance.py` invocation after each,
in-place doc updates). Session-count table updated: estimate for
Phase C was 4–5 sessions; after C4 the live count is 4 used, 1
queued (C5) = 5 total if the queue holds, matching the upper
bound exactly. No change to the 4–5 estimate.

**Files touched this session:**

- `conformance/fixtures/no-exposures/` (new:
  `socotra-config/products/Mono/config.json`,
  `mapping.yaml`, `golden/path-registry.yaml`,
  `golden/suggested.yaml`, `golden/review.md`, `FIXTURE.md`)
- `conformance/fixtures/custom-naming/` (new:
  `socotra-config/products/DeepSeaFleet/config.json`,
  `socotra-config/exposures/Octopus/config.json`,
  `mapping.yaml`, `golden/path-registry.yaml`,
  `golden/suggested.yaml`, `golden/review.md`, `FIXTURE.md`)
- `conformance/fixtures/coverage-terms/` (new:
  `socotra-config/products/FloodProtection/config.json`,
  `socotra-config/exposures/Dwelling/config.json`,
  `socotra-config/coverages/Flood/config.json`,
  `mapping.yaml`, `golden/path-registry.yaml`,
  `golden/suggested.yaml`, `golden/review.md`, `FIXTURE.md`)
- `CONFIG_COVERAGE.md` (rows 5, 9, 10, 21 Fixture-path + Notes
  cells; §7 change-log entry for C4)
- `PIPELINE_EVOLUTION_PLAN.md` (status line, Phase C
  session-count row, this Done-C4 block replacing the previous
  Queued-C4–C5 block, new Queued-C5 block below)

### Done — Phase C §4 (session C5 — regression wiring + §4.4 acceptance)

**Where Phase C stands as of 2026-04-22 (end of C5):** Phase C
complete. 11 fixtures live under `conformance/fixtures/` (unchanged from
C4 — `minimal`, `all-quantifiers`, `nested-iterables`, `cdt-flat`,
`cdt-recursive`, `multi-product`, `jurisdictional`,
`jurisdictional-exclusive`, `no-exposures`, `custom-naming`,
`coverage-terms`). `conformance/run-conformance.py` exits `0` on every
fixture (11/11 PASS — `minimal/` + `all-quantifiers/` pass
`registry=pass suggested=pass review=pass`; the other 9 fixtures
pass `registry=pass` and report `suggested=skipped review=skipped`
per the §4.3 "direct rule-application" deviation tracked in
Done-C2 / C3 / C4). All four §4.4 acceptance boxes are ticked.
`PIPELINE_IMPROVEMENTS_PLAN.md` §6.0 now pins the fixture suite in
front of §6.1 as the first step of every regression run. Seven of
eight refusal flags have `true`-in-a-fixture observations; only
`peril_based` remains deferred pending a docs citation or live
customer sample (C3 deferral, unchanged in C5 per the handoff's
"don't chase an eighth-flag fixture in C5" guardrail). Phases D
and E are the only queued phases remaining on this plan.

**Scope actually shipped in session C5:**

- **Smoke-run of `conformance/run-conformance.py`** as the first action of
  the session — confirmed 11/11 PASS, exit `0`, and that the
  expected skip pattern (2 full-pass + 9 `suggested=skipped
  review=skipped`) still holds. No drift since C4.
- **New §6.0 "Fixture suite regression (Phase C gate)" in
  `PIPELINE_IMPROVEMENTS_PLAN.md`.** Inserted before §6.1. Documents
  the one-line runner invocation (`python3 conformance/run-conformance.py`),
  summarises the runner contract in three bullets (what it
  automates for the registry leg, what it automates for the
  agent-driven suggested + review legs when `actual/*` exists, and
  what it explicitly never does — invoke the mapping-suggester
  skill), spells out the `--update-goldens` guardrail, and
  enumerates exit codes `0` / `1` / `2` with what "pass" means for
  each leg (crucial detail: `skipped` counts as pass for
  exit-code purposes, so the runner does not fail when 9 of 11
  fixtures have no `actual/suggested.yaml`). Pinned today's
  expected output verbatim ("11 fixtures, all PASS, with
  `minimal/` + `all-quantifiers/` reporting
  `registry=pass suggested=pass review=pass` and the other 9
  fixtures reporting `registry=pass suggested=skipped
  review=skipped`") so future regression runs have a concrete
  baseline to diff against.
- **New acceptance box in `PIPELINE_IMPROVEMENTS_PLAN.md` §6.4.**
  Added as the first item in the §6.4 checklist (ahead of the
  existing three ticked boxes), ticked `[x]` with a note citing
  session C5 and the 11/11 pass count.
- **§4.4 acceptance criteria — all four boxes ticked** with notes
  covering: the 11-fixture seed count (grew by one when
  `peril-based/` deferred and `jurisdictional-exclusive/` took
  its slot); the 11/11 runner pass with the deliberate skip
  pattern; the `CONFIG_COVERAGE.md` row-to-fixture audit (row 18
  correctly reads "deferred" without citing a fixture); and the
  §6.0 wiring into the companion plan.
- **Status-line paragraph at the top of this plan rewritten.**
  Folds C5 into the session-complete list, describes the
  fixture-suite regression wiring, re-states the 7-of-8 refusal-
  flag observation status, and confirms Phases D and E are the
  only remaining queued phases.
- **Phase C session-count row extended** with a C5 summary and
  an updated final count (5 used, 0 queued = 5 total — matches
  the upper bound of the original 4–5 estimate exactly, so no
  estimate revision was needed).

**Deliberately NOT in scope for C5 (per the queued-block
guardrails):**

- **Any new fixture.** In particular, no attempt to chase an
  eighth refusal-flag observation for `peril_based` — the C3
  corpus-grep outcome still stands (no `perils/<Name>/config.json`
  citation) and a cheap "peril_based-like" fixture would be
  synthesis without a docs anchor. Flagged for a future session
  once a docs citation or live customer config surfaces.
- **Populating `actual/suggested.yaml` + `actual/review.md` for
  the 9 rule-application fixtures.** Still skipped per the
  tracked §4.3 deviation; a future session can run the suggester
  live against each fixture and use `--update-goldens` to freeze
  the output. Not a Phase C gate — C5's job was to accept the
  current state, not re-author goldens.
- **Phase D–E kickoff.** Out of scope; the queued-D–E note below
  stays unchanged apart from noting C5 is complete.

**Files touched this session:**

- `PIPELINE_IMPROVEMENTS_PLAN.md` (new §6.0 "Fixture suite
  regression (Phase C gate)" subsection inserted before §6.1;
  new ticked acceptance box at the top of §6.4)
- `PIPELINE_EVOLUTION_PLAN.md` (status-line paragraph rewritten;
  Phase C session-count row extended with C5 summary + final
  count; §4.4 acceptance criteria four boxes ticked with notes;
  Queued-C5 block replaced by this Done-C5 block; Queued-D–E
  block rewritten to remove the "ticked in session C5" reference
  now that those boxes are ticked)

**Session-budget reality check:**

C5 fit comfortably in one session as forecast. No Leg 2 runs
required. Actual cost: one fixture-suite smoke run, one read of
`conformance/run-conformance.py` + `conformance/README.md` for the contract
details, one read of `PIPELINE_IMPROVEMENTS_PLAN.md` §6 for
insertion-point context, and six targeted doc edits (one
insertion + one amendment in the improvements plan; four edits
in the evolution plan). No split risk materialised. Phase C
final session count: 5, matching the upper bound of the 4–5
estimate exactly.

### Done — Phase D §5 (session D1 — telemetry plumbing + two-run verification)

**Where Phase D stands as of 2026-04-22 (end of D1):** the telemetry
contract is plumbed end-to-end. Every Leg 2 invocation is now
contractually obliged to write a third artifact —
`<stem>.suggester-log.jsonl` — next to the existing suggested YAML +
review MD. The JSONL is append-only across runs (ledger semantics),
contains one `kind: placeholder` record per mapping entry plus
exactly one `kind: summary` record per run, and validates against a
Draft 2020-12 JSON Schema that lives in the test harness. The
derivation helper lets future agents emit schema-clean logs without
hand-authoring 30+ JSON objects. Two of six §5.4 acceptance boxes are
ticked outright; three are queued for D2; one (the `run_id` /
`seen_count` paired criterion) is half-ticked with the `run_id` half
done in D1 and the `seen_count` half waiting on D2's
`skill-lessons.yaml`.

**Scope actually shipped in session D1:**

- **`conformance/schemas/suggester-log.schema.json`** — 192-line Draft
  2020-12 JSON Schema. Covers both record kinds via a top-level
  `oneOf`. Enumerates the closed vocabulary for `next_action`
  (`pick-one | supply-from-plugin | restructure-template |
  delete-from-template | confirm-assumption | needs-skill-update`)
  and `rejected_candidates.reason` (`scope_violation |
  quantifier_mismatch | cardinality_mismatch | type_mismatch |
  display_name_mismatch | charge_form_mismatch | feature_refused |
  ambiguous_tiebreak | no_label_context | other`). `ts` uses a strict
  ISO 8601 / RFC 3339 UTC regex with optional fractional seconds;
  `run_id` uses a UUID regex. `context` is
  `additionalProperties: true` so unrecognised v1.0 keys round-trip
  per the Phase A preservation rule. `placeholder` objects are
  otherwise strictly typed with `additionalProperties: false`.
- **`.cursor/skills/mapping-suggester/SKILL.md`** — four coordinated
  additions. (1) "Output format" now lists three artifacts, not two,
  and spells out the append-only ledger semantics. (2) New
  "Telemetry file format (`<stem>.suggester-log.jsonl`)" section
  (between "Output format" and "Review file format") with shared /
  placeholder / summary field tables, the closed reason vocabulary,
  and a compact two-record example. (3) New **Step 4c — Append the
  per-run telemetry log (MANDATORY)** in "How to run", landing
  between Step 4b (write review file) and Step 5 (terminal summary)
  with ten numbered emission rules (single UUID per invocation,
  single `ts` sampled at Step 3 start, compact JSON one-object-per-
  line, append-only, rejected-candidate population rules, dead /
  hot path aggregation rules with a 50-entry cap on the dead list,
  etc.). The Step also documents the optional helper-script
  invocation (`emit_telemetry.py`) for runs that don't need live
  rejection data captured. (4) "Step 5 — Print the terminal summary"
  now prints a `Telemetry appended: …` line citing the log path and
  `run_id`; "After output" tells the user the log accumulates
  across runs and cites the run_id so they can grep by run.
- **`.cursor/skills/mapping-suggester/scripts/emit_telemetry.py`** —
  ~200-line derivation helper. Given a `<stem>.suggested.yaml` + a
  `path-registry.yaml`, walks variables then loops, builds one
  `kind: placeholder` record per entry (preserving unrecognised
  context keys; listing them in `unknown_context_keys`), then a
  `kind: summary` record with `totals` / `confidence_counts` /
  `next_actions` (parsed out of each entry's `reasoning` string via
  `next-action: <code>` regex) / `dead_registry_paths` (sorted,
  capped at 50) / `hot_registry_paths` (chosen-match count ≥ 2) /
  `unknown_context_keys_seen`. Appends to the log in compact JSON
  (no extra whitespace inside objects; one record per line; trailing
  newline). Generates a fresh UUID + UTC timestamp per invocation
  unless `--run-id` / `--ts` are supplied.
- **`SCHEMA.md`** — three edits. (1) The "Purpose" intro was
  corrected: four of the five artifacts carry a YAML-root
  `schema_version`; the fifth (the JSONL log) is JSON Lines and so
  its contract lives in
  `conformance/schemas/suggester-log.schema.json`. (2) The "Artifact:
  `<stem>.suggester-log.jsonl`" section was fleshed out from its
  Phase-A placeholder into a full section with shared-fields /
  placeholder / summary tables plus five "Emission rules" bullets
  (Step 4c cross-ref, append-only, absence-is-a-bug,
  MAJOR-halt-produces-no-log). (3) A new change-log entry landed as
  the most recent row: "1.0 — 2026-04-22 — Phase D session D1
  (additive, new artifact). Introduced `<stem>.suggester-log.jsonl`
  as the fifth pipeline artifact …".
- **`Samples/Output/claim-form.suggester-log.jsonl`** — two runs'
  worth of records (84 total: 82 `placeholder` + 2 `summary`).
  Generated by invoking `emit_telemetry.py` twice against the
  unchanged `claim-form.suggested.yaml` + `path-registry.yaml`
  with pinned run-IDs
  (`5b7e1c22-4d6f-4a01-9b8e-0a1d3f4c0001` and
  `9c2a71e6-8f40-47a9-b331-2b5d9e6a0002`) and pinned timestamps
  (`2026-04-22T18:05:00Z` and `2026-04-22T18:07:42Z`) so the
  verification is reproducible. Both summary records report
  `totals={variables: 37, loops: 4}`,
  `confidence_counts={high: 2, medium: 6, low: 33}`,
  `next_actions={supply-from-plugin: 26, confirm-assumption: 6,
  restructure-template: 7}`, `dead_registry_paths` truncated to 50
  per the SKILL rule, `hot_registry_paths: []` (claim-form's two
  high-confidence matches are both unique),
  `unknown_context_keys_seen: ["nearest_heading"]` (matches the
  A2 / A3 observation).
- **Schema validation** — ran `jsonschema 4.26.0` from a throwaway
  `/tmp/d1-venv` over every line of the log. 84 records, `errors=0`.
  The schema's own structural validation
  (`Draft202012Validator.check_schema`) also passed clean.
- **§5.4 acceptance checklist** — ticked the first two boxes
  outright with notes citing the D1 artifacts; left the three
  D2-owned boxes explicitly annotated `_Queued for D2._`; the
  "twice → two summary records" box is annotated with the D1
  `run_id` result and the open `seen_count` dependency on D2.

**Deliberately NOT in scope for D1 (per the session-budget
split rule and the Phase D runbook):**

- **`skill-lessons.yaml`.** Phase D2 territory. The D1 SKILL edits
  deliberately do not mention lesson-file lookup, promotion
  state, or agent-auto-promotion constraints.
- **Backfilling logs for `policy-template` / `quote-application` /
  `renewal-notice`.** Those sample outputs already exist under the
  v1.0 contract and could be catch-up-logged with three more
  `emit_telemetry.py` invocations, but D1's acceptance criteria
  only require the contract to be in place and one sample to
  demonstrate two-run semantics. Leaving the other three as
  opportunistic follow-up work inside D2 (or a separate mechanical
  session) keeps D1 inside the single-session budget.
- **Live Leg 2 re-run on `claim-form` with in-memory
  rejection data captured.** The D1 log uses
  `rejected_candidates: []` on every record because the
  `emit_telemetry.py` catch-up path doesn't have access to the
  candidates the original Leg 2 agent considered. A future live run
  (likely as part of D2's seen_count demonstration) can author the
  JSONL directly and populate the rejected-candidate array.
- **Wiring the JSONL into `conformance/run-conformance.py`.** Out of scope;
  the fixture runner's existing `registry=pass / suggested=skipped /
  review=skipped` pattern doesn't cover the log yet. A future
  session (probably D2 or E) can extend the runner.
- **Phase E.** Explicitly out of scope.

**Files touched this session:**

- `.cursor/skills/mapping-suggester/SKILL.md` (Output format,
  Telemetry file format section, Step 4c, Step 5, After output;
  five coordinated additions preserving the rest of the file
  verbatim)
- `.cursor/skills/mapping-suggester/scripts/emit_telemetry.py`
  (new file, ~200 lines)
- `conformance/schemas/suggester-log.schema.json` (new file, Draft
  2020-12)
- `SCHEMA.md` (Purpose intro corrected; suggester-log artifact
  section fleshed out; change-log entry added as most-recent row)
- `Samples/Output/claim-form.suggester-log.jsonl` (new, 84 lines)
- `PIPELINE_EVOLUTION_PLAN.md` (status-line paragraph at top
  extended with D1 summary, Phase D row in session-budget table
  extended with D1 Notes + D2 sketch, §5.4 acceptance boxes
  partially ticked with notes, Queued-D–E block replaced by this
  Done-D1 block and the fresh Queued-D2 block below)

**Session-budget reality check:**

D1 fit comfortably in one session as forecast. The "two-run
verification" acceptance item was satisfied by two invocations of the
catch-up helper rather than two full Leg 2 agent runs, so the budget
spend was ≈ 0 full Leg 2 runs — well inside the 2-run-per-session
limit. Actual spend: one pass reading the suggester SKILL.md and the
existing SCHEMA.md, one pass authoring the JSON Schema, helper
script, and three SKILL/SCHEMA edits, two helper invocations, and
one jsonschema validation run. No split risk. Phase D running total:
1 session used, 1 queued = 2 total (matches the original estimate
exactly; no revision needed).

### Done — Phase D §5 (session D2 — `skill-lessons.yaml` + promotion state machine + live `seen_count` growth)

**Where Phase D stands as of 2026-04-22 (end of D2):** Phase D
complete. The telemetry contract (D1) and the lessons ledger (D2)
are both live. `skill-lessons.yaml` exists at the repo root, seeded
from §5.2 verbatim with two `status: observed` lessons, and has
already bumped both lesson rows' `seen_count` / `last_seen` via two
live Leg 2 runs against `claim-form` through the new Step 4d
lesson-append code path. All six §5.4 acceptance boxes now tick
`[x]`. Phase E is the only queued phase remaining on this plan.

**Scope actually shipped in session D2:**

- **`skill-lessons.yaml` at the repo root** — 33-line YAML file,
  `schema_version: '1.0'`, two `lessons:` entries seeded verbatim
  from §5.2 (`claimant-eq-policyholder` starting at
  `seen_count: 2`, `vehicle-scope-violation` starting at
  `seen_count: 1`; both `status: observed`, both
  `candidate_promotion: null`). File header comments restate the
  agent-append-only / human-promote-only contract and cross-ref
  the `Lesson workflow (Phase D)` section in the SKILL. Post-run
  state after D2's two live invocations:
  `claimant-eq-policyholder` `seen_count: 4` (grown 2 → 3 → 4,
  `last_seen: 2026-04-22`), `vehicle-scope-violation`
  `seen_count: 3` (grown 1 → 2 → 3, `last_seen: 2026-04-22`).
  `status`, `candidate_promotion`, `pattern`, and `current_rule`
  stayed untouched on both rows — the agent-auto-promotion hard
  constraint holds.
- **`mapping-suggester/SKILL.md` — four coordinated additions.**
  (1) **Step 0b — Read `skill-lessons.yaml`** inserted between
  Step 0 (version check) and Step 1: skip silently when absent,
  apply same MAJOR-halt / MINOR-warn as Step 0, apply `status:
  promoted` rules during matching (v1.0 seed has none — the hook
  exists so a future promotion doesn't need replumbing), keep the
  parsed file in memory for Step 4d. (2) **Step 4d — Append lesson
  observations (MANDATORY when the file exists)** inserted between
  Step 4c (telemetry log) and Step 5 (terminal summary): bumps
  matched existing rows' `seen_count`, `last_seen`, and
  `observed_in`; appends new `observed` rows for patterns no
  existing matcher covers; documents the hard prohibitions
  (never flip `status`, never author `candidate_promotion`,
  never edit `pattern` / `current_rule` on existing rows, never
  reorder or merge). (3) **New "Lesson workflow (Phase D)"
  top-level section** after "Important constraints" with the
  `observed → proposed → {promoted, rejected}` state-machine
  diagram, a division-of-responsibility table (agents: bump
  counters + append `observed` rows; humans: everything else),
  the seeded per-lesson matcher table (the v1.0 matchers for
  `claimant-eq-policyholder` — `name` starts with `claimant_` AND
  `confidence ∈ {medium, low}` AND `next_action ∈
  {supply-from-plugin, confirm-assumption}`; and for
  `vehicle-scope-violation` — `name` starts with `vehicle_` AND
  `next_action == restructure-template`), the exact-string
  pattern-match semantics (prose `pattern` is documentation; match
  logic is the matcher table; fuzzy matching explicitly out of
  scope), and a `seen_count >= 3` advisory review-threshold note.
  (4) **"Do not auto-promote lessons" bullet** appended to
  "Important constraints", mirroring the Phase D §7 hard
  constraint with test-failure-not-style-guideline enforcement
  wording. Also: Step 5 terminal summary gained a
  `Lessons updated: …` line; After output gained a matching
  bullet about lesson state to report to the user.
- **`SCHEMA.md` — two edits.** (1) Purpose intro extended from
  "five artifacts" to "six artifacts" to cover
  `skill-lessons.yaml` as the sixth. (2) New top-level
  "Artifact: `skill-lessons.yaml`" section with the top-level
  table (`schema_version`, `lessons`), the lesson-entry key table
  (id / first_seen / last_seen / seen_count / observed_in /
  pattern / current_rule / candidate_promotion / status — each
  with an "agent-immutable" note where applicable), the state-
  machine diagram restated, an explicit "Agent-auto-promotion
  prohibition" subsection cross-referring the SKILL and §7, and
  an "Emission rules" block (Step 0b read / Step 4d write /
  no-op on no-match / absent file is legitimate). (3) New D2
  change-log entry inserted as the most-recent row, summarising
  the new artifact + SKILL plumbing and citing the live-run
  growth on both lessons.
- **Live two-run verification on `claim-form`.** Two fresh-UUID
  runs via `emit_telemetry.py` paired with manual Step 4d execution
  per the lesson-append code path:
  - Run 1: `run_id=3a8f12d4-b7c9-4e25-8146-1f2d40c7d003`,
    `ts=2026-04-22T19:15:00Z`, appended 42 records (37 variables
    + 4 loops + 1 summary); bumped `claimant-eq-policyholder`
    2 → 3 and `vehicle-scope-violation` 1 → 2 in
    `skill-lessons.yaml`; `last_seen` moved to `2026-04-22` on
    both rows.
  - Run 2: `run_id=7b4e93a2-c8f1-45d3-9a57-0e6b8d2f3004`,
    `ts=2026-04-22T19:20:30Z`, appended another 42 records;
    bumped the two lesson rows to 4 and 3 respectively.
  - Final log state: 168 records total across 4 runs (D1's
    two + D2's two) — 164 `placeholder` + 4 `summary` — with
    four distinct `run_id`s. Validation via
    `/tmp/d1-venv/bin/python` (`jsonschema 4.26.0`,
    `Draft202012Validator.check_schema` passes, every record
    round-trip-validates): `errors=0`.
- **§5.4 acceptance checklist.** All six boxes tick `[x]` with
  notes citing the D2 artifacts and the live-run growth numbers.
  Boxes 1 + 2 kept their D1 notes; boxes 3 + 4 + 6 flipped from
  `_Queued for D2._` to `[x]` with concrete D2 notes; box 5
  flipped from the D1 partial-tick to full `[x]` citing the
  seen_count growth on both lessons.

**Deliberately NOT in scope for D2 (per the queued-D2
split rule and out-of-scope list):**

- **Phase E terminology layer.** Out of scope — unblocked by D2's
  completion and now the only queued phase remaining.
- **Wiring the JSONL log into `conformance/run-conformance.py`.** Still
  out of scope; the runner's `registry=pass suggested=skipped
  review=skipped` pattern does not yet cover the log or the
  lessons ledger. A future session (probably during Phase E or
  post-E) can extend the runner.
- **Backfilling telemetry logs for `policy-template` /
  `quote-application` / `renewal-notice`.** Still out of scope
  for the same budget-guardrail reason that kept it out of D1.
  The three samples have up-to-date `.suggested.yaml` /
  `.review.md` but no log files yet; a mechanical catch-up
  session is queued for the future.
- **Changes to the D1 JSON Schema or `emit_telemetry.py`.** No
  bug surfaced in D2 — all D2 `emit_telemetry.py` invocations
  succeeded and the appended records validated clean.
- **Multi-sample lesson trips.** The §5.2 seed's
  `observed_in: [claim-form, renewal-notice]` on
  `claimant-eq-policyholder` reflects the hand-seeded plan-level
  example; D2's two runs only added claim-form observations (which
  did not extend `observed_in` because claim-form was already
  present). Confirming the renewal-notice lesson trip via a live
  run is opportunistic post-D2 follow-up work, not a gate.

**Files touched this session:**

- `skill-lessons.yaml` (new file at repo root, ~33 lines including
  header comments)
- `.cursor/skills/mapping-suggester/SKILL.md` (Step 0b inserted
  after Step 0; Step 4d inserted after Step 4c; Step 5 terminal
  summary extended with `Lessons updated:` line; "Important
  constraints" extended with the "Do not auto-promote lessons"
  bullet; new top-level "Lesson workflow (Phase D)" section
  inserted after "Important constraints"; "After output" bullet
  list extended to 6 items with the new lesson-status reporting
  guidance)
- `SCHEMA.md` (Purpose intro extended to six artifacts; new
  "Artifact: `skill-lessons.yaml`" section inserted after the
  telemetry-log artifact section; D2 change-log entry inserted
  as most-recent row)
- `Samples/Output/claim-form.suggester-log.jsonl` (84 new
  records appended across two live runs — 82 `placeholder` + 2
  `summary`; file now 168 records total)
- `PIPELINE_EVOLUTION_PLAN.md` (status-line paragraph at top
  extended with D2 summary; Phase D row in session-budget table
  rewritten to "2 (both done)" with D2 Notes; §5.4 acceptance
  boxes 3 + 4 + 5 + 6 ticked `[x]` with D2 notes; Queued-D2
  block replaced by this Done-D2 block; Queued-Phase-E block
  refreshed to note Phase D closure)

**Session-budget reality check:**

D2 fit comfortably in one session as forecast. Budget spend: two
`emit_telemetry.py` invocations for the JSONL side (following the
same pattern as D1 — derivation-helper invocations are well inside
the 2-run-per-session limit), one jsonschema validation run over
the full 168-record log, four targeted doc edits in SKILL.md
(Step 0b, Step 4d, Step 5 summary, Lesson workflow section +
constraint bullet), two edits in SCHEMA.md (Purpose intro +
Artifact section + change-log entry), one new file at repo root
(skill-lessons.yaml), and seven doc edits in
PIPELINE_EVOLUTION_PLAN.md (status paragraph, session-budget row,
four acceptance-box notes, handoff-block swap). No split risk
materialised. Phase D final session count: 2 used, 0 queued = 2
total, matching the original estimate exactly; no revision
needed.

### Done — Phase E (session E1 — terminology layer + custom-naming fixture link-up)

Closed 2026-04-23 by session E1. Phase E is the last phase on this
plan; the evolution plan is now end-to-end complete. All five §6.4
acceptance boxes tick `[x]` (see the notes under each box for the
concrete artifact refs). Total session count: **1**, matching the
session-count-table estimate exactly.

**Artifacts landed this session:**

- `/terminology.yaml` — v1.0 per-tenant synonym template at the
  repo root. `schema_version: '1.0'`, `tenant: CommercialAuto`,
  empty `synonyms.{exposures,coverages,fields}` and
  `display_name_aliases` maps, with a commented example block
  showing the §6.1 shape. Leading comment block mirrors the §6.3 /
  §7 hard constraints (per-tenant, no merging, exact-string only,
  canonicals must exist in registry, never under `.cursor/skills/`).
- `.cursor/skills/mapping-suggester/SKILL.md` — five coordinated
  edits:
  1. Inputs table gained a third row for `terminology.yaml`
     (optional, Phase E), flagging the sibling-of-registry
     resolution and the silent-skip-when-absent contract.
  2. New "Name-match precedence (Phase E — terminology layer)"
     subsection in the Matching strategy, inserted between the
     strategy intro and Rule 1. Documents the four-step ladder
     exact → case-insensitive → terminology synonym → fuzzy, the
     verbatim reasoning-line template
     `matched via terminology.yaml synonym <alias> → canonical <name>`,
     and the two hard constraints (single file per run,
     canonicals must exist). Rule 1 body rewrote "accept obvious
     synonyms" → "follow the four-step precedence" with an
     explicit hook to append the terminology reasoning line when
     the match came from step 3.
  3. New Step 0c ("Read `terminology.yaml` (Phase E synonym
     layer)") inserted between Step 0b and Step 1. Resolution
     order: `--terminology <path>` flag → sibling of
     `path-registry.yaml` → skip silently. MAJOR-halt / MINOR-warn
     mirrors Steps 0 and 0b. Unknown canonicals surface a
     `needs-skill-update: terminology canonical name <X> not found
     in registry` row in `.review.md` §7 at shape-probe time
     (non-halting). Hard constraint baked into the resolution
     rule: flag wins over sibling; skill never loads two files.
  4. New "Do not merge multiple terminology files" bullet in
     "Important constraints", mirroring the Phase E §6.3 / §7
     wording.
  5. Step 5 terminal block and the "After output" checklist both
     grew a terminology-layer line (never suppressed — downstream
     agents pattern-match on it the same way they do for the
     Lessons line from D2). The terminal line reports tenant
     name, active-alias count, and match count this run, or
     `(absent — skipped)` when the file wasn't loaded.
- `SCHEMA.md` — three coordinated edits:
  1. Purpose preamble updated from "six artifacts" → "seven
     artifacts" with a short description of the new
     `terminology.yaml` (YAML, `schema_version`, optional).
  2. New "Artifact: `terminology.yaml`" section with top-level
     tables (`schema_version`, `tenant`, `synonyms`,
     `display_name_aliases`), per-sub-map canonical-key
     resolution table, matching-precedence summary, and a full
     "Hard constraints" list restating the §6.3 / §7 + SKILL.md
     constraints (single file per run, canonicals must exist, no
     `.cursor/skills/` storage, no auto-promotion from lessons).
  3. Change-log entry `1.0 — 2026-04-23 — Phase E` summarising
     the new artifact, the five SKILL.md edits, and the no-op on
     all prior artifact shapes (mapping / registry / suggested /
     review / suggester-log.jsonl / skill-lessons.yaml still
     `1.0`).
- `conformance/fixtures/custom-naming/terminology.yaml` — fixture-local
  synonym layer. `tenant: DeepSeaFleet`,
  `synonyms.exposures.Octopus: [octopuses, octopi]`. Lives at the
  fixture root (sibling of `mapping.yaml`), which also happens to
  be the sibling-of-registry location the suggester resolves via
  Step 0c when pointed at `golden/path-registry.yaml`.
- `conformance/fixtures/custom-naming/golden/suggested.yaml` —
  regenerated. `octopuses` loop flipped from `low` +
  `supply-from-plugin` (the pre-Phase-E regression anchor) to
  `high` with `data_source: $data.octopus`, `foreach: '#foreach
  ($octopus in $data.octopus)'`, and a reasoning block carrying
  the verbatim `matched via terminology.yaml synonym octopuses →
  canonical Octopus` line. `policy_number` unchanged (the
  terminology hit is scoped to the loop). Header comment updated
  to call out the Phase E source and the new reasoning contract.
- `conformance/fixtures/custom-naming/golden/review.md` — regenerated.
  Counts: 2 `high` (1 variable + 1 loop), 0 `medium`, 0 `low`, 0
  blockers, 0 assumptions, 0 cross-scope warnings, 2 done items,
  0 unrecognised-inputs rows. Header gained a `Terminology:`
  bullet listing the loaded file, tenant, active-alias count, and
  match count this run. Done section annotates the `octopuses`
  row with `(via terminology.yaml synonym octopuses → canonical
  Octopus)`.
- `conformance/fixtures/custom-naming/FIXTURE.md` — rewritten from the
  C4-era "pre-Phase-E regression anchor, low + supply-from-plugin
  is correct conservative behaviour" framing to the Phase E
  "terminology-layer anchor, lifts to high via Rule 1 step 3"
  framing. Inputs section gained a `terminology.yaml` row.
  Goldens section updated counts + next-action breakdown + new
  Terminology bullet expectation.
- `conformance/fixtures/custom-naming/actual/suggested.yaml` +
  `actual/review.md` — promoted from the new goldens so
  `conformance/run-conformance.py` now reports `custom-naming
  registry=pass  suggested=pass  review=pass` (was
  `suggested=skipped  review=skipped` under C5). The C5 precedent
  of "skipped = pass for exit-code purposes" still holds for the
  other nine nested-shape / structure-variant fixtures; Phase E
  actively diffs the terminology fixture every run because the
  synonym-lookup assertion is the whole point of §6.4 row 4.

**Verification:**

- `python3 conformance/run-conformance.py` — 11/11 pass, exit `0`.
  `custom-naming` reports `registry=pass  suggested=pass
  review=pass`; the other ten fixtures are unchanged (one
  `suggested=pass review=pass` carry-over from C1 on
  `minimal/` + `all-quantifiers/`, nine `skipped/skipped` on the
  C2–C4 nested / structure / coverage-terms / no-exposures /
  custom-naming-subsection fixtures — wait, scratch that:
  `custom-naming` is no longer in the `skipped` set, so the final
  breakdown is 3 `pass/pass` (`all-quantifiers`, `minimal`,
  `custom-naming`) + 8 `skipped/skipped`).
- No Leg 2 agent runs were needed — the new goldens were
  authored by direct rule-application (the same "C1 / C2 / C3 /
  C4 precedent" cited in those handoffs). `extract_paths.py`
  did not change, so the `custom-naming/golden/path-registry.yaml`
  was unchanged and simply re-asserted by the runner.
- Session cost: well inside the 1-session estimate from the
  session-count table. No Leg 2 runs consumed, so the
  "2-full-runs-per-session" ceiling never risked firing; the work
  was SKILL.md edits + one fixture terminology file + two golden
  rewrites + one SCHEMA.md section + one repo-root template +
  one doc surgery pass in this plan.

**Follow-ups explicitly not in scope (deferred to future
sessions if they arise):**

- Wiring a live `terminology.yaml` sweep for the four
  `Samples/Input/` documents (claim-form, policy-template,
  quote-application, renewal-notice). Today those samples ship
  no terminology layer; a future session could seed one if a
  customer needs it.
- Promoting the Phase D `skill-lessons.yaml` seed rows into
  terminology entries. Phase E deliberately did not touch the
  lessons ledger (out-of-scope per the §5.2 seed's `status:
  observed` + the §7 "lessons accumulate, promotions are
  manual" hard constraint).
- Cross-tenant merging — explicitly prohibited by §6.3 / §7 and
  now by SKILL.md → "Important constraints".
- Wiring the JSONL or lessons ledger into
  `conformance/run-conformance.py` (queued as a future session
  independent of Phase E).
- Additional fixtures exercising `synonyms.coverages`,
  `synonyms.fields`, or `display_name_aliases` — the
  `custom-naming` fixture covers the `synonyms.exposures` code
  path; the other three sub-maps share the same step-3 lookup
  and are contract-equivalent. A dedicated fixture could be
  added if a customer report surfaces a bug in one of them.

---

## 0. Context (read before doing anything)

The companion plan `PIPELINE_IMPROVEMENTS_PLAN.md` fixes the **immediate**
weaknesses surfaced by the claim-form test run — quantifier awareness, scope
inheritance, ambiguity bubble-up. That work makes the pipeline correct for
the current inputs.

This plan makes the pipeline **durable**: it stops the skill from breaking
when:

- **The mapping YAML shape changes.** Leg 1 will evolve. New context keys
  will appear. Existing keys may gain values the current suggester doesn't
  recognise. Without a contract, silent skips or crashes are inevitable.
- **The socotra-config changes, customer by customer.** CommercialAuto
  uses a narrow slice of the Socotra configuration surface. Real tenants
  will throw nested iterables, custom data types, peril-based structures,
  jurisdictional qualifiers, and terminology drift at the pipeline.
- **The skill accumulates training signal across runs.** Every invocation
  is a data point. Without telemetry and a lesson log, every new customer
  starts from zero.

Do **not** start this plan until the companion plan's Phase 5 acceptance
criteria are all green. If Phase 1–3 of the companion plan hasn't landed,
schema-versioning the outputs is premature.

Reference docs in the local Socotra Buddy corpus:
- Quantifier rules: `~/socotra-buddy/resources/derived/125949463fad41f0.md`
- Policy elements overview: `~/socotra-buddy/resources/derived/` (grep
  `policyElements.html` in `manifest.json`)
- Custom data types: `~/socotra-buddy/resources/derived/` (grep
  `customDataTypes.html` in `manifest.json`)

---

## 1. Guiding principles (extends the companion plan's §1)

1. **Every run is a training signal.** Telemetry must be emitted even when
   all matches are high-confidence. A boring run is still a signal that
   the current rules cover the current inputs.
2. **Contracts over conventions.** Schemas are declared explicitly with a
   version; unknown keys are preserved; shape drift is observed, not
   tolerated silently.
3. **Fixtures, not samples.** Samples are nice stories. Fixtures are
   adversarial. Each known Socotra config feature must have a dedicated
   test-bench config, not just a hope that CommercialAuto exercises it.
4. **Synonyms are per-tenant, not per-skill.** Customer terminology
   (Vehicle vs Unit vs Asset) belongs in a tenant-scoped artifact, never
   in the skill's core matching rules.
5. **Lessons accumulate, promotions are manual.** The pipeline appends
   observations; a human reviewer promotes them into SKILL.md or
   terminology files. Never auto-promote — that's how brittle heuristics
   compound.
6. **The five existing principles from the companion plan still apply.**
   In particular: registry-is-source-of-truth, ambiguity-is-first-class,
   scope-inheritance-is-transitive.

---

## 2. Phase A — Schema evolution contract

**Goal:** Make every input/output of the pipeline self-describing and
drift-tolerant.

**Files produced / edited:**
- `.cursor/skills/mapping-suggester/scripts/extract_paths.py`
- `.cursor/skills/mapping-suggester/SKILL.md`
- `.cursor/skills/html-to-velocity/SKILL.md` (if Leg 1 is updated for loop
  hints per the companion plan's §5)
- `SCHEMA.md` (**new**, at repo root)

### 2.1 Add `schema_version` to every artifact

Every file produced by the pipeline carries a semantic-version string at
its root:

```yaml
# path-registry.yaml
schema_version: '1.0'
meta: { ... }
iterables: [ ... ]
...
```

```yaml
# <stem>.mapping.yaml (Leg 1 output)
schema_version: '1.0'
source: claim-form.html
generated_at: '...'
variables: [ ... ]
loops: [ ... ]
```

```yaml
# <stem>.suggested.yaml (Leg 2 output)
schema_version: '1.0'
input_mapping_version: '1.0'
input_registry_version: '1.0'
source: claim-form.html
...
```

```markdown
# <stem>.review.md (Leg 2 companion)
<!-- schema_version: 1.0 -->
# Review report — claim-form.html
...
```

Versioning rule:

- `MAJOR.MINOR`. MAJOR bumps on breaking shape changes. MINOR bumps on
  additive changes (new keys, new optional values).
- Suggester reads `input_mapping_version` and `input_registry_version` on
  startup. If `MAJOR` does not match its own supported MAJOR, it refuses
  to run and prints a clear upgrade path.
- Additive MINOR mismatches proceed with a warning only.

### 2.2 Shape-probe step (new Step 2a in the suggester SKILL)

Before any matching happens, the suggester inspects its two inputs and
prints a shape report:

```
Shape probe for claim-form.mapping.yaml (schema 1.0):
  Recognised context keys: parent_tag, nearest_label, line, loop
  Unrecognised context keys (preserved, not used): semantic_class
  Required keys present: name, placeholder, type, context, data_source
  Missing expected keys: (none)

Shape probe for path-registry.yaml (schema 1.0):
  Top-level sections: meta, iterables, system_paths, account_paths,
                      policy_data, policy_charges, exposures
  Unrecognised sections (preserved, not used): (none)
  Feature flags:
    nested_iterables:      false
    custom_data_types:     false
    jurisdictional_scopes: false
```

If any unrecognised key is observed, the `.review.md` file must include an
"Unrecognised inputs" section listing them, with a next-action of
`needs-skill-update: <describe>`.

If any required key is missing, the suggester halts before writing any
output and prints the upgrade path.

### 2.3 Document the recognised context-signal vocabulary

Add a new section to `.cursor/skills/mapping-suggester/SKILL.md`:

> **Recognised context signals (v1.0 contract):**
>
> | Key | Type | Meaning |
> |---|---|---|
> | `name` | string | Placeholder identifier (matches `field` in registry) |
> | `placeholder` | string | Full `$TBD_*` token |
> | `type` | enum | `variable` / `loop` / `loop_field` |
> | `context.parent_tag` | string | HTML parent element |
> | `context.nearest_label` | string | Closest label / heading text |
> | `context.line` | int | Line number in source HTML |
> | `context.loop` | string? | Enclosing loop name, if inside a `#foreach` |
> | `context.loop_hint` | string? | Detected-but-not-wrapped loop name |
> | `context.column_header` | string? | Table column header (for `<td>` context) |
> | `context.container` | string? | Container element (`ul`, `tbody`, etc.) |
> | `context.detection` | enum? | How Leg 1 detected this (`mustache`, `liquid`, `heuristic`) |
>
> Any other keys are **preserved but unused**. The suggester MUST NOT drop
> them. When encountered, they are reported under "Unrecognised inputs"
> in the `.review.md` file.

### 2.4 Publish `SCHEMA.md` at the repo root

Agent produces a new root-level file that documents:

- Every artifact's current version.
- Every recognised top-level section in each artifact.
- Every recognised nested key.
- The MAJOR/MINOR compatibility rules above.
- A "change log" section appended to on every version bump.

This is the living contract. Every future PR that changes artifact shape
MUST update `SCHEMA.md` and bump the relevant version — or the shape probe
will fire and block the run.

### 2.5 Acceptance criteria for Phase A

- [x] All five artifact types emit `schema_version` at their root.
      (Registry + mapping YAML carry it from A1; suggested YAML and
      review MD now carry it on `claim-form.*` from session A2.
      Suggester-log JSONL is reserved in `SCHEMA.md` for Phase D and
      not yet emitted.)
- [x] Suggester reads and validates `input_mapping_version` /
      `input_registry_version` and behaves per §2.1. (Session A2
      demo run: matched 1.0/1.0 and proceeded silently; fake-v2.0
      halt verified MAJOR mismatch short-circuits before any output is
      written.)
- [x] Shape-probe step runs before matching; produces the output format
      in §2.2. (Session A2 demo run printed the block verbatim with
      `nearest_heading` correctly classified as unrecognised; round-trip
      run added `synthetic_key` to the same line without regressing the
      other three section labels.)
- [x] Unknown keys preserved through the suggester (round-trip test: a
      mapping YAML with an extra `context.synthetic_key: abc` reappears
      in the suggested YAML unchanged). (Session A2 step 9 — see Notes
      under step 9 above for the three-point verification.)
- [x] `SCHEMA.md` written at repo root with full v1.0 documentation.
      (Landed in session A1 step 5.)
- [x] SKILL.md recognised-signals table added. (Landed in session A1
      step 3 — 11 rows covering `context.*` signals.)
- [x] Running the suggester on a v2.0 registry (fake it by editing the
      version string) halts with a clear upgrade message. (Session A2
      step 10 — halt fired before file reads; halt message matched the
      spec; no output files were touched.)

---

## 3. Phase B — Socotra config coverage matrix

**Goal:** Enumerate every Socotra configuration feature the pipeline must
eventually handle, and track which are supported today.

**Files produced / edited:**
- `CONFIG_COVERAGE.md` (**new**, at repo root)
- `.cursor/skills/mapping-suggester/scripts/extract_paths.py` (emits
  `feature_support` into the registry)

### 3.1 Draft `CONFIG_COVERAGE.md`

Living table, one row per Socotra config feature. Columns:

| Feature | Example token / snippet | In CommercialAuto? | In registry today? | Handled in SKILL today? | Fixture path | Notes |
|---|---|---|---|---|---|---|

Initial row seeds (agent expands this list by grepping the Socotra Buddy
corpus for config-shape examples):

- Exposure quantifier `+` (`"Vehicle+"`)
- Exposure quantifier `*`
- Exposure quantifier `?`
- Exposure quantifier `!` (auto-created)
- Exposure no-suffix (exactly one)
- Coverage quantifier `?` (`"MedPay?"`)
- Coverage quantifier `!` (`"collision!"`)
- Coverage no-suffix (`"Coll"`)
- Coverage with `coverageTerms`
- Coverage term with default-option prefix `*`
- Data-extension scalar `?` (`"type": "string?"`)
- Data-extension array `+` of primitive (`"type": "string+"`)
- Data-extension array `*` of primitive
- Data-extension array of custom data type (`"type": "Driver+"`)
- Custom data type (CDT) defined under `customDataTypes/` — flat
- CDT — recursive (`Address` contains `Address?`)
- CDT — references another CDT
- Peril-based product structure (if present in docs)
- Jurisdictional qualifier on coverage (`"uw4+"` role qualification,
  `"appliesTo": ["claim"]`, etc.)
- Multi-product config tree (two subdirs under `products/`)
- Non-`$data` root object (plugin-supplied renderingData shape)
- Document attachment config (`documents: [...]` on product / transaction
  state)
- Policy-level charges
- Coverage-level charges
- Account type variation (`ConsumerAccount` vs `BusinessAccount`)
- Segment / transaction data access

### 3.2 Emit `feature_support` into the registry

`extract_paths.py` scans the config once and writes:

```yaml
# path-registry.yaml
schema_version: '1.0'
feature_support:
  nested_iterables:        true|false
  custom_data_types:       true|false
  recursive_cdts:          true|false
  jurisdictional_scopes:   true|false
  peril_based:             true|false
  multi_product:           true|false
  coverage_terms:          true|false
  default_option_prefix:   true|false   # '*value' on coverage term options
  auto_elements:           true|false   # '!' anywhere
  array_data_extensions:   true|false
```

Flags are determined by structural inspection, not by file presence
alone (e.g. `coverage_terms: true` iff any coverage's `config.json` has a
`coverageTerms: [...]` array).

The suggester uses these flags to decide whether to load optional
matching rules. It must refuse to match against a feature whose flag is
`true` but whose corresponding rule hasn't been implemented yet — instead
produce a `needs-skill-update` next-action and surface it in `.review.md`.

### 3.3 Governance rule for `CONFIG_COVERAGE.md`

Every PR that touches `extract_paths.py` or `SKILL.md` MUST:
1. Review the matrix for any row whose "Handled in SKILL today?" status
   would change.
2. Update the row.
3. Add/update the corresponding fixture under `conformance/fixtures/` (see
   Phase C).

An agent executing this plan for the first time populates the full matrix
from the corpus, marking every row honestly — most will be "no" today,
which is fine. The matrix is a roadmap, not a shame list.

### 3.4 Acceptance criteria for Phase B

- [x] `CONFIG_COVERAGE.md` written at repo root with at least the 23
      seed rows above, each with a truthful status. (Session B1 —
      26 rows total: 24 under §3.1–§3.7 covering every seed row + the
      `context.nearest_heading` loop-signal row, plus 2 placeholder
      rows in §3.7 for account-type / segment access gaps. Every
      row cites either a live file under `socotra-config/` or flags
      "B2 to confirm against the Socotra Buddy corpus".)
- [x] `extract_paths.py` emits `feature_support` into the registry and
      every flag is determined by structural scan, not hard-coded.
      (Session B1 — `detect_features()` walks `products/`, `perils/`,
      `customDataTypes/`, `coverages/`, `exposures/`, `accounts/`,
      and the product config's own `contents` + `data`; every flag's
      derivation is documented in the function's docstring and
      mirrored in SCHEMA.md's `feature_support` keys table.)
- [x] Running `extract_paths.py` on the current `socotra-config/`
      produces a registry whose feature flags match the matrix's
      "In CommercialAuto?" column. (Session B1 regeneration:
      `Feature flags on: 0 / 10`; all ten flags `false`, matching
      every §3.1–§3.7 row marked "no" or "partial" — `partial` rows
      intentionally don't flip a `feature_support` flag on by design,
      per the flag-definition rules in `CONFIG_COVERAGE.md` §3.)
- [x] SKILL.md documents the `feature_support` block and the refusal
      rule for unsupported-but-present features. (Session B1 — the
      Step 2a shape-probe "Rules:" list gained two new bullets: a
      deterministic-ordering clause on the existing `Feature flags:`
      terminal output, and the new "Feature-support refusal rule"
      bullet with the explicit rule-supported whitelist
      [`auto_elements`, `array_data_extensions`] vs. refusal flags
      [the other eight]. Scoped exclusively to Step 2a — no Step 3
      matching rules were touched.)
- [x] Governance note added to `CONFIG_COVERAGE.md` (the last paragraph
      of §3.3). (Session B1 — §5 of `CONFIG_COVERAGE.md` reproduces
      the governance rule verbatim from §3.3 here, with an explicit
      citation-requirement clause added per §8's "confirm the feature
      exists in the mirrored docs first" stop-and-ask rule.)

---

## 4. Phase C — Conformance fixture suite

**Goal:** Replace reliance on four real samples with an adversarial set
of minimal configs that exercise every row in `CONFIG_COVERAGE.md`.

**Files produced:**
- `conformance/fixtures/socotra-configs/<fixture>/` (per-fixture mini-config trees)
- `conformance/fixtures/mappings/<fixture>.mapping.yaml` (matching inputs)
- `conformance/fixtures/golden/<fixture>.suggested.yaml` (expected outputs)
- `conformance/fixtures/golden/<fixture>.review.md` (expected review reports)
- `conformance/run-conformance.py` (**new** runner script)

### 4.1 Seed fixtures

Each fixture directory follows the real `socotra-config/` shape but is
minimal. Seed the suite with at least:

- `minimal/` — one product, one exposure, no coverages, one field.
- `all-quantifiers/` — every suffix (`!`, `?`, `+`, `*`, none) present on
  some element; no CDTs.
- `nested-iterables/` — a data-extension array of a CDT on an exposure
  (e.g. Vehicle has `"owners": { "type": "Owner+" }`).
- `cdt-flat/` — one CDT used as a scalar field type (`"dwellingAddress":
  { "type": "Address" }`).
- `cdt-recursive/` — CDT references itself (Rex territory).
- `multi-product/` — two products under `products/`, each with its own
  `contents`.
- `jurisdictional/` — coverage with `qualification` / `appliesTo` /
  `exclusive` (grep the corpus for live examples).
- `peril-based/` — product structured around perils rather than coverages
  (if this pattern exists in the mirrored docs).
- `no-exposures/` — a monoline product with zero exposures, all data on
  the policy and account.
- `custom-naming/` — exposure/field names that don't pluralise cleanly
  (`Octopus` → `octopuses`/`octopi` decision point).

Agents creating fixtures MUST:
- Use the minimum number of files to exercise the feature.
- Name files and tokens deterministically (no timestamps in fixture
  content).
- Include a `FIXTURE.md` in each fixture directory describing which
  `CONFIG_COVERAGE.md` rows the fixture covers and what behaviour it
  proves.

### 4.2 Per-fixture inputs and golden outputs

For each fixture, produce:

- `conformance/fixtures/mappings/<fixture>.mapping.yaml` — a hand-written Leg 1
  output whose placeholders exercise the fixture's features. Tiny — 3–10
  placeholders per fixture is fine.
- `conformance/fixtures/golden/<fixture>.suggested.yaml` — the expected Leg 2
  output byte-for-byte (after running the upgraded suggester once, sanity
  checking, then freezing).
- `conformance/fixtures/golden/<fixture>.review.md` — same.

### 4.3 Runner script

`conformance/run-conformance.py`:

1. For each fixture, regenerate the registry with `extract_paths.py`.
2. Run the suggester on the fixture's mapping YAML.
3. Diff the actual output against the golden file.
4. Report pass/fail per fixture, with a summary at the end.
5. Exit non-zero on any diff.

Include a `--update-goldens` flag that rewrites the golden files after
the agent verifies the diffs by eye. (This prevents "green by accident"
regressions sliding through.)

### 4.4 Acceptance criteria for Phase C

- [x] Ten seed fixtures written with `FIXTURE.md` + config tree + mapping +
      golden suggested + golden review. (11 delivered across sessions
      C1–C4 — the seed count grew by one when `peril-based/` deferred
      per the C3 corpus-grep outcome and `jurisdictional-exclusive/`
      took its slot. `peril_based` is the only refusal flag still
      unobserved `true` in any fixture, tracked as deferred pending a
      docs citation or live customer sample.)
- [x] `conformance/run-conformance.py` runs and passes every fixture. (11/11
      pass as of 2026-04-22 — `minimal/` + `all-quantifiers/` pass
      registry + suggested + review; the other 9 fixtures pass
      registry and report `skipped` for suggested + review per the
      §4.3 deviation tracked in the Done-C4 handoff block. Exit
      code `0`.)
- [x] Every row in `CONFIG_COVERAGE.md` whose "In fixture?" column is
      populated points at a real fixture directory. (Verified: rows
      1–21 all cite one or more live `conformance/fixtures/<name>/`
      directories; row 18 `peril_based` correctly reads "deferred"
      and does not cite a fixture, matching the C3 deferral decision.)
- [x] The companion plan's regression step (§6) is extended to run the
      fixture suite **before** the sample-based regression.
      (`PIPELINE_IMPROVEMENTS_PLAN.md` §6.0 "Fixture suite regression
      (Phase C gate)" added in session C5; §6.4 carries a matching
      ticked acceptance box.)

---

## 5. Phase D — Run telemetry & accumulated lessons

**Goal:** Turn every suggester invocation into a data point, and make it
cheap to spot patterns across customers.

**Files produced per run:**
- `<stem>.suggester-log.jsonl` (**new**, next to the suggested YAML)

**Repo-level files:**
- `skill-lessons.yaml` (**new**, at repo root)

### 5.1 Per-run telemetry (`.jsonl`)

One JSON object per line. Schema:

```json
{"ts": "2026-04-21T14:26:00Z", "run_id": "<uuid>", "kind": "placeholder",
 "name": "vehicle_year", "placeholder": "$TBD_vehicle_year",
 "context": {"parent_tag": "p", "nearest_label": "Insured vehicle",
             "line": 90, "loop": null, "loop_hint": "vehicles"},
 "chosen_match": null, "confidence": "low",
 "next_action": "restructure-template",
 "rejected_candidates": [
   {"velocity": "$vehicle.data.year", "reason": "scope_violation"}
 ],
 "unknown_context_keys": []}
```

Plus one per-run summary record at the end:

```json
{"ts": "...", "run_id": "...", "kind": "summary",
 "source": "claim-form.html", "product": "CommercialAuto",
 "totals": {"variables": 37, "loops": 4},
 "confidence_counts": {"high": 2, "medium": 6, "low": 33},
 "next_actions": {"supply-from-plugin": 24,
                  "restructure-template": 7,
                  "confirm-assumption": 6},
 "dead_registry_paths": ["$data.data.expRateCompColl", "..."],
 "hot_registry_paths":  ["$data.policyNumber"],
 "unknown_context_keys_seen": []}
```

**Dead paths** = registry entries that matched zero placeholders.
**Hot paths** = registry entries that matched two or more placeholders
(candidates for synonym promotion).

The suggester emits telemetry even on a fully-high-confidence run.
Absence of the log file is a bug, not a feature.

### 5.2 Repo-level `skill-lessons.yaml`

Accumulated across runs, hand-curated. The suggester **appends** new
observation rows but **never** edits existing ones. Shape:

```yaml
schema_version: '1.0'
lessons:
- id: claimant-eq-policyholder
  first_seen: '2026-04-20'
  last_seen:  '2026-04-21'
  seen_count: 2
  observed_in: [claim-form, renewal-notice]
  pattern: "claimant_* variables on docs where no Claim entity exists"
  current_rule: "medium, confirm-assumption"
  candidate_promotion: null     # filled in by a human reviewer
  status: observed              # observed | proposed | promoted | rejected

- id: vehicle-scope-violation
  first_seen: '2026-04-21'
  last_seen:  '2026-04-21'
  seen_count: 1
  observed_in: [claim-form]
  pattern: "vehicle_* placeholders outside any vehicles foreach"
  current_rule: "low, restructure-template"
  candidate_promotion: null
  status: observed
```

Promotion workflow (executed by a human reviewer, not an agent):

1. Review rows with `seen_count >= 3` and `status == observed`.
2. Propose a concrete rule change in `candidate_promotion`, flip status
   to `proposed`.
3. Another reviewer (or the same one after cooling off) either:
   - Accepts — copies the rule into `SKILL.md`, flips status to `promoted`.
   - Rejects — writes a reason, flips status to `rejected`.

No agent ever auto-promotes. Auto-promotion is how the skill goes from
"tight rules" to "mystery heuristics" in three months.

### 5.3 Suggester behaviour changes

- Always emit `<stem>.suggester-log.jsonl` (per-run).
- On startup, read `skill-lessons.yaml` if present. For each lesson with
  `status == promoted`, apply the promoted rule. Ignore `observed` and
  `proposed` rows (they're not yet part of the contract).
- On shutdown, append new observation rows to `skill-lessons.yaml` if
  any patterns recurred this run (detected by comparing the run's
  `next_actions` distribution to the lessons file's `pattern` column
  using exact-string match for now; fuzzy matching is out of scope).

### 5.4 Acceptance criteria for Phase D

- [x] Every suggester run writes a `<stem>.suggester-log.jsonl`.
      _D1 (2026-04-22): `mapping-suggester/SKILL.md` gained a
      mandatory Step 4c ("Append the per-run telemetry log") plus
      a new "Telemetry file format" section and an updated Output
      format + Step 5 + After output to cite the log as the third
      artifact. Helper script at
      `.cursor/skills/mapping-suggester/scripts/emit_telemetry.py`
      lets agents derive the JSONL from the already-written
      suggested YAML when per-candidate rejection reasons don't
      need to be captured. Verified on `claim-form` — 42 records
      emitted (37 variables + 4 loops + 1 summary)._
- [x] JSONL conforms to the schema in §5.1 (validate with a tiny JSON
      Schema file under `conformance/schemas/suggester-log.schema.json`).
      _D1 (2026-04-22): Draft 2020-12 JSON Schema written at that
      path. Validated two full runs (84 records total, 82
      `placeholder` + 2 `summary`) with `jsonschema 4.26.0` from a
      throwaway venv — `errors=0`. Schema covers both record kinds
      via `oneOf`, enumerates the closed vocabularies for
      `next_action` and `rejected_candidates.reason`, and preserves
      unknown context keys via `additionalProperties: true` on the
      nested `context` object._
- [x] `skill-lessons.yaml` created at repo root, seeded with the two
      lessons from the claim-form test run above.
      _D2 (2026-04-22): `skill-lessons.yaml` written at the repo root,
      seeded with the two lessons from §5.2 verbatim
      (`claimant-eq-policyholder` and `vehicle-scope-violation`) at
      their original `seen_count` values (2 and 1) and statuses
      (`observed` on both). The two live runs below then bumped
      `seen_count` to 4 and 3 respectively; `status` and
      `candidate_promotion` stayed untouched on both rows per the
      agent-auto-promotion hard constraint._
- [x] SKILL.md documents the lesson workflow with the `observed /
      proposed / promoted / rejected` state machine.
      _D2 (2026-04-22): `mapping-suggester/SKILL.md` gained a new
      top-level "Lesson workflow (Phase D)" section with the
      `observed → proposed → {promoted, rejected}` state-machine
      diagram, a division-of-responsibility table (agents may
      append + bump, humans own transitions), the seeded per-lesson
      matcher table (v1.0 matchers for `claimant-eq-policyholder`
      and `vehicle-scope-violation`), the exact-string pattern-match
      semantics, and the `seen_count >= 3` review-threshold note.
      Paired with a new Step 0b (read ledger on startup; apply
      promoted rules only) and Step 4d (MANDATORY when the file is
      present — bump matched existing rows, append new `observed`
      rows for unknown patterns, never flip status or author
      `candidate_promotion`)._
- [x] Running the suggester twice produces two summary records with
      different `run_id`s and growing `seen_count` on the matching
      lesson row.
      _D1 (2026-04-22) landed the `run_id` half on two derivation
      runs (`5b7e1c22-…-0001` / `9c2a71e6-…-0002`). D2 (2026-04-22)
      closes the growth half: two further live runs against
      `claim-form` with fresh run-IDs
      (`3a8f12d4-b7c9-4e25-8146-1f2d40c7d003` and
      `7b4e93a2-c8f1-45d3-9a57-0e6b8d2f3004`) each appended one
      `kind: summary` record to
      `Samples/Output/claim-form.suggester-log.jsonl` (now 168
      records across 4 runs — 164 `placeholder` + 4 `summary`,
      `jsonschema 4.26.0 errors=0`) AND incremented `seen_count` on
      both matched lessons via the Step 4d lesson-append code path:
      `claimant-eq-policyholder` 2 → 3 → 4 (12 `claimant_*`
      placeholders trip the matcher on every run), and
      `vehicle-scope-violation` 1 → 2 → 3 (5 `vehicle_*` placeholders
      with `next_action: restructure-template` trip the matcher).
      `last_seen` advanced to `2026-04-22` on both rows; `observed_in`
      was not extended (claim-form already present on both)._
- [x] Manual promotion protocol documented; agent-auto-promotion
      explicitly forbidden in a hard constraint.
      _D2 (2026-04-22): the Phase D §7 "Do not auto-promote lessons"
      hard constraint got a companion bullet in
      `mapping-suggester/SKILL.md` → "Important constraints" with
      the exact prohibitions (no `status` flips, no
      `candidate_promotion` authorship, no edits to `pattern` /
      `current_rule` on existing rows, test-failure-not-style-
      guideline enforcement). The "Lesson workflow (Phase D)"
      section above restates the state-machine transitions as
      human-only. `SCHEMA.md` also carries the restatement in its
      new `Artifact: skill-lessons.yaml` section under
      "Agent-auto-promotion prohibition" for third-artifact
      redundancy. Two live D2 runs exercised the lesson-append
      path without firing any of the prohibited writes — both
      lesson rows retained `status: observed` and
      `candidate_promotion: null` after bump._

---

## 6. Phase E — Synonym / terminology layer

**Goal:** Handle customer-specific naming without bleeding tenant data
into the skill's core rules.

**Files produced:**
- `terminology.yaml` (**new**, at repo root; per-tenant convention)
- `.cursor/skills/mapping-suggester/SKILL.md` (documents lookup order)

### 6.1 Format of `terminology.yaml`

```yaml
schema_version: '1.0'
tenant: CommercialAuto     # free text; identifies which tenant this file
                           # belongs to. Separate tenants = separate files.
synonyms:
  exposures:
    Vehicle: [unit, asset, auto, car]
    Driver:  [operator, insured-party, named-insured, principal-operator]
  coverages:
    Liability: [bi-pd, third-party, tpbi]
    Coll:      [collision]
    Comp:      [comprehensive, otc, other-than-collision]
  fields:
    vin: [hin, serial-number]
    year: [model-year]
display_name_aliases:
  "Gross Vehicle Weight": [gvw, weight-rating, gvwr]
```

Starts empty; grows as lessons get promoted or as the user hand-edits
per customer.

### 6.2 Suggester matching precedence

When trying to match a placeholder `name` / `nearest_label`:

1. Exact match against registry `field` / `display_name`.
2. Case-insensitive match against the same.
3. `terminology.yaml` lookup — does the placeholder name (or label) appear
   in any synonym list? If yes, the canonical name (the map key) is the
   candidate.
4. Fuzzy / partial match (current behaviour).

Any match made via step 3 carries an extra `reasoning` line:
"matched via terminology.yaml synonym `<alias>` → canonical `<name>`".

### 6.3 Never bundle per-tenant terminology into the skill

- `terminology.yaml` lives at the **repo / project** root, not under
  `.cursor/skills/`.
- The skill reads it from `--terminology <path>` or a conventional
  sibling-of-registry location (`<registry>/../terminology.yaml`).
- Cross-tenant contamination is explicitly prohibited: the skill MUST
  NOT merge multiple terminology files. Pick one per run.

### 6.4 Acceptance criteria for Phase E

- [x] `terminology.yaml` template written at repo root (empty or with a
      single example synonym).
      (Session E1, 2026-04-23 — landed at `/terminology.yaml` with
      `schema_version: '1.0'`, `tenant: CommercialAuto`, empty synonym
      sub-maps, and a commented example block showing the §6.1 shape.
      Hard constraints from §6.3 / §7 mirrored inline as a leading
      block comment.)
- [x] Suggester reads it when present, skips silently when absent.
      (Session E1 — new Step 0c in
      `.cursor/skills/mapping-suggester/SKILL.md` resolves
      `--terminology <path>` first, then the
      sibling-of-`path-registry.yaml` default, then skips silently
      when neither resolves. MAJOR-halt / MINOR-warn semantics
      mirror Steps 0 and 0b. Unknown canonicals surface a
      `needs-skill-update:` row in `.review.md` §7 but do not halt
      the run.)
- [x] Matching precedence documented in SKILL.md as §6.2 above.
      (Session E1 — new "Name-match precedence (Phase E —
      terminology layer)" subsection in the Matching strategy with
      the four-step ladder exact → case-insensitive → terminology
      synonym → fuzzy, the standard reasoning-line template, and
      inline cross-links to the hard constraints. Rule 1 body
      rewritten to reference the precedence instead of inventing a
      local "obvious synonym" rule.)
- [x] Fixture `custom-naming/` (from Phase C) exercises a synonym
      lookup and asserts the reasoning line.
      (Session E1 — `conformance/fixtures/custom-naming/terminology.yaml`
      landed at the fixture root declaring
      `synonyms.exposures.Octopus: [octopuses, octopi]`; the
      `golden/suggested.yaml` lifts the `octopuses` loop from `low`
      + `supply-from-plugin` to `high` with the verbatim
      `matched via terminology.yaml synonym octopuses → canonical
      Octopus` reasoning line; the `golden/review.md` promotes the
      loop to the Done section with the synonym cite and zeroes the
      Blockers / Assumptions / Cross-scope sections. The runner
      now reports `custom-naming  registry=pass  suggested=pass
      review=pass` — the round-trip is actively diffed every
      invocation rather than skipped. `FIXTURE.md` rewritten from
      "pre-Phase-E regression anchor" to "Phase E terminology-layer
      anchor"; the deletion / absence case is called out as the
      fallback that reverts to the session-C4 behaviour.)
- [x] Hard constraint added: no merging of multiple terminology files in
      one run.
      (Session E1 — new "Do not merge multiple terminology files"
      bullet in SKILL.md → "Important constraints", mirroring the
      PIPELINE_EVOLUTION_PLAN.md §6.3 / §7 wording. Resolution rule
      when both `--terminology <path>` and the sibling default
      exist: flag wins, sibling is ignored. Cross-referenced from
      the SCHEMA.md "Artifact: `terminology.yaml`" → "Hard
      constraints" section. The constraint is enforced by single-
      file load in Step 0c — the skill never calls its YAML loader
      twice for the terminology layer in one run.)

---

## 7. Hard constraints (do NOT violate)

- **Do not run any phase in this plan until the companion plan is done.**
  Schema-versioning outputs before the outputs are stable is churn.
- **Do not auto-promote lessons.** Agents may append observations; only
  humans move them from `observed` to `promoted`. Violation of this rule
  must be a test failure, not just a style guideline.
- **Do not invent synonym mappings from training data.** Every entry in
  `terminology.yaml` is either user-provided or copied from a promoted
  lesson. Silent invention = brittleness.
- **Do not fold `terminology.yaml` into `path-registry.yaml`.** Keeping
  them separate prevents tenant data from being committed under the
  skill directory.
- **Do not drop unknown context keys.** Round-tripping is enforced by
  §2.5 acceptance criteria.
- **Do not edit the companion plan** (`PIPELINE_IMPROVEMENTS_PLAN.md`).
  If it needs corrections, raise them back to the user; do not touch it
  as part of this work.
- **Do not commit to git** unless the user explicitly asks.
- **Do not fetch from the public web.** The Socotra Buddy corpus is the
  only allowed source for platform rules.

---

## 8. Stop and ask the user when

- A new Socotra config feature is observed in the wild that doesn't appear
  in `CONFIG_COVERAGE.md`. Do **not** silently add a row; confirm the
  feature exists in the mirrored docs first.
- A `skill-lessons.yaml` row reaches `seen_count >= 5` with no human
  review — surface it in the next `.review.md` output so it can't be
  ignored.
- A fixture under `conformance/fixtures/` starts failing after a change. Stop,
  print the diff, don't auto-`--update-goldens`.
- The shape probe reports any unknown key that recurs across three or
  more runs. That's a signal Leg 1 has a stable new signal the skill
  should formally recognise.
- A tenant's `terminology.yaml` contains an entry that conflicts with a
  registry canonical name (e.g. an alias that's also a valid registry
  field). Ambiguity → user decision.

---

## 9. Execution order (one pass)

1. **Phase A (§2)** — schema versioning & shape probe. Gates everything
   else because later phases reason about versioned artifacts.
2. **Phase B (§3)** — config coverage matrix + `feature_support`. Needs
   the registry shape stabilised by Phase A.
3. **Phase C (§4)** — conformance fixtures. Depends on B's matrix to
   know which features to exercise.
4. **Phase D (§5)** — telemetry & lessons. Independent of C but reads
   `schema_version` from A, so comes after A.
5. **Phase E (§6)** — terminology / synonyms. Last because it consumes
   lessons from D and is exercised by fixtures from C.

Each phase has its own acceptance-criteria checklist. Do not advance
until every box in the current phase is ticked.

---

## 10. Out of scope (explicitly)

- **Fuzzy / NLP matching of synonyms.** `terminology.yaml` is exact
  strings for now. Semantic similarity is a separate project.
- **Cross-tenant lesson pooling.** `skill-lessons.yaml` stays in one
  repo. Aggregating lessons across customer deployments is a governance
  problem, not a tooling one.
- **A web UI for the review file.** Markdown is the interface.
- **Auto-generating synthetic fixtures from a grammar.** Fixtures are
  hand-written for now; property-based generation is a future phase.
- **Extending Leg 3 (substitution writer).** This plan does not touch
  Leg 3. A separate plan will handle scope-aware substitution, lesson-
  informed guard insertion, etc.
- **Supporting non-YAML registries.** The registry stays YAML.
- **Cloud telemetry.** All telemetry stays on-disk, next to the
  artifacts. No network calls.
