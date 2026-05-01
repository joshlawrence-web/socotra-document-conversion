# Stage 2 — Agent C: Validation

**Depends on:** [Stage 1A](01-stage-1A-leg2-run-modes.md) AND [Stage 1B](02-stage-1B-leg1-batch.md) both complete

Agent C is **read-mostly**. It runs scripts, reads output files, and reports pass/fail. It does not edit `SKILL.md` or `convert.py` — any fixes required go back to the owning agent (A or B).

---

## Pre-flight checklist

Before running anything, confirm:

- [ ] `mapping-suggester/SKILL.md` contains `## Run modes` (search for the heading)
- [ ] `convert.py` accepts `--batch` (run `python3 convert.py --help` and check the flag appears)
- [ ] All 4 sample `.mapping.yaml` files exist under `samples/output/<stem>/`

If any pre-flight check fails, report which Stage 1 agent needs to be re-run and stop.

---

## Test 1 — Leg 1 batch mode

**Command:**

```bash
python3 .cursor/skills/html-to-velocity/scripts/convert.py \
    --batch samples/input/claim-form.html \
            samples/input/policy-template.html \
            samples/input/quote-application.html \
            samples/input/renewal-notice.html \
    --output-dir samples/output \
    --registry path-registry.yaml
```

**Pass criteria:**

| Check | Expected |
|---|---|
| Exit code | 0 |
| Output folders | `samples/output/claim-form/`, `policy-template/`, `quote-application/`, `renewal-notice/` all exist |
| Files per folder | `.vm`, `.mapping.yaml`, `README.md` present in each |
| Terminal output | Contains `Batch complete:` line with file count |
| Registry read count | Registry file opened exactly once (not 4 times) — verify via script print or by adding a temp debug print if needed |

---

## Test 2 — Leg 2 terse mode (manual invocation check)

Ask the Leg 2 skill to process `samples/output/claim-form/claim-form.mapping.yaml` in terse mode:

> "Run the mapping-suggester in terse mode on samples/output/claim-form/claim-form.mapping.yaml"

**Pass criteria:**

| Check | Expected |
|---|---|
| `## Run modes` section recognized | Agent reports mode as `terse` before Step 0 |
| Shape probe | Single-line summary printed, no table |
| `reasoning:` fields in `.suggested.yaml` | Every entry has a single quoted string (not a YAML block scalar `>`) |
| `.review.md` | Contains confidence table and blockers table; no per-blocker prose paragraphs |
| Terminal summary | 5 lines max |

---

## Test 3 — Leg 2 batch mode (manual invocation check)

Ask the Leg 2 skill to batch-process all 4 mapping files:

> "Run the mapping-suggester in batch mode on all four mapping files under samples/output"

**Pass criteria:**

| Check | Expected |
|---|---|
| `path-registry.yaml` read count | 1 (reported in terminal output) |
| Output files | `.suggested.yaml`, `.review.md`, `.suggester-log.jsonl` present for each stem |
| Combined terminal summary | Appears after all 4 docs processed |

---

## Test 4 — Schema compliance spot-check

For each `.suggested.yaml` produced in Test 2 or 3:

- [ ] `schema_version: '1.0'` is the first key
- [ ] Every entry has `name`, `placeholder`, `type`, `data_source`, `confidence`, `reasoning`
- [ ] `confidence` value is one of: `high`, `medium`, `low`
- [ ] `reasoning` is a non-empty string (single-line in terse mode)
- [ ] No entry has a `reasoning` block scalar (`>` or `|`) in terse mode

---

## Test 5 — Backward-compatibility check (Leg 1)

Run a single-file invocation to confirm no regression:

```bash
python3 .cursor/skills/html-to-velocity/scripts/convert.py \
    samples/input/renewal-notice.html \
    --output-dir samples/output/renewal-notice \
    --registry path-registry.yaml
```

**Pass criteria:** exit code 0, three output files written, no `--batch`-related error messages.

---

## Reporting

After all tests, Agent C produces a brief report in the terminal:

```
Validation report — pipeline-improvements
==========================================
Test 1  Leg 1 batch mode          PASS / FAIL
Test 2  Leg 2 terse mode          PASS / FAIL
Test 3  Leg 2 batch mode          PASS / FAIL
Test 4  Schema compliance         PASS / FAIL
Test 5  Leg 1 backward compat     PASS / FAIL

Overall: PASS / FAIL
```

On any FAIL, include the specific check that failed and which Stage 1 plan file owns the fix.
