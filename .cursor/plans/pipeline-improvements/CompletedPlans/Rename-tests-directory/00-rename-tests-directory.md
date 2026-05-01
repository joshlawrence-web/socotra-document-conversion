# Plan: Rename `tests/` (conformance fixtures + runner)

**Status:** completed (2026-04-26)  
**Created:** 2026-04-26  
**Motivation:** The top-level directory `tests/` reads like a generic unit-test tree (pytest, `npm test`, etc.). In this repo it is **not** that: it holds **adversarial Socotra mini-configs**, **golden-file** outputs, a **fixture runner** that diffs `extract_paths.py` (and optionally Leg 2 artifacts), and **JSON Schema** for telemetry. A name that signals *pipeline conformance / regression goldens* reduces confusion for contributors and tooling.

---

## 1. What `tests/` actually does

| Piece | Role |
|--------|------|
| `conformance/fixtures/<name>/` | Each fixture: minimal `socotra-config/`, hand-written `mapping.yaml`, `golden/` frozen outputs, `actual/` (often gitignored) for live runs vs goldens. |
| `conformance/run-conformance.py` | Regression entrypoint: runs `extract_paths.py` per fixture, canonicalizes volatile registry meta, diffs against goldens; optionally diffs suggester outputs when `actual/` is populated. Supports `--update-goldens`. |
| `conformance/schemas/suggester-log.schema.json` | Draft 2020-12 JSON Schema for `.suggester-log.jsonl` telemetry (referenced from docs and skills). |
| `conformance/README.md` | Contract for layout, runner workflow, adding fixtures. |

So the folder is **conformance / golden regression** for the HTML → Velocity pipeline (Phase C in [PIPELINE_EVOLUTION_PLAN.md](../alpha-beta-plan/PIPELINE_EVOLUTION_PLAN.md)), not a conventional automated test package.

---

## 2. Suggested replacement names (pick one convention)

Names are ordered from **most explicit** to **shorter**. Subfolders can stay `fixtures/` and `schemas/` under the new root, or you can flatten—see §4.

| Candidate root | Pros | Cons |
|----------------|------|------|
| **`conformance/`** | Matches existing README title (“Conformance fixtures”); clearly not “library unit tests”. | Still generic in huge monorepos. |
| **`pipeline-conformance/`** | Unambiguous: belongs to this repo’s two-leg pipeline. | Longer path in docs and commands. |
| **`regression-fixtures/`** | Emphasizes golden diff workflow. | “Regression” alone is vague. |
| **`golden-suite/`** | Highlights frozen expected outputs. | Less obvious that mini Socotra configs live here. |
| **`fixtures/`** (repo root) | Short. | Collides mentally with pytest `conftest` / `conformance/fixtures`; easy to misread. |

**Recommendation:** Prefer **`conformance/`** (or **`pipeline-conformance/`** if you expect more conformance-style dirs later). Pair the runner with a name that is not `pytest`-shaped, e.g. keep `run-conformance.py` inside that directory or rename to `run_conformance.py` for clarity—optional second step.

---

## 3. Inventory: where `tests/` paths appear today

Use this as a checklist when renaming. After the move, run `rg 'tests/'` and `rg 'tests/run'` from repo root to catch stragglers (no `tests/` directory should remain).

### 3.1 Code (must update)

| File | Notes |
|------|--------|
| `conformance/run-conformance.py` | Sets `FIXTURES_DIR = REPO_ROOT / "conformance" / "fixtures"`; docstrings and `print(...)` messages embed `conformance/fixtures/...`. |
| `conformance/schemas/suggester-log.schema.json` | `$id` is `https://velocityconverter/conformance/schemas/suggester-log.schema.json` — update if you treat `$id` as stable URI (optional but good hygiene). |

### 3.2 Fixture-generated artifacts (bulk path strings)

Many `path-registry.yaml` files under `conformance/fixtures/*/golden/` and `conformance/fixtures/*/actual/` include **`meta.config_dir`** as an **absolute path** ending in `.../conformance/fixtures/<name>/socotra-config`. After a directory rename, either:

- re-run `python3 <new-path>/run-conformance.py --update-goldens` from a clean `actual/` so goldens pick up the new prefix, or  
- scripted find-replace **only** inside the old path segment (risky if machine-specific paths differ).

CI / other clones will have different usernames; the runner already ignores some volatile registry keys—confirm `config_dir` normalization still matches the runner’s ignore list after any path shape change.

### 3.3 Golden / hand-authored docs inside fixtures

Files that literally say `conformance/fixtures/...` in prose or YAML comments:

- `conformance/fixtures/*/golden/review.md` (several)
- `conformance/fixtures/*/golden/suggested.yaml` (comment headers in some)
- `conformance/fixtures/custom-naming/golden/review.md`
- `conformance/fixtures/*/actual/review.md` (if tracked; update or regenerate)

### 3.4 Repo docs

| File | Usage |
|------|--------|
| `README.md` | Table row for `conformance/`, “Testing” section commands. |
| `conformance/README.md` | Entire document is path-centric; rename heading and all commands. |
| `SCHEMA.md` | Multiple references to `conformance/schemas/suggester-log.schema.json` and one to `conformance/fixtures/custom-naming/`. |
| `CONFIG_COVERAGE.md` | Fixture path column + narrative references to `conformance/fixtures/...` and `conformance/run-conformance.py`. |
| [`PIPELINE_EVOLUTION_PLAN.md`](../alpha-beta-plan/PIPELINE_EVOLUTION_PLAN.md) | Extensive historical + procedural references. |
| [`PIPELINE_IMPROVEMENTS_PLAN.md`](../alpha-beta-plan/PIPELINE_IMPROVEMENTS_PLAN.md) | Runner invocation and contract pointers. |
| [`GENERALISATION_AUDIT.md`](../alpha-beta-plan/GENERALISATION_AUDIT.md) | At least one `conformance/fixtures/` mention (count may be stale). |

### 3.5 Skills and plans

| File | Usage |
|------|--------|
| `.cursor/skills/mapping-suggester/scripts/emit_telemetry.py` | Comment pointing at schema path. |
| `.cursor/skills/mapping-suggester/SKILL-output-formats.md` | Several `conformance/schemas/...` references. |
| `.cursor/plans/pipeline-improvements/State-improvement/00-state-linking-and-delta-audit.md` | `conformance/schemas/`, `tests/` in registry-move checklist. |

### 3.6 Likely no change

- `mapping-suggester/SKILL.md` — **no** `tests/` hits at time of audit (telemetry/schema lives in companion docs).
- `.cursor/skills/html-to-velocity/` — no dependency found on `tests/` paths.

### 3.7 External / tooling

- Any personal notes, CI YAML outside this repo, or chat logs that tell people to run `python3 conformance/run-conformance.py` — update manually if they exist.

---

## 4. Implementation outline (when you execute the rename)

1. **Choose** root name (`conformance/` recommended) and whether to **rename the script** (optional: `run-conformance.py` → `run_conformance.py`).
2. **Git mv** `tests/` → `<new>/` (preserves history).
3. **Edit** `run-conformance.py` (or renamed script): `REPO_ROOT` logic unchanged; update `FIXTURES_DIR` and user-facing strings.
4. **Replace** path strings across §3.3–§3.5 (structured search-replace `tests/` → `conformance/` or chosen name).
5. **Refresh goldens** or bulk-update `config_dir` inside YAML goldens/actuals per §3.2; run `python3 <new>/run-conformance.py` until exit `0`.
6. **Update** JSON Schema `$id` if you rely on it for documentation or validators.
7. **Verify:** `rg '\btests/'` from repo root (expect hits only in this historical plan or intentional prose); fix stray path hits.
8. **Optional:** Add a one-line **redirect note** at old path is not possible with directories—rely on changelog or commit message; if submodule consumers exist, flag **breaking path** in release notes.

---

## 5. Non-goals (this plan)

- Splitting `schemas/` out to repo root (could be a follow-up).
- Wiring JSONL validation into the runner (called out elsewhere as future work).
- Renaming `fixtures/` subfolder (usually keep it; it is standard vocabulary).

---

## 6. Success criteria

- One obvious top-level directory name for “golden conformance for the pipeline”.
- `python3 <that-dir>/run-conformance.py` exits `0` on a clean checkout.
- Documentation and skills reference the new paths only; `rg 'tests/fixtures'` returns no stale filesystem-path hits (aside from this plan’s historical mentions, if any).
