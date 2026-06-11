# Product Improvement List

**Generated:** 2026-06-09  
**Source:** Pipeline audit + architectural review

---

## Core Architecture Principle (Document This First)

This pipeline is **product-agnostic**. Swap three things to target any Socotra customer:

1. `registry/path-registry.yaml` — regenerated from their `socotra-config/` via `extract_paths.py`
2. `build/customer-config.jar` + `build/core-datamodel-*.jar` — their compiled artifacts (Leg 4)
3. `socotra-config/` — their config directory (drives registry regen)

ZenCover is the bundled demo only. Every pipeline command that accepts `registry=` or `--customer-jar` is already parameterised for any product. This is the #1 thing any LLM or developer reading this project should understand upfront.

**Currently missing from:** README hero section, CLAUDE.md framing, registry/README.md, MCP tool descriptions.

---

## Priority List

### 0 — Document hot-swap architecture
- Add product-agnostic framing to README (above the pipeline diagram)
- Add to CLAUDE.md top-level (before pipeline commands)
- Update `registry/README.md` to say "per-customer, regenerate for your product"
- MCP tool docstrings: every tool taking `registry` param should explain it as the hot-swap point

---

### 1 — Additive plugin: structural parser + gap identifier
**Plan:** [Leg4-additive-plugin-update](./Leg4-additive-plugin-update/00-plan.md) ✅ Complete  
**Remaining gaps:**
- Naive regex on `renderingData.put(...)` — no AST validation
- Conditional blocks always appended (no dedup by content)
- No pre-flight validation that insertion anchors exist before writing
- No dry-run mode (`--dry-run` prints diff, no write)
- Gap report not available as standalone output

---

### 2 — MCP tool parity
**Missing tools vs CLI:**
- `convert_docx_to_html` — Leg 0 (doc → HTML + fields + conditional form)
- `generate_snapshot_plugin` — Leg 4 (.suggested.yaml → Java plugin)
- `list_available_paths` — path catalog (registry → grouped Markdown)
- `parse_conditional_form` — post-customer-return step

---

### 3 — Test coverage gaps
- **Leg 0:** zero tests for doc ingestion
- **Leg 3:** no unit tests (only covered indirectly via integration)
- **Leg 4:** no tests for plugin generation, additive mode, or multi-form
- **agent.py orchestration:** no tests for `RUN_PIPELINE` parsing/dispatch
- **MCP tools:** no contract tests

---

### 4 — Pipeline documentation
- Data-flow diagram: Leg 0 → 1 → 2 → 3 → 4 with file types at each stage
- Registry schema reference (field meanings, how to update/regenerate)
- How to onboard a new customer (registry regen, config fingerprint, SDK deps)
- Additive plugin flow walkthrough
- Leg 2 confidence scoring explanation

---

### 5 — Path catalog enhancements
**Plan:** [path-catalog](./path-catalog/00-plan.md) — Status: Ready  
**Remaining:**
- Filterable output (`--section`, `--type`)
- Search mode (`--search premium`)
- MCP tool with `section` and `query` params
- "Used in template" mode — given `.final.vm`, show which paths are referenced vs available

---

### 6 — Leg 2 completeness check
- `mode=terse` has no test coverage
- No validation that every token in `.mapping.yaml` appears in `.suggested.yaml` (silent drops possible)
- Add completeness assertion: mapping tokens ⊆ suggested tokens

---

### 7 — Multi-product / registry freshness
**Plan:** [quote-paths-registry](./quote-paths-registry/00-plan.md) — Status: Ready  
- Registry is statically generated; no auto-regen when config changes
- `build_schema_index.py` not wired into any CI or pipeline trigger
- No guidance for multi-product setups (different registries per product in same run)

---

### 8 — Conditionals: template-side `#if` (Option B, deferred)
**Origin:** [10-conditional-field-tokens](./CompletedPlans/10-conditional-field-tokens/00-plan.md) §3 — Status: Deferred
- Plugin-side concatenation (Option A) shipped for fields inside conditional blocks
- Option B (plugin puts a boolean; Leg 3 wraps block content in `#if($data.condN)…#end`)
  would support per-exposure (`item.*`) and account fields inside conditionals naturally
- Revisit if those become a real customer need; it changes the conditional contract for
  every existing template/plugin and the additive-mode key semantics

---

## Active Plans (Ready / In Progress)

| Plan | Status |
|------|--------|
| [datafetcher-jar-probe-fix](./datafetcher-jar-probe-fix/00-plan.md) | Active |
| [Leg2-data-root-prefix-fix](./Leg2-data-root-prefix-fix/00-plan.md) | Ready |
| [Leg4-plugin-enrichment](./Leg4-plugin-enrichment/00-plan.md) | Not started |
| [nested-conditional-blocks](./nested-conditional-blocks/00-plan.md) | Ready |
| [path-catalog](./path-catalog/00-plan.md) | Ready |
| [quote-paths-registry](./quote-paths-registry/00-plan.md) | Ready |
| [strict-token-schema](./strict-token-schema/00-plan.md) | Ready |
