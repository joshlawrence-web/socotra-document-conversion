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
python3 -m velocity_converter.agent "RUN_PIPELINE <operation> [key=value ...]"
```

Or with auto-confirm for CI/headless use:

```bash
python3 -m velocity_converter.agent --yes "RUN_PIPELINE <operation> [key=value ...]"
```

The agent enforces the `RUN_PIPELINE` gate, shows a preflight summary, requires
`PROCEED` confirmation, and dispatches to Leg 1 / Leg 2 / Leg 3 / Leg 4.

---

## Examples

```bash
# Leg 1 only
python3 -m velocity_converter.agent "RUN_PIPELINE leg1 input=samples/input/Simple-form.html output=samples/output"

# Leg 2 only
python3 -m velocity_converter.agent "RUN_PIPELINE leg2 mode=terse mapping=samples/output/Simple-form/Simple-form.mapping.yaml"

# End-to-end Leg 1 + Leg 2 (mode defaults to terse)
python3 -m velocity_converter.agent "RUN_PIPELINE leg1+leg2 input=samples/input/Simple-form.html registry=registry/path-registry.yaml output=samples/output"

# Full pipeline through Leg 3
python3 -m velocity_converter.agent "RUN_PIPELINE leg1+leg2+leg3 input=samples/input/Simple-form.html registry=registry/path-registry.yaml output=samples/output"

# Leg 4 only — generate DocumentDataSnapshotPlugin from existing .suggested.yaml
python3 -m velocity_converter.agent "RUN_PIPELINE leg4 suggested=samples/output/Simple-form/Simple-form.suggested.yaml"

# Full pipeline including Leg 4 (HTML → .vm + plugin)
python3 -m velocity_converter.agent "RUN_PIPELINE leg1+leg2+leg3+leg4 input=samples/input/Simple-form.html registry=registry/path-registry.yaml output=samples/output"

# Batch Leg 2
python3 -m velocity_converter.agent "RUN_PIPELINE leg2 mode=batch mapping=[samples/output/Simple-form/Simple-form.mapping.yaml, samples/output/Additional-form/Additional-form.mapping.yaml]"
```

---

## Invocation format

```
RUN_PIPELINE <operation> [key=value ...]
```

| Key | Required for | Default |
|---|---|---|
| `input` | leg1, leg1+leg2, leg1+leg2+leg3, leg1+leg2+leg3+leg4 | — |
| `mode` | leg2, leg1+leg2, leg1+leg2+leg3, leg1+leg2+leg3+leg4 | `terse` for combo ops |
| `mapping` | leg2 | — |
| `suggested` | leg3, leg4 | — |
| `registry` | all (optional) | `registry/path-registry.yaml` |
| `output` | all (optional) | `samples/output` |
| `terminology` | leg2 (optional) | — |
| `high_only` | leg3, leg1+leg2+leg3, leg1+leg2+leg3+leg4 (optional) | `false` |
| `compile_check` | leg4, leg1+leg2+leg3+leg4 (optional) | `true` |

---

## How it works

1. Parses `key=value` pairs from the invocation string
2. Validates inputs (existence, extensions, path safety)
3. Shows a preflight summary listing every file that will be written
4. Waits for `PROCEED` — no files touched until confirmed
5. Runs `convert.py` (Leg 1), `leg2_fill_mapping.py` (Leg 2), `leg3_substitute.py` (Leg 3), and/or `leg4_generate_plugin.py` (Leg 4) as subprocesses
6. Prints a post-run artifact list

For design context see:
`.cursor/plans/pipeline-improvements/CompletedPlans/claude-agent-improvements/00-plan.md`
