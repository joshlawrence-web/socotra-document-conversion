# AIG (C11697DBG) live end-to-end render — workflow plan

*2026-07-16. Goal: render `C11697DBG(quote).final.vm` through the REAL ad-hoc render
endpoint (deployed SnapshotPlugin, real quote) — no spoofed renderingData.*

## Ground truth (from recon, 2026-07-16)

- The **real AIG config exists in-repo**: `workspace-prod/reference/socotra-config/`
  (product `BlanketSpecialRisk`, `Risk+` exposure, 48 coverages, coverage terms,
  ~195 tables) + matching jars in `workspace-prod/reference/build/`
  (`customer-config.jar`, `core-datamodel-v1.7.71.jar`). Registry
  (`workspace-prod/registry/path-registry.yaml`, 608 paths) was generated from it.
  **No config authoring needed — deploy what we have.**
- Sandbox access is live: `.env.ai-documents` filled, WelcomeLetter(quote) renders.
  Current tenant runs **ZenCover** — a different config tree.
- Deploy tooling is **external/manual** (Studio UI or Config Deployments API);
  `build/socotra-uploaded-datamodel.zip` proves a prior manual round-trip.
- Pipeline state for the doc: path-review **filled** (8 plain fields resolved),
  variants layer **0/89 passing** (Blockers A/B/C in
  `workspace-prod/C11697DBG_remaining-blockers.md`), Leg 3 never re-run → final.vm
  still all `$TBD_*`.
- Fonts used by the doc: Cambria, Calibri, Lato, Futura — none PDF-standard.

## Milestones (each renders something real)

- **M1 — skeleton renders live**: the 8 plain fields (policyholder block, policy
  number, dates) render on a real quote. No conditionals. Proves tenant + plugin +
  quote + endpoint end to end.
- **M2 — state-driven text**: the ~32 `account.data.policyHolderState` conditionals
  (fraud warnings) fire. Requires Blocker B (account condition root) built in the
  pipeline.
- **M3 — benefit schedule**: the per-Risk/per-benefit rows. Requires the Blocker A
  design decision (foreach loop vs plugin-bent booleans). Biggest lift; explicitly
  out of scope until M1+M2 hold.

## Phase 0 — decisions (Josh, blocking)

1. **Tenant strategy** — recommended: a **second sandbox tenant** carrying the AIG
   reference config as-is. (Merging BlanketSpecialRisk into the ZenCover tenant's
   config tree means reconciling accounts/dataTypes/charges — high risk, no payoff.)
2. **Deploy mechanism** — Studio UI upload vs Config Deployments API with the PAT.
   Whatever produced `build/socotra-uploaded-datamodel.zip` before is fine.

## Phase 1 — config pre-flight (agents, parallel)

- **Agent A (lint)**: run `socotra-config-lint` over
  `workspace-prod/reference/socotra-config/`; fix only deploy-blocking findings.
- **Agent B (plugin inventory)**: check the reference config's `plugins/` — does it
  carry a RatePlugin (quote creation may need rating to succeed)? Report what must
  ship for a quote to reach a renderable state, using `socotra-jar-building-block`
  introspection on the reference jars.
- **Agent C (leg 3 re-run)**: apply the filled `path-review.csv`
  (`legminus1_apply`), re-run Leg 2+3 with the AIG registry → a skeleton
  `final.vm` where the 8 plain fields resolve (conditionals inert). Grep-gate:
  no bare `$data.data.` / `$data.<systemField>`. Then Leg 4 with
  `--customer-jar workspace-prod/reference/build/customer-config.jar
  --datamodel-jar workspace-prod/reference/build/core-datamodel-v1.7.71.jar
  --compile-check`.

## Phase 2 — deploy (Josh, manual; agent preps)

- Agent zips the config bundle + drops the generated
  `*DocumentDataSnapshotPluginImpl.java` into `plugins/java/` inside it.
- Josh uploads/deploys to the new tenant, records the new
  `AI_DOCUMENTS_TENANT_LOCATOR` (separate env file or suffixically-named vars —
  keep ZenCover's working set untouched).

## Phase 3 — test data (agent + Josh's PAT)

- **Agent D (test-builder)**: use `socotra-test-builder` to derive, mechanically
  from the config tree: an account create payload (policyholder + state — pick a
  fraud-warning state like NY so M2 has something to fire), and a quote create
  payload with 1–2 `Risk` exposures carrying a handful of benefit coverages
  (AD&D, AccidentMedicalExpense, Coma) with coverage terms set.
- Script the create calls, capture the **quote locator**, set
  `AI_DOCUMENTS_REFERENCE_QUOTE` for the AIG env.

## Phase 4 — M1 render + iterate

- `render_preview --template …C11697DBG(quote).final.vm --reference-type quote
  --reference-locator <new> --out … --open`.
- Iterate template-side only (hot-swap loop) until the 8 fields show real data.

## Phase 5 — fonts (parallel with 3/4)

- Leg 3 report now flags the four fonts. **Licensing**: Cambria/Calibri are
  Microsoft-licensed — don't upload those files; use metric-compatible open
  substitutes (Carlito ≈ Calibri, Caladea ≈ Cambria, both Google-made). Lato is
  OFL (free). Futura is commercial — substitute (e.g. Jost) or accept fallback.
- Declare names in config `customFonts` + the DocumentConfig, deploy, upload
  TTF/OTF via `addFont`, assign to a resource group.

## Phase 6 — M2 (pipeline dev, separate branch)

- **Agent E (Blocker B build)**: allow `account.*` as a condition-DSL root; typed
  account local + Map-access codegen in Leg 4. This is the highest-leverage
  tractable blocker (~32 of 89 blocks). Test fixture first
  (`TestAccountCondition(quote)`), then re-parse the AIG variants.csv.
- Blocker C (4 blocks: `not in`, `diffDays`, metadata indexing, bare `data.` root)
  — fold in here or defer; low count.

## Phase 7 — M3 decision gate (Josh + design session)

- Blocker A: benefit schedule as per-exposure `#foreach` + in-loop `#if` (template
  restructure) vs plugin-computed doc-scoped booleans (`benefitX_present`). Needs a
  design decision before any agent builds. Not scheduled.

## Execution log

- **2026-07-16 — Phases 1–2 DONE via API** (the PAT carries `deploy` +
  `create-tenant`, so no Studio needed). Bundle built in scratchpad from the
  reference config + two fixes: `"Deductible"`→`"deductible"` in
  coverageTerms/config.json, and one placeholder data row added to the
  header-only `bootstrap/resources/resourceFiles/tables/CatCashAdjustmentLookup_2017_50.csv`
  (table CSVs live under bootstrap/resources/resourceFiles/, NOT tables/<name>/).
  Hardened plugin baked into `plugins/java/`. `validateConfig` → 200.
- **Tenant `aig-bsr-dev` created**: locator `4a6c9ff6-3258-4fa0-a2d4-3959ac779580`,
  deploy success, `documentDataSnapshot` plugin registered
  (`BlanketSpecialRiskDocumentDataSnapshotPluginImpl`), bootstrap queued.
- `reversalTypes` absence: server accepted — non-issue.
- **2026-07-16 — M1 ACHIEVED.** `C11697DBG(quote).m1-preview.pdf` rendered via the
  real ad-hoc endpoint against quote `01KXN6ZCY8JBXR1BREMQBJD4DX`: policyholder
  name/address, effective + termination dates all live. Two fixes en route:
  1. **Platform strips empty-string values from renderingData** (JSON round-trip;
     confirmed via debug renders — `$data.quote` arrives as LinkedHashMap and
     `""` entries vanish, breaking strict mode). All 50 conditional stubs and the
     `.orElse("")` unwraps now use a single space `" "` instead. Redeployed via
     `POST /config/{tenant}/deployments/deploy` (version 01KXNJ7HPFMKF9AJ8V4F167H69).
  2. Template `${data.policyHolderAddress2}` repointed to
     `$!{data.quote.data.policyHolder.policyHolderAddress.address2}` (real CDT
     field; was riding a stub).
  Known-blank leftovers in the PDF, all expected: Policy Number (quote has none
  reserved), `{---}`/`{$---}` per-Risk fields (M3), `(formNumber)`/`(formDescription)`
  riders table (unconverted repeating table — M3 scope).

- **2026-07-16 — M2 ACHIEVED (and doc re-rooted to `(segment)`).** Josh renamed the
  input to `C11697DBG(segment).docx`; full pipeline re-run under the policy/segment
  rendering root. **Blocker B dissolved without new pipeline codegen**: ground truth
  is that the state does NOT live on the account — `PolicyholderData` has no
  `policyHolderState` field; the state is the product-data path
  `policy.data.policyHolder.policyHolderAddress.state` (AIG's own liquid templates
  read `data.data.policyHolder.policyHolderAddress.state`). The existing
  quote/policy condition DSL + jar-walk already handles that chain. What was done:
  1. `variants.csv` surgery (new stem `C11697DBG(segment).variants.csv`): 33
     `account.*` `when` cells rewritten to the product-data path **and state
     abbreviations translated to full names** ("NY"→"New York" — the tenant stores
     `fullStateName` per the States constraint table; abbreviations never match).
     40 Blocker-A/C blocks neutralized to default-only rows (render a single
     space); 39 orphaned nested-only label rows deleted (return with M3).
     Scripts in scratchpad; conditional registry now writes clean: **50 blocks,
     10 real conditions** (8 fraud warnings + address2 + UT/RI/TX/SC label).
  2. **Leg 4 codegen fix (pipeline, durable)**: all five `""` puts/initializers
     for conditional keys now emit `" "` — the platform strips empty-string
     renderingData values (M1 lesson) so a false condition no longer kills strict
     mode. Test suite: all 11 fixtures + plugin generation PASS.
  3. Plugin regenerated fresh for the segment stem (policy overload, compile
     PASS). Hand-hardening now minimal: a `policyView` wrapper (policyNumber
     `.orElse(" ")`, start/end `Instant` → MM/dd/yyyy UTC) + the address2
     variant-text accessor (registry lacks nested-CDT rows so Leg 4 can't wire
     variant-text leaves — known gap). Backup `.java.bak`. Unbacked-ref check:
     52 template keys, 0 unbacked.
  4. **Deploy is now scripted**: `tools/aig_deploy_bundle.py` rebuilds the M1
     bundle durably (reference config + the two fixes + current plugin →
     validate → deploy). Deployed version `01KXNKVTJJ7BKTE6F06MAH923V`.
  5. Quote `01KXN6ZCY8JBXR1BREMQBJD4DX` **accepted + issued** → policy (same
     locator; policyNumber `SRG 0000000000`). Rendered via
     `--reference-type policy` → `C11697DBG(segment).m2-preview.pdf`: NY fraud
     warning renders with real text; other states' warnings blank; policy number
     + formatted dates live. `{---}` per-Risk fields and the riders table remain
     M3 scope.

- **2026-07-16 — M3 ACHIEVED (benefit schedule renders live).** Josh's decision:
  marker machinery, not plugin booleans. Chain (all steps scripted in
  `workspace-prod/restructure_benefit_schedule.py` — apply/revert/fill/
  patch-mapping/patch-vm):
  1. **Pipeline features built first** (tested, in-tree): in-loop `[Name?]` VALUE
     regions (per-item conditions → template `#if` via `condition_to_velocity`;
     Leg 4 skips) and repeated-`[[$token]]` dedupe (shared state labels).
  2. **Doc restructured**: section 2.A wrapped in `[Risk/]`; 36 benefit tokens →
     `[Cov?]` presence regions (single-flavor) / `[token?]` value regions keyed on
     the config's type fields (PTD×3, FA×2, SB×2 — our reference config has ONE
     coverage per family + a type field, unlike AIG prod's separate elements);
     sub-limits → nested value regions; CSV texts moved into the body with leaves
     resolved via exact/term/fuzzy/token-set matching + LEAF_OVERRIDES. 9 punts
     (fields absent in this config / mixed scope) stay neutralized markers.
  3. **`embedTrueTypeFonts` stripped in Leg 0 Stage A** (durable fix): the
     customer doc's settings.xml flag made LibreOffice base64-embed local fonts
     into the XHTML → "huge text node" hard fail.
  4. **renderingData casing contract discovered (live keySet() debug):** the JSON
     round-trip serializes coverage keys **lowerCamel** (`$risk.coma`, NOT the
     registry's `$risk.Coma`) and coverage TERMS as plain values (**no `.value`
     hop**). Registry velocities are wrong live — `--patch-vm` rewrites the
     final.vm post-Leg 3 as a stopgap. **Follow-up: pipeline-wide casing fix**
     (registry velocities, extract_loops guards, condition_to_velocity) — this
     also means ZenCover's CoverGrid demo guards (`#if($item.Breakdown)`) never
     matched live: the "blank guarded cells" in that proof PDF were this bug.
  5. Plugin updated ADDITIVELY (M2 policyView hardening kept, compile PASS,
     0 unbacked refs), deployed version `01KXP4HWG8N1NH7HW00EQP3YBY`, rendered
     `C11697DBG(segment).m3-preview.pdf` vs policy `01KXN6ZCY8JBXR1BREMQBJD4DX`:
     CLASS(ES) Class A, AD 50000, AME 25000 + Dental sub-limit value regions
     firing, Coma $10000; all 33 unattached benefits hidden.
  Cosmetic leftovers: `$$` double currency where authored `$` meets a
  `$`-formatted value; AME "Note:" lines render outside their hidden sub-regions
  (authored layout). Riders table (formNumber/formDescription) still open —
  needs a name→form lookup design. Mapping patch (`--patch-mapping`) re-applies
  the 7 policyholder/date data_sources after any re-ingest.

## Sequencing

Phase 1 agents run in parallel today. Phase 2–4 need Josh's Phase-0 decisions.
Phase 5 parallel. Phase 6 independent of 2–4 (pipeline-side). M1 is achievable
without any pipeline code changes.

## Phase 3 — test data (2026-07-16, DONE)

Seeded via `tools/aig_dev_tenant_seed.py` (re-runnable; derives every value from
the reference config tree + bootstrap constraint-table CSVs; reads
`.env.ai-documents` for API URL + PAT, tenant locator pinned in-script).

- **Tenant**: `4a6c9ff6-3258-4fa0-a2d4-3959ac779580` (aig-bsr-dev)
- **Account locator**: `01KXN6ZBT905NJZNW11J9YRKF5` (PolicyholderData,
  "Test Policyholder Inc", address state "New York" — the States constraint
  column is `fullStateName`, so "NY" the abbreviation is not a legal value)
- **Quote locator**: `01KXN6ZCY8JBXR1BREMQBJD4DX` — state **priced** ($0, no
  RatePlugin, as expected). Term 2026-08-01 → 2027-08-01.
- Quote data carries `policyHolder` (name + nested policyHolderAddress:
  123 Test Street / New York / New York / 10001) for the M1 template reads.
- 1 `Risk` exposure (riskClass `Class A  (Base Premium Factor = 0.02)` — the
  field is constrained to the RiskClasses table, so a bare "1" is illegal)
  carrying AD&D (AccidentalDeathMaximumAmount 50000), AccidentMedicalExpense
  (AccidentMedicalExpenseAmount 25000), Coma (ComaMaximumAmount 10000).
- All required elements present: PermissibleLoss (bare ref = required),
  PolicyAdjustmentFactor, GeneralExclusions, Limitations, Injury,
  RightToTermination, BeneficiaryDetails.
- Gotchas learned: account must be PATCH-validated before quote create
  (errorCode 212002); response element types carry a `Quote` suffix
  (`RiskQuote` etc.); no bootstrap-pending errors were hit.
- Use `01KXN6ZCY8JBXR1BREMQBJD4DX` as `AI_DOCUMENTS_REFERENCE_QUOTE` in the
  AIG env file for Phase 4 (do not edit the ZenCover `.env.ai-documents`).
