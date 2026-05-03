# Stage 1 — Audit & Spec

**Status:** COMPLETE
**Depends on:** nothing (first stage)
**Output:** annotated gap table + per-rule implementation spec; no code changes yet

---

## Task 1.1 — Map current script behavior to SKILL-matching.md Rules 1–6

Read `scripts/leg2_fill_mapping.py` and `SKILL-matching.md` side-by-side and fill this table:

| Rule | What SKILL says | What script does today | Gap |
|---|---|---|---|
| Name-match precedence (4 steps: exact → CI → terminology → fuzzy) | Steps 1–4, stop at first hit | `specials` dict hardcoded; flat index CI lookup only via `.lower()` on field names; no display_name scan; no terminology | No display_name matching; no terminology; fuzzy is specials-only |
| Rule 1: Loop matching via iterables | Match loop name against iterables index, 4-step precedence | Hardcoded `if ln == "drivers"` / `"vehicles"` etc. | Not generic; breaks for any non-CommercialAuto iterable name |
| Rule 2: Scope checking (context.loop / context.loop_hint) | loop satisfies scope; loop_hint is reasoning aid only | Not implemented — no scope check at all | All scoped fields treated as unscoped |
| Rule 3: Confidence grading | high/medium/low per match quality | high for specials hits; low for misses | No medium for display_name/fuzzy matches without specials entry |
| Rule 4: Optional-element guard (`?` quantifier) | append note to reasoning | Not implemented | Missing from all outputs |
| Rule 5: Auto-element note (`!` quantifier) | append note to reasoning | Not implemented | Missing |
| Rule 6: Charge disambiguation | use velocity_amount for amounts; velocity_object for iteration | Not implemented — charges not matched at all for variables | Missing |

## Task 1.2 — Document the `specials` dict contract

The `specials` dict in `pick_policy_var` encodes CommercialAuto + policy-template conventions.
After Stage 2 lands, these cases should be handled by the generic matcher. Audit each entry:

- Mark entries that become redundant once display_name CI matching works (e.g. `policy_number` → CI on display_name "Policy number")
- Mark entries that need explicit handling (e.g. `policyholder_name` → account.name is an assumption, not a registry hit — keep as medium/confirm-assumption output from fuzzy logic)
- Mark entries that have NO registry counterpart and must stay as low/supply-from-plugin (e.g. `insured_first_name`, `broker_name`)

The goal is to **delete** the `specials` dict and have the generic matcher reproduce the same correct outputs deterministically.

## Task 1.3 — Specify the name-match algorithm

Write pseudocode for the 4-step name-match function:

```python
def match_name(name: str, label: str | None, registry: dict, terminology: dict | None) -> MatchResult:
    """
    Returns (velocity_path, confidence, reasoning, next_action | None).
    Stops at the first step that produces a hit.

    Step 1 — Exact match:
        Compare name against every registry entry's `field` key (case-sensitive).
        Compare label against every entry's `display_name` (case-sensitive).
        Accept if exactly one hit; ambiguous if 2+.

    Step 2 — Case-insensitive match:
        Same comparisons, ASCII case-fold equality.
        Separately fold name vs field, and label vs display_name.

    Step 3 — Terminology synonym lookup:
        If terminology loaded: check synonyms.fields, synonyms.exposures,
        synonyms.coverages, display_name_aliases.
        Match is exact string in alias list (case-insensitive).

    Step 4 — Fuzzy:
        snake_case ↔ camelCase transform of name vs field.
        Obvious single-word plurals (e.g. "vehicles" → "Vehicle").
        Only accept when unambiguous; otherwise return low/supply-from-plugin.
    """
```

## Task 1.4 — Specify scope-check logic

```python
def check_scope(entry: dict, variable: dict) -> ScopeResult:
    """
    entry: a registry entry with `requires_scope: [...]`
    variable: a mapping entry with optional context.loop and context.loop_hint

    Returns: SATISFIED | VIOLATED_WITH_HINT | VIOLATED_NO_HINT | NOT_REQUIRED
    """
    if not entry["requires_scope"]:
        return NOT_REQUIRED
    loop = variable["context"].get("loop")
    loop_hint = variable["context"].get("loop_hint")
    # ... match loop against requires_scope iterators
    # ... if loop_hint matches outermost: VIOLATED_WITH_HINT
    # ... else: VIOLATED_NO_HINT
```

## Acceptance criteria

- [x] Gap table above is filled in and reviewed by human before Stage 2 starts
- [x] Every `specials` entry is classified (redundant / explicit-assumption / no-registry-counterpart)
- [x] `match_name` and `check_scope` pseudocode reviewed and agreed
- [x] No code changes in this stage

## Execution notes

Stage 1 was performed as in-context analysis during the same session as Stage 2. The gap table was confirmed valid — `specials` entries fell cleanly into the three buckets. The `match_name` and `check_scope` pseudocode was approved and used verbatim as the implementation spec for Stage 2.
