# Improvement note — human-fill friction in path-review & variants.csv

**Status:** RESOLVED 2026-06-18 — all four gaps fixed + regression-tested (462 pass)
**Owner:** Josh
**Effort:** mixed — three small fixes, one real design fix

> **Resolution summary (2026-06-18):**
> - **Gap 1** — `registry_match.match_leaf` now has a full-accessor pass-through:
>   a token equal to a known registry accessor resolves to itself (`match: full
>   accessor`). Tests: `test_legminus1.py::test_full_accessor_passthrough`,
>   `::test_dotted_non_accessor_still_unmatched`.
> - **Gap 2** — `leg0_ingest.write_variants_csv` now compares against any existing
>   file and **skips + warns** rather than overwriting an edited CSV (identical
>   content is a no-op rewrite). Tests: `test_leg0_variants.py::test_does_not_clobber_edited_csv`,
>   `::test_rewrites_identical_csv`.
> - **Gap 3** — stub `when` pre-fills changed from `!= null` to `present`; the DSL
>   parser raises a targeted hint on a `null`/`nil`/`none` literal. Tests:
>   `test_leg0_variants.py::test_stub_when_uses_present_not_null`,
>   `test_condition_dsl.py::test_null_literal_gives_present_absent_hint`.
> - **Gap 4** — route (a): `condition_dsl.build_registry_index` indexes quote custom
>   fields under a `quote.data.<f>` alias (full-accessor-only, kept out of bare-leaf
>   resolution so leaves stay unambiguous); the quote scope check already allows the
>   `quote.` root. Verified end-to-end (Leg 4 `--compile-check` PASS on
>   `quote.data().discountAmount()` / `coolingOffPeriod()`). Tests:
>   `test_condition_dsl.py::test_quote_data_custom_field_valid_in_quote_scope`,
>   `::test_quote_data_alias_rejected_in_policy_scope`.
**Context:** Filling the two customer-facing files (`<stem>.path-review.md` and
`<stem>.variants.csv`) for `ZenCoverWelcomeLetter(quote)` surfaced four gaps. The
render pipeline itself was smooth end-to-end; **all** the friction lives in the
human-fill step — which is exactly the part a real customer touches unaided. None
blocks a render, but each makes the handoff look broken or forces a non-obvious
workaround. See [[render-preview-demo-working]] for the run that exposed them.

---

## Gap 1 — Leg -1 reports "NO MATCH" for full dotted accessors  ⭐ cheapest win

**Symptom:** author wrote full accessors inside the braces — `{account.data.firstName}`,
`{quote.quoteNumber}`, `{quote.data.coolingOffPeriod}`, `{quote.data.newBusinessWaitPeriod}`.
Leg -1 resolves *bare leaves* only, so every dotted token failed to match and the
`path-review.md` showed **5 of 6 fields as "NO MATCH in registry"** with blank
`Final:` lines. The accessors were all valid — they just weren't *leaves*.

**Why it's bad:** a customer reading "NO MATCH" on 5/6 fields concludes the tool is
broken. The data was correct; only the lookup mode was wrong.

**Fix sketch:** before declaring NO MATCH, check whether the token is already a valid
full accessor (present in the registry index). If so, mark it `resolved (full
accessor)` and pre-fill `Final:` with the token verbatim (pass-through). Only fall to
"NO MATCH" when it is neither a known leaf nor a known accessor.

**Where:**
- `velocity_converter/legminus1_resolve_paths.py:152` — `match_leaf(...)` call site /
  verdict assembly (`Status:` lines at `:189`/`:192`/`:194`).
- `velocity_converter/registry_match.py:182` — `match_leaf()`; add a full-accessor
  short-circuit, or do it at the call site against the registry index.

---

## Gap 2 — full Leg 0 re-ingest clobbers the filled variants.csv

**Symptom:** filled the `when` conditions in `variants.csv`, then ran the full `leg0`
ingest (needed to write the `.conditional-blocks.yaml` sidecar) — the ingest
**overwrote the CSV back to blank/default rows**, discarding the fill. Had to re-fill
before `--parse-variants-csv`.

**Why it's bad:** the documented order (intake → fill → full leg0 → parse) silently
destroys the customer's work. Already a known issue — see memory
`leg0-reingest-clobbers-fills` — but it bit again here, so it stays on the list.

**Fix sketch:** when `write_variants_csv` is about to overwrite an existing CSV that
already has non-empty `when`/`text` cells, either (a) skip the write and warn, (b)
snapshot+restore the fills, or (c) write to a `.regenerated` sidecar and diff. Option
(a) is smallest and safest.

**Where:** `velocity_converter/leg0_ingest.py:835` — `write_variants_csv()`.

---

## Gap 3 — `!= null` accepted-looking but rejected, with no hint

**Symptom:** the scan pre-fills `when` as `quote.quoteNumber != null`. The DSL has no
`null` literal — it wants `present`/`absent`. Parsing `quote.quoteNumber != null`
raises `ConditionError: expected a literal, found bare word 'null'`, which does not
tell the customer what to write instead.

**Why it's bad:** the tool ships a pre-filled example that its own parser rejects, and
the error doesn't point at the fix.

**Fix sketch (two parts):**
1. Stop pre-filling `when` with `!= null` in the scan — leave it blank, or pre-fill a
   valid `present` check.
2. In the parser, special-case a `null` literal after `==`/`!=` and raise a targeted
   message: *"use `present`/`absent` for null checks, not `!= null`"*.

**Where:**
- pre-fill: `velocity_converter/leg0_ingest.py:835` `write_variants_csv()` (whatever
  seeds the example `when`).
- parser hint: `velocity_converter/condition_dsl.py` (literal parsing — the branch
  that raises "expected a literal").

---

## Gap 4 — quote-scoped conditions can't reference custom fields  ⭐ real design fix

**Symptom:** the natural welcome-letter conditions — `quote.data.discountAmount present`,
`quote.data.newBusinessWaitPeriod == 0` — are **rejected at validation** as "not a
known accessor", even though both are in the path catalog and the DSL *parses* them
fine. Forced a fallback to `quote.quoteNumber present` / `quote.startTime present`,
which don't express the actual business logic.

**Root cause (two layers):**
1. The registry has **no `quote_data` category**. Quote custom fields are stored as
   `policy_data` with velocity `$data.data.<field>`, so
   `build_registry_index` derives their condition accessor as `policy.data.<field>` —
   never `quote.data.<field>`.
2. `_SCOPE_ROOTS["quote"] = {"quote"}` then rejects any `policy.*` root at quote scope.

Net: **a quote-scoped document can only condition on `quote.*` *system* fields.** No
custom field is reachable in a quote condition — the single biggest content
limitation for a quote letter.

**Fix sketch (needs a decision):** either
- (a) index quote custom fields under a `quote.data.*` condition accessor (teach
  `_derive_condition_accessor` that, at quote scope, `policy_data`/`$data.data.*`
  is addressable as `quote.data.*`), **and** allow `quote.data.*` through the quote
  scope check; or
- (b) introduce a real `quote_data` category in the registry + extractor so quote
  custom fields are first-class (cleaner, larger — touches the registry generator;
  mind `registry-generator-staleness`).

**Where:**
- `velocity_converter/condition_dsl.py:267` — `_SCOPE_ROOTS`.
- `velocity_converter/condition_dsl.py:273` — `_derive_condition_accessor()`.
- `velocity_converter/condition_dsl.py:302` — `build_registry_index()`.
- `registry/path-registry.yaml` (+ its extractor) if going route (b).

---

## Suggested order

1. Gap 1 (Leg -1 pass-through) — tiny, removes the scariest customer-facing symptom.
2. Gap 3 (drop `!= null` pre-fill + targeted parser hint) — tiny.
3. Gap 2 (don't clobber a filled CSV) — small, prevents data loss.
4. Gap 4 (quote-scope custom fields) — the design fix; unblocks real conditional logic.
