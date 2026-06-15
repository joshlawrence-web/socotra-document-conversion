"""Pure-Python tool implementations for the pipeline-orchestrator agent.

No Claude API code here — only business logic called by agent.py dispatch.
"""

import re
import subprocess
import sys
from pathlib import Path

from velocity_converter.workspace import (
    action_needed_dir,
    machine_dir_for_action_file,
)

_INTERMEDIATE_SUFFIXES = frozenset({
    ".mapping.yaml",
    ".review.md",
})

_FULL_PIPELINE_OPS = frozenset({
    "leg0+leg2+leg3",
    "leg2+leg3",
    "leg1+leg2+leg3",
    "leg1+leg2+leg3+leg4",
})


def _try_read_product(suggested_path: "str | Path") -> "str | None":
    """Best-effort: read product: from a .mapping.yaml or .suggested.yaml. Returns None on failure."""
    try:
        import yaml  # noqa: PLC0415
        p = Path(suggested_path)
        if not p.exists():
            return None
        text = p.read_text(encoding="utf-8")
        filtered = "\n".join(ln for ln in text.splitlines() if not ln.startswith("#"))
        data = yaml.safe_load(filtered) or {}
        return (data.get("product") or "").strip() or None
    except Exception:
        return None


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

    valid_ops = {"leg0", "leg0+leg2+leg3", "leg1", "leg2", "leg2+leg3", "leg1+leg2", "leg3", "leg1+leg2+leg3", "leg4", "leg1+leg2+leg3+leg4", "list_paths"}
    if operation not in valid_ops:
        errors.append(
            f"Invalid operation {operation!r}. Must be one of: {', '.join(sorted(valid_ops))}"
        )

    if operation in ("leg0", "leg0+leg2+leg3"):
        if not input_html:
            missing.append("input")
        else:
            try:
                p = _resolve_safe(input_html, repo_root)
                if not p.exists():
                    errors.append(f"input not found: {input_html!r}")
                elif p.suffix.lower() not in (".docx", ".pdf"):
                    errors.append(f"input must be a .docx or .pdf file, got: {p.name!r}")
            except ValueError as e:
                errors.append(str(e))

    if operation in ("leg1", "leg1+leg2", "leg1+leg2+leg3", "leg1+leg2+leg3+leg4"):
        if not input_html:
            missing.append("input")
        else:
            try:
                p = _resolve_safe(input_html, repo_root)
                if not p.exists():
                    errors.append(f"input not found: {input_html!r}")
                elif p.suffix.lower() != ".html":
                    errors.append(f"input must be a .html file, got: {p.name!r}")
            except ValueError as e:
                errors.append(str(e))

    if operation in ("leg2", "leg2+leg3"):
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

    if operation in ("leg3", "leg4"):
        if not suggested:
            missing.append("suggested")
        else:
            suggesteds = suggested if isinstance(suggested, list) else [suggested]
            if operation == "leg3" and len(suggesteds) > 1:
                errors.append("leg3 accepts a single suggested file (leg4 accepts a list)")
            for s_item in suggesteds:
                try:
                    p = _resolve_safe(s_item, repo_root)
                    if not p.exists():
                        errors.append(f"suggested not found: {s_item!r}")
                    elif not (p.name.endswith(".mapping.yaml") or p.name.endswith(".suggested.yaml")):
                        errors.append(f"suggested must be a .mapping.yaml (or legacy .suggested.yaml) file, got: {p.name!r}")
                except ValueError as e:
                    errors.append(str(e))

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


def list_candidates(output_dir: str = "workspace/output") -> list[str]:
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
    suggested: str | None = None,
) -> list[str]:
    writes = []
    if operation in ("leg0", "leg0+leg2+leg3") and input_html:
        stem = Path(input_html).stem
        base = f"{out_dir}/{stem}"
        action = action_needed_dir(Path(base))
        writes += [
            f"{base}/{stem}.raw.html",
            f"{base}/{stem}.annotated.html",
            f"{base}/{stem}.mapping.yaml",
            f"{action}/{stem}.conditional-form.md",
        ]
    if operation in ("leg1", "leg1+leg2", "leg1+leg2+leg3", "leg1+leg2+leg3+leg4") and input_html:
        stem = Path(input_html).stem
        base = f"{out_dir}/{stem}"
        writes += [
            f"{base}/{stem}.vm",
            f"{base}/{stem}.mapping.yaml",
            f"{base}/{stem}.report.md",
            f"{base}/{stem}.conditional-registry.yaml",
            f"{base}/{stem}.conditional-review.md",
            f"{base}/{stem}.conditional-ref.html",
        ]
    if operation in ("leg2", "leg2+leg3", "leg0+leg2+leg3", "leg1+leg2", "leg1+leg2+leg3", "leg1+leg2+leg3+leg4"):
        if operation in ("leg2", "leg2+leg3") and mapping:
            mappings = mapping if isinstance(mapping, list) else [mapping]
        elif operation == "leg0+leg2+leg3" and input_html:
            stem = Path(input_html).stem
            mappings = [f"{out_dir}/{stem}/{stem}.mapping.yaml"]
        elif operation in ("leg1+leg2", "leg1+leg2+leg3", "leg1+leg2+leg3+leg4") and input_html:
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
                f"{base}/{stem}.review.md",
            ]
    if operation in ("leg3", "leg2+leg3", "leg0+leg2+leg3", "leg1+leg2+leg3", "leg1+leg2+leg3+leg4"):
        if operation == "leg3" and suggested:
            stem = Path(suggested).stem
            if stem.endswith(".suggested"):
                stem = stem[: -len(".suggested")]
            base = str(Path(suggested).parent)
        elif operation == "leg2+leg3" and mapping:
            m = mapping if isinstance(mapping, str) else (mapping[0] if mapping else None)
            if m:
                stem = Path(m).stem
                if stem.endswith(".mapping"):
                    stem = stem[: -len(".mapping")]
                base = str(Path(m).parent)
            else:
                stem = base = None
        elif operation == "leg0+leg2+leg3" and input_html:
            stem = Path(input_html).stem
            base = f"{out_dir}/{stem}"
        elif operation in ("leg1+leg2+leg3", "leg1+leg2+leg3+leg4") and input_html:
            stem = Path(input_html).stem
            base = f"{out_dir}/{stem}"
        else:
            stem = base = None
        if stem and base:
            writes += [
                f"{base}/{stem}.final.vm",
                f"{base}/{stem}.leg3-report.md",
            ]
    if operation in ("leg4", "leg1+leg2+leg3+leg4"):
        if operation == "leg4" and suggested:
            leg4_paths = suggested if isinstance(suggested, list) else [suggested]
        elif operation == "leg1+leg2+leg3+leg4" and input_html:
            s = Path(input_html).stem
            leg4_paths = [f"{out_dir}/{s}/{s}.mapping.yaml"]
        else:
            leg4_paths = []
        for i, leg4_base_path in enumerate(leg4_paths):
            stem4 = Path(leg4_base_path).stem
            for _sfx in (".suggested", ".mapping"):
                if stem4.endswith(_sfx):
                    stem4 = stem4[: -len(_sfx)]
                    break
            base4 = str(Path(leg4_base_path).parent)
            if i == 0:
                # The shared plugin .java lands in the first form's directory
                product = _try_read_product(leg4_base_path)
                java_name = (
                    f"{product}DocumentDataSnapshotPluginImpl.java"
                    if product
                    else "<Product>DocumentDataSnapshotPluginImpl.java"
                )
                writes.append(f"{base4}/{java_name}")
            writes.append(f"{base4}/{stem4}.plugin-report.md")
    return writes


def build_preflight(
    operation: str,
    input_html: str | None = None,
    mapping=None,
    registry: str | None = None,
    output: str | None = None,
    terminology: str | None = None,
    suggested: str | None = None,
    compile_check: bool = True,
    keep_intermediates: bool = False,
) -> str:
    """Return the formatted preflight block as a string. Does not write anything."""
    reg_path = registry or "registry/path-registry.yaml"
    out_dir = output or "workspace/output"

    W = 54  # inner width (between ║ borders)

    def row(text: str) -> str:
        return f"║{text:<{W}}║"

    lines = [
        "╔" + "═" * W + "╗",
        row("  PIPELINE PREFLIGHT SUMMARY"),
        "╠" + "═" * W + "╣",
        row(f"  Operation : {operation}"),
    ]
    if operation in ("leg4", "leg1+leg2+leg3+leg4"):
        lines.append(row(f"  Compile   : {'yes' if compile_check else 'no (--compile-check disabled)'}"))
    if input_html:
        input_label = "Input     " if operation in ("leg0", "leg0+leg2+leg3") else "Input HTML"
        lines.append(row(f"  {input_label}: {input_html}"))
    if mapping:
        mappings = mapping if isinstance(mapping, list) else [mapping]
        for m in mappings:
            lines.append(row(f"  Mapping   : {m}"))
    lines.append(row(f"  Registry  : {reg_path}"))
    lines.append(row(f"  Output dir: {out_dir}"))
    if suggested:
        for s_item in (suggested if isinstance(suggested, list) else [suggested]):
            lines.append(row(f"  Suggested : {s_item}"))
    if terminology:
        lines.append(row(f"  Terminology: {terminology}"))
    lines.append("╠" + "═" * W + "╣")

    writes = _predict_writes(operation, input_html, mapping, out_dir, suggested)

    clean_intermediates = (not keep_intermediates) and (operation in _FULL_PIPELINE_OPS)
    if clean_intermediates:
        final_writes = [w for w in writes if not any(w.endswith(s) for s in _INTERMEDIATE_SUFFIXES)]
        temp_writes = [w for w in writes if any(w.endswith(s) for s in _INTERMEDIATE_SUFFIXES)]
    else:
        final_writes = writes
        temp_writes = []

    lines.append(row("  Files that WILL be written:"))
    for w in final_writes:
        display = w if len(w) <= W - 4 else "…" + w[-(W - 5):]
        lines.append(row(f"    {display}"))

    if temp_writes:
        lines.append("╠" + "═" * W + "╣")
        lines.append(row("  Temp (removed on success):"))
        for w in temp_writes:
            display = w if len(w) <= W - 4 else "…" + w[-(W - 5):]
            lines.append(row(f"    {display}"))
        lines.append(row("  Add keep=intermediates to retain these files."))

    lines.append("╚" + "═" * W + "╝")
    lines.append("")
    lines.append("Reply PROCEED to run, or CANCEL to abort.")
    return "\n".join(lines)


def run_leg0(input_path: str, output_dir: str) -> dict:
    """Run leg0_ingest.py for Leg 0. Returns ok/artifacts/stdout/stderr."""
    repo_root = _find_repo_root()
    cmd = [
        sys.executable,
        "-m",
        "velocity_converter.leg0_ingest",
        "--input",
        str(_resolve_safe(input_path, repo_root)),
        "--output-dir",
        str(_resolve_safe(output_dir, repo_root)),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
    if result.returncode != 0:
        return {"ok": False, "returncode": result.returncode, "stderr": result.stderr}

    input_p = _resolve_safe(input_path, repo_root)
    stem = input_p.stem
    out_p = _resolve_safe(output_dir, repo_root)

    # (dir, filename) pairs — the conditional form is projected into action-needed/.
    artifact_locs = [
        (out_p, f"{stem}.raw.html"),
        (out_p, f"{stem}.annotated.html"),
        (out_p, f"{stem}.mapping.yaml"),
        (action_needed_dir(out_p), f"{stem}.conditional-form.md"),
    ]
    artifacts = [
        str((d / name).relative_to(repo_root))
        for d, name in artifact_locs
        if (d / name).exists()
    ]
    return {"ok": True, "artifacts": artifacts, "stdout": result.stdout, "stderr": result.stderr}


def run_legminus1(input_path: str, registry: str, output_dir: str) -> dict:
    """Run Leg -1 (suggest): bare {leaf} → full accessor review + map + audit.

    Returns ok/artifacts/stdout/stderr. Artifacts land in ``output_dir/<stem>/``.
    """
    repo_root = _find_repo_root()
    cmd = [
        sys.executable,
        "-m",
        "velocity_converter.legminus1_resolve_paths",
        "--input",
        str(_resolve_safe(input_path, repo_root)),
        "--registry",
        str(_resolve_safe(registry, repo_root)),
        "--output-dir",
        str(_resolve_safe(output_dir, repo_root)),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
    if result.returncode != 0:
        return {"ok": False, "returncode": result.returncode, "stderr": result.stderr}

    stem = Path(input_path).stem
    out_p = _resolve_safe(output_dir, repo_root) / stem
    # path-review.md is projected into action-needed/; map + audit stay in out_p.
    artifact_locs = [
        (action_needed_dir(out_p), f"{stem}.path-review.md"),
        (out_p, f"{stem}.path-map.yaml"),
        (out_p, f"{stem}.path-changes.md"),
    ]
    artifacts = [
        str((d / name).relative_to(repo_root))
        for d, name in artifact_locs
        if (d / name).exists()
    ]
    return {"ok": True, "artifacts": artifacts, "stdout": result.stdout, "stderr": result.stderr}


def run_legminus1_apply(review: str, output_dir: str | None = None) -> dict:
    """Run Leg -1 (apply): parse a human-edited path-review → final map +
    audit + resolved doc. Returns ok/artifacts/stdout/stderr."""
    repo_root = _find_repo_root()
    cmd = [
        sys.executable,
        "-m",
        "velocity_converter.legminus1_resolve_paths",
        "--parse-path-review",
        str(_resolve_safe(review, repo_root)),
    ]
    if output_dir:
        cmd += ["--output-dir", str(_resolve_safe(output_dir, repo_root))]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
    if result.returncode != 0:
        return {"ok": False, "returncode": result.returncode, "stderr": result.stderr}
    if output_dir:
        out_p = _resolve_safe(output_dir, repo_root)
    else:
        review_abs = Path(review) if Path(review).is_absolute() else _resolve_safe(review, repo_root)
        out_p = machine_dir_for_action_file(review_abs) or review_abs.parent
    artifacts = (
        [str(f.relative_to(repo_root)) for f in out_p.glob("*")
         if f.is_file() and (".path-map" in f.name or ".path-changes" in f.name or ".resolved." in f.name)]
        if out_p.is_dir() else []
    )
    return {"ok": True, "artifacts": artifacts, "stdout": result.stdout, "stderr": result.stderr}


def run_leg1(
    input_html: str,
    output_dir: str,
    registry: str,
    no_conditionals: bool = False,
    auto_detect_loops: bool = False,
) -> dict:
    """Run convert.py for Leg 1. Returns ok/artifacts/stdout/stderr."""
    repo_root = _find_repo_root()
    cmd = [
        sys.executable,
        "-m",
        "velocity_converter.convert",
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
) -> dict:
    """Run leg3_substitute.py for Leg 3. Returns ok/artifacts/stdout/stderr."""
    repo_root = _find_repo_root()
    cmd = [
        sys.executable,
        "-m",
        "velocity_converter.leg3_substitute",
        "--suggested",
        str(_resolve_safe(suggested, repo_root)),
        "--out",
        str(_resolve_safe(out, repo_root)),
        "--report-out",
        str(_resolve_safe(report_out, repo_root)),
    ]
    if vm:
        cmd += ["--vm", str(_resolve_safe(vm, repo_root))]

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
    telemetry_log: str | None = None,
    terminology: str | None = None,
) -> dict:
    """Run leg2_fill_mapping.py for Leg 2. Returns ok/artifacts/stdout/stderr."""
    repo_root = _find_repo_root()
    cmd = [
        sys.executable,
        "-m",
        "velocity_converter.leg2_fill_mapping",
        "--mapping",
        str(_resolve_safe(mapping, repo_root)),
        "--registry",
        str(_resolve_safe(registry, repo_root)),
        "--out",
        str(_resolve_safe(out, repo_root)),
        "--review-out",
        str(_resolve_safe(review_out, repo_root)),
    ]
    if telemetry_log:
        cmd += ["--telemetry-log", str(_resolve_safe(telemetry_log, repo_root))]
    if terminology:
        cmd += ["--terminology", str(_resolve_safe(terminology, repo_root))]

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
    if result.returncode != 0:
        return {"ok": False, "returncode": result.returncode, "stderr": result.stderr}

    artifacts = []
    for p_str in [out, review_out, telemetry_log]:
        if p_str is None:
            continue
        p = _resolve_safe(p_str, repo_root)
        if p.exists():
            artifacts.append(str(p.relative_to(repo_root)))
    return {"ok": True, "artifacts": artifacts, "stdout": result.stdout, "stderr": result.stderr}


def _warn_missing_cond_registry(suggested_path: Path) -> None:
    """Warn if a form's annotated HTML has conditionals but no registry."""
    stem = suggested_path.name
    for sfx in (".suggested.yaml", ".mapping.yaml", ".yaml"):
        if stem.endswith(sfx):
            stem = stem[: -len(sfx)]
            break
    form_dir = suggested_path.parent
    if (form_dir / f"{stem}.conditional-registry.yaml").exists():
        return
    annotated = form_dir / f"{stem}.annotated.html"
    if not annotated.exists():
        return
    n = len(set(re.findall(r'\$doc\.cond\d+', annotated.read_text(encoding="utf-8"))))
    if n == 0:
        return
    form = action_needed_dir(form_dir) / f"{stem}.conditional-form.md"
    if form.exists():
        fix = (
            f"python3 -m velocity_converter.leg0_ingest "
            f"--parse-conditional-form {form} "
            f"--output-dir {form_dir}"
        )
    else:
        fix = "(conditional-form.md not found — re-run Leg 0 first)"
    print(
        f"WARNING: {n} conditional(s) detected in {stem}.annotated.html "
        f"but no conditional-registry.yaml found.\nRun: {fix}"
    )


def run_leg4(
    suggested: "str | list[str]",
    customer_jar: str | None = None,
    datamodel_jar: str | None = None,
    compile_check: bool = True,
    output_dir: str | None = None,
) -> dict:
    """Run leg4_generate_plugin.py once for one or more mapping files.

    All forms go to a single invocation (repeated --suggested). The plugin
    .java lands in output_dir (default: the first form's directory); the first
    form writes it fresh — or updates it additively if it already exists —
    and every subsequent form is merged additively into the same file.
    Returns ok/artifacts/stdout/stderr.
    """
    repo_root = _find_repo_root()
    suggested_list = suggested if isinstance(suggested, list) else [suggested]
    suggested_paths = [_resolve_safe(s, repo_root) for s in suggested_list]

    cmd = [sys.executable, "-m", "velocity_converter.leg4_generate_plugin"]
    for sp in suggested_paths:
        _warn_missing_cond_registry(sp)
        cmd += ["--suggested", str(sp)]
    if output_dir:
        cmd += ["--output-dir", str(_resolve_safe(output_dir, repo_root))]
    if customer_jar:
        cmd += ["--customer-jar", str(_resolve_safe(customer_jar, repo_root))]
    if datamodel_jar:
        cmd += ["--datamodel-jar", str(_resolve_safe(datamodel_jar, repo_root))]
    if compile_check:
        cmd.append("--compile-check")

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
    if result.returncode != 0:
        return {"ok": False, "returncode": result.returncode, "stderr": result.stderr, "stdout": result.stdout}

    plugin_dir = (
        _resolve_safe(output_dir, repo_root) if output_dir else suggested_paths[0].parent
    )
    artifacts = []
    for sp in suggested_paths:
        stem = sp.name
        for suffix in (".suggested.yaml", ".mapping.yaml", ".yaml"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        report = sp.parent / f"{stem}.plugin-report.md"
        if report.exists():
            artifacts.append(str(report.relative_to(repo_root)))
    for java_f in sorted(plugin_dir.glob("*DocumentDataSnapshotPluginImpl.java")):
        artifacts.append(str(java_f.relative_to(repo_root)))
    return {"ok": True, "artifacts": artifacts, "stdout": result.stdout, "stderr": result.stderr}


def get_intermediate_paths(
    operation: str,
    input_html: str | None,
    output: str,
    leg2_suggested: str | None,
) -> list[Path]:
    """Return intermediate file Paths for cleanup after a successful full-pipeline run."""
    if operation not in _FULL_PIPELINE_OPS:
        return []

    if operation in ("leg1+leg2+leg3", "leg1+leg2+leg3+leg4") and input_html:
        stem = Path(input_html).stem
        base = Path(output) / stem
        # Keep .mapping.yaml — leg4 and leg3 re-runs need it
        suffixes = [".review.md"]
    elif operation == "leg0+leg2+leg3" and input_html:
        stem = Path(input_html).stem
        base = Path(output) / stem
        # Keep .mapping.yaml — it's the enriched YAML artifact
        suffixes = [".review.md"]
    elif operation == "leg2+leg3" and leg2_suggested:
        p = Path(leg2_suggested)
        stem = p.stem
        for sfx in (".suggested", ".mapping"):
            if stem.endswith(sfx):
                stem = stem[: -len(sfx)]
                break
        base = p.parent
        # Keep .mapping.yaml — leg4 and leg3 re-runs need it
        suffixes = [".review.md"]
    else:
        return []

    return [base / f"{stem}{s}" for s in suffixes]


def _velocity_to_accessor(velocity: str, category: str) -> str:
    """Mirror leg0_ingest._derive_accessor — derive the shorthand accessor key a user would write."""
    v = (velocity or "").strip()
    cat = (category or "").strip()
    if cat in ("system", "policy_data"):
        return "policy." + v[len("$data."):] if v.startswith("$data.") else v.lstrip("$")
    if cat == "quote_system":
        return "quote." + v[len("$data."):] if v.startswith("$data.") else v.lstrip("$")
    if v.startswith("$data."):
        return v[len("$data."):]
    if v.startswith("$"):
        return v[1:]
    return v


def _catalog_velocity(velocity: str, category: str) -> str:
    """Velocity path for a catalog/user accessor.

    Registry entries are historically root-relative. Quote-root documents render
    with a named ``quote`` object in renderingData, so quote accessors must land
    under ``$data.quote``.
    """
    v = (velocity or "").strip()
    cat = (category or "").strip()
    if cat == "quote_system" and v.startswith("$data."):
        return "$data.quote." + v[len("$data."):]
    return v


def build_velocity_lookup(registry_path: "str | Path") -> "dict[str, str]":
    """Build a flat lookup map: accessor shorthand (and full suffix) → velocity path.

    Two keys per registry entry:
      Pass 1 — full suffix: velocity.lstrip("$")  e.g. "data.account.data.firstName"
      Pass 2 — accessor shorthand: what list_paths shows  e.g. "account.data.firstName"
      Extra quote-data aliases — product data fields are valid on quote roots as
        quote.data.<field> and resolve deterministically to $data.quote.data.<field>.
    Pass 1 wins on collision (more specific key).
    Returns {} on any read/parse failure.
    """
    from velocity_converter.models import ContractError, PathRegistry, validate_contract

    try:
        import yaml as _yaml  # noqa: PLC0415
        data = _yaml.safe_load(Path(registry_path).read_text(encoding="utf-8")) or {}
        validate_contract(data, PathRegistry, artifact="path-registry.yaml", path=Path(registry_path))
    except ContractError as exc:
        print(f"WARNING: ignoring invalid registry (velocity lookup disabled)\n{exc}", file=sys.stderr)
        return {}
    except Exception:
        return {}

    pass1: "dict[str, str]" = {}
    pass2: "dict[str, str]" = {}

    def _collect(node: object, category: str = "") -> None:
        if isinstance(node, dict):
            v = node.get("velocity")
            cat = node.get("category") or category
            if v and isinstance(v, str):
                pass1[v.lstrip("$")] = v
                acc = _velocity_to_accessor(v, cat)
                resolved = _catalog_velocity(v, cat)
                if acc not in pass2:
                    pass2[acc] = resolved
                if cat == "policy_data" and v.startswith("$data.data."):
                    quote_acc = "quote." + v[len("$data."):]
                    quote_vel = "$data.quote." + v[len("$data."):]
                    if quote_acc not in pass2:
                        pass2[quote_acc] = quote_vel
            for child in node.values():
                _collect(child, cat)
        elif isinstance(node, list):
            for item in node:
                _collect(item, category)

    _collect(data)
    return {**pass2, **pass1}  # pass1 wins on collision


def build_velocity_meta_lookup(registry_path: "str | Path") -> "dict[str, dict]":
    """Build accessor/suffix → entry metadata, carrying DataFetcher wiring.

    Mirrors :func:`build_velocity_lookup`'s keys (full suffix, accessor
    shorthand, and quote-data aliases) but maps each to a metadata dict so
    Leg 0 can tag DataFetcher-sourced placeholders with a ``candidate`` block.
    Each value is ``{velocity, source, datafetcher_method, datafetcher_arg,
    datafetcher_key, valid_roots}``.

    DataFetcher binding is **object-level**, not per-field: one ``getAccount``
    returns the whole Account, whose ``data()`` Map serves *every*
    ``$data.account.*`` path. So the spec is keyed by ``datafetcher_key``, and
    any path under ``$data.<key>`` inherits it — there is no need for a
    per-field ``datafetcher_paths`` row. ``_validate_datafetcher_entry``
    guarantees each row's velocity starts with ``$data.<key>``, so the key is
    the first path segment. Returns ``{}`` on read failure.
    """
    from velocity_converter.models import ContractError, PathRegistry, validate_contract

    try:
        import yaml as _yaml  # noqa: PLC0415
        data = _yaml.safe_load(Path(registry_path).read_text(encoding="utf-8")) or {}
        validate_contract(data, PathRegistry, artifact="path-registry.yaml", path=Path(registry_path))
    except ContractError as exc:
        print(f"WARNING: ignoring invalid registry (velocity meta lookup disabled)\n{exc}", file=sys.stderr)
        return {}
    except Exception:
        return {}

    # Pass 0 — collect the per-key DataFetcher spec (method/arg/valid_roots are
    # consistent across all rows sharing a datafetcher_key).
    key_specs: "dict[str, dict]" = {}

    def _scan_specs(node: object) -> None:
        if isinstance(node, dict):
            if node.get("source") == "datafetcher":
                k = node.get("datafetcher_key") or ""
                if k and k not in key_specs:
                    key_specs[k] = {
                        "datafetcher_method": node.get("datafetcher_method") or "",
                        "datafetcher_arg": node.get("datafetcher_arg"),
                        "valid_roots": list(node.get("valid_roots") or []),
                    }
            for child in node.values():
                _scan_specs(child)
        elif isinstance(node, list):
            for item in node:
                _scan_specs(item)

    _scan_specs(data)

    def _meta(velocity: str) -> dict:
        seg = velocity[len("$data."):].split(".", 1)[0] if velocity.startswith("$data.") else ""
        spec = key_specs.get(seg)
        if spec:
            return {
                "velocity": velocity,
                "source": "datafetcher",
                "datafetcher_method": spec["datafetcher_method"],
                "datafetcher_arg": spec["datafetcher_arg"],
                "datafetcher_key": seg,
                "valid_roots": list(spec["valid_roots"]),
            }
        return {
            "velocity": velocity, "source": "", "datafetcher_method": "",
            "datafetcher_arg": None, "datafetcher_key": "", "valid_roots": [],
        }

    pass1: "dict[str, dict]" = {}
    pass2: "dict[str, dict]" = {}

    def _collect(node: object, category: str = "") -> None:
        if isinstance(node, dict):
            v = node.get("velocity")
            cat = node.get("category") or category
            if v and isinstance(v, str):
                pass1.setdefault(v.lstrip("$"), _meta(v))
                acc = _velocity_to_accessor(v, cat)
                pass2.setdefault(acc, _meta(_catalog_velocity(v, cat)))
                if cat == "policy_data" and v.startswith("$data.data."):
                    quote_acc = "quote." + v[len("$data."):]
                    quote_vel = "$data.quote." + v[len("$data."):]
                    pass2.setdefault(quote_acc, _meta(quote_vel))
            for child in node.values():
                _collect(child, cat)
        elif isinstance(node, list):
            for item in node:
                _collect(item, category)

    _collect(data)
    return {**pass2, **pass1}  # pass1 (full suffix) wins on collision


def resolve_dotted_path(name: str, lookup: "dict[str, str]") -> "str | None":
    """Return the velocity path for a dotted accessor name, or None on miss."""
    return lookup.get(name)


def run_list_paths(registry_path: str, out_path: str | None = None) -> str:
    """Render path catalog Markdown from the registry."""
    repo_root = _find_repo_root()
    from velocity_converter.list_paths import render_catalog  # noqa: PLC0415
    abs_registry = str(_resolve_safe(registry_path, repo_root))
    catalog = render_catalog(abs_registry)
    if out_path:
        out = _resolve_safe(out_path, repo_root)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(catalog, encoding="utf-8")
    return catalog
