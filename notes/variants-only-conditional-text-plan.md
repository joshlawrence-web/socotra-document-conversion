# Implementation plan — variants-only conditional text (retire the conditional form)

**Status:** IMPLEMENTED (2026-06-17) — all of §2.1–2.9 landed; test suite green
(8 fixtures + Leg 4). `variants.csv` (human) + `conditional-blocks.yaml` (machine
sidecar) replace `conditional-form.md`; legacy `--parse-conditional-form` retained
for in-flight forms. Decision B resolver + Leg -1 `--variants-csv` pass 2 shipped.
**Supersedes the "Decision" in:** [variants-only-conditional-text.md](variants-only-conditional-text.md)
(that doc is the idea + motivating bug; this is the actionable plan).
**Owner:** Josh
**Goal:** make `variants.csv` the single human-fill file for *all* conditional text.
Binary `[[text]]` blocks fold into the variant mechanism as a one-real-row + empty-default
group. The conditional form (`<stem>.conditional-form.md`) goes away. One mechanism, one
parser, one emit path, one Leg 4 generator.

---

## 0. Two decisions locked before scoping the work

These were open questions in the idea doc; they are now decided and drive the plan.

### Decision A — loop-in-conditional IS supported (as a `when`-only CSV row, NOT a gap)

Originally scoped as an accepted gap ("conditional text can't contain a loop"). **Reversed
2026-06-17** — it collapses cleanly because the loop's text never needs to live in a CSV
`text` cell. A `render: template` block (e.g. `TestGiftSchedule` — `[Item]…[/Item]` inside
`[[…]]`) needs three things, all already handled, none requiring the `text` column:

1. **Leaves inside the loop** (`{item.data.itemTypeCode}`) are authored **in the docx**, so
   Leg -1 pass 1 already scans + loop-scopes them today (`legminus1_resolve_paths.py:90-107`,
   `_loop_spans`/`_loop_for_position`). Doc-resident — the CSV never touches them.
2. **Loop scaffold + surrounding prose** stay in the `.vm` via `render: template`: Leg 0
   flips it (`leg0_ingest.py:690`), Leg 3 keeps the `#if` (`leg3_substitute.py:133`), Leg 4
   emits a Boolean and `_analyse_cond_fields` skips it (`leg4_generate_plugin.py:416`).
   Already works end-to-end.
3. **The condition (Boolean)** is the only human input. Today it's a `Condition:` line in the
   conditional form; in variants-only it becomes a **`when` cell** — the same shift binary
   blocks make.

**So a template block = a `when`-only CSV row** (`placeholder` + `when`, **text blank/locked**
because the text lives in the `.vm`). Symmetric with binary folding; the only difference is
binary fills `text`, template leaves it empty. No special-case form survives, no gap.

Work this adds (small, folded into §2.1/§2.3):
- Leg 0 emit: for a `render: template` block, write a CSV stub row pre-marked template
  (blank/locked text), customer fills only `when`. Leg 0 already detects template blocks at
  scan time.
- CSV parse: `parse_variants_csv` must accept a template-marked row **without** requiring
  `text`/default (its current "default + ≥1 conditioned row" check needs a template branch),
  and carry the `render: template` flag CSV → registry.
- Downstream (registry → Leg 3 → Leg 4) already handles `render: template` — zero change.
- `TestGiftSchedule` **stays** and becomes the regression guard for the template-as-CSV-row
  path.

**The one genuinely-unsupported edge** (document, don't fix): an **N-way** block whose
variants each carry their **own loop** (different loop-bearing wording per condition). Loop
bodies can't live in CSV `text` cells and `render: template` is binary show/hide, not N-way.
Vanishingly unlikely. Document in CLAUDE.md (Leg 0 "Loop inside a conditional" section) +
`docs/leg-internals.md` + the CSV header comment Leg 0 emits.

### Decision B — bare leaves in variant text get the same human-in-the-loop resolution as doc leaves

Variant `text` is authored in the CSV **after** Leg -1 has run, so the leaves in it were
never seen by Leg -1's scan (the source doc only held `[[$token]]`, no text). Today those
bare leaves silently degrade to `// TODO` + WARN in Leg 4 (`leg4_generate_plugin.py:349`).

**Resolution model (decided):** mirror the existing `path-review.md` flow exactly —
auto-fill the confident registry match into a `Final:` line as the default, list ranked
alternatives / leave an empty `Final:` for ambiguous and unmatched leaves, let the human
edit, then **re-run the form** to re-parse. Reuse Leg -1's resolver + review machinery;
do not invent new resolution logic.

Because variant text post-dates the up-front intake package, this is a **second,
conditional resolution moment** (see §3) — only triggered when the returned CSV contains
bare leaves. Full accessors / no field tokens → skipped entirely.

---

## 1. What already works (do NOT rebuild)

- **Leg -1 already scans leaves inside inline `[[…]]` doc text.** `collect_placeholders()`
  (`legminus1_resolve_paths.py:121`) runs `_FIELD_RE` over the whole doc as flattened
  plain text — brackets are invisible to it, so a `{leaf}` inside a `[[…]]` block authored
  *in the source doc* is resolved like any other. Inline conditional text is covered today.
  The gap is **only** text authored in the CSV (Decision B).
- **Leg 3 is already block-type-agnostic.** `build_cond_map` / `apply_cond_substitutions`
  (`leg3_substitute.py:102,115`) resolve `$doc.<key>` → `${data.<key>}` identically for
  binary and variant blocks via the `key` join field. **No Leg 3 changes needed.**
- **`condition_dsl.parse_variants_csv`** (`condition_dsl.py:694`) already parses
  `placeholder,when,text` rows, validates one-default-per-placeholder, detects mixed scope.
  Empty-default round-trip needs *confirming* (test), likely already works.
- **Leg 4 variant generator** (`_render_variant_puts`, `leg4_generate_plugin.py:1184`)
  already emits the if/else-if chain + default. Binary blocks fold into it.

---

## 2. Work breakdown (with touchpoints)

Ordered cheapest→riskiest. Leg 3 is intentionally absent — no change.

### 2.1 Leg 0 emit — one CSV writer for all blocks  *(low–med)*
- Merge `write_conditional_form()` (`leg0_ingest.py:828`) into the CSV writer
  `write_variants_csv_stub()` (`leg0_ingest.py:888`).
- For each **binary** `[[…]]` block: auto-generate a placeholder key (`cond1`, `cond2`, …),
  pre-fill the `text` cell from the doc text, emit a 2-row stub (one `when` row to fill +
  one empty-default row). Customer fills only `when`.
- For each **`render: template`** block (Decision A): emit a `when`-only stub row, placeholder
  auto-keyed like binary, **text blank/locked** + a template marker. Customer fills only
  `when`. Leg 0 already knows the block is template at scan time (`extract_loops`).
- Stop calling the form writer in `_write_human_fill_files()` (`leg0_ingest.py:1128`,
  calls at `:1141`/`:1146`) and in both `main()` modes (`:1282`, `:1301`).
- Add the CSV header comment documenting the one unsupported edge (N-way block with
  per-variant loops — Decision A).

### 2.2 Schema — universal variant shape  *(med)*
- `ConditionalBlock` (`models.py:328`): make `variants[]`+`default`+`placeholder`+`scope`
  the universal representation; deprecate `conditions[]`+`operator` (binary-only fields).
  Keep a compatibility read-path for old artifacts, or ship a converter (§2.7).
- `write_conditional_registry()` (`leg0_ingest.py:1037`) — no signature change, just
  serializes the unified structure.

### 2.3 Parse — delete the binary regex, unify on CSV  *(med)*
- `parse_conditional_form()` (`leg0_ingest.py:930`): delete the binary block_re
  (`:956`, the DOTALL body-capture that *was* the motivating bug). Variant + CSV-merge
  path (`:1002`–`:1032`) becomes the only path.
- Confirm empty-`when` / empty-default rows round-trip through `parse_variants_csv`
  (`condition_dsl.py:740`).
- Add a **template-row branch** to `parse_variants_csv` (`condition_dsl.py:694`): a
  template-marked row has `when` but no `text`/default — skip the "default + ≥1 conditioned
  row" validation for it and carry the `render: template` flag through to the registry.

### 2.4 Leg 4 — fold binary into the variant generator + Decision B resolver  *(high)*
- Delete `_render_binary_puts`; route binary blocks through `_render_variant_puts`
  (`leg4_generate_plugin.py:1184`). `render_conditional_puts` (`:867` binary path) collapses.
- `_analyse_cond_fields` (`:400`): binary-text fields now analyzed like variant-text fields.
- **Decision B core:** run variant-text `{leaf}` through Leg -1's registry resolver before
  `_registry_accessor_to_velocity` (`:291`) / `_augment_field_lookup_for_variants` (`:320`).
  Replace the silent `// TODO`+WARN degradation (`:349`) with: resolved → bake accessor;
  ambiguous/unmatched → route into the §2.6 review (not a silent skip).

### 2.5 Routing / UI / MCP — drop the form file  *(low)*
- `workspace.py:35` `ACTION_NEEDED_SUFFIXES` — remove `.conditional-form.md`.
- `agent_tools.py` `_predict_writes` (`:204`,`:214`) — predict `variants.csv`, not the form.
  Also `run_legminus1_apply` prediction (`~:400`).
- `tools/demo_ui.py` — `FILL_SUFFIXES` (`:51`) + ~15 form refs (`:62`,`209`,`226`,`233`–`237`,
  `337`,`339`): variant-only fill flow.
- `mcp_server.py` `ingest_document` (`~:236`) — output-file list.

### 2.6 Variant-text leaf review (Decision B) — idempotent Leg -1, run twice  *(med)*

Do **not** build a bespoke variant-text scanner. Make Leg -1's existing scan idempotent
and feed `variants.csv` text into it as a second input source, then fire the same machinery
at both ends of the customer fill. The second firing surfaces only net-new leaves.

- **`variants.csv` text becomes a second text source for `collect_placeholders`**
  (`legminus1_resolve_paths.py:121`). Leg -1 already scans flattened plain text, so the CSV
  `text` cells are just more text — concatenate/append them to the doc text before the scan.
  No new resolver, no new review format; reuse `run_suggest` + `write_path_review` +
  `parse_path_review` wholesale.
- **Dedup against the already-resolved `path-map.yaml`.** Any leaf that already carries a
  confident `Final:` accessor from pass 1 is carried forward **silently**; only net-new
  leaves (those the customer introduced in the CSV text) surface into the review. This is
  the "don't re-warn already-picked-up leaves" behavior — keyed on the existing path-map
  entry. `run_apply` already diffs parsed `Final:` against the original path-map to detect
  edits (`legminus1_resolve_paths.py:461`), so the dedup hook is half-built.
- **Fire at both ends, same code path:**
  1. **Pass 1 (intake):** Leg -1 over the docx → `path-review.md` (doc-body + binary-text
     leaves; binary text is in the doc so it's caught here already).
  2. **Pass 2 (after CSV returns):** Leg -1 over docx **+ filled `variants.csv`**, dedup vs
     pass-1 path-map → review delta containing only the N-way variant-text leaves.
  - This is unavoidable, not a design choice: N-way variant text doesn't exist at intake
    (the doc holds only `[[$token]]`), so its leaves can't be discovered until pass 2. The
    idempotent rerun makes pass 2 painless rather than a separate mechanism.
- **"Run the form again"** = re-parse the edited pass-2 review → fold resolved accessors
  into the CSV text / path-map before Leg 4 wires them.
- **Pass 2 self-skips** when the rerun surfaces no net-new leaves (full accessors / no field
  tokens in the CSV) — the dedup naturally yields an empty delta, no human touch needed.
- **Not chosen — single-round reorder:** emitting the CSV stub first, customer fills variant
  text, then one combined Leg -1 over docx+CSV. Gives one review round but the customer fills
  variant text "blind" (no accessor help) and doc-body review is delayed. Rejected: doc body
  is the bulk and deserves up-front help; variant-text additions are the exception.

### 2.7 Backward compatibility  *(low)*
- Old `.conditional-form.md` files exist in customer hands. Either keep
  `--parse-conditional-form` as a legacy reader, or ship a one-shot
  `conditional-form.md → variants.csv` converter. Decide based on whether any in-flight
  customer is mid-fill.

### 2.8 Tests  *(med)*
- `tests/pipeline/condition_seeds.yaml` (binary block→condition map) → migrate to CSV-row
  seeds, or keep legacy form support for the harness.
- `run_test_pipeline.py`: `_autofill_form` (`~:80`–`97`) becomes CSV-row generation;
  variant seeding (`~:171`–`174`) merges with it; form path/validation (`~:155`–`167`).
- Fixtures in `tools/generate_test_fixtures.py` unchanged in shape. `TestGiftSchedule`
  (loop-inside-conditional) **stays** — it becomes the regression guard for the
  template-block-as-`when`-only-CSV-row path (Decision A). Add a fixture with a bare leaf in
  variant text to exercise Decision B resolution (pass-2 dedup).
- `TestVariantThenBinary` (the regression fixture for the original bug) stays — under
  variants-only, both blocks parse through one path, which is the whole point.

### 2.9 Docs sweep  *(low, wide — ~60 refs / 8–10 files)*
- CLAUDE.md, AGENTS.md, README.md, `docs/pipeline-dataflow.md`, `docs/leg-internals.md`,
  `docs/CODEMAP.md`, `docs/demo-story.md`. Update the four-stage flow, intake package
  description (three fill files → two), and add the Decision A loop-gap limitation.

---

## 3. Flow before vs. after

**Before** (three fill files): `path-review.md` + `conditional-form.md` + `variants.csv`.

**After** (two fill files, with a conditional third touch):
1. Intake → Leg -1 pass 1 → `path-review.md` (doc-body + binary-text leaves) +
   `variants.csv` stub (all blocks).
2. Customer fills both, returns them.
3. Leg -1 **pass 2** over docx + filled `variants.csv`, dedup vs pass-1 path-map → review
   delta of net-new N-way variant-text leaves. **Self-skips when the delta is empty**
   (full accessors / no field tokens). Customer confirms any delta, re-run.
4. Parse → conditional-registry → Leg 2/3/4.

> Honest note: §2.6 pass 2 can re-introduce a second human touch for conditional text — so
> the "one touchpoint" win is "one *up-front* file + a follow-up only when the rerun finds
> net-new leaves," not an absolute single touch. It's the **same Leg -1 machinery** both
> times, and the dedup makes step 3 vanish when there's nothing new. Encouraging full
> accessors in CSV text keeps step 3 rare.

---

## 4. Effort estimate

~2–3 days: ~1 day mechanical (§2.1/2.2/2.3/2.5; Leg 3 free), ~1 day §2.4 (Leg 4 fold +
wiring the resolved accessors), ~0.5–1 day §2.6 + §2.8 tests + §2.9 docs. §2.6 is cheaper
than first scoped — reusing Leg -1's scan + review + apply (idempotent rerun + path-map
dedup) instead of a bespoke variant-text resolver removes most of its net-new code.

Decision B (§2.4/§2.6) has standalone value — feeding `variants.csv` into Leg -1's scan
fixes the silent bare-leaf degradation that bites variant text *today*, independent of
retiring the form. Ship it first (see §5).

---

## 5. Suggested landing order

1. **First, independent of the refactor:** Decision B resolver for variant text (§2.6 +
   the §2.4 resolver change). Ships value now, de-risks the big change.
2. Leg 0 emit + schema + parse unification (§2.1–2.3), including the template `when`-only row
   (Decision A), then Leg 4 fold (§2.4).
3. Routing/UI/MCP (§2.5), tests (§2.8), docs (§2.9, incl. the one unsupported edge),
   back-compat (§2.7).
