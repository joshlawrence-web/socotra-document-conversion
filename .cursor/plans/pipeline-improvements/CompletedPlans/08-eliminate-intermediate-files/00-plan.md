# Eliminate Intermediate Pipeline Files

**Status:** Done
**Completed:** 2026-06-09
**Created:** 2026-06-09

## START HERE (implementing agent)

This plan is complete. It is recorded here for provenance.

---

## 1. Background

The pipeline was writing three artifacts that were either dead ends, always-on noise, or conceptually redundant:

| File | Problem |
|------|---------|
| `<stem>.fields.yaml` | Written by Leg 0, never read by any downstream leg. Redundant with `.mapping.yaml`. |
| `<stem>.suggester-log.jsonl` | Telemetry audit log appended on every Leg 2 run, even when nobody needed it. Opt-in at the script level but effectively always-on via the orchestrator. |
| `<stem>.suggested.yaml` | Leg 2 → Leg 3/4 hand-off. Conceptually just an enriched form of `.mapping.yaml`. Caused a second YAML file per stem with a confusing name. |

**Goal:** One YAML file per stem — `.mapping.yaml` — which Leg 1 creates (Schema 1.0) and Leg 2 enriches in-place (Schema 2.0). Legs 3 and 4 read from the same file.

---

## 2. Decisions

| # | Topic | Decision |
|---|-------|----------|
| D1 | `.fields.yaml` removal | Stop writing it. Content (variable names + empty `data_source`) is already present in `.mapping.yaml`. No test or downstream script reads it. `write_fields_yaml()` function removed from `leg0_ingest.py`. |
| D2 | `suggester-log.jsonl` removal | Default to `None` for `telemetry_log` in all `leg2_paths` dicts in `agent.py`. The script-level `--telemetry-log` flag remains for explicit opt-in. |
| D3 | `.suggested.yaml` → `.mapping.yaml` in-place enrichment | Leg 2's `--out` path now resolves to `<stem>.mapping.yaml` (overwriting the Leg 1 output). Leg 3 and Leg 4 strip `.mapping.yaml` as a suffix in addition to `.suggested.yaml`. |
| D4 | Backward compat | Leg 3/4 `--suggested` flag still accepts legacy `.suggested.yaml` paths. Validation in `agent_tools.py` allows both suffixes. Interactive mode globs for both. |
| D5 | Cleanup logic | `get_intermediate_paths()` previously kept `.suggested.yaml` (Leg 4 needed it) and deleted `.mapping.yaml` (superseded). After this change, `.mapping.yaml` is kept; only `.review.md` is cleaned. |
| D6 | Re-run safety | Leg 2 reads `variables[].name/placeholder/type/context` — keys present in both Schema 1.0 and 2.0. Extra enrichment fields are ignored on re-read. A second Leg 2 run cleanly re-enriches. |

---

## 3. Files changed

| File | Change |
|------|--------|
| `scripts/leg0_ingest.py` | Removed `write_fields_yaml()` call and function; updated docstring |
| `scripts/agent.py` | `_derive_leg2_paths()` now returns `mapping.yaml` as `out`; all three inline `leg2_paths` dicts updated; `telemetry_log` defaults to `None`; `_derive_leg3_paths()` strips `.mapping` suffix; interactive menu and `REFUSAL` block updated |
| `scripts/agent_tools.py` | `_INTERMEDIATE_SUFFIXES` trimmed; `build_writes()` drops `.fields.yaml`, `.suggested.yaml`, `.suggester-log.jsonl`; `get_intermediate_paths()` drops log, keeps `.mapping.yaml`; `run_leg0`/`run_leg4` artifact lists updated; validation accepts `.mapping.yaml`; leg4 path uses `.mapping.yaml` |
| `scripts/leg2_fill_mapping.py` | Stem derivation strips `.mapping.yaml`; YAML comment header updated; function docstring updated |
| `scripts/leg2_review_writer.py` | User-facing report line references `.mapping.yaml` |
| `scripts/leg3_substitute.py` | Suffix list adds `.mapping.yaml`; docstring, DD-4 comment, and report text updated |
| `scripts/leg4_generate_plugin.py` | Suffix list adds `.mapping.yaml`; docstring, report content updated |
| `CLAUDE.md` | Architecture table, Leg 0 output list, Leg 3/4 examples updated |
| `README.md` | Mermaid diagram, leg descriptions, output table, CLI examples updated |

---

## 4. Output directory before vs after

**Before** (full `leg1+leg2+leg3+leg4` run):
```
<stem>.vm
<stem>.mapping.yaml         ← Leg 1 (cleaned up after run)
<stem>.suggested.yaml       ← Leg 2 (kept)
<stem>.review.md            ← Leg 2 (cleaned up after run)
<stem>.suggester-log.jsonl  ← Leg 2 (always written)
<stem>.final.vm             ← Leg 3
<stem>.leg3-report.md       ← Leg 3
<stem>.java                 ← Leg 4
<stem>.plugin-report.md     ← Leg 4
```

**After**:
```
<stem>.vm
<stem>.mapping.yaml         ← Leg 1 (enriched in-place by Leg 2, kept)
<stem>.review.md            ← Leg 2 (cleaned up after run)
<stem>.final.vm             ← Leg 3
<stem>.leg3-report.md       ← Leg 3
<stem>.java                 ← Leg 4
<stem>.plugin-report.md     ← Leg 4
```

---

## 5. Verification

```bash
# 229/229 regression tests pass
python3 -m pytest tests/ -q

# Full pipeline — no fields.yaml / suggested.yaml / log written
python3 scripts/agent.py --yes \
  "RUN_PIPELINE leg1+leg2+leg3+leg4 input=samples/input/Simple-form.html \
   registry=registry/path-registry.yaml output=samples/output"
ls samples/output/Simple-form/
# Must NOT see: .fields.yaml, .suggested.yaml, .suggester-log.jsonl

# Leg 3 standalone (new path)
python3 scripts/agent.py --yes \
  "RUN_PIPELINE leg3 suggested=samples/output/Simple-form/Simple-form.mapping.yaml"

# Backward compat — old suggested.yaml still accepted
python3 scripts/leg3_substitute.py \
  --suggested samples/output/Simple-form/Simple-form.suggested.yaml \
  --vm samples/output/Simple-form/Simple-form.vm
```
