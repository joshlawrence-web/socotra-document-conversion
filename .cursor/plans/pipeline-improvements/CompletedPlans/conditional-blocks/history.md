# History — Conditional Block Extraction (Leg 1 + Leg 4)

Append-only. One entry per work session.

---

## 2026-06-05 — Plan created + fully implemented

### Context

HTML input templates contain a second `[...]` syntax — `[prose text with spaces]` —
distinct from the existing loop-token syntax `[identifier]`/`[/identifier]`.
These blocks map to Java runtime conditions in the `DocumentDataSnapshotPlugin`:
the `.vm` receives a `$doc.condN` variable; the plugin sets it to the prose string
or `""` based on Java expressions filled by humans after pipeline runs.

The triggering input was line 14 of `samples/input/Simple-form(quote).html`:
```
[this is some boiler plate text that will be included if the coverage selected is breakdown]
```

### Summary

**Leg 1 changes (`convert.py`):**
- Added `COND_BLOCK_RE = re.compile(r'\[([^\[\]\n]{4,})\]')` and `_is_loop_token()`
  guard (skips simple identifiers that `MUSTACHE_RE` would already handle).
- Added `conditional_blocks: list[dict]` field to `Mapping` dataclass.
- Added `extract_conditional_blocks(soup, mapping)` — runs as step 5.5 (after
  leftover-token check, before loop-hint annotation); replaces `[prose]` in soup
  text nodes with `$doc.condN`, records `{id, source_text}` entries.
- Added `write_conditional_registry(blocks, csv_path)` — writes
  `<stem>.conditional-registry.csv` with header `id,source_text,conditions,operator,notes`;
  always written even when empty.
- Added `write_conditional_ref_html(original_html, blocks, ref_path)` — annotates
  original HTML with `<sup>N</sup>` markers for human lookup; only written when
  at least one block was found.
- `convert()` return extended to `(vm_path, yaml_path, report_path, csv_path, ref_path, n_vars, n_loops, n_conds)`.
- `main()` updated for both single-file and batch modes; single-file prints new paths.

**Leg 4 changes (`leg4_generate_plugin.py`):**
- Added `import csv`.
- Added `load_conditional_registry(csv_path)` — reads CSV, splits `conditions` on `|`,
  defaults `operator` to `AND`; returns `[]` if file absent.
- Added `render_conditional_puts(blocks)` — emits a TODO stub when `conditions` is
  blank; emits a full `String condN = ""; if (...) { condN = "..."; } renderingData.put(...)`
  block when conditions are present.
- `JAVA_TEMPLATE` updated: `%(quote_conditional_puts)s` and `%(policy_conditional_puts)s`
  placeholders inserted after the existing `*_datafetcher_extras` lines in both handlers.
- `render_java()` accepts `cond_blocks` param; calls `render_conditional_puts`.
- `main()` auto-discovers `<stem>.conditional-registry.csv` alongside the
  `.suggested.yaml`; passes `cond_blocks` to `render_java()` and `write_report()`.
- `write_report()` appends a "Conditional blocks" section — table with id, source_text,
  conditions, and wired/TODO status.

**Prediction changes (`agent_tools.py`):**
- `_predict_writes()` Leg 1 block extended to include
  `<stem>.conditional-registry.csv` and `<stem>.conditional-ref.html`.

### Files touched
- `.cursor/skills/html-to-velocity/scripts/convert.py` (amended: T1–T6)
- `scripts/leg4_generate_plugin.py` (amended: T7–T12)
- `scripts/agent_tools.py` (amended: T13)

### Verification
```bash
# Step 1 — Leg 1 artifacts
python3 scripts/agent.py --yes "RUN_PIPELINE leg1 input=samples/input/Simple-form(quote).html output=samples/output"
# → conditional-registry.csv (1 row, blank conditions)
# → conditional-ref.html (<sup>1</sup> after the [text])
# → .vm contains $doc.cond1 where [text] was

# Step 2 — Leg 4 TODO stub
python3 scripts/leg4_generate_plugin.py \
  --suggested samples/output/Simple-form\(quote\)/Simple-form\(quote\).suggested.yaml \
  --compile-check
# → Java: renderingData.put("cond1", ""); + TODO comment · compile=PASS
# → plugin-report.md: Conditional blocks (1 total) · status=TODO

# Step 3 — Leg 4 wired if-block (manually set conditions in CSV first)
# → Java: if (condition) { cond1 = "..."; } renderingData.put("cond1", cond1);
# → plugin-report.md: status=wired

# Step 4 — Full pipeline regression
python3 scripts/agent.py --yes "RUN_PIPELINE leg1+leg2+leg3 input=samples/input/Simple-form(quote).html registry=registry/path-registry.yaml output=samples/output"
# → All legs complete; existing fields resolve; new CSV + ref HTML present
```

### Open items / next
- Leg 4 does not yet support operator=OR when building the multi-condition join
  differently from AND — code is implemented but untested with a real OR case.
- The CSV's `notes` column is captured but not surfaced in the plugin report; could
  add as a tooltip or extra column if useful.
- No automated test added for `extract_conditional_blocks`; covered only by the
  end-to-end pipeline run above.

---

<!-- Template for future entries:

## YYYY-MM-DD — Short title

### Summary
- bullet

### Files touched
- path

### Verification
- command

-->
