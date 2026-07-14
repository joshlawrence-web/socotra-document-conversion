# Tables in templates — implemented 2026-07-12 (overnight)

You asked for: a re-usable, prescriptive way to get **a new table row per coverage**,
including the "excel inside a Word doc" case — one giant table whose rows only exist
when a coverage exists. All three pieces are implemented, tested, and live-rendered.

## What to look at first (the proof)

| File | What it shows |
|---|---|
| `workspace/output/ZenCoverCoverGrid(segment)/ZenCoverCoverGrid(segment).preview.pdf` | **Live tenant render** of the giant-table demo. The DISHWASHER item renders; the Accidental Damage row is *hidden* (that item doesn't hold it); Breakdown row shows with blank guarded cells. Rows literally appear/disappear per coverage. |
| `workspace/inbox/ZenCoverCoverGrid(segment).docx` | The Word doc an author writes for that PDF. Open it — the marker syntax is the whole trick. |
| `workspace/output/ZenCoverCoverageSchedule(segment)/ZenCoverCoverageSchedule(segment).preview.pdf` | Live render of the `[Coverage/]` plugin-list demo (rows appear once the new plugin is deployed — see "deploy gap" below). |
| `workspace/output/ZenCoverCoverGrid(segment)/ZenCoverDocumentDataSnapshotPluginImpl.java` | One combined generated plugin for both demos: the `Theft` presence Boolean + the `coverages` list builder. Compiles clean (`compile=PASS`). |

## The three capabilities

### 1. `[Name?]` … `[/Name]` — conditional row regions (the giant-table gap)
Wrap any rows in a marker pair with a `?` opener. Three shapes, resolved automatically:
- **`[AccidentalDamage?]` inside `[Item/]`** → row renders only when that item holds the
  coverage (`#if($item.AccidentalDamage)`). Zero customer fill.
- **`[Theft?]` at document level** (Theft is a registry coverage) → row renders when ANY
  item holds Theft. The generated plugin computes the Boolean automatically — the
  variants.csv doesn't even show it. Zero customer fill.
- **`[CoolingOffRow?]` (any other name)** → a generic conditional row region: one
  `when`-only row in variants.csv, exactly like a loop's (blank = always render).

### 2. Coverage fields are now always null-guarded (bug fix)
`{item.Breakdown.data.labourCovered}` previously rendered unguarded because the config
says Breakdown is "always present" — but live tenant data disagreed and the render
API 400'd (I hit this for real). Every coverage-hop field now gets
`#if($item.<Cov>)…#end` regardless of quantifier.

### 3. `[Coverage/]` … `[/Coverage]` — one row per coverage, dynamically
A real loop over a list that doesn't exist on any entity: the registry now declares a
`Coverage` iterable (`kind: plugin_list`, `registry/path-registry.yaml`), and the
generated plugin **builds** the list — one entry per (item × coverage present) with
`name`, `displayName`, `itemTypeCode`, and the coverage's data fields (`""` where a
coverage type lacks one). Template authors write `{coverage.displayName}` etc. inside
the markers, same mental model as `[Item/]`.

## How to run it (both demos, end to end)

```
python3 -m velocity_converter.leg0_ingest --input "workspace/inbox/ZenCoverCoverGrid(segment).docx" --output-dir "workspace/output/ZenCoverCoverGrid(segment)"
# fill workspace/action-needed/ZenCoverCoverGrid(segment).variants.csv (only Item + CoolingOffRow rows appear)
python3 -m velocity_converter.leg0_ingest --parse-variants-csv "workspace/action-needed/ZenCoverCoverGrid(segment).variants.csv" --output-dir "workspace/output/ZenCoverCoverGrid(segment)"
python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg2+leg3 mapping=workspace/output/ZenCoverCoverGrid(segment)/ZenCoverCoverGrid(segment).mapping.yaml registry=registry/path-registry.yaml"
python3 -m velocity_converter.leg4_generate_plugin --suggested "workspace/output/ZenCoverCoverGrid(segment)/ZenCoverCoverGrid(segment).mapping.yaml" --customer-jar build/customer-config.jar --datamodel-jar build/core-datamodel-v1.7.61.jar --compile-check
python3 tools/validate_demo.py "ZenCoverCoverGrid(segment)" --output workspace/output   # → PASS
```

## Test coverage added

- **2 new pipeline fixtures** (11 total, all PASS end-to-end incl. combined Leg 4 +
  compile): `TestCoverageGrid(segment)` (all three `[Name?]` shapes) and
  `TestCoverageSchedule(segment)` (plugin-list loop). `python3 tests/pipeline/run_test_pipeline.py --auto`
- **New regression file** `tests/regression/test_conditional_regions.py` (14 tests):
  marker parsing, presence-block flow, CSV skip, Leg 3 guard survival, always-guard,
  Leg 4 presence Java. Full regression suite: **521 passed, 0 failed**.

## Self-review (8-angle code review, findings fixed)

Fixed from review: in-loop guards now use the registry iterable's real iterator (not a
`name.lower()` guess); Leg 4 never guesses `items()` when the registry lacks a list
accessor (puts `false` + TODO instead); `tools/validate_demo.py`'s done-gate now
catches surviving `[Name/]`/`[Name?]`/`[/Name]` markers (it only knew legacy `[Item]`);
CLAUDE.md's renderingData checklist and `docs/leg-internals.md` updated for the new
marker types. Accepted as deliberate: small helper duplication across legs (matches the
legs-are-standalone convention) and the mapping freezing the registry's coverage spec
(mapping-as-contract convention — re-run Leg 2 after registry changes).

## Known limits (deliberate, documented in CLAUDE.md)

- **Per-coverage premium** can't be a `[Coverage/]` entry field — charge amounts aren't
  reachable from the snapshot records (charges live on pricing). Needs its own design.
- **Deploy gap** (pre-existing): live renders execute the *deployed* plugin. Until the
  regenerated `ZenCoverDocumentDataSnapshotPluginImpl.java` is deployed to the tenant,
  `[Theft?]`/`[CoolingOffRow?]` rows stay hidden and `$data.coverages` iterates empty —
  which is also proof the templates degrade gracefully instead of erroring.
- An N-way variant block whose variants each carry their own loop remains unsupported
  (pre-existing).
