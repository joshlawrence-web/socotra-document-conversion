# Leg 2 Completeness Check

**Status:** Open
**When done:** set `Status: Done`, add `Completed:` date, move folder to `CompletedPlans/` (§6).
**Created:** 2026-06-09
**Item:** Plan-for-plans #6

## START HERE (implementing agent)

After Leg 2 runs, add a completeness check: what fraction of tokens resolved? How many `$TBD_*` remain at each confidence tier? Surface this as a summary badge in `review.md` and as a machine-readable field in `.suggested.yaml`.

> **Cross-reference (plan 10-conditional-field-tokens, D5):** Leg 4 now hard-fails when a
> field inside a `[[...]]` conditional block has no `data_source`. The user's stated
> direction is to catch this *earlier* — this completeness check is the natural home for
> a pre-Leg-4 gate: flag any unresolved token that appears inside a conditional block as
> a blocking item (not just a percentage), so the failure surfaces at Leg 2 review time.

**Read in this order:**
1. This file — §2 (decisions), §3 (task list)
2. `scripts/leg2_fill_mapping.py` — `suggest_variable()` (line 792), `confidence_grade()` (line 627) — where confidence is assigned
3. `scripts/leg2_review_writer.py` — `write_review()` — the review.md writer; where to add the summary section
4. `conformance/schemas/` — `.suggested.yaml` schema to extend with a `completeness` field
5. `tests/regression/test_leg2_review_writer.py` — test pattern to follow

---

## 1. Background

After Leg 2 runs, a template author has to open `review.md` and manually scan for unresolved tokens. There is no at-a-glance signal for whether the run was "mostly done" or "half missing". Similarly, `agent.py` has no way to programmatically decide whether to proceed to Leg 3 or warn the user.

**Current state:**
- `.suggested.yaml` contains per-token `confidence: high/medium/low/none`
- `review.md` lists tokens by confidence tier but has no summary count at the top

**This plan adds:**
- A completeness summary at the top of `review.md` (counts + % resolved)
- A `completeness` block in `.suggested.yaml` metadata
- An optional `--require-completeness N` flag on `leg3_substitute.py` that aborts if resolution % < N

---

## 2. Decisions

| # | Topic | Decision |
|---|-------|----------|
| D1 | Resolved definition | A token is "resolved" if `confidence` is `high` or `medium`. `low` and `none` are unresolved. `high_only` mode: only `high` counts as resolved. |
| D2 | Summary location in review.md | First section, above all confidence tiers. Title: `## Completeness Summary`. |
| D3 | Summary content | Table: Total tokens, Resolved (high+medium), High only, Low, None (old-format/unknown). Plus a % bar: `████████░░ 80%`. ASCII bar 10 chars wide, rounded. |
| D4 | `.suggested.yaml` metadata field | Add a top-level `completeness:` block (not inside any token entry): `{total, high, medium, low, none, resolved_pct}`. Written by `leg2_fill_mapping.py` when it writes the YAML. |
| D5 | `--require-completeness` flag | On `leg3_substitute.py`. Takes an integer 0–100. If `completeness.resolved_pct < N`, print a warning and exit 1. Default: 0 (no check). Allows CI to gate on quality. |
| D6 | `high_only` mode | When `leg3_substitute.py` runs with `high_only=true`, use `high` count for the % check (not `high+medium`). |
| D7 | No change to token schema | The per-token `confidence` field is unchanged. Only the top-level `completeness:` block is new. |
| D8 | Backwards compat | `.suggested.yaml` files without a `completeness:` block are silently treated as "unknown" by Leg 3; no error. |

---

## 3. Task list

### T1 — `compute_completeness()` in `leg2_fill_mapping.py`

**Goal:** Add a function that aggregates confidence counts from a list of token results.

```python
def compute_completeness(token_results: list[dict]) -> dict:
    """Aggregate confidence counts from suggest_variable() results.
    Returns:
      {total, high, medium, low, none, resolved_pct: float}
    resolved_pct = (high + medium) / total * 100, rounded to 1 decimal.
    """
```

Call at the end of the main mapping loop; write the result into the `.suggested.yaml` top-level block.

**Files:** `scripts/leg2_fill_mapping.py`

---

### T2 — Completeness section in `review.md`

**Goal:** Add `## Completeness Summary` as the first section in `review.md`.

```markdown
## Completeness Summary

| | Count | % |
|-|-------|---|
| Total tokens | 25 | — |
| Resolved (high + medium) | 20 | 80% |
| High confidence | 18 | 72% |
| Medium confidence | 2 | 8% |
| Low confidence | 3 | 12% |
| Unresolved (none) | 2 | 8% |

Progress: `████████░░` 80%
```

**Files:** `scripts/leg2_review_writer.py`

---

### T3 — `completeness:` block in `.suggested.yaml`

**Goal:** Write the completeness dict as a top-level YAML key when saving the suggested mapping.

```yaml
completeness:
  total: 25
  high: 18
  medium: 2
  low: 3
  none: 2
  resolved_pct: 80.0
```

**Files:** `scripts/leg2_fill_mapping.py` (YAML write step)

---

### T4 — `--require-completeness` flag on `leg3_substitute.py`

**Goal:** Gate Leg 3 on completeness threshold.

```bash
python3 scripts/leg3_substitute.py \
  --suggested samples/output/ZenCover/ZenCover.suggested.yaml \
  --require-completeness 90
# If resolved_pct < 90:
# ERROR: Completeness check failed: 80.0% resolved (required: 90%).
# Run Leg 2 again or fix unresolved tokens in review.md before proceeding.
# Exit 1.
```

**Files:** `scripts/leg3_substitute.py`

---

### T5 — Pipeline integration via `agent.py`

**Goal:** Expose `require_completeness=` as a `RUN_PIPELINE` kwarg.

```
RUN_PIPELINE leg1+leg2+leg3 input=... registry=... require_completeness=80
```

**Files:** `scripts/agent.py`, `scripts/agent_tools.py`

---

### T6 — Tests

Test cases:
- `test_completeness_all_high` — 5 high tokens → `resolved_pct=100.0`
- `test_completeness_mixed` — 3 high, 1 medium, 1 none → `resolved_pct=80.0`
- `test_completeness_all_none` — 3 none → `resolved_pct=0.0`
- `test_review_md_has_summary_section` — output Markdown starts with `## Completeness Summary`
- `test_ascii_bar_80pct` — `████████░░` appears in output at 80%
- `test_require_completeness_passes` — leg3 with `require_completeness=70` when pct=80 → exit 0
- `test_require_completeness_fails` — leg3 with `require_completeness=90` when pct=80 → exit 1

**Files:** `tests/regression/test_leg2_completeness.py` (new)

---

## 4. Definition of done

```bash
# Full pipeline run — check review.md has summary
python3 scripts/agent.py --yes \
  "RUN_PIPELINE leg1+leg2+leg3 input=samples/input/Simple-form(quote).html \
   registry=registry/path-registry.yaml output=samples/output"
grep "Completeness Summary" samples/output/Simple-form\(quote\)/Simple-form\(quote\).review.md

# Check .suggested.yaml has completeness block
python3 -c "
import yaml
d = yaml.safe_load(open('samples/output/Simple-form(quote)/Simple-form(quote).suggested.yaml'))
assert 'completeness' in d
print(d['completeness'])
"
```

| Check | Expected |
|-------|----------|
| `review.md` first section is Completeness Summary | ✓ |
| `.suggested.yaml` has top-level `completeness:` block | ✓ |
| ASCII bar renders correctly for 80%, 100%, 0% | ✓ |
| `--require-completeness 90` exits 1 when pct < 90 | ✓ |
| `--require-completeness 0` (default) never blocks | ✓ |
| All T6 tests pass | ✓ |
| Existing conformance goldens updated (new YAML key) | ✓ |

---

## 5. Files touched

| File | Change |
|------|--------|
| `scripts/leg2_fill_mapping.py` | Add `compute_completeness()`; write `completeness:` block |
| `scripts/leg2_review_writer.py` | Add Completeness Summary section |
| `scripts/leg3_substitute.py` | Add `--require-completeness` flag |
| `scripts/agent_tools.py` | Thread `require_completeness` kwarg |
| `scripts/agent.py` | Accept `require_completeness=` in dispatch |
| `tests/regression/test_leg2_completeness.py` | **New** |
| `conformance/fixtures/` | Update goldens (new `completeness:` top-level key) |

---

## 6. Self-certification (completing agent — required)

When every item in §4 Definition of done is satisfied:

1. Edit this file: change `**Status:** Open` → `**Status:** Done` and add `**Completed:** <date>`.
2. Move this folder: `mv .cursor/plans/pipeline-improvements/06-leg2-completeness-check/ .cursor/plans/pipeline-improvements/CompletedPlans/`
3. Commit both changes with your implementation (or in a follow-up commit).

**Do not skip this step.** Plans left "Open" after completion create false signals about remaining work.
