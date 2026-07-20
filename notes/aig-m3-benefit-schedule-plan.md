# AIG M3 — benefit schedule restructure plan

*2026-07-16. Josh's decision (recorded): model the C11697DBG benefit schedule on the
marker machinery — `[Risk/]` loop + `[Cov?]` presence regions + in-loop VALUE
conditions — NOT plugin-computed doc-scoped booleans. This note is the execution spec;
the enabling pipeline work is DONE and merged into the working tree (see below).*

## Pipeline work completed this session (tested, 520 regression + 11 fixtures PASS)

1. **In-loop value conditions** — a `[Name?]` region inside a `[Loop/]` whose `Name`
   is NOT a coverage of that exposure is now a when-only variants.csv row whose
   condition is **per-item** (paths root at the loop iterator, e.g.
   `risk.AccidentMedicalExpense.data.includeDeductible == "Yes"`). Leg 3 compiles it
   via `condition_dsl.condition_to_velocity()` into an in-template `#if` inside the
   loop (every hop truthiness-guarded); Leg 4 skips it (no plugin key). Sidecar and
   registry blocks carry `loop_scope: {loop, iterator}`. Exercised by
   `TestCoverageGrid(segment)`'s `[BreakdownLabourRow?]` + `tests/regression/
   test_conditional_regions.py::InLoopValueConditionTests`.
2. **Repeated `[[$token]]` markers are legal** — dedupe to one block with a stderr
   NOTE; every occurrence annotates to the same `$doc.<token>` (the annotator's
   literal-replace path). Needed because the shared state label
   `[[$coveredActivityMaxAmtLabel]]` appears in ~30 benefit texts once they move
   into the doc body.

## Ground truth (recon this session)

- The schedule (docx section 2.A) is a **flat list of 36 `[[$token]]` markers**, one
  per benefit; each token's text lives in the filled
  `workspace-prod/action-needed/C11697DBG(quote).variants.csv` (89 rows — the
  source of truth for benefit text; the (segment) CSV had these rows neutralized in
  the M2 surgery).
- AIG registry (`workspace-prod/registry/path-registry.yaml`): iterable **Risk**,
  iterator **$risk**, list `$data.risks`; **44 coverages on Risk** whose names match
  the `quote.benefitsAndElements.<X>` presence checks (strip the `Quote` suffix the
  response types carry, e.g. `CovidRiderQuote` → `CovidRider`). Coverage `fields`
  carry every sub-limit leaf (AME: includeDeductible, coinsurancePercentage, …).

## The mechanical mapping (per benefit token)

| Authored today | Restructured |
|---|---|
| `[[$accidentalDismembermentBenefit]]` marker, text in CSV, `when: quote.benefitsAndElements.AccidentalDismembermentBenefit != null and benefit.data.X != null` | `[AccidentalDismembermentBenefit?]` … body text … `[/AccidentalDismembermentBenefit]` inside `[Risk/]` — coverage presence, zero fill |
| `{field}` bare leaves in CSV text | `{risk.<Cov>.data.<field>}` dotted coverage-hop fields (auto cell-guarded by Leg 3) |
| sub-conditional rows (`benefit.data.includeSublimits == "Yes"`, `benefit.data.physicalTherapySubLimit != null`) | nested `[<uniqueName>?]` in-loop VALUE regions; CSV `when` = `risk.<Cov>.data.<f> == "Yes"` / `risk.<Cov>.data.<f> present` |
| nested `[[$coveredActivityMaxAmtLabel]]` etc. inside texts | stay as inline `[[$label]]` markers in the body (now-legal duplicates); their state-conditioned rows return to the variants.csv (doc-scoped — same for every risk, correct semantics) |

Simplification (deliberate): the authored `and benefit.data.X != null` conjunct on
presence rows is dropped — coverage presence implies its required fields; the field
cell-guard blanks the value if not. Wrap section 2.A from `CLASS(ES) {classNumbers}`
through the `[[$aggregateDeductible]]`/`[[$aggregateLimit]]` lines in
`[Risk/]`…`[/Risk]`; `{classNumbers}` and the AD maximum (`{---}` fields from the M1
report) become `{risk.data.<f>}` loop fields.

## Riders table (`(formNumber)`/`(formDescription)`)

A plugin-list loop (like ZenCover's `[Coverage/]`): declare a `kind: plugin_list`
iterable in the AIG registry (one entry per rider attached to any risk). **Open
design point:** formNumber/formDescription are not coverage data fields — they need
a name→form lookup (constraint table or hardcoded map) inside the generated/hardened
list builder. Check the reference config's tables for a forms lookup first.

## Remaining execution steps (next session)

1. Converter script (scratchpad): read the (quote) CSV → emit the restructured
   section 2.A content; splice into `C11697DBG(segment).docx` via python-docx
   (git is the undo). Token→coverage name from each row's `when`
   (`benefitsAndElements.<X>`, strip `Quote` suffix).
2. Full re-run: leg0 ingest (AIG registry passed so `[Cov?]` classifies) →
   programmatic CSV fill (labels + fraud warnings reuse the M2 segment fills;
   value-region whens from the mapping above) → parse → Leg 2+3 (grep-gate) →
   Leg 4 (`--customer-jar workspace-prod/reference/build/customer-config.jar
   --datamodel-jar …v1.7.71.jar --compile-check`).
3. Re-apply the minimal hand-hardening (policyView wrapper + address2 accessor —
   see `notes/aig-live-render-plan.md` M2 entry), rebuild + deploy via
   `tools/aig_deploy_bundle.py`, render vs policy `01KXN6ZCY8JBXR1BREMQBJD4DX`
   (`--reference-type policy`). Seeded coverages available live: AD&D,
   AccidentMedicalExpense, Coma — those rows should render, all others hide.
4. Blocker C leftovers (4 blocks: `not in`, `diffDays`, metadata indexing, bare
   `data.` root) remain out of scope.
