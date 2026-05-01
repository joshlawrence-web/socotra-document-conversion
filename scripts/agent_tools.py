"""Pure-Python tool implementations for the pipeline-orchestrator agent.

No Claude API code here — only business logic called by agent.py dispatch.
"""

import subprocess
import sys
from pathlib import Path


def _find_repo_root() -> Path:
    """Walk up from CWD until a directory containing .cursor/ is found."""
    p = Path.cwd().resolve()
    for candidate in [p, *p.parents]:
        if (candidate / ".cursor").is_dir():
            return candidate
    raise RuntimeError(
        "Cannot locate repo root: no .cursor/ directory found in ancestors of CWD"
    )


def _resolve_safe(p: str, repo_root: Path) -> Path:
    """Resolve a path to absolute and verify it stays inside repo_root."""
    resolved = (repo_root / p).resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError:
        raise ValueError(f"Path escapes repo root: {p!r}")
    return resolved


def validate_inputs(
    operation: str,
    input_html: str | None = None,
    mapping=None,
    registry: str | None = None,
    output: str | None = None,
    mode: str | None = None,
    terminology: str | None = None,
    suggested: str | None = None,
    **kwargs,
) -> dict:
    """
    Returns {"ok": True} or {"ok": False, "errors": [...], "missing": [...]}.
    Checks file existence, correct extensions, and path safety (no escaping repo root).
    Does NOT read file contents.
    """
    repo_root = _find_repo_root()
    errors: list[str] = []
    missing: list[str] = []

    valid_ops = {"leg1", "leg2", "leg1+leg2", "leg3", "leg1+leg2+leg3"}
    if operation not in valid_ops:
        errors.append(
            f"Invalid operation {operation!r}. Must be one of: {', '.join(sorted(valid_ops))}"
        )

    if operation in ("leg1", "leg1+leg2"):
        if not input_html:
            missing.append("input_html")
        else:
            try:
                p = _resolve_safe(input_html, repo_root)
                if not p.exists():
                    errors.append(f"input_html not found: {input_html!r}")
                elif p.suffix.lower() != ".html":
                    errors.append(f"input_html must be a .html file, got: {p.name!r}")
            except ValueError as e:
                errors.append(str(e))

    if operation in ("leg2",):
        if not mapping:
            missing.append("mapping")
        else:
            mappings = mapping if isinstance(mapping, list) else [mapping]
            for m in mappings:
                try:
                    p = _resolve_safe(m, repo_root)
                    if not p.exists():
                        errors.append(f"mapping not found: {m!r}")
                    elif not p.name.endswith(".mapping.yaml"):
                        errors.append(f"mapping must be a .mapping.yaml file, got: {p.name!r}")
                except ValueError as e:
                    errors.append(str(e))

    if operation == "leg3":
        if not suggested:
            missing.append("suggested")
        else:
            try:
                p = _resolve_safe(suggested, repo_root)
                if not p.exists():
                    errors.append(f"suggested not found: {suggested!r}")
                elif not p.name.endswith(".suggested.yaml"):
                    errors.append(f"suggested must be a .suggested.yaml file, got: {p.name!r}")
            except ValueError as e:
                errors.append(str(e))

    if operation in ("leg2", "leg1+leg2", "leg1+leg2+leg3"):
        valid_modes = {"full", "terse", "delta", "batch"}
        if not mode:
            missing.append("mode")
        elif mode not in valid_modes:
            errors.append(
                f"Invalid mode {mode!r}. Must be one of: {', '.join(sorted(valid_modes))}"
            )

    default_registry = repo_root / "registry" / "path-registry.yaml"
    if registry:
        try:
            p = _resolve_safe(registry, repo_root)
            if not p.exists():
                errors.append(f"registry not found: {registry!r}")
        except ValueError as e:
            errors.append(str(e))
    elif not default_registry.exists():
        errors.append("Default registry not found: registry/path-registry.yaml")

    if terminology:
        try:
            p = _resolve_safe(terminology, repo_root)
            if not p.exists():
                errors.append(f"terminology not found: {terminology!r}")
        except ValueError as e:
            errors.append(str(e))

    if errors or missing:
        return {"ok": False, "errors": errors, "missing": missing}
    return {"ok": True}


def list_candidates(output_dir: str = "samples/output") -> list[str]:
    """Find all *.mapping.yaml files under output_dir, sorted by mtime descending."""
    repo_root = _find_repo_root()
    try:
        d = _resolve_safe(output_dir, repo_root)
    except ValueError:
        return []
    if not d.is_dir():
        return []
    files = sorted(
        d.rglob("*.mapping.yaml"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return [str(f.relative_to(repo_root)) for f in files]


def _predict_writes(
    operation: str,
    input_html: str | None,
    mapping,
    out_dir: str,
    mode: str | None,
    suggested: str | None = None,
) -> list[str]:
    writes = []
    if operation in ("leg1", "leg1+leg2", "leg1+leg2+leg3") and input_html:
        stem = Path(input_html).stem
        base = f"{out_dir}/{stem}"
        writes += [f"{base}/{stem}.vm", f"{base}/{stem}.mapping.yaml", f"{base}/{stem}.report.md"]
    if operation in ("leg2", "leg1+leg2", "leg1+leg2+leg3"):
        if operation == "leg2" and mapping:
            mappings = mapping if isinstance(mapping, list) else [mapping]
        elif operation in ("leg1+leg2", "leg1+leg2+leg3") and input_html:
            stem = Path(input_html).stem
            mappings = [f"{out_dir}/{stem}/{stem}.mapping.yaml"]
        else:
            mappings = []
        for m in mappings:
            stem = Path(m).stem
            if stem.endswith(".mapping"):
                stem = stem[: -len(".mapping")]
            base = str(Path(m).parent)
            writes += [
                f"{base}/{stem}.suggested.yaml",
                f"{base}/{stem}.review.md",
                f"{base}/{stem}.suggester-log.jsonl",
            ]
    if operation in ("leg3", "leg1+leg2+leg3"):
        if operation == "leg3" and suggested:
            stem = Path(suggested).stem
            if stem.endswith(".suggested"):
                stem = stem[: -len(".suggested")]
            base = str(Path(suggested).parent)
        elif operation == "leg1+leg2+leg3" and input_html:
            stem = Path(input_html).stem
            base = f"{out_dir}/{stem}"
        else:
            stem = base = None
        if stem and base:
            writes += [
                f"{base}/{stem}.final.vm",
                f"{base}/{stem}.leg3-report.md",
            ]
    return writes


def build_preflight(
    operation: str,
    input_html: str | None = None,
    mapping=None,
    registry: str | None = None,
    output: str | None = None,
    mode: str | None = None,
    terminology: str | None = None,
    suggested: str | None = None,
    high_only: bool = False,
) -> str:
    """Return the formatted preflight block as a string. Does not write anything."""
    reg_path = registry or "registry/path-registry.yaml"
    out_dir = output or "samples/output"

    W = 54  # inner width (between ║ borders)

    def row(text: str) -> str:
        return f"║{text:<{W}}║"

    lines = [
        "╔" + "═" * W + "╗",
        row("  PIPELINE PREFLIGHT SUMMARY"),
        "╠" + "═" * W + "╣",
        row(f"  Operation : {operation}"),
    ]
    if mode:
        lines.append(row(f"  Mode      : {mode}"))
    if high_only:
        lines.append(row(f"  High-only : yes (medium/low confidence deferred)"))
    if input_html:
        lines.append(row(f"  Input HTML: {input_html}"))
    if mapping:
        mappings = mapping if isinstance(mapping, list) else [mapping]
        for m in mappings:
            lines.append(row(f"  Mapping   : {m}"))
    lines.append(row(f"  Registry  : {reg_path}"))
    lines.append(row(f"  Output dir: {out_dir}"))
    if suggested:
        lines.append(row(f"  Suggested : {suggested}"))
    if terminology:
        lines.append(row(f"  Terminology: {terminology}"))
    lines.append("╠" + "═" * W + "╣")
    lines.append(row("  Files that WILL be written:"))

    writes = _predict_writes(operation, input_html, mapping, out_dir, mode, suggested)
    for w in writes:
        display = w if len(w) <= W - 4 else "…" + w[-(W - 5):]
        lines.append(row(f"    {display}"))

    lines.append("╚" + "═" * W + "╝")
    lines.append("")
    lines.append("Reply PROCEED to run, or CANCEL to abort.")
    return "\n".join(lines)


def run_leg1(
    input_html: str,
    output_dir: str,
    registry: str,
    no_conditionals: bool = False,
    auto_detect_loops: bool = False,
) -> dict:
    """Run convert.py for Leg 1. Returns ok/artifacts/stdout/stderr."""
    repo_root = _find_repo_root()
    script = repo_root / ".cursor" / "skills" / "html-to-velocity" / "scripts" / "convert.py"
    cmd = [
        sys.executable,
        str(script),
        str(_resolve_safe(input_html, repo_root)),
        "--output-dir",
        str(_resolve_safe(output_dir, repo_root)),
        "--registry",
        str(_resolve_safe(registry, repo_root)),
    ]
    if no_conditionals:
        cmd.append("--no-conditionals")
    if auto_detect_loops:
        cmd.append("--auto-detect-loops")

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
    if result.returncode != 0:
        return {"ok": False, "returncode": result.returncode, "stderr": result.stderr}

    stem = Path(input_html).stem
    out_path = _resolve_safe(output_dir, repo_root) / stem
    artifacts = (
        [str(f.relative_to(repo_root)) for f in out_path.glob("*") if f.is_file()]
        if out_path.is_dir()
        else []
    )
    return {"ok": True, "artifacts": artifacts, "stdout": result.stdout, "stderr": result.stderr}


def run_leg3(
    suggested: str,
    out: str,
    report_out: str,
    vm: str | None = None,
    high_only: bool = False,
) -> dict:
    """Run leg3_substitute.py for Leg 3. Returns ok/artifacts/stdout/stderr."""
    repo_root = _find_repo_root()
    script = repo_root / "scripts" / "leg3_substitute.py"
    cmd = [
        sys.executable,
        str(script),
        "--suggested",
        str(_resolve_safe(suggested, repo_root)),
        "--out",
        str(_resolve_safe(out, repo_root)),
        "--report-out",
        str(_resolve_safe(report_out, repo_root)),
    ]
    if vm:
        cmd += ["--vm", str(_resolve_safe(vm, repo_root))]
    if high_only:
        cmd.append("--high-only")

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
    if result.returncode != 0:
        return {"ok": False, "returncode": result.returncode, "stderr": result.stderr}

    artifacts = []
    for p_str in [out, report_out]:
        p = _resolve_safe(p_str, repo_root)
        if p.exists():
            artifacts.append(str(p.relative_to(repo_root)))
    return {"ok": True, "artifacts": artifacts, "stdout": result.stdout, "stderr": result.stderr}


def run_leg2(
    mapping: str,
    registry: str,
    out: str,
    review_out: str,
    telemetry_log: str,
    mode: str,
    terminology: str | None = None,
    base_suggested: str | None = None,
) -> dict:
    """Run leg2_fill_mapping.py for Leg 2. Returns ok/artifacts/stdout/stderr."""
    repo_root = _find_repo_root()
    script = repo_root / "scripts" / "leg2_fill_mapping.py"
    cmd = [
        sys.executable,
        str(script),
        "--mapping",
        str(_resolve_safe(mapping, repo_root)),
        "--registry",
        str(_resolve_safe(registry, repo_root)),
        "--out",
        str(_resolve_safe(out, repo_root)),
        "--review-out",
        str(_resolve_safe(review_out, repo_root)),
        "--telemetry-log",
        str(_resolve_safe(telemetry_log, repo_root)),
        "--mode",
        mode,
    ]
    if terminology:
        cmd += ["--terminology", str(_resolve_safe(terminology, repo_root))]
    if base_suggested:
        cmd += ["--base-suggested", str(_resolve_safe(base_suggested, repo_root))]

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
    if result.returncode != 0:
        return {"ok": False, "returncode": result.returncode, "stderr": result.stderr}

    artifacts = []
    for p_str in [out, review_out, telemetry_log]:
        p = _resolve_safe(p_str, repo_root)
        if p.exists():
            artifacts.append(str(p.relative_to(repo_root)))
    return {"ok": True, "artifacts": artifacts, "stdout": result.stdout, "stderr": result.stderr}
