# Audit — legs -1 → 2: YAGNI cuts, partitioning candidates, gaps

**Status:** findings recorded — decisions pending (2026-07-02)
**Owner:** Josh
**Effort:** mixed — see per-item
**Context:** full audit of the early pipeline (Leg -1, 0, 1, 2 + orchestration),
hunting over-engineering, leg-partition candidates, and glaring gaps. Read this
**before re-auditing** — it records what was checked, what was cut-listed, and one
false positive that must not be re-reported.

**Standing constraint (do not violate):** templates must be generatable **without a
registry** (customer hand-maps every accessor). The registry is an optional
enrichment, never a required authority. Any fix below that touches accessor handling
must be warn-only and skipped when no registry is loaded. Already encoded:
`legminus1_resolve_paths.py:781-789` (registry-less no-suggest), Leg 0's optional
`--registry`. Leg 2 is the only inherently registry-required leg.

Related notes (pre-existing, complementary — this audit does NOT supersede them):
- [decompose-clonker-legs.md](decompose-clonker-legs.md) — Leg 4 merge / Leg 0
  conditional-I/O / Leg 2 match-vs-verdict seams
- [dedup-shared-registry-and-markup.md](dedup-shared-registry-and-markup.md) —
  registry-index triplication (leg2 :252, registry_match :56, condition_dsl :302)
- [retire-legacy-conditional-form.md](retire-legacy-conditional-form.md) — same
  finding as cut #3 below; that note has the full location table

---

## Ranked cuts (biggest first)

1. **`yagni:` Leg 1 (`convert.py`) is a second template dialect with zero current
   users.** ~1,150 of 1,358 lines serve `{{var}}`/`[loop]`/`[prose]` HTML input; all
   inbox HTMLs are gone, every real flow is docx→Leg 0, and Leg 0 shares **no code**
   with it — loops/conditionals/fields/mapping-writer implemented twice in different
   syntaxes. **Decision pending: kill** (breaks 2 MCP tools in `mcp_server.py:57-147`
   + `test_convert.py`, 631 lines) **or fold** HTML input into Leg 0's dialect
   (`{field}` / `[Name]` / `[[cond]]`). Two template languages is the deepest debt in
   the repo. If kept as-is, the dedup note's shared-`markup.py` is the fallback.
2. **`delete:` Leg -1's `.path-review.md` canonical-copy ceremony, ~150 lines.**
   Writes an .md "system record", folds the customer CSV back onto it with a regex
   patcher, then re-parses the .md it just patched (`write_path_review` :167,
   `_patch_review_finals` :302, `parse_path_review` :496, plus the second
   `--parse-path-review` operator entry). Nothing reads the .md but this round-trip —
   `path-map.yaml` is the machine record. Replacement: CSV → path-map directly.
3. **`delete:` legacy `--parse-conditional-form`, ~141 lines.** No producer since
   variants-only shipped 2026-06-17. Tracked in
   [retire-legacy-conditional-form.md](retire-legacy-conditional-form.md) — do that.
4. **`delete:` `.resolved.docx` writer, ~75 lines** (`_rewrite_docx` +
   `write_resolved_doc`, legminus1 :534-595). Produces an artifact no flow consumes
   (verified: `agent_tools` only *lists* it); it's a documented second way to feed
   Leg 0 that nothing uses — the path-map is the real channel.
5. **`shrink:` RUN_PIPELINE preflight box + PROCEED/CANCEL, ~150 lines**
   (`agent.py:144-153`, `agent_tools.build_preflight` :302-372). Every scripted
   caller passes `--yes`; the interactive surfaces (demo_ui, MCP) never route through
   it. Confirmation theater.
6. **`delete:` `.path-changes.md` provenance audit, ~45 lines** (legminus1 :354-383 +
   decided-by tracking in `run_apply`). Nothing reads it. *Caveat:* if it's a
   customer-facing traceability deliverable (AIG-style engagements), keep — Josh's
   call.
7. **`yagni:` condition-DSL operators nobody uses** — `!=`, `>`, `>=`, `<`, `<=`,
   `in`, `absent`: zero uses in any fixture/seed (only `present`, `==`, blank
   default). ~31 lines codegen (`condition_dsl.py:538-640`) + ~240 test lines. Tested
   and correct → mark `# ponytail: unused until 50-state forms`, don't delete.
8. **`yagni:` terminology matching** (15 lines, `leg2_fill_mapping.py:1407-1421` +
   match step 3 :435-447; works, 1 test, 0 production use) and **feature gate**
   (~50 lines, :850-874; exactly one `requires_feature` registry entry). Mark, keep.
9. **`shrink:` `demo_ui.py` at 2,003 lines** — ~9 color themes (incl. MySpace) are
   demo glitter roughly the size of Leg -1. Trim when it annoys.

**Rough line math:** items 2+3+4+6 ≈ 410 lines deletable now without the Leg 1
decision; ~1,600 if Leg 1 dies.

## Leg-partitioning candidates (beyond the decompose note's seams)

1. **Merge Leg -1 into Leg 0** — strongest candidate, not in the decompose note.
   Leg -1 imports Leg 0's `_FIELD_RE`/`_LOOP_MARKER_RE`/`convert_docx/pdf` then
   **re-implements loop-membership classification on flattened text** (~50 lines
   hand-synced to "Leg 0's loop-field rule"). Intake already runs them back-to-back,
   parsing the same doc twice. One `_parse_document()` pass emitting both fill files
   kills the duplicate parser, the drift risk, and the pass-2 ordering trap (Leg -1
   runs before variant text exists — the only reason pass 2 is a separate step).
   Leg -1's unique value is just `registry_match.py`, already its own module.
   Registry-optionality survives: Leg 0 already treats the registry as optional input.
2. **Give the renderingData splice one owner.** The pre-splice→entity-key rewrite
   lives in `agent_tools.render_root_velocity` AND `leg2_fill_mapping._reprefix` —
   the documented #1 trap, implemented twice. Extract one shared function.
3. **Leg 1: fold or kill** (cut #1) — the decision, not just a deletion.
4. **Make `agent_tools` the API.** The string DSL (`agent.py` parse_invocation +
   preflight + dispatch, ~350 lines) is bypassed by every serious consumer; the
   snapshot/restore-around-reingest and parse-variants-preflight patterns are
   re-implemented 2-3× across demo_ui/run_demo/test-runner because there's no
   callable "finalize" primitive. `run_demo.finalize` is the closest — make it *the*
   one.

## Glaring gaps (ranked by blast radius)

1. **`run_apply` never validates customer `final` accessors**
   (legminus1 :640-664). Typos flow into path-map → baked into placeholders →
   surface two legs later as confusing Leg 2 verdicts. Fix: check finals against the
   registry candidate index at apply — **warn-only, skipped when no registry**
   (standing constraint above; registries also legitimately lack keys, e.g. charge
   accessors).
2. **No fingerprint on the source docx between intake and finalize.** Word resaved
   the inbox doc mid-flow on 2026-07-01 and broke a live demo. `path-map.yaml`
   already records `input_path`; add a sha256 beside it, compare at ingest.
3. **Leg -1 pass 2 (`--variants-csv`) unreachable from every general front door**
   (RUN_PIPELINE, intake, demo_ui, run_demo) — only the raw script flag and
   `tools/zencover_demo.py` wire it. First-pass path-review therefore always lacks
   variant-text leaves. Wire into finalize/resolve between variant fill and
   re-ingest — or dissolve via partition #1.
4. **path-review.csv shows pre-splice accessors** (`$data.data.<f>` forms that never
   render as written) — customers confirm paths that get silently rewritten
   downstream. Show/annotate the post-splice form in the `suggested` column
   (registry-path only; manual path untouched).
5. **`sdk-schema-index.yaml` has no staleness gate** — the registry gets a
   config-sha gate (`suggester_state.py`) but the schema index has no fingerprint
   against the JAR it was built from. Same failure class as the registry-generator
   staleness incident.

## False positive — do NOT re-report

An Explore-agent sweep flagged `load_schema_index` (`leg2_fill_mapping.py:480`) +
`build_schema_index.py` (91 lines) as dead code. **Verified wrong:** `schema_index`
flows main → `annotate_mapping` → `derive_variable_candidate` → `match_token`, which
does the strict `Entity.field` lookup at `leg2_fill_mapping.py:472`, and
`registry/sdk-schema-index.yaml` exists on disk. `build_schema_index.py` is its
offline generator. Load-bearing — the only real finding there is gap #5 (staleness).

## Verified NOT over-engineered (don't re-litigate)

- `workspace.py` (84 ln) — single source of truth for the inbox/action-needed/output
  split; every caller routes through it.
- `suggester_state.py` (125 ln) — registry↔config fingerprint gate; single caller by
  design, safety-critical.
- `registry_match.py` (271 ln) — imports leg2's helpers, doesn't duplicate them
  (but see the dedup note's index-triplication for the shared-index direction).
- `models.py` pydantic contracts (~527 ln) — 11+ validation sites across 3 artifact
  types; proportionate.
- `leg2_review_writer.py` (389 ln) — human-read artifact for the manual-review stage;
  correctly deleted as an intermediate on full-pipeline success.
