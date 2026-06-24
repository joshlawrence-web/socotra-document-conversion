# Improvement note — Leg 4 additive merge keeps stale occurrence guards

**Status:** idea — not started (2026-06-19)
**Owner:** Josh
**Effort:** small–medium (refresh the guard block on additive merge; behavior-preserving for non-guard content)
**Context:** found while tracing a live-render 422 on `ZenCoverDemoLetter(quote)`. The
snapshot plugin threw `IllegalStateException: Document data missing for required
fields: quote.data.discountType (required)` because the quote had no `discountType`.
Fixing it (mark the field optional) surfaced two regen wrinkles below — both are
footguns for anyone changing a field's occurrence on an already-generated form.

## Wrinkle 1 — occurrence change needs a re-ingest, not just a docx edit + Generate

Occurrence is parsed from the `{symbol}name` token at **Leg 0 ingest** (`leg0_ingest.py`
`_FIELD_RE` / `OCCURRENCE_SYMBOLS`) and frozen into `<stem>.mapping.yaml` as
`occurrence: <value>`. `do_generate` (UI Stage 4 / `demo_ui.py:603`) starts at **Leg 2**
and reads the existing `mapping.yaml` — it never re-reads the docx. So editing the
source `{discountType}` → `{$discountType}` and hitting **Generate** does nothing to
occurrence.

Correct order: **Stage 3 Resolve & ingest** (`do_resolve_ingest`, re-runs Leg 0 from the
docx, snapshots/restores the filled path-review + variants CSVs so answers survive) →
**Stage 4 Generate**. Verified: after re-ingest, `mapping.yaml` flipped to
`occurrence: optional`.

> Symbols: `{x}` required · `{$x}` optional (single) · `{+x}` one-or-more (collection) ·
> `{*x}` zero-or-more (collection). For a non-mandatory *scalar*, use `{$x}` — not `{*x}`
> (which means a repeating element). Only `required` and `one_or_more` emit a guard
> (`leg4_generate_plugin.py:589`).

## Wrinkle 2 — additive Leg 4 does NOT refresh the occurrence-guard block (the real bug)

`safe_leg4` / `run_leg4` run **additively** when a `*DocumentDataSnapshotPluginImpl.java`
already exists: the additive helpers (`leg4_generate_plugin.py:826+`) only **add missing
`renderingData.put` keys**. They never rewrite the occurrence-guard block — that block is
emitted only on a *fresh* (no-existing-file) generation. So after re-ingest flipped
`discountType` to optional, the regenerated plugin **still carried the old `required`
guard** and would still throw. The Leg 4 report says "PASS / keys already present", giving
a false sense the regen was complete.

Net footgun: **any occurrence change (required↔optional, or +/- a guarded field) on an
already-generated plugin is silently ignored.** Same applies to a field that *becomes*
required — no guard is added.

### Workaround used this time

Surgically deleted the stale guard block from the `.java` by hand (it was the only
required field, so a fresh gen now emits no block at all → result is intent-identical to
a fresh gen, without clobbering hand-edits). Compiles clean against `customer-config.jar`.
A blunter alternative — delete the `.java` and let Leg 4 regen fresh — works only if the
plugin has no hand-edits worth keeping.

### Proposed fix

On additive merge, treat the occurrence-guard block like a managed region: re-derive it
from the current `mapping.yaml` occurrences and **replace** the existing block (delimited
by the `// Occurrence guards —` header + `_GUARD_MARKER` lines) instead of leaving it
untouched. Keep `renderingData.put` keys additive as today. Add regression coverage:
required→optional drops the guard; optional→required adds it; non-guard keys/hand-edits
untouched.

## Touch points

| Location | What |
|---|---|
| `velocity_converter/leg0_ingest.py` (`_FIELD_RE`, `OCCURRENCE_SYMBOLS`) | occurrence parsed from token symbol → frozen in mapping.yaml |
| `velocity_converter/leg4_generate_plugin.py:543` (`_GUARD_MARKER`), `:570` (`render_occurrence_guards`) | guard block generator (fresh-gen only) |
| `velocity_converter/leg4_generate_plugin.py:826+` | additive merge helpers — add keys only, skip guards |
| `tools/demo_ui.py:603` (`do_generate`), `:268` (`do_resolve_ingest`) | Generate starts at Leg 2 (no docx re-read); Resolve&ingest re-runs Leg 0 |

## Wrinkle 3 — Leg 3 `$TBD_` regex swallowed a sentence-ending period (FIXED 2026-06-19)

After the re-ingest + regen, the live render then failed with Velocity error
**216041 "Variable $TBD_quote has not been set"** — a `$TBD_` placeholder leaked
unsubstituted into `final.vm` (lines 5–6: `$TBD_quote.data.discountType`,
`$TBD_account.data.email`). The Leg 3 report cheerfully said "all 5 tokens resolved"
because the report is built from the mapping, not from the actual replacements.

Root cause: `_TBD_TOKEN_RE = \$(?:\w+\.)?TBD_[\w.]+` (`leg3_substitute.py:313`). The
`[\w.]+` tail is greedy and `.` is in the class, so a placeholder immediately followed
by a sentence period captured the period too: `"...is $TBD_quote.data.discountType."`
→ token `$TBD_quote.data.discountType.` (trailing dot) → not in the substitution map →
left as `$TBD_`. `firstName`/`lastName` escaped only because they were followed by `,`
and a space, not `.`.

**Fix:** anchor the path so it never ends in a dot —
`\$(?:\w+\.)?TBD_\w+(?:\.\w+)*`. A bare trailing dot is now treated as sentence
punctuation (the Leg 0 cond-field finder already did this — `test_cond_field_tokens.py
::test_sentence_punctuation_not_swallowed` — but Leg 3's `$TBD_` regex was never tested
for it). Regression added: `tests/regression/test_leg3_substitute.py` (7 cases — trailing
period, comma/space/EOL, bare token, unresolved-preserved, end-to-end). Full suite 473
green.

> Follow-on idea (not done): the Leg 3 report says "resolved" from the mapping, not from
> the post-substitution text — so a leaked `$TBD_` passes the report silently. Consider
> re-scanning the written `final.vm` for residual `$TBD_` and downgrading the report
> status / failing the step when any remain.

## Wrinkle 4 — optional occurrence had no template-side null-safety (FIXED 2026-06-19)

With the plugin guard gone (Wrinkle 1) and the `$TBD_` leak fixed (Wrinkle 3), the render
then failed with **216041 "Reference $data.quote.data.discountType evaluated to null"**.
Socotra's renderer is **strict on null references**, and the demo quote has no
`discountType`. Making the field `optional` only removed the *plugin* guard — the template
still referenced it **bare** (`$data.quote.data.discountType`), so an absent value moved
the failure from the snapshot plugin to the renderer. Occurrence was only half-wired:
`required` → plugin guard + bare ref, but `optional` → no guard + bare ref → renderer dies.

Key structural fact: the snapshot plugin does `renderingData.put("quote", quote)` — it
hands the renderer the **live object** and the template walks `$data.quote.data.discountType`.
So a Java `null -> ""` coalesce can't help (the plugin can't make `quote.data().discountType()`
return ""); that would require rewriting optional fields to flat plugin-populated keys —
a cross-leg refactor (Leg 2 ref style + Leg 3 ref + Leg 4 put). The template-side guard is
the model-consistent fix.

**Fix:** Leg 3 now emits a Velocity **quiet reference** for `optional` fields —
`$data.quote.data.discountType` → `$!{data.quote.data.discountType}` — which renders empty
instead of erroring when null. Required fields stay bare/loud (an absent required value
*should* fail). This is the template-side mirror of the plugin guard, keyed on the same
`occurrence` in `mapping.yaml`. Implementation: `_to_quiet_ref()` + an occurrence branch in
`build_substitution_map` (`leg3_substitute.py`). Verified end-to-end: live render of quote
`01KV33…` now returns HTTP 200 (was 216041). Tests: `test_leg3_substitute.py
::TestOptionalQuietRef` (3 cases). Full suite 476 green.

> `$!` confirmed to suppress Socotra's strict-null error by live render (not just docs).
> Collections (`zero_or_more`) are intentionally NOT wrapped — they're driven by #foreach,
> which handles an empty list fine. Only optional *scalars* get the quiet ref.
> Follow-on (not done): a `#if`-line guard would *omit* the whole sentence when absent
> (nicer than rendering "Your discount type on file is ."), but needs line/region boundary
> logic in `process_vm`. Quiet ref is the minimal generic baseline.

## How to trace the original symptom again

Live render 422 (`errorCode 100020`, `FAILED_PRECONDITION`) hides the real cause behind a
gRPC `InvocationTargetException`. Pull the plugin log by requestId:

1. `GET {API}/plugin/{tenant}/logs/list?requestId=<id>&extended=true` → log `locator` + `pluginType`.
2. `GET {API}/plugin/{tenant}/logs/{locator}` → streamed stack trace; read the `Caused by:` line.

Auth: existing `AI_DOCUMENTS_PAT` (security group `logs`, perms read/list). Idea:
surface this lookup in `demo_ui.py` so a 422 shows the `Caused by` line instead of the
opaque gRPC message — see [render-preview-todo](render-preview-todo.md).
