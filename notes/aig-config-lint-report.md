# AIG reference config — lint report

**Config:** `workspace-prod/reference/socotra-config/` (pristine reference — not modified)
**Date:** 2026-07-16
**Tool:** `socotra-config-lint` (plugin `socotra-daily-driver` 0.2.1, `lint_config.py`) — rules: NAME-CASE, DATA-CLOSED, STAR-LEAK, TERM-TYPE, TERM-DEFAULT, LAYOUT, REF-RESOLVE, JSON-PARSE. Findings cross-checked against the mirrored docs.socotra.com corpus (socotra-buddy) and by direct inspection.

## Totals

| Rule | Raw findings | After cross-check |
|---|---|---|
| DATA-CLOSED | 1,137 | **0 — all false positives** (linter allowlist too narrow) |
| REF-RESOLVE | 30 | **0 — all false positives** (layout mismatch) |
| TERM-TYPE | 1 | **1 probable blocker** (different line than the linter pointed at) |
| LAYOUT | 1 | **1 to verify** (missing `reversalTypes/`) |
| **Total** | **1,169** | **1 probable blocker + 1 verify item** |

## Deploy-blocking

1. **`coverageTerms/config.json` line 14 — `"type": "Deductible"` (capital D)** on term
   `AccidentMedicalExpenseAmount`. Docs (features/policy-management/coverage-terms) define the
   enum as lowercase `limit` | `deductible`; every other term in the file uses lowercase
   `deductible` (32/33). Fix: change to `"deductible"`. *(The linter reported this rule as
   "type 'None'" against the file's top level — a layout artifact; the genuine anomaly is the
   capitalized value.)*

## To verify (possibly blocking)

2. **`reversalTypes/` directory absent entirely** (LAYOUT rule: `reversalTypes/Standard`
   expected). The lint rule stands in for a real server rejection, and offline nothing
   scaffolds it (`POST /config/formatConfig` does that online). However, a tenant-exported
   config may legitimately omit it. Treat as blocking until a deploy or `formatConfig`
   round-trip proves otherwise; the fix is copying a `Standard` reversal type from a
   known-good tree.

## False positives (why 1,167 findings were discarded)

- **DATA-CLOSED × 1,137** — flagged properties `tag` (729), `defaultValue` (351),
  `constraint` (55), `searchable` (2) across 139 files. All four are **documented, legal**
  data-field/PropertyRef properties: the data-extensions overview
  (docs.socotra.com/configuration/data-extensions/overview) lists `tag` and `defaultValue`
  in its comprehensive properties list; `constraint` is the documented constraint-table
  binding (`{"table": …, "column": …}` — this config ships `constraintTables/`); `searchable`
  was added to PropertyRef per the release notes. The linter's allowlist
  (`displayName, type, options, maxLength, min, max, precision`) is narrower than the
  platform schema. Per the skill's maintenance rule these should be added to the allowlist.
- **REF-RESOLVE × 30** — every coverage's `coverageTerms` reference was reported dangling
  because the linter resolves refs to per-entity **directories**, while this config defines
  all 33 terms as keys in a single `coverageTerms/config.json` map (the layout the docs'
  own examples use). Verified programmatically: all 30+ refs (quantifiers stripped, e.g.
  `AccidentalDeathMaximumAmount!`) resolve to keys in that map. Zero genuinely dangling.

## Warnings / informational

- 13 of 15 option-style coverage terms have no `*`-prefixed default option (e.g.
  `BereavementAndTraumaMaximumAmount`). Per docs this is legal for regular elements —
  it only bites on **automatic** elements ("Automatic elements cannot have any coverage
  terms unless … optional or has a default option"). No such pairing detected as blocking;
  worth a glance if any coverage is `exactly_one_auto`.
- STAR-LEAK, NAME-CASE, TERM-DEFAULT, JSON-PARSE: clean (verified no `*`-prefixed values in
  any data-field `options` array anywhere in the tree).
- Plan dirs otherwise present: installmentPlans (Standard + Annual/Monthly/Quarterly/
  SemiAnnually), delinquencyPlans, autoRenewalPlans, excessCreditPlans, retryPlans — all
  have `Standard`.

## Verdict

**Needs 1 fix first** (`Deductible` → `deductible` in `coverageTerms/config.json`), plus
verify whether the missing `reversalTypes/Standard` is server-rejected or server-defaulted.
Everything else is lint-clean against known platform rules once the two documented
allowlist/layout gaps in the linter itself are set aside. (Lint-clean ≠ validated — only a
tenant round-trip validates.)
