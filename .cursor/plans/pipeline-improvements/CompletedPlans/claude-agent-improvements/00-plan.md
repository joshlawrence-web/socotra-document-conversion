# pipeline-orchestrator: Claude SDK Agent Improvements

## Status: READY TO IMPLEMENT

Invocation hardening is complete. This plan describes the next improvement:
replace the SKILL.md-only orchestrator with a real Python agent backed by the
Claude API with tool use.

---

## Read these files first (in order)

1. `.cursor/skills/pipeline-orchestrator/SKILL.md` — current orchestrator (pure AI instructions, 275 lines)
2. `.cursor/skills/html-to-velocity/scripts/convert.py` lines 1103–1149 — Leg 1 CLI flags
3. `scripts/leg2_fill_mapping.py` lines 1231–1257 — Leg 2 CLI flags
4. `registry/path-registry.yaml` — understand the registry format (first 30 lines is enough)
5. `SCHEMA.md` — artifact contracts (first 50 lines)

---

## Problem with current state

The `pipeline-orchestrator` skill is **pure AI instructions** (SKILL.md). The LLM reads those
instructions and acts as the orchestrator. This is brittle:

- The LLM can drift from the instructions across model updates
- It is Cursor-locked — can't run from CLI, CI, or scripts
- No real error handling for subprocess failures
- No testability — you can't unit-test instruction-following

The Python scripts that do the real work already exist and are solid:
- **Leg 1:** `.cursor/skills/html-to-velocity/scripts/convert.py` (1,206 lines)
- **Leg 2:** `scripts/leg2_fill_mapping.py` (1,441 lines)

The orchestration layer is the only part that is weak.

---

## What to build

A Python CLI agent (`scripts/agent.py`) backed by the Claude API with tool use.
The agent replaces the LLM-following-SKILL.md approach with a deterministic
tool-use loop. The existing scripts stay untouched — the agent just dispatches to them.

### Architecture

```
User (CLI or future Cursor shim)
        │
        ▼
  scripts/agent.py              ← NEW: Claude API agent with tool use
        │
        ├── tool: validate_inputs()
        ├── tool: show_preflight()
        ├── tool: list_candidates()   → filesystem scan
        ├── tool: run_leg1()          → subprocess: convert.py
        └── tool: run_leg2()          → subprocess: leg2_fill_mapping.py
```

---

## Implementation plan

### Step 1 — `scripts/agent_tools.py` (tool implementations)

Create this module. It contains the pure-Python functions that the agent's tool use
calls. No Claude API code here — just business logic.

**Functions to implement:**

```python
def validate_inputs(operation, input_html, mapping, registry, output, mode, terminology) -> dict:
    """
    Returns {"ok": True} or {"ok": False, "errors": [...], "missing": [...]}.
    Checks: files exist, correct extensions (.html, .mapping.yaml, .yaml),
    paths stay inside repo root (reject any path with .. that escapes),
    registry exists at given path or falls back to registry/path-registry.yaml.
    Does NOT read file contents — existence checks only.
    """

def list_candidates(output_dir="samples/output") -> list[str]:
    """
    Finds all *.mapping.yaml files under output_dir, sorted by mtime descending.
    Returns repo-relative paths.
    """

def build_preflight(operation, input_html, mapping, registry, output, mode, terminology) -> str:
    """
    Returns the formatted preflight block (the box with ╔═══╗ border) as a string.
    Lists every file that WILL be written. Does not write anything.
    """

def run_leg1(input_html, output_dir, registry, no_conditionals=False, auto_detect_loops=False) -> dict:
    """
    Runs: python3 .cursor/skills/html-to-velocity/scripts/convert.py
              <input_html> --output-dir <output_dir> --registry <registry>
    Returns {"ok": True, "artifacts": [...paths...], "stdout": ..., "stderr": ...}
    or      {"ok": False, "returncode": N, "stderr": ...}
    """

def run_leg2(mapping, registry, out, review_out, telemetry_log, mode,
             terminology=None, base_suggested=None) -> dict:
    """
    Runs: python3 scripts/leg2_fill_mapping.py
              --mapping <mapping> --registry <registry>
              --out <out> --review-out <review_out>
              --telemetry-log <telemetry_log>
              --mode <mode>
              [--terminology <terminology>]
              [--base-suggested <base_suggested>]
    Returns same shape as run_leg1.
    """
```

**Path resolution rules (implement in a shared helper):**
- Repo root = directory containing `.cursor/` (walk up from CWD until found)
- All input paths normalized to absolute before passing to subprocesses
- Reject any path where `Path(p).resolve()` is not under repo root

---

### Step 2 — `scripts/agent.py` (Claude API agent)

This is the main entry point. It creates a Claude client, registers tools, and runs
a multi-turn conversation loop.

**Tool definitions (Claude tool_use schema):**

Register these five tools with the Claude client:

```python
tools = [
    {
        "name": "validate_inputs",
        "description": "Validate all pipeline inputs before running. Returns errors and missing fields.",
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["leg1", "leg2", "leg1+leg2"]},
                "input_html": {"type": "string"},
                "mapping": {"type": ["string", "array"]},
                "registry": {"type": "string"},
                "output": {"type": "string"},
                "mode": {"type": "string", "enum": ["full", "terse", "delta", "batch"]},
                "terminology": {"type": "string"}
            },
            "required": ["operation"]
        }
    },
    {
        "name": "list_candidates",
        "description": "List available .mapping.yaml files for Leg 2 auto-discovery.",
        "input_schema": {
            "type": "object",
            "properties": {
                "output_dir": {"type": "string", "default": "samples/output"}
            }
        }
    },
    {
        "name": "show_preflight",
        "description": "Render and display the preflight summary. Must be called before run_leg1 or run_leg2.",
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {"type": "string"},
                "input_html": {"type": "string"},
                "mapping": {"type": ["string", "array"]},
                "registry": {"type": "string"},
                "output": {"type": "string"},
                "mode": {"type": "string"},
                "terminology": {"type": "string"}
            },
            "required": ["operation"]
        }
    },
    {
        "name": "run_leg1",
        "description": "Execute Leg 1: convert HTML to .vm + .mapping.yaml. Only call after PROCEED confirmed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "input_html": {"type": "string"},
                "output_dir": {"type": "string"},
                "registry": {"type": "string"},
                "no_conditionals": {"type": "boolean", "default": False},
                "auto_detect_loops": {"type": "boolean", "default": False}
            },
            "required": ["input_html", "output_dir", "registry"]
        }
    },
    {
        "name": "run_leg2",
        "description": "Execute Leg 2: suggest paths for .mapping.yaml. Only call after PROCEED confirmed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mapping": {"type": "string"},
                "registry": {"type": "string"},
                "out": {"type": "string"},
                "review_out": {"type": "string"},
                "telemetry_log": {"type": "string"},
                "mode": {"type": "string"},
                "terminology": {"type": "string"},
                "base_suggested": {"type": "string"}
            },
            "required": ["mapping", "registry", "out", "review_out", "telemetry_log", "mode"]
        }
    }
]
```

**System prompt for the agent:**

```python
SYSTEM_PROMPT = """
You are the pipeline-orchestrator agent for an HTML→Velocity template conversion pipeline.

## Hard gate
Only proceed if the user's message contains the token RUN_PIPELINE (case-insensitive).
If absent, print the refusal block and stop:

  This agent requires an explicit invocation token. Examples:
    RUN_PIPELINE leg1 input=samples/input/claim-form.html output=samples/output
    RUN_PIPELINE leg2 mode=terse mapping=samples/output/claim-form/claim-form.mapping.yaml
    RUN_PIPELINE leg1+leg2 input=samples/input/claim-form.html registry=registry/path-registry.yaml

## Workflow (follow in order, no skipping)
1. Parse inputs from the user's message (operation, mode, input, mapping, registry, output, terminology).
2. Call validate_inputs. If errors → report them and stop. If missing → ask ONLY for missing fields.
3. Call show_preflight. Display the result to the user.
4. Wait for PROCEED (or "yes, proceed") before calling any run_* tool.
   - CANCEL or "no" → print "Aborted. No files were written." and stop.
   - Any other reply → re-show preflight and wait again.
5. Call run_leg1 and/or run_leg2 depending on operation.
   - leg1+leg2: run Leg 1 first; derive mapping path from output; run Leg 2.
   - If any run_* returns ok=False: print full stderr and stop.
6. Print post-run summary listing all written artifacts.

## Constraints
- NEVER call run_leg1 or run_leg2 before PROCEED is confirmed.
- NEVER call show_preflight before validate_inputs passes.
- Default registry: registry/path-registry.yaml
- Default output: samples/output
- Default mode for leg1+leg2 when mode not specified: terse
"""
```

**Main loop (pseudocode):**

```python
def main():
    client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY from env
    messages = []

    # Get initial user message (argv or stdin)
    user_input = get_initial_input()  # sys.argv[1:] joined, or input()
    messages.append({"role": "user", "content": user_input})

    while True:
        response = client.messages.create(
            model="claude-opus-4-7",  # most capable for instruction-following
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
        )

        # Append assistant turn
        messages.append({"role": "assistant", "content": response.content})

        # Handle tool use
        tool_calls = [b for b in response.content if b.type == "tool_use"]
        if tool_calls:
            tool_results = []
            for tc in tool_calls:
                result = dispatch_tool(tc.name, tc.input)
                # Print tool output to terminal (user should see preflight, etc.)
                if tc.name == "show_preflight":
                    print(result["display"])
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": json.dumps(result),
                })
            messages.append({"role": "user", "content": tool_results})
            continue  # loop back for next assistant turn

        # No tool calls — text response
        text = next((b.text for b in response.content if b.type == "text"), "")
        print(text)

        # Check stop reason
        if response.stop_reason == "end_turn":
            # Need human input? Check if the agent is waiting for PROCEED
            if needs_human_input(text):
                user_reply = input("> ").strip()
                messages.append({"role": "user", "content": user_reply})
            else:
                break  # done
```

**CLI flags for `agent.py`:**

```
usage: python3 scripts/agent.py [MESSAGE] [--yes] [--model MODEL]

positional:
  MESSAGE     Full invocation string, e.g. "RUN_PIPELINE leg1 input=..."
              If omitted, reads from stdin (interactive mode).

optional:
  --yes       Auto-confirm PROCEED (CI/headless use)
  --model     Claude model ID (default: claude-opus-4-7)
```

---

### Step 3 — Update `pipeline-orchestrator/SKILL.md`

After agent.py is working, update the orchestrator skill to delegate to it.
Replace the 275-line instruction body with:

```markdown
# pipeline-orchestrator

This skill delegates to the Python agent. Run:

  python3 scripts/agent.py "RUN_PIPELINE <operation> [key=value ...]"

Or interactively:

  python3 scripts/agent.py

The agent enforces the RUN_PIPELINE gate and PROCEED confirmation.
See .cursor/plans/pipeline-improvements/claude-agent-improvements/00-plan.md
for full design context.
```

Do this AFTER agent.py is verified working — don't delete the SKILL.md instructions
until the agent is confirmed correct.

---

### Step 4 — Smoke test

Run these commands from repo root and verify output matches expected:

```bash
# Should print refusal block (no RUN_PIPELINE token)
python3 scripts/agent.py "convert the HTML file"

# Should print preflight, wait for PROCEED
python3 scripts/agent.py "RUN_PIPELINE leg1 input=samples/input/Simple-form.html output=samples/output"

# Should run end-to-end non-interactively
python3 scripts/agent.py "RUN_PIPELINE leg1+leg2 input=samples/input/Simple-form.html registry=registry/path-registry.yaml output=samples/output" --yes
```

Verify:
- Leg 1 output: `samples/output/Simple-form/Simple-form.vm`, `.mapping.yaml`, `.report.md`
- Leg 2 output: `samples/output/Simple-form/Simple-form.suggested.yaml`, `.review.md`, `.suggester-log.jsonl`

---

### Step 5 — Conformance check

Run the existing conformance suite to make sure nothing broke:

```bash
python3 conformance/run-conformance.py
```

Expected: 11/11 fixtures pass. The agent does not interact with conformance fixtures directly
(they test the scripts, not the agent), but verify the scripts still work standalone.

---

## Backing script CLI reference

### Leg 1 — `convert.py`

```bash
python3 .cursor/skills/html-to-velocity/scripts/convert.py \
    <input.html> \
    --output-dir <dir> \
    --registry <path-registry.yaml> \
    [--no-conditionals] \
    [--auto-detect-loops] \
    [--batch file1.html file2.html ...]
```

Outputs: `<output-dir>/<stem>/<stem>.vm`, `.mapping.yaml`, `.report.md`

### Leg 2 — `leg2_fill_mapping.py`

```bash
python3 scripts/leg2_fill_mapping.py \
    --mapping <stem.mapping.yaml> \
    --registry <path-registry.yaml> \
    --out <stem.suggested.yaml> \
    --review-out <stem.review.md> \
    --telemetry-log <stem.suggester-log.jsonl> \
    --mode <full|terse|delta|batch> \
    [--terminology <terminology.yaml>] \
    [--base-suggested <prior.suggested.yaml>]   # required for delta mode
```

---

## Artifact contracts (SCHEMA.md summary)

| Artifact | Schema version | Producer | Consumer |
|---|---|---|---|
| `<stem>.mapping.yaml` | v1.0 | Leg 1 | Leg 2 |
| `registry/path-registry.yaml` | v1.1 | extract_paths.py | Leg 2 |
| `<stem>.suggested.yaml` | v1.1 | Leg 2 | Human |
| `<stem>.review.md` | v1.1 | Leg 2 | Human |
| `<stem>.suggester-log.jsonl` | v1.0 | Leg 2 | Telemetry |

---

## Key constraints (never violate)

- `run_leg1` / `run_leg2` tool calls: NEVER before PROCEED confirmed
- `show_preflight`: NEVER before `validate_inputs` passes
- Registry default: `registry/path-registry.yaml` (repo-relative)
- Output default: `samples/output`
- Path safety: reject any path where `Path(p).resolve()` escapes repo root
- `leg1+leg2` mode default when mode not in invocation: `terse`
- Batch Leg 2: run `leg2_fill_mapping.py` once per mapping file sequentially

---

## Files NOT to touch

- `.cursor/skills/html-to-velocity/scripts/convert.py` — do not modify
- `scripts/leg2_fill_mapping.py` — do not modify
- `registry/path-registry.yaml` — do not modify
- `conformance/` — do not modify
- `.cursor/skills/html-to-velocity/SKILL.md` — do not modify yet (Step 3 is last)
- `.cursor/skills/mapping-suggester/SKILL.md` — do not modify

---

## Definition of done

- [x] `scripts/agent_tools.py` — all 5 functions implemented and tested standalone
- [x] `scripts/agent.py` — pure-Python orchestrator (no SDK needed), tool loop, CLI flags
- [x] Smoke test: refusal without token, preflight with token, end-to-end with --yes
- [x] `conformance/run-conformance.py` still passes (12/12)
- [x] `pipeline-orchestrator/SKILL.md` updated to delegate to agent.py

### Implementation note
`agent.py` was built as a pure-Python CLI instead of a Claude API agent.
The `RUN_PIPELINE key=value` format is structured enough that deterministic
parsing is more reliable than LLM parsing, and requires no ANTHROPIC_API_KEY.
