# Leg 2 — Root-aware confidence — history log

Append-only. **Newest session first.** Link from [00-plan.md](./00-plan.md).

---

## 2026-06-03 — Planning session (user + agent)

### Context

A Leg 4 pilot exposed that Leg 2 rates confidence from name-match against the
config-only registry and never consults the compiled SDK. `$data.policyNumber` was
rated `high` even though `ItemCareSegment` (the `renderingData` root Leg 4 emits for
policy documents) has no `policyNumber()` — the field lives on the sibling
`com.socotra.coremodel.Policy`. Full evidence in [problem.md](./problem.md).

### Investigation summary

- `scripts/leg2_fill_mapping.py` → `_confidence_from_step` grades `exact/ci/terminology`
  → `high` with **no JAR check**. Registry (`registry/path-registry.yaml`) is
  config-derived (`extract_paths.py`), single notional `$data` root.
- `scripts/leg4_generate_plugin.py` already has SDK introspection (`_javap`,
  `_zero_arg_methods`, `_unwrap_type`, `validate_path`) and already warns on the
  `policyNumber` gap — but only in its report, downstream.
- `docs/SCHEMA.md`: `.suggested.yaml` is currently `1.1`; every prior change was an
  additive MINOR. A per-root verdict change is a shape change.

### Open questions (problem.md §7) → user decisions

| Q | Topic | User decision |
|---|-------|---------------|
| 1 | Where SDK truth lives | **JARs are the authority.** Leg 2 introspects them to determine available paths per document root (quote/segment/invoice). Registry = name→candidate only. (→ D1, D7) |
| 2 | How a doc declares root(s) | **Filename brackets** `<stem>(<root>).html` — removes ambiguity, no inference. (→ D2) |
| 4 | Verdict schema | **MAJOR bump.** Per-root verdicts now, to give a future "analyse-plugin-and-suggest-updates" process full context. (→ D4) |
| 5 | Invoice scope | **Out** of the first cut. (→ D5) |
| Bonus | Loop-close with Leg 4 | Focus on registry + Leg 2; **describe** the downstream-leg changes adequately for later harmonisation rather than building them. (→ D6, 00-plan §14) |
| Follow-up | Delta mode | **Out of the first cut** — re-merge into a base `.suggested.yaml` is for a more mature pipeline; block `--mode delta` cleanly on 2.0 for now. (→ D10) |

Agent's recommendation on Q1/Q2 (validation-layer + hybrid inference) and Q4 (MINOR)
were **overridden** by the user in favour of JARs-as-authority, filename-declared roots,
and a MAJOR bump.

### Outputs from this session

- [00-plan.md](./00-plan.md) — decisions D1-D9, the `.suggested.yaml` **2.0** schema
  (`rendering_roots`, per-variable `candidate` + per-root `verdicts`, `sdk_status` enum),
  JAR-introspection plan via a shared `scripts/sdk_introspect.py`, filename convention,
  task list (Phases 0-3), definition of done, conformance impact, and the §14
  downstream-harmonisation spec.
- [README.md](./README.md) — plan index.
- This history file.

### Next agent actions

1. Open [README.md](./README.md) → [problem.md](./problem.md) → [00-plan.md](./00-plan.md) START HERE.
2. Implement **Phase 1** (00-plan §9): shared `sdk_introspect.py`, per-root verdicts,
   `.suggested.yaml` 2.0, filename root parsing.
3. Meet the **§12 definition of done** on `Simple-form(segment).html`, and re-run the
   Leg 4 §12 check to prove the shared-module refactor caused no regression.
4. Append a handoff per 00-plan §16.

### Open items / risks

- **Conformance goldens break** on the MAJOR bump (00-plan §13) — budget time to
  regenerate fixtures and update runner assertions.
- **Delta mode deferred (D10):** `--mode delta` is blocked cleanly on 2.0 (P1.6); the
  per-root diff port is a later phase (P3.4). Confirm no fixture/regression relies on a
  delta run.
- **Downstream MAJOR-halt:** Leg 3 / Leg 4 must halt on `2.0` until §14 lands; ensure
  the upgrade message is wired so it is not a silent break.

---

## 2026-06-03 — Implementation session (Phases 1 + 2)

### Summary

Implemented the root-aware, SDK-grounded Leg 2 (`.suggested.yaml` **2.0**). All
of **Phase 1** (P1.1–P1.7) and most of **Phase 2** (P2.1–P2.4) are done. The
canonical bug is fixed and proven on the pilot.

- **P1.1/P1.2** — New shared `scripts/sdk_introspect.py`: moved Leg 4's
  `_javap` / `_zero_arg_methods` / `_unwrap_type` / `validate_path` /
  `_default_datamodel_jar` / `_class_exists` here (Leg 4 imports them back,
  byte-identical report — re-ran Leg 4 `--compile-check` = PASS, no regression).
  Added `roots_for_product()`, `sibling_probe()`, `resolve_element_type()`, and a
  Leg-2 `classify_path()` returning the §6.3 `sdk_status` enum. `classify_path`
  resolves methods **case-insensitively** to mirror Velocity property access
  (`$item.Accessories` → `accessories()`), so valid coverage paths aren't
  falsely demoted; Leg 4's strict `validate_path` is untouched.
- **P1.3** — `parse_rendering_roots()` reads `<stem>(<root>).html` from the
  mapping's `source:`; missing/empty/unknown bracket → hard blocker review,
  exit 2 (no verdicts, no false `high`).
- **P1.4/P1.5** — `derive_variable_candidate()` (root-independent name-match) +
  `variable_verdict_for_root()` / loop verdict builders + `confidence_grade()`
  ("JAR can only demote"). `annotate_mapping()` now writes `rendering_roots` +
  per-entry `candidate` + per-root `verdicts`; `--customer-jar`/`--datamodel-jar`
  CLI flags (sensible `build/` defaults; fail loud if absent).
- **P1.6** — `--mode delta` exits non-zero with a clear message on 2.0 (D10).
- **P2.3** — `leg2_review_writer.py` rewritten per-root: Summary table per root,
  Blockers/Done/Assumptions as `(placeholder × root)` rows, `sdk_status` +
  `sibling_hint` surfaced.
- **P2.1** — `docs/SCHEMA.md`: `.suggested.yaml` + `.review.md` bumped to 2.0
  with full `rendering_roots` / `candidate` / `verdicts` / `sdk_status` tables
  and a MAJOR change-log row (incl. downstream-halt + conformance notes).
- **P2.2** — mapping-suggester `SKILL.md`: new "SDK-grounded confidence" section,
  JAR inputs, filename convention, JAR-only-demote, updated Step 0 command,
  delta-blocked notes.
- **P2.4** — `emit_telemetry.py` emits one record per `(placeholder × root)` with
  `root` + `sdk_status`; JSON schema extended (additive). All 6 pilot records
  validate against `conformance/schemas/suggester-log.schema.json`.

### Pilot result (§12 definition of done) — MET

`Simple-form(segment).html` → `Simple-form.suggested.yaml` (schema 2.0):

- `LOCATOR` → `$data.locator` · `confidence: high` · `sdk_status: verified` ✅
- `POLICY_NUMBER` → `confidence: low` · `sdk_status: sibling_only` ·
  `sibling_hint: Policy.policyNumber()` · `next-action: supply-from-plugin` ✅
  (the false-`high` bug is fixed)
- `POLICYHOLDER_NAME` (`$data.account.data.name`) → `not_found` (account isn't on
  the segment root nor a request sibling — true negative, confirmed via `javap`).
- Missing-bracket → blocker review + exit 2 ✅; multi-root `(quote,segment)`
  emits independent per-root verdicts ✅; `--mode delta` blocked ✅.
- Leg 4 `--compile-check` still PASS (no regression from the shared module) ✅.
- `socotra-config/` untouched ✅.

### Files touched

- `scripts/sdk_introspect.py` (new)
- `scripts/leg4_generate_plugin.py` (imports shared module; behaviour identical)
- `scripts/leg2_fill_mapping.py` (root-aware 2.0 rewrite)
- `scripts/leg2_review_writer.py` (per-root rendering)
- `.cursor/skills/mapping-suggester/scripts/emit_telemetry.py` (per-root records)
- `conformance/schemas/suggester-log.schema.json` (additive `root` + `sdk_status`)
- `docs/SCHEMA.md`, `.cursor/skills/mapping-suggester/SKILL.md`
- `samples/input/Simple-form(segment).html` (new pilot input),
  `samples/output/Simple-form/Simple-form.mapping.yaml` (source bracket + LOCATOR)

### Verification

```bash
python3 scripts/leg2_fill_mapping.py --mapping samples/output/Simple-form/Simple-form.mapping.yaml \
  --registry registry/path-registry.yaml --customer-jar build/customer-config.jar \
  --datamodel-jar build/core-datamodel-v1.7.61.jar \
  --out samples/output/Simple-form/Simple-form.suggested.yaml --mode terse
python3 scripts/leg4_generate_plugin.py --suggested samples/output/Simple-form/Simple-form.suggested.yaml --compile-check  # PASS
python3 conformance/run-conformance.py   # 12/12 PASS (registry; suggested/review unaffected)
```

### Open items / risks

- **P2.5 (conformance goldens) — BLOCKED, needs a decision.** §13 asks to
  regenerate fixture `suggested`/`review` goldens to 2.0 *from live runs*, but a
  live 2.0 run requires the **compiled product JARs**, which only exist for
  `ItemCare` (not the fixtures' synthetic Multi/Homeowner/Octopus/… products).
  This collides head-on with D1 ("JARs are the authority; fail loud if absent").
  Mitigating facts: the conformance runner only *auto-runs* `extract_paths.py`
  (registry) — those still pass 12/12 — and it only diffs `suggested`/`review`
  when an `actual/` exists, comparing the existing 1.x actuals against 1.x
  goldens (untouched by this work). So nothing is red. §13 item 3 (keep one
  sibling-demotion + one segment-resident-high case against real JARs) is already
  satisfied by the `Simple-form` pilot. **Options for the next agent / user:**
  (a) leave fixture goldens at 1.x with the documented note (recommended —
  consistent with D1); (b) add an ItemCare-JAR-backed conformance fixture and
  regenerate only that to 2.0; (c) build a registry-only fixture fallback mode
  for Leg 2 (large new scope, contradicts D1).
- **Downstream MAJOR-halt (§14, describe-only):** Leg 3 / Leg 4 are 1.x consumers
  and currently read a 2.0 file as having no high-confidence scalar fields
  (Leg 4 `--compile-check` still PASS but `high=0`). The explicit upgrade-path
  halt is §14 work — not built here. Until then the SCHEMA.md change-log records
  the expected behaviour.
- **`merge_delta()` is now dead code** (delta blocked at `main`); left in place,
  not wired.

---

## 2026-06-03 — P2.5 resolved: JAR-backed conformance fixture (option b)

### Summary

- User chose **option (b)** from the open item below: add one ItemCare-JAR-backed
  conformance fixture with real 2.0 `suggested`/`review` goldens and retire the
  orphaned 1.x ones. Done.
- New fixture **`conformance/fixtures/itemcare-jar/`** — backed by a copy of the
  repo's real `ItemCare` `socotra-config/`, so its registry paths line up with the
  compiled `build/*.jar`. Mapping declares `source: itemcare-jar(segment).html`
  (segment root). Covers the whole 2.0 verdict matrix in one artifact:
  - `$TBD_LOCATOR` → `verified` / **high** (strong match the JAR confirms on the root)
  - `$TBD_POLICY_NUMBER` → `sibling_only` / **low** (the original bug:
    `Policy.policyNumber()`, not on `ItemCareSegment`)
  - `$TBD_POLICYHOLDER_NAME` → `not_found` / **low** (fuzzy, JAR can't confirm)
  - `$TBD_EFFECTIVE_START_DATE` → `skipped` / **low** (no registry candidate)
  - loop `items` → `verified` / **high**; field `goods_category_code` → `verified`
    / **high** via element-type resolution `items()` → `Collection<ItemPolicy>` →
    `goodsCategoryCode()`.
- **Runner now drives Leg 2 for JAR-backed fixtures.** A `leg2.json` marker opts a
  fixture in; `run-conformance.py` runs `leg2_fill_mapping.py --mode terse` (fully
  deterministic — no AI narrative) against the frozen golden registry + `build/*.jar`,
  writes `actual/suggested.yaml` + `actual/review.md`, and diffs vs the 2.0 goldens.
  Determinism confirmed (two back-to-back runs identical).
- **Orphaned 1.x goldens retired.** Every synthetic fixture (no JAR ⇒ a 2.0 run
  would fail loud per D1) had its `golden/suggested.yaml` + `golden/review.md`
  (and any stale `actual/` copies) removed; they keep `golden/path-registry.yaml`.
- Volatile-field handling extended so the JAR-backed diff is stable: added
  `path_registry` to `IGNORED_SUGGESTED_PATHS`; added `Run id` / `Source mapping` /
  `Suggested output` / `Path registry` / `Inputs` / `Registry lineage` to the
  review-normaliser prefixes.

### Files touched

- `conformance/fixtures/itemcare-jar/` (new): `socotra-config/` (copy),
  `mapping.yaml`, `leg2.json`, `FIXTURE.md`, `golden/{path-registry,suggested}.yaml`,
  `golden/review.md`.
- `conformance/run-conformance.py`: `LEG2_SCRIPT`/`LEG2_MARKER` consts, `_run_leg2()`,
  call in `_evaluate_fixture`, extended `IGNORED_SUGGESTED_PATHS` +
  `NORMALISED_REVIEW_PREFIXES`, updated module docstring.
- Retired goldens under `conformance/fixtures/{all-quantifiers,cdt-flat,cdt-recursive,
  coverage-terms,custom-naming,itemcare-simple,jurisdictional,jurisdictional-exclusive,
  minimal,multi-product,nested-iterables,no-exposures}/`.
- `00-plan.md` §9 P2.5 checked off.

### Verification

- `python3 conformance/run-conformance.py` → **13/13 PASS** (`itemcare-jar`
  registry+suggested+review; the other 12 registry-only/skipped).
- `python3 conformance/run-conformance.py --only itemcare-jar` ×2 → identical PASS
  (determinism).
- No linter errors on `run-conformance.py`.

### Open items / risks

- The JAR-backed fixture is **machine-coupled to `build/`** — if the ItemCare JARs are
  regenerated with a changed `ItemCareSegment`/`ItemPolicy` surface, this fixture's
  goldens must be refreshed (that is the point — it is the SDK-drift tripwire).
- Downstream MAJOR-halt (§14) and dead `merge_delta()` remain as noted in the prior
  entry — unchanged by this work.

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
