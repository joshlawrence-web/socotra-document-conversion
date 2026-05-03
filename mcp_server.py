#!/usr/bin/env python3
"""Velocity Converter MCP server — HTML to Velocity template pipeline.

Exposes four tools (one per leg, plus full pipeline) so Claude Code can
convert HTML files from any project directory without needing this repo
in the working directory.
"""

import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

INSTALL_ROOT = Path(__file__).parent
_CONVERT = INSTALL_ROOT / ".cursor" / "skills" / "html-to-velocity" / "scripts" / "convert.py"
_LEG2 = INSTALL_ROOT / "scripts" / "leg2_fill_mapping.py"
_LEG3 = INSTALL_ROOT / "scripts" / "leg3_substitute.py"
_DEFAULT_REGISTRY = INSTALL_ROOT / "registry" / "path-registry.yaml"

mcp = FastMCP("velocity-converter")


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (Path.cwd() / p).resolve()


def _run(cmd: list[str]) -> tuple[bool, str]:
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def _artifact_summary(directory: Path, stem: str) -> str:
    files = sorted(directory.glob("*")) if directory.is_dir() else []
    lines = [f"Output: {directory}"]
    for f in files:
        lines.append(f"  {f.name}")
    lines.append(f"\nCheck {stem}.leg3-report.md for resolved/unresolved tokens.")
    return "\n".join(lines)


@mcp.tool()
def convert_html_to_velocity(
    input_html: str,
    output_dir: str = "velocity-output",
    registry: str = "",
    high_only: bool = False,
) -> str:
    """Convert an HTML file into a production-ready Velocity (.vm) template.

    Runs the full 3-leg pipeline:
      Leg 1 — parse HTML, extract $TBD_* placeholder tokens
      Leg 2 — match placeholders to Socotra data-source paths via registry
      Leg 3 — substitute matched paths, write .final.vm and .leg3-report.md

    Use when the user says: "convert my HTML", "run the pipeline",
    "generate the template", "process my HTML file", "finalise the template".

    Args:
        input_html: Path to the HTML file (absolute, or relative to CWD).
        output_dir: Directory for all output files. Default: velocity-output/
        registry:   Path to path-registry.yaml. Defaults to the built-in registry.
        high_only:  If true, only substitute confidence:high tokens. Medium/low
                    tokens stay as $TBD_* and appear in the deferred report section.
    """
    input_path = _resolve(input_html)
    out_path = _resolve(output_dir)
    reg = _resolve(registry) if registry else _DEFAULT_REGISTRY
    stem = input_path.stem
    stem_dir = out_path / stem

    # Leg 1
    ok, msg = _run([sys.executable, str(_CONVERT), str(input_path),
                    "--output-dir", str(out_path), "--registry", str(reg)])
    if not ok:
        return f"Leg 1 failed:\n{msg}"

    # Leg 2
    mapping = stem_dir / f"{stem}.mapping.yaml"
    suggested = stem_dir / f"{stem}.suggested.yaml"
    review_out = stem_dir / f"{stem}.review.md"
    telemetry = stem_dir / f"{stem}.suggester-log.jsonl"

    ok, msg = _run([sys.executable, str(_LEG2),
                    "--mapping", str(mapping), "--registry", str(reg),
                    "--out", str(suggested), "--review-out", str(review_out),
                    "--telemetry-log", str(telemetry), "--mode", "terse"])
    if not ok:
        return f"Leg 1 succeeded, Leg 2 failed:\n{msg}"

    # Leg 3
    final_vm = stem_dir / f"{stem}.final.vm"
    report = stem_dir / f"{stem}.leg3-report.md"
    cmd = [sys.executable, str(_LEG3),
           "--suggested", str(suggested), "--out", str(final_vm),
           "--report-out", str(report)]
    if high_only:
        cmd.append("--high-only")

    ok, msg = _run(cmd)
    if not ok:
        return f"Legs 1+2 succeeded, Leg 3 failed:\n{msg}"

    return _artifact_summary(stem_dir, stem)


@mcp.tool()
def extract_velocity_tokens(
    input_html: str,
    output_dir: str = "velocity-output",
    registry: str = "",
) -> str:
    """Run Leg 1 only: parse HTML and extract $TBD_* placeholder tokens.

    Writes <stem>.vm and <stem>.mapping.yaml but does NOT suggest paths.
    Use this when you want to inspect the token mapping before committing
    to path suggestions, or when the user says "run leg 1 only" / "just
    extract the tokens".

    Args:
        input_html: Path to the HTML file (absolute, or relative to CWD).
        output_dir: Directory for output. Default: velocity-output/
        registry:   Path to path-registry.yaml. Defaults to built-in registry.
    """
    input_path = _resolve(input_html)
    out_path = _resolve(output_dir)
    reg = _resolve(registry) if registry else _DEFAULT_REGISTRY
    stem = input_path.stem
    stem_dir = out_path / stem

    ok, msg = _run([sys.executable, str(_CONVERT), str(input_path),
                    "--output-dir", str(out_path), "--registry", str(reg)])
    if not ok:
        return f"Leg 1 failed:\n{msg}"

    files = sorted(stem_dir.glob("*")) if stem_dir.is_dir() else []
    lines = [f"Leg 1 complete. Output: {stem_dir}"]
    for f in files:
        lines.append(f"  {f.name}")
    lines.append(f"\nEdit {stem}.mapping.yaml then run suggest_velocity_paths to continue.")
    return "\n".join(lines)


@mcp.tool()
def suggest_velocity_paths(
    mapping: str,
    registry: str = "",
    mode: str = "terse",
    terminology: str = "",
) -> str:
    """Run Leg 2 only: suggest Socotra data-source paths for an existing .mapping.yaml.

    Writes <stem>.suggested.yaml and <stem>.review.md alongside the mapping file.
    Use when the user says "suggest paths", "run leg 2", or when resuming after
    manually editing a .mapping.yaml.

    Args:
        mapping:     Path to the .mapping.yaml file (absolute, or relative to CWD).
        registry:    Path to path-registry.yaml. Defaults to built-in registry.
        mode:        Suggester verbosity: terse (default), full, delta, or batch.
        terminology: Optional path to a terminology.yaml override file.
    """
    mapping_path = _resolve(mapping)
    reg = _resolve(registry) if registry else _DEFAULT_REGISTRY
    stem = mapping_path.stem
    if stem.endswith(".mapping"):
        stem = stem[: -len(".mapping")]
    base = mapping_path.parent

    suggested = base / f"{stem}.suggested.yaml"
    review_out = base / f"{stem}.review.md"
    telemetry = base / f"{stem}.suggester-log.jsonl"

    cmd = [sys.executable, str(_LEG2),
           "--mapping", str(mapping_path), "--registry", str(reg),
           "--out", str(suggested), "--review-out", str(review_out),
           "--telemetry-log", str(telemetry), "--mode", mode]
    if terminology:
        cmd += ["--terminology", str(_resolve(terminology))]

    ok, msg = _run(cmd)
    if not ok:
        return f"Leg 2 failed:\n{msg}"

    lines = [f"Leg 2 complete. Files written to {base}:"]
    for f in sorted(base.glob(f"{stem}.*")):
        lines.append(f"  {f.name}")
    lines.append(f"\nReview {stem}.review.md, then run write_final_template to finish.")
    return "\n".join(lines)


@mcp.tool()
def write_final_template(
    suggested: str,
    high_only: bool = False,
) -> str:
    """Run Leg 3 only: substitute paths into the .vm and write the final template.

    Reads an existing .suggested.yaml (from Leg 2) and produces .final.vm
    and .leg3-report.md alongside it.

    Use when the user says "write the final vm", "run leg 3", "finalise the
    template", or after reviewing the .suggested.yaml manually.

    Args:
        suggested:  Path to the .suggested.yaml file (absolute, or relative to CWD).
        high_only:  If true, only substitute confidence:high tokens. Medium/low
                    tokens stay as $TBD_* in the output and appear in a Deferred
                    section of the report. Use this when fuzzy matches need human
                    review before going to production.
    """
    suggested_path = _resolve(suggested)
    stem = suggested_path.stem
    if stem.endswith(".suggested"):
        stem = stem[: -len(".suggested")]
    base = suggested_path.parent

    final_vm = base / f"{stem}.final.vm"
    report = base / f"{stem}.leg3-report.md"

    cmd = [sys.executable, str(_LEG3),
           "--suggested", str(suggested_path), "--out", str(final_vm),
           "--report-out", str(report)]
    if high_only:
        cmd.append("--high-only")

    ok, msg = _run(cmd)
    if not ok:
        return f"Leg 3 failed:\n{msg}"

    lines = [f"Leg 3 complete. Files written to {base}:"]
    for f in sorted(base.glob(f"{stem}.*")):
        lines.append(f"  {f.name}")
    lines.append(f"\nCheck {stem}.leg3-report.md for resolved/unresolved tokens.")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
