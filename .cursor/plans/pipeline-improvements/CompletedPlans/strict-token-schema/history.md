# History — Strict SDK-Grounded Token Schema

Append-only. Newest entry first.

---

## 2026-06-05 — heart-circulatory(quote).html token migration

### What changed
- **samples/input/heart-circulatory(quote).html**: Converted 3 tokens to dotted format; `{{ACCOUNT_firstNAME}}` left old-format (same limitation as `{{ACCOUNT_NAME}}` in Simple-form — account name not accessible from quote root via SDK)
  - `{{PRODUCT_NAME}}` → `{{ZenCoverQuote.productName}}`
  - `{{QUOTE_NUMBER}}` → `{{ZenCoverQuote.quoteNumber}}`
  - `{{START_TIME}}` → `{{ZenCoverQuote.startTime}}`

### Root cause (investigation notes)
Pipeline returned "EMPTY — no placeholders found" on first run. Traced through:
1. Leg 1 mapping.yaml had `variables: []` → convert.py was not extracting tokens
2. `VAR_RE` in convert.py requires a dot (`+` quantifier on the dot group); dotless names like `{{PRODUCT_NAME}}` silently pass through unconverted
3. A VAR_RE fix (making dot optional, `*`) was attempted but reverted — the strict dot requirement is **intentional** per this plan; it forces authors to use `EntityType.fieldName` format
4. Correct fix: update the HTML source to use dotted names

### Verification
- `ZenCoverQuote.productName` → `match_step: exact`, `confidence: high`, `$data.quote.productName` ✓
- `ZenCoverQuote.quoteNumber` → `match_step: exact`, `confidence: high`, `$data.quote.quoteNumber` ✓
- `ZenCoverQuote.startTime` → `match_step: exact`, `confidence: high`, `$data.quote.startTime` ✓
- Leg 3 status: COMPLETE — 3/3 resolved, 0 unresolved ✓

---

## 2026-06-05 — All phases implemented (P1–P4)

### What changed
- **sdk_introspect.py**: Added `build_schema_index()` (BFS from rendering roots); trimmed `jar_candidate()` — removed Steps 3+4 (prefix/label-word fuzzy)
- **scripts/build_schema_index.py**: New CLI — generates `registry/sdk-schema-index.yaml`
- **registry/sdk-schema-index.yaml**: Generated — 49 entity types, 456 fields, depth 3
- **leg2_fill_mapping.py**: Added `match_token()`, `_ci_lookup()`, `_make_schema_entries()`, `_step3_terminology_strict()`, `load_schema_index()`; removed `_step4_fuzzy()` call; updated `confidence_grade()` (old-format/none → "none", terminology capped at medium D7); removed coverage squashing (D6); removed loop last-token split; updated `annotate_mapping()` to accept and use `schema_index`
- **leg2_review_writer.py**: Added `none` column to summary table; added "Token Format Errors" section (§7.4)
- **convert.py**: Updated `VAR_RE` to require dotted path; updated `tbd_pattern` in `wrap_conditionals()` to capture full dotted tokens
- **leg3_substitute.py**: Updated `_TBD_TOKEN_RE` and `_GUARD_OPEN_RE` to match `[\w.]+` (handles dotted placeholders `$TBD_Entity.field`)
- **Simple-form(quote).html**: Converted 3 tokens to dotted format; `{{ACCOUNT_NAME}}` left old-format (no SDK entity for account name from quote root)

### Deviations
- `PersonalAccount.firstName` (plan's example) is not in ZenCover JARs — account entity accessed via DataFetcher. Used `ZenCoverQuote.productName` as real example.
- `leg3_substitute.py` and `convert.py` regex updates were not explicitly called out in the plan but were required to handle the new `$TBD_Entity.field` placeholder format.

### Implementation cost retrospective
Two unplanned iteration cycles added significant token/time overhead:

1. **Missing regex cascade** — Plan did not mention that `_TBD_TOKEN_RE` in `leg3_substitute.py` and `tbd_pattern` in `wrap_conditionals()` (convert.py) also need to match `[\w.]+` for dotted placeholders. Discovered only after running the pipeline and seeing `$TBD_ZenCoverQuote.productName` survive substitution unchanged. Required a second investigation + fix + re-run.

2. **`cand()` missing `match_step`** — In `derive_variable_candidate()`, the schema-validated terminal branch forgot to pass `match_step=step` to `cand()`, causing the candidate block to show `match_step: none` instead of `exact`. Caught on the first pipeline run.

**Future plan authoring note:** Any plan that changes the `{{token}}` placeholder format must also audit `_TBD_TOKEN_RE` (leg3), `_GUARD_OPEN_RE` (leg3), and `tbd_pattern` in `wrap_conditionals()` (convert.py). These three are a coupled set — changing one without the others silently breaks substitution.

### Verification
- `ZenCoverQuote.productName` → `match_step: exact`, `confidence: high`, `$data.quote.productName` ✓
- `ZenCoverQuote.quoteNumber` → `match_step: exact`, `confidence: high`, `$data.quote.quoteNumber` ✓
- `ZenCoverQuote.startTime` → `match_step: exact`, `confidence: high`, `$data.quote.startTime` ✓
- No `fuzzy`/`step4_fuzzy`/`prefix-fuzzy` in output ✓

---

## 2026-06-05 — Plan created

### Summary
- Identified 6 fuzzy match sites across `leg2_fill_mapping.py` and `sdk_introspect.py`
- Defined strict token format `{{EntityType.fieldName}}`
- Specified `build_schema_index()` function and `registry/sdk-schema-index.yaml` output artefact
- Wrote full plan: 4 phases, 14 tasks

### Open items (now resolved)
- Phase 1 not yet started
- `samples/input/Simple-form(quote).html` tokens not yet migrated
