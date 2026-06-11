# Pipeline Data-Flow Diagram (Leg 0–4 with File Types)

**Status:** Done
**Completed:** 2026-06-09
**When done:** set `Status: Done`, add `Completed:` date, move folder to `CompletedPlans/` (§6).
**Created:** 2026-06-09
**Item:** Plan-for-plans #4

## START HERE (implementing agent)

Produce a canonical Leg 0–4 data-flow diagram that shows every file artifact and its type at each stage. Target: `docs/pipeline-dataflow.md` (standalone) + embedded in `README.md`.

**Read in this order:**
1. This file — §2 (decisions), §3 (task list)
2. `README.md` — existing diagram (Leg 1–3 only; file types not labeled)
3. `docs/` — existing docs folder to understand style
4. `scripts/agent_tools.py` — `run_leg0()`, `run_leg1()`, etc. — authoritative list of inputs/outputs per leg

---

## 1. Background

The README mermaid diagram covers only Legs 1–3 and does not label file types. When a new contributor reads the repo, they cannot tell at a glance:

- Which legs accept `.docx` vs `.html` vs `.yaml`
- Which outputs are "hand-off" artifacts (sent to customer or reviewed by human) vs internal pipeline state
- Where the hot-swap deploy step happens
- What branching point produces the plugin vs the template

A complete, labeled diagram fixes onboarding confusion and serves as authoritative reference for future plan authors.

---

## 2. Decisions

| # | Topic | Decision |
|---|-------|----------|
| D1 | Format | Mermaid `flowchart LR` — renders natively in GitHub and in Cursor. |
| D2 | Canonical location | `docs/pipeline-dataflow.md` — standalone file for deep-linking. Also embedded in `README.md` replacing the existing diagram (D3 in plan #0). Plans should cross-reference this file. |
| D3 | File type labels | Every artifact node shows the file extension and a brief description in the node label. E.g. `".mapping.yaml\n(TBD placeholders)"`. |
| D4 | Human touchpoints | Nodes that require human action (customer fills conditional-form; human reviews `.review.md`; human deploys `.vm`) styled with a different shape (`[/text/]` parallelogram or `[(text)]` cylinder). |
| D5 | Leg 0 branching | Show both paths from Leg 0: (a) `.raw.html` → customer fills `.conditional-form.md` → `.conditional-registry.yaml` → Leg 2+3 ; (b) `.mapping.yaml` → Leg 2+3 directly (when customer skips the conditional form). |
| D6 | Leg 4 branch | Show Leg 4 as a branch off `.suggested.yaml` (not off `.final.vm`) — the plugin is generated from paths, not from the rendered template. |
| D7 | Deploy step | Show a `socotra-config/` node as the deploy target, with arrows from `.final.vm` and `SnapshotPlugin.java`. |
| D8 | Multi-leg chains | Annotate the arrows with the `RUN_PIPELINE` chain that produces them, e.g. `leg0+leg2+leg3`. |
| D9 | Prose companion | Below the diagram, add a one-paragraph plain-English walk-through of the full flow. Not a repetition of README — written for someone who is stuck looking at a broken output file and wants to know which leg produced it. |

---

## 3. Task list

### T1 — Draft full mermaid diagram

**Goal:** Write the complete Leg 0–4 flowchart in `docs/pipeline-dataflow.md`.

**Full node inventory:**

Inputs:
- `DOC` — `.docx` / `.pdf`
- `HTML` — `.html` mockup

Leg 0 outputs:
- `RAW_HTML` — `.raw.html`
- `ANNOTATED_HTML` — `.annotated.html`
- `FIELDS_YAML` — `.fields.yaml`
- `LEG0_MAPPING` — `.mapping.yaml` (Leg 0 flavour)
- `COND_FORM` — `.conditional-form.md` → **customer fills** → `.conditional-registry.yaml`

Leg 1 outputs:
- `MAPPING` — `.mapping.yaml`

Leg 2 outputs:
- `SUGGESTED` — `.suggested.yaml`
- `REVIEW` — `.review.md` → **human review (optional)**

Leg 3 outputs:
- `FINAL_VM` — `.final.vm` → deploy to `socotra-config/`

Leg 4 outputs:
- `PLUGIN_JAVA` — `SnapshotPlugin.java` → deploy to `socotra-config/`

Registry inputs to Leg 2:
- `REGISTRY` — `path-registry.yaml`
- `SCHEMA_IDX` — `sdk-schema-index.yaml`

**Files:** `docs/pipeline-dataflow.md` (new)

---

### T2 — Prose walk-through

**Goal:** 3–5 paragraph plain-English section after the diagram in `docs/pipeline-dataflow.md`.

Structure:
1. Starting from a Word/PDF doc (Leg 0 path)
2. Starting from an HTML mockup (Leg 1 path)
3. Path matching and review (Leg 2)
4. Template finalisation (Leg 3)
5. Plugin generation (Leg 4)
6. Deploying to Socotra

**Files:** `docs/pipeline-dataflow.md`

---

### T3 — Embed in README.md

**Goal:** Replace the existing Leg 1–3 mermaid diagram in README.md with the new Leg 0–4 version (same mermaid source as T1).

Add a link: `> Full data-flow reference: [docs/pipeline-dataflow.md](docs/pipeline-dataflow.md)`

**Files:** `README.md`

---

### T4 — Cross-reference in CLAUDE.md

**Goal:** In the CLAUDE.md architecture overview table (added in plan #0 / T3), add a line:

```
> Full data-flow diagram: [docs/pipeline-dataflow.md](docs/pipeline-dataflow.md)
```

**Files:** `CLAUDE.md`

---

## 4. Definition of done

- `docs/pipeline-dataflow.md` exists and renders correctly in GitHub (mermaid block + prose)
- Diagram includes all 5 legs, all major artifact files with extensions, human touchpoints, and deploy step
- README.md diagram replaced (Leg 0–4)
- Link from CLAUDE.md to `docs/pipeline-dataflow.md`

---

## 5. Files touched

| File | Change |
|------|--------|
| `docs/pipeline-dataflow.md` | **New** — standalone diagram + prose |
| `README.md` | Replace existing diagram; add link to docs/ |
| `CLAUDE.md` | Add link to diagram in architecture overview |

---

## 6. Self-certification (completing agent — required)

When every item in §4 Definition of done is satisfied:

1. Edit this file: change `**Status:** Open` → `**Status:** Done` and add `**Completed:** <date>`.
2. Move this folder: `mv .cursor/plans/pipeline-improvements/04-pipeline-dataflow-diagram/ .cursor/plans/pipeline-improvements/CompletedPlans/`
3. Commit both changes with your implementation (or in a follow-up commit).

**Do not skip this step.** Plans left "Open" after completion create false signals about remaining work.
