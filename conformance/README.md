# conformance/ — Conformance fixtures

This directory hosts the adversarial fixture suite for the HTML →
Velocity pipeline (Phase C of [PIPELINE_EVOLUTION_PLAN.md](../.cursor/plans/pipeline-improvements/CompletedPlans/alpha-beta-plan/PIPELINE_EVOLUTION_PLAN.md)). Each
fixture is a minimal `socotra-config/` tree plus a hand-written
`mapping.yaml` that exercises one or more rows from
[CONFIG_COVERAGE.md](../docs/CONFIG_COVERAGE.md). Goldens are frozen copies of the outputs an agent
produced on a clean run; the runner diffs live outputs against them.

## Layout

```
conformance/
  README.md                          ← this file
  run-conformance.py                 ← runner (see below)
  fixtures/
    <name>/
      FIXTURE.md                     ← rows this fixture covers
      socotra-config/                ← mini config tree
        products/<Name>/config.json
        exposures/<Name>/config.json
        coverages/<Name>/config.json
        customDataTypes/<Name>/config.json
        charges/<Name>/config.json
      mapping.yaml                   ← hand-authored Leg 1 output
      golden/
        path-registry.yaml           ← frozen registry for this fixture (repo uses `registry/path-registry.yaml`)
      actual/                        ← populated by the runner / the
        path-registry.yaml             agent when re-running Leg 2;
        suggested.yaml                 this directory is gitignored so
        review.md                      diffs stay clean between runs
```

### Registry-only by design

Every fixture is **registry-only**: it freezes what `extract_paths.py` must
emit for one class of config shape (quantifiers, CDTs, nested iterables,
jurisdictional scopes, …). Each fixture carries its own mini
`socotra-config/`, so the suite runs identically on any fresh copy of the
tool with no JARs and no user product.

Leg 2 (`suggested`/`review`) goldens are deliberately **not** committed.
Leg 2's SDK-grounded output is pinned to whatever product is compiled in
`build/`, and this tool ships product-agnostic — every deployment inserts
its own `socotra-config/` and JARs, so a committed product-pinned golden
could never run on a fresh copy. (The old JAR-backed `itemcare-jar` leg2
goldens were retired for exactly this reason; see its `FIXTURE.md`.) Leg 2
behaviour is covered by the regression suite and
`tests/pipeline/run_test_pipeline.py`. A team may still freeze *local*
leg2 goldens for its own product — the runner diffs `actual/suggested.yaml`
/ `actual/review.md` against goldens whenever an agent leaves them.

## Runner workflow

`conformance/run-conformance.py` is the regression entrypoint. It is **fully
automated for the registry** (Leg 2a, `extract_paths.py`) and
**human-in-the-loop for the suggester** (Leg 2, the mapping-suggester
skill). The split matters because `extract_paths.py` is deterministic
Python but Leg 2 is an agent-executed skill.

Per fixture, the runner:

1. Deletes any stale `actual/path-registry.yaml`.
2. Runs
   `python3 -m velocity_converter.extract_paths
   --config-dir <fixture>/socotra-config
   --output <fixture>/actual/path-registry.yaml`.
3. Diffs `actual/path-registry.yaml` against `golden/path-registry.yaml`,
   ignoring the volatile `meta.generated_at` and `meta.config_dir`
   fields (see `_canonicalize_registry` in the runner source for the
   exact list of ignored keys).
4. If `actual/suggested.yaml` / `actual/review.md` exist (left by an
   agent), the runner diffs those against their goldens.
   `suggested.yaml` is canonicalised against a volatile-key list;
   `review.md` is text-diffed with the volatile bullets (run id, the
   source/output/registry paths, input sha digests, registry lineage,
   `Generated at`) normalised. When `actual/` is missing or empty, the
   runner reports `suggested=skipped` / `review=skipped` and does not fail —
   the deterministic registry half passes in isolation.
5. Exits non-zero on any diff.

### Refreshing goldens

After confirming a diff is intentional (for example, because the
suggester or `extract_paths.py` gained a new feature), copy the live
`actual/` files over the goldens:

```bash
python3 conformance/run-conformance.py --update-goldens
```

The flag rewrites every `golden/*.yaml` / `golden/*.md` from the
corresponding `actual/*` file. The runner refuses to update a golden
that does not have a matching actual (guards against zeroing out
frozen artifacts).

## Adding a new fixture

1. Read [PIPELINE_EVOLUTION_PLAN.md](../.cursor/plans/pipeline-improvements/CompletedPlans/alpha-beta-plan/PIPELINE_EVOLUTION_PLAN.md) §4.1 (seed fixtures) and
   [CONFIG_COVERAGE.md](../docs/CONFIG_COVERAGE.md) §3 (which row you're covering).
2. Create `conformance/fixtures/<name>/socotra-config/` with the minimum
   files to exercise the feature. Name tokens deterministically (no
   timestamps, no UUIDs).
3. Write `mapping.yaml` with 3–10 placeholders that touch the
   feature — avoid piling unrelated placeholders in.
4. Run the agent-executed suggester on the fixture's mapping once; the
   output lands in `actual/suggested.yaml` and `actual/review.md`.
5. Run `python3 conformance/run-conformance.py --update-goldens` to freeze the
   outputs.
6. Hand-check the goldens; they must be short enough to diff by eye.
7. Write `FIXTURE.md` listing:
   - which `CONFIG_COVERAGE.md` rows this fixture exercises,
   - which `feature_support` flags the registry is expected to set,
   - what behaviour is proven (e.g. "Rule 4 optional-element guard
     fires on MedPay?").
8. Update `CONFIG_COVERAGE.md`: remove `(pending)` from the Fixture
   path column for every row the new fixture covers.

