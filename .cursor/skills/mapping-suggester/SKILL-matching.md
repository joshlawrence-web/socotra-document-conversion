# mapping-suggester — Matching rules (reference only, post-Stage-4)

> **NOTE (post-Stage-4):** `scripts/leg2_fill_mapping.py` implements these rules.
> This file is the authoritative spec — read it when debugging script behavior,
> not during normal AI-skill runs.

Read this file at **Step 3** of the old `SKILL.md` flow, or when debugging the script.
The AI skill no longer reads this file on every run.
a placeholder or loop.

**Prerequisites in `SKILL.md`:** "Recognised context signals", "Quantifier
semantics", and "Important constraints" (terminology + lessons). Consult
those sections when applying the rules below.

---

## Matching strategy

Every registry entry carries four fields Leg 2 must respect:

- `quantifier` / `cardinality` / `iterable` — see Quantifier semantics in `SKILL.md`.
- `requires_scope` — an ordered list (outermost first) of `#foreach` steps
  that must be active for the `velocity` path to be valid. Top-level system
  / account / policy-data / policy-charge entries have `requires_scope: []`.

The top-level `iterables:` section at the start of the registry is a flat
index of every foreach-able element in the product.

All suggested paths are dot-notation Velocity references copied **verbatim**
from the `velocity` / `velocity_amount` / `list_velocity` fields. Never
rewrite a path into method-call form (`$data.get("locator")`), and never
synthesise a path — if the registry doesn't list it, it doesn't exist.

Apply the rules below in priority order when filling each entry.

### Name-match precedence (Phase E — terminology layer)

Every name comparison Rule 1 and Rule 2 below perform against the
registry (`name`, `display_name`, derived plural, or a `display_name`
scan) follows this strict four-step precedence. Stop at the first step
that produces a hit; do not re-run later steps after a hit. The same
precedence is used for placeholder `name`, `context.nearest_label`, and
`context.nearest_heading` lookups.

1. **Exact match.** Case-sensitive equality against the registry's
   `name` / `display_name` / derived plural (e.g. loop `vehicles` →
   iterable `Vehicle` with derived plural `vehicles`).
2. **Case-insensitive match.** ASCII case-fold equality against the
   same three fields (e.g. loop `VEHICLES` → iterable `Vehicle`).
3. **Terminology synonym lookup** (skipped silently when no
   `terminology.yaml` was loaded in Step 0c). Check whether the
   placeholder's name (or label / heading) appears verbatim in any
   `synonyms.exposures[*]`, `synonyms.coverages[*]`, `synonyms.fields[*]`,
   or `display_name_aliases[*]` list. If so, the map key (e.g.
   `Octopus` for alias `octopuses` under `synonyms.exposures`) is the
   canonical name. Resolve it back to the registry exactly as for a
   step-1 hit. **Every match made at step 3 carries this reasoning
   line verbatim:**
   > matched via terminology.yaml synonym `<alias>` → canonical `<name>`
4. **Fuzzy / obvious-synonym fallback** — the "derived plural" +
   obvious-synonym logic already cited in Rule 1 (`drivers` ↔
   `Driver`). Retained as the last-resort matcher for single-word
   plurals that are grammatically obvious without a terminology entry.
   Never synthesise a match that a reviewer would need to justify —
   when step 4 is the only path to a hit and the match feels shaky,
   treat it as a miss (`confidence: low`, `next_action:
   supply-from-plugin`).

Steps 1–3 always run in order; step 4 runs only when the first three
produce no candidate. Terminology hits do not change `confidence` or
`next_action` semantics — a step-3 hit on an iterable's exposure
alias still earns `high` when Rules 2–6 are satisfied.

Hard constraints (see `SKILL.md` § Important constraints):

- The suggester MUST NOT merge multiple `terminology.yaml` files in a
  single run. Exactly one terminology source per run.
- Terminology canonical names MUST exist in the registry. An alias
  pointing at a missing canonical surfaces a `needs-skill-update:
  terminology canonical name <X> not found in registry` row in
  `.review.md` §7 and the alias is **not** used for matching.

### Rule 1 — Loop matches demand an iterable

When mapping a `loops` entry:

- Check `iterables:` at the top of the registry first.
- Match the loop `name` against each iterable's `name` / `display_name` /
  derived plural using the four-step "Name-match precedence" above
  (exact → case-insensitive → terminology synonym → fuzzy). Accept
  obvious synonyms (`drivers` ↔ `Driver`) only at step 4 when no
  terminology entry applies.
- Only set `data_source` if a match exists on an entry with
  `iterable: true`. Copy `list_velocity`, `iterator`, and `foreach`
  verbatim from the iterable entry. When the match came from step 3
  (terminology), append the "matched via terminology.yaml synonym
  `<alias>` → canonical `<name>`" line to `reasoning`.
- If no iterable matches, leave `data_source` blank, set `confidence: low`,
  note "no iterable element in the registry; data must come from a plugin
  or external snapshot", and pair with a next-action from the Ambiguity
  bubble-up vocabulary (typically `supply-from-plugin`).

Coverage loops (a `coverages` loop nested inside a `vehicles` loop) remain
a special case: match the loop name against a coverage on the parent
exposure and set `data_source` to that coverage's `velocity` path. The
coverage itself is not iterable — the "loop" is the template iterating the
fixed set of coverages on the exposure.

### Rule 2 — Scope inheritance is transitive

Two Leg 1 keys participate here, and they are **not** equivalent:

- **`context.loop`** — emitted on every loop field (a variable whose
  template occurrence is inside a detected `{{#name}}...{{/name}}` block
  or an auto-detected sibling-repetition loop). Value is the loop name as
  it appears in the template. **This key _satisfies_ a `requires_scope`
  step** when its value matches that step's iterable (same `name`,
  `display_name`, or derived plural). Loop fields are also nested under
  their loop's `fields:` list — the explicit `context.loop` key removes
  the need to walk YAML structure.
- **`context.loop_hint`** — emitted on top-level (non-loop) variables
  whose name strongly implies they belong inside an iterable (today:
  `vehicle_*` → `Vehicle`, `driver_*` → `Driver`). **This key does NOT
  satisfy a `requires_scope` step.** It only tells Leg 2 which iterable
  to look up when searching for a concrete candidate path to cite in
  `reasoning`. The resulting item stays `low` + `restructure-template`.

Algorithm when mapping a `variables` entry:

1. **No scope required.** If the candidate registry entry has
   `requires_scope: []`, no scope check is needed. Grade by Rule 3.

2. **Scope satisfied.** If the candidate has a non-empty `requires_scope`
   and the variable's `context.loop` (plus any outer `context.loop` chain
   recorded by nested-loop Leg 1 output) matches every step in
   `requires_scope` in order (outermost to innermost), accept the match.
   **All** scopes in `requires_scope` must be active simultaneously —
   partial satisfaction is not satisfaction. Grade by Rule 3.

3. **Scope violated, iterable known via `loop_hint`.** If the candidate
   has a non-empty `requires_scope`, `context.loop` does not satisfy it,
   and `context.loop_hint` matches the outermost step's iterable:
   - Leave `data_source` blank and set `confidence: low`.
   - In `reasoning`, cite the concrete candidate path and the scope
     violation. Example:

     > registry candidate `$vehicle.data.year` — template heading
     > implies Vehicle scope (loop_hint: Vehicle) but the variable is
     > not inside a matching `#foreach ($vehicle in $data.vehicles)`
     > block; scope violation.

   - Pair with `next_action: restructure-template` (wrap the block in
     the missing `#foreach` with an `#if` selector) unless the cleaner
     fix is `supply-from-plugin` (when the template intent is a
     flattened scalar, e.g. `$data.data.loss_vehicle_year`).

4. **Scope violated, no `loop_hint`.** If the candidate has a non-empty
   `requires_scope`, neither `context.loop` nor `context.loop_hint`
   signals the iterable, but the variable's `name` still matches a
   scoped registry entry by name alone: treat as scope violation,
   `confidence: low`, cite the candidate path in `reasoning` with the
   note "name match on scoped entry but no scope signal from Leg 1;
   template must be restructured or a plugin must supply a flattened
   scalar". Pair with `next_action: restructure-template` or
   `supply-from-plugin` as appropriate.

5. **No match.** If no registry entry matches by name and no
   `loop_hint` narrows the search, treat as unmatched: `confidence:
   low`, `next_action: supply-from-plugin` with a suggested shape
   (e.g. `$data.data.<field_name>` as a claim- or policy-level
   scalar).

**Never** set `data_source` to a scoped path based on `context.loop_hint`
alone. A `loop_hint` is a reasoning aid, not a scope proof.

### Rule 3 — Confidence levels

| Level | When to use |
|---|---|
| `high` | `name` or `display_name` matches unambiguously **and** scope requirements (if any) are satisfied by the template's current loop context. |
| `medium` | Plausible label/name match but semantic ambiguity (e.g. `claimant_phone` → account phone under the assumption `claimant == policyholder`). Also use when multiple registry entries are equally plausible — list all of them in `reasoning`. |
| `low` | No match, or a match exists but scope is wrong, or the name is ambiguous across multiple scopes. Always leave `data_source: ''`. |

Every `medium` and `low` entry MUST carry exactly one next-action from the
Ambiguity bubble-up vocabulary below. `high` entries do not need one.

### Rule 4 — Optional-element guard (`quantifier: '?'`)

When the matched path sits on an element with `quantifier: '?'` (e.g.
MedPay, Umbi, Umpd, or any data-extension field typed `<T>?`), append to
`reasoning`:

> requires `#if(<parent>.<Child>)` guard before access (element is
> zero-or-one)

Confidence is unaffected — the guard is a template-rendering concern, not
a match concern.

### Rule 5 — Auto-element note (`quantifier: '!'`)

When the matched path sits on an element with `quantifier: '!'`, append to
`reasoning`:

> element is auto-created on validation; always present (no `#if` guard
> needed)

### Rule 6 — Charge path disambiguation

In the registry, every charge exposes both a `velocity_object` (e.g.
`$data.charges.GoodDriverDiscount`) and a `velocity_amount` (e.g.
`$data.charges.GoodDriverDiscount.amount`).

- If the variable is a **charge amount** (label says "premium", "discount
  amount", "fee", currency-formatted cell, etc.), use `velocity_amount`
  and note this in `reasoning`.
- Use `velocity_object` only when the template iterates the charge itself
  (rare in document templates — usually a dashboard or detail view).

---

## Ambiguity bubble-up

Every `low` and every `medium` item MUST carry exactly one **next-action**
in its `reasoning` field, chosen from this closed vocabulary:

- `pick-one: <path1> | <path2> | ...` — registry has multiple plausible
  matches; the human must choose. List every candidate path.
- `supply-from-plugin: <suggested plugin field shape>` — no registry entry
  exists; the template wants data that must be computed by a plugin
  (e.g. claim-domain fields, loss-vehicle flattening). Sketch the plugin
  output shape the template expects (e.g.
  `$data.data.claimNumber` / string / scalar).
- `restructure-template: <describe>` — a registry entry exists but its
  `requires_scope` doesn't match the template structure; the template
  must be rewritten (typically wrap a block in `#foreach` with an `#if`
  selector).
- `delete-from-template: <reason>` — the field has no business purpose in
  this document (very rare; use sparingly).
- `confirm-assumption: <assumption>` — the match is reasonable if a named
  assumption holds (e.g. "claimant == policyholder"). The user must
  confirm before Leg 3 runs.
- `needs-skill-update: <describe>` — Leg 1 or the registry produced a
  key / section the suggester does not yet understand (surfaced by the
  shape probe). The placeholder itself may or may not have a valid
  match; this code tells the reviewer the skill's recognised-signal
  vocabulary must grow (or the key must be removed upstream) before the
  input can be reasoned about. Used exclusively in the `.review.md`
  **Unrecognised inputs** section — never on variable- or loop-level
  next-actions (those stick to the five codes above).

Exactly one next-action per `low` / `medium` item. `high` items do not
carry a next-action. If an ambiguity doesn't fit one of these codes,
stop and ask the user — do not invent a new code.
