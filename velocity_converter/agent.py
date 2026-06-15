#!/usr/bin/env python3
"""Pipeline orchestrator — no API key required.

Parses a structured RUN_PIPELINE invocation, validates inputs, shows a preflight
summary, requires PROCEED confirmation, then dispatches to Leg 1 / Leg 2 / Leg 3 / Leg 4 scripts.

Usage:
    python3 -m velocity_converter.agent "RUN_PIPELINE leg1 input=samples/input/Simple-form.html"
    python3 -m velocity_converter.agent "RUN_PIPELINE leg1+leg2 input=samples/input/Simple-form.html"
    python3 -m velocity_converter.agent "RUN_PIPELINE leg3 suggested=samples/output/Simple-form/Simple-form.mapping.yaml"
    python3 -m velocity_converter.agent "RUN_PIPELINE leg1+leg2+leg3 input=samples/input/Simple-form.html registry=registry/path-registry.yaml"
    python3 -m velocity_converter.agent "RUN_PIPELINE leg4 suggested=samples/output/Simple-form/Simple-form.mapping.yaml"
    python3 -m velocity_converter.agent "RUN_PIPELINE leg1+leg2+leg3+leg4 input=samples/input/Simple-form.html registry=registry/path-registry.yaml"
    python3 -m velocity_converter.agent --yes "RUN_PIPELINE leg1+leg2+leg3+leg4 input=samples/input/Simple-form.html"
    python3 -m velocity_converter.agent          # interactive stdin mode
"""

import argparse
import re
import sys
from pathlib import Path

from velocity_converter.agent_tools import (
    build_preflight,
    get_intermediate_paths,
    list_candidates,
    run_leg0,
    run_leg1,
    run_leg2,
    run_leg3,
    run_leg4,
    run_list_paths,
    validate_inputs,
    _find_repo_root,
    _FULL_PIPELINE_OPS,
)

REFUSAL = """\
This agent requires an explicit invocation token. Examples:

  RUN_PIPELINE leg0 input=samples/input/policy-form.docx output=samples/output
  RUN_PIPELINE leg0+leg2+leg3 input=samples/input/policy-form.docx registry=registry/path-registry.yaml output=samples/output
  RUN_PIPELINE leg1 input=samples/input/Simple-form.html output=samples/output
  RUN_PIPELINE leg2 mapping=samples/output/Simple-form/Simple-form.mapping.yaml
  RUN_PIPELINE leg2+leg3 mapping=samples/output/Simple-form/Simple-form.mapping.yaml registry=registry/path-registry.yaml
  RUN_PIPELINE leg1+leg2 input=samples/input/Simple-form.html registry=registry/path-registry.yaml
  RUN_PIPELINE leg3 suggested=samples/output/Simple-form/Simple-form.mapping.yaml
  RUN_PIPELINE leg1+leg2+leg3 input=samples/input/Simple-form.html registry=registry/path-registry.yaml
  RUN_PIPELINE leg4 suggested=samples/output/Simple-form/Simple-form.mapping.yaml
  RUN_PIPELINE leg1+leg2+leg3+leg4 input=samples/input/Simple-form.html registry=registry/path-registry.yaml
  RUN_PIPELINE list_paths registry=registry/path-registry.yaml
  RUN_PIPELINE list_paths registry=registry/path-registry.yaml out=samples/output/field-catalog.md

Required per operation:
  legminus1          : input=<file.docx|file.pdf|file.html>
  legminus1_apply    : review=<file.path-review.md>
  leg0               : input=<file.docx|file.pdf>
  leg0+leg2+leg3     : input=<file.docx|file.pdf>
  leg1               : input=<file.html>
  leg2               : mapping=<file.mapping.yaml>
  leg2+leg3          : mapping=<file.mapping.yaml>
  leg1+leg2          : input=<file.html>
  leg3               : suggested=<file.mapping.yaml>
  leg1+leg2+leg3     : input=<file.html>
  leg4               : suggested=<file.mapping.yaml>
  leg1+leg2+leg3+leg4: input=<file.html>

  list_paths         : registry=<path> (optional)  out=<file> (optional)
Optional for all:           output=<dir>  registry=<path>  terminology=<path>
Optional for leg4 variants: compile_check=false  (skip javac after generating plugin)
"""

VALID_OPS = {"legminus1", "legminus1_apply", "leg0", "leg0+leg2+leg3", "leg1", "leg2", "leg2+leg3", "leg1+leg2", "leg3", "leg1+leg2+leg3", "leg4", "leg1+leg2+leg3+leg4", "list_paths"}


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
        r"run_pipeline\s+(list_paths|legminus1_apply|legminus1|leg0\+leg2\+leg3|leg1\+leg2\+leg3\+leg4|leg1\+leg2\+leg3|leg1\+leg2|leg0|leg1|leg2\+leg3|leg3|leg2|leg4)(.*)",
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
    """Compute Leg 3 artifact paths from a .mapping.yaml or .suggested.yaml path."""
    stem = Path(suggested).stem
    for sfx in (".suggested", ".mapping"):
        if stem.endswith(sfx):
            stem = stem[: -len(sfx)]
            break
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
        "out": f"{base}/{stem}.mapping.yaml",
        "review_out": f"{base}/{stem}.review.md",
        "telemetry_log": None,
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
    terminology = parsed.get("terminology")
    suggested = parsed.get("suggested")
    compile_check_raw = parsed.get("compile_check", "true")
    compile_check = compile_check_raw.lower() not in ("false", "0", "no")
    keep_intermediates = parsed.get("keep", "").lower() == "intermediates"

    # --- Leg -1 fast-path (registry-only path resolution, no preflight needed) ---
    if operation == "legminus1":
        from velocity_converter.agent_tools import run_legminus1
        if not input_html:
            print("Missing required field: input=<doc.docx|.pdf|.html>", file=sys.stderr)
            return 1
        r = run_legminus1(input_path=input_html, registry=registry, output_dir=output)
        if not r["ok"]:
            print(f"Leg -1 failed (rc={r['returncode']}):\n{r['stderr']}", file=sys.stderr)
            return 1
        print(r.get("stdout", ""))
        print("Leg -1 artifacts:")
        for a in r.get("artifacts", []):
            print(f"  {a}")
        return 0

    if operation == "legminus1_apply":
        from velocity_converter.agent_tools import run_legminus1_apply
        review = parsed.get("review")
        if not review:
            print("Missing required field: review=<path.path-review.md>", file=sys.stderr)
            return 1
        r = run_legminus1_apply(review=review, output_dir=parsed.get("output"))
        if not r["ok"]:
            print(f"Leg -1 apply failed (rc={r['returncode']}):\n{r['stderr']}", file=sys.stderr)
            return 1
        print(r.get("stdout", ""))
        print("Leg -1 apply artifacts:")
        for a in r.get("artifacts", []):
            print(f"  {a}")
        return 0

    # --- list_paths fast-path (no preflight / PROCEED needed) ---
    if operation == "list_paths":
        out_path = parsed.get("out") or "samples/output/field-catalog.md"
        try:
            run_list_paths(registry_path=registry, out_path=out_path)
        except Exception as exc:
            print(f"list_paths failed: {exc}", file=sys.stderr)
            return 1
        print(f"Field catalog written to {out_path}")
        return 0

    # --- Validate ---
    result = validate_inputs(
        operation=operation,
        input_html=input_html,
        mapping=mapping,
        registry=registry,
        output=output,
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
        terminology=terminology,
        suggested=suggested,
        compile_check=compile_check,
        keep_intermediates=keep_intermediates,
    )
    print(preflight)

    if not _prompt_confirm(auto_yes):
        print("Aborted. No files were written.")
        return 0

    # --- Run ---
    repo_root = _find_repo_root()

    leg0_mapping_path: str | None = None

    if operation in ("leg0", "leg0+leg2+leg3"):
        print("\nRunning Leg 0…")
        from pathlib import Path as _Path
        stem = _Path(input_html).stem
        leg0_out_dir = f"{output}/{stem}"
        r = run_leg0(input_path=input_html, output_dir=leg0_out_dir)
        if not r["ok"]:
            print(f"Leg 0 failed (rc={r['returncode']}):\n{r['stderr']}", file=sys.stderr)
            return 1
        print("Leg 0 artifacts:")
        for a in r.get("artifacts", []):
            print(f"  {a}")
        leg0_mapping_path = f"{leg0_out_dir}/{stem}.mapping.yaml"
        # leg0+leg2+leg3: seed the .vm base that Leg 3 expects from the annotated HTML
        if operation == "leg0+leg2+leg3":
            import shutil as _shutil
            _annotated = f"{leg0_out_dir}/{stem}.annotated.html"
            _vm_seed = f"{leg0_out_dir}/{stem}.vm"
            _shutil.copy2(_annotated, _vm_seed)

    # leg2+leg3: seed the .vm base Leg 3 substitutes against from the sibling
    # .annotated.html. A docx-origin mapping always has an .annotated.html (Leg 0)
    # and that is the authoritative, freshly-regenerated base — so always refresh
    # the .vm from it, mirroring the leg0+leg2+leg3 copy above. (Refreshing only
    # "if the .vm is missing" lets a stale .vm from an earlier run shadow an
    # updated doc, leaving old $TBD_ tokens in the final template.) HTML/Leg 1
    # flows have no .annotated.html, so their real Leg 1 .vm is left untouched.
    if operation == "leg2+leg3" and mapping:
        import shutil as _shutil
        _m_stem = Path(mapping).stem
        if _m_stem.endswith(".mapping"):
            _m_stem = _m_stem[: -len(".mapping")]
        _m_base = Path(mapping).parent
        _vm_seed = _m_base / f"{_m_stem}.vm"
        _annotated = _m_base / f"{_m_stem}.annotated.html"
        if _annotated.exists():
            _shutil.copy2(str(_annotated), str(_vm_seed))

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

    if operation in ("leg2", "leg2+leg3", "leg0+leg2+leg3", "leg1+leg2", "leg1+leg2+leg3"):
        if operation == "leg0+leg2+leg3":
            # Leg 0 wrote {stem}.mapping.yaml — enrich it in place
            m_path = leg0_mapping_path
            stem = Path(m_path).stem
            if stem.endswith(".mapping"):
                stem = stem[: -len(".mapping")]
            base = str(Path(m_path).parent)
            leg2_paths = {
                "mapping": m_path,
                "out": m_path,
                "review_out": f"{base}/{stem}.review.md",
                "telemetry_log": None,
            }
        elif operation in ("leg1+leg2", "leg1+leg2+leg3"):
            leg2_paths = _derive_leg2_paths(input_html, output)
        else:  # leg2 or leg2+leg3
            stem = Path(mapping).stem
            if stem.endswith(".mapping"):
                stem = stem[: -len(".mapping")]
            base = str(Path(mapping).parent)
            leg2_paths = {
                "mapping": mapping,
                "out": f"{base}/{stem}.mapping.yaml",
                "review_out": f"{base}/{stem}.review.md",
                "telemetry_log": None,
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
            this_suggested = leg2_paths.get("out") or f"{base}/{stem}.mapping.yaml"
            print(f"\nRunning Leg 2 for {m}…")
            r = run_leg2(
                mapping=m,
                registry=registry,
                out=this_suggested,
                review_out=leg2_paths.get("review_out") or f"{base}/{stem}.review.md",
                telemetry_log=leg2_paths.get("telemetry_log"),
                terminology=terminology,
            )
            if not r["ok"]:
                print(f"Leg 2 failed (rc={r['returncode']}):\n{r['stderr']}", file=sys.stderr)
                return 1
            print("Leg 2 artifacts:")
            for a in r.get("artifacts", []):
                print(f"  {a}")
            leg2_suggested_path = this_suggested

    if operation in ("leg3", "leg2+leg3", "leg0+leg2+leg3", "leg1+leg2+leg3", "leg1+leg2+leg3+leg4"):
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
        )
        if not r["ok"]:
            print(f"Leg 3 failed (rc={r['returncode']}):\n{r['stderr']}", file=sys.stderr)
            return 1
        print("Leg 3 artifacts:")
        for a in r.get("artifacts", []):
            print(f"  {a}")

    if operation in ("leg4", "leg1+leg2+leg3+leg4"):
        if operation == "leg4":
            leg4_suggested = suggested
        else:
            leg4_suggested = leg2_suggested_path

        if not leg4_suggested:
            print("ERROR: could not determine suggested.yaml path for Leg 4", file=sys.stderr)
            return 1

        print(f"\nRunning Leg 4 for {leg4_suggested}…")
        r = run_leg4(
            suggested=leg4_suggested,
            compile_check=compile_check,
        )
        if not r["ok"]:
            print(f"Leg 4 failed (rc={r['returncode']}):\n{r.get('stderr', '')}", file=sys.stderr)
            if r.get("stdout"):
                print(r["stdout"], file=sys.stderr)
            return 1
        print("Leg 4 artifacts:")
        for a in r.get("artifacts", []):
            print(f"  {a}")

    if (not keep_intermediates) and operation in _FULL_PIPELINE_OPS:
        to_delete = get_intermediate_paths(
            operation=operation,
            input_html=input_html,
            output=output,
            leg2_suggested=leg2_suggested_path,
        )
        removed = []
        for p in to_delete:
            if p.exists():
                p.unlink()
                removed.append(str(p.resolve().relative_to(repo_root)))
        if removed:
            print("\nRemoved intermediates:")
            for f in removed:
                print(f"  rm {f}")

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
    print("  1) leg1               — HTML → .vm + .mapping.yaml")
    print("  2) leg2               — suggest paths for an existing .mapping.yaml")
    print("  3) leg1+leg2          — end-to-end through Leg 2 (default)")
    print("  4) leg2+leg3          — suggest paths + write final .vm from an existing .mapping.yaml")
    print("  5) leg3               — write final .vm from an existing .mapping.yaml")
    print("  6) leg1+leg2+leg3     — full pipeline")
    print("  7) leg4               — generate DocumentDataSnapshotPlugin from .mapping.yaml")
    print("  8) leg1+leg2+leg3+leg4 — full pipeline including plugin\n")
    op_choice = _ask("Choose [1/2/3/4/5/6/7/8]", default="3")
    op_map = {
        "1": "leg1", "2": "leg2", "3": "leg1+leg2",
        "4": "leg2+leg3", "5": "leg3", "6": "leg1+leg2+leg3",
        "7": "leg4", "8": "leg1+leg2+leg3+leg4",
        "leg1": "leg1", "leg2": "leg2", "leg1+leg2": "leg1+leg2",
        "leg2+leg3": "leg2+leg3", "leg3": "leg3", "leg1+leg2+leg3": "leg1+leg2+leg3",
        "leg4": "leg4", "leg1+leg2+leg3+leg4": "leg1+leg2+leg3+leg4",
    }
    operation = op_map.get(op_choice, "leg1+leg2")

    parts = [f"RUN_PIPELINE {operation}"]

    # Input HTML (leg1 / leg1+leg2 / combos)
    if operation in ("leg1", "leg1+leg2", "leg1+leg2+leg3", "leg1+leg2+leg3+leg4"):
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

    # Mapping (leg2 / leg2+leg3)
    if operation in ("leg2", "leg2+leg3"):
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

    # Suggested (leg3 / leg4 standalone only)
    if operation in ("leg3", "leg4"):
        candidates = sorted(
            list((repo_root / "samples" / "output").rglob("*.mapping.yaml")) +
            list((repo_root / "samples" / "output").rglob("*.suggested.yaml"))
        )
        if candidates:
            print("\nAvailable mapping files:")
            for i, c in enumerate(candidates, 1):
                print(f"  {i}) {c.relative_to(repo_root)}")
            choice = _ask("Pick a number or type a path", default="1")
            if choice.isdigit() and 1 <= int(choice) <= len(candidates):
                suggested = str(candidates[int(choice) - 1].relative_to(repo_root))
            else:
                suggested = choice
        else:
            suggested = _ask("Path to .mapping.yaml file")
        parts.append(f"suggested={suggested}")

    # Compile check (leg4 / combos with leg4)
    if operation in ("leg4", "leg1+leg2+leg3+leg4"):
        print("\nCompile check: run javac against the generated plugin after codegen.")
        print("  Requires JDK javac on PATH.")
        compile_val = _ask("Run compile check? [Y/n]", default="y")
        if compile_val.lower() in ("n", "no"):
            parts.append("compile_check=false")

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
