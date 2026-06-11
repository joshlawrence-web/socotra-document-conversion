# Leg 4 — Conditional Registry Guard

**Status:** Done
**Completed:** 2026-06-09
**When done:** set `Status: Done`, add `Completed:` date, move folder to `CompletedPlans/` (§6).
**Created:** 2026-06-09

## START HERE (implementing agent)

When Leg 4 runs and finds no `{stem}.conditional-registry.yaml`, it silently emits a plugin with zero conditional puts. The user only discovers the omission by inspecting the output. The annotated HTML written by Leg 0 is the ground truth: if it contains `$doc.condN` markers, conditionals exist and the registry is required.

**Read in this order:**
1. This file — §2 (decisions), §3 (task list)
2. `scripts/leg4_generate_plugin.py` lines 581–598 — `load_conditional_registry()` — the silent-return-`[]` site
3. `scripts/leg4_generate_plugin.py` lines 1034–1036 — call site where `cond_blocks` is populated
4. `scripts/leg4_generate_plugin.py` lines 856–868 — `write_plugin_report()` conditional section
5. `scripts/agent_tools.py` lines 528–567 — `_run_leg4_single()` — subprocess launcher (preflight goes here)
6. `tests/test_leg2_review_writer.py` — test pattern to follow

---

## 1. Background

**Root cause:** `load_conditional_registry()` (leg4:581) returns `[]` with no diagnostic when its target file is absent. Nothing downstream checks whether conditionals *should* exist before accepting the empty list.

**Observable failure:** User ran `leg0` (which wrote `{stem}.annotated.html` with `$doc.cond1`–`$doc.cond7`), then ran `leg2+leg3+leg4` without first parsing the conditional form. Leg 4 emitted `Product=ZenCover high=0 ignored=0 compile=PASS` — a clean-looking result with all conditionals silently dropped.

**Detection signal available:** `{stem}.annotated.html` always lives alongside the mapping in `out_dir`. It is written by Leg 0 and contains every `$doc.condN` annotation. Counting unique `$doc.condN` occurrences in that file is an exact, zero-false-positive signal for "conditionals exist in this document."

**Fix goal:** Emit a clear, actionable warning — with the exact fix command — whenever Leg 4 detects conditionals in the annotated HTML but has no registry to work from. Do not silently succeed.

---

## 2. Decisions

| # | Topic | Decision |
|---|-------|----------|
| D1 | Warning vs hard error | **Warning, not error.** A document may legitimately have no conditional form parsed yet (draft stage). Block only if `--require-registry` flag is passed (future work — not in this plan). |
| D2 | Detection source | `{stem}.annotated.html` in the same `out_dir`. Count unique `$doc.condN` occurrences via regex. If file absent, count = 0 (no warning). |
| D3 | Warning in leg4 script | Print to **stderr** immediately after the `load_conditional_registry` call (leg4:1036). Message includes count and exact fix command. |
| D4 | Warning in agent_tools preflight | `_run_leg4_single()` performs the same check before launching the subprocess. Prints to **stdout** (visible in pipeline output). Same message format. |
| D5 | Plugin report | Upgrade the passive "_No conditional-registry.yaml found_" line (leg4:868) to a `> ⚠ WARNING` blockquote with count + fix command when annotated HTML has conditionals. When annotated HTML has no conditionals, keep the current passive message. |
| D6 | Warning format | Same text in all three locations: `"WARNING: {N} conditional(s) detected in {stem}.annotated.html but no conditional-registry.yaml found.\nRun: python3 scripts/leg0_ingest.py --parse-conditional-form {form_path} --output-dir {out_dir}"` |
| D7 | Form path in message | Derive from `out_dir / f"{stem}.conditional-form.md"`. If that file doesn't exist, omit the `--parse-conditional-form` arg and say `"(conditional-form.md not found — re-run Leg 0 first)"`. |
| D8 | No new dependency | Detection uses only stdlib `re` and `pathlib.Path`. No new imports. |
| D9 | No behaviour change when registry present | If `conditional-registry.yaml` exists (even empty), no warning. The existing happy path is unchanged. |

---

## 3. Task list

### T1 — `_count_annotated_conditionals()` helper in `leg4_generate_plugin.py`

**Goal:** Add a private helper function that counts unique `$doc.condN` markers in `{stem}.annotated.html`.

Place it immediately after `load_conditional_registry()` at line 598.

```python
def _count_annotated_conditionals(out_dir: Path, stem: str) -> int:
    """Count unique $doc.condN markers in {stem}.annotated.html. Returns 0 if file absent."""
    annotated = out_dir / f"{stem}.annotated.html"
    if not annotated.exists():
        return 0
    return len(set(re.findall(r'\$doc\.cond\d+', annotated.read_text(encoding="utf-8"))))
```

**Files:** `scripts/leg4_generate_plugin.py`

---

### T2 — Warn at load site in `leg4_generate_plugin.py`

**Goal:** After `cond_blocks = load_conditional_registry(cond_yaml)` (line 1036), add a warning when the registry is absent but conditionals exist.

Replace the current lines 1034–1036:
```python
# --- Load conditional registry (Leg 1 artifact) --------------------------
cond_yaml = out_dir / f"{stem}.conditional-registry.yaml"
cond_blocks = load_conditional_registry(cond_yaml)
```

With:
```python
# --- Load conditional registry (Leg 1 artifact) --------------------------
cond_yaml = out_dir / f"{stem}.conditional-registry.yaml"
cond_blocks = load_conditional_registry(cond_yaml)
if not cond_yaml.exists():
    n_conds = _count_annotated_conditionals(out_dir, stem)
    if n_conds > 0:
        form_path = out_dir / f"{stem}.conditional-form.md"
        if form_path.exists():
            fix_cmd = (
                f"python3 scripts/leg0_ingest.py "
                f"--parse-conditional-form {form_path} "
                f"--output-dir {out_dir}"
            )
        else:
            fix_cmd = "(conditional-form.md not found — re-run Leg 0 first)"
        print(
            f"WARNING: {n_conds} conditional(s) detected in {stem}.annotated.html "
            f"but no conditional-registry.yaml found.\nRun: {fix_cmd}",
            file=sys.stderr,
        )
```

**Files:** `scripts/leg4_generate_plugin.py`

---

### T3 — Upgrade plugin report warning in `write_plugin_report()`

**Goal:** When `cond_blocks` is empty, check if the annotated HTML has conditionals. If so, replace the passive message with an actionable warning blockquote.

The function signature at ~line 730 already receives `out_dir` (as `report_path.parent`) and the stem is derivable from `report_path.stem` (strip `.plugin-report`). Check the actual signature and derive `out_dir` and `stem` from the parameters already available. Do not add new parameters.

Current passive line (leg4:868):
```python
lines.append("_No conditional-registry.yaml found alongside this .mapping.yaml._")
```

Replace the `else` branch of the `if cond_blocks:` block (lines 858–868) with:

```python
if cond_blocks:
    lines += ["| id | depth | parent_id | source_text | conditions | status |", "|---|---|---|---|---|---|"]
    for b in cond_blocks:
        truncated = b["source_text"][:60] + ("..." if len(b["source_text"]) > 60 else "")
        status = "wired" if b["conditions"] else "TODO"
        conds = " \\| ".join(b["conditions"]) if b["conditions"] else "(empty)"
        parent_id = b.get("parent_id") or ""
        depth = b.get("depth", 0)
        lines.append(f"| {b['id']} | {depth} | {parent_id} | {truncated} | `{conds}` | **{status}** |")
else:
    # Determine report's stem and out_dir to check for unanswered conditionals
    report_stem = report_path.stem  # e.g. "ZenCoverTest(quote).plugin-report"
    if report_stem.endswith(".plugin-report"):
        doc_stem = report_stem[: -len(".plugin-report")]
    else:
        doc_stem = report_stem
    report_out_dir = report_path.parent
    n_conds = _count_annotated_conditionals(report_out_dir, doc_stem)
    if n_conds > 0:
        form_path = report_out_dir / f"{doc_stem}.conditional-form.md"
        if form_path.exists():
            fix_cmd = (
                f"python3 scripts/leg0_ingest.py "
                f"--parse-conditional-form {form_path} "
                f"--output-dir {report_out_dir}"
            )
        else:
            fix_cmd = "(conditional-form.md not found — re-run Leg 0 first)"
        lines.append(
            f"> ⚠ WARNING: {n_conds} conditional(s) detected in `{doc_stem}.annotated.html` "
            f"but no `conditional-registry.yaml` was found — all conditionals were omitted from the plugin.\n"
            f"> Fix: `{fix_cmd}`"
        )
    else:
        lines.append("_No conditional-registry.yaml found alongside this .mapping.yaml._")
```

**Files:** `scripts/leg4_generate_plugin.py`

---

### T4 — Preflight check in `_run_leg4_single()` in `agent_tools.py`

**Goal:** Before launching the Leg 4 subprocess, warn if conditionals exist but no registry is present. This surfaces the issue in the pipeline output (stdout) before the subprocess runs — not just in stderr from the subprocess itself.

In `_run_leg4_single()` (agent_tools.py:528), after deriving `stem` and `out_dir` (which currently happens *after* the subprocess at lines 554–560), **duplicate that derivation before the subprocess call** and add the preflight check.

Insert immediately after line 541 (`str(_resolve_safe(suggested, repo_root)),`), before line 542 (`if customer_jar:`):

```python
    # Preflight: warn if annotated HTML has conditionals but no registry
    _suggested_path = _resolve_safe(suggested, repo_root)
    _stem = _suggested_path.name
    for _sfx in (".suggested.yaml", ".mapping.yaml", ".yaml"):
        if _stem.endswith(_sfx):
            _stem = _stem[: -len(_sfx)]
            break
    _out_dir = _suggested_path.parent
    _cond_yaml = _out_dir / f"{_stem}.conditional-registry.yaml"
    if not _cond_yaml.exists():
        _annotated = _out_dir / f"{_stem}.annotated.html"
        if _annotated.exists():
            import re as _re
            _n = len(set(_re.findall(r'\$doc\.cond\d+', _annotated.read_text(encoding="utf-8"))))
            if _n > 0:
                _form = _out_dir / f"{_stem}.conditional-form.md"
                if _form.exists():
                    _fix = (
                        f"python3 scripts/leg0_ingest.py "
                        f"--parse-conditional-form {_form} "
                        f"--output-dir {_out_dir}"
                    )
                else:
                    _fix = "(conditional-form.md not found — re-run Leg 0 first)"
                print(
                    f"WARNING: {_n} conditional(s) detected in {_stem}.annotated.html "
                    f"but no conditional-registry.yaml found.\nRun: {_fix}"
                )
```

Note: `import re` is already at the top of `leg4_generate_plugin.py` but check whether it is also imported in `agent_tools.py`. If not, add `import re` to the import block at the top of the file instead of the inline `import re as _re`.

**Files:** `scripts/agent_tools.py`

---

### T5 — Tests

Add tests in `tests/test_leg4_conditional_guard.py` (new file).

**Test cases:**

| Test | Setup | Assert |
|------|-------|--------|
| `test_no_warning_when_registry_present` | `out_dir` has both `{stem}.annotated.html` (with `$doc.cond1`) and `{stem}.conditional-registry.yaml` | `_count_annotated_conditionals` returns 1; no warning emitted |
| `test_count_returns_zero_no_annotated_html` | `out_dir` has neither file | `_count_annotated_conditionals` returns 0 |
| `test_count_deduplicates` | annotated HTML has `$doc.cond1` three times | `_count_annotated_conditionals` returns 1 (unique count) |
| `test_count_multiple_conds` | annotated HTML has `$doc.cond1`, `$doc.cond2`, `$doc.cond3` | returns 3 |
| `test_plugin_report_shows_warning` | call `write_plugin_report()` with `cond_blocks=[]`; `out_dir` has annotated HTML with `$doc.cond1` | report text contains `"⚠ WARNING"` and `"1 conditional(s)"` |
| `test_plugin_report_no_warning_when_no_annotated_html` | call `write_plugin_report()` with `cond_blocks=[]`; no annotated HTML | report text contains `"_No conditional-registry.yaml found"` (passive) |

Use `tmp_path` (pytest fixture) to write synthetic HTML and call functions directly — no subprocess.

**Files:** `tests/test_leg4_conditional_guard.py` (new)

---

## 4. Definition of done

```bash
# 1. Reproduce the original failure scenario
python3 scripts/leg0_ingest.py \
  --input samples/input/ZenCoverTest\(quote\).docx \
  --output-dir samples/output/ZenCoverTest\(quote\)/

# 2. Run leg4 WITHOUT parsing the conditional form first
python3 scripts/leg4_generate_plugin.py \
  --suggested "samples/output/ZenCoverTest(quote)/ZenCoverTest(quote).mapping.yaml" \
  --customer-jar build/customer-config.jar \
  --datamodel-jar build/core-datamodel-v1.7.61.jar
# Expected stderr: WARNING: 7 conditional(s) detected ... but no conditional-registry.yaml found.
# Expected: includes fix command pointing to the conditional-form.md

# 3. Check plugin-report.md contains the warning blockquote
grep "⚠ WARNING" "samples/output/ZenCoverTest(quote)/ZenCoverTest(quote).plugin-report.md"

# 4. Run the fix and verify clean run
python3 scripts/leg0_ingest.py \
  --parse-conditional-form "samples/output/ZenCoverTest(quote)/ZenCoverTest(quote).conditional-form.md" \
  --output-dir "samples/output/ZenCoverTest(quote)/"
python3 scripts/leg4_generate_plugin.py \
  --suggested "samples/output/ZenCoverTest(quote)/ZenCoverTest(quote).mapping.yaml" \
  --customer-jar build/customer-config.jar \
  --datamodel-jar build/core-datamodel-v1.7.61.jar
# Expected: no WARNING in stderr; plugin-report shows 7 conditional blocks; compile=PASS

# 5. Tests pass
python3 -m pytest tests/test_leg4_conditional_guard.py -v
```

| Check | Expected |
|-------|----------|
| Leg 4 without registry → stderr WARNING with count=7 and fix command | ✓ |
| Plugin report without registry → `⚠ WARNING` blockquote with count + fix command | ✓ |
| Pipeline (`agent_tools`) without registry → stdout WARNING before subprocess | ✓ |
| Leg 4 with registry present → no warning, identical output to before | ✓ |
| Plugin report with no annotated HTML → passive message (unchanged) | ✓ |
| All T5 tests pass | ✓ |

---

## 5. Files touched

| File | Change |
|------|--------|
| `scripts/leg4_generate_plugin.py` | Add `_count_annotated_conditionals()`; warn at load site (T1, T2); upgrade report (T3) |
| `scripts/agent_tools.py` | Add preflight check in `_run_leg4_single()` (T4) |
| `tests/test_leg4_conditional_guard.py` | **New** — 6 test cases (T5) |

No other files are touched. No schema changes. No new CLI flags.

---

## 6. Self-certification (completing agent — required)

When every item in §4 Definition of done is satisfied:

1. Edit this file: change `**Status:** Open` → `**Status:** Done` and add `**Completed:** <date>`.
2. Move this folder: `mv .cursor/plans/pipeline-improvements/09-leg4-conditional-registry-guard/ .cursor/plans/pipeline-improvements/CompletedPlans/`
3. Commit both changes with your implementation (or in a follow-up commit).

**Do not skip this step.** Plans left "Open" after completion create false signals about remaining work.
