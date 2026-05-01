## Goals

- Make `.suggested.yaml`, `.review.md`, and `*.suggester-log.jsonl` **linkable per run**.
- Make **delta runs auditable** (track exactly what changed vs what was carried forward) even if `.suggested.yaml` is overwritten.
- Make troubleshooting answerable from artifacts alone: **what inputs + what rules + what changed**.
- Treat **`path-registry.yaml` as derived state**, not a static reference file: it is produced from `socotra-config/` by `extract_paths.py`. When the config tree changes, the registry is **stale until regenerated**. That relationship must be **first-class in provenance and tooling**, not something operators infer from vibes or accidental diffs.
- **Enforce registry ↔ config alignment by hash** whenever the suggester can see both sides: because config changes are **infrequent**, it is easy to keep editing mappings against an **out-of-date registry** for weeks. A deterministic **`source_config_sha256`** in the registry plus the same algorithm over `--config-dir` at Leg 2 start makes mismatch **impossible to miss** — default behavior is **refuse to run** (non-zero exit, clear remediation text), not a quiet warning.
- **Stop “floating” `path-registry.yaml` at the repo root:** the canonical registry for this project lives under a **dedicated directory** (e.g. `registry/path-registry.yaml` — exact folder name to pick in implementation) so derived pipeline artifacts are visually and structurally separate from source docs, skills, and unrelated YAML. Same enforcement and provenance as today; only **layout + defaults + discovery** change.

## Constraints / non-goals

- **No automatic rollback** for delta runs.
- Keep **append-only history** where possible (`*.suggester-log.jsonl`).
- Preserve v1.0 compatibility unless explicitly bumping `schema_version` (and update `SCHEMA.md` + tests).
- **Registry–config verification is strict by default** when preconditions are met (see Workstream E): mismatch **aborts** before writing `.suggested.yaml` / `.review.md` / JSONL. A single **explicit escape hatch** (e.g. `--allow-stale-registry` or `--skip-registry-config-check`) is allowed for fixtures, bisects, or emergencies only — it must **print a loud banner** and stamp the run metadata / JSONL summary so audits never confuse an escaped run with a verified one. Do not silently rewrite the registry from Leg 2.
- **Layout change is a deliberate migration:** moving the registry off the repo root updates README, skills, samples, fixtures, scripts, and any hard-coded `--registry path-registry.yaml` examples. Prefer landing **Workstream F** in the same release window as **Workstream E** so operators learn one new layout + one new hash contract together.

---

## Workstream A — Run identity + provenance stamping

### Owner agent

Artifact Prover

### Deliverable

Per-run metadata consistently stamped into `.suggested.yaml`, `.review.md`, and JSONL summaries so a human can correlate artifacts by `run_id` and verify inputs by hash.

### Tasks

- Add top-level metadata to `<stem>.suggested.yaml`:
  - `run_id` (UUID)
  - `mode` (`full|terse|delta|batch`)
  - `generated_at` (ISO-8601 UTC)
  - `input_mapping_sha256` (hash of the mapping file bytes read for this run)
  - `input_registry_sha256` (hash of the registry **file** bytes read for this run, regardless of path — see Workstream F for canonical relative path stamped in `path_registry` / review)
  - **Registry derivation (from the registry file’s own `meta` block, copied/stamped at run time — see Workstream E):**
    - `registry_schema_version` (string; from registry root `schema_version`)
    - `registry_generated_at` (ISO string; from `meta.generated_at`)
    - `registry_config_dir` (string; from `meta.config_dir` — which tree the registry *claimed* it was built from)
    - `registry_source_config_sha256` (string; from `meta.source_config_sha256` once Workstream E lands; `null` or omitted for older registries)
  - **Live config verification (when `--config-dir` is supplied and Workstream E has landed — see Workstream E for abort vs success rules):**
    - `live_source_config_sha256` — hash recomputed from the passed `--config-dir` at suggester start
    - `registry_config_verified` — boolean, true only on successful runs where embedded and live fingerprints **matched** (or verification was skipped per explicit escape hatch)
    - `registry_config_check` — string enum documenting outcome, e.g. `matched` \| `skipped_no_config_dir` \| `skipped_escape_hatch` \| `failed_mismatch` (last case implies the run aborted and normally has no output artifacts — include for batch partial failure design if applicable)
  - Delta-only:
    - `previous_run_id` (from the base suggested file, if present; else null)
    - `base_suggested_sha256` (hash of the base suggested bytes)
  - Optional but recommended:
    - `tooling: { mapping_suggester: { version: <string>, ruleset_id: <string> } }`

- Stamp matching run metadata into `<stem>.review.md` header bullets:
  - `Run id`, `Mode`, `Inputs`, and (delta) `Base suggested`.
  - **Registry lineage:** registry file hash, `registry_generated_at`, `registry_config_dir`, embedded vs live `source_config_sha256`, and **`registry_config_check`** (e.g. `matched` or `skipped_escape_hatch` with a visible warning banner).

- Extend `*.suggester-log.jsonl` `kind: summary` record to include provenance:
  - `mode`
  - `input_mapping_sha256`, `input_registry_sha256`
  - Same **registry derivation + verification** fields as on `.suggested.yaml` (so JSONL alone answers “was this run hash-verified against disk config?”)
  - `base_suggested_sha256` (delta)
  - `previous_run_id` (delta)
  - `result_suggested_sha256`

- Update `SCHEMA.md` and any JSON schema in `conformance/schemas/` as needed:
  - Prefer a **MINOR bump** (e.g. `1.1`) if only adding optional keys.
  - Add fixture + test asserting `.suggested.yaml` and `.review.md` include the same `run_id` and that JSONL records carry that `run_id`.

### Acceptance criteria

- Given only `<stem>.suggested.yaml`, a teammate can find the exact JSONL batch via `run_id`.
- Given a JSONL `run_id`, a teammate can verify the exact inputs via the recorded hashes.
- Given a `.suggested.yaml` or JSONL summary, a teammate can see **which config directory the registry was generated from** and **when**; they can see whether the run was **hash-verified** against disk (`registry_config_check`, `registry_config_verified`) without opening `path-registry.yaml` manually.

---

## Workstream B — Delta change tracking (audit, not rollback)

### Owner agent

Delta Auditor

### Deliverable

Every delta run emits a deterministic change set: added/changed/cleared/carry-forward, tied to `run_id`, without requiring manual diffs of YAML.

### Definitions (per placeholder)

- **added**: `data_source: '' → '$path'`
- **changed**: `'$old' → '$new'`
- **cleared**: `'$old' → ''`
- **carried_forward_confirmed**: skipped because already confirmed
- **re-suggested_unconfirmed**: filled because blank/TBD/unconfirmed

### Tasks

- Implement delta merge as “overwrite latest view” but compute a change set first.
- Emit the change set in one (or both) places:
  - JSONL `kind: summary` under `delta_changes: {added:[], changed:[], cleared:[], carried_forward_count: N, ...}`
  - Optional sidecar: `<stem>.delta-changes.json` (or `.md`) in the same folder for human-friendly reading.
- When Workstream E is in place: if the registry file hash or config fingerprint changed vs the previous run’s summary, surface **`registry_or_config_changed`** at the summary level (see Workstream E → Delta runs). Note: a **failed** hash gate produces no new suggested file — delta tooling still sees the prior run until the operator regenerates the registry.

- Include in each changed row:
  - `name`, `placeholder`, `context.line`
  - `old_data_source`, `new_data_source`
  - `old_confidence`, `new_confidence` (if present)

### Human edits / locks (recommended)

- Support an optional per-entry key such as `status: confirmed` (or `locked: true`).
- Delta behavior:
  - Confirmed/locked entries are carried forward unchanged.
  - If the engine would change a locked entry, do **not** overwrite; record under `would_change_locked` in the change set.

### Acceptance criteria

- After delta, a teammate can answer “what changed?” by reading either the JSONL summary or the sidecar file (no YAML diff required).
- Locked entries never change silently.

---

## Workstream C — Troubleshooting ergonomics (inspection tools)

### Owner agent

Debug UX

### Deliverable

Small scripts that let humans inspect state across runs quickly using JSONL as the source of truth.

### Tasks

- Add a script (example name) `scripts/suggester_inspect.py` that can:
  - `list-runs <stem>`: show `run_id`, timestamp, mode, high/med/low counts
  - `show-run <stem> --run-id <id>`: show provenance + delta change summary
  - `diff-runs <stem> --a <run_id> --b <run_id>`: compare chosen matches per placeholder
  - `registry-lineage <stem> --run-id <id>` (or fold into `show-run`): print `input_registry_sha256`, embedded `registry_source_config_sha256`, `live_source_config_sha256` if recorded, and `registry_config_check`

- Add a short “State summary” section to `.review.md`:
  - run_id, previous_run_id (delta), changed counts (delta), file hashes.
  - Registry lineage one-liner: generated_at, config_dir, **verified yes/no** (or check enum).

### Acceptance criteria

- A teammate can diagnose “why did this mapping change?” in <2 minutes using inspector output.

---

## Workstream D — Contract + compatibility governance

### Owner agent

Schema Sheriff

### Deliverable

Safe evolution with explicit versioning and tests, including backwards-reading of older artifacts.

### Tasks

- Decide schema bump strategy:
  - YAML artifacts: bump `schema_version` MINOR if adding keys.
  - JSONL: update `conformance/schemas/suggester-log.schema.json` to allow new `summary` keys.

- Migration / fallback rules:
  - If base `.suggested.yaml` lacks `run_id`, `previous_run_id: null` is allowed but `base_suggested_sha256` must still be recorded.
  - Older JSONL lines without provenance remain readable; provenance fields are optional when parsing.
  - Older `path-registry.yaml` files without `meta.source_config_sha256`: if `--config-dir` is supplied, **default is refuse** (“regenerate registry with current `extract_paths.py`”) so CI cannot pass a silent no-op check. Document a **temporary** escape hatch (e.g. `--allow-missing-registry-fingerprint`) for migrating old fixtures, with the same loud audit stamping as stale-registry escape. If `--config-dir` is omitted, set `registry_config_check: skipped_no_config_dir` and document that **CI must pass `--config-dir`** so the hash gate always runs in automation.

- Add fixture(s) covering delta:
  - base suggested with confirmed entries
  - delta output with `previous_run_id`, `base_suggested_sha256`, and a populated change set.

### Acceptance criteria

- New runs validate against schemas; older artifacts still parse and can be inspected (with “unknown provenance” where missing).

---

## Workstream E — Registry ↔ socotra-config fingerprint (**enforced** hash gate)

### Owner agent

Artifact Prover (extract_paths + suggester coordination)

### Problem

`input_registry_sha256` proves *which registry file bytes* Leg 2 read. It does **not** prove that those bytes still reflect the current `socotra-config/` tree. Because the config changes rarely, teams **forget to re-run `extract_paths.py`**; Leg 2 then “succeeds” against a lying path universe. Operators need a **stable, comparable fingerprint of the config inputs** inside the registry and a **mandatory compare** against disk when Leg 2 is given the config directory.

### Deliverable

1. **`extract_paths.py`** extends `path-registry.yaml` → `meta` with a deterministic **`source_config_sha256`** (document the exact file walk, sort order, and “what counts as input” in `SCHEMA.md` — e.g. hashed contents of relevant `config.json` / YAML leaves under the product tree, excluding noise if needed). Bump registry **`schema_version` MINOR** if adding a key (coordinate with Schema Sheriff).
2. **`mapping-suggester`** reads `meta.source_config_sha256` after parsing the registry and **stamps** it into `.suggested.yaml` / `.review.md` / JSONL (Workstream A fields).
3. **Hash gate (default strict):** When **`--config-dir`** is supplied:
   - Recompute `live_source_config_sha256` with the **same algorithm** as `extract_paths.py`.
   - If `meta.source_config_sha256` is **missing**: **abort** with a clear message to regenerate the registry (unless the temporary migration flag from Workstream D is set — then stamp `registry_config_check: skipped_escape_hatch` and print the loud banner).
   - If both are present and **equal**: proceed; set `registry_config_verified: true`, `registry_config_check: matched`.
   - If both are present and **not equal**: **abort immediately** (non-zero exit); print embedded vs live hashes and “re-run: `extract_paths.py --config-dir …`”. Do not write suggested/review/JSONL for that document (or roll back batch — define consistent batch semantics in implementation).
4. When **`--config-dir` is omitted:** skip live compare; stamp `registry_config_check: skipped_no_config_dir`, `registry_config_verified: false`; document that **automation must always pass `--config-dir`** so the gate runs in CI. Optionally add a **separate** `--require-registry-config-check` that aborts if `--config-dir` is missing (nice for CI one-liners).
5. **Escape hatch** (explicit flag only): allow running with a mismatched or un-fingerprinted registry for emergencies/fixtures; must set `registry_config_check` to a `skipped_*` or `override` value and print stderr + review banner so escaped runs are never mistaken for verified ones.

### Delta runs (tie-in to Workstream B)

- If `input_registry_sha256` or `registry_source_config_sha256` differs from the previous run’s summary, the delta **change set** or summary should include **`registry_or_config_changed`**. A **failed** hash gate never produces a new artifact, so “no new run” can also mean “fix registry first” — consider a one-line stderr hint for delta invocations.

### Acceptance criteria

- Regenerating `path-registry.yaml` after a config edit produces a new `source_config_sha256` in `meta`.
- Leg 2 with `--config-dir` pointing at the **same** tree the registry was built from **succeeds** and records `registry_config_check: matched`.
- Leg 2 with `--config-dir` after a **config edit** but **without** regenerating the registry **fails fast** with no partial writes (unless escape hatch).
- JSONL + `.review.md` for successful runs always show whether verification ran (`matched` vs `skipped_no_config_dir` vs escape hatch).

---

## Workstream F — Canonical `path-registry.yaml` location (dedicated folder)

### Owner agent

Artifact Prover (plus doc/skill touchpoints)

### Problem

A single `path-registry.yaml` sitting at the **repository root** sits next to unrelated project files (`README.md`, `SCHEMA.md`, `terminology.yaml`, etc.). That makes the registry feel like “just another root file” instead of a **derived, config-bound artifact** grouped with its operational story.

### Deliverable

1. **Choose a dedicated directory** at repo root (recommendation: **`registry/`** — short, obvious; add a one-line `registry/README.md` or `registry/.gitkeep` policy note only if the team wants an in-folder explanation; otherwise document in root `README.md` + `SCHEMA.md` only).
2. **Move** the tracked canonical file from `./path-registry.yaml` → **`./registry/path-registry.yaml`** (or `<chosen-dir>/path-registry.yaml`). Update **all** internal references: `README.md`, `SCHEMA.md`, `CONFIG_COVERAGE.md` cross-links if any, `.cursor/skills/*`, `samples/`, `conformance/` fixtures and `run-conformance.py`, `scripts/leg2_fill_mapping.py`, invocation plans, and terminal examples that pass `--registry …`.
3. **`extract_paths.py` default output:** when `--output` is omitted, emit to **`<repo>/registry/path-registry.yaml`** when run from this repo’s documented workflow (or: default remains “parent of config dir” for ad-hoc runs **outside** this repo, but document that **this repo’s** standard command always targets `registry/path-registry.yaml` — pick one consistent story and document it).
4. **Leg 1 / Leg 2 discovery:** update any “walk ancestors for `path-registry.yaml`” logic so the **preferred** resolution order includes the new folder (e.g. check `./registry/path-registry.yaml` relative to cwd or repo root before giving up), **or** require explicit `--registry` in docs and accept that auto-discovery only finds the new layout. Do not leave two competing canonical copies (delete or stop updating root-level file after migration).
5. **`.suggested.yaml` / emitters:** set `path_registry` (or equivalent) to the **relative path from the mapping output** to the registry file (e.g. `../registry/path-registry.yaml` for files under `samples/output/<stem>/` — tune so paths stay stable and human-readable).
6. **`terminology.yaml`:** `SCHEMA.md` today convention is “sibling of `path-registry.yaml`”. After the move, either (a) keep `terminology.yaml` at repo root and document “terminology resolution: repo root first, then sibling of registry file”, or (b) co-locate optional `registry/terminology.yaml` — **decide in implementation** and update `SCHEMA.md` + mapping-suggester Step 0c in one PR.

### Acceptance criteria

- No canonical `path-registry.yaml` at repo root; CI and fixture runners pass with the new path.
- Fresh clone instructions: one obvious command sequence produces the registry **inside** the dedicated folder.
- Grep / CI guard (optional): fail if a new root-level `path-registry.yaml` is reintroduced by mistake.

---

## Inter-agent reporting (mandatory handoffs)

Purpose: the next agent (or the same agent in a later session) must not re-derive scope from raw diffs alone. Every handoff records **what shipped**, **where it lives**, and **what downstream agents must assume**.

### Where to write

1. **Append-only log (source of truth between sessions)**  
   Add each handoff as a new top-level `## Handoff — …` section to **`handoff-log.md`** in this same directory (`.cursor/plans/pipeline-improvements/State-improvement/`). Create the file on the first handoff. **Prepend** each new section immediately after the file title / one-line purpose blurb so **newest handoffs appear first**; receiving agents read from the top.

2. **Session end message (Cursor chat)**  
   Paste the same content (or a tight subset: Completed + Blockers) into the final assistant message when closing an agent turn, so humans scanning the thread see the summary without opening the log.

### When to write

- **Before** declaring a workstream or agent bundle “done” for handoff to another role.
- **After** any merge or push that another agent will build on, even if work is partial (then label **Partial** and list what remains).

### Required template (copy per handoff)

Use these headings verbatim so greps and humans stay aligned:

```markdown
## Handoff — <ISO date> — <Owner agent name> — Workstreams: <e.g. A, E, F>

### Summary (3–6 bullets)
- What behavior changed for operators / CI.

### Files and entry points
- List paths touched; note any new CLIs, flags, env vars, or schema keys.

### Contracts downstream must use
- Exact field names, `schema_version` values, default paths (e.g. registry location), and CLI flags the next agent must not rename silently.

### Verification performed
- Commands (tests, conformance, sample runs); pass/fail.

### Open items / risks for next agent
- TODOs, known edge cases, ordering deps (e.g. “B assumes summary keys X from A”).

### Read next
- Which sections of this plan or `SCHEMA.md` / conformance schemas the next agent should re-read.
```

### Rules for receiving agents

- **Read** the latest relevant `handoff-log.md` entry (and any entry it references) **before** implementing dependent workstreams.
- If a handoff is missing or ambiguous, **do not guess**: add a short clarification sub-bullet under Open items in your own handoff after you resolve it, or ask the human once.

### Workstream-specific minimums (in addition to the template)

| Workstream | Handoff must explicitly state |
|------------|----------------------------------|
| **A** | `run_id` and provenance field names as implemented; where they appear (suggested / review / JSONL); any deviation from this plan’s naming. |
| **B** | Shape of `delta_changes` (and sidecar path if any); behavior for locked/confirmed rows; how `registry_or_config_changed` is surfaced once E exists. |
| **C** | Script names, subcommands, and which JSONL/summary fields each reads. |
| **D** | Schema / `schema_version` bumps; fixture IDs; migration flags documented. |
| **E** | Hash algorithm location (doc pointer), `meta.source_config_sha256` shape, gate and escape-hatch flag names, batch abort semantics. |
| **F** | Chosen directory name, default `--output` / discovery behavior, and `path_registry` relative path convention in emitted artifacts. |

---

## Parallel execution order (recommended)

- **Reporting:** each agent follows **Inter-agent reporting (mandatory handoffs)** before handoff. Agent 2 reads Agent 1’s log entry for provenance field names and registry layout; Agent 3 reads A/B summaries for JSONL shape; Agent 4 logs schema bumps and points other agents at new `schema_version` / conformance paths.

- Agent 1 (Artifact Prover): implement Workstream A first (run_id + hashes everywhere), **Workstream F** (registry folder layout + path updates), and **Workstream E** in lockstep (hash in `meta` + strict `--config-dir` gate + escape hatch) so operators get **one** migration story.

- Agent 2 (Delta Auditor): implement Workstream B once run_id plumbing exists; pick up **`registry_or_config_changed`** (or equivalent) once E’s fields exist.
- Agent 3 (Debug UX): implement Workstream C once JSONL summary fields are decided.
- Agent 4 (Schema Sheriff): implement Workstream D across all changes (versions + tests), including **registry MINOR bump**, suggested/review schema allowances for new provenance keys, and **SCHEMA.md / convention updates** for the new registry path + `terminology.yaml` resolution.

---

## Definition of done

- **Handoffs:** `handoff-log.md` in this plan directory contains entries for each completed agent/workstream bundle per **Inter-agent reporting**, so a new session can resume without re-reading the entire implementation history.
- Every `.suggested.yaml` and `.review.md` includes **run_id** + **input hashes**, and delta runs include **previous linkage**.
- **Registry state is explicit and aligned:** embedded registry lineage appears on suggested + review + JSONL; when `--config-dir` is supplied and the registry carries `meta.source_config_sha256`, **Leg 2 refuses to run** if the live config hash does not match (unless an explicit escape hatch was used and stamped).
- Every delta run emits a **change set** (in JSONL summary and/or sidecar file), including a clear signal when **the registry file or underlying config fingerprint changed** vs the previous run (so path churn is not mistaken for mapping-only edits).
- Humans can trace `.suggested.yaml → run_id → JSONL batch → provenance → what changed` reliably, including **whether Leg 2’s path universe matched the socotra-config on disk** for that run.
- **Layout:** the canonical `path-registry.yaml` lives only under the **dedicated `registry/` (or chosen) folder**, not as a loose file at the repo root.

