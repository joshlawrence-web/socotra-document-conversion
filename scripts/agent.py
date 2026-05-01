#!/usr/bin/env python3
"""Pipeline orchestrator — no API key required.

Parses a structured RUN_PIPELINE invocation, validates inputs, shows a preflight
summary, requires PROCEED confirmation, then dispatches to Leg 1 / Leg 2 scripts.

Usage:
    python3 scripts/agent.py "RUN_PIPELINE leg1 input=samples/input/Simple-form.html"
    python3 scripts/agent.py "RUN_PIPELINE leg1+leg2 input=samples/input/Simple-form.html"
    python3 scripts/agent.py --yes "RUN_PIPELINE leg1+leg2 input=samples/input/Simple-form.html"
    python3 scripts/agent.py          # interactive stdin mode
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agent_tools import (
    build_preflight,
    list_candidates,
    run_leg1,
    run_leg2,
    run_leg3,
    validate_inputs,
    _find_repo_root,
)

REFUSAL = """\
This agent requires an explicit invocation token. Examples:

  RUN_PIPELINE leg1 input=samples/input/claim-form.html output=samples/output
  RUN_PIPELINE leg2 mode=terse mapping=samples/output/claim-form/claim-form.mapping.yaml
  RUN_PIPELINE leg1+leg2 input=samples/input/claim-form.html registry=registry/path-registry.yaml
  RUN_PIPELINE leg3 suggested=samples/output/claim-form/claim-form.suggested.yaml
  RUN_PIPELINE leg1+leg2+leg3 input=samples/input/claim-form.html registry=registry/path-registry.yaml

Required per operation:
  leg1           : input=<file.html>
  leg2           : mode=<full|terse|delta|batch>  mapping=<file.mapping.yaml>
  leg1+leg2      : input=<file.html>  [mode defaults to terse]
  leg3           : suggested=<file.suggested.yaml>
  leg1+leg2+leg3 : input=<file.html>  [mode defaults to terse]

Optional for all: output=<dir>  registry=<path>  terminology=<path>
"""

VALID_OPS = {"leg1", "leg2", "leg1+leg2", "leg3", "leg1+leg2+leg3"}
VALID_MODES = {"full", "terse", "delta", "batch"}


def parse_invocation(text: str) -> dict | None:
    """
    Extract key=value pairs from a RUN_PIPELINE invocation string.
    Returns None if the RUN_PIPELINE token is absent.
    """
    if not re.search(r"run_pipeline", text, re.IGNORECASE):
        return None

    # Strip the token and leading operation from the string
    # Match: RUN_PIPELINE <operation> [key=value ...]
    m = re.search(
        r"run_pipeline\s+(leg1\+leg2\+leg3|leg1\+leg2|leg1|leg2\+leg3|leg3|leg2)(.*)",
        text,
        re.IGNORECASE,
    )
    if not m:
        return {}

    operation = m.group(1).lower()
    rest = m.group(2)

    # Parse key=value pairs; values may be quoted or bracket-list
    parsed: dict = {"operation": operation}
    for match in re.finditer(r'(\w+)=(\[.*?\]|"[^"]*"|\'[^\']*\'|\S+)', rest):
        key = match.group(1).lower()
        val = match.group(2).strip("\"'")
        if val.startswith("[") and val.endswith("]"):
            # list: [a, b, c]
            val = [v.strip().strip("\"'") for v in val[1:-1].split(",")]
        parsed[key] = val

    return parsed


def _derive_leg3_paths(suggested: str) -> dict:
    """Compute Leg 3 artifact paths from a .suggested.yaml path."""
    stem = Path(suggested).stem
    if stem.endswith(".suggested"):
        stem = stem[: -len(".suggested")]
    base = str(Path(suggested).parent)
    return {
        "out": f"{base}/{stem}.final.vm",
        "report_out": f"{base}/{stem}.leg3-report.md",
    }


def _derive_leg2_paths(input_html: str, output: str) -> dict:
    """Compute Leg 2 artifact paths from Leg 1 inputs."""
    stem = Path(input_html).stem
    base = f"{output}/{stem}"
    return {
        "mapping": f"{base}/{stem}.mapping.yaml",
        "out": f"{base}/{stem}.suggested.yaml",
        "review_out": f"{base}/{stem}.review.md",
        "telemetry_log": f"{base}/{stem}.suggester-log.jsonl",
    }


def _prompt_confirm(auto_yes: bool) -> bool:
    """Return True if the user confirms PROCEED."""
    if auto_yes:
        print("> PROCEED  (auto-confirmed via --yes)")
        return True
    try:
        reply = input("> ").strip()
    except EOFError:
        return False
    return reply.lower() in {"proceed", "yes", "yes, proceed", "y"}


def run(invocation: str, auto_yes: bool) -> int:
    parsed = parse_invocation(invocation)

    if parsed is None:
        print(REFUSAL)
        return 1

    if not parsed:
        print("Could not find a valid operation after RUN_PIPELINE.")
        print(REFUSAL)
        return 1

    operation = parsed.get("operation", "")
    if operation not in VALID_OPS:
        print(f"Unknown operation: {operation!r}")
        print(REFUSAL)
        return 1

    # Collect fields
    input_html = parsed.get("input") or parsed.get("input_html")
    mapping = parsed.get("mapping")
    registry = parsed.get("registry") or "registry/path-registry.yaml"
    output = parsed.get("output") or "samples/output"
    mode = parsed.get("mode")
    terminology = parsed.get("terminology")
    suggested = parsed.get("suggested")
    high_only = parsed.get("high_only", "").lower() in ("true", "1", "yes")

    # Apply defaults
    if operation in ("leg1+leg2", "leg1+leg2+leg3") and not mode:
        mode = "terse"

    # --- Validate ---
    result = validate_inputs(
        operation=operation,
        input_html=input_html,
        mapping=mapping,
        registry=registry,
        output=output,
        mode=mode,
        terminology=terminology,
        suggested=suggested,
    )

    if not result["ok"]:
        if result.get("errors"):
            print("Validation errors:")
            for e in result["errors"]:
                print(f"  • {e}")
        if result.get("missing"):
            missing = result["missing"]
            print(f"\nMissing required field(s): {', '.join(missing)}")
            if "mode" in missing:
                print("  mode must be one of: full, terse, delta, batch")
            if "mapping" in missing:
                candidates = list_candidates(output)
                if candidates:
                    print("  Available .mapping.yaml files:")
                    for c in candidates[:5]:
                        print(f"    {c}")
            print(f'\nAdd the missing fields and re-run, e.g.:')
            example_extra = " ".join(f"{f}=<value>" for f in missing)
            print(f"  RUN_PIPELINE {operation} {example_extra} ...")
        return 1

    # --- Preflight ---
    preflight = build_preflight(
        operation=operation,
        input_html=input_html,
        mapping=mapping,
        registry=registry,
        output=output,
        mode=mode,
        terminology=terminology,
        suggested=suggested,
        high_only=high_only,
    )
    print(preflight)

    if not _prompt_confirm(auto_yes):
        print("Aborted. No files were written.")
        return 0

    # --- Run ---
    repo_root = _find_repo_root()

    if operation in ("leg1", "leg1+leg2", "leg1+leg2+leg3"):
        print("\nRunning Leg 1…")
        r = run_leg1(
            input_html=input_html,
            output_dir=output,
            registry=registry,
        )
        if not r["ok"]:
            print(f"Leg 1 failed (rc={r['returncode']}):\n{r['stderr']}", file=sys.stderr)
            return 1
        print("Leg 1 artifacts:")
        for a in r.get("artifacts", []):
            print(f"  {a}")

    leg2_suggested_path: str | None = None

    if operation in ("leg2", "leg1+leg2", "leg1+leg2+leg3"):
        if operation in ("leg1+leg2", "leg1+leg2+leg3"):
            leg2_paths = _derive_leg2_paths(input_html, output)
        else:
            stem = Path(mapping).stem
            if stem.endswith(".mapping"):
                stem = stem[: -len(".mapping")]
            base = str(Path(mapping).parent)
            leg2_paths = {
                "mapping": mapping,
                "out": f"{base}/{stem}.suggested.yaml",
                "review_out": f"{base}/{stem}.review.md",
                "telemetry_log": f"{base}/{stem}.suggester-log.jsonl",
            }

        mappings = (
            [leg2_paths["mapping"]]
            if isinstance(leg2_paths["mapping"], str)
            else leg2_paths["mapping"]
        )
        if isinstance(mapping, list) and operation == "leg2":
            # batch: multiple explicit mappings
            mappings = mapping

        for m in mappings:
            stem = Path(m).stem
            if stem.endswith(".mapping"):
                stem = stem[: -len(".mapping")]
            base = str(Path(m).parent)
            this_suggested = leg2_paths.get("out") or f"{base}/{stem}.suggested.yaml"
            print(f"\nRunning Leg 2 for {m}…")
            r = run_leg2(
                mapping=m,
                registry=registry,
                out=this_suggested,
                review_out=leg2_paths.get("review_out") or f"{base}/{stem}.review.md",
                telemetry_log=leg2_paths.get("telemetry_log") or f"{base}/{stem}.suggester-log.jsonl",
                mode=mode,
                terminology=terminology,
            )
            if not r["ok"]:
                print(f"Leg 2 failed (rc={r['returncode']}):\n{r['stderr']}", file=sys.stderr)
                return 1
            print("Leg 2 artifacts:")
            for a in r.get("artifacts", []):
                print(f"  {a}")
            leg2_suggested_path = this_suggested

    if operation in ("leg3", "leg1+leg2+leg3"):
        if operation == "leg3":
            # suggested provided directly
            leg3_suggested = suggested
        else:
            # derived from leg2 output
            leg3_suggested = leg2_suggested_path

        if not leg3_suggested:
            print("ERROR: could not determine suggested.yaml path for Leg 3", file=sys.stderr)
            return 1

        leg3_paths = _derive_leg3_paths(leg3_suggested)
        print(f"\nRunning Leg 3 for {leg3_suggested}…")
        r = run_leg3(
            suggested=leg3_suggested,
            out=leg3_paths["out"],
            report_out=leg3_paths["report_out"],
            high_only=high_only,
        )
        if not r["ok"]:
            print(f"Leg 3 failed (rc={r['returncode']}):\n{r['stderr']}", file=sys.stderr)
            return 1
        print("Leg 3 artifacts:")
        for a in r.get("artifacts", []):
            print(f"  {a}")

    print("\nDone.")
    return 0


def _ask(prompt: str, default: str = "") -> str:
    display = f"{prompt} [{default}]: " if default else f"{prompt}: "
    try:
        val = input(display).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(0)
    return val or default


def guided_mode() -> str:
    """Interactive wizard — returns a RUN_PIPELINE invocation string."""
    repo_root = _find_repo_root()

    print("\n=== Velocity Converter — guided mode ===\n")

    # Operation
    print("What do you want to run?")
    print("  1) leg1          — HTML → .vm + .mapping.yaml")
    print("  2) leg2          — suggest paths for an existing .mapping.yaml")
    print("  3) leg1+leg2     — end-to-end through Leg 2 (default)")
    print("  4) leg3          — write final .vm from an existing .suggested.yaml")
    print("  5) leg1+leg2+leg3 — full pipeline\n")
    op_choice = _ask("Choose [1/2/3/4/5]", default="3")
    op_map = {
        "1": "leg1", "2": "leg2", "3": "leg1+leg2",
        "4": "leg3", "5": "leg1+leg2+leg3",
        "leg1": "leg1", "leg2": "leg2", "leg1+leg2": "leg1+leg2",
        "leg3": "leg3", "leg1+leg2+leg3": "leg1+leg2+leg3",
    }
    operation = op_map.get(op_choice, "leg1+leg2")

    parts = [f"RUN_PIPELINE {operation}"]

    # Input HTML (leg1 / leg1+leg2)
    if operation in ("leg1", "leg1+leg2"):
        candidates = sorted((repo_root / "samples" / "input").glob("*.html"))
        if candidates:
            print("\nAvailable input files:")
            for i, c in enumerate(candidates, 1):
                print(f"  {i}) {c.relative_to(repo_root)}")
            choice = _ask("Pick a number or type a path", default="1")
            if choice.isdigit() and 1 <= int(choice) <= len(candidates):
                input_html = str(candidates[int(choice) - 1].relative_to(repo_root))
            else:
                input_html = choice
        else:
            input_html = _ask("Path to input HTML file")
        parts.append(f"input={input_html}")

    # Mapping (leg2 only)
    if operation == "leg2":
        candidates = sorted((repo_root / "samples" / "output").rglob("*.mapping.yaml"))
        if candidates:
            print("\nAvailable mapping files:")
            for i, c in enumerate(candidates, 1):
                print(f"  {i}) {c.relative_to(repo_root)}")
            choice = _ask("Pick a number or type a path", default="1")
            if choice.isdigit() and 1 <= int(choice) <= len(candidates):
                mapping = str(candidates[int(choice) - 1].relative_to(repo_root))
            else:
                mapping = choice
        else:
            mapping = _ask("Path to .mapping.yaml file")
        parts.append(f"mapping={mapping}")

    # Suggested (leg3 only)
    if operation == "leg3":
        candidates = sorted((repo_root / "samples" / "output").rglob("*.suggested.yaml"))
        if candidates:
            print("\nAvailable suggested files:")
            for i, c in enumerate(candidates, 1):
                print(f"  {i}) {c.relative_to(repo_root)}")
            choice = _ask("Pick a number or type a path", default="1")
            if choice.isdigit() and 1 <= int(choice) <= len(candidates):
                suggested = str(candidates[int(choice) - 1].relative_to(repo_root))
            else:
                suggested = choice
        else:
            suggested = _ask("Path to .suggested.yaml file")
        parts.append(f"suggested={suggested}")

    # Mode (leg2 / leg1+leg2 / leg1+leg2+leg3)
    if operation in ("leg2", "leg1+leg2", "leg1+leg2+leg3"):
        print("\nSuggester mode:")
        print("  terse — concise review.md (default)")
        print("  full  — detailed reasoning per field")
        print("  delta — only unresolved $TBD_ fields")
        mode_val = _ask("Mode", default="terse")
        parts.append(f"mode={mode_val}")

    # Optional overrides
    output = _ask("\nOutput directory", default="samples/output")
    if output != "samples/output":
        parts.append(f"output={output}")

    registry = _ask("Registry path", default="registry/path-registry.yaml")
    if registry != "registry/path-registry.yaml":
        parts.append(f"registry={registry}")

    invocation = " ".join(parts)
    print(f"\nInvocation: {invocation}\n")
    return invocation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message", nargs="*", help="Invocation string (omit for stdin)")
    parser.add_argument("--yes", action="store_true", help="Auto-confirm PROCEED (CI/headless)")
    parser.add_argument("--guided", action="store_true", help="Interactive wizard mode")
    args = parser.parse_args()

    if args.guided or (not args.message and sys.stdin.isatty()):
        invocation = guided_mode()
    elif args.message:
        invocation = " ".join(args.message)
    else:
        print("Enter pipeline invocation:")
        invocation = sys.stdin.read().strip()

    if not invocation:
        print("No input provided.", file=sys.stderr)
        sys.exit(1)

    sys.exit(run(invocation, auto_yes=args.yes))


if __name__ == "__main__":
    main()
