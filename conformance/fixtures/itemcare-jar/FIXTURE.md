# itemcare-jar — full real-product registry extraction

## Purpose

Registry-extraction regression against a **complete real product config**
(a frozen copy of the original `ItemCare` product), as opposed to the
minimal synthetic trees in the other fixtures. With 148 paths and an
iterable exposure it exercises the extractor at realistic scale:
exposures, coverages, charges, account/policy/system paths, and
DataFetcher entries together in one document.

## History

This fixture previously also carried frozen Leg 2 (`suggested.yaml` /
`review.md`) goldens, run JAR-backed via a `leg2.json` marker against the
compiled ItemCare JARs in `build/`. Those goldens were retired: Leg 2's
SDK-grounded output is pinned to whatever product is compiled in `build/`,
and this tool ships product-agnostic — every deployment inserts its own
`socotra-config/` and JARs, so a committed product-pinned golden can never
run on a fresh copy. Leg 2 behaviour is covered by the regression suite
and `tests/pipeline/run_test_pipeline.py` instead. (A frozen copy of the
old suggested output lives on as a static input for the telemetry schema
test at `tests/regression/fixtures/itemcare.suggested.yaml`.)

## Inputs

- `socotra-config/` — frozen copy of the original `ItemCare` product config.
- `mapping.yaml` — 4 variables + 1 loop (1 field); `source` carries the
  `(segment)` root; all `data_source` blank. Kept for agent-driven Leg 2
  experiments (the runner diffs `actual/` outputs only if an agent leaves
  them — see conformance/README.md).

## Goldens

- `golden/path-registry.yaml` — 148 paths, 1 iterable (`Item`).
