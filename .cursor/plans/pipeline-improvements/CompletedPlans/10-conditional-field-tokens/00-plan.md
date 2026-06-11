# Field Tokens Inside Conditional Blocks

**Status:** Done
**Completed:** 2026-06-11
**Created:** 2026-06-11
**Item:** Gap — conditional text segments containing `{field}` placeholders render the literal `$TBD_*` token in the final document.

## Implementation notes (deltas vs plan)

- **Custom policy fields resolve on the segment type**, not core `Policy` —
  `policy.data.X` → `segment.data().X()` in Java (`com.socotra.coremodel.Policy` has no
  `data()`). Applied to field concatenation AND to condition translation in the policy
  overload (`_rewrite_condition_root`). Verified by javap + compile check.
- **Optional unwrap**: many system accessors return `Optional<T>` (quoteNumber,
  policyNumber, jurisdiction…). Wiring is javap-verified per chain
  (`_walk_java_chain`); `Optional` returns emit `.map(Object::toString).orElse("")`
  instead of `Objects.toString(...)` (which would render "Optional[x]").
  A chain that doesn't resolve in Java is flagged resolved-but-unsupported, never
  generated broken.
- **Symmetric condition scope rule**: blocks with `policy.*`-rooted conditions now get
  an empty put in the *quote* overload (mirror of the existing quote-in-policy rule) —
  previously they generated uncompilable references to a nonexistent `policy` local.
- **Leg 4 gained `--registry`** (defaults: mapping's `path_registry`, then
  `<repo>/registry/path-registry.yaml`) to map velocity paths → categories.
- **Test runner**: cleans stale `*.java`/`*.java.bak` before Leg 4 (a stale plugin from
  a prior run silently flipped the suite into additive mode) and fails on any literal
  `$TBD_` in generated plugins.
- T8 needed no new fixture — `TestRenewalNotice(segment)` already had two fields inside
  its loyalty-discount conditional block.
- Fresh `TestRenewalNotice` plugin passes `--compile-check` with zero `$TBD_` (AC 1).

## START HERE (implementing agent)

Make `[[conditional text with {field} placeholders]]` render correctly end to end. Today the
plugin emits the conditional text as a **static Java string**, so any field placeholder inside
a conditional block survives as a literal `$TBD_field` in the rendered document — silently,
with every leg reporting success.

**Read in this order:**
1. This file — §1 (failure chain), §2 (decisions), §4 (challenges), §5 (task list)
2. `scripts/leg0_ingest.py` — `main()` ordering (line 611–617), `write_conditional_form()` (line 431), `parse_conditional_form()` (line 470)
3. `scripts/leg4_generate_plugin.py` — `_source_text_to_java()` (line 633), `render_conditional_puts()` (line 645), `_velocity_to_accessor` category mapping (line ~55–70), `_accessor_to_java()` (line 73)
4. `scripts/leg3_substitute.py` — `apply_cond_substitutions()` (line 98), main flow ordering (line 692–693), report categorisation (line 696+)

---

## 1. Background — the failure chain

Input: `[[You qualify for a {discount_name} discount]]`

| Step | What happens | Problem |
|------|--------------|---------|
| Leg 0 | `annotate_fields()` runs **before** `extract_conditionals()` → block `source_text` = `You qualify for a $TBD_discount_name discount` | Internal token leaks into customer-facing form and registry |
| Form | Customer sees `> You qualify for a $TBD_discount_name discount` | Confusing; customer may "fix" it, corrupting round-trip |
| Leg 3 | `process_vm()` substitutes the token in the template copy, then `apply_cond_substitutions()` replaces the whole `[[...]]$doc.condN` block with `${data.condN}` | Substitution work discarded; report still counts the token as resolved |
| Leg 4 | `_source_text_to_java()` escapes source_text into a Java string literal; only `$doc.condN` refs become concatenation | `$TBD_discount_name` is baked into the plugin string verbatim |
| Render | Plugin puts the literal string into `renderingData.condN`; template outputs it via `${data.condN}` (Velocity does not re-parse plugin output) | **Final document shows `$TBD_discount_name`. No leg errored.** |

The architecture decision "the plugin owns conditional text" (leg3 DD — template only outputs
`${data.condN}`) is what makes this a gap: dynamic content inside a conditional must be
resolved **in Java**, not in Velocity.

---

## 2. Decisions

| # | Topic | Decision |
|---|-------|----------|
| D1 | Architecture | **Plugin-side concatenation** (Option A, §3). Keep "plugin owns conditional text". Leg 4 replaces `$TBD_field` in source_text with Java accessor concatenation, mirroring the existing `$doc.condN` → `" + condN + "` mechanism. No change to leg 3's `${data.condN}` contract. |
| D2 | Value source | Leg 4 builds a `name → data_source` lookup from the enriched `--suggested` mapping.yaml (already loaded). Velocity path → accessor via existing `_velocity_to_accessor`, then `_accessor_to_java`. |
| D3 | Null safety | Wrap each injected accessor in `Objects.toString(<expr>, "")` so a null field renders as empty string, not `"null"`. Intermediate-chain NPE risk is accepted — identical to the existing condition codegen risk profile. Add `java.util.Objects` import when used. |
| D4 | Unsupported scopes (MVP) | `item.*` / per-exposure fields inside a conditional are **flagged, not generated** — the conditional put is emitted once per document, not per exposure. Emit a `// TODO` comment + keep literal text + WARN row in the plugin report. Same for DataFetcher-sourced fields (would need a fetch before the cond block) — deferred, TODO-flag only in this plan. Note: these are *resolved-but-unsupported*, distinct from D5's *unresolved*. |
| D5 | Unresolved fields | If a field inside a conditional block has no `data_source`, **Leg 4 fails**: print an error listing each unresolved field and the block ID it appears in, write no plugin, exit non-zero. Rationale (user decision 2026-06-11): fail loudly so later bugs get caught — a silently-degraded plugin is worse than a blocked run. **Future direction:** fail *before* Leg 4 — a pre-flight completeness gate is a natural extension of plan `06-leg2-completeness-check`; add a cross-reference there when implementing. |
| D6 | Quote vs policy scope | Reuse the existing scope logic in `render_conditional_puts`: a `quote.*`-sourced field inside a block emitted in the `policy` overload gets the same empty-put treatment as quote-scoped conditions today. |
| D7 | Form display | `write_conditional_form()` displays `{field_name}` (original author syntax), not `$TBD_field_name`. `parse_conditional_form()` converts `{name}` back to `$TBD_name` when writing the registry, so the registry stays in canonical machine form. Parser accepts **both** formats so already-sent forms still parse. Round-trip is symmetric. |
| D8 | Token matching | Match `$TBD_` tokens in source_text by **longest-match against known mapping names** (not a bare greedy regex) — `$TBD_name.` followed by sentence punctuation must not swallow the trailing dot. Fall back to `\$TBD_[A-Za-z_][\w.]*\b` with trailing-dot strip for names absent from the mapping. |
| D9 | Leg 3 report honesty | Tokens whose **only** occurrences in the `.vm` lie inside `[[...]]$doc.condN` blocks get a new report category: "Delegated to plugin (condN)" instead of counting as template-resolved. Detection: scan the pre-substitution vm_text block spans. |
| D10 | Literal braces | Brace text not matching `_FIELD_RE` (e.g. `{0}`, `{ "k": 1 }`) passes through untouched, as today. Out of scope. |
| D11 | Additive mode | Field concat must survive cond-ID offsetting (high-water). It does naturally — offsetting touches only `$doc.condN` refs. Add a regression test to lock it. |

---

## 3. Architecture options considered

**Option A — plugin-side concatenation (chosen).** Leg 4 turns
`"You qualify for a $TBD_discount_name discount"` into:

```java
String cond3 = "";
if (policy.data().promoEligible()) {
    cond3 = "You qualify for a " + Objects.toString(policy.data().discountName(), "") + " discount";
}
renderingData.put("cond3", cond3);
```

Localized to leg 4 (+ cosmetics in leg 0, + report honesty in leg 3). Preserves the deployed
plugin/template contract, additive mode, multi-form, and the existing test fixtures.

**Option B — boolean flag + template-side `#if` (rejected for MVP).** Plugin puts a boolean;
leg 3 keeps block content inline wrapped in `#if($data.condN)…#end`, so fields substitute
naturally in Velocity (and `item.*` fields inside loops would work). Rejected because it
changes the conditional contract for every existing template/plugin, complicates nested
blocks (a parent's source_text concatenates child cond **strings** — mixing string and boolean
children breaks the concat model), and invalidates the additive-mode key semantics. Revisit
if per-exposure fields inside conditionals become a real customer need — note it in
PRODUCT-IMPROVEMENT-LIST.md.

---

## 4. Challenges (why this isn't a one-liner)

1. **The substitution work is discarded silently.** Leg 3 substitutes the token, then deletes
   the block. Nothing fails; the report lies. Fixing rendering (leg 4) without fixing the
   report (D9) leaves a second, subtler lie.
2. **Scope split.** The plugin has quote and policy overloads; a field accessor rooted at
   `quote.` is unavailable in the policy overload. Existing condition-scope logic must be
   extended to the source_text accessors (D6).
3. **Per-exposure fields are structurally unsupported.** `item.data.vin` has no meaning in a
   once-per-document put. Must be detected and loudly flagged (D4), not generated as broken Java.
4. **DataFetcher-sourced fields** need a fetch executed before the cond block — orderable but
   non-trivial; deferred to TODO-flag in MVP (D4).
5. **Token boundary ambiguity.** `$TBD_name` followed by `.` or `,` in prose; dotted
   placeholder names (`{account.data.firstName}` → `$TBD_account.data.firstName`) are legal
   per `_FIELD_RE`. Longest-match against mapping names (D8).
6. **Form round-trip symmetry.** Displaying `{field}` in the form (D7) means
   `parse_conditional_form()` must convert back, or the registry/plugin pipeline breaks on the
   very documents this plan fixes. The parse regex takes source_text **from the form**, so
   display format = registry input format unless converted.
7. **Java string escaping order.** `_source_text_to_java` escapes `\` and `"` first, then
   substitutes refs. Field substitution must run on the escaped string the same way the cond
   ref substitution does, and compose with it (a block can contain both `$doc.condN` and
   `$TBD_x`).
8. **Null/format fidelity.** Java `Objects.toString` formatting (BigDecimal, dates) may differ
   from Velocity-side rendering of the same path. Accepted for MVP; note in plugin report
   footer that formatted fields inside conditionals may need a custom format call.
9. **Leg 2 dependency.** The registry can exist (customer returned the form) before Leg 2
   enriched the mapping. With D5, running Leg 4 on an unenriched mapping that has fields
   inside conditionals now **fails** rather than degrading — the error message must say
   "run Leg 2 first" explicitly, since this is the most likely cause. The CLAUDE.md
   pre-flight only forces registry-before-downstream, not enrichment.

---

## 5. Task list

| # | Task | File(s) |
|---|------|---------|
| T1 | Form display: `$TBD_name` → `{name}` in `write_conditional_form()`; inverse conversion in `parse_conditional_form()` before writing the registry (accept both formats — D7) | `scripts/leg0_ingest.py` |
| T2 | Build `name → data_source` lookup from `--suggested` mapping in leg 4; thread into `render_conditional_puts()` | `scripts/leg4_generate_plugin.py` |
| T3 | Extend `_source_text_to_java(source_text, field_lookup, scope)`: longest-match `$TBD_` tokens → `Objects.toString(<java accessor>, "")` concat; compose with existing `$doc.condN` concat | `scripts/leg4_generate_plugin.py` |
| T4 | Scope + unsupported handling: quote-rooted fields in policy overload → empty put; `item.*`/DataFetcher-sourced → TODO comment, literal kept, plugin-report WARN section; **unresolved → hard fail**: error listing field + block ID + "run Leg 2 first" hint, no plugin written, exit non-zero (D4/D5/D6) | `scripts/leg4_generate_plugin.py` |
| T5 | Add `java.util.Objects` import emission when any field concat generated | `scripts/leg4_generate_plugin.py` |
| T6 | Leg 3 report: "Delegated to plugin (condN)" category for tokens occurring only inside cond blocks (D9) | `scripts/leg3_substitute.py` |
| T7 | Regression tests: `_source_text_to_java` field concat (incl. punctuation boundary, dotted names, mixed `$doc.condN` + `$TBD_`), scope split, unresolved → hard fail + no plugin written, additive-mode offset survival (D11) | `tests/regression/` |
| T8 | Pipeline fixture: add a field-inside-conditional block to one existing fixture builder + condition seed; assert final plugin Java contains the accessor concat and the final doc has no `$TBD_` | `scripts/generate_test_fixtures.py`, `tests/pipeline/condition_seeds.yaml`, `tests/pipeline/run_test_pipeline.py` |
| T9 | Docs: CLAUDE.md leg-4 section + `docs/pipeline-dataflow.md` note on fields-in-conditionals support and MVP exclusions (item-scope, DataFetcher) | `CLAUDE.md`, `docs/` |

Suggested order: T2→T3→T4→T5 (core), T7 alongside, then T1, T6, T8, T9.

---

## 6. Acceptance criteria

1. Fixture doc with `[[ ... {field} ... ]]` runs leg 0 → form fill → parse → leg 2+3 → leg 4
   via `python3 tests/pipeline/run_test_pipeline.py --auto` with zero `$TBD_` strings in the
   generated plugin's `condN` assignments (for supported scopes) and a passing compile check.
2. Conditional form shows `{field}` syntax; registry round-trips to `$TBD_field`; a form
   written in the old `$TBD_` format still parses.
3. Per-exposure / DataFetcher-sourced fields inside a block produce a visible WARN in
   `<stem>.plugin-report.md` — never a silent literal.
4. An **unresolved** field inside a block makes Leg 4 exit non-zero with the field name,
   block ID, and a "run Leg 2 first" hint; no plugin file is written or modified.
5. Leg 3 report no longer counts cond-block-only tokens as template-resolved.
6. Existing fixtures and regression suite pass unchanged (no contract break for
   field-free conditionals; additive mode intact).
