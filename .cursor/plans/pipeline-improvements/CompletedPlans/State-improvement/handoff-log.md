# State improvement — agent handoffs

Newest sections first. See `00-state-linking-and-delta-audit.md` for scope.

---

## Handoff — 2026-04-26 — Artifact Prover + Schema Sheriff — Workstreams: A, B, C, D, E, F

### Summary (3–6 bullets)

- Canonical registry is **`registry/path-registry.yaml`**; root `path-registry.yaml` is removed and **conformance fails** if a root copy reappears.
- **`extract_paths.py`** writes registry **1.1** with `meta.source_config_sha256` (algorithm in `scripts/socotra_config_fingerprint.py` + `SCHEMA.md`). Default `--output` is `<config-dir>/../registry/path-registry.yaml`.
- **`scripts/leg2_fill_mapping.py`** stamps provenance (`run_id`, hashes, registry lineage, `registry_config_check`), optional **delta** merge (`--base-suggested`, `delta_changes`, locked/`status: confirmed` carry-forward, `would_change_locked`), writes **`.review.md`** with a **State summary**, supports **`--config-dir`** hash gate with **`--allow-stale-registry`** and **`--allow-missing-registry-fingerprint`**, and **`--require-registry-config-check`**.
- **`emit_telemetry.py`** merges the same provenance + `delta_changes` into JSONL **`kind: summary`**; **`conformance/schemas/suggester-log.schema.json`** extended with optional summary keys.
- **`scripts/suggester_inspect.py`**: `list-runs`, `show-run`, `diff-runs`, `registry-lineage`.
- **`html-to-velocity` `convert.py`** resolves **`registry/path-registry.yaml`** before **`path-registry.yaml`** per ancestor directory.

### Files and entry points

- `scripts/socotra_config_fingerprint.py`, `scripts/suggester_state.py`, `scripts/suggester_inspect.py`, `scripts/leg2_fill_mapping.py`
- `.cursor/skills/mapping-suggester/scripts/extract_paths.py`, `emit_telemetry.py`
- `.cursor/skills/html-to-velocity/scripts/convert.py`
- `conformance/run-conformance.py`, `conformance/schemas/suggester-log.schema.json`, all fixture **`golden/path-registry.yaml`** regenerated
- `registry/path-registry.yaml`, `README.md`, `SCHEMA.md`, `.cursor/skills/mapping-suggester/SKILL.md`, `.cursor/skills/html-to-velocity/SKILL.md` (batch `--registry` example)
- `tests/test_socotra_config_fingerprint.py`

### Contracts downstream must use

- Registry **`schema_version: '1.1'`**, **`meta.source_config_sha256`** (64-char lowercase hex).
- Suggested **`schema_version: '1.1'`** with provenance field names as in `SCHEMA.md` § `<stem>.suggested.yaml`.
- **`registry_config_check`**: `matched` \| `skipped_no_config_dir` \| `skipped_escape_hatch` \| `skipped_missing_registry_fingerprint` \| `failed_mismatch`.
- **`delta_changes`** keys: `added`, `changed`, `cleared`, `carried_forward_confirmed`, `re_suggested_unconfirmed`, `would_change_locked`, `carried_forward_count`, `registry_or_config_changed`.

### Verification performed

- `python3 conformance/run-conformance.py` — all 11 fixtures PASS.
- `python3 -m unittest tests.test_socotra_config_fingerprint -v` — PASS.
- `python3 scripts/leg2_fill_mapping.py … --config-dir socotra-config` + `scripts/suggester_inspect.py list-runs` — PASS.

### Open items / risks for next agent

- **SKILL Step 4c / human runs:** mapping-suggester should mirror provenance + delta behaviour when authoring by hand; `leg2_fill_mapping.py` is the reference implementation.
- **jsonschema:** optional local install to validate JSONL batches against the updated schema.

**Resolved (2026-04-27):** Golden and sample `<stem>.review.md` files now use
`<!-- schema_version: 1.1 -->` and `Schema: 1.1 (mapping 1.0, registry 1.1)`;
`SCHEMA.md` documents v1.1 review layout and optional provenance / State
summary for tool runs. Conformance goldens still omit full provenance blocks
until refreshed from a suggester / `leg2_fill_mapping.py` run.

### Read next

- `SCHEMA.md` (registry fingerprint, suggested 1.1, JSONL v1.1 extensions, terminology resolution).
- `00-state-linking-and-delta-audit.md` Definition of done.
