# Stage 1A — Agent A: Leg 2 Run Modes

**Runs in parallel with:** [Stage 1B](02-stage-1B-leg1-batch.md)
**Hands off to:** [Stage 2 — Validation](03-stage-2-validation.md) (after Stage 1B also finishes)

---

## Scope

One file only:

```
.cursor/skills/mapping-suggester/SKILL.md
```

No other files are touched by this agent.

---

## Change 1 — Add `## Run modes` section

**Insert location:** after line 41 (end of the "What this skill does" list block), before `## If a user asks what this skill does`.

The new section defines the mode vocabulary the agent resolves **before Step 0** on every invocation.

```markdown
## Run modes

Resolve the active mode from the user's invocation before doing anything else.
If no keyword is present, default to `full`.

| Mode | Trigger keywords | Description |
|---|---|---|
| `full` | *(default)* | Current behavior. Verbose reasoning, full shape probe, full review.md prose. |
| `terse` | "terse", "quick pass", "quick run" | Abbreviated outputs. Single-line reasoning, table-only review.md, one-line shape probe. ~50% fewer output tokens. |
| `batch` | "batch", "run on all files", or multiple `.mapping.yaml` paths given | Read `path-registry.yaml` once; process each mapping file sequentially in `terse` sub-mode; print a combined terminal summary. ~60% fewer total tokens for 4-doc runs. |
| `delta` | "delta", "re-run", "refresh", "only unconfirmed" | Skip entries whose `data_source` is already non-empty and does not contain `$TBD_`. Merge new suggestions into the existing `.suggested.yaml`. Report `N skipped, M suggested` in terminal summary. |

Mode-specific behavior overrides are listed in each step below where they apply.
A `batch` run runs `terse` automatically for every document in the batch.
```

---

## Change 2 — Step 2a: shape probe override for `terse`

Find the `### Step 2a — Shape probe` section. After the existing rule prose, append:

```markdown
**`terse` override:** Instead of the full table, print a single-line summary:
`Shape: <N> variables, <M> loops (<K> loop_fields), <P> registry entries, <Q> iterables`
Then proceed directly to Step 3.
```

---

## Change 3 — Step 3: reasoning format override for `terse`

Find `### Step 3 — Suggest mappings`. After the existing matching rules block, append:

```markdown
**`terse` reasoning format:** Write `reasoning` as a single quoted string, not a block scalar.
Format: `"<match-type> match → <velocity-path> (<registry-section>)"`

Examples:
- `"exact match → $data.policyNumber (system_paths)"`
- `"fuzzy match → $vehicle.data.year (Vehicle exposure fields)"`
- `"no match — nearest_label 'Claimant Name' has no registry counterpart"`

Do NOT write multi-line prose blocks in terse mode. One line per entry.
```

---

## Change 4 — Step 4b: review.md override for `terse`

Find `### Step 4b — Write the review file`. After the existing section list, append:

```markdown
**`terse` override:** Emit only:
1. The confidence summary table (high / medium / low counts)
2. The blockers table (one row per entry with `next_action` that is not `none`)
3. A one-line assumptions note: `N assumptions to confirm — see .suggested.yaml`

Omit: per-blocker narrative paragraphs, scope violation explanation prose, the "Done" section narrative, and the unrecognised-inputs prose block.
```

---

## Change 5 — Step 4: batch-mode multi-doc loop

Find `### Step 4 — Write the suggested mapping`. After the existing instructions, append:

```markdown
**`batch` mode:** Before writing any output, confirm the list of `.mapping.yaml` paths the user provided. Then loop:

```
for each mapping_file in [file1, file2, ...]:
    derive stem from mapping_file
    run Steps 1–4c for this stem (using the already-loaded registry)
    update lesson observations buffer (do not write skill-lessons.yaml yet)
end loop
write skill-lessons.yaml once after the loop (Step 4d)
print combined terminal summary (Step 5)
```

`path-registry.yaml` is read exactly once per batch invocation, before the loop.
```

---

## Change 6 — Step 4: delta-mode pre-filter

Find `### Step 4 — Write the suggested mapping`. In the same area, append:

```markdown
**`delta` mode:** Before Step 3 matching, partition entries:
- **confirmed**: `data_source` is non-empty AND does not contain `$TBD_` → skip; carry forward as-is into output
- **unconfirmed**: `data_source` is empty OR contains `$TBD_` → run normal matching

When writing `.suggested.yaml`, merge confirmed entries (unchanged) with newly suggested entries.
Step 5 terminal summary line: `Delta: N confirmed carried forward, M newly suggested`
```

---

## Change 7 — Step 5: terse terminal summary

Find `### Step 5 — Print the terminal summary`. After the existing format block, append:

```markdown
**`terse` override:** Condense to 5 lines:
```
Mode:     terse
Document: <stem>
Stats:    <high> high / <medium> medium / <low> low
Blockers: <N> (see <stem>.review.md)
Output:   <stem>.suggested.yaml  <stem>.review.md  <stem>.suggester-log.jsonl
```

**`batch` override:** After processing all documents, print a combined summary:
```
Batch complete — <N> documents processed
          high: <total>  medium: <total>  low: <total>
       blockers: <total> across all docs
```
```

---

## Acceptance criteria for Stage 1A

- [ ] `## Run modes` section exists in `SKILL.md` between "What this skill does" and "If a user asks what this skill does"
- [ ] Steps 2a, 3, 4, 4b, 5 each contain a `terse`/`batch`/`delta` override block
- [ ] No existing rule text is removed or reordered — overrides are additive only
- [ ] All added text is valid markdown (no broken tables, no unclosed code fences)
