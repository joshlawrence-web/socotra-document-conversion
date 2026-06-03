# Leg 2 — Root-aware, SDK-grounded confidence

**Implementing agents: start here.**

| Read first | Purpose |
|------------|---------|
| [problem.md](./problem.md) | The bug + reproducible `javap` evidence (`policyNumber` rated `high` but absent on `ItemCareSegment`). |
| [00-plan.md](./00-plan.md) | Locked decisions, the new `.suggested.yaml` **2.0** schema, JAR-introspection design, filename convention, task list, definition of done. |
| [history.md](./history.md) | Session log — append when you finish work. |

**Status:** Planning complete (2026-06-03) · decisions locked · no code yet.

**One-line summary:** Make Leg 2 grade confidence per **(placeholder × rendering root)**
by introspecting the compiled JARs (`build/*.jar`) — the JARs are the authority for
which `$data.*` paths actually exist on the quote / segment / invoice root a document
renders against. The root is declared in the filename: `Simple-form(segment).html`.

**Locked decisions (00-plan §3):**

- **D1** JARs are the SDK authority; registry stays the name→candidate source only.
- **D2** Rendering root declared in the filename brackets — no inference.
- **D3** Shared `scripts/sdk_introspect.py` (factored from Leg 4) used by Leg 2 + Leg 4.
- **D4** `.suggested.yaml` **MAJOR bump → 2.0** with per-root verdicts.
- **D5** Invoice root out of the first cut.
- **D6** Downstream Leg 1/3/4 changes are **described, not built** (00-plan §14).
- **D10** Delta mode out of the first cut — blocked cleanly for 2.0; deferred to a more mature pipeline.

**Acceptance:** `Simple-form` `POLICY_NUMBER` is no longer `high` on the segment root
(demoted to `low` + `supply-from-plugin` with a `Policy.policyNumber()` sibling hint),
while a segment-resident field (`$data.locator`) still rates `high`.

**Do not** expand scope beyond [00-plan.md §3](./00-plan.md) without user approval, and
**do not** implement the §14 downstream-leg changes in this effort.
