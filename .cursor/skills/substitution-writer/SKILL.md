---
name: substitution-writer
description: >
  Given a Leg 1 `.vm` template (with `$TBD_*` placeholders and `#if` guards)
  and a Leg 2 `.suggested.yaml` (with confirmed `data_source` paths), runs
  `scripts/leg3_substitute.py` to produce a production-ready `.final.vm` and
  a human-editable `.leg3-report.md` remedy form.
  Use whenever the user wants to finalise a template, write out resolved paths,
  generate the final Velocity file, or run Leg 3.
  Trigger on phrases like "finalise the template", "write the final vm",
  "run leg 3", "substitute the placeholders", "generate the final template",
  or any reference to producing a `.final.vm`.
---

# substitution-writer

## For demos and team use: go through `pipeline-orchestrator`

This is an internal pipeline tool. If the user's message does **not** contain
`RUN_PIPELINE` (case-insensitive), **do not run the substitution writer**.
Instead print:

```
For demos and production runs, please use the pipeline-orchestrator skill.

Quick start:
  RUN_PIPELINE leg3 suggested=samples/output/<stem>/<stem>.suggested.yaml

  RUN_PIPELINE leg1+leg2+leg3 input=samples/input/<file>.html registry=registry/path-registry.yaml

See .cursor/skills/pipeline-orchestrator/SKILL.md for the full invocation format.
```

Then stop. Questions about what this skill does are fine to answer — just don't execute.

If `RUN_PIPELINE` IS present in the message, continue with normal execution below.

---

## What this skill does

Leg 3 of the HTML → Velocity pipeline. Takes the two upstream artifacts:

1. **`<stem>.vm`** — produced by `html-to-velocity` (Leg 1). Contains every
   `$TBD_*` placeholder and `#if($TBD_*)...#end` guard wrapping each one.

2. **`<stem>.suggested.yaml`** — produced by `mapping-suggester` (Leg 2).
   Contains the reviewed `data_source` paths for each placeholder, plus
   `confidence` and `reasoning`.

Outputs (all written to `samples/output/<stem>/`):

- **`<stem>.final.vm`** — the production-ready Velocity template.
  Resolved `$TBD_*` tokens replaced with real paths. `#if($TBD_*)...#end`
  guards stripped (DD-1). Unresolved tokens left as `$TBD_*` (DD-2).

- **`<stem>.leg3-report.md`** — the remedy form. Lists resolved and unresolved
  tokens with labels, line numbers, Leg 2 notes, action guidance, and
  ready-to-fill YAML blocks. This document is the handoff to human reviewers
  when tokens remain unresolved — they fill it in, update the `.suggested.yaml`,
  and re-run Leg 3.

---

## Design decisions

| Code | Decision | Rationale |
|---|---|---|
| DD-1 | `#if($TBD_*)...#end` guards stripped from all variables | Readability over null-safety. Guards can be added manually or by a future leg once the full data contract is known. |
| DD-2 | Unresolved `$TBD_*` tokens preserved as-is | Keeps the template parseable; makes unresolved tokens visible at a glance. |
| DD-3 | Lenient mode — substitute what can be resolved, report the rest | Never abort on low-confidence or empty data_source entries. |

---

## How to run

Leg 3 is always run via `scripts/agent.py`. Do **not** call
`scripts/leg3_substitute.py` directly when inside a pipeline context.

### Leg 3 only (finalise an existing .suggested.yaml)

```
RUN_PIPELINE leg3 suggested=samples/output/<stem>/<stem>.suggested.yaml
```

### Full end-to-end (HTML → final .vm in one shot)

```
RUN_PIPELINE leg1+leg2+leg3 input=samples/input/<file>.html registry=registry/path-registry.yaml
```

---

## What the output looks like

### `<stem>.final.vm`

Identical to the Leg 1 `.vm` except:
- `#if($TBD_X)` opener lines removed (DD-1)
- `#end` closer lines for those guards removed (DD-1)
- Resolved `$TBD_X` tokens replaced with their `data_source` values
- Unresolved `$TBD_X` tokens left in place (DD-2)
- `#foreach($TBD_X in $TBD_COLLECTION)` replaced with real directive when the
  loop had a resolved `foreach` entry in the suggested.yaml

### `<stem>.leg3-report.md`

Sections:
1. **Status header** — COMPLETE / PARTIAL / BLOCKED
2. **Resolved** — table of substituted tokens with confidence levels
3. **Unresolved** — one sub-section per token, with label, source line,
   Leg 2 note, action guidance, and a YAML snippet the reviewer fills in
4. **Next steps** — the exact `RUN_PIPELINE` command to re-run after fixes

---

## Unresolved token workflow

When tokens remain unresolved after Leg 3:

1. Open `<stem>.leg3-report.md`
2. For each unresolved token, find the correct Velocity path (check the
   registry, your plugin, or the Socotra config)
3. Update `data_source` in `<stem>.suggested.yaml` for that entry
4. Re-run: `RUN_PIPELINE leg3 suggested=<path>`

If the correct path does not exist in the registry yet:
- Add the field to your Socotra config
- Re-run `extract_paths.py` to regenerate the registry
- Re-run Leg 2 to update the suggested mapping
- Then re-run Leg 3

---

## Important constraints

- **Never invent Velocity paths.** The only valid source of paths is the
  registry (`path-registry.yaml`) or an explicit human edit. If a path is not
  in the registry, leave the token as `$TBD_*` and report it as unresolved.
- **Never overwrite `.vm`.** Output always goes to `<stem>.final.vm`.
  The Leg 1 `.vm` is preserved as the original intermediate artifact.
- **Preserve unknown keys.** Any key in `.suggested.yaml` not recognised by
  this skill passes through to the report's metadata unchanged.
