"""Pure-Python tool implementations for the pipeline-orchestrator agent.

No Claude API code here — only business logic called by agent.py dispatch.
"""

import re
import subprocess
import sys
from pathlib import Path

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
            try:
                p = _resolve_safe(suggested, repo_root)
                if not p.exists():
                    errors.append(f"suggested not found: {suggested!r}")
                elif not (p.name.endswith(".mapping.yaml") or p.name.endswith(".suggested.yaml")):
                    errors.append(f"suggested must be a .mapping.yaml (or legacy .suggested.yaml) file, got: {p.name!r}")
            except ValueError as e:
                errors.append(str(e))

    if operation in ("leg2", "leg2+leg3", "leg0+leg2+leg3", "leg1+leg2", "leg1+leg2+leg3", "leg1+leg2+leg3+leg4"):
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
    if operation in ("leg0", "leg0+leg2+leg3") and input_html:
        stem = Path(input_html).stem
        base = f"{out_dir}/{stem}"
        writes += [
            f"{base}/{stem}.raw.html",
            f"{base}/{stem}.annotated.html",
            f"{base}/{stem}.mapping.yaml",
            f"{base}/{stem}.conditional-form.md",
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
            leg4_base_path = suggested
        elif operation == "leg1+leg2+leg3+leg4" and input_html:
            s = Path(input_html).stem
            leg4_base_path = f"{out_dir}/{s}/{s}.mapping.yaml"
        else:
            leg4_base_path = None
        if leg4_base_path:
            stem4 = Path(leg4_base_path).stem
            for _sfx in (".suggested", ".mapping"):
                if stem4.endswith(_sfx):
                    stem4 = stem4[: -len(_sfx)]
                    break
            base4 = str(Path(leg4_base_path).parent)
            product = _try_read_product(leg4_base_path)
            java_name = (
                f"{product}DocumentDataSnapshotPluginImpl.java"
                if product
                else "<Product>DocumentDataSnapshotPluginImpl.java"
            )
            writes += [
                f"{base4}/{java_name}",
                f"{base4}/{stem4}.plugin-report.md",
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
    compile_check: bool = True,
    keep_intermediates: bool = False,
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
        lines.append(row(f"  Suggested : {suggested}"))
    if terminology:
        lines.append(row(f"  Terminology: {terminology}"))
    lines.append("╠" + "═" * W + "╣")

    writes = _predict_writes(operation, input_html, mapping, out_dir, mode, suggested)

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
    script = repo_root / "scripts" / "leg0_ingest.py"
    cmd = [
        sys.executable,
        str(script),
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

    artifact_names = [
        f"{stem}.raw.html",
        f"{stem}.annotated.html",
        f"{stem}.mapping.yaml",
        f"{stem}.conditional-form.md",
    ]
    artifacts = [
        str((out_p / name).relative_to(repo_root))
        for name in artifact_names
        if (out_p / name).exists()
    ]
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
    telemetry_log: str | None = None,
    mode: str = "terse",
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
        "--mode",
        mode,
    ]
    if telemetry_log:
        cmd += ["--telemetry-log", str(_resolve_safe(telemetry_log, repo_root))]
    if terminology:
        cmd += ["--terminology", str(_resolve_safe(terminology, repo_root))]
    if base_suggested:
        cmd += ["--base-suggested", str(_resolve_safe(base_suggested, repo_root))]

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


def _run_leg4_single(
    suggested: str,
    customer_jar: str | None,
    datamodel_jar: str | None,
    compile_check_flag: bool,
    repo_root: Path,
) -> dict:
    """Run leg4_generate_plugin.py for a single suggested.yaml."""
    script = repo_root / "scripts" / "leg4_generate_plugin.py"
    cmd = [
        sys.executable,
        str(script),
        "--suggested",
        str(_resolve_safe(suggested, repo_root)),
    ]

    # Preflight: warn if annotated HTML has conditionals but no registry
    _suggested_path = _resolve_safe(suggested, repo_root)
    _stem = _suggested_path.name
    for _sfx in (".suggested.yaml", ".mapping.yaml", ".yaml"):
        if _stem.endswith(_sfx):
            _stem = _stem[: -len(_sfx)]
            break
    _out_dir = _suggested_path.parent
    _cond_yaml = _out_dir / f"{_stem}.conditional-registry.yaml"
    if not _cond_yaml.exists():
        _annotated = _out_dir / f"{_stem}.annotated.html"
        if _annotated.exists():
            _n = len(set(re.findall(r'\$doc\.cond\d+', _annotated.read_text(encoding="utf-8"))))
            if _n > 0:
                _form = _out_dir / f"{_stem}.conditional-form.md"
                if _form.exists():
                    _fix = (
                        f"python3 scripts/leg0_ingest.py "
                        f"--parse-conditional-form {_form} "
                        f"--output-dir {_out_dir}"
                    )
                else:
                    _fix = "(conditional-form.md not found — re-run Leg 0 first)"
                print(
                    f"WARNING: {_n} conditional(s) detected in {_stem}.annotated.html "
                    f"but no conditional-registry.yaml found.\nRun: {_fix}"
                )

    if customer_jar:
        cmd += ["--customer-jar", str(_resolve_safe(customer_jar, repo_root))]
    if datamodel_jar:
        cmd += ["--datamodel-jar", str(_resolve_safe(datamodel_jar, repo_root))]
    if compile_check_flag:
        cmd.append("--compile-check")

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
    if result.returncode != 0:
        return {"ok": False, "returncode": result.returncode, "stderr": result.stderr, "stdout": result.stdout}

    suggested_path = _resolve_safe(suggested, repo_root)
    stem = suggested_path.name
    for suffix in (".suggested.yaml", ".mapping.yaml", ".yaml"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    out_dir = suggested_path.parent
    artifacts = []
    report = out_dir / f"{stem}.plugin-report.md"
    if report.exists():
        artifacts.append(str(report.relative_to(repo_root)))
    for java_f in sorted(out_dir.glob("*DocumentDataSnapshotPluginImpl.java")):
        artifacts.append(str(java_f.relative_to(repo_root)))
    return {"ok": True, "artifacts": artifacts, "stdout": result.stdout, "stderr": result.stderr}


def run_leg4(
    suggested: "str | list[str]",
    customer_jar: str | None = None,
    datamodel_jar: str | None = None,
    compile_check: bool = True,
) -> dict:
    """Run leg4_generate_plugin.py for one or more suggested.yaml files.

    When multiple forms are passed, processes sequentially so each run reads
    the prior state — additive mode auto-activates when the Java file already exists.
    Returns ok/artifacts/stdout/stderr.
    """
    repo_root = _find_repo_root()
    suggested_list = suggested if isinstance(suggested, list) else [suggested]

    all_artifacts: list[str] = []
    all_stdout: list[str] = []

    for s in suggested_list:
        result = _run_leg4_single(s, customer_jar, datamodel_jar, compile_check, repo_root)
        if not result["ok"]:
            return result
        all_artifacts.extend(result.get("artifacts") or [])
        if result.get("stdout"):
            all_stdout.append(result["stdout"])

    return {
        "ok": True,
        "artifacts": all_artifacts,
        "stdout": "\n".join(all_stdout),
        "stderr": "",
    }


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


def build_velocity_lookup(registry_path: "str | Path") -> "dict[str, str]":
    """Build a flat lookup map: accessor shorthand (and full suffix) → velocity path.

    Two keys per registry entry:
      Pass 1 — full suffix: velocity.lstrip("$")  e.g. "data.account.data.firstName"
      Pass 2 — accessor shorthand: what list_paths shows  e.g. "account.data.firstName"
    Pass 1 wins on collision (more specific key).
    Returns {} on any read/parse failure.
    """
    try:
        import yaml as _yaml  # noqa: PLC0415
        data = _yaml.safe_load(Path(registry_path).read_text(encoding="utf-8")) or {}
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
                if acc not in pass2:
                    pass2[acc] = v
            for child in node.values():
                _collect(child, cat)
        elif isinstance(node, list):
            for item in node:
                _collect(item, category)

    _collect(data)
    return {**pass2, **pass1}  # pass1 wins on collision


def resolve_dotted_path(name: str, lookup: "dict[str, str]") -> "str | None":
    """Return the velocity path for a dotted accessor name, or None on miss."""
    return lookup.get(name)


def run_list_paths(registry_path: str, out_path: str | None = None) -> str:
    """Render path catalog Markdown from the registry."""
    repo_root = _find_repo_root()
    sys.path.insert(0, str(repo_root / "scripts"))
    from list_paths import render_catalog  # noqa: PLC0415
    abs_registry = str(_resolve_safe(registry_path, repo_root))
    catalog = render_catalog(abs_registry)
    if out_path:
        out = _resolve_safe(out_path, repo_root)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(catalog, encoding="utf-8")
    return catalog
