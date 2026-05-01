# Pipeline Demo Runbook

A teammate can run Leg 1 + Leg 2 in under 5 minutes by copy-pasting from this doc.

---

## Prerequisites

1. Repo cloned and open in Cursor.
2. Python 3 available. Install dependencies if needed:
   ```bash
   pip install beautifulsoup4 pyyaml --break-system-packages
   ```
3. The `pipeline-orchestrator` skill is in `.cursor/skills/pipeline-orchestrator/SKILL.md`.
   Cursor will load it automatically when you open this repo.

---

## Demo invocations

### Option 1 — Leg 1 only (convert HTML to Velocity template)

```
RUN_PIPELINE leg1 input=samples/input/Simple-form.html output=samples/output
```

What you get:
- `samples/output/Simple-form/Simple-form.vm` — Velocity template with `$TBD_*` placeholders
- `samples/output/Simple-form/Simple-form.mapping.yaml` — variable catalogue (blank `data_source` fields)
- `samples/output/Simple-form/Simple-form.report.md` — sanity report

### Option 2 — Leg 2 only (suggest paths for an existing mapping)

```
RUN_PIPELINE leg2 mode=terse mapping=samples/output/Simple-form/Simple-form.mapping.yaml registry=registry/path-registry.yaml
```

What you get:
- `samples/output/Simple-form/Simple-form.suggested.yaml` — suggested `$data.*` paths
- `samples/output/Simple-form/Simple-form.review.md` — human review report (start here)
- `samples/output/Simple-form/Simple-form.suggester-log.jsonl` — telemetry

### Option 3 — End-to-end (Leg 1 then Leg 2 in one shot)

```
RUN_PIPELINE leg1+leg2 input=samples/input/Simple-form.html registry=registry/path-registry.yaml output=samples/output
```

Leg 1 runs first, then Leg 2 (terse mode) runs on the output automatically.

### Option 4 — Batch Leg 2

```
RUN_PIPELINE leg2 mode=batch mapping=[samples/output/Simple-form/Simple-form.mapping.yaml, samples/output/Additional-form/Additional-form.mapping.yaml] registry=registry/path-registry.yaml
```

---

## What "good output" looks like

After Leg 2 runs, open `<stem>.review.md`. A healthy run shows:

- **§1 High confidence** — most fields matched; no action needed.
- **§3 Blockers** — zero or one or two items with `$TBD_` still present; these need human resolution before Leg 3.
- **§4 Assumptions to confirm** — medium-confidence suggestions; read the `reasoning` and either accept or override.

Open `<stem>.suggested.yaml` to see the full suggestions. Edit `data_source:` fields for any overrides, then run Leg 3 (Substitution Writer) to produce the final renderable `.vm`.

---

## Safety story: why `RUN_PIPELINE` + `PROCEED` exist

During demos, it's easy to accidentally trigger a pipeline run by asking a question
like "can you suggest paths for this?" or "what would happen if I ran the converter?".
Without a guard, the pipeline would silently write files and consume tokens.

The two-step handshake prevents this:

1. **`RUN_PIPELINE` token** — a deliberate signal that you want execution, not explanation.
2. **`PROCEED` confirmation** — lets you review the exact files that will be written before anything happens.

**Example of a vague request that does NOT run:**

> "run the suggester on the Simple-form mapping"

The orchestrator will respond with the refusal block and show the correct one-liner to copy-paste. No files are touched.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Error: input file not found` | Check the path is repo-relative and the file exists in `samples/input/` |
| `Error: registry not found` | Regenerate with `python3 scripts/extract_paths.py --config-dir socotra-config/` |
| Script exits non-zero | Read the stderr output printed by the orchestrator; fix the underlying issue |
| Mode not recognized | Use: `full`, `terse`, `delta`, or `batch` |
