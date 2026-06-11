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
      leg2.json                      ← OPTIONAL opt-in marker: this is a
                                       JAR-backed fixture; the runner runs
                                       Leg 2 itself (see below)
      golden/
        path-registry.yaml           ← frozen registry for this fixture (repo uses `registry/path-registry.yaml`)
        suggested.yaml               ← frozen Leg 2 output (JAR-backed fixtures only)
        review.md                    ← frozen Leg 2 companion (JAR-backed fixtures only)
      actual/                        ← populated by the runner / the
        path-registry.yaml             agent when re-running Leg 2;
        suggested.yaml                 this directory is gitignored so
        review.md                      diffs stay clean between runs
```

### Two kinds of fixture

- **Registry-only (most fixtures).** Synthetic `socotra-config/` trees for
  products that were never compiled. There is no JAR to introspect, so a
  schema-2.0, SDK-grounded Leg 2 run would fail loud by design
  (Leg2-root-aware-confidence plan **D1**). These fixtures keep only
  `golden/path-registry.yaml`; their old 1.x `suggested`/`review` goldens were
  **retired**. The runner diffs the registry and reports `suggested=skipped`.
- **JAR-backed (`itemcare-jar`).** Carries a `leg2.json` marker and is backed by
  the **real `ItemCare`** config, so its registry paths match the compiled
  `build/*.jar`. The runner runs Leg 2 here and diffs **2.0** `suggested`/
  `review` goldens. This is the single end-to-end SDK-grounded regression test.

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
4. **JAR-backed fixtures only** (a `leg2.json` marker is present): runs
   `python3 -m velocity_converter.leg2_fill_mapping --mode terse` against the frozen
   `golden/path-registry.yaml` + the `build/*.jar` set, writing
   `actual/suggested.yaml` + `actual/review.md`. `terse` mode is fully
   deterministic (no AI narrative), so this half is automatable. Needs the
   compiled product JARs in `build/` — fails loud if they are absent (D1).
5. If `actual/suggested.yaml` / `actual/review.md` exist (from step 4, or
   left by an agent for a non-JAR fixture), the runner diffs those against
   their goldens. `suggested.yaml` is canonicalised against a volatile-key
   list; `review.md` is text-diffed with the volatile bullets (run id, the
   source/output/registry paths, input sha digests, registry lineage,
   `Generated at`) normalised. When `actual/` is missing or empty, the
   runner reports `suggested=skipped` / `review=skipped` and does not fail —
   the deterministic registry half passes in isolation.
6. Exits non-zero on any diff.

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

### Adding a JAR-backed (schema 2.0) fixture

Only viable for a product with **compiled JARs** in `build/` (today: the real
`ItemCare`). See `fixtures/itemcare-jar/` as the worked example.

1. Copy the real config in: `cp -R socotra-config conformance/fixtures/<name>/socotra-config`.
2. Write `mapping.yaml` whose `source` declares a rendering root in brackets —
   `source: <name>(segment).html` (or `quote`). This is mandatory; without it
   Leg 2 blocks (plan D2/§8).
3. Drop a `leg2.json` marker: `{"mode": "terse"}`.
4. Generate the registry golden, then let the runner produce the 2.0 goldens:
   ```bash
   python3 -m velocity_converter.extract_paths \
     --config-dir conformance/fixtures/<name>/socotra-config \
     --output     conformance/fixtures/<name>/golden/path-registry.yaml
   python3 conformance/run-conformance.py --only <name>                 # writes actual/, will FAIL (no goldens yet)
   python3 conformance/run-conformance.py --only <name> --update-goldens
   python3 conformance/run-conformance.py --only <name>                 # confirm PASS
   ```
5. Hand-check `golden/suggested.yaml` + `golden/review.md`, then write `FIXTURE.md`.
