# AIG C11697DBG(quote) — M1 skeleton report (2026-07-16)

M1 goal: a `.final.vm` with the 8 resolved plain fields substituted to real accessors +
a compiled SnapshotPlugin. Conditional layer deliberately left inert (0/89 known-blocked;
`--parse-variants-csv` NOT retried — documented M1 exception to the pre-flight rule).

All artifacts: `workspace-prod/output/C11697DBG(quote)/`.
Snapshots taken first: `workspace-prod/action-needed.bak-m1-2026-07-16/` and
`workspace-prod/output/C11697DBG(quote).bak-m1-2026-07-16/`.

## What ran

1. **Leg -1 apply** — `legminus1_resolve_paths --parse-path-review-csv` (script directly,
   explicit `--output-dir`; the agent wrapper assumes `workspace/`). Folded the filled CSV
   onto the canonical md → `path-map.yaml` (8 chosen accessors; `classNumbers` and
   `accidentalDeathMaximumAmount` = `---` unresolvable-at-doc-scope markers).
2. **Leg 0 re-ingest with `--path-map`** — required, not optional: the existing mapping was
   built without the path-map, so the nested accessors couldn't reach Leg 2 from it.
   - `soffice` conversion **fails on this docx** (`huge text node` parser error in the
     xhtml export — embedded-font base64 blob); used `--converter legacy` (styling
     discarded, same as the original prod run).
   - The filled `variants.csv` was **not** clobbered — Leg 0's edit-guard kept it
     ("already exists with edits — keeping it").
3. **Leg 2** with the AIG registry + jars. Two gaps surfaced, one fixed:
   - Built the missing AIG schema index → `workspace-prod/registry/sdk-schema-index.yaml`
     (`build_schema_index --product BlanketSpecialRisk`, 522 types / 4310 fields). It is
     auto-discovered as a registry sibling from now on.
   - Even so, Leg 2's matcher cannot resolve nested-CDT dotted accessors
     (`quote.data.policyHolder.name`) or `quote.<system>` (AIG registry has no
     `quote_system` rows; schema-index tokens are single-level `EntityType.field`).
     Used the sanctioned manual-mapping fallback: set explicit `data_source` on the 8
     variables in the mapping (Leg 2/3 preserve explicit paths by design).
4. **Leg 3** — after re-seeding `<stem>.vm` from the fresh `annotated.html` (the agent
   flow does this copy; running the script directly had picked up a stale `.vm`).
5. **Leg 4** with `--customer-jar`/`--datamodel-jar` and `--compile-check`.

## Results

**Field resolution: 8/8.** Leg 3 report status COMPLETE; all 8 substituted, javap-verified
by Leg 4:

| Field | Template path | javap |
|---|---|---|
| policyHolder | `$data.quote.data.policyHolder.name` | ok (String) |
| address1/city/state/postalCode | `$data.quote.data.policyHolder.policyHolderAddress.<f>` | ok (String) |
| policyNumber | `$data.quote.reservedPolicyNumber` | ok (Optional\<String\>) |
| effective/termination date | `$data.quote.startTime` / `$data.quote.endTime` | ok (Optional\<Instant\>) |

The 2 known-unresolvable fields (`classNumbers`, `accidentalDeathMaximumAmount` — per-Risk
scope) appear as literal `{---}` text in the final.vm: render-safe (plain text), visibly a
gap for a human reviewer.

**Grep gate: PASS.** 0 bare `$data.data.`, 0 bare `$data.<systemField>`; the only
`$data.<key>` first segment for resolved fields is `quote` (8 refs).

**Compile check: PASS.** `BlanketSpecialRiskDocumentDataSnapshotPluginImpl.java` —
`resolved=8 unresolved=0 compile=PASS`.

## Render-readiness verdict: NOT render-ready as-is

Inventory of the final.vm:
- `$TBD_*` tokens: **0**
- `$doc.*` refs: **0**
- `#if` / `#foreach`: **0**
- **50 distinct `${data.<token>}` conditional refs** (one occurrence each — the 50
  document-level `[[$token]]` markers; the other 39 of the 89 blocks are nested-only and
  never appear in the template).

The generated plugin puts only `quote` / `pricing` / `productType` — none of the 50
conditional keys. Socotra renders in Velocity **strict mode**, where an undefined
reference is a hard error (quiet `$!{}` notation does **not** suppress
undefined-reference errors in strict mode). The first `${data.accidentalDismembermentBenefit}`
etc. would abort the render. So the skeleton renders only if the 50 keys exist in
renderingData.

**Smallest viable mitigations (not implemented):**
1. **Plugin stub-keys (smallest)** — have the plugin `.put()` each of the 50 template
   conditional keys with `""` (a static `List.of(...)` + one loop, ~5 lines hand-added to
   the generated Java). Template untouched; conditional slots render blank. Fully
   render-ready skeleton.
2. **Template `#if` wraps** — wrap each `${data.<key>}` in `#if($data.<key>)…#end`
   (strict mode permits undefined refs inside `#if` tests). 50 template edits; no plugin
   change; slots vanish instead of blank.
3. **Real fix (M2)** — unblock the variants layer (Blockers A/B/C) so
   `--parse-variants-csv` produces the conditional registry and Leg 4 wires genuine
   conditional strings. This is the actual roadmap item; 1–2 are throwaway bridges.

Secondary cosmetic gap: the three Optional-returning accessors
(`reservedPolicyNumber`, `startTime`, `endTime`) render as `Optional[...]` strings —
mitigate later by formatting them in the plugin (dates → MM/dd/yyyy per the earlier
session notes), not in M1.

## New/changed durable artifacts

- `workspace-prod/registry/sdk-schema-index.yaml` — NEW, AIG schema index (M2 will need it)
- `workspace-prod/output/C11697DBG(quote)/` — refreshed mapping (8 explicit
  `data_source` entries marked `manual`), `*.final.vm`, `*.leg3-report.md`,
  `BlanketSpecialRiskDocumentDataSnapshotPluginImpl.java`, `*.plugin-report.md`,
  `*.path-map.yaml` / `*.path-changes.md` / `*.resolved.docx`
- Pipeline gap observed (not fixed): Leg 0 `--path-map` pre-fill leaves nested-CDT and
  system dotted accessors `UNRESOLVED:`, and Leg 2 can't recover them without manual
  `data_source` — the "Leg -1 dotted paths" gap from the render-preview session, now
  reproduced on a real customer doc.

## Render-ready hardening (M1) — 2026-07-16

Mitigation option 1 (plugin stub-keys) + the Optional-formatting cosmetic fix, hand-applied
to the generated `BlanketSpecialRiskDocumentDataSnapshotPluginImpl.java` (backup:
`…PluginImpl.java.bak`). Template untouched. **Do not re-run Leg 4 generation on this form
— it would regenerate the file and drop these edits.**

- **Stubbed: 50** document-level conditional keys → `renderingData.put(key, "")` via one
  `String[]` + loop in the quote overload, marked
  `// M1 stub: conditional layer pending (Blockers A/B/C) — remove when variants registry lands`.
  Names cross-checked: the 50 distinct `${data.<token>}` refs in the final.vm are exactly a
  subset of the `conditional-blocks.yaml` keys (0 mismatches).
- **Optional formatting:** the `"quote"` renderingData entry is now a wrapper map
  (`quoteView`) instead of the raw record — `data` → `quote.data()` (so
  `$data.quote.data.policyHolder.*` chains still resolve), `reservedPolicyNumber` →
  `.orElse("")`, `startTime`/`endTime` → `Optional<Instant>` formatted `MM/dd/yyyy` (UTC)
  via `SimpleDateFormat`, empty when absent. No more `Optional[...]` in the render.
- **Compile:** PASS — `javac -encoding UTF-8` against
  `workspace-prod/reference/build/{customer-config.jar, core-datamodel-v1.7.71.jar, slf4j-api-1.7.36.jar}`
  (same classpath/flags as Leg 4 `--compile-check`).
- **Unbacked-ref check:** every `$data.<root>` the final.vm references (51 root keys =
  `quote` + 50 stubs) is now `.put()` by the plugin — **0 unbacked refs**.

Verdict update: the M1 skeleton is now render-ready under strict mode. The stubs render
conditional slots as blank; M2 (variants registry → real conditional strings) replaces them.
