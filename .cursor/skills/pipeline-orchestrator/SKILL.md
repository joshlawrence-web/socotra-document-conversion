---
name: pipeline-orchestrator
description: >
  The ONLY entry point for running the HTML → Velocity pipeline in demos and team use.
  Trigger ONLY when the user's message contains the token RUN_PIPELINE (case-insensitive).
  For any other message, provide information only — do not run the pipeline.
---

# pipeline-orchestrator

This skill delegates to the Python agent. Run from the repo root:

```bash
python3 scripts/agent.py "RUN_PIPELINE <operation> [key=value ...]"
```

Or with auto-confirm for CI/headless use:

```bash
python3 scripts/agent.py --yes "RUN_PIPELINE <operation> [key=value ...]"
```

The agent enforces the `RUN_PIPELINE` gate, shows a preflight summary, requires
`PROCEED` confirmation, and dispatches to Leg 1 / Leg 2.

---

## Examples

```bash
# Leg 1 only
python3 scripts/agent.py "RUN_PIPELINE leg1 input=samples/input/claim-form.html output=samples/output"

# Leg 2 only
python3 scripts/agent.py "RUN_PIPELINE leg2 mode=terse mapping=samples/output/claim-form/claim-form.mapping.yaml"

# End-to-end (mode defaults to terse)
python3 scripts/agent.py "RUN_PIPELINE leg1+leg2 input=samples/input/claim-form.html"

# Batch Leg 2
python3 scripts/agent.py "RUN_PIPELINE leg2 mode=batch mapping=[samples/output/a/a.mapping.yaml, samples/output/b/b.mapping.yaml]"
```

---

## Invocation format

```
RUN_PIPELINE <operation> [key=value ...]
```

| Key | Required for | Default |
|---|---|---|
| `input` | leg1, leg1+leg2 | — |
| `mode` | leg2, leg1+leg2 | `terse` for leg1+leg2 |
| `mapping` | leg2 | — |
| `registry` | all (optional) | `registry/path-registry.yaml` |
| `output` | all (optional) | `samples/output` |
| `terminology` | leg2 (optional) | — |

---

## How it works

1. Parses `key=value` pairs from the invocation string
2. Validates inputs (existence, extensions, path safety)
3. Shows a preflight summary listing every file that will be written
4. Waits for `PROCEED` — no files touched until confirmed
5. Runs `convert.py` (Leg 1) and/or `leg2_fill_mapping.py` (Leg 2) as subprocesses
6. Prints a post-run artifact list

For design context see:
`.cursor/plans/pipeline-improvements/claude-agent-improvements/00-plan.md`
