# Leg 4 — Document snapshot plugin — history log

Append-only. **Newest session first.** Link from [00-plan.md](./00-plan.md).

---

## 2026-06-03 — Leg 4 Phase 3 complete

### Summary
- P3.1: `run_leg4()` added to `scripts/agent_tools.py` — mirrors `run_leg3()`;
  dispatches `leg4_generate_plugin.py` with `--suggested`, optional `--customer-jar`,
  `--datamodel-jar`, and `--compile-check`. Artifacts discovered by globbing
  `*DocumentDataSnapshotPluginImpl.java` and `{stem}.plugin-report.md`.
- P3.1: `scripts/agent.py` extended — `leg4` and `leg1+leg2+leg3+leg4` added to
  `VALID_OPS`; parse regex updated (longest match first); `compile_check` param
  parsed (default `true`); preflight updated to show compile flag and leg4 artifact
  predictions (product read from YAML via `_try_read_product`); full dispatch block
  added; `guided_mode` updated with options 6 and 7.
- P3.2: `.cursor/skills/pipeline-orchestrator/SKILL.md` — added leg4 / full-pipeline
  examples, `compile_check` to invocation table, Leg 4 in "How it works" list.

### Files touched
- `scripts/agent_tools.py` (amended: `_try_read_product`, valid_ops, leg4 predict, `build_preflight`, `run_leg4`)
- `scripts/agent.py` (amended: import, VALID_OPS, REFUSAL, parse regex, compile_check, preflight, dispatch, guided_mode)
- `.cursor/skills/pipeline-orchestrator/SKILL.md` (amended)
- `00-plan.md` (Phase 3 checked, status updated)

### Verification
```bash
# Leg 4 standalone
python3 scripts/agent.py --yes "RUN_PIPELINE leg4 suggested=samples/output/Simple-form/Simple-form.suggested.yaml"
# → Leg 4 artifacts: Simple-form.plugin-report.md, ItemCareDocumentDataSnapshotPluginImpl.java

# Full pipeline preflight (type anything other than PROCEED to cancel)
python3 scripts/agent.py "RUN_PIPELINE leg1+leg2+leg3+leg4 input=samples/input/Simple-form.html registry=registry/path-registry.yaml output=samples/output"
# → 10 artifacts listed including plugin + report
```

### Open items / next
- Phase 4 enrichment (§16) — deferred.

---

## 2026-06-03 — Leg 4 Phase 2 complete

### Summary
- P2.1: `.cursor/skills/plugin-builder/SKILL.md` — full skill card with CLI
  reference, design decisions table, output shape, and constraints.
- P2.2: `docs/SCHEMA.md` — updated Purpose section (three→four skills),
  added Leg 4 changelog entry (tenth + eleventh pipeline artifacts).
- P2.3: `CLAUDE.md` — new "Generating the DocumentDataSnapshotPlugin (Leg 4)"
  section with trigger phrases and the direct `leg4_generate_plugin.py` command.
- P0.4: `README.md` — one-line Leg 4 pointer after the Leg 3 description.

### Files touched
- `.cursor/skills/plugin-builder/SKILL.md` (new)
- `docs/SCHEMA.md` (amended)
- `CLAUDE.md` (amended)
- `README.md` (amended)
- `00-plan.md` (P0.4 + P2.1–P2.3 checked)

### Open items / next
- Phase 3 pipeline integration (`RUN_PIPELINE leg4`, `agent_tools.py`, `agent.py`) — deferred.
- Phase 4 enrichment — deferred.

---

## 2026-06-02 — Leg 4 Phase 1 complete

### Summary
- Implemented **P1.1–P1.8**: `scripts/leg4_generate_plugin.py` generates one
  `{Product}DocumentDataSnapshotPluginImpl.java` per product from a
  `.suggested.yaml`, deterministically (no LLM).
- Mirrors `leg3_substitute.py` (`_repo_root`, `_load_yaml`, argparse style).
- `javap` introspection verifies the plugin interface + nested request types
  (`{Product}QuoteRequest`, `{Product}Request`, `InvoiceDetailsRequest`); fails
  fast (exit 1) if any are missing. `--datamodel-jar` defaults to the newest
  `build/core-datamodel-v*.jar`.
- Emitted Java matches §10 golden template: quote → `request.quote()`; policy →
  fail-loud `orElseThrow` with SLF4J ERROR + `IllegalStateException` (D10);
  invoice → empty-map stub + `log.warn` + TODO.
- High-confidence path validation walks the segment type via `javap`
  (report-only, non-fatal — §9). `$data.policyNumber` correctly surfaces a
  **warning** (no `policyNumber()` on `ItemCareSegment`); the whole object is
  still passed so it resolves at runtime if present on the live model.
- `<stem>.plugin-report.md` written per §13; `--compile-check` runs `javac`.
- **Generated Java compiles: yes** (customer + datamodel + slf4j on classpath).

### Files touched
- `scripts/leg4_generate_plugin.py` (new)
- `samples/output/Simple-form/ItemCareDocumentDataSnapshotPluginImpl.java` (generated)
- `samples/output/Simple-form/Simple-form.plugin-report.md` (generated)
- `00-plan.md`, `README.md` (status + P1 checkboxes)

### Verification (§12 — all pass)
```bash
python3 scripts/leg4_generate_plugin.py \
  --suggested samples/output/Simple-form/Simple-form.suggested.yaml \
  --output-dir samples/output/Simple-form \
  --customer-jar build/customer-config.jar \
  --datamodel-jar build/core-datamodel-v1.7.61.jar \
  --compile-check
# exit 0 · Product=ItemCare high=1 ignored=3 compile=PASS
# Java + report written · `git status socotra-config/` clean (0 changes)
```

### Open items / next
- Phase 2 (skill, `docs/SCHEMA.md`, `CLAUDE.md` one-liner) — **not started** (per user, Phase 1 only this session).
- Phase 3 pipeline integration + Phase 4 enrichment remain deferred (§16).

---

## 2026-06-02 — Planning session (user + agent)

### Context

User asked to enable **Socotra `DocumentDataSnapshotPlugin`** generation from pipeline output, using:

- `samples/output/Simple-form/Simple-form.suggested.yaml` as the **source of truth** (alongside Leg 3 for `.final.vm`)
- `build/` JARs (`customer-config.jar`, `core-datamodel-*.jar`) for compile-correct types
- A **simple plugin-builder skill** (later: thin wrapper over a Python script)

### Investigation summary

- `build/customer-config.jar` exposes `DocumentDataSnapshotPlugin` with `ItemCareQuoteRequest`, `ItemCareRequest`, `InvoiceDetailsRequest` nested types; deployed config has **no implementation yet** (stub only).
- `DocumentDataSnapshot.builder().renderingData(Object)` in `core-datamodel-*.jar`.
- Path registry assumes `$data` = `renderingData` root (segment-shaped paths like `$data.policyNumber`).
- Simple-form `.suggested.yaml`: 1 high, 1 medium, 2 low (`supply-from-plugin`); `.final.vm` still has 2 `$TBD_*` tokens.

### Questions asked (initial plan)

Agent proposed Leg 4 with questions on: pipeline placement, per-document vs per-product plugin, renderingData shape, YAML patching, confidence policy, output paths, loops, testing.

### User answers (locked → see 00-plan §3)

| Topic | Answer |
|--------|--------|
| TODOs / semantics | Fine to leave open; refine later |
| Plugin scope | **1 plugin per product**, many documents |
| renderingData | **Pass full object**; Velocity navigates |
| YAML / plugin-only path patching | **Later phase** |
| Confidence | **High only**; ignore medium/low — lowest bar |
| Output | `samples/output/Simple-form/`; no `config.json` |
| JARs | For **compile-check** / one-shot deploy |
| Loops | Keep simple; moot for now |
| Tests | Next phase |
| Script vs AI | User asked if **Python can write Java accurately** — **yes** for MVP (template + javap); agreed as approach |
| Missing segment | **Fail loud** with **log** so failure is obvious to operators |

### Outputs from this session

- Created [00-plan.md](./00-plan.md) with task checklist (Phases 0–4).
- Created this history file.

### Next agent actions

1. Open [README.md](./README.md) → [00-plan.md](./00-plan.md) **START HERE**.
2. Implement **Phase 1** (§7, §11): `scripts/leg4_generate_plugin.py` using golden Java in §10.
3. Meet **§12 Definition of done** on Simple-form.
4. Append handoff per §18.

### Plan enrichment (same session)

`00-plan.md` expanded with repo signposting, input contract, javap cookbook, golden Java, path-validation algorithm, report layout, compile command, Phase 3 sketch, and definition-of-done block so a cold-start agent can implement without re-reading the chat.

### Verification commands (after Phase 1)

```bash
python3 scripts/leg4_generate_plugin.py \
  --suggested samples/output/Simple-form/Simple-form.suggested.yaml \
  --output-dir samples/output/Simple-form \
  --customer-jar build/customer-config.jar \
  --datamodel-jar build/core-datamodel-v1.7.61.jar \
  --compile-check
```

---

<!-- Template for future entries:

## YYYY-MM-DD — Short title

### Summary
- bullet

### Files touched
- path

### Verification
- command

-->
