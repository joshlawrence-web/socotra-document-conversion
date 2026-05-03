# Integration tests — pipeline use-case coverage

**Status:** DONE — all 7 test files implemented and passing (56 tests)
**Why:** Regression tests (`tests/regression/`) prove implementation correctness but not
business correctness. They do not verify that the pipeline resolves the right paths for
a real document against a real Socotra config, nor that it handles different config
permutations. This plan adds tests that prove the thing the tool is actually for.

---

## The gap

The regression suite answers: "does the code do what it does?"
These integration tests answer: "does the pipeline do what it's supposed to?"

Specifically, they must prove:
1. A correctly labelled HTML field resolves to the correct `$data.*` path (not just *some* path)
2. The full leg1+leg2+leg3 chain produces a clean `.vm` with no `$TBD_*` for resolvable fields
3. The pipeline handles different Socotra config shapes without silently producing wrong output
4. Unresolvable fields are always flagged (never silently produce a wrong path)

---

## Test suite: `tests/integration/`

### IT-1 — Label-match quality contract

**What it proves:** If a field's `nearest_label` exactly matches a `display_name` in the
registry, leg2 MUST return `confidence: high` and the correct `velocity` path.

**How:** Build a minimal mapping.yaml programmatically from the real `registry/path-registry.yaml`.
For each entry in the registry that has a `display_name`, construct a mapping variable whose
`nearest_label` equals that `display_name`. Run `annotate_mapping`. Assert:
- `confidence == "high"` for every entry
- `data_source == entry["velocity"]` — the exact path, not just non-empty

**Why this matters:** This is the core quality contract. If a user labels their HTML correctly,
the tool must resolve every field. A failure here means the tool is broken for its primary use case.

**Fixture source:** `registry/path-registry.yaml` (real ItemCare config)

---

### IT-2 — End-to-end clean `.vm` for fully resolvable documents

**What it proves:** A document where all fields have registry entries produces a final `.vm`
with zero `$TBD_*` tokens (after leg3 with all-confidence substitution).

**How:** Use the `itemcare-simple` conformance fixture. It has a known mapping + registry.
Run `annotate_mapping` (leg2), then `leg3_substitute.py`. Assert:
- No `$TBD_*` remains in the final `.vm`
- Every `#foreach` block has a corresponding `#end`
- Every substituted path starts with `$data.` or `$<iterator>.`

**Why this matters:** This is the end-to-end guarantee. The whole pipeline exists to eliminate
`$TBD_*` — this test asserts it actually does that.

**Fixture source:** `conformance/fixtures/itemcare-simple/`

---

### IT-3 — Unresolvable fields are always flagged, never silently wrong

**What it proves:** A field with no matching registry entry gets `confidence: low` and
`next-action:` in reasoning. It is never assigned a guessed path.

**How:** Construct a mapping with variables whose names and labels do not exist in any
registry entry. Run `annotate_mapping`. Assert for every variable:
- `confidence == "low"`
- `data_source == ""`  (empty, not a guessed path)
- `"next-action:"` is in `reasoning`

**Why this matters:** Silent wrong paths are worse than `$TBD_*`. This test ensures the tool
fails loudly rather than producing plausible-looking but incorrect Velocity.

**Fixture source:** Synthetic mapping + real registry (any field names that don't exist in registry)

---

### IT-4 — Cross-config permutation: same document, different registry shapes

**What it proves:** The pipeline handles the full range of Socotra config shapes without
crashing or producing schema-invalid output. Each conformance fixture exercises a different
config feature set.

**How:** Parameterise over all conformance fixtures that have a `golden/suggested.yaml`.
For each:
1. Run `leg2_fill_mapping.py` with the fixture's `mapping.yaml` + `path-registry.yaml`
2. Assert the output is schema-valid (has `schema_version`, `variables`, `loops`, all required keys)
3. Assert every entry has `confidence` in `{high, medium, low}` and `data_source` is a string
4. Assert no entry has `confidence: high` with `data_source: ""`  (the worst failure mode)

Config shapes covered by existing fixtures:
- `minimal` — system paths only, no exposures
- `itemcare-simple` — exposures + iterables
- `all-quantifiers` — optional/required/list quantifiers
- `cdt-flat` / `cdt-recursive` — custom data types
- `coverage-terms` — coverage-level fields
- `nested-iterables` — iterables inside iterables
- `multi-product` — multiple product configs
- `no-exposures` — system + account paths only
- `jurisdictional` / `jurisdictional-exclusive` — scoped paths

**Why this matters:** Reusability. If the pipeline only works for one config shape, it is not
general-purpose. This test suite is the evidence that it handles the full Socotra config surface.

**Fixture source:** `conformance/fixtures/*/`

---

### IT-5 — Confidence stability: re-running leg2 on a confirmed mapping

**What it proves:** Running leg2 on a mapping that already has `confirmed: true` entries
(delta mode) does not change those entries. Confirmed paths are preserved across re-runs.

**How:** Take the `itemcare-simple` golden suggested.yaml. Mark two entries as `confirmed: true`.
Run `merge_delta`. Assert those entries are unchanged in the output (same `data_source`, same
`confidence`, `confirmed` still true).

**Why this matters:** Users confirm mappings before running leg3. If leg2 can overwrite
confirmed entries, human review work is silently discarded. This test asserts the invariant
that `confirmed` is a one-way gate.

**Fixture source:** `conformance/fixtures/itemcare-simple/`

---

### IT-6 — Loop field scope: loop fields never appear as top-level variables

**What it proves:** A field inside a `[loopname]...[/loopname]` block is always recorded as
a loop field, never as a top-level variable. Scope is never lost during leg1 processing.

**How:** Construct HTML with a loop containing 3 fields and 2 top-level fields. Run leg1
(`process_all_mustache_loops` + `rewrite_vars_in_subtree`). Assert:
- `mapping.variables` contains exactly 2 entries
- `mapping.loops[0]["fields"]` contains exactly 3 entries
- Every loop field has `context.loop` set
- No loop field appears in `mapping.variables`

**Why this matters:** Scope loss means loop fields get treated as system-level paths, which
produces silently wrong Velocity (field used outside its `#foreach` block).

**Fixture source:** Synthetic HTML (constructed in test)

---

### IT-7 — High-only mode: medium/low fields stay as `$TBD_*` after leg3

**What it proves:** When leg3 runs with `high_only=True`, only `confidence: high` entries
are substituted. Medium and low entries remain as `$TBD_*` tokens in the final `.vm`.

**How:** Use `itemcare-simple` mapping with a mix of high/medium/low entries.
Run leg3 with `high_only=True`. Assert:
- All `$TBD_*` tokens remaining in `.vm` correspond to medium or low entries
- No `$TBD_*` token corresponds to a high-confidence entry
- Medium/low entries appear in the `.leg3-report.md` "Deferred" section

**Why this matters:** High-only mode exists specifically for production safety — users review
fuzzy matches before they go live. If high-only mode substitutes medium/low entries, it
defeats the entire purpose of the mode.

**Fixture source:** `conformance/fixtures/itemcare-simple/` + leg3 script

---

## Implementation approach

Tests live in `tests/integration/`. Each test loads real fixtures from `conformance/fixtures/`
or constructs minimal synthetic inputs. No mocking — real registry files, real leg2 script,
real leg3 script.

```
tests/
  __init__.py
  regression/           ← existing (implementation correctness)
    test_convert.py
    test_leg2_advanced.py
    test_leg2_registry_index.py
    test_leg2_review_writer.py
    test_socotra_config_fingerprint.py
  integration/          ← new (business correctness)
    __init__.py
    test_it1_label_quality.py
    test_it2_clean_vm.py
    test_it3_unresolvable_flagged.py
    test_it4_cross_config.py
    test_it5_delta_stability.py
    test_it6_loop_scope.py
    test_it7_high_only_mode.py
```

### Dependencies

- IT-1 to IT-5: only `leg2_fill_mapping.py` + `leg3_substitute.py` (already available)
- IT-2, IT-7: need to invoke `leg3_substitute.py` as a function, not a subprocess — requires
  exporting a `substitute(suggested_path, high_only)` function from `leg3_substitute.py`
  (currently only callable via `main()`). **This is a prerequisite before IT-2 and IT-7 can
  be implemented.**

### Order of implementation

```
1. IT-6  (loop scope — synthetic, no new dependencies)
2. IT-3  (unresolvable flagging — synthetic, no new dependencies)
3. IT-1  (label quality — uses real registry, straightforward)
4. IT-4  (cross-config — parameterised over conformance fixtures)
5. IT-5  (delta stability — uses existing merge_delta)
6. Export substitute() from leg3_substitute.py
7. IT-2  (end-to-end clean .vm)
8. IT-7  (high-only mode)
```

---

## Definition of done

- All 7 integration test files exist and pass against the real `socotra-config/` + `registry/`
- `python3 -m unittest discover -s tests` runs all regression + integration tests together
- IT-4 is parameterised: adding a new conformance fixture automatically adds a new test case
- Any new Socotra config feature that breaks IT-4 is caught before it reaches production
