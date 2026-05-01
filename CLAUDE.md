# Velocity Converter — Claude instructions

## Converting HTML files to Velocity templates

When the user asks to convert HTML files, run the full pipeline. No explanation needed — just do it.

**Steps:**
1. List `samples/input/` to find available `.html` files
2. If ambiguous which files, ask. If they said "all" or "my files", run all of them.
3. Run from repo root: `python3 scripts/agent.py --yes "RUN_PIPELINE leg1+leg2+leg3 input=<path> registry=registry/path-registry.yaml output=samples/output"`
4. Report what was written. Tell the user to check `<stem>.leg3-report.md` for any unresolved tokens.

**Trigger phrases** (not exhaustive — use judgment):
- "convert my files"
- "convert X to velocity"
- "run the pipeline"
- "process my HTML"
- "generate the templates"
- "finalise the template"
- "write the final vm"
- "run leg 3"

**Leg 1 only** (HTML → `.vm` + `.mapping.yaml`, no path suggestions):
```
python3 scripts/agent.py --yes "RUN_PIPELINE leg1 input=<path> output=samples/output"
```

**Leg 2 only** (suggest paths for an existing mapping):
```
python3 scripts/agent.py --yes "RUN_PIPELINE leg2 mode=terse mapping=<path> registry=registry/path-registry.yaml"
```

**Leg 3 only** (finalise an existing `.suggested.yaml` into a `.final.vm`):
```
python3 scripts/agent.py --yes "RUN_PIPELINE leg3 suggested=<path>"
```

**Leg 3 high-confidence only** (substitute only `confidence: high` tokens; medium/low stay as `$TBD_*` and appear in a "Deferred" section of the report — use when fuzzy matches need human review before going live):
```
python3 scripts/agent.py --yes "RUN_PIPELINE leg3 suggested=<path> high_only=true"
```

**Full pipeline high-confidence only** (same as above but runs from HTML):
```
python3 scripts/agent.py --yes "RUN_PIPELINE leg1+leg2+leg3 input=<path> registry=registry/path-registry.yaml output=samples/output high_only=true"
```

**Trigger phrases for high-only mode** (use judgment):
- "only fill the high confidence fields"
- "skip the fuzzy matches"
- "don't substitute medium/low confidence"
- "I want to review the medium confidence first"

**Leg 1+2 only** (HTML → suggested paths, no final write — useful when many tokens are unresolved and need human review first):
```
python3 scripts/agent.py --yes "RUN_PIPELINE leg1+leg2 input=<path> registry=registry/path-registry.yaml output=samples/output"
```

**Output lands in** `samples/output/<stem>/`:
- Check `<stem>.leg3-report.md` first — it shows what resolved and what still needs work.
- `<stem>.final.vm` is the production template.
- `<stem>.review.md` (from Leg 2) is the path-confidence breakdown.

## Future: plugin / MCP migration

This CLAUDE.md approach only works because the user's CWD is this repo. When this becomes a plugin, migrate to an MCP server instead:

- Each pipeline operation (`leg1`, `leg2`, `leg1+leg2`, `leg3`, `leg1+leg2+leg3`) becomes an MCP tool
- Tool descriptions replace this CLAUDE.md — Claude uses them to decide when to invoke
- The CLAUDE.md trigger phrases above map directly to tool `description` fields
- `scripts/agent_tools.py` already has the business logic; MCP layer just wraps it

When the user asks to build the plugin, start here.
