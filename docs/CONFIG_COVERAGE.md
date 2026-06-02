# CONFIG_COVERAGE.md — Socotra config feature coverage

**Status:** Living matrix. Seeded in session B1 (2026-04-22) against
`socotra-config/CommercialAuto`. Every PR that touches
`.cursor/skills/mapping-suggester/scripts/extract_paths.py` or
`.cursor/skills/mapping-suggester/SKILL.md` MUST review and update the
rows whose "Handled in SKILL today?" status would change, per the
governance rule in §5 below.

## 1. Purpose

This matrix enumerates every Socotra configuration feature the pipeline
must eventually handle. For each feature it records:

- whether the feature is **present today** in the local
  `socotra-config/` tree (`In CommercialAuto?`);
- whether the registry (`registry/path-registry.yaml`) **captures** the feature's shape
  (`In registry today?`);
- whether the mapping-suggester has a **specific matching rule** for it
  (`Handled in SKILL today?`);
- a pointer to the conformance **fixture** that exercises the feature
  (Phase C; not yet written);
- freeform **Notes** linking to Socotra Buddy corpus files or live
  sample evidence.

Most rows are "no" today, and that is expected. The matrix is a roadmap,
not a scorecard. A "no" row is a contract that the pipeline will NOT
silently invent behaviour for that feature — when the feature appears
in the wild, the shape probe surfaces it as `needs-skill-update` in
`<stem>.review.md` and the next agent extends both this matrix and the
skill in the same PR.

## 2. Legend

- **In CommercialAuto?** — `yes` / `no` / `partial` / `n/a`. Derived from
  a structural scan of `socotra-config/` (same scan
  `extract_paths.py → detect_features()` runs). `partial` means the
  feature is used but not in every place a richer tenant would use it.
- **In registry today?** — `yes` / `partial` / `no`. `partial` means the
  feature is emitted in a degraded form (e.g. CDTs are not walked
  recursively; only a `custom_type_ref` stub is surfaced).
- **Handled in SKILL today?** — `yes` / `partial` / `no`. `partial`
  means the suggester respects the feature when it happens to appear
  (e.g. via generic quantifier rules) but has no dedicated logic.
- **`feature_support` flag** — the name of the flag in the registry's
  `feature_support:` block, when one exists. `—` when the feature has
  no dedicated flag (either because it's always present, like
  policy-level charges, or because Phase B deliberately left it out).
- **Fixture path** — `conformance/fixtures/<name>/`, populated in Phase C.
- **Notes** — live evidence: corpus files, sample reviews, open
  questions.

## 3. Socotra config feature matrix

### 3.1 Quantifiers on exposure `contents`

| # | Feature | Example token | In CommercialAuto? | In registry today? | Handled in SKILL today? | `feature_support` flag | Fixture path | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | Exposure quantifier `+` (one-or-more, iterable) | `"Vehicle+"` | yes | yes (iterables-index + `quantifier: +`) | yes (Rule 1 — loop match) | — | `conformance/fixtures/all-quantifiers/` (C1, 2026-04-22) | CommercialAuto has `contents: ["Vehicle+", "Driver+"]`. Every `+` exposure shows up in the top-level `iterables:` index with `cardinality: one_or_more`. Fixture exercises via Vehicle+ → $data.vehicles loop (high-confidence Rule 1 match). |
| 2 | Exposure quantifier `*` (any, iterable) | `"Vehicle*"` | no | yes (same code path as `+`) | yes (same rule path as `+`) | — | `conformance/fixtures/all-quantifiers/` (C1, 2026-04-22) | Distinction between `+` and `*` collapses in a document template (both render via the same `#foreach`); `cardinality` differs in the registry but no SKILL rule branches on it today. Fixture exercises via Driver* → $data.drivers loop. |
| 3 | Exposure quantifier `?` (zero-or-one, not iterable) | `"SecondVehicle?"` | no | yes (emitted with `quantifier: '?'`, `iterable: false`) | partial (Rule 4 optional-element guard fires if a field on this exposure is matched) | — | `conformance/fixtures/all-quantifiers/` (C1, 2026-04-22 — registry shape only; no placeholder) | No CommercialAuto exposure uses `?`; unusual pattern — typically coverages use `?`, not exposures. The C1 fixture carries `Addon?` on the product contents purely to verify the registry emits `quantifier: '?'`, `iterable: false` on an exposure; no mapping placeholder exercises it end-to-end yet. |
| 4 | Exposure quantifier `!` (exactly-one, auto-created) | `"Driver!"` | no | yes (emitted with `quantifier: '!'`) | partial (Rule 5 auto-element note fires on matched fields; no exposure-level branch) | `auto_elements` | `conformance/fixtures/all-quantifiers/` (C1, 2026-04-22 — registry shape + `auto_elements` flag proven via `SpecialUnit!` + `Comp!`) | `!` commonly appears on coverages; on an exposure it's rare. The flag is a single bit — it fires for a `!` anywhere (exposure contents, coverage contents, or data-extension type). Fixture proves `auto_elements: true` does NOT trigger the refusal rule (rule-supported whitelist). |
| 5 | Exposure no-suffix (exactly one, not iterable) | `"Policyholder"` | no | yes (emitted with `quantifier: ''`) | partial (matchable by field name; scope rules assume no-foreach) | — | `conformance/fixtures/minimal/` (C1, 2026-04-22) + `conformance/fixtures/all-quantifiers/` (C1) + `conformance/fixtures/no-exposures/` (C4, 2026-04-22 — absence-of-exposure regression) | `extract_paths.py` still walks the exposure and emits its fields under a `requires_scope: [#foreach ...]` branch that mirrors `+`/`*` exposures (i.e. no-suffix and iterable share the same scope contract). `minimal/` is the canonical regression — its `vehicle_vin` placeholder proves Rule 2 step 4 fires (low + restructure-template) when a scope signal is missing. `no-exposures/` (added C4) is the complement: proves `build_registry()` emits `iterables: []` and `exposures: []` cleanly when `product.contents: []` and no `exposures/` directory exists, and that variables-only mappings resolve at `high` without touching the iterables index. Together the three fixtures lock down all three structural cases (`+`-quantified iterable, no-suffix exposure with scope, no exposures at all). |

### 3.2 Quantifiers on coverage `contents`

| # | Feature | Example token | In CommercialAuto? | In registry today? | Handled in SKILL today? | `feature_support` flag | Fixture path | Notes |
|---|---|---|---|---|---|---|---|---|
| 6 | Coverage quantifier `?` (zero-or-one, needs `#if` guard) | `"MedPay?"` | yes (`MedPay?`, `Umbi?`, `Umpd?` on Vehicle) | yes (coverage block carries `quantifier: '?'`) | yes (Rule 4 optional-element guard) | — | `conformance/fixtures/all-quantifiers/` (C1, 2026-04-22) | Live evidence: `socotra-config/exposures/Vehicle/config.json` `contents` list. Rule 4 appends the `#if(...)` guidance to `reasoning` on matched fields. Fixture exercises via `medpay_limit` loop-field (high confidence + Rule 4 guard note). |
| 7 | Coverage quantifier `!` (auto-created) | `"collision!"` | no | yes (emitted with `quantifier: '!'`) | yes (Rule 5 auto-element note) | `auto_elements` | `conformance/fixtures/all-quantifiers/` (C1, 2026-04-22) | Same flag as exposure-side `!` (row 4) — the scan is a single pass over all `contents` / `type` tokens. Fixture exercises via `comp_limit` loop-field (high confidence + Rule 5 auto-element note). |
| 8 | Coverage no-suffix (exactly one) | `"Coll"` | yes (`Coll`, `Comp`, `Liability` on Vehicle) | yes | yes (Rule 1 special-case for coverage loops; Rule 2 for scoped field access) | — | `conformance/fixtures/all-quantifiers/` (C1, 2026-04-22) + `conformance/fixtures/minimal/` (C1, 2026-04-22 — exposure no-suffix baseline) | Live evidence: `socotra-config/coverages/Coll/config.json` (no suffix on the Vehicle `contents` token). `all-quantifiers/` exercises the exact shape via `coll_deductible` (high confidence, no Rule 4/5 note); `minimal/` covers the no-suffix contract at the exposure level. |
| 9 | Coverage with `coverageTerms: [...]` | `coverageTerms: [{ name: "deductible", options: […] }]` | no | no (extractor never reads `coverageTerms`) | no | `coverage_terms` | `conformance/fixtures/coverage-terms/` (C4, 2026-04-22) | No CommercialAuto coverage has a `coverageTerms` key (greps for `coverageTerms` return zero hits under `socotra-config/`). When this flag flips `true`, the shape probe MUST surface a `needs-skill-update` row — §4's refusal rule is the contract. C4 fixture uses `Flood.coverageTerms[deductible].options: ["250", "*500", "1000"]`; the coverage's `data.effectiveDate` field still emits cleanly (proves the extractor walks `data` independently of `coverageTerms`), while `flood_deductible` — the placeholder whose resolution would require reading the term — downgrades to `low` + `needs-skill-update: coverage_terms / default_option_prefix refusal`. |
| 10 | Coverage term with default-option prefix `*value` | `options: ["500", "*1000", "2000"]` | no | no (depends on row 9 first) | no | `default_option_prefix` | `conformance/fixtures/coverage-terms/` (C4, 2026-04-22) | Only meaningful if `coverage_terms` is true. Flag scans every term's `options` list for a leading `*`. C4 fixture exercises both flags together via `"*500"` in the `deductible` term's options list; proves the two flags co-fire cleanly and surface as two separate §7 Unrecognised-inputs rows (alphabetical: `coverage_terms`, `default_option_prefix`) with a single combined `needs-skill-update` on the affected placeholder — mirroring the `nested-iterables/` three-flag co-fire convention. |

### 3.3 Quantifiers on data-extension `type`

| # | Feature | Example token | In CommercialAuto? | In registry today? | Handled in SKILL today? | `feature_support` flag | Fixture path | Notes |
|---|---|---|---|---|---|---|---|---|
| 11 | Data-extension scalar `?` (zero-or-one) | `"type": "string?"` | yes (`garagingAddress2`, account `mailingAddress2`) | yes (quantifier preserved on every field entry) | yes (Rule 4 optional-element guard) | — | `conformance/fixtures/all-quantifiers/` (C1, 2026-04-22) | Live evidence: `socotra-config/products/CommercialAuto/config.json` line 26 and `socotra-config/accounts/ConsumerAccount/config.json` line 21. Fixture exercises via the product's `refNumber: {type: string?}` field matched by `ref_number` placeholder (high confidence + Rule 4 guard note). |
| 12 | Data-extension array `+` of primitive | `"type": "string+"` | no | partial (flattened into a single entry with `iterable: true`; **no inner-foreach `requires_scope` step is added**) | no (generic flatten only; no scoped matching rule) | `array_data_extensions` | `conformance/fixtures/nested-iterables/` (C2, 2026-04-22 — partial: shared flag path via `Owner+`) | `extract_paths.py` docstring explicitly defers "expand recursively"; an inner `#foreach` is NOT required today because the flattened entry is treated as a scalar-array reference. Refusal rule applies when the flag flips on — see §4. The C2 `nested-iterables/` fixture exercises the same `array_data_extensions` detection code path (line 476 of `extract_paths.py` — any iterable quantifier on a data-extension type fires the flag regardless of primitive vs CDT base), so the flag-flip + refusal behaviour is regression-covered. A dedicated primitive-array fixture (`"type": "string+"` or `"int*"`) would add strictly no new detection logic; track as satisfied-by-proxy and revisit only if a future `array_data_extensions` scope-walker distinguishes primitive from CDT arrays. |
| 13 | Data-extension array `*` of primitive | `"type": "int*"` | no | partial (same as row 12) | no | `array_data_extensions` | `conformance/fixtures/nested-iterables/` (C2, 2026-04-22 — partial: shared flag path) | Same flag + same caveat as row 12; only the cardinality differs. Coverage rationale identical to row 12's — the `+` and `*` branches of `parse_quantified_token` both map to `ITERABLE_QUANTIFIERS` and hit the same `array_data_extensions = True` line, so the C2 `nested-iterables/` fixture regressions both by shared code path. |
| 14 | Data-extension array of custom data type | `"type": "Driver+"` | no | partial (emits `custom_type_ref: Driver` + `iterable: true` but does NOT walk Driver's `data` map from this reference; a second foreach is NOT added to `requires_scope`) | no | `nested_iterables` | `conformance/fixtures/nested-iterables/` (C2, 2026-04-22) | This is the richest case: a proper fix needs (a) recursive CDT walk, (b) a second `#foreach` pushed into the nested entries' `requires_scope`, (c) SKILL Rule 2 extension to match through the extra scope. Live example from the mirrored docs (see Notes in row 15). C2 fixture uses `Vehicle.owners: Owner+` — `nested_iterables: true`, `custom_data_types: true`, and `array_data_extensions: true` all flip together; `owners` loop-field gets `low` + `needs-skill-update` with three separate §7 rows (one per refusal flag); the unaffected `vehicle_vin` placeholder stays `high`. |

### 3.4 Custom data types

| # | Feature | Example | In CommercialAuto? | In registry today? | Handled in SKILL today? | `feature_support` flag | Fixture path | Notes |
|---|---|---|---|---|---|---|---|---|
| 15 | Custom data type (flat) | `customDataTypes/Address/config.json` with scalar `data` fields | no (no `customDataTypes/` dir) | no | no | `custom_data_types` | `conformance/fixtures/cdt-flat/` (C2, 2026-04-22) | Socotra Buddy corpus has examples under `~/socotra-buddy/resources/derived/` — the B2 agent greps `manifest.json` for `customDataTypes.html` to find the canonical shape. C2 fixture uses `Policyholder.dwellingAddress: Address` (scalar CDT reference); proves `custom_data_types: true` flips via `_iter_subdir_configs(customDataTypes)` and that the CDT's own `street` / `city` / `postalCode` fields are **not** emitted as addressable paths (expansion is intentionally deferred per `extract_paths.py` line 181–186). The `dwelling_address` loop-field is downgraded to `low` + `needs-skill-update`; unaffected entries stay `high`. |
| 16 | CDT references another CDT | `Address` contains `nestedAddress: { type: "Address" }` (non-recursive chain) | no | no | no | `custom_data_types` | `conformance/fixtures/cdt-flat/` (C2, 2026-04-22 — partial: detection-only) | No dedicated flag; `custom_data_types` is true if any CDT parses. Chain depth is a runtime concern for the scope-walker. Detection + refusal machinery is identical to row 15 (both flip `custom_data_types: true` via the same `_iter_subdir_configs` scan). A dedicated fixture with a CDT-to-CDT chain (e.g. `Address.billingAddress: BillingAddress`) adds no new flag logic until the CDT walker lands; track as detection-satisfied and revisit when Phase C/D's CDT-aware scope walker is authored. |
| 17 | CDT recursive (self-reference) | `Address` contains `subAddress: { type: "Address?" }` | no | no | no | `recursive_cdts` | `conformance/fixtures/cdt-recursive/` (C2, 2026-04-22) | Detection: `detect_features` checks every CDT's data map for a field whose `base_type` equals the CDT's own name. Rex territory — once this flag flips `true`, the suggester must refuse to match anything depending on it until a recursion-safe walker lands. C2 fixture uses `Address.subAddress: Address?` — proves `recursive_cdts: true` flips even through a `?` quantifier (the equality check in `extract_paths.py` line 435 compares base-type only), and that `custom_data_types` + `recursive_cdts` co-fire cleanly (two separate §7 rows, one combined `needs-skill-update` on the affected field). |

### 3.5 Product-structure variants

| # | Feature | Example | In CommercialAuto? | In registry today? | Handled in SKILL today? | `feature_support` flag | Fixture path | Notes |
|---|---|---|---|---|---|---|---|---|
| 18 | Peril-based product structure | `perils/<Name>/config.json` grouping instead of `coverages/` | no (no `perils/` dir) | no | no | `peril_based` | `conformance/fixtures/peril-based/` (deferred, C3 2026-04-22 — swapped for `jurisdictional-exclusive/`) | Session C3 reality-checked the `perils/` pattern against `~/socotra-buddy/resources/derived/`: the only hit for "peril" (`125949463fad41f0.md`, the quantifiers page) uses the word conversationally to describe coverages like comprehensive / collision, NOT to describe a `perils/<Name>/config.json` directory layout. Per the C3 handoff block in `.cursor/plans/pipeline-improvements/CompletedPlans/alpha-beta-plan/PIPELINE_EVOLUTION_PLAN.md`, the peril-based fixture was swapped for a second jurisdictional variant (`jurisdictional-exclusive/`, row 19). `peril_based` detection code (`extract_paths.py` lines 417–419) stays in place and the flag remains in the refusal vocabulary; fixture coverage waits for either a docs citation or a live customer sample. Do NOT invent this row's behaviour without a source. |
| 19 | Jurisdictional qualifier on coverage | `"qualification": {...}`, `"appliesTo": ["claim"]`, `"exclusive": true` | no (zero hits under `socotra-config/`) | no | no | `jurisdictional_scopes` | `conformance/fixtures/jurisdictional/` (C3, 2026-04-22) + `conformance/fixtures/jurisdictional-exclusive/` (C3, 2026-04-22) | Flag scans both coverage configs and the product config for any of the three keys via `any(...)` at `extract_paths.py` line 455 (coverages) / 458 (product). Fixture pair splits regression coverage across all three keys: `jurisdictional/` exercises `qualification` on a Collision coverage; `jurisdictional-exclusive/` carries BOTH `exclusive: true` AND `appliesTo: ["claim"]` on an Umbrella coverage (one fixture covers two of the three keys + proves `any(...)` short-circuits correctly — still a single §7 row despite two contributing keys). Refusal path: any loop field that traverses a jurisdictional coverage downgrades to `low` + `needs-skill-update: jurisdictional_scopes refusal`; non-jurisdictional placeholders (system paths, iterable loop heads, plain exposure fields) stay `high`. |
| 20 | Multi-product config tree | two or more subdirs under `products/` | no (only `CommercialAuto/`) | partial (extractor picks the alphabetically-first product dir; a multi-product config would silently drop the rest) | no | `multi_product` | `conformance/fixtures/multi-product/` (C3, 2026-04-22) | Detection: `len([d for d in products/ if d.is_dir()]) > 1`. Session C3 also added a deterministic sort to `build_registry()` (`sorted(..., key=lambda d: d.name)` replacing the raw `iterdir()` iteration) so the "picks first" selection is reproducible across filesystems rather than iterdir-order-dependent; the fixture's goldens depend on this. Fixture exercises both halves of the contract: AutoLine is selected (A < H alphabetically), HomeLine silently dropped, `roof_material` variable (a cross-product placeholder with no candidate in AutoLine's registry) downgrades to `low` + `needs-skill-update: multi_product refusal` per `CONFIG_COVERAGE.md` §4; system / AutoLine-scoped matches stay `high`. When the flag flips, the suggester must refuse to match cross-product paths until the skill is extended to accept a `--product <name>` argument (or merged-registry mode). |
| 21 | Non-`$data` root object (plugin-supplied `renderingData`) | plugin returns `{customer: {...}, vehicles: [...]}` instead of `$data.*` | no (no plugin return-shape descriptor found in `socotra-config/`) | no (registry hard-codes `$data` as the root) | no | — (Phase B deliberately did not flag this — it's a runtime template concern, not a config one) | `conformance/fixtures/no-exposures/` (C4, 2026-04-22 — partial / indirect) | Flagged for B2 / C: decide whether this deserves its own flag or stays an out-of-band runtime concern. Current contract assumes `$data` is the one-and-only root. C4 `no-exposures/` fixture keeps the `$data` root but stresses the "everything flat on the policy / account" shape that a plugin-flattened template would mirror — a direct regression for the non-root case still needs a dedicated fixture once B2 decides whether to carve out a flag for it. |

### 3.6 Charges and documents

| # | Feature | Example | In CommercialAuto? | In registry today? | Handled in SKILL today? | `feature_support` flag | Fixture path | Notes |
|---|---|---|---|---|---|---|---|---|
| 22 | Policy-level charges | product `config.json` → `"charges": ["GoodCustomerDiscount", ...]` | yes (4 charges: `GoodCustomerDiscount`, `GoodDriverDiscount`, `ServiceFee`, `InceptionFee`) | yes (`policy_charges:` list with `velocity_amount` / `velocity_object`) | yes (Rule 6 charge-path disambiguation) | — | `conformance/fixtures/minimal/` (pending) | Always present; no flag needed. |
| 23 | Coverage-level charges | coverage `config.json` → `"charges": ["premium"]` | yes (`premium` on Coll / Comp / Liability / MedPay / Umbi / Umpd) | yes (under each coverage's `charges:` list) | yes (Rule 6) | — | `conformance/fixtures/minimal/` (pending) | Always present when any coverage has a `charges:` array. |
| 24 | Document attachment config | product `config.json` → `"documents": ["<Name>", ...]` with matching `documents/<Name>/` directory | yes (`BusinessAutoCoverageForm_CA_00_01`, `Summary`) | no (extractor does not surface the `documents:` list) | no (template generation is Leg 1's domain, not the suggester's) | — | — | The suggester doesn't need this, but `CONFIG_COVERAGE.md` tracks it because Phase C / D telemetry may want to cross-reference document names against the `source:` of each mapping YAML. |

### 3.7 Account-type variation

| # | Feature | Example | In CommercialAuto? | In registry today? | Handled in SKILL today? | `feature_support` flag | Fixture path | Notes |
|---|---|---|---|---|---|---|---|---|
| 25 | Account type variation (ConsumerAccount vs BusinessAccount) | `accounts/ConsumerAccount/`, `accounts/BusinessAccount/` | partial (only `ConsumerAccount/`; no `BusinessAccount/`) | partial (registry's `account_paths` are hard-coded to a fixed set of 9 strings in `build_registry()`, independent of what `accounts/` actually defines) | no | — | `conformance/fixtures/cdt-flat/` partially exercises via `Address` (pending) | Real gap: `extract_paths.py` ignores the actual `accounts/<Type>/config.json` and emits a hand-curated list. Fixing this is explicitly Phase C / D scope. Not a `feature_support` flag yet — flagged here so the next agent sees the gap. |
| 26 | Segment / transaction data access | `$data.transaction.*` / `$data.segment.*` (cross-segment / cross-transaction data) | no (no segment or transaction references in the product config) | no | no | — | — | Socotra Buddy corpus has the canonical semantics; B2 is responsible for confirming whether this belongs in the registry or in a downstream plugin shape. |

## 4. Refusal rule — `feature_support` flag flips on, SKILL rule missing

When `extract_paths.py` emits `feature_support.<flag>: true` **and** the
mapping-suggester does not have a matching rule for that flag (see the
"Handled in SKILL today?" column above), the suggester MUST:

1. Surface a row in the `<stem>.review.md` **Unrecognised inputs**
   section (§7) with `next_action: needs-skill-update: <flag> is true
   but SKILL has no rule; extend or refuse`.
2. NOT attempt a match that depends on the unsupported feature. If the
   registry happens to emit a matchable shape (e.g. a flattened
   `array_data_extensions` entry), set `confidence: low` and pair with
   `next_action: needs-skill-update` — do not silently emit a `high`
   match.
3. Continue to emit the `.suggested.yaml` and `.review.md` artifacts;
   the refusal is per-variable/loop, not a whole-run halt.

The Step 2a shape probe in
`.cursor/skills/mapping-suggester/SKILL.md` enumerates every flag the
registry carries and checks them against the SKILL's "supported flags"
whitelist. The whitelist today (session B1, mapping-suggester v1.0):

- **Rule-supported flags** (no refusal when `true`): `auto_elements`
  (Rule 5 handles the note), `array_data_extensions` (partial — see
  rows 12 / 13; flag true emits a low-confidence `needs-skill-update`
  row because no dedicated scope-walker exists yet).
- **Refusal flags** (surface `needs-skill-update` when `true`):
  `nested_iterables`, `custom_data_types`, `recursive_cdts`,
  `jurisdictional_scopes`, `peril_based`, `multi_product`,
  `coverage_terms`, `default_option_prefix`.

Every CommercialAuto flag today is `false`, so no refusal fires in the
current regression run. The rule is dormant but contractually in place.

## 5. Governance rule (from .cursor/plans/pipeline-improvements/CompletedPlans/alpha-beta-plan/PIPELINE_EVOLUTION_PLAN.md §3.3)

Every PR that touches
`.cursor/skills/mapping-suggester/scripts/extract_paths.py` or
`.cursor/skills/mapping-suggester/SKILL.md` MUST:

1. Review this matrix for any row whose "Handled in SKILL today?"
   status would change.
2. Update the row (including the `feature_support` flag column when
   adding or renaming a flag).
3. Add or update the corresponding fixture under `conformance/fixtures/`
   (Phase C — not yet scaffolded; reference the target fixture path
   from the matrix row so the Phase C agent knows where to land it).

An agent extending the matrix MUST cite a source for every new row:
either a concrete file under `socotra-config/`, a Socotra Buddy corpus
file under `~/socotra-buddy/resources/derived/`, or a prior review
artifact that surfaced the feature as `needs-skill-update`. Silent
row additions (without a source) are forbidden and must be reverted —
see `.cursor/plans/pipeline-improvements/CompletedPlans/alpha-beta-plan/PIPELINE_EVOLUTION_PLAN.md` §8: "A new Socotra config feature is
observed in the wild that doesn't appear in `CONFIG_COVERAGE.md` — do
not silently add a row; confirm the feature exists in the mirrored
docs first."

## 6. Cross-leg vocabulary pending promotion

Separate from the socotra-config feature matrix above, this section
tracks **Leg 1 mapping-YAML signals** that the shape probe has flagged
as `needs-skill-update` and that are candidates for promotion into the
v1.x contract in `SCHEMA.md` / SKILL.md. These aren't features of
`socotra-config/`; they're signals emitted by the HTML → Leg 1
converter that the suggester does not yet know how to reason about.

| # | Signal | Source artifact | First seen | Current handling | Proposed resolution |
|---|---|---|---|---|---|
| L1 | `context.nearest_heading` on loop entries | `<stem>.mapping.yaml` (Leg 1) | session A2 (`claim-form.review.md`) and session A3 (`policy-template.review.md`) | Preserved pass-through; surfaced in §7 Unrecognised inputs with `next_action: needs-skill-update` | Either promote to v1.1 of the mapping contract (recognise `nearest_heading` on loop entries as equivalent in spirit to `nearest_label` on variables) **or** rename the Leg 1 emitter so loops use `nearest_label` like variables do. Decision deferred to a future `SKILL.md` + `SCHEMA.md` edit that bumps MINOR to 1.1; not in B1 / B2 scope. Live evidence: 1 loop on `claim-form` (4 foreach loops, all four emit the key), 7 of 9 loops on `policy-template`. |

Promotion is gated by the same governance rule in §5: an agent
promoting a signal MUST update `SCHEMA.md` (bumping the mapping YAML's
MINOR), the recognised-signals table in
`.cursor/skills/mapping-suggester/SKILL.md`, and this section (move
the row out with a changelog note pointing at the release).

## 7. Change log

- **2026-04-22 — Session C4** — Three remaining Phase C seed fixtures
  landed: `conformance/fixtures/no-exposures/`,
  `conformance/fixtures/custom-naming/`, and
  `conformance/fixtures/coverage-terms/`. Fixture path cells updated on
  rows 5, 9, 10, and 21. Rows 9 (`coverage_terms`) and 10
  (`default_option_prefix`) — the last two refusal flags awaiting a
  live `true` observation (per the C3 changelog entry) — are now
  directly covered by `coverage-terms/`; the two flags co-fire
  cleanly (same pattern as `nested-iterables/`'s three-flag
  co-fire) and surface as two separate §7 Unrecognised-inputs rows
  with a single combined `needs-skill-update` on the affected
  placeholder. Row 5 (`Exposure no-suffix`) now points at
  `no-exposures/` in addition to `minimal/` + `all-quantifiers/`,
  locking down all three structural cases (`+`-quantified
  iterable, no-suffix-with-scope, no-exposures-at-all). Row 21
  (non-`$data` root) gains a partial/indirect pointer at
  `no-exposures/` (proxy for the flat-on-policy shape; a direct
  regression for non-`$data` roots still needs a dedicated fixture
  once B2 decides whether to carve out a flag for it).
  `custom-naming/` was authored without a dedicated matrix row —
  it's the pre-Phase-E regression anchor for Rule 1's strict
  name-match, exercising the `Octopus` → `$data.octopus`
  pluralisation edge case. Refusal-flag coverage status after C4:
  seven of the eight refusal flags now have a `true`-in-a-fixture
  observation (`nested_iterables`, `custom_data_types`,
  `recursive_cdts`, `array_data_extensions` from C2;
  `jurisdictional_scopes`, `multi_product` from C3;
  `coverage_terms`, `default_option_prefix` from C4). The eighth
  (`peril_based`) remains deferred pending a docs citation or live
  customer sample, per the C3 corpus-grep outcome. C4 did not
  need a Leg 2 suggester run (goldens authored by direct
  rule-application; same precedent as C1 / C2 / C3) —
  `extract_paths.py` was invoked three times, once per fixture,
  and the three generated registries were promoted to goldens
  verbatim. `conformance/run-conformance.py` passes on all 11 current
  fixtures (registry: 11/11 pass; suggested+review: 2/11 pass as
  before — `minimal/` + `all-quantifiers/` — 9/11 skipped because
  the C2–C4 fixtures have no `actual/suggested.yaml`). Phase C's
  §4.4 acceptance criteria remain unticked; C5 is the closing
  session (runner wiring into `.cursor/plans/pipeline-improvements/CompletedPlans/alpha-beta-plan/PIPELINE_IMPROVEMENTS_PLAN.md` §6
  + tick all four §4.4 boxes + status-line update).
- **2026-04-22 — Session B1** — Initial matrix seed: 26 rows covering
  §3.1–§3.7 plus 1 cross-leg signal in §6. All 10 `feature_support`
  flags determined to be `false` against CommercialAuto by
  `extract_paths.py → detect_features()`. Refusal rule documented in
  §4; governance rule documented in §5 (verbatim from
  `.cursor/plans/pipeline-improvements/CompletedPlans/alpha-beta-plan/PIPELINE_EVOLUTION_PLAN.md` §3.3). Fixture paths are placeholders;
  Phase C is responsible for creating each referenced directory under
  `conformance/fixtures/`.
- **2026-04-22 — Session C3** — Three product-structure-variant Phase C
  fixtures landed: `conformance/fixtures/multi-product/`,
  `conformance/fixtures/jurisdictional/`, and
  `conformance/fixtures/jurisdictional-exclusive/`. Fixture path cells
  updated on rows 18, 19, and 20. Row 20 (`multi_product`) and row 19
  (`jurisdictional_scopes`) are now direct coverage. Row 18
  (`peril_based`) is flagged as **deferred** — the C3 agent
  reality-checked the `perils/<Name>/config.json` pattern against
  `~/socotra-buddy/resources/derived/` per the C3 handoff block's
  "reality-check first" rule, and the corpus returned exactly one
  hit (`125949463fad41f0.md`) which uses "peril" conversationally to
  describe coverages, not a directory layout. Per the C3 handoff's
  explicit fallback ("swap this fixture for a second jurisdictional
  variant") `peril-based/` was replaced by `jurisdictional-exclusive/`,
  which exercises the `exclusive` + `appliesTo` detection branches
  (the sibling `jurisdictional/` fixture covers `qualification`).
  Two refusal flags graduated to `true`-in-a-fixture-registry this
  session: `jurisdictional_scopes` and `multi_product`. Remaining
  refusal flags still awaiting a live `true` observation:
  `peril_based` (deferred per above), `coverage_terms`,
  `default_option_prefix` — all queued for C4. Incidental code
  change: `build_registry()` in
  `.cursor/skills/mapping-suggester/scripts/extract_paths.py` now
  sorts product subdirectories by name before picking the first one,
  so multi-product fixtures are reproducible across filesystems
  rather than dependent on `iterdir()` order. Verified no impact on
  the live CommercialAuto registry or on the existing five fixtures
  — `conformance/run-conformance.py` reports 8/8 registry pass post-change.
  C3 did not need a Leg 2 suggester run (goldens authored by direct
  rule-application; same precedent as C1 and C2) —
  `extract_paths.py` was invoked three times, once per fixture, and
  the three generated registries were promoted to goldens verbatim.
- **2026-04-22 — Session C2** — Three nested-shape Phase C fixtures
  landed: `conformance/fixtures/nested-iterables/`,
  `conformance/fixtures/cdt-flat/`, and `conformance/fixtures/cdt-recursive/`.
  Fixture path cells updated in place on rows 12, 13, 14, 15, 16,
  and 17 (rows 14 / 15 / 17 are direct coverage; rows 12 / 13 / 16
  are detection-satisfied-by-shared-code-path and annotated as
  `partial` with rationale in their Notes cells). First refusal-rule
  fixtures in the matrix: `nested_iterables`, `custom_data_types`,
  `array_data_extensions`, and `recursive_cdts` have now been
  observed `true` in at least one fixture's registry, and each
  fixture carries the matching §7 Unrecognised-inputs rows in its
  `golden/review.md`. `auto_elements` remains the only
  rule-supported flag proven via a fixture (C1, all-quantifiers);
  the other four `feature_support` refusal flags
  (`jurisdictional_scopes`, `peril_based`, `multi_product`,
  `coverage_terms` + dependent `default_option_prefix`) are queued
  for sessions C3–C5. C2 did not need a Leg 2 suggester run
  (goldens authored by direct rule-application; same precedent as
  C1) — `extract_paths.py` was invoked three times, once per
  fixture, and the three generated registries were promoted to
  goldens verbatim. `conformance/run-conformance.py` passes on all 5 current
  fixtures (registry: 5/5 pass; suggested+review: 2/5 pass, 3/5
  skipped because the C2 fixtures have no `actual/suggested.yaml` —
  a future session can populate those by running the suggester
  live against each fixture and using `--update-goldens`).
- **2026-04-22 — Session C1** — First two Phase C fixtures landed:
  `conformance/fixtures/minimal/` and `conformance/fixtures/all-quantifiers/`.
  Fixture path columns on rows 1, 2, 3, 4, 5, 6, 7, 8, and 11
  updated in place (each cell now names the fixture and the session
  that produced it, replacing the `(pending)` marker). `conformance/run-conformance.py`
  runner script added — registry diff automated, suggester diff is
  agent-refresh / `--update-goldens` workflow. Rows 9, 10, 12–26
  remain `(pending)` and are carved up across sessions C2–C5 per the
  `.cursor/plans/pipeline-improvements/CompletedPlans/alpha-beta-plan/PIPELINE_EVOLUTION_PLAN.md` handoff block. `auto_elements: true`
  is now the only `feature_support` flag exercised by a fixture;
  every refusal flag (rows 9, 12–20) still needs a dedicated Phase C
  fixture before `CONFIG_COVERAGE.md` §4's refusal contract is
  regression-covered end-to-end.
