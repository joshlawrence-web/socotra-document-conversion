## Status

| Workstream | Deliverable | Status | File(s) |
|---|---|---|---|
| A | Invocation contract (written) | ✅ Done | This document |
| B | `pipeline-orchestrator` skill | ✅ Done | `.cursor/skills/pipeline-orchestrator/SKILL.md` |
| C | Leg 1 refusal guard | ✅ Done | `.cursor/skills/html-to-velocity/SKILL.md` |
| C | Leg 2 refusal guard | ✅ Done | `.cursor/skills/mapping-suggester/SKILL.md` |
| D | Missing-inputs UX (in orchestrator) | ✅ Done | `.cursor/skills/pipeline-orchestrator/SKILL.md` §Missing inputs |
| E | Demo runbook | ✅ Done | `.cursor/plans/pipeline-improvements/DEMO-RUNBOOK.md` |

**Acceptance criteria checklist (run these in Cursor to verify):**

- [ ] `RUN_PIPELINE` absent → orchestrator prints refusal (no reads/writes)
- [ ] Vague "run the suggester" → mapping-suggester refuses, shows orchestrator example
- [ ] Vague "convert this HTML" → html-to-velocity refuses, shows orchestrator example
- [ ] Valid `RUN_PIPELINE leg1 input=…` → preflight shown, no writes until PROCEED
- [ ] Valid `RUN_PIPELINE leg2 mode=terse mapping=… registry=…` → preflight shown, runs after PROCEED
- [ ] Partial `RUN_PIPELINE leg2` (no mode/mapping) → asks only for missing fields
- [ ] Teammate can run Leg 1 + Leg 2 under 5 min from the demo runbook

---

## Implementation log

### 2026-05-01 — All artifacts created (Claude Code)

**Created:**
- `.cursor/skills/pipeline-orchestrator/SKILL.md` — new orchestrator skill (Workstream B + D)
  - Hard gate: refuses any message without `RUN_PIPELINE` token; prints copy-paste refusal block
  - Steps 1–6: parse → validate → preflight summary → PROCEED gate → dispatch → post-run summary
  - Dispatches Leg 1 via `python3 .cursor/skills/html-to-velocity/scripts/convert.py`
  - Dispatches Leg 2 via `python3 scripts/leg2_fill_mapping.py` (exists at repo root)
  - `leg1+leg2` chains automatically: runs Leg 1, derives mapping path, runs Leg 2
  - § Missing inputs: asks only for missing fields; auto-discovers `.mapping.yaml` candidates
- `.cursor/plans/pipeline-improvements/DEMO-RUNBOOK.md` — teammate runbook (Workstream E)
  - 4 copy-paste invocations (leg1, leg2, leg1+leg2, batch)
  - "Good output" guide; safety story; troubleshooting table

**Modified:**
- `.cursor/skills/html-to-velocity/SKILL.md` — added refusal guard at top (Workstream C)
  - If `RUN_PIPELINE` absent: prints orchestrator one-liners and stops
  - If `RUN_PIPELINE` present: continues with normal execution (dev use permitted per plan)
- `.cursor/skills/mapping-suggester/SKILL.md` — same refusal guard pattern (Workstream C)
- This plan document — added Status table and this log

**Open items:**
- Acceptance criteria above are all unchecked — these are AI behavioral instructions and can only be verified by running the skills in Cursor
- Decision point (deferred): if the orchestrator gate should be the **only** path even for dev use, Leg 1 and Leg 2 should always redirect regardless of `RUN_PIPELINE`. Current behavior allows direct invocation with `RUN_PIPELINE` as an intentional dev escape hatch (per Workstream C: "remain usable on their own for development")
- Move this plan to `CompletedPlans/` once acceptance criteria are verified

---

## Goal

Create a single **Pipeline Orchestrator Agent** (a dedicated “chat entrypoint”) that makes the HTML → Velocity pipeline **reliably callable via conversation** with **minimal required inputs**, while being **hard to invoke accidentally**.

For demos, teammates should interact with exactly one agent. That agent validates inputs, previews the run, requires explicit confirmation, and only then invokes Leg 1 (`html-to-velocity`) and/or Leg 2 (`mapping-suggester`).

---

## Constraints / non-goals

- No GUI / web UI: invocation happens via chat only.
- “Accidental invocation” must be prevented even if a user says something vague like “run the suggester”.
- Default behavior must be safe: **no file reads/writes** until inputs are validated and the user confirms intent.
- Keep the experience fast for demos: minimal back-and-forth once the minimum inputs are provided.
- Do not rely on “the user will remember the right phrasing”. The agent must enforce a contract.
- Prefer “repo-contained” behavior: a teammate clones/opens this repo and gets the same orchestration behavior.

---

## Recommendation: keep the agent inside this repo

Put the orchestrator **in this project folder** (under `.cursor/`) so:

- Teammates can clone/open the repo and immediately run the same demo.
- The orchestrator can reliably locate the pipeline artifacts (`samples/`, `path-registry.yaml`, `.cursor/skills/`).
- You avoid machine-specific global configuration and drift.

Only consider a “global” agent outside the repo if you want the orchestrator to work across many unrelated projects. For this demo/product-prototype, **repo-local is the safest and easiest**.

---

## Current baseline (what exists today)

- The repo already describes the pipeline and a quick-start “say this in chat” flow in `README.md`.
- `mapping-suggester` already has a strong internal contract (mode selection, shape probe, schema checks), but it focuses on run correctness, not preventing accidental starts.

This plan adds a single orchestrator agent that provides an explicit **invocation gate**: minimal inputs, validation, and a confirmation handshake before any reads/writes.

---

## Workstream A — Define the Orchestrator “Invocation Contract”

### Deliverable

A stable, written contract that the orchestrator enforces, including demo-ready examples short enough to copy/paste.

### Contract (minimum inputs)

For the orchestrator to proceed, it must have:

- **Operation**: which action to run
  - `leg1` (convert HTML → `.vm` + `.mapping.yaml`)
  - `leg2` (suggest paths for an existing `.mapping.yaml`)
  - (optional) `leg1+leg2` (end-to-end demo in one orchestration)
- **Mode** (Leg 2 only): `full | terse | delta | batch`
- **File inputs** (absolute or repo-relative paths)
  - Leg 1: one `*.html`
  - Leg 2: one or more `*.mapping.yaml` + one `path-registry.yaml`
- **Output location** (optional if there is a well-defined default)
  - Leg 1: default next to the input (current repo behavior) OR `samples/output/<stem>/` (preferred demo behavior—pick one and lock it)
  - Leg 2: default `samples/output/<stem>/` (per `SKILL.md`)
- **Explicit confirmation**: a final “Proceed” step after the orchestrator prints a preview of resolved inputs and expected writes.

### Anti-accidental rule (hard gate)

The orchestrator must **not** proceed unless:

- the user’s message includes an explicit **run intent token**, e.g. `RUN_PIPELINE` (case-insensitive accepted), AND
- at least the minimum inputs above are present or can be resolved from the message, AND
- the assistant has echoed back a “Resolved inputs” block and the user has replied with `PROCEED` (or `yes, proceed`).

This two-step handshake is intentionally redundant; it is the primary defense against accidental invocation during demos.

### Demo-ready invocation examples

Leg 1:

> `RUN_PIPELINE leg1 input=samples/input/claim-form.html output=samples/output`

Leg 2:

> `RUN_PIPELINE leg2 mode=terse mapping=samples/output/claim-form/claim-form.mapping.yaml registry=path-registry.yaml`

Leg 2 delta:

> `RUN_PIPELINE leg2 mode=delta mapping=samples/output/claim-form/claim-form.mapping.yaml registry=path-registry.yaml`

Batch:

> `RUN_PIPELINE leg2 mode=batch mapping=[samples/output/a/a.mapping.yaml, samples/output/b/b.mapping.yaml] registry=path-registry.yaml`

### Acceptance criteria

- A vague chat like “can you suggest paths for this mapping?” never runs.
- A teammate can copy/paste one line (above) and reach the confirmation step.
- The assistant always prints a “Resolved inputs” block before doing any work.

---

## Workstream B — Build the Pipeline Orchestrator Agent (the only entrypoint)

### Deliverable

A new orchestrator under `.cursor/skills/` (recommended name: `pipeline-orchestrator`) whose only job is to:

- parse/validate the invocation contract
- show a deterministic preflight summary
- require confirmation
- dispatch to Leg 1 and/or Leg 2

### Tasks

- **Create the orchestrator skill folder**: `.cursor/skills/pipeline-orchestrator/`
- **Define invocation format(s)** the orchestrator accepts:
  - primary: `RUN_PIPELINE` + `key=value` pairs (copy/paste friendly)
  - optional: JSON block (machine-friendly)
- **Implement parsing + validation** (shared module is OK, but keep it near the orchestrator):
  - parse `operation`, `mode`, `input`/`mapping`/`registry`, `output`
  - normalize repo-relative paths
  - reject paths outside the repo unless explicitly allowed (demo-safe default: reject)
  - file existence + extension checks
- **Preflight summary (always printed)**:
  - operation, mode, inputs, resolved output folder(s)
  - explicit list of files that will be written/overwritten
- **Confirmation**:
  - require `PROCEED` before any reads/writes
  - if not received, stop and show the one-line invocation examples again
- **Dispatch implementation choice**:
  - preferred: call the existing scripts (`convert.py`, suggester runner) so behavior matches the CLI outputs
  - acceptable: invoke the skill logic directly if the code is already importable (only if it reduces duplication)

### Guardrails

- **No reads/writes before confirmation** (strict mode).
- **No companion-file reads** (for Leg 2) before confirmation.
- **Dry-run preview** is always shown, even when everything is valid.

### Acceptance criteria

- Given a well-formed one-liner invocation, the system reaches “Resolved inputs” in one turn.
- Given a malformed invocation, the system stops with a single actionable error message.
- No outputs are read/written unless `PROCEED` is received.

---

## Workstream C — Make Leg 1 / Leg 2 “internal tools” (still runnable, but not footguns)

### Deliverable

Leg 1 and Leg 2 remain usable on their own for development, but their instructions strongly steer demos toward the orchestrator, and they refuse to run without the same explicit intent token.

### Tasks

- In both `html-to-velocity/SKILL.md` and `mapping-suggester/SKILL.md`:
  - add a top section: “For demos, use `pipeline-orchestrator`.”
  - add refusal behavior:
    - if `RUN_PIPELINE` not present, do not run; instead print:
      - the orchestrator one-liner examples
      - the minimal required inputs
  - ensure trigger phrases in skill metadata bias toward *help/explain* vs *execute* unless token present

### Acceptance criteria

- Normal documentation questions do not trigger a run.
- The assistant guides the user to the orchestrator one-line invocation format.

---

## Workstream D — Minimal-input UX: eliminate ambiguous questions

### Deliverable

A deterministic question flow that only asks for what is missing, and asks it in the smallest possible form.

### Tasks

- Define a canonical “Missing inputs” prompt format:
  - ask only for the missing fields
  - present allowed values (e.g., mode list)
  - show example reply
- Add a “path auto-discovery” rule (optional, but demo-friendly):
  - if `mapping=` is omitted, allow selecting from the most recent `samples/output/**/<stem>.mapping.yaml` files
  - still requires `RUN_PIPELINE` + `PROCEED`

### Acceptance criteria

- If the user supplies everything, no follow-up questions.
- If the user supplies only `RUN_PIPELINE leg2` the assistant asks only for mode + mapping + registry (and nothing else).

---

## Workstream E — Demo script + team handoff docs

### Deliverable

A single markdown doc that a teammate can follow to reproduce the demo without learning internals.

### Tasks

- Add a short “Demo runbook” Markdown doc under `.cursor/plans/pipeline-improvements/` (alongside existing pipeline plans):
  - prerequisites
  - 2–3 copy/paste invocations
  - what files to open (`.review.md`) and what “good output” looks like
- Include a “Safety story” section:
  - explain why `RUN_PIPELINE` + `PROCEED` exists
  - show an example of a vague request that does *not* run

### Acceptance criteria

- A teammate can run Leg 1 + Leg 2 in under 5 minutes by copy/paste.
- A reviewer understands why accidental invocation is prevented.

---

## Recommended execution order

- Start with Workstream A (contract) and immediately implement Workstream B (invocation gate), because everything else depends on it.
- Then update Workstream C (skill triggers) so the gate is actually enforced.
- Finally refine Workstream D/E for demo polish.

---

## Definition of done

- The orchestrator is the clear demo entrypoint and enforces **(1) RUN_PIPELINE** and **(2) PROCEED** before any reads/writes.
- The minimum input set is documented and enforced by the orchestrator.
- Demo invocations are single-line and reproducible.

