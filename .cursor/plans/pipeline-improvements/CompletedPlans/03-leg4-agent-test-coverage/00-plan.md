# Leg 4 + agent.py Test Coverage

**Status:** Done
**Completed:** 2026-06-09
**When done:** set `Status: Done`, add `Completed:` date, move folder to `CompletedPlans/` (§6).
**Created:** 2026-06-09
**Item:** Plan-for-plans #3

## START HERE (implementing agent)

Add regression and integration tests for `leg4_generate_plugin.py` and `agent.py`. Currently: zero test files for either script.

**Read in this order:**
1. This file — §2 (decisions), §3 (task list)
2. `scripts/leg4_generate_plugin.py` — `run_leg4()` (line 573), additive merge (line 860–956), report writer (line 600–700)
3. `scripts/agent.py` — `parse_pipeline_args()` (line 86), dispatch block (line ~200–400)
4. `tests/regression/test_leg2_advanced.py` — regression pattern to follow
5. `tests/integration/test_it1_label_quality.py` — integration pattern to follow
6. `conformance/fixtures/` — golden file convention

---

## 1. Background

`leg4_generate_plugin.py` is the most complex script in the pipeline — it probes JARs, renders Java, handles additive merge, writes a plugin report. It has zero test coverage. Bugs in additive merge (duplicate keys, wrong `condN` counter, malformed Java) will only surface at compile time.

`agent.py` parses all pipeline invocations via `parse_pipeline_args()`. There are no tests for: unknown op rejection, missing required args, valid multi-leg chains, or `--yes` flag behaviour. A parse regression here silently produces wrong pipeline runs.

---

## 2. Decisions

| # | Topic | Decision |
|---|-------|----------|
| D1 | JAR dependency in tests | Most Leg 4 tests must be **JAR-free** — fake/mock the JAR probing (`sdk_introspect.jar_candidate`, `_zero_arg_methods`) using `unittest.mock.patch`. Only one integration test exercises real JARs (skipped if `build/` absent). |
| D2 | Additive merge tests | Use in-memory fixture Java files (string constants) — no disk write needed. Test `_merge_additive()` directly. |
| D3 | Rendered Java tests | Assert on substrings, not full golden files. Full goldens are brittle against whitespace. Assert: class name, `put("expectedKey"`, `renderingData.builder()`, `.build()`. |
| D4 | agent.py tests | Unit-test `parse_pipeline_args()` with a table of valid and invalid invocation strings. Do not run the actual pipeline in parse tests. |
| D5 | agent.py integration | One end-to-end test using the existing `samples/` fixtures: run `agent.py --yes "RUN_PIPELINE list_paths ..."` and assert exit 0 + stdout contains `## System Fields`. |
| D6 | Compile-check test | If `javac` is available on PATH, add one test that calls `--compile-check` on a known-good `.java` fixture. Skip if `javac` absent. |
| D7 | Test file locations | Regression tests (no JARs, no disk) → `tests/regression/`. Integration tests (may write files, may need build/) → `tests/integration/`. |

---

## 3. Task list

### T1 — `test_leg4_render.py` — fresh plugin rendering

**Goal:** Test that `run_leg4()` (with mocked JAR probe) produces correct Java structure.

Test cases:
- `test_class_name_in_output` — class name matches product name
- `test_put_calls_for_all_keys` — one `put("key"` per suggested key
- `test_builder_pattern_present` — `renderingData.builder()` and `.build()` in output
- `test_no_tbd_in_output` — no `$TBD_` in final Java
- `test_plugin_report_written` — `.plugin-report.md` created

**Fixtures:** Create `tests/regression/fixtures/simple.suggested.yaml` — a minimal suggested YAML with 3 keys, no datafetcher.

**Files:** `tests/regression/test_leg4_render.py` (new)

---

### T2 — `test_leg4_additive.py` — additive merge

**Goal:** Test the additive merge path directly.

Test cases:
- `test_new_keys_added` — keys in suggested but not in existing plugin are inserted
- `test_existing_keys_not_duplicated` — keys already in plugin are not added again
- `test_bak_written` — `.java.bak` file created before modification
- `test_cond_counter_continues` — `condN` counter starts at `cond_high_water + 1`
- `test_empty_existing_keys` — additive on a file with 0 puts → all keys inserted

**Fixtures:** String constants `VALID_PLUGIN_JAVA` and `PLUGIN_WITH_SOME_KEYS` in the test file.

**Files:** `tests/regression/test_leg4_additive.py` (new)

---

### T3 — `test_agent_parse.py` — parse_pipeline_args unit tests

**Goal:** Table-driven tests for `parse_pipeline_args()`.

Valid cases (should return non-None, correct fields):
- `"RUN_PIPELINE leg1 input=foo.html"`
- `"RUN_PIPELINE leg1+leg2+leg3 input=foo.html registry=r.yaml"`
- `"RUN_PIPELINE leg0 input=form.docx output=samples/output"`
- `"RUN_PIPELINE list_paths registry=r.yaml"`
- `"RUN_PIPELINE leg4 suggested=foo.suggested.yaml"`
- `"RUN_PIPELINE leg3 high_only=true suggested=foo.yaml"`

Invalid cases (should return None or raise, not crash):
- `"RUN_PIPELINE unknown_op"` — unknown operation
- `"RUN_PIPELINE leg1"` — missing required `input`
- `"not a pipeline invocation"` — no RUN_PIPELINE token
- `""` — empty string

**Files:** `tests/regression/test_agent_parse.py` (new)

---

### T4 — `test_it8_agent_dispatch.py` — agent.py end-to-end

**Goal:** Run `agent.py --yes "RUN_PIPELINE list_paths registry=..."` in a subprocess and assert exit 0 + output contains Markdown headers.

This exercises the full dispatch path without JARs.

```python
import subprocess, sys

def test_agent_list_paths_end_to_end():
    result = subprocess.run(
        [sys.executable, "scripts/agent.py", "--yes",
         "RUN_PIPELINE list_paths registry=registry/path-registry.yaml"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0
    assert "## System Fields" in result.stdout
```

**Files:** `tests/integration/test_it8_agent_dispatch.py` (new)

---

### T5 — `test_leg4_report.py` — plugin report content

**Goal:** Assert structure of the plugin report Markdown.

Test cases:
- `test_report_has_key_count` — report contains "Keys written"
- `test_report_additive_section` — additive mode report includes "Additive update summary"
- `test_report_unresolved_section` — if $TBD_ keys present, "Unresolved" section appears

**Files:** `tests/regression/test_leg4_report.py` (new)

---

## 4. Definition of done

```bash
# Run all new tests
python3 -m pytest tests/regression/test_leg4_render.py \
                  tests/regression/test_leg4_additive.py \
                  tests/regression/test_agent_parse.py \
                  tests/regression/test_leg4_report.py \
                  tests/integration/test_it8_agent_dispatch.py \
                  -v
```

| Check | Expected |
|-------|----------|
| All T1 tests pass (mocked JARs) | ✓ |
| All T2 additive merge tests pass | ✓ |
| All T3 parse tests pass | ✓ |
| T4 end-to-end exits 0 | ✓ |
| T5 report tests pass | ✓ |
| No new test requires JARs unless explicitly skipped | ✓ |
| Existing test suite unaffected | ✓ |

---

## 5. Files touched

| File | Change |
|------|--------|
| `tests/regression/test_leg4_render.py` | **New** |
| `tests/regression/test_leg4_additive.py` | **New** |
| `tests/regression/test_agent_parse.py` | **New** |
| `tests/regression/test_leg4_report.py` | **New** |
| `tests/integration/test_it8_agent_dispatch.py` | **New** |
| `tests/regression/fixtures/simple.suggested.yaml` | **New** — minimal fixture |

---

## 6. Self-certification (completing agent — required)

When every item in §4 Definition of done is satisfied:

1. Edit this file: change `**Status:** Open` → `**Status:** Done` and add `**Completed:** <date>`.
2. Move this folder: `mv .cursor/plans/pipeline-improvements/03-leg4-agent-test-coverage/ .cursor/plans/pipeline-improvements/CompletedPlans/`
3. Commit both changes with your implementation (or in a follow-up commit).

**Do not skip this step.** Plans left "Open" after completion create false signals about remaining work.
