# mapping-suggester — Phase D Lesson Workflow

This file contains the full contract for the `skill-lessons.yaml` ledger.
Referenced from `SKILL.md` §"Lesson workflow (Phase D)".

---

## Purpose

The mapping-suggester keeps a repo-level lessons ledger at
`skill-lessons.yaml` (see `SCHEMA.md` → "Artifact: `skill-lessons.yaml`"
for the shape). The ledger accumulates patterns that keep surfacing
across customers and documents, so a human reviewer can decide
whether the pattern deserves a first-class rule in `SKILL.md`.

---

## State machine

```
observed  ──┐
            ├──► proposed  ──►  promoted
            │         │
            │         └────►  rejected
            │
            └── (stays at observed until a human acts)
```

- **observed** — the suggester has seen this pattern one or more
  times and appended it to the ledger. Every agent-authored row is
  born in this state. Nothing downstream consumes `observed` rows.
- **proposed** — a human reviewer wrote a concrete rule change in
  `candidate_promotion` and flipped `status` to `proposed`. Still
  observation-only from the pipeline's point of view.
- **promoted** — another human accepted the `candidate_promotion`,
  copied its rule into `SKILL.md`, and flipped `status` to `promoted`.
  From this moment Step 0b applies the rule on every run. The v1.0
  contract has zero promoted rows — the hook exists so a future
  promotion doesn't need another plumbing round-trip.
- **rejected** — the reviewer rejected the proposal. The row stays
  in the ledger for historical record; `seen_count` keeps incrementing
  if the pattern recurs, so the row can be re-proposed later.

---

## Division of responsibility

| Actor | May edit | Must not |
|---|---|---|
| `mapping-suggester` (agents) | `seen_count`, `last_seen`, `observed_in` on existing rows; append new `observed` rows. | Flip `status` on any row; author or rewrite `candidate_promotion`; edit `pattern` or `current_rule` on existing rows; reorder, merge, or delete rows. |
| Human reviewer | Anything. Typically: write `candidate_promotion` and flip `status` to `proposed`; later flip to `promoted` / `rejected`. | — |

The hard constraint in `SKILL.md` § "Important constraints" is the
test-failure-not-style-guideline enforcement of this table.

---

## Seeded lesson matchers (v1.0 contract — session D2)

The seed ledger carries two lessons. Each matcher is a closed rule
keyed by lesson `id`; agents apply the matchers exactly, never
paraphrasing or generalising. New lessons add new matchers here.

| Lesson `id` | Fires on a placeholder when |
|---|---|
| `claimant-eq-policyholder` | `name` begins with `claimant_` AND `confidence ∈ {medium, low}` AND `next_action ∈ {supply-from-plugin, confirm-assumption}`. Captures the pattern where claimant identity collapses onto the policyholder because no Claim entity exists in the registry. |
| `vehicle-scope-violation` | `name` begins with `vehicle_` AND `next_action == restructure-template`. Captures scope-violation fallout from Rule 2 — a name that would match a registry entry if the template wrapped the block in `#foreach ($vehicle in $data.vehicles)`. |

A lesson is "matched this run" iff at least one placeholder in the
run satisfies its matcher. `seen_count` increments by 1 per run,
never by the number of placeholders that fired the matcher.

---

## Pattern-match semantics (exact-string only)

`skill-lessons.yaml` stores each lesson's `pattern` as prose for
human readers; matching is done by the per-lesson matchers above,
not by string-matching against `pattern`. When a new pattern is
observed that no existing matcher covers, the agent appends a new
row with a new matcher added to this section at the same time. A
row with no matcher is a maintenance bug.

Fuzzy / inferred matching is explicitly out of scope. If a run's
behaviour is within one synonym of an existing matcher but does not
satisfy it literally, append a new lesson rather than loosening the
existing matcher.

---

## Review threshold

When any lesson's `seen_count` reaches `>= 3` with `status ==
observed`, the next `.review.md` output surfaces a one-line note in
§7 ("Unrecognised inputs") with the lesson id and its current
`current_rule`, reminding the reviewer to consider promotion. The
threshold is advisory — the suggester never blocks on it.

---

## Step 4d procedure (agent write contract)

If Step 0b loaded a `skill-lessons.yaml`, update it after Step 4c.
If absent, this step is a no-op. The file is never auto-created.

1. For every lesson in `skill-lessons.yaml`, check whether at least
   one placeholder record from this run satisfies its matcher.
2. For every matched existing lesson: increment `seen_count` by 1,
   set `last_seen` to today's UTC date (`YYYY-MM-DD`), append the
   current source stem to `observed_in` if not already present.
   Leave all other keys untouched.
3. For any pattern observed this run not represented by an existing
   lesson, append a new row with keys in this order: `id`,
   `first_seen`, `last_seen`, `seen_count: 1`, `observed_in`,
   `pattern`, `current_rule`, `candidate_promotion: null`,
   `status: observed`.
4. Write the file back as a YAML round-trip. Preserve existing
   comments and key order on untouched rows.

Hard prohibitions (test failure, not style guideline):

- **Never** flip any row's `status`.
- **Never** author or rewrite `candidate_promotion`.
- **Never** edit `pattern` or `current_rule` on an existing row.
- **Never** reorder, merge, or delete existing lesson rows.

See [`PIPELINE_EVOLUTION_PLAN.md`](../../plans/pipeline-improvements/CompletedPlans/alpha-beta-plan/PIPELINE_EVOLUTION_PLAN.md) §7 for the authoritative wording.
