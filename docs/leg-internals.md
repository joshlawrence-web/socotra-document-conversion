# Leg Internals — control-flow per leg

What happens *inside* each leg: the function call order, branch points, and non-obvious
invariants. Read the relevant section before editing a leg, instead of reading the whole
module. Companion docs:

- [pipeline-dataflow.md](pipeline-dataflow.md) — the end-to-end *artifact* flow between legs
- [CODEMAP.md](CODEMAP.md) — the full per-module symbol index (function → line)

Line numbers drift as code changes; `grep -n 'def <name>'` if one looks off.

---

## Leg 0 — `leg0_ingest.py`

```mermaid
flowchart TD
  A["main()<br/>CLI entry"] -->|--parse-conditional-form| B["parse_conditional_form() — 923"]
  A -->|"--input .docx/.pdf (ingest or --scan)"| P["_parse_document()<br/>(writes nothing → ParseResult)"]

  subgraph PD["_parse_document()"]
    C["detect suffix"]
    C -->|.docx| D["convert_docx() — 74"]
    C -->|.pdf| E["convert_pdf() — 137"]
    D --> F["apply_path_map() — 325"]
    E --> F
    F --> G["extract_fields() — 225"]
    G --> H["annotate_fields() — 359"]
    H --> I["extract_conditionals() — 432"]
    I --> J["annotate_conditionals() — 518"]
    J --> K["extract_loops() — 596<br/>(sets render: template)"]
  end

  P --> PD
  PD --> Q{--scan?}
  Q -->|"yes (scan / intake)"| W["_write_human_fill_files()"]
  Q -->|"no (full ingest)"| L["write raw + annotated +<br/>write_leg2_mapping() — 779"]
  L --> W
  W --> M["write_conditional_form() — 821"]
  M --> N["write_variants_csv_stub() — 881<br/>(only if a variant block exists)"]
  B --> O["write_conditional_registry() — 1024"]
```

**Entry:** `main()` — three modes: (1) default ingest (`--input <.docx|.pdf>`) extracts
fields/conditionals/loops and emits annotated HTML + mapping + form; (2) `--input … --scan`
runs the same parse but writes ONLY the human-fill files (conditional-form + variants.csv),
front-loading the customer handoff; (3) `--parse-conditional-form <filled-form.md>` parses
customer responses → conditional-registry.yaml.

**Shared parse:** both ingest and `--scan` call `_parse_document()` → `ParseResult`
(convert → `extract_fields` → `annotate_fields` → `extract_conditionals` →
`annotate_conditionals` → `extract_loops`); it writes nothing. The caller then chooses
which artifacts to persist — full ingest writes machine artifacts + `_write_human_fill_files()`,
scan writes only `_write_human_fill_files()`. The `render: template` flag the form depends on
is set inside `extract_loops`, so scan must run the full parse (not a markup-only regex).

**Inputs → Outputs:** `.docx`/`.pdf` (+ optional `path-map.yaml`) → `.raw.html`,
`.annotated.html`, `.mapping.yaml`, `.conditional-form.md` (+ `.variants.csv` if variants exist);
or filled `.conditional-form.md` + `.variants.csv` → `.conditional-registry.yaml`.

**Key internal stages:**
- `convert_docx()` (74) / `convert_pdf()` (137) — parse paragraphs/tables/text → raw HTML.
- `extract_fields()` (225) — regex-extract `{field}` tokens with occurrence symbols (`$ + *`), dedupe, optionally resolve dotted names via registry.
- `extract_conditionals()` (432) — recursive `[[…]]` matching; detect variant tokens `[[$placeholder]]`, assign stable block IDs, nest children, dedupe keys.
- `extract_loops()` (596) — match `[Name]…[/Name]`; move enclosed fields to loop scope; flip a containing conditional block to `render: template`; emit `#foreach`/`#end`.
- `parse_conditional_form()` (923) — parse filled form + sibling `.variants.csv` → block list with resolved conditions.
- `write_leg2_mapping()` (779) — emit `.mapping.yaml` in Leg 2 contract (variables + loops, top-level/loop field split).

**Invariants / gotchas:**
- **Field token format:** `{field}` + occurrence symbol → deduped, normalized to `$TBD_field` (symbol never appears in output); name conflicts keep the first symbol seen and warn on stderr.
- **Loop field membership** is decided *after* field annotation: a field whose every occurrence is inside `[Name]…[/Name]` moves to that loop; a field used both in and out stays top-level.
- **Conditional with a loop inside** flips to `render: template` — `#if($doc.condN)` wraps the loop in the template and the plugin emits `condN` as a Boolean. Nested loops, or a loop crossing a block boundary, are refused (markers left literal, stderr warning).
- **Variant placeholder dedupe:** `[[$stateClause]]` → placeholder `stateClause`; a colliding placeholder warns and falls back to positional `cond<id>` so registry keys stay unique.
- **Path-map rewrite** runs *before* extraction (non-destructive; the source doc is never modified — the rewrite targets the working HTML).

---

## Leg 1 — `convert.py`

```mermaid
flowchart TD
  main["main() — 1248"] --> convert["convert() — 1166"]
  convert --> sanity["build_sanity_report() — 788"]
  convert --> collect["_collect_mustache_tokens() — 435"]
  collect --> findpair["_find_innermost_pair() — 452<br/>(loop, cap 1000)"]
  findpair -->|pair| procpair["_process_mustache_pair() — 477"]
  procpair --> recvar["_record_var() — 300"]
  procpair --> findpair
  findpair -->|none left| autoloop["auto_detect_loops() — 653"]
  autoloop --> rewrite["rewrite_vars_in_subtree() — 368"]
  rewrite --> recvar
  rewrite --> wrapc["wrap_conditionals() — 689"]
  wrapc --> extractc["extract_conditional_blocks() — 1065"]
  extractc --> linkc["_link_cond_parents() — 1103"]
  linkc --> hints["annotate_loop_hints() — 1047"]
  hints --> dump["dump_yaml() — 1035"]
  dump --> wreg["write_conditional_registry() — 1119"]
  wreg --> wrev["write_conditional_review_md() — 1140"]
  wrev --> wref["write_conditional_ref_html() — 1157"]
```

**Entry:** `main()` (1248) → `convert()` (1166).

**Inputs → Outputs:** HTML with `{{variable}}`, `[name]…[/name]` and `[prose]` annotations →
`.vm`, `.mapping.yaml`, `.report.md` (sanity), `.conditional-registry.yaml`, `.conditional-ref.html`.

**Key internal stages:**
- `_collect_mustache_tokens()` (435) — scan DOM for `[name]`/`[/name]` loop markers.
- `_find_innermost_pair()` (452) / `_process_mustache_pair()` (477) — convert loops innermost-first → `#foreach $iter in $TBD_name`, recording loop fields separately.
- `rewrite_vars_in_subtree()` (368) — `{{var}}` → `$TBD_var` outside loops, with nearest-label context.
- `wrap_conditionals()` (689) — wrap block-level elements bearing `$TBD_*` in `#if(…)…#end`.
- `extract_conditional_blocks()` (1065) — `[prose]` → `$doc.condN`, link parent/child nesting.

**Label inference:** `_record_var()` (300) → `nearest_label()` (131) walks up ≤5 parents for
the first non-empty previous-sibling text; for `<td>`, `nearest_column_header()` (148) reads the
header at the matching column index.

**Invariants / gotchas:**
- Loop pairing is innermost-first with a 1000-iteration safety cap; unconsumed tokens and cross-parent pairs become warnings, not errors.
- Loop-scoped `$TBD_` tokens are prefixed `$iterator.TBD_…` (e.g. `$vehicle.TBD_year`).
- `wrap_conditionals()` skips text already inside a `#foreach` (`_inside_foreach()` 725) to avoid double-guarding.

---

## Leg 2 — `leg2_fill_mapping.py`

```mermaid
flowchart TD
  A["main() — 1444"] --> B["parse_rendering_roots() — 538"]
  B --> C{roots + product valid?}
  C -->|no| Z["blocker .review.md, exit 2"]
  C -->|yes| D["load_schema_index() — 480<br/>load_terminology() — 1407"]
  D --> F["build_registry_index() — 252"]
  F --> G["annotate_mapping() — 1284"]
  G --> H["per variable — 1320"]
  H --> I["derive_variable_candidate() — 604"]
  I --> I1["_quote_accessor_candidate() — 379"]
  I1 --> I2["match_token() — 450<br/>exact | ci | terminology"]
  I2 --> I3["check_scope() — 321"]
  I3 --> J["per root: variable_verdict_for_root() — 877"]
  J --> J1{DataFetcher?}
  J1 -->|yes| J2["_datafetcher_verdict() — 744"]
  J1 -->|no| J3["classify_path() — JAR probe"]
  J2 --> J4["confidence_grade() — 589"]
  J3 --> J4
  J4 --> K["apply_feature_gate() — 850"]
  K --> L["per loop: suggest_loop_root() — 988<br/>loop_root_verdict_for_root() — 1210"]
  L --> M["per loop field: suggest_loop_field() — 1109<br/>loop_field_verdict_for_root() — 1240"]
  M --> N["reorder_top_keys() — 1184"]
  N --> P["validate_contract() → write .mapping.yaml"]
  P --> R["_write_review_md() — review_writer"]
```

**Entry:** `main()` (1444) → `annotate_mapping()` (1284).

**Inputs → Outputs:** `<stem>(root).mapping.yaml` + `path-registry.yaml` (optional
`terminology.yaml`, `sdk-schema-index.yaml`) → enriched `<stem>.mapping.yaml` (schema 2.0) + `.review.md`.

**Matching pipeline (per variable):**
1. `derive_variable_candidate()` (604) — root-independent name match via `match_token()` (450): exact `Entity.field` → case-insensitive → terminology synonym; `_quote_accessor_candidate()` (379) handles direct `quote.data.*`. `check_scope()` (321) gates by required `#foreach` iterator. Terminal candidates (no match / scope violation / ambiguous) skip JAR probing.
2. `variable_verdict_for_root()` (877), per root — DataFetcher lifecycle gate (`_datafetcher_verdict()` 744) **or** `classify_path()` JAR probe on the reprefixed path.
3. `apply_feature_gate()` (850) — demotes verdicts (clears `data_source`, `sdk_status: feature_gated`) when a `requires_feature` flag is disabled.

Loops: `suggest_loop_root()` (988) does exact iterable-name lookup → list velocity + iterator;
`suggest_loop_field()` (1109) parses `$ITER.TBD_FIELD` and matches an exposure field or a coverage
via `_match_coverage_field()` (1048, prefix decomposition e.g. `medpay_limit` → `MedPay.limit`).

**Verdict + confidence:**
- `confidence_grade()` (589): `high` only when `match_step == exact` AND `sdk_status == verified`; else `low`/`none`.
- DataFetcher verdicts bypass the direct-path probe; lifecycle gate may demote to low.
- Feature-gated paths → `confidence: low`, `sdk_status: feature_gated`, empty `data_source`, **across all roots** (document-scoped).
- Sibling-only matches → `confidence: medium` with the sibling path as `data_source`.

**Invariants / gotchas:**
- Strict schema-index validation: tokens must be `Entity.field` dotted; old `{FIELDNAME}` or unknown entity/field → terminal, `next-action: fix-token`.
- Quote-accessor candidates carry `no_reprefix: True` — `quote.data.field` is terminal and not reprefixed to a root prefix.
- Scope violation is terminal (`next-action: restructure-template`) — never escalated by a JAR probe.
- Loop-field verdicts cache the iterator element type per (root, list_velocity) to avoid redundant JAR walks.

---

## Leg 3 — `leg3_substitute.py`

```mermaid
flowchart TD
  A["main() — 691"] --> B["_load_yaml() — 64"]
  B --> C["_flatten_to_primary_root() — 230"]
  C --> D["build_substitution_map() — 265"]
  D --> E["build_foreach_map() — 292"]
  E --> F["_load_cond_registry() — 72"]
  F --> G["build_cond_map() — 102"]
  G --> H["process_vm() — 338"]
  H --> I["apply_cond_substitutions() — 115"]
  I --> J["split_delegated() — 175"]
  J --> K["write_report() — 451"]
  K --> L["write .final.vm + .leg3-report.md"]
```

**Entry:** `main()` (691).

**Inputs → Outputs:** enriched `.mapping.yaml` (+ optional `.conditional-registry.yaml`) + the
Leg 1 `.vm` → `.final.vm` + `.leg3-report.md`.

**Key internal stages:**
- `build_substitution_map()` (265) — `{$TBD_*: data_source path}` from variables + loop fields.
- `build_foreach_map()` (292) — loop placeholder → `#foreach` directive (where both data_source and foreach exist).
- `build_cond_map()` (102) — `$doc.condN` → `${data.condN}`.
- `process_vm()` (338) — strip `#if($TBD_*)` guards, substitute resolved tokens, replace foreach placeholders.
- `apply_cond_substitutions()` (115) — multi-pass innermost-first resolution of `[[…]]$doc.condN` blocks.
- `split_delegated()` (175) — separate tokens that live only inside conditional blocks (plugin-wired) from template-resolved tokens.

**Invariants / gotchas:**
- Unresolved tokens (`$TBD_*` with empty data_source) stay verbatim in the output and are listed in the report.
- `$doc.condN` → `${data.condN}` because the **plugin owns conditional text**; the template only emits the resolved block string.
- Tokens inside `[[…]]$doc.condN` blocks are *delegated to Leg 4* — they don't appear in `.final.vm`, only in the report.
- `#if($TBD_*)` guard wrappers are stripped entirely; nested `#if`/`#foreach` inside them are preserved with substitution.
- Schema 2.0 mapping promotes per-root verdicts to flat fields via the primary root; schema 1.x passes through unchanged.

---

## Leg 4 — `leg4_generate_plugin.py`

```mermaid
flowchart TD
  A["main() — 1691<br/>(loop over --suggested forms)"] --> C["_process_form() — 1729"]
  C --> D["load .mapping.yaml + extract product"]
  D --> F{java_path exists?}
  F -->|no — fresh| I["_flatten_to_segment_root() — 582"]
  I --> J["_collect_datafetcher_calls() — 975"]
  J --> K["load_conditional_registry() — 1049"]
  K --> L["_build_cond_field_lookup() — 205<br/>_augment_field_lookup_for_variants() — 320"]
  L --> M["_analyse_cond_fields() — 400"]
  M --> N{unresolved field?}
  N -->|yes| O["❌ hard-fail (run Leg 2)"]
  N -->|no| P["render_java() — 1383"]
  F -->|yes — additive| Q["parse_plugin_keys() — 749"]
  Q --> R["_required_keys() — 840"]
  R --> S["_diff_keys() — 873 (offset cond ids)"]
  S --> T["_append_to_plugin() — 898"]
  P --> V["render_conditional_puts() — 1244"]
  T --> V
  V --> W["render_occurrence_guards() — 482"]
  W --> X["write .java"]
  X --> Y["validate_path() per resolved var"]
  Y --> Z{--compile-check?}
  Z -->|yes| AA["compile_check() — 1666 (javac)"]
  Z -->|no| AC
  AA --> AC["write_report() — 1428"]
```

**Entry:** `main()` (1691) → `_process_form()` (1729), called once per `--suggested` form.

**Inputs → Outputs:** one `.mapping.yaml` (+ `.conditional-registry.yaml`) per form → one
`{Product}DocumentDataSnapshotPluginImpl.java` (fresh or appended) + one `.plugin-report.md` per form.

**Generation stages:**
1. `_flatten_to_segment_root()` (582) — schema 2.0 per-root verdicts → segment root.
2. `_collect_datafetcher_calls()` (975) — DataFetcher vars per scope (quote & policy).
3. `load_conditional_registry()` (1049) → `_build_cond_field_lookup()` (205) + `_augment_field_lookup_for_variants()` (320) → `_analyse_cond_fields()` (400).
4. `render_java()` (1383) or `_append_to_plugin()` (898) — assemble the `.java`.
5. `render_conditional_puts()` (1244) — binary + variant `if/else-if/else` chains.
6. `render_occurrence_guards()` (482) — null/empty checks for required & one_or_more.
7. `validate_path()` (javap-walk) → `compile_check()` (1666, optional) → `write_report()` (1428).

**Fresh vs additive vs multi-form:**
- **Fresh** (no existing `.java`): `render_java()` writes a complete file.
- **Additive** (`.java` exists): `parse_plugin_keys()` (749) reads existing keys + conditional high-water mark; `_diff_keys()` (873) computes missing keys and offsets conditional IDs past the high-water mark; `_append_to_plugin()` (898) inserts only the missing puts (a `.java.bak` is written first).
- **Multi-form:** each form runs `_process_form()` sequentially — first writes/appends, each subsequent merges additively into the same `.java`.
- **Named variant blocks** merge by `block_key()` (name-based) — no positional renumber; a duplicate name is a logged conflict.

**Conditional / variant / occurrence handling:**
- **Binary block:** `String cond<id> = ""; if (<java_cond>) { cond<id> = <baked_text>; }`.
- **N-way variant** (`_render_variant_puts()` 1184): `if (<cond0>) {…} else if (…) {…} else { <default> }`, first match wins.
- **Field tokens inside blocks** → in-scope fields wired as Java accessor concat (`Objects.toString(policy.data().lastName(), "")`); unresolved field inside a block **hard-fails** (run Leg 2); unsupported (per-exposure/account/DataFetcher) → `// TODO` + WARN row.
- **Occurrence guards:** required/one_or_more vars add to `missingRequired`; throw `IllegalStateException` before returning `renderingData`.
- **Scope blocking:** a quote-scoped condition in the policy overload (or vice-versa) renders an empty put; mixed-scope blocks render empty in both overloads.

**Invariants / gotchas:**
- Conditional-ID renumber is form-local and positional for binary blocks; named variants never renumber.
- Occurrence guard names are tracked in the existing `.java` so additive re-runs don't double-guard.
- DataFetcher calls are deduped per root and skipped when the root isn't in `valid_roots`; the legacy `pricing` key is always skipped for quote.
- `segment` is optional in the policy overload (`.orElse(null)`) — a missing segment warns but does not fail.
