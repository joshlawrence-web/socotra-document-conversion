# Plan — Fix the variants-only test fallout

**Branch:** `feat/multi-variant-conditionals`
**Owner:** (handoff to another agent)
**Status:** not started

## Background

Commit `9499c87 "feat(conditionals): variants-only conditional text — retire
conditional-form.md"` migrated Leg 0 from the old `conditional-form.md` hand-fill
flow to the single `variants.csv` flow. It removed two functions from
`velocity_converter/leg0_ingest.py`:

- `write_conditional_form(blocks, stem, path)` — **deleted**
- `write_variants_csv_stub(blocks, stem, path)` — **renamed** to
  `write_variants_csv(blocks, stem, output_path)`

`parse_conditional_form(...)` was **kept** (legacy `--parse-conditional-form`
path), so imports of *that* name are still valid.

Several regression tests were not migrated, so they reference the deleted names.
This is leftover work from that commit — **not** related to the Leg -1
quote-vs-policy ambiguity fix (`registry_match.py`) that shipped alongside it.

### Current failures (verified on this branch, independent of the Leg -1 fix)

3 **collection errors** (whole module won't import — `ImportError:
write_conditional_form`):
- `tests/regression/test_leg0_variants.py`
- `tests/regression/test_leg0_loops.py`
- `tests/regression/test_cond_field_tokens.py`

4 **assertion failures** (assert retired behavior):
- `tests/regression/test_leg0_scan.py::TestScanMode::test_scan_emits_only_human_fill_files`
- `tests/regression/test_leg0_scan.py::TestScanMode::test_binary_only_fixture_has_no_variants_csv`
- `tests/regression/test_leg0_scan.py::TestScanMode::test_scan_forms_match_full_ingest`
- `tests/regression/test_leg4_variants.py::TestVariantCodegen::test_template_plus_variants_hard_error`

## The variants-only API (what tests should target now)

Old round-trip (gone):
```
blocks = extract_conditionals(...)
write_conditional_form(blocks, stem, form_path)   # write hand-fill
# (fill Condition: lines in the .md)
blocks = parse_conditional_form(form_path, registry=...)   # read back
```

New round-trip:
```
blocks = extract_conditionals(...)
write_variants_csv(blocks, stem, csv_path)              # human-fill file
write_conditional_blocks(blocks, sidecar_path)          # machine sidecar
# (fill the `when` column in the .csv)
meta   = load_conditional_blocks(sidecar_path)
blocks = parse_variants_csv_to_blocks(csv_path, meta, registry=...)  # read back
```

Relevant signatures (all in `velocity_converter/leg0_ingest.py`):
- `write_variants_csv(blocks: list[dict], stem: str, output_path: Path) -> None`
- `write_conditional_blocks(blocks: list[dict], output_path: Path) -> None`
- `load_conditional_blocks(path: Path) -> list[dict]`
- `parse_variants_csv_to_blocks(csv_path, blocks_meta, registry=None, *, classpath=None, product=None) -> list[dict]`
  — raises `ValueError` on any CSV/DSL/scope validation error.
- `parse_conditional_form(...)` — still present (legacy); fine to keep importing
  if a test deliberately exercises the legacy path, but prefer migrating.

The CSV writer pre-fills one conditioned row + one default row per block. For a
hand-fill simulation, write the `when` cell(s) directly into the CSV text (mirror
how `tests/pipeline/run_test_pipeline.py` builds CSVs from
`tests/pipeline/condition_seeds.yaml` — reuse that pattern rather than inventing a
new CSV string format).

## Tasks

### Task 1 — `test_leg0_variants.py` (collection error)
- Imports `write_conditional_form` (deleted) and `write_variants_csv_stub`
  (renamed). Usage: L86 `write_conditional_form`, L97/L109 `write_variants_csv_stub`,
  L123/140/147 `parse_conditional_form`.
- Replace `write_variants_csv_stub` → `write_variants_csv` (same arg shape:
  `(blocks, "Demo", out_path)`).
- The L86 test asserts the old "conditional-form variant pointer" — drop it or
  rewrite to assert the equivalent `variants.csv` content (the `$token` row).
- For the parse tests (L123/140/147): migrate to the
  `write_conditional_blocks` + `parse_variants_csv_to_blocks` round-trip, OR keep
  `parse_conditional_form` only if the intent is to guard the *legacy* path
  explicitly (note that in a docstring if so). Preferred: migrate.
- Update the module docstring (L1-6) which still says "conditional-form variant
  pointer".

### Task 2 — `test_leg0_loops.py` (collection error)
- Imports `write_conditional_form` + `parse_conditional_form` (L24-25); usage at
  L218-225 is a write→parse round-trip on a `.conditional-form.md`.
- Migrate that round-trip to the variants.csv + sidecar flow (Task-1 pattern).
- This module also tests loop-in-conditional (`render: template`) — make sure the
  migrated round-trip still exercises the template block becoming a `when`-only
  row (variants-only plan "Decision A").

### Task 3 — `test_cond_field_tokens.py` (collection error)
- Imports `write_conditional_form` + `parse_conditional_form` (L20-21); usage at
  L345-346 (write+parse) and L368-370 (parse only).
- Migrate both round-trips to variants.csv + sidecar.
- These tests cover field tokens inside conditional blocks (Leg 4 wiring) — keep
  the assertions about baked Java accessors; only the produce-blocks step changes.

### Task 4 — `test_leg0_scan.py` (3 assertion failures)
- The scan flow no longer writes `conditional-form.md`; `_write_human_fill_files`
  now writes only `{stem}.variants.csv` (see `leg0_ingest.py:1220`).
- `test_scan_emits_only_human_fill_files` (L40-46): drop the
  `assertIn(f"{stem}.conditional-form.md", names)` assertion; keep the
  `variants.csv` + no-machine-artifacts assertions.
- `test_binary_only_fixture_has_no_variants_csv` (L48-53): the premise is now
  wrong — under variants-only, a binary-only fixture DOES get a `variants.csv`
  (binary blocks are a 2-row fold in the same CSV). Rewrite to assert the
  binary-only fixture produces a `variants.csv` (and no `conditional-form.md`), or
  delete if redundant with Task-4 first test. Confirm against the actual
  `_write_human_fill_files` behavior before settling the assertion.
- `test_scan_forms_match_full_ingest` (L55-78): drop `conditional-form.md` from
  the compared filenames; compare only `variants.csv` byte-for-byte.
- Update module docstring (L1-9) — it still describes "conditional-form.md +
  variants.csv".

### Task 5 — `test_leg4_variants.py::test_template_plus_variants_hard_error`
- Asserts `render_conditional_puts` raises `ValueError` for a `render: template`
  block that also has `variants`. Under variants-only this is **no longer an
  error**: a template block legitimately carries its single `when` as a one-entry
  `variants` payload, and `render_conditional_puts` routes it to
  `_render_template_put` (see `leg4_generate_plugin.py:1351-1356`).
- Rewrite the test to assert the *new* behavior: a `render: template` block with a
  one-entry `when` produces a Boolean put (e.g. assert the generated Java contains
  `renderingData.put("stateClause", ...)` with the boolean expression from the
  `when`, and does NOT throw). Use `_render_template_put`'s output shape as the
  oracle. Update the class docstring (L5) which references "the render:template +
  variants hard error".

## Verification

```
python3 -m pytest tests/regression/ -q
```
Expected after the fix: 0 collection errors, 0 failures. Specifically the 7
items above must pass, and nothing previously passing may regress (385 currently
pass once the 4 assertion-failures are excluded; all should pass after).

Also run the end-to-end suite to confirm no fixture drift:
```
python3 tests/pipeline/run_test_pipeline.py --auto
```

## Out of scope
- Do **not** touch `velocity_converter/registry_match.py` or
  `tests/regression/test_legminus1.py` — that's the separate Leg -1
  quote-vs-policy ambiguity fix, already done.
- Do not re-add `write_conditional_form`. The retirement is intentional; tests
  move to the variants.csv API. (`parse_conditional_form` may remain as the
  documented legacy path.)
