# Feature idea — collapse conditional text onto variants (drop the conditional form)

**Status:** idea — not started (2026-06-16)
**Owner:** Josh
**Context:** follow-up to `multi-variant-conditional-plan.md` and the
`feat/multi-variant-conditionals` branch. Surfaced while demoing
`ZenCoverDemoLetter` — see "Motivating bug" below.

## The idea

Today the customer fills **two** human files for conditional text:

- `<stem>.conditional-form.md` — **binary** blocks (`[[text]]`): one `Condition:`
  line each; the text either appears or it doesn't.
- `<stem>.variants.csv` — **N-way** blocks (`[[$token]]`): one row per
  `when`/`text`, plus a default row.

A binary block is just a **degenerate 2-way variant**: "show this text when
`<condition>`, otherwise show nothing." So in principle *every* conditional block
could be expressed as a variant, and the conditional form could go away entirely —
one mechanism (`variants.csv`), one parser path, one human-fill file for all
conditional text.

```
[[A cooling-off period applies.]]   with   Condition: quote.quoteNumber != null
```
becomes a one-real-row variant with an **empty default**:
```csv
placeholder,when,text
coolingOff,"quote.quoteNumber != null","A cooling-off period applies."
coolingOff,,""
```

## Why it's attractive

1. **One human touchpoint, not two.** The intake package drops from three fill
   files to two (`path-review.md` + `variants.csv`). Simpler customer story.
2. **One code path.** Binary/template/variant are three branches through
   `parse_conditional_form` + the registry schema + Leg 3 emit + Leg 4 wiring.
   Collapsing to variants removes the binary/variant *duality* — which is exactly
   the seam the motivating bug lived in.
3. **More expressive by default.** A customer who wrote a binary block and later
   wants a second wording just adds a row — no migration from one file format to
   another.

## Motivating bug (why this is on my mind)

`parse_conditional_form`'s binary-block regex (`leg0_ingest.py:~952`) used a
DOTALL non-greedy body capture that scanned **past** a variant block (which has no
`Condition:` line) and stole the *following* binary block's condition — producing
two `id: 1` entries and dropping a block. Fixed 2026-06-16 by tempering the body
capture so it can't cross a `## Block` header or a `Variant placeholder:` line.

The root irritation: the parser has to juggle two block kinds that share a
numbering space and a markdown layout. **A variants-only world deletes that whole
class of bug** — there's only one block kind to parse.

> Regression gap to close regardless of this idea: no fixture exercises a
> `$variant` block *immediately followed by* a binary block in one doc (the exact
> trigger). Add one to `tools/generate_test_fixtures.py` to lock in the fix.

## Sketch of the work (if pursued)

Rough, unvalidated — flesh out before committing.

1. **Leg 0 emit.** Stop writing `conditional-form.md`. For every `[[...]]` block
   (binary, template, *and* `[[$token]]`), emit a row group in `variants.csv`.
   Binary blocks get an auto-generated placeholder key (e.g. `cond1`) and a
   2-row stub: one `when` row to fill, one empty default.
   - Template blocks (`render: template`, loop-inside-conditional) need thought —
     their body isn't a single string, so they may *not* collapse cleanly. Likely
     stays a special case. **Open question.**
2. **CSV schema.** Already supports `when` (condition DSL) + `text` + default. A
   binary block is `text` = the literal, default `text` = `""`. Confirm an empty
   default round-trips through `condition_dsl.parse_variants_csv`.
3. **Registry.** Everything becomes a `variant: true` entry. Drop the binary
   branch from the conditional-registry schema (or keep it as a compatibility
   read-path for old artifacts).
4. **Leg 3 emit.** Binary `#if($data.condN)...#end` becomes the same
   `${data.<placeholder>}` indirection variants already use — the plugin owns the
   text selection. Net simplification.
5. **Leg 4 wiring.** Variant wiring already builds an if/else-if chain and
   concatenates `{field}` accessors. Binary blocks fold into the same generator.
   - **UX asymmetry to fix first (not a bug, but a trap):** variant-text `{field}`
     tokens must be written as **full accessors** (`{policy.data.discountAmount}`)
     because the variants.csv text never passes through Leg -1 resolution — the
     registry lookup is keyed by full accessor (`_registry_accessor_to_velocity`).
     A **bare leaf** (`{discountAmount}`) silently degrades to a `// TODO` + WARN.
     Meanwhile the *document body* accepts bare leaves (Leg -1 resolves them). If
     binary blocks collapse onto variants, this asymmetry would start biting text
     that works fine today — so resolve it first: either run variant text through
     the same leaf→accessor resolver, or validate it at parse time.
6. **Backward compatibility.** Old `conditional-form.md` files still exist in
   customer hands. Either keep `--parse-conditional-form` as a legacy reader, or
   ship a one-shot `conditional-form.md → variants.csv` converter.

## Risks / open questions

- **Template blocks** (loop-inside-conditional, `render: template`) probably don't
  reduce to a single `text` string — may need to stay separate, which undercuts
  the "one mechanism" win. Resolve this first; it decides whether the idea is
  "drop the form" or only "drop binary blocks from the form."
- **Worse ergonomics for the simple case?** A plain "show this sentence or not"
  is one `Condition:` line today vs. a 2-row CSV with an empty default. Need a
  clean stub so the simple case doesn't feel heavier. Maybe Leg 0 pre-writes the
  empty default row so the customer only fills `when`.
- **The variant-text full-accessor asymmetry** (item 5) is a hard prerequisite —
  customers writing bare leaves in CSV text is the obvious foot-gun.
- **Docs/triggers churn:** CLAUDE.md, demo-story.md, the UI's four-stage flow, and
  the test harness all reference the conditional form. Non-trivial sweep.

## Decision

**Updated 2026-06-17 — actionable plan written:** see
[variants-only-conditional-text-plan.md](variants-only-conditional-text-plan.md).
Two open questions are now decided: (A) loop-in-conditional IS supported — a
`render: template` block becomes a `when`-only `variants.csv` row (text stays in the
`.vm`, loop leaves already resolved by Leg -1); the only unsupported edge is an N-way
block with per-variant loops; (B) bare leaves in variant text get the same
human-in-the-loop resolution as doc leaves
(reuse Leg -1's `path-review` machinery, re-run after edit). The Decision B resolver has
standalone value and is the suggested first landing step.

_(Original park note:)_ Parked until the `feat/multi-variant-conditionals` work lands and
the variant-text wiring WARN is resolved — those answer whether the collapse is
clean or leaves template blocks as a stubborn special case.
