#!/usr/bin/env python3
"""Velocity Converter MCP server — HTML to Velocity template pipeline.

Exposes four tools (one per leg, plus full pipeline) so Claude Code can
convert HTML files from any project directory without needing this repo
in the working directory.
"""

import os
import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

REPO_ROOT = Path(__file__).resolve().parent.parent
_CONVERT = "velocity_converter.convert"
_LEG0 = "velocity_converter.leg0_ingest"
_LEG2 = "velocity_converter.leg2_fill_mapping"
_LEG3 = "velocity_converter.leg3_substitute"
_LEG4 = "velocity_converter.leg4_generate_plugin"
_DEFAULT_REGISTRY = REPO_ROOT / "registry" / "path-registry.yaml"

mcp = FastMCP("velocity-converter")


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (Path.cwd() / p).resolve()


def _pkg_env() -> dict:
    """Subprocess env with the package importable even when not pip-installed.

    Must not change cwd — callers pass cwd-relative paths through _resolve().
    """
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(REPO_ROOT) + (os.pathsep + existing if existing else "")
    return env


def _run(cmd: list[str]) -> tuple[bool, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, env=_pkg_env())
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
    """
    input_path = _resolve(input_html)
    out_path = _resolve(output_dir)
    reg = _resolve(registry) if registry else _DEFAULT_REGISTRY
    stem = input_path.stem
    stem_dir = out_path / stem

    # Leg 1
    ok, msg = _run([sys.executable, "-m", _CONVERT, str(input_path),
                    "--output-dir", str(out_path), "--registry", str(reg)])
    if not ok:
        return f"Leg 1 failed:\n{msg}"

    # Leg 2
    mapping = stem_dir / f"{stem}.mapping.yaml"
    suggested = stem_dir / f"{stem}.suggested.yaml"
    review_out = stem_dir / f"{stem}.review.md"
    telemetry = stem_dir / f"{stem}.suggester-log.jsonl"

    ok, msg = _run([sys.executable, "-m", _LEG2,
                    "--mapping", str(mapping), "--registry", str(reg),
                    "--out", str(suggested), "--review-out", str(review_out),
                    "--telemetry-log", str(telemetry)])
    if not ok:
        return f"Leg 1 succeeded, Leg 2 failed:\n{msg}"

    # Leg 3
    final_vm = stem_dir / f"{stem}.final.vm"
    report = stem_dir / f"{stem}.leg3-report.md"
    ok, msg = _run([sys.executable, "-m", _LEG3,
                    "--suggested", str(suggested), "--out", str(final_vm),
                    "--report-out", str(report)])
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

    ok, msg = _run([sys.executable, "-m", _CONVERT, str(input_path),
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
    terminology: str = "",
) -> str:
    """Run Leg 2 only: suggest Socotra data-source paths for an existing .mapping.yaml.

    Writes <stem>.suggested.yaml and <stem>.review.md alongside the mapping file.
    Use when the user says "suggest paths", "run leg 2", or when resuming after
    manually editing a .mapping.yaml.

    Args:
        mapping:     Path to the .mapping.yaml file (absolute, or relative to CWD).
        registry:    Path to path-registry.yaml. Defaults to built-in registry.
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

    cmd = [sys.executable, "-m", _LEG2,
           "--mapping", str(mapping_path), "--registry", str(reg),
           "--out", str(suggested), "--review-out", str(review_out),
           "--telemetry-log", str(telemetry)]
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
) -> str:
    """Run Leg 3 only: substitute paths into the .vm and write the final template.

    Reads an existing .suggested.yaml (from Leg 2) and produces .final.vm
    and .leg3-report.md alongside it.

    Use when the user says "write the final vm", "run leg 3", "finalise the
    template", or after reviewing the .suggested.yaml manually.

    Args:
        suggested:  Path to the .suggested.yaml file (absolute, or relative to CWD).
    """
    suggested_path = _resolve(suggested)
    stem = suggested_path.stem
    if stem.endswith(".suggested"):
        stem = stem[: -len(".suggested")]
    base = suggested_path.parent

    final_vm = base / f"{stem}.final.vm"
    report = base / f"{stem}.leg3-report.md"

    ok, msg = _run([sys.executable, "-m", _LEG3,
                    "--suggested", str(suggested_path), "--out", str(final_vm),
                    "--report-out", str(report)])
    if not ok:
        return f"Leg 3 failed:\n{msg}"

    lines = [f"Leg 3 complete. Files written to {base}:"]
    for f in sorted(base.glob(f"{stem}.*")):
        lines.append(f"  {f.name}")
    lines.append(f"\nCheck {stem}.leg3-report.md for resolved/unresolved tokens.")
    return "\n".join(lines)


@mcp.tool()
def ingest_document(
    input_path: str,
    output_dir: str = "samples/output",
) -> str:
    """Ingest a Word (.docx) or PDF document into raw HTML and a conditional form.

    Runs Leg 0 of the pipeline:
      - Converts .docx or .pdf to raw HTML
      - Annotates {field} tokens as $TBD_* placeholders
      - Extracts conditional blocks into a customer-facing form
      - Writes .mapping.yaml for Leg 2 input

    Use when the user says: "convert my Word document", "ingest this PDF",
    "process my docx", "run leg 0".

    Args:
        input_path: Path to the .docx or .pdf file (absolute, or relative to CWD).
        output_dir: Directory for all output files. Default: samples/output/
    """
    inp = _resolve(input_path)
    out = _resolve(output_dir)
    stem = inp.stem

    ok, msg = _run([sys.executable, "-m", _LEG0, "--input", str(inp), "--output-dir", str(out)])
    if not ok:
        return f"ERROR: Leg 0 failed:\n{msg}"

    artifact_names = [
        f"{stem}.raw.html",
        f"{stem}.annotated.html",
        f"{stem}.mapping.yaml",
        f"{stem}.conditional-form.md",
    ]
    lines = [f"Leg 0 complete. Output: {out}"]
    for name in artifact_names:
        if (out / name).exists():
            lines.append(f"  {name}")
    lines.append(f"\nSend {stem}.conditional-form.md to the customer for conditional logic review.")
    lines.append(f"Then run suggest_velocity_paths on {out}/{stem}.mapping.yaml to continue.")
    return "\n".join(lines)


@mcp.tool()
def generate_snapshot_plugin(
    suggested_path: str,
    customer_jar: str,
    datamodel_jar: str,
    compile_check: bool = True,
) -> str:
    """Generate (or additively update) a DocumentDataSnapshotPluginImpl.java from a .mapping.yaml.

    Runs Leg 4 of the pipeline. If the plugin already exists in the output
    directory, runs in additive mode (adds missing keys, never removes existing
    ones, writes a .java.bak backup first).

    Use when the user says: "generate the plugin", "build the snapshot plugin",
    "run leg 4", "create the DocumentDataSnapshotPluginImpl".

    Args:
        suggested_path: Path to the .mapping.yaml (absolute, or relative to CWD).
        customer_jar:   Path to the customer config JAR.
        datamodel_jar:  Path to the core-datamodel JAR.
        compile_check:  If true (default), compile the generated Java class.
    """
    sugg = _resolve(suggested_path)
    cjar = _resolve(customer_jar)
    djar = _resolve(datamodel_jar)
    base = sugg.parent
    stem = sugg.stem
    for sfx in (".mapping", ".suggested"):
        if stem.endswith(sfx):
            stem = stem[: -len(sfx)]
            break

    cmd = [
        sys.executable, "-m", _LEG4,
        "--suggested", str(sugg),
        "--customer-jar", str(cjar),
        "--datamodel-jar", str(djar),
    ]
    if compile_check:
        cmd.append("--compile-check")

    ok, msg = _run(cmd)
    if not ok:
        return f"ERROR: Leg 4 failed:\n{msg}"

    lines = [f"Leg 4 complete. Files written to {base}:"]
    for f in sorted(base.glob("*PluginImpl*.java")):
        lines.append(f"  {f.name}")
    report = base / f"{stem}.plugin-report.md"
    if report.exists():
        lines.append(f"  {report.name}")
    lines.append(f"\nCheck {stem}.plugin-report.md for path validation + compile result.")
    return "\n".join(lines)


@mcp.tool()
def list_velocity_paths(
    registry_path: str = "",
    out_path: str = "",
) -> str:
    """Render a Markdown catalog of all available Velocity paths for this product.

    If out_path is given, writes the catalog to that file and returns a summary.
    Otherwise returns the full Markdown string (suitable for Claude to read and
    answer questions about available fields).

    Use when the user says: "what fields can I use", "list available paths",
    "show me the field catalog", "what data is available in the template".

    Args:
        registry_path: Path to path-registry.yaml. Defaults to the built-in registry.
        out_path:      Optional file to write the catalog to. If omitted, returns inline.
    """
    reg = _resolve(registry_path) if registry_path else _DEFAULT_REGISTRY

    try:
        from velocity_converter.list_paths import render_catalog  # noqa: PLC0415
        catalog = render_catalog(str(reg))
    except Exception as e:
        return f"ERROR: {e}"

    if out_path:
        out = _resolve(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(catalog, encoding="utf-8")
        return f"Field catalog written to {out}\n({len(catalog.splitlines())} lines)"

    return catalog


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
