# Implementation plan — multi-variant conditional blocks (the 50-state feature)

**Status:** plan / not started (2026-06-15)
**Depends on:** `notes/condition-dsl-design.md` (this is its killer use case — the DSL
ships *as part of* this feature, not before it).
**Goal:** let one template carry N text variants behind a single `[[…]]` conditional,
selected by data at render time. Solves "50 different state disclosures in one
template" without 50 templates.

---

## 1. The shape of the feature

Today a `[[…]]` block is **binary**: one condition, text present or absent. Leg 4
emits one guarded assignment:

```java
String cond1 = "";
if (quoteNumber != null) { cond1 = "…text…"; }
renderingData.put("cond1", cond1);
```

A multi-variant block is the **N-way generalisation** — same `condN` key, an
if/else-if chain instead of a single `if`:

```java
String cond1 = "";
String st = Objects.toString(segment.data().state(), "");          // codegen'd accessor
if      (Objects.equals(st, "CA")) { cond1 = "…California text…"; } // first match wins
else if (Objects.equals(st, "NY")) { cond1 = "…New York text…"; }
…                                                                   // 48 more
else                               { cond1 = "…default disclosure…"; }  // default row
renderingData.put("cond1", cond1);
```

**Author syntax.** Inside the doc the author writes a *named token* instead of literal
text: `[[$stateClause]]`. The leading `$` + single-token (no spaces) discriminates a
**variant block** from today's binary `[[literal text]]`. Both forms coexist — binary
inline blocks stay as-is so simple docs need no CSV. (Mirrors the occurrence-symbol
prefix convention `{$x}`/`{+x}`.)

**What does NOT change** — the elegance of the design:

- **Leg 1, Leg 2** — untouched.
- **The template** — still emits `${data.<key>}`. All N-way logic lives in the plugin
  (consistent with the existing "plugin owns conditional text" rule).
- **Field wiring inside the text** (`_source_text_to_java` `:1010`,
  `_build_cond_field_lookup` `:197`) — reused **per variant**; a variant text
  containing `{discountAmount}` still gets concatenated as a Java accessor.

**What DOES change beyond the obvious — the author's token name replaces `condN`.**
See §1a. Leg 3's `_COND_BLOCK_RE`/`build_cond_map` and Leg 4's id machinery are
affected — so Leg 3 is *not* untouched, and the multi-form renumbering retires.

The real work is in **four places**: Leg 0 detection + CSV surface, the parse step
(CSV → validated YAML), Leg 4 codegen (single `if` → if/else-if), and the key-naming
change in Leg 3 + Leg 4. Plus the shared **DSL foundation**.

---

## 1a. Named keys replace positional `condN`

Today `condN` is a pipeline-invented **positional** key: `annotate_conditionals`
(`leg0_ingest.py:447`) appends `$doc.cond1`, `$doc.cond2`… in document order, and it is
the join key across template (`${data.cond1}`), registry (`id: 1`), and plugin
(`put("cond1", …)`). The author never sees it.

Once the author tokenises the block (`[[$stateClause]]`), **the token name IS the
key**, end to end — no `condN` indirection:

| Stage | Today (positional) | With named token |
|-------|--------------------|------------------|
| Leg 0 annotate | `[[…]]$doc.cond1` | `[[$stateClause]]$doc.stateClause` |
| Leg 3 collapse | `${data.cond1}` | `${data.stateClause}` |
| Registry | `id: 1` | `key: stateClause` |
| Leg 4 | `put("cond1", …)` | `put("stateClause", …)` |

**Payoff — the renumbering machinery retires.** `_parse_existing_cond_high_water`
(`leg4_generate_plugin.py:647`) and the id-offset logic in `_diff_keys` (`:776`) exist
*only* because positional numeric keys collide on additive multi-form merge (form B's
`cond1` must shift past form A's high-water mark). **Named keys don't collide by
position** → additive merge becomes a plain set-union by name. Keys also stay **stable
across edits**: insert a block mid-doc and nothing downstream renumbers.

**Two caveats:**
1. **Untokenised binary `[[literal]]` blocks have no name.** Either commit to "tokenise
   every conditional" (more author burden, but accepted), or assign untokenised blocks
   a **stable** auto-name once and persist it (NOT a renumber-on-insert positional
   index). Either way the renumbering dance dies. Recommended: tokenised → author name;
   untokenised → stable auto-name (e.g. `cond1` treated as an opaque persisted *name*,
   never re-derived).
2. **Names need validation** (Leg 0 / parse): unique per doc, valid `[A-Za-z_]\w*`, no
   clash with field `$TBD_` names. `condN` was unique + identifier-safe by construction;
   author names are not, so check them while the customer is in the loop.

**Back-compat:** treat the registry key as a *string* throughout. Existing registries'
numeric `id: 1` becomes the string key `"cond1"` — same mechanism, no migration. Code
that formats `cond{id}` becomes `{key}`.

---

## 2. Customer UX → standardised format (the central decision)

> Principle (from the design discussion): give the customer the best possible authoring
> surface — **Excel/CSV**, never raw YAML — then normalise that into the pipeline's
> standardised internal format.

### 2a. Customer-facing surface: one CSV per document

Leg 0 generates a **pre-filled CSV stub**, `<stem>.variants.csv`, one row group per
`$token` it found. Customer opens it in Excel, fills rows, saves as CSV (UTF-8).
Columns chosen for Excel ergonomics:

| Column        | Meaning                                                                 |
|---------------|-------------------------------------------------------------------------|
| `placeholder` | the `$token` from the doc, e.g. `stateClause` (pre-filled by Leg 0)      |
| `when`        | the selector in **DSL** (`state == "CA"`, `premium > 500`); blank/`*`/`else` = default row |
| `text`        | the variant text — multi-line HTML is fine (Excel cell wraps; CSV quotes it) |

- **Row order = priority** (first match wins). Customer reorders by dragging rows —
  intuitive in Excel, no priority column needed.
- **Default row**: `when` blank or `*` → the `else` branch. Exactly one per
  placeholder; parse warns if missing (block would silently render empty) or if >1.
- **Long/rich text**: Python's stdlib `csv` reader handles RFC-4180 quoted multi-line
  cells, which is exactly what Excel writes. No fragment-file indirection needed for v1;
  revisit only if real disclosures exceed what a cell comfortably holds.
- **Switch sugar (optional, nice-to-have)**: if every `when` for a placeholder is
  `<field> == <literal>` on the *same* field, codegen hoists the accessor once (the
  `String st = …` line above) and emits `Objects.equals(st, …)` per row. Falls back to
  per-row independent conditions otherwise. Pure codegen optimisation — no schema impact.

`.xlsx` direct ingest is **out of scope for v1** (needs `openpyxl`). CSV is the
interchange; Excel reads and writes it natively via "Save As → CSV UTF-8".

### 2b. Standardised internal format: extended `ConditionalBlock`

The CSV normalises into the existing `conditional-registry.yaml`, extending
`ConditionalBlock` (`velocity_converter/models.py`) with three optional fields. A block
with `variants` is N-way; a block without is today's binary block (clean back-compat,
old registries still load):

```yaml
- key: stateClause                  # NEW — string key; the $token name (§1a), or a
                                    #       stable auto-name ("cond1") for binary blocks
  placeholder: stateClause          # NEW — the $token; null for binary blocks
  render: plugin
  scope: policy                     # NEW — computed once at parse time (quote|policy)
  variants:                         # NEW — ordered, first-match-wins
    - when:   { path: policy.data.state, op: "==", value: "CA" }   # structured AST
      raw:    'state == "CA"'        # back-compat passthrough (DSL note §5)
      text:   "California requires…"
    - when:   { path: policy.data.state, op: "==", value: "NY" }
      raw:    'state == "NY"'
      text:   "New York requires…"
  default: "Default disclosure text…"   # the else row (when blank/*)
```

- `variants` present → Leg 4 uses the new N-way emitter; absent → existing binary
  emitter. No behaviour change for existing blocks.
- All variants of a block **must share one scope** (they assign the same `condN`,
  emitted in one overload). Mixed scope → hard error at parse time, surfaced to the
  customer while they're still in the loop.

---

## 3. Shared foundation — the condition DSL (`notes/condition-dsl-design.md`)

This feature can't ship on raw-string conditions: 50 hand-written Java conditions = 50
chances to NPE, mis-compile, or hit reference-equality (`==` on String). Build the DSL
the note sketches, scoped to what variants need:

1. **Grammar** (~40 lines, no deps): `<path> <op> <literal>`, ops
   `== != > >= < <= present absent in`, joined by `and`/`or`. Each `when` cell parses
   to one of these.
2. **Parser → AST** — `{path, op, value}` (+ `and`/`or` join). Stored structured in
   `variants[].when`, with `raw:` kept alongside for back-compat/debuggability.
3. **Validator** (at parse time, customer in the loop):
   - path exists in `path-registry.yaml` and root is legal for the block's scope;
   - leaf type vs literal type (string op on a number → error);
   - reuse `_walk_java_chain` (already validates field-token paths in Leg 4).
   Bad rows → a validation report back to the customer, not a broken plugin at deploy.
4. **Codegen from AST** (Leg 4):
   - stepwise **null-safe** accessor chain (reuse the occurrence-guard helper);
   - `Objects.equals()` for `==`/`!=` (kills the reference-equality bug);
   - `compareTo` for `>`/`<` on `BigDecimal`/dates; enum-aware;
   - `present`/`absent` → `!= null` / `== null`; `in [...]` → `List.of(...).contains(...)`.
   - scope classification computed once at parse, read at codegen.

The binary `[[literal]]` path can keep its current passthrough until the DSL proves
out, OR be migrated onto the same codegen — decide during Phase 1 (low risk either way
because of `raw:` fallback).

---

## 4. Phased implementation

### Phase 0 — DSL foundation
New module `velocity_converter/condition_dsl.py`:
- `parse_condition(str) -> ConditionAST | error`
- `validate_condition(ast, registry, scope, classpath, product) -> [errors]`
  (wraps `_walk_java_chain`)
- `condition_to_java(ast, scope, javap_ctx) -> str` (null-safe, `Objects.equals`,
  `compareTo`, enum/`in` aware)
- Unit tests: round-trip parse, each op, scope rejection, type-mismatch rejection,
  generated-Java string assertions.

### Phase 1 — registry schema + CSV normaliser
- `models.py` `ConditionalBlock`: add `key: str` (the §1a named join key — author token
  or stable auto-name), `placeholder: str | None`, `variants: list[Variant] | None`,
  `default: str | None`, `scope` (persist the computed scope). New `Variant` contract
  model `{when: ConditionAST-or-raw, text}`. Keep numeric `id` only as a transitional
  alias (`id: N` → `key: "condN"`); read `key` everywhere downstream.
- New `parse_variants_csv(path) -> {placeholder: [variant], default}` using stdlib
  `csv`. Validates: exactly one default per placeholder, ≥1 non-default row, all rows'
  `when` parse + validate via Phase 0, single shared scope per placeholder.
- Contract-validation update so YAML shape checks accept the new keys.

### Phase 2 — Leg 0 detection + CSV stub
- `extract_conditionals` (`leg0_ingest.py:403`) / `_find_top_level_brackets` (`:372`):
  recognise `[[$token]]` — record `placeholder=token`, mark block as variant.
  Validation: a variant token must be a single bare identifier (warn + treat as literal
  binary if it has spaces/punctuation).
- `annotate_conditionals` (`:447`): append `$doc.<key>` instead of `$doc.condN` (§1a) —
  the author token for variant blocks, a stable auto-name for untokenised binary blocks.
  Validate key uniqueness + identifier-safety here, while assigning.
- `write_conditional_form` (`:748`): for a variant block emit a pointer block
  ("Block N — variant placeholder `$stateClause`: fill `<stem>.variants.csv`") instead
  of a `Condition:` line. Binary blocks unchanged.
- New `write_variants_csv_stub(blocks, stem, out)` — header row + one pre-filled
  `placeholder` row per token + an example default row + a top-of-file instructions
  comment.

### Phase 3 — parse step wiring
- `parse_conditional_form` (`leg0_ingest.py:796`): after parsing the `.md`, auto-detect
  a sibling `<stem>.variants.csv`; if present, run Phase 1's normaliser and merge
  `variants`/`default`/`placeholder`/`scope` into the matching block ids. Surface any
  DSL/validation errors as a report (don't write a half-valid registry).
- No new CLI flag needed — `--parse-conditional-form` picks up the sibling CSV. (Add an
  explicit `--variants-csv <path>` override for non-standard locations.)

### Phase 3b — Leg 3 named-key collapse (§1a)
- `_COND_BLOCK_RE` (`leg3_substitute.py:316`) and `build_cond_map` (`:101`): match
  `$doc.<key>` (identifier, not just `cond\d+`) → `${data.<key>}`. `apply_cond_substitutions`
  (`:110`) phase-0 `#if($doc.condN)` guard rewrite → `#if($doc.<key>)`.

### Phase 4 — Leg 4 N-way codegen + key simplification
- Emit `put("<key>", …)` and `String <key> = "";` using the registry `key` (§1a).
- **Delete the renumbering path** for named keys: `_parse_existing_cond_high_water`
  (`:647`) + `_diff_keys` id-offset (`:776`) → additive merge by name set-union (a
  repeated key across forms is a *conflict to report*, not a silent renumber).
- `render_conditional_puts` (`leg4_generate_plugin.py:1034`): branch on
  `block.variants`. New helper `_render_variant_puts(block, scope, field_lookup)`:
  - hoist switch-field accessor once when the switch-sugar condition holds;
  - emit `String condN = "";` then ordered `if/else if` from
    `condition_to_java(variant.when)`, each body `condN = <_source_text_to_java(text)>;`
    (reusing field wiring per variant);
  - trailing `else { condN = <default-or-""> }`;
  - `renderingData.put("condN", condN);`.
- Scope handling: a variant block whose scope ≠ current overload emits the empty put
  (same rule as binary, `:1034` docstring D6).
- `render: template` blocks with `variants` → **hard error** (a loop/Boolean block
  can't be a text selector), consistent with existing refusals.
- Additive/high-water (`:647`, `:776`) — no change; one key per block.

### Phase 5 — tests + fixtures
- New fixture `TestStateDisclosure(segment)` in `tools/generate_test_fixtures.py`: a
  doc with `[[$stateClause]]`, plus a companion `variants.csv` seed (3–4 states +
  default) — add to `ALL_FIXTURES` (`run_test_pipeline.py`) and seed file.
- **Field tokens inside the conditional text — mandatory coverage.** At least one
  variant `text` MUST embed a field placeholder, e.g.
  `[[Your policy {quote.quoteNumber} is approved in California.]]` /
  `text: "Your policy {quote.quoteNumber} is approved in California."`. Assert the
  generated branch body concatenates the accessor, not the literal token:
  `condStateClause = "Your policy " + Objects.toString(quote.quoteNumber(), "") + " is approved in California.";`
  Cover both axes so the per-variant wiring (`_source_text_to_java` called inside each
  `if` body) is exercised:
  - **system field** (`{quote.quoteNumber}` → quote overload) and **custom field**
    (`{policy.data.*}` → segment) — the two supported wiring categories;
  - an **unsupported** field (per-exposure `{item.*}` or DataFetcher-sourced) → assert
    it stays literal with a `// TODO` comment + a WARN row in the plugin report, exactly
    as the binary path does today (`leg4` "Field tokens inside conditional blocks" §).
  - a field token in the **default/else** row, not just a conditioned variant.
- Also add a **binary** regression asserting `[[text here {quote.quoteNumber}]]` (no
  `$token`, untokenised) still bakes the concat — confirms §1a's named-key switch didn't
  break the existing field-in-conditional behaviour (already exercised loosely by
  `TestRenewalNotice`/`TestGiftSchedule`, but pin it with an explicit assertion).
- Extend `tests/pipeline/condition_seeds.yaml` (or a new `variant_seeds/`) so `--auto`
  can fill the CSV unattended.
- **Wire compile-check on** for this fixture (the DSL note flags that today's seeds
  generate non-compiling Java with compile-check deliberately off — this feature is the
  reason to turn it on). Assert the if/else-if chain — **with the field concatenation
  inside branch bodies** — compiles against `customer-config.jar`.
- Regression: existing binary-block fixtures (`TestQuoteSummary`, `TestGiftSchedule`,
  …) must produce byte-identical plugins (no `variants` → old path).

---

## 5. Open questions / risks

- **Switch sugar detection** — implement in v1 or defer? Defer is fine; per-row
  independent conditions are correct, just slightly more verbose Java.
- **Excel CSV dialect** — Excel-on-Windows may write `;`-separated or UTF-16/BOM. The
  normaliser should sniff the dialect and strip a BOM. Cheap, do it in Phase 1.
- **Very long disclosures** — if a single variant's text is huge, the baked Java string
  is large but nowhere near javac's 64KB-per-method bytecode limit for 50 assignments.
  Only revisit fragment-file indirection if a real doc proves CSV cells unwieldy.
- **Method size at scale** — 50 states × multiple placeholders in one overload could
  eventually approach the 64KB method limit. Not a v1 concern; note it and add a
  per-block method-extraction escape hatch later if needed.
- **Binary-block migration** — keep the current binary emitter, or route binary blocks
  through the new DSL codegen too? `raw:` fallback makes either safe; decide in Phase 1
  based on how clean the DSL codegen turns out.

---

## 6. Touch list (quick reference)

| File | Change |
|------|--------|
| `velocity_converter/condition_dsl.py` | **new** — grammar, parser, validator, Java codegen |
| `velocity_converter/models.py` | `ConditionalBlock` += `placeholder`/`variants`/`default`/`scope`; new `Variant` |
| `velocity_converter/leg0_ingest.py` | `extract_conditionals` detect `[[$token]]`; `write_conditional_form` variant pointer; new `write_variants_csv_stub`; `parse_conditional_form` merge sibling CSV; new `parse_variants_csv` |
| `velocity_converter/leg4_generate_plugin.py` | `render_conditional_puts` branch on `variants`; new `_render_variant_puts`; route conditions through `condition_dsl`; key off `<key>` not `condN`; **delete** high-water/`_diff_keys` renumbering (merge by name) |
| `velocity_converter/leg3_substitute.py` | `_COND_BLOCK_RE`/`build_cond_map`/guard rewrite match `$doc.<key>` not `$doc.cond\d+` (§1a) |
| `tools/generate_test_fixtures.py` | new `TestStateDisclosure` fixture + CSV seed |
| `tests/pipeline/run_test_pipeline.py` | register fixture; turn compile-check on for it |
| `tests/pipeline/condition_seeds.yaml` | variant seeds |
| `docs/pipeline-dataflow.md` | document the new `.variants.csv` artifact |
