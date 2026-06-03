# Leg 4 — Plugin Enrichment (Phase 4)

**Status:** Not started  
**Created:** 2026-06-03  
**Predecessor:** [Leg4-document-snapshot-plugin](../Leg4-document-snapshot-plugin/00-plan.md) — Phases 1–3 complete  
**History:** [history.md](./history.md) (append-only)

---

## START HERE (implementing agent)

Phase 4 extends `scripts/leg4_generate_plugin.py` and the broader Leg 4 pipeline
with features deferred from the MVP. The MVP (Phases 1–3) already:

- Generates a compile-correct `{Product}DocumentDataSnapshotPlugin` Java class
- Passes the full segment / quote object as `renderingData` (D3)
- Reports high-confidence path validation in `<stem>.plugin-report.md`
- Is wired into `RUN_PIPELINE leg4` and `leg1+leg2+leg3+leg4` via `agent.py`

**Read in this order:**

1. This file — §2 (locked decisions from MVP), §3 (new decisions), §4 (task list)
2. `scripts/leg4_generate_plugin.py` — current implementation
3. `samples/output/Simple-form/Simple-form.suggested.yaml` — pilot input
4. `samples/output/Simple-form/ItemCareDocumentDataSnapshotPluginImpl.java` — current output

**Do not** change the MVP behaviour (full-object renderingData, single-overload per request type)
unless a specific task below says so.

---

## 1. Background — what the MVP does not do

The MVP passes the entire segment or quote object as `renderingData`. This is correct for
Velocity templates that navigate `$data.policyNumber` etc. — the platform resolves paths at
render time.

What it **doesn't** do:

- Emit per-document branching when a product has multiple document templates with
  different `renderingData` shapes
- Handle medium/low-confidence variables (they stay as `$TBD_*` in the template)
- Auto-suggest or patch the `.suggested.yaml` for `supply-from-plugin` fields
- Copy the generated Java into `socotra-config/plugins/java/` automatically
- Test the generated output
- Handle `#foreach` / loop variables that require snapshot iteration

---

## 2. Locked decisions carried forward from MVP

Do not reverse without a new design decision entry.

| # | Topic | Decision |
|---|--------|----------|
| D2 | Plugin cardinality | One plugin per product, many document templates |
| D3 | `renderingData` shape | Pass full platform object — Velocity navigates |
| D5 | Confidence gate | `high` only in path-validation report |
| D6 | Output location | `samples/output/<stem>/` only unless deploy task says otherwise |
| D7 | Compile truth | `build/customer-config.jar` + newest `build/core-datamodel-v*.jar` |
| D10 | Missing segment | Fail loud: ERROR log + throw `IllegalStateException` |

---

## 3. New decisions needed (fill in before implementing each task)

| # | Topic | Decision |
|---|--------|----------|
| N1 | Per-document branching trigger | How does the script detect that a product needs branching? (e.g. multiple stems with same product in `.suggested.yaml`s, or an explicit `documents:` key in YAML?) |
| N2 | Medium/low stub shape | Emit `// TODO` stubs in Java, or only in the report? |
| N3 | Deploy target path | Where exactly inside `socotra-config/` does the `.java` file land? |
| N4 | Test framework | Pure pytest + subprocess? Or separate `javac`-based test harness? |
| N5 | Loop snapshot contract | What does Socotra expect for `#foreach` — does the platform iterate, or must the plugin return a `List`? |

---

## 4. Task list

Check boxes when done; append a handoff to [history.md](./history.md).

### P4.1 — `supply-from-plugin` YAML patching / alias suggestions

Leg 2 tags unresolved fields with `next-action: supply-from-plugin` in `reasoning`.
Today those remain as `$TBD_*` in the final template.

**Goal:** detect these fields in the `.suggested.yaml`, look up the segment/quote
type via `javap`, and suggest a `data_source` path (or emit a warning if no method
matches). Write suggestions back into the YAML (or a new `.enriched.yaml`) so
a subsequent Leg 3 run can substitute them.

**Files:**
- `scripts/leg4_generate_plugin.py` — new `--enrich-suggested` flag (or separate script)
- `samples/output/<stem>/<stem>.suggested.yaml` — updated with new `data_source` values
- `<stem>.plugin-report.md` — new "YAML enrichment" section

**Definition of done:**
- At least one `supply-from-plugin` field in Simple-form gets a suggested path
- Running Leg 3 after enrichment substitutes the newly-suggested path

---

### P4.2 — `supply-from-plugin` computed fields in Java

Some fields can't be navigated directly from the platform object and need computed
values in the plugin (e.g. formatted dates, concatenated names).

**Goal:** for fields tagged `next-action: supply-from-plugin` that have no direct
path match, emit a TODO stub method in the Java class with a comment describing
what the field needs.

**Files:**
- `scripts/leg4_generate_plugin.py` — extend Java template with stub methods
- `samples/output/Simple-form/ItemCareDocumentDataSnapshotPluginImpl.java` — new stubs

**Decision needed:** N2 (stub shape).

---

### P4.3 — Per-document `request.config().name()` branching

When a product has multiple document templates with different `renderingData` shapes
(e.g. one policy doc uses segment, another uses quote), the single-overload plugin
needs a `switch` or `if` on `request.config().name()` to return the right object.

**Goal:** detect multi-document products from multiple `.suggested.yaml` inputs (or
a new `documents:` key), emit a branching `dataSnapshot(ItemCareRequest)` method.

**Files:**
- `scripts/leg4_generate_plugin.py` — multi-stem / multi-document mode
- Golden Java template extended with branching pattern

**Decision needed:** N1 (trigger mechanism).

**Note:** Do not break the single-document case — it should remain the default.

---

### P4.4 — Copy to `socotra-config/plugins/java/`

Today the generated `.java` file lands in `samples/output/<stem>/` and must be
copied manually.

**Goal:** add a `--deploy` flag to `leg4_generate_plugin.py` (and a `deploy=true`
param to `RUN_PIPELINE leg4`) that copies the file to the correct location inside
`socotra-config/plugins/java/`.

**Files:**
- `scripts/leg4_generate_plugin.py` — `--deploy` flag
- `scripts/agent_tools.py` — pass `deploy` to `run_leg4()`
- `scripts/agent.py` — expose `deploy=true` in invocation
- `CLAUDE.md` — add deploy trigger phrases

**Decision needed:** N3 (exact target path in `socotra-config/`).

---

### P4.5 — Conformance + unit tests

**Goal:** pytest suite that:
- Runs `leg4_generate_plugin.py` on `Simple-form.suggested.yaml`
- Asserts the Java file is written and compiles
- Asserts the plugin-report contains expected sections
- Asserts `run_leg4()` in `agent_tools.py` returns `ok=True`

**Files:**
- `tests/test_leg4.py` (new)

**Decision needed:** N4 (test framework).

---

### P4.6 — `#foreach` / loop snapshot logic

Velocity `#foreach` loops in `.final.vm` require the plugin to return a collection
as `renderingData` (or a wrapper object that Socotra iterates). Today the plugin
passes a single object; loop variables are out of scope.

**Goal:** understand the Socotra contract for loop documents, then extend the
Java template to return the correct collection type.

**Files:**
- `scripts/leg4_generate_plugin.py` — loop-aware `renderingData` shape
- `registry/path-registry.yaml` — document loop convention if needed

**Decision needed:** N5 (Socotra loop contract).

**Pre-requisite:** confirm with Socotra docs / platform team what `renderingData`
must look like when the template uses `#foreach`.

---

## 5. Recommended order

1. **P4.5** (tests) — establish a regression baseline before changing behaviour
2. **P4.1** (YAML enrichment) — highest pipeline value; closes the `$TBD_*` gap
3. **P4.2** (stub methods) — low effort, makes generated Java more useful
4. **P4.4** (deploy flag) — removes a manual step
5. **P4.3** (branching) — only needed once you have multi-document products
6. **P4.6** (loops) — needs platform clarification first

---

## 6. Repo signposting

| Path | Role |
|------|------|
| `scripts/leg4_generate_plugin.py` | Main script to extend |
| `scripts/agent_tools.py` | `run_leg4()` — extend params as needed |
| `scripts/agent.py` | Invocation dispatch — add new params |
| `samples/output/Simple-form/Simple-form.suggested.yaml` | Pilot input |
| `samples/output/Simple-form/ItemCareDocumentDataSnapshotPluginImpl.java` | Current output — extend, don't replace |
| `build/customer-config.jar` | Plugin interface + request types |
| `build/core-datamodel-v1.7.61.jar` | Platform model types |
| `.cursor/skills/plugin-builder/SKILL.md` | User-facing skill — update trigger phrases when adding flags |
| `CLAUDE.md` | Pipeline trigger phrases — update for new flags/ops |
