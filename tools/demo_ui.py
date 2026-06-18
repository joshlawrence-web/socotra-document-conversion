#!/usr/bin/env python3
"""Demo UI for the Velocity Converter pipeline — intake front-door edition.

Single-file local web app (stdlib only — no Flask):

    python3 tools/demo_ui.py            # serves http://localhost:8765
    python3 tools/demo_ui.py --port 9000

This UI tells the "Priya / ZenCover Welcome Letter" story (docs/demo-story.md):
the customer writes a normal Word letter with four markers, hands it over once,
and the pipeline gives back three fill-in-the-blank files.

Flow (five stages, left to right):
  1. Intake    — drop a .docx/.pdf → Leg -1 (suggest) + Leg 0 (scan) produce the
                 THREE human-fill files: <stem>.path-review.md,
                 <stem>.variants.csv.
  2. Fill      — click any fill file to edit it right in the browser:
                 confirm the Final: accessor lines, write the Condition: lines,
                 fill the variant rows. Save without leaving the page.
  3. Resolve   — "Resolve & ingest" runs Leg -1 (apply) → path-map, then the full
                 Leg 0 ingest WITH that path-map → the machine .mapping.yaml.
                 Human fill files are snapshotted/restored across the re-ingest so
                 customer answers are never clobbered.
  4. Generate  — parse the variants.csv → registry, then Leg 2+3
                 → .final.vm; optional toggle also runs Leg 4 (snapshot plugin).
  5. Preview   — render the .final.vm against a live tenant quote/policy (ad-hoc
                 render) and pop the PDF open. Renders against the ALREADY-deployed
                 SnapshotPlugin; needs .env.ai-documents creds at the repo root.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from velocity_converter.agent_tools import (  # noqa: E402
    run_leg0_scan,
    run_leg2,
    run_leg3,
    run_leg4,
    run_legminus1,
    run_legminus1_apply,
)
from velocity_converter.models import (  # noqa: E402
    ContractError,
    PathRegistry,
    validate_contract,
)
from velocity_converter.render_preview import (  # noqa: E402
    ENV_PREFIX,
    REFERENCE_TYPES,
    RenderPreviewError,
    load_env,
    render_template,
    require_settings,
    reveal_file,
)
from velocity_converter.socotra_config_fingerprint import (  # noqa: E402
    compute_source_config_sha256,
    iter_tracked_config_json_files,
)
from velocity_converter.workspace import action_needed_dir  # noqa: E402

INPUT_DIR = REPO_ROOT / "workspace" / "inbox"
OUTPUT_DIR = REPO_ROOT / "workspace" / "output"
CONFIG_DIR = REPO_ROOT / "socotra-config"
PATH_REGISTRY = "registry/path-registry.yaml"
CUSTOMER_JAR = "build/customer-config.jar"
DATAMODEL_JAR = "build/core-datamodel-v1.7.61.jar"

ALLOWED_UPLOAD_SUFFIXES = {".docx", ".pdf"}

# The three customer-facing hand-fill files (suffixes), in fill order.
FILL_SUFFIXES = (".path-review.md", ".variants.csv")


# --------------------------------------------------------------------------
# Pipeline helpers
# --------------------------------------------------------------------------

def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def _inbox_source(stem: str) -> Path | None:
    """Locate the original .docx/.pdf in workspace/inbox/ for a form stem."""
    for suffix in (".docx", ".pdf"):
        cand = INPUT_DIR / f"{stem}{suffix}"
        if cand.is_file():
            return cand
    return None


def _count_blank(path: Path, pattern: str) -> int:
    """Count lines matching ``pattern`` (a `^…$` regex) in a text file."""
    if not path.exists():
        return 0
    return len(re.findall(pattern, path.read_text(encoding="utf-8"), re.M))


def form_status(form_dir: Path) -> dict:
    stem = form_dir.name
    # Machine artifacts live in form_dir; the human-fill files (path review,
    # variants CSV) live in the flat action-needed/ space.
    # Surface both in the card so the demo shows everything that needs filling.
    action_dir = action_needed_dir(form_dir)
    action_files = sorted(action_dir.glob(f"{stem}.*")) if action_dir.is_dir() else []
    files = sorted(
        [f for f in form_dir.iterdir() if f.is_file() and not f.name.startswith(".")]
        + [f for f in action_files if f.is_file()],
        key=lambda f: f.name,
    )
    plugin = sorted(form_dir.glob("*DocumentDataSnapshotPluginImpl.java"))

    review_f = action_dir / f"{stem}.path-review.md"
    variants_f = action_dir / f"{stem}.variants.csv"
    pathmap_f = form_dir / f"{stem}.path-map.yaml"
    registry_f = form_dir / f"{stem}.conditional-registry.yaml"
    sidecar_f = form_dir / f"{stem}.conditional-blocks.yaml"
    mapping_f = form_dir / f"{stem}.mapping.yaml"

    # Leg -1: how many Final: accessor lines the human still has to fill.
    path_unfilled = _count_blank(review_f, r"^Final:\s*$")

    # variants.csv edited after the registry it produced → conditionals are stale.
    form_stale = (
        registry_f.exists()
        and variants_f.exists()
        and variants_f.stat().st_mtime > registry_f.stat().st_mtime
    )
    # path-review edited after the ingest that consumed it → paths are stale.
    paths_stale = (
        pathmap_f.exists()
        and review_f.exists()
        and review_f.stat().st_mtime > pathmap_f.stat().st_mtime
    )
    # Count conditional blocks the customer still has to fill. Before parse, every
    # block in the machine sidecar counts as outstanding; after parse, only the
    # registry blocks left without a condition.
    if registry_f.exists() and not form_stale:
        unfilled = len(unfilled_conditions(stem))
    elif sidecar_f.exists():
        import yaml
        unfilled = len(yaml.safe_load(sidecar_f.read_text(encoding="utf-8")) or [])
    else:
        unfilled = 0

    return {
        "stem": stem,
        "dir": _rel(form_dir),
        "files": [
            {"name": f.name, "path": _rel(f), "size": f.stat().st_size}
            for f in files
        ],
        "pathReview": review_f.exists(),
        "pathUnfilled": path_unfilled,
        "pathMap": pathmap_f.exists(),
        "pathsStale": paths_stale,
        "variants": variants_f.exists(),
        "ingested": mapping_f.exists(),
        # JS-facing flag: the single conditional fill file is now variants.csv.
        "conditionalForm": variants_f.exists(),
        "registry": registry_f.exists(),
        "template": (form_dir / f"{stem}.final.vm").exists(),
        "plugin": bool(plugin),
        "unfilled": unfilled,
        "formStale": form_stale,
        # Reference type baked into the stem suffix (e.g. Foo(quote) → quote),
        # used as the default for the live render preview (Stage 5).
        "renderType": _scope_from_stem(stem),
    }


def list_forms() -> list[dict]:
    if not OUTPUT_DIR.is_dir():
        return []
    forms = [form_status(d) for d in sorted(OUTPUT_DIR.iterdir()) if d.is_dir()]
    return [f for f in forms if f["files"]]


def do_intake(rel_path: str) -> dict:
    """Run the intake front door: Leg -1 (suggest) + Leg 0 (scan).

    Produces the two human-fill files at once — path-review.md and variants.csv.
    Mirrors the ``RUN_PIPELINE intake`` operation in agent.py.
    """
    src = (REPO_ROOT / rel_path).resolve()
    if not str(src).startswith(str(INPUT_DIR.resolve())) or not src.is_file():
        return {"ok": False, "error": "File must live in workspace/inbox/."}
    if src.suffix.lower() not in ALLOWED_UPLOAD_SUFFIXES:
        return {"ok": False, "error": "Intake needs a .docx or .pdf document."}

    stem = src.stem
    # Step 1 — Leg -1 suggest: bare {leaf} → accessor review (registry-only).
    r1 = run_legminus1(
        input_path=_rel(src),
        registry=PATH_REGISTRY,
        output_dir="workspace/output",
    )
    if not r1.get("ok"):
        return {"ok": False, "error": f"Leg -1 (suggest) failed.\n{r1.get('stderr', '')}", "stem": stem}

    # Step 2 — Leg 0 scan: the single variants.csv only, no machine
    # artifacts. Runs without a path-map (path-review isn't filled yet).
    r2 = run_leg0_scan(input_path=_rel(src), output_dir=f"workspace/output/{stem}")
    if not r2.get("ok"):
        return {"ok": False, "error": f"Leg 0 (scan) failed.\n{r2.get('stderr', '')}", "stem": stem}

    return {
        "ok": True,
        "stem": stem,
        "artifacts": (r1.get("artifacts") or []) + (r2.get("artifacts") or []),
        "stdout": (r1.get("stdout") or "") + (r2.get("stdout") or ""),
    }


def do_upload(filename: str, body: bytes) -> dict:
    name = Path(filename).name  # strip any path components
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        return {"ok": False, "error": f"Only {', '.join(sorted(ALLOWED_UPLOAD_SUFFIXES))} files are accepted."}
    if not body:
        return {"ok": False, "error": "Empty upload."}

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = INPUT_DIR / name
    dest.write_bytes(body)
    result = do_intake(_rel(dest))
    result["saved"] = _rel(dest)
    return result


def list_samples() -> list[dict]:
    if not INPUT_DIR.is_dir():
        return []
    return [
        {
            "name": f.name,
            "path": _rel(f),
            "ingested": (OUTPUT_DIR / f.stem).is_dir(),
        }
        for f in sorted(INPUT_DIR.iterdir())
        if f.is_file() and f.suffix.lower() in ALLOWED_UPLOAD_SUFFIXES
    ]


def do_resolve_ingest(stem: str) -> dict:
    """Stage 3: apply the filled path-review (Leg -1), then full Leg 0 ingest.

    Leg -1 apply parses the human-edited path-review.md into a path-map. The full
    Leg 0 ingest is then run WITH that path-map so bare {leaf} placeholders bake
    into full accessors in the .mapping.yaml. The variants.csv and
    variants.csv are snapshotted before the ingest and restored after, because
    Leg 0 rewrites them as blank stubs (it would otherwise wipe customer answers).
    """
    form_dir = OUTPUT_DIR / stem
    src = _inbox_source(stem)
    if src is None:
        return {"ok": False, "error": f"No source .docx/.pdf for '{stem}' in workspace/inbox/."}

    steps: list[dict] = []
    action_dir = action_needed_dir(form_dir)
    review = action_dir / f"{stem}.path-review.md"

    # --- Leg -1 apply (only when a path-review exists) ---
    if review.exists():
        if _count_blank(review, r"^Final:\s*$"):
            return {
                "ok": False,
                "error": f"{stem}.path-review.md still has blank Final: lines — fill them first.",
            }
        r1 = run_legminus1_apply(review=_rel(review), output_dir=f"workspace/output/{stem}")
        steps.append({"step": "Leg -1 apply — resolve paths", **r1})
        if not r1.get("ok"):
            return {"ok": False, "steps": steps, "error": "Leg -1 apply failed."}

    path_map = form_dir / f"{stem}.path-map.yaml"

    # --- snapshot the human-fill forms so the ingest can't clobber answers ---
    fill_files = [
        action_dir / f"{stem}.variants.csv",
    ]
    snapshot = {p: p.read_bytes() for p in fill_files if p.exists()}

    # --- full Leg 0 ingest (with the path-map when available) ---
    cmd = [
        sys.executable, "-m", "velocity_converter.leg0_ingest",
        "--input", str(src),
        "--output-dir", str(form_dir),
    ]
    if path_map.exists():
        cmd += ["--path-map", str(path_map)]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))

    # --- restore the customer's fills (block structure is identical per doc) ---
    for p, data in snapshot.items():
        p.write_bytes(data)

    ok = r.returncode == 0
    steps.append({
        "step": "Leg 0 ingest — extract fields + build mapping",
        "ok": ok,
        "stdout": r.stdout,
        "stderr": r.stderr,
    })
    if not ok:
        return {"ok": False, "steps": steps, "error": "Leg 0 ingest failed."}
    return {"ok": True, "steps": steps, "form": form_status(form_dir)}


MAX_PREVIEW_BYTES = 300_000


def read_file(rel_path: str) -> dict:
    target = (REPO_ROOT / rel_path).resolve()
    if not str(target).startswith(str(REPO_ROOT)) or not target.is_file():
        return {"ok": False, "error": "File not found inside the repository."}
    if target.suffix.lower() in {".docx", ".pdf"}:
        return {"ok": False, "error": "Binary file — double-click to open it natively."}
    data = target.read_bytes()
    return {
        "ok": True,
        "content": data[:MAX_PREVIEW_BYTES].decode("utf-8", "replace"),
        "truncated": len(data) > MAX_PREVIEW_BYTES,
    }


def save_fill_file(rel_path: str, content: str) -> dict:
    """Save an edited human-fill file back into action-needed/."""
    target = (REPO_ROOT / rel_path).resolve()
    action_root = (REPO_ROOT / "workspace" / "action-needed").resolve()
    if (
        not str(target).startswith(str(action_root))
        or not target.is_file()
        or not target.name.endswith(FILL_SUFFIXES)
    ):
        return {"ok": False, "error": "Only the path-review / variants fill files can be edited here."}
    target.write_text(content, encoding="utf-8")
    return {"ok": True}


def config_status() -> dict:
    """Socotra-config ↔ path-registry sync status + editable config file list."""
    reg = REPO_ROOT / PATH_REGISTRY
    embedded = product = generated = None
    if reg.exists():
        head = reg.read_text(encoding="utf-8")[:4000]
        m = re.search(r"^\s+source_config_sha256:\s*([0-9a-f]{64})", head, re.M)
        embedded = m.group(1) if m else None
        m = re.search(r"^\s+product:\s*(\S+)", head, re.M)
        product = m.group(1) if m else None
        m = re.search(r"^\s+generated_at:\s*'?([^'\n]+)", head, re.M)
        generated = m.group(1) if m else None
    live = compute_source_config_sha256(CONFIG_DIR) if CONFIG_DIR.is_dir() else None
    files = (
        [
            {
                "name": p.relative_to(CONFIG_DIR).as_posix(),
                "path": _rel(p),
                "size": p.stat().st_size,
            }
            for p in iter_tracked_config_json_files(CONFIG_DIR)
        ]
        if CONFIG_DIR.is_dir()
        else []
    )
    return {
        "ok": True,
        "product": product,
        "configDir": _rel(CONFIG_DIR),
        "registryPath": PATH_REGISTRY,
        "generatedAt": generated,
        "embedded": embedded,
        "live": live,
        "inSync": bool(embedded and live and embedded == live),
        "files": files,
    }


def rebuild_registry() -> dict:
    """Regenerate path-registry.yaml from socotra-config/.

    The checked-in registry carries hand-curated sections (quote_paths,
    datafetcher_paths) that extract_paths does not emit — those are carried
    over from the old registry, and the old file is backed up to .bak first.
    """
    import yaml

    reg = REPO_ROOT / PATH_REGISTRY
    tmp = reg.parent / (reg.name + ".new")
    cmd = [
        sys.executable, "-m", "velocity_converter.extract_paths",
        "--config-dir", str(CONFIG_DIR),
        "--output", str(tmp),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    if r.returncode != 0:
        tmp.unlink(missing_ok=True)
        return {"ok": False, "error": r.stderr or "extract_paths failed", "stdout": r.stdout}

    new = yaml.safe_load(tmp.read_text(encoding="utf-8"))
    tmp.unlink()
    preserved = []
    backup = None
    if reg.exists():
        old = yaml.safe_load(reg.read_text(encoding="utf-8")) or {}
        for key, val in old.items():
            if key not in new and isinstance(val, list) and val:
                new[key] = val
                preserved.append(f"{key} ({len(val)} paths)")
        backup = reg.parent / (reg.name + ".bak")
        shutil.copy2(reg, backup)

    try:
        validate_contract(new, PathRegistry, artifact="path-registry.yaml", path=reg)
    except ContractError as exc:
        return {"ok": False, "error": f"Merged registry failed contract validation — registry NOT replaced.\n{exc}"}

    reg.write_text(yaml.safe_dump(new, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return {
        "ok": True,
        "preserved": preserved,
        "backup": _rel(backup) if backup else None,
        "stdout": r.stdout,
        "status": config_status(),
    }


def save_config_file(rel_path: str, content: str) -> dict:
    target = (REPO_ROOT / rel_path).resolve()
    if (
        not str(target).startswith(str(CONFIG_DIR.resolve()))
        or not target.is_file()
        or target.suffix != ".json"
    ):
        return {"ok": False, "error": "Only existing .json files under socotra-config/ can be edited here."}
    try:
        json.loads(content)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"Not saved — invalid JSON: {exc}"}
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "status": config_status()}


def do_reset(stem: str) -> dict:
    """Delete a form's generated output + its human-fill files (fresh start)."""
    target = (OUTPUT_DIR / stem).resolve()
    if (
        not stem
        or target == OUTPUT_DIR.resolve()
        or not str(target).startswith(str(OUTPUT_DIR.resolve()))
        or not target.is_dir()
    ):
        return {"ok": False, "error": "Form output folder not found."}
    action_dir = action_needed_dir(target)
    shutil.rmtree(target)
    if action_dir.is_dir():
        for f in action_dir.glob(f"{stem}.*"):
            f.unlink()
    return {"ok": True}


def parse_variants(stem: str) -> dict:
    """Parse the filled variants.csv (+ sidecar) → conditional-registry.yaml."""
    form_dir = OUTPUT_DIR / stem
    csv_path = action_needed_dir(form_dir) / f"{stem}.variants.csv"
    if not csv_path.exists():
        return {"ok": False, "error": f"{csv_path.name} not found."}
    cmd = [
        sys.executable, "-m", "velocity_converter.leg0_ingest",
        "--parse-variants-csv", str(csv_path),
        "--output-dir", str(form_dir),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    return {
        "ok": r.returncode == 0,
        "stdout": r.stdout,
        "stderr": r.stderr,
        "error": r.stderr if r.returncode != 0 else None,
    }


def unfilled_conditions(stem: str) -> list:
    """Return keys of registry blocks left without a usable condition.

    Variants-only: every block carries its condition in ``variants`` (binary/
    variant → when+text; template → the when) or legacy ``conditions[]``. The CSV
    parser already rejects an unfilled block (the registry wouldn't be written),
    so this only catches a hand-edited/legacy registry with a genuinely empty
    block.
    """
    registry = OUTPUT_DIR / stem / f"{stem}.conditional-registry.yaml"
    if not registry.exists():
        return []
    import yaml

    entries = yaml.safe_load(registry.read_text(encoding="utf-8")) or []
    bad = []
    for e in entries:
        if e.get("variants") or e.get("conditions"):
            continue
        bad.append(e.get("key") or e.get("id"))
    return bad


def preflight_conditions(stem: str) -> dict | None:
    """Parse the variants.csv if the registry is missing or stale. None = fine."""
    form_dir = OUTPUT_DIR / stem
    registry = form_dir / f"{stem}.conditional-registry.yaml"
    variants = action_needed_dir(form_dir) / f"{stem}.variants.csv"
    newest_input = variants.stat().st_mtime if variants.exists() else 0.0
    stale = registry.exists() and variants.exists() and newest_input > registry.stat().st_mtime
    if variants.exists() and (not registry.exists() or stale):
        r = parse_variants(stem)
        if not r["ok"]:
            return {"ok": False, "error": f"{stem}: variants.csv parse failed.", **r}
    return None


def safe_leg4(stems: "str | list[str]") -> dict:
    """Run Leg 4 for one or more forms (one combined plugin), with guard rails.

    Refuses if any form still has unfilled conditions; on failure restores the
    pre-run .java state across all involved directories so a bad run can't
    poison later additive merges.
    """
    stems = [stems] if isinstance(stems, str) else list(stems)
    blocked = {s: bad for s in stems if (bad := unfilled_conditions(s))}
    if blocked:
        detail = "; ".join(f"{s}: condition(s) {bad}" for s, bad in blocked.items())
        return {
            "ok": False,
            "error": (
                f"Unfilled conditions — open each variants.csv, fill them in, "
                f"save, then retry. {detail}"
            ),
        }
    dirs = {OUTPUT_DIR / s for s in stems}
    snapshots = {
        p: p.read_bytes()
        for d in dirs
        for p in d.glob("*DocumentDataSnapshotPluginImpl.java")
    }
    r4 = run_leg4(
        suggested=[f"workspace/output/{s}/{s}.mapping.yaml" for s in stems],
        customer_jar=CUSTOMER_JAR,
        datamodel_jar=DATAMODEL_JAR,
        compile_check=True,
    )
    if not r4.get("ok"):
        # Leg 4 writes the .java before the compile check — restore the
        # pre-run state so a failed run can't poison later additive merges.
        for d in dirs:
            for p in d.glob("*DocumentDataSnapshotPluginImpl.java"):
                if p in snapshots:
                    p.write_bytes(snapshots[p])
                else:
                    p.unlink()
    return r4


def do_plugin_all(stems: list[str]) -> dict:
    """One combined snapshot plugin from every requested form (Leg 4 multi-form)."""
    stems = sorted(
        s for s in stems
        if (OUTPUT_DIR / s / f"{s}.mapping.yaml").exists()
    )
    if not stems:
        return {"ok": False, "error": "No forms with a mapping.yaml found."}
    for s in stems:
        err = preflight_conditions(s)
        if err:
            return err
    r4 = safe_leg4(stems)
    r4["stems"] = stems
    r4["landed_in"] = _rel(OUTPUT_DIR / stems[0]) if r4.get("ok") else None
    return r4


def do_generate(stem: str, with_plugin: bool) -> dict:
    form_dir = OUTPUT_DIR / stem
    mapping = f"workspace/output/{stem}/{stem}.mapping.yaml"
    if not (REPO_ROOT / mapping).exists():
        return {"ok": False, "error": f"{stem}.mapping.yaml not found — run “Resolve & ingest” first."}

    steps: list[dict] = []

    # Mandatory pre-flight: parse the variants.csv if the registry is
    # missing or the form was edited after the registry was last written.
    err = preflight_conditions(stem)
    if err:
        return {"ok": False, "steps": steps, **err}

    r2 = run_leg2(
        mapping=mapping,
        registry=PATH_REGISTRY,
        out=mapping,
        review_out=f"workspace/output/{stem}/{stem}.review.md",
    )
    steps.append({"step": "Leg 2 — suggest paths", **r2})
    if not r2.get("ok"):
        return {"ok": False, "steps": steps, "error": "Leg 2 failed."}

    # Leg 3 expects a .vm base — seed it from the annotated HTML if missing.
    vm_seed = form_dir / f"{stem}.vm"
    annotated = form_dir / f"{stem}.annotated.html"
    if not vm_seed.exists() and annotated.exists():
        shutil.copy2(annotated, vm_seed)

    r3 = run_leg3(
        suggested=mapping,
        out=f"workspace/output/{stem}/{stem}.final.vm",
        report_out=f"workspace/output/{stem}/{stem}.leg3-report.md",
    )
    steps.append({"step": "Leg 3 — write final.vm", **r3})
    if not r3.get("ok"):
        return {"ok": False, "steps": steps, "error": "Leg 3 failed."}

    if with_plugin:
        r4 = safe_leg4(stem)
        steps.append({"step": "Leg 4 — generate plugin", **r4})
        if not r4.get("ok"):
            return {
                "ok": False,
                "steps": steps,
                "error": r4.get("error") or "Leg 4 failed.",
                "form": form_status(form_dir),
            }

    return {"ok": True, "steps": steps, "form": form_status(form_dir)}


def do_plugin(stem: str) -> dict:
    form_dir = OUTPUT_DIR / stem
    mapping = f"workspace/output/{stem}/{stem}.mapping.yaml"
    if not (REPO_ROOT / mapping).exists():
        return {"ok": False, "error": f"{stem}.mapping.yaml not found."}

    # Same pre-flight as generate: pick up a freshly edited variants.csv.
    err = preflight_conditions(stem)
    if err:
        return err

    r4 = safe_leg4(stem)
    r4["form"] = form_status(form_dir)
    return r4


def _scope_from_stem(stem: str) -> str | None:
    """Reference type baked into the stem suffix, e.g. ``Foo(quote)`` → ``quote``.

    Returns None when the suffix is absent or not a renderable reference type.
    """
    m = re.search(r"\(([^)]+)\)\s*$", stem)
    scope = m.group(1).lower() if m else None
    return scope if scope in REFERENCE_TYPES else None


def preview_env() -> dict:
    """Live-render readiness for the UI: are creds present + which locators known.

    Cheap (reads the small .env.ai-documents once). The UI uses ``configured`` to
    enable/disable the Stage-5 Render button and ``locators`` to pre-fill the
    per-reference-type locator field.
    """
    env = load_env(REPO_ROOT)
    configured = all(env.get(f"{ENV_PREFIX}{n}") for n in ("API_URL", "TENANT_LOCATOR", "PAT"))
    tenant = env.get(f"{ENV_PREFIX}TENANT_LOCATOR") or ""
    locators = {
        t: env[f"{ENV_PREFIX}REFERENCE_{t.upper()}"]
        for t in REFERENCE_TYPES
        if env.get(f"{ENV_PREFIX}REFERENCE_{t.upper()}")
    }
    return {
        "configured": bool(configured),
        "tenant": (tenant[:8] + "…") if tenant else None,
        "locators": locators,
    }


def do_render_preview(stem: str, reference_type: str = "", reference_locator: str = "") -> dict:
    """Stage 5: render ``<stem>.final.vm`` against the live tenant (ad-hoc render).

    Renders against the ALREADY-deployed DocumentDataSnapshotPlugin — there is no
    deploy step here. Writes the rendered PDF/HTML next to the template and pops it
    open in the OS viewer (mirrors ``render_preview --open``). The reference type
    defaults to the one baked into the stem; the locator defaults to
    ``AI_DOCUMENTS_REFERENCE_<TYPE>`` when the caller leaves it blank.
    """
    form_dir = OUTPUT_DIR / stem
    template = form_dir / f"{stem}.final.vm"
    if not template.exists():
        return {"ok": False, "error": f"{stem}.final.vm not found — run Generate first."}

    env = load_env(REPO_ROOT)
    try:
        api_url, tenant_locator, token = require_settings(env)
    except RenderPreviewError as exc:
        return {"ok": False, "error": str(exc)}

    ref_type = (reference_type or _scope_from_stem(stem) or "").lower()
    if ref_type not in REFERENCE_TYPES:
        return {
            "ok": False,
            "error": (
                f"Reference type must be one of {', '.join(REFERENCE_TYPES)} — none is "
                f"baked into the stem (rename like Foo(quote)) so pass one explicitly."
            ),
        }
    locator = (reference_locator or "").strip() or env.get(
        f"{ENV_PREFIX}REFERENCE_{ref_type.upper()}", ""
    )
    if not locator:
        return {
            "ok": False,
            "error": (
                f"No {ref_type} locator — enter one in the field, or set "
                f"{ENV_PREFIX}REFERENCE_{ref_type.upper()} in .env.ai-documents."
            ),
        }

    try:
        rendered, content_type = render_template(
            api_url=api_url,
            tenant_locator=tenant_locator,
            token=token,
            template_text=template.read_text(encoding="utf-8"),
            reference_type=ref_type,
            reference_locator=locator,
            product_name=env.get(f"{ENV_PREFIX}PRODUCT_NAME"),
        )
    except RenderPreviewError as exc:
        msg = str(exc)
        if exc.body:
            msg += "\n" + exc.body[:800]
        return {"ok": False, "error": msg}

    # The render endpoint returns the PDF with an empty Content-Type header — sniff
    # the magic bytes rather than trusting the header (same as the CLI).
    is_pdf = rendered[:5] == b"%PDF-" or "pdf" in (content_type or "").lower()
    if not content_type and is_pdf:
        content_type = "application/pdf (sniffed)"
    out_path = form_dir / f"{stem}.preview.{'pdf' if is_pdf else 'html'}"
    out_path.write_bytes(rendered)
    opened = reveal_file(out_path)  # the --open beat: pop it into the OS viewer
    return {
        "ok": True,
        "out": _rel(out_path),
        "size": len(rendered),
        "contentType": content_type or "unknown type",
        "referenceType": ref_type,
        "referenceLocator": locator,
        "opened": opened,
        "form": form_status(form_dir),
    }


def do_open(rel_path: str) -> dict:
    target = (REPO_ROOT / rel_path).resolve()
    if not str(target).startswith(str(REPO_ROOT)) or not target.exists():
        return {"ok": False, "error": "File not found inside the repository."}
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, str(target)])
    return {"ok": True}


# --------------------------------------------------------------------------
# HTTP server
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter console
        pass

    def _json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/":
            data = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif path == "/api/forms":
            self._json({"ok": True, "forms": list_forms(), "preview": preview_env()})
        elif path == "/api/samples":
            self._json({"ok": True, "samples": list_samples()})
        elif path == "/api/file":
            query = urllib.parse.parse_qs(parsed.query)
            self._json(read_file(query.get("path", [""])[0]))
        elif path == "/api/config":
            self._json(config_status())
        else:
            self._json({"ok": False, "error": "Not found"}, 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == "/api/upload":
                filename = urllib.parse.unquote(self.headers.get("X-Filename", ""))
                self._json(do_upload(filename, self._body()))
                return

            payload = json.loads(self._body() or b"{}")
            if path == "/api/open":
                self._json(do_open(payload.get("path", "")))
            elif path == "/api/intake":
                self._json(do_intake(payload.get("path", "")))
            elif path == "/api/resolve-ingest":
                self._json(do_resolve_ingest(payload.get("stem", "")))
            elif path == "/api/generate":
                self._json(do_generate(payload.get("stem", ""), bool(payload.get("plugin"))))
            elif path == "/api/plugin":
                self._json(do_plugin(payload.get("stem", "")))
            elif path == "/api/render-preview":
                self._json(do_render_preview(
                    payload.get("stem", ""),
                    payload.get("referenceType", ""),
                    payload.get("referenceLocator", ""),
                ))
            elif path == "/api/parse-form":
                self._json(parse_variants(payload.get("stem", "")))
            elif path == "/api/reset":
                self._json(do_reset(payload.get("stem", "")))
            elif path == "/api/plugin-all":
                self._json(do_plugin_all(payload.get("stems") or []))
            elif path == "/api/rebuild-registry":
                self._json(rebuild_registry())
            elif path == "/api/save-fill":
                self._json(save_fill_file(payload.get("path", ""), payload.get("content", "")))
            elif path == "/api/save-config":
                self._json(save_config_file(payload.get("path", ""), payload.get("content", "")))
            else:
                self._json({"ok": False, "error": "Not found"}, 404)
        except Exception as exc:  # surface errors to the UI instead of a broken pipe
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)


# --------------------------------------------------------------------------
# Frontend (embedded)
# --------------------------------------------------------------------------

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Velocity Converter — Intake Console</title>
<style>
  :root {
    /* default = "Midnight" (the original navy/teal console look) */
    --navy-0: #050a18;
    --navy-1: #0a1228;
    --navy-2: #0f1c3d;
    --navy-3: #16264f;
    --teal: #16e0cf;
    --teal-dim: #0e9c91;
    --chartreuse: #c3f53c;
    --text: #d7e3f4;
    --text-dim: #7f93b4;
    --danger: #ff5d7a;
    --radius: 14px;
    /* surfaces + glows (themeable; default values reproduce the original) */
    --glow-1: rgba(22, 224, 207, .10);
    --glow-2: rgba(195, 245, 60, .06);
    --surface-1: rgba(22, 38, 79, .75);
    --surface-2: rgba(10, 18, 40, .92);
    --card-1: rgba(15, 28, 61, .85);
    --card-2: rgba(8, 14, 32, .95);
    --card-border: rgba(127, 147, 180, .16);
    --heading-fg: #eaf3ff;
    --body-font: -apple-system, "SF Pro Text", "Segoe UI", system-ui, sans-serif;
  }

  /* ============================ THEMES ============================ */
  /* Light — clean daylight */
  html[data-theme="light"] {
    --navy-0: #ffffff; --navy-1: #f1f5fb; --navy-2: #e6edf7; --navy-3: #d8e2f0;
    --teal: #0a8f86; --teal-dim: #57b3ac; --chartreuse: #7a9c1e;
    --text: #1c2b44; --text-dim: #5a6b88; --danger: #c8324f;
    --glow-1: rgba(10, 143, 134, .10); --glow-2: rgba(122, 156, 30, .08);
    --surface-1: #ffffff; --surface-2: #eef3fb;
    --card-1: #ffffff; --card-2: #f4f7fc;
    --card-border: rgba(28, 43, 68, .14); --heading-fg: #102038;
  }
  /* Solarized Dark */
  html[data-theme="solarized"] {
    --navy-0: #002b36; --navy-1: #073642; --navy-2: #0a4350; --navy-3: #0e5263;
    --teal: #2aa198; --teal-dim: #1f7a73; --chartreuse: #b58900;
    --text: #eee8d5; --text-dim: #93a1a1; --danger: #dc322f;
    --glow-1: rgba(42, 161, 152, .12); --glow-2: rgba(181, 137, 0, .10);
    --surface-1: rgba(7, 54, 66, .85); --surface-2: rgba(0, 43, 54, .95);
    --card-1: rgba(7, 54, 66, .9); --card-2: rgba(0, 43, 54, .96);
    --card-border: rgba(147, 161, 161, .2); --heading-fg: #fdf6e3;
  }
  /* Nord */
  html[data-theme="nord"] {
    --navy-0: #2e3440; --navy-1: #3b4252; --navy-2: #434c5e; --navy-3: #4c566a;
    --teal: #88c0d0; --teal-dim: #5e81ac; --chartreuse: #a3be8c;
    --text: #eceff4; --text-dim: #aeb7c8; --danger: #bf616a;
    --glow-1: rgba(136, 192, 208, .12); --glow-2: rgba(163, 190, 140, .10);
    --surface-1: rgba(59, 66, 82, .85); --surface-2: rgba(46, 52, 64, .95);
    --card-1: rgba(59, 66, 82, .9); --card-2: rgba(46, 52, 64, .96);
    --card-border: rgba(174, 183, 200, .2); --heading-fg: #eceff4;
  }
  /* Dracula */
  html[data-theme="dracula"] {
    --navy-0: #21222c; --navy-1: #282a36; --navy-2: #343746; --navy-3: #44475a;
    --teal: #8be9fd; --teal-dim: #6272a4; --chartreuse: #50fa7b;
    --text: #f8f8f2; --text-dim: #a9acc4; --danger: #ff5555;
    --glow-1: rgba(139, 233, 253, .12); --glow-2: rgba(80, 250, 123, .10);
    --surface-1: rgba(40, 42, 54, .85); --surface-2: rgba(33, 34, 44, .95);
    --card-1: rgba(40, 42, 54, .9); --card-2: rgba(33, 34, 44, .96);
    --card-border: rgba(98, 114, 164, .35); --heading-fg: #f8f8f2;
  }
  /* Amber terminal */
  html[data-theme="amber"] {
    --navy-0: #0a0600; --navy-1: #140d02; --navy-2: #1e1404; --navy-3: #2a1c06;
    --teal: #ffb000; --teal-dim: #b97c00; --chartreuse: #ffd166;
    --text: #ffce7a; --text-dim: #b5853a; --danger: #ff5a2a;
    --glow-1: rgba(255, 176, 0, .12); --glow-2: rgba(255, 209, 102, .08);
    --surface-1: rgba(30, 20, 4, .85); --surface-2: rgba(10, 6, 0, .95);
    --card-1: rgba(30, 20, 4, .9); --card-2: rgba(10, 6, 0, .96);
    --card-border: rgba(255, 176, 0, .25); --heading-fg: #ffd98a;
    --body-font: "SF Mono", ui-monospace, Menlo, monospace;
  }
  /* Rosé — soft pink */
  html[data-theme="rose"] {
    --navy-0: #191724; --navy-1: #1f1d2e; --navy-2: #26233a; --navy-3: #2f2b45;
    --teal: #ebbcba; --teal-dim: #c4848a; --chartreuse: #f6c177;
    --text: #e0def4; --text-dim: #a8a3c4; --danger: #eb6f92;
    --glow-1: rgba(235, 188, 186, .12); --glow-2: rgba(246, 193, 119, .10);
    --surface-1: rgba(31, 29, 46, .85); --surface-2: rgba(25, 23, 36, .95);
    --card-1: rgba(38, 35, 58, .9); --card-2: rgba(25, 23, 36, .96);
    --card-border: rgba(235, 188, 186, .22); --heading-fg: #f2eefb;
  }
  /* Ocean */
  html[data-theme="ocean"] {
    --navy-0: #04141f; --navy-1: #062430; --navy-2: #093646; --navy-3: #0c4a5e;
    --teal: #34d6e8; --teal-dim: #1f8fa0; --chartreuse: #6fe3c2;
    --text: #d4f0f6; --text-dim: #6fa3b3; --danger: #ff6b8a;
    --glow-1: rgba(52, 214, 232, .12); --glow-2: rgba(111, 227, 194, .10);
    --surface-1: rgba(6, 36, 48, .85); --surface-2: rgba(4, 20, 31, .95);
    --card-1: rgba(9, 54, 70, .9); --card-2: rgba(4, 20, 31, .96);
    --card-border: rgba(52, 214, 232, .2); --heading-fg: #e4f7fb;
  }
  /* Forest */
  html[data-theme="forest"] {
    --navy-0: #0a140d; --navy-1: #0f1f15; --navy-2: #15301f; --navy-3: #1c4129;
    --teal: #7fd88a; --teal-dim: #4a9c5a; --chartreuse: #d4e157;
    --text: #dcefdf; --text-dim: #8aab93; --danger: #e8736b;
    --glow-1: rgba(127, 216, 138, .12); --glow-2: rgba(212, 225, 87, .10);
    --surface-1: rgba(15, 31, 21, .85); --surface-2: rgba(10, 20, 13, .95);
    --card-1: rgba(21, 48, 31, .9); --card-2: rgba(10, 20, 13, .96);
    --card-border: rgba(127, 216, 138, .2); --heading-fg: #eaf7ec;
  }
  /* MySpace — rainbow, for 90-00s kids only */
  html[data-theme="myspace"] {
    --navy-0: #1a0033; --navy-1: #2a0a4a; --navy-2: #3a1060; --navy-3: #4a1878;
    --teal: #00ffea; --teal-dim: #ff00d4; --chartreuse: #fff000;
    --text: #ffffff; --text-dim: #ffb3f0; --danger: #ff0044;
    --glow-1: rgba(255, 0, 212, .22); --glow-2: rgba(0, 255, 234, .18);
    --surface-1: rgba(58, 16, 96, .82); --surface-2: rgba(26, 0, 51, .9);
    --card-1: rgba(74, 24, 120, .85); --card-2: rgba(26, 0, 51, .94);
    --card-border: #ff00d4; --heading-fg: #fff000;
    --body-font: "Comic Sans MS", "Comic Sans", "Chalkboard SE", cursive;
  }
  html[data-theme="myspace"] body {
    background:
      repeating-linear-gradient(45deg,
        rgba(255,0,212,.10) 0 22px, rgba(0,255,234,.10) 22px 44px),
      linear-gradient(135deg, #ff0066, #fff000, #00ff66, #00ffea, #6a00ff, #ff00d4, #ff0066);
    background-size: auto, 400% 400%;
    animation: msrainbow 14s ease infinite;
  }
  @keyframes msrainbow {
    0% { background-position: 0 0, 0% 50%; }
    50% { background-position: 0 0, 100% 50%; }
    100% { background-position: 0 0, 0% 50%; }
  }
  html[data-theme="myspace"] h1,
  html[data-theme="myspace"] .card h3 {
    text-shadow: 1px 1px 0 #ff00d4, -1px -1px 0 #00ffea;
  }
  html[data-theme="myspace"] .card,
  html[data-theme="myspace"] .stage { border-width: 2px; box-shadow: 0 0 22px var(--glow-1); }
  html[data-theme="myspace"] .stage-num,
  html[data-theme="myspace"] .logo { animation: msrainbow 6s linear infinite; background-size: 300% 300%; }
  * { box-sizing: border-box; }
  html, body { margin: 0; min-height: 100%; }
  body {
    background:
      radial-gradient(1100px 500px at 80% -10%, var(--glow-1), transparent 60%),
      radial-gradient(900px 500px at 5% 110%, var(--glow-2), transparent 60%),
      linear-gradient(180deg, var(--navy-0), var(--navy-1) 45%, var(--navy-0));
    color: var(--text);
    font: 15px/1.5 var(--body-font);
    padding: 32px 28px calc(34vh + 80px);
  }
  .mono { font-family: "SF Mono", ui-monospace, Menlo, monospace; }

  /* ---- header ---- */
  header { max-width: 1180px; margin: 0 auto 8px; display: flex; align-items: baseline; gap: 16px; }
  .logo {
    width: 38px; height: 38px; border-radius: 10px; align-self: center; flex: none;
    background: conic-gradient(from 210deg, var(--teal), #2b6cff, var(--chartreuse), var(--teal));
    box-shadow: 0 0 24px rgba(22, 224, 207, .45);
    -webkit-mask: radial-gradient(circle at 50% 50%, transparent 8px, #000 9px);
            mask: radial-gradient(circle at 50% 50%, transparent 8px, #000 9px);
  }
  h1 {
    margin: 0; font-size: 24px; font-weight: 650; letter-spacing: .14em; text-transform: uppercase;
    background: linear-gradient(90deg, #eaf6ff, var(--teal) 60%, var(--chartreuse));
    -webkit-background-clip: text; background-clip: text; color: transparent;
  }
  header .sub { color: var(--text-dim); letter-spacing: .26em; font-size: 11px; text-transform: uppercase; }
  #theme {
    margin-left: auto; align-self: center; cursor: pointer;
    background: var(--surface-1); color: var(--text);
    border: 1px solid var(--card-border); border-radius: 999px;
    padding: 6px 12px; font-size: 12px; font-family: inherit;
  }
  #theme:hover { border-color: var(--teal); }
  #gear { align-self: center; position: relative; font-size: 16px; }
  #gear-dot {
    position: absolute; top: 3px; right: 3px; width: 8px; height: 8px; border-radius: 50%;
    background: var(--danger); box-shadow: 0 0 8px var(--danger);
  }
  .story {
    max-width: 1180px; margin: 0 auto 22px; color: var(--text-dim); font-size: 13px;
    border-left: 2px solid rgba(22, 224, 207, .35); padding-left: 12px;
  }
  .story b { color: var(--text); font-weight: 600; }

  /* ---- pipeline rail ---- */
  .rail { max-width: 1180px; margin: 0 auto 18px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; position: relative; }
  .rail::before {
    content: ""; position: absolute; top: 34px; left: 6%; right: 6%; height: 1px; z-index: 0;
    background: linear-gradient(90deg, transparent, var(--teal-dim), var(--chartreuse), transparent);
    opacity: .5;
  }
  .stage {
    position: relative; z-index: 1;
    background: linear-gradient(165deg, var(--surface-1), var(--surface-2));
    border: 1px solid rgba(22, 224, 207, .18);
    border-radius: var(--radius);
    padding: 18px 16px 18px;
    backdrop-filter: blur(6px);
    box-shadow: 0 14px 40px rgba(2, 6, 18, .55), inset 0 1px 0 rgba(255,255,255,.04);
  }
  .stage-num {
    display: inline-flex; align-items: center; justify-content: center;
    width: 28px; height: 28px; border-radius: 8px; margin-right: 10px;
    font-size: 13px; font-weight: 700; color: var(--navy-0);
    background: linear-gradient(135deg, var(--teal), var(--chartreuse));
    box-shadow: 0 0 16px rgba(22, 224, 207, .35);
  }
  .stage h2 { display: inline; font-size: 13px; letter-spacing: .16em; text-transform: uppercase; font-weight: 600; }
  .stage p { color: var(--text-dim); font-size: 12.5px; margin: 12px 0 0; }

  /* ---- dropzone ---- */
  .drop {
    margin-top: 14px; padding: 22px 12px; text-align: center; cursor: pointer;
    border: 1.5px dashed rgba(22, 224, 207, .4); border-radius: 12px;
    color: var(--text-dim); transition: all .18s ease;
  }
  .drop:hover, .drop.armed {
    border-color: var(--chartreuse); color: var(--text);
    background: rgba(195, 245, 60, .05); box-shadow: 0 0 22px rgba(22, 224, 207, .18) inset;
  }
  .drop b { color: var(--teal); font-weight: 600; }
  .drop.busy { pointer-events: none; opacity: .55; }

  /* ---- sample chips ---- */
  .chips { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 7px; }
  .chips-label { width: 100%; color: var(--text-dim); font-size: 10.5px; letter-spacing: .18em; text-transform: uppercase; }
  .chip {
    font-size: 12px; padding: 4px 12px; border-radius: 999px; cursor: pointer;
    border: 1px solid rgba(22, 224, 207, .35); color: var(--text-dim);
    transition: all .15s ease; user-select: none;
  }
  .chip:hover { color: var(--text); border-color: var(--chartreuse); background: rgba(195, 245, 60, .06); }
  .chip .tick { color: var(--chartreuse); }

  /* ---- markers legend ---- */
  .markers { list-style: none; margin: 12px 0 0; padding: 0; font-size: 12px; }
  .markers li { margin: 5px 0; color: var(--text-dim); }
  .markers code { color: var(--chartreuse); font-family: "SF Mono", ui-monospace, Menlo, monospace; }

  /* ---- forms board ---- */
  .board { max-width: 1180px; margin: 26px auto 0; display: grid; grid-template-columns: 1fr; gap: 22px; }
  .card {
    background: linear-gradient(170deg, var(--card-1), var(--card-2));
    border: 1px solid var(--card-border);
    border-radius: var(--radius); padding: 18px 18px 16px;
    box-shadow: 0 12px 34px rgba(2, 6, 18, .5);
  }
  .card.flash { animation: flash 1.2s ease; }
  @keyframes flash { 0% { border-color: var(--chartreuse); box-shadow: 0 0 30px rgba(195,245,60,.35); } 100% {} }
  .card h3 { margin: 0 0 10px; font-size: 16px; font-weight: 650; color: var(--heading-fg); word-break: break-all; }
  .pills { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin-bottom: 12px; }
  .pill {
    font-size: 10.5px; letter-spacing: .08em; text-transform: uppercase; font-weight: 650;
    padding: 3px 9px; border-radius: 999px; border: 1px solid rgba(127,147,180,.3); color: var(--text-dim);
  }
  .pill--done { border-color: var(--teal); color: var(--teal); background: rgba(22, 224, 207, .08); }
  .pill--next { border-color: var(--chartreuse); color: var(--chartreuse); background: rgba(195, 245, 60, .08); }
  .pill--stale { border-color: var(--chartreuse); color: var(--chartreuse); background: rgba(195, 245, 60, .08); }
  .pill--warn { border-color: var(--danger); color: var(--danger); background: rgba(255, 93, 122, .07); }
  .pill--pending { opacity: .35; }
  .pill-sep { color: var(--text-dim); font-size: 12px; user-select: none; padding: 0 2px; }
  .next-step {
    font-size: 13px; font-weight: 650; padding: 10px 12px; border-radius: 10px;
    margin-bottom: 10px; border-left: 3px solid var(--chartreuse);
    background: rgba(195, 245, 60, .08); color: var(--chartreuse);
  }
  .next-step--warn { border-color: var(--danger); color: var(--danger); background: rgba(255, 93, 122, .08); }
  .next-step--hot  { border-color: var(--chartreuse); color: var(--chartreuse); }
  .next-step--done { border-color: var(--teal); color: var(--teal); background: rgba(22, 224, 207, .08); }
  .next-step--next { border-color: var(--chartreuse); }

  .files { border-top: 1px solid rgba(127,147,180,.14); margin: 0 -6px; padding-top: 6px; max-height: 230px; overflow: auto; }
  .file {
    display: flex; justify-content: space-between; gap: 12px; align-items: center;
    padding: 6px 8px; border-radius: 8px; cursor: pointer; user-select: none;
    font-size: 12.5px; color: var(--text);
  }
  .file:hover { background: rgba(22, 224, 207, .08); }
  .file .nm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .file .sz { color: var(--text-dim); font-size: 11px; flex: none; }
  .file.fill .nm { color: var(--chartreuse); }
  .file.key .nm { color: var(--teal); }
  .file.urgent { background: rgba(255, 93, 122, .07); }
  .file.urgent .nm { color: var(--danger); }
  .hint { color: var(--text-dim); font-size: 11.5px; margin: 8px 2px 12px; }

  .actions { display: flex; gap: 10px; align-items: center; margin-top: 12px; flex-wrap: wrap; }
  button {
    font: inherit; font-size: 13px; font-weight: 650; letter-spacing: .04em;
    padding: 9px 16px; border-radius: 10px; cursor: pointer; border: 1px solid transparent;
    transition: all .15s ease;
  }
  .btn-primary {
    color: var(--navy-0); background: linear-gradient(135deg, var(--teal), var(--chartreuse));
    box-shadow: 0 4px 18px rgba(22, 224, 207, .35);
  }
  .btn-primary:hover:not(:disabled) { filter: brightness(1.1); transform: translateY(-1px); }
  .btn-ghost { background: transparent; color: var(--teal); border-color: rgba(22, 224, 207, .45); }
  .btn-ghost:hover:not(:disabled) { background: rgba(22, 224, 207, .1); }
  .iconbtn { padding: 7px 10px; font-size: 14px; line-height: 1; }
  button:disabled { opacity: .45; cursor: not-allowed; }
  .chk { display: flex; align-items: center; gap: 7px; font-size: 12.5px; color: var(--text-dim); cursor: pointer; }
  .chk input { accent-color: var(--chartreuse); width: 15px; height: 15px; }

  /* Stage 5 — live render preview controls (one row under the actions) */
  .render-row {
    display: flex; gap: 9px; align-items: center; flex-wrap: wrap;
    margin-top: 10px; padding-top: 11px; border-top: 1px dashed rgba(127, 147, 180, .25);
  }
  .render-label { font-size: 11.5px; letter-spacing: .04em; color: var(--text-dim); }
  .render-label b { color: var(--teal); }
  .render-loc {
    flex: 1; min-width: 150px; font-size: 12px; padding: 7px 10px;
    border-radius: 9px; border: 1px solid rgba(127, 147, 180, .3);
    background: var(--navy-0); color: var(--text);
  }
  .render-loc:focus { outline: none; border-color: var(--teal); }
  .render-loc:disabled { opacity: .5; }

  .spin {
    width: 15px; height: 15px; border-radius: 50%; flex: none; display: inline-block;
    border: 2px solid rgba(22,224,207,.25); border-top-color: var(--chartreuse);
    animation: rot .7s linear infinite; vertical-align: -3px; margin-right: 8px;
  }
  @keyframes rot { to { transform: rotate(360deg); } }

  /* ---- console ---- */
  #console {
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 50;
    background: rgba(5, 10, 24, .92); backdrop-filter: blur(10px);
    border-top: 1px solid rgba(22, 224, 207, .25);
    max-height: 34vh; overflow: auto; padding: 10px 26px 14px;
    font-size: 12px;
  }
  #console .row { display: flex; gap: 10px; padding: 2px 0; }
  #console .t { color: var(--text-dim); flex: none; }
  #console .ok { color: var(--teal); }
  #console .warn { color: var(--chartreuse); }
  #console .err { color: var(--danger); }
  #console-title {
    position: sticky; top: 0; padding: 2px 0 6px; background: inherit;
    color: var(--text-dim); letter-spacing: .22em; font-size: 10px; text-transform: uppercase;
    display: flex; align-items: center; justify-content: space-between; cursor: pointer;
    user-select: none;
  }
  #console-toggle {
    background: none; border: 0; cursor: pointer; padding: 2px 6px;
    color: var(--teal); font: inherit; letter-spacing: .12em;
  }
  #console-toggle:hover { color: var(--chartreuse); }
  body.console-collapsed #console { max-height: none; overflow: visible; }
  body.console-collapsed #console .row { display: none; }
  .empty { max-width: 1180px; margin: 40px auto; text-align: center; color: var(--text-dim); }
  .toolbar {
    max-width: 1180px; margin: 26px auto -6px; display: flex; gap: 10px; align-items: center;
  }
  .toolbar[hidden] { display: none; }

  /* ---- preview panel ---- */
  #preview {
    position: fixed; top: 0; right: 0; bottom: 0; z-index: 60;
    width: min(720px, 56vw); display: flex; flex-direction: column;
    background: rgba(7, 13, 30, .97); backdrop-filter: blur(14px);
    border-left: 1px solid rgba(22, 224, 207, .35);
    box-shadow: -30px 0 70px rgba(0, 0, 0, .55);
    animation: slide .18s ease;
  }
  @keyframes slide { from { transform: translateX(24px); opacity: 0; } }
  #preview[hidden] { display: none; }
  #preview-ta {
    flex: 1; margin: 0; padding: 16px 18px 60px; border: none; outline: none; resize: none;
    background: rgba(195, 245, 60, .03); color: var(--text);
    font: 12px/1.55 "SF Mono", ui-monospace, Menlo, monospace;
  }

  /* ---- system drawer ---- */
  #system {
    position: fixed; top: 0; right: 0; bottom: 0; z-index: 55;
    width: min(420px, 90vw); display: flex; flex-direction: column;
    background: rgba(7, 13, 30, .97); backdrop-filter: blur(14px);
    border-left: 1px solid rgba(22, 224, 207, .35);
    box-shadow: -30px 0 70px rgba(0, 0, 0, .55);
    animation: slide .18s ease;
  }
  #system[hidden] { display: none; }
  #system-head {
    display: flex; align-items: center; gap: 10px;
    padding: 14px 18px; border-bottom: 1px solid rgba(127, 147, 180, .18);
    letter-spacing: .22em; font-size: 12px; text-transform: uppercase; color: var(--text-dim);
  }
  #system-body { flex: 1; overflow: auto; padding: 16px 18px 60px; font-size: 13px; }
  .sys-row { margin-bottom: 10px; color: var(--text-dim); }
  .sys-row b { color: var(--text); }
  .sync-badge {
    display: inline-block; padding: 5px 12px; border-radius: 999px; margin: 4px 0 6px;
    font-size: 11.5px; font-weight: 650; letter-spacing: .08em; text-transform: uppercase;
  }
  .sync-badge.good { color: var(--teal); border: 1px solid var(--teal); background: rgba(22, 224, 207, .08); }
  .sync-badge.bad { color: var(--danger); border: 1px solid var(--danger); background: rgba(255, 93, 122, .08); }
  .fp { color: var(--text-dim); font-size: 11px; word-break: break-all; }
  #preview-head {
    display: flex; align-items: center; gap: 10px;
    padding: 14px 18px; border-bottom: 1px solid rgba(127, 147, 180, .18);
  }
  #preview-name { font-size: 13px; color: var(--chartreuse); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  #preview-body {
    flex: 1; overflow: auto; margin: 0; padding: 16px 18px 60px;
    font-size: 12px; line-height: 1.55; white-space: pre-wrap; word-break: break-word;
    color: var(--text); font-family: "SF Mono", ui-monospace, Menlo, monospace;
  }
</style>
</head>
<body>

<header>
  <div class="logo"></div>
  <h1>Velocity Converter</h1>
  <div class="sub">Socotra &middot; document intake console</div>
  <select id="theme" title="Theme" aria-label="Theme">
    <option value="midnight">🌌 Midnight</option>
    <option value="light">☀️ Light</option>
    <option value="solarized">🟤 Solarized</option>
    <option value="nord">🧊 Nord</option>
    <option value="dracula">🧛 Dracula</option>
    <option value="amber">🟠 Amber Terminal</option>
    <option value="rose">🌹 Rosé</option>
    <option value="ocean">🌊 Ocean</option>
    <option value="forest">🌲 Forest</option>
    <option value="myspace">🌈 MySpace (90-00s kids only)</option>
  </select>
  <button class="btn-ghost iconbtn" id="gear" title="System — Socotra config &amp; path registry">⚙<span id="gear-dot" hidden></span></button>
</header>

<div class="story">
  <b>Write the letter like you'd write it to a person.</b> Wherever a real value goes, leave a marker.
  Hand it over once — the pipeline gives back three fill-in-the-blank files. Fill them like a form; no code.
</div>

<div class="rail">
  <div class="stage">
    <span class="stage-num">1</span><h2>Intake</h2>
    <p>Drop a Word/PDF letter. Leg&nbsp;-1 + Leg&nbsp;0 emit the three customer fill-in files at once.</p>
    <div class="drop" id="drop">Drop a <b>.docx</b> / <b>.pdf</b> here<br>or click to browse</div>
    <input type="file" id="fileInput" accept=".docx,.pdf" multiple hidden>
    <div class="chips" id="samples"></div>
  </div>
  <div class="stage">
    <span class="stage-num">2</span><h2>Fill</h2>
    <p>Click a <b style="color:var(--chartreuse)">fill file</b> in a card to edit it in-browser:</p>
    <ul class="markers">
      <li><code>path-review.md</code> — confirm the <code>Final:</code> accessor lines</li>
      <li><code>variants.csv</code> — fill the <code>when</code> condition (and variant <code>text</code>) for every conditional block</li>
    </ul>
  </div>
  <div class="stage">
    <span class="stage-num">3</span><h2>Resolve</h2>
    <p>“Resolve &amp; ingest” applies your paths (Leg&nbsp;-1) then runs Leg&nbsp;0 with the path-map to build the machine <b style="color:var(--teal)">.mapping.yaml</b>.</p>
  </div>
  <div class="stage">
    <span class="stage-num">4</span><h2>Generate</h2>
    <p>Parse the conditions, then Legs&nbsp;2&nbsp;+&nbsp;3 write the production <b style="color:var(--teal)">.final.vm</b>. Optionally build the snapshot plugin (Leg&nbsp;4).</p>
  </div>
  <div class="stage">
    <span class="stage-num">5</span><h2>Preview</h2>
    <p>Render the <b style="color:var(--teal)">.final.vm</b> against a live quote/policy on the tenant and pop the PDF open. Needs the plugin <b>deployed</b> + <span class="mono">.env.ai-documents</span> creds.</p>
  </div>
</div>

<div class="toolbar" id="toolbar" hidden>
  <span class="chips-label" style="width:auto" id="toolbar-label"></span>
  <span style="flex:1"></span>
  <button class="btn-primary" id="gen-all">Generate all templates</button>
  <button class="btn-ghost" id="plugin-all" title="One combined DocumentDataSnapshotPlugin from every form (Leg 4 multi-form)">Build combined plugin</button>
</div>

<div class="board" id="board"></div>
<div class="empty" id="empty" hidden>No documents yet — drop a <b>.docx</b> / <b>.pdf</b> above to start the intake.</div>

<div id="system" hidden>
  <div id="system-head">
    System
    <span style="flex:1"></span>
    <button class="btn-ghost iconbtn" id="system-close" title="Close (Esc)">✕</button>
  </div>
  <div id="system-body">
    <div class="sys-row">Product <b id="sys-product">—</b></div>
    <div class="sys-row">Config <b class="mono" id="sys-dir">—</b></div>
    <div id="sys-sync"></div>
    <div class="fp" id="sys-fp"></div>
    <div class="actions" style="margin:14px 0 18px">
      <button class="btn-primary" id="sys-rebuild">Rebuild registry</button>
      <button class="btn-ghost" id="sys-openconfig">Open config folder</button>
    </div>
    <div class="chips-label" style="margin-bottom:6px">Config files — click to view / edit</div>
    <div class="files" id="sys-files" style="max-height:none"></div>
    <div class="hint" style="margin-top:14px">Changing a config file marks the registry stale —
      rebuild it before the next Leg&nbsp;2 run. Hand-curated registry sections
      (quote / DataFetcher paths) are preserved across rebuilds; the previous
      registry is kept as <span class="mono">.bak</span>.</div>
  </div>
</div>

<div id="preview" hidden>
  <div id="preview-head">
    <span id="preview-name" class="mono"></span>
    <span style="flex:1"></span>
    <button class="btn-ghost" id="preview-edit" hidden>Edit</button>
    <button class="btn-primary" id="preview-save" hidden>Save</button>
    <button class="btn-ghost" id="preview-open">Open natively</button>
    <button class="btn-ghost iconbtn" id="preview-close" title="Close (Esc)">✕</button>
  </div>
  <pre id="preview-body"></pre>
  <textarea id="preview-ta" spellcheck="false" hidden></textarea>
</div>

<div id="console"><div id="console-title" onclick="toggleConsole()"><span>Pipeline log</span><button id="console-toggle" type="button" aria-expanded="true">Hide ▾</button></div></div>

<script>
/* ---- theme picker (persisted in localStorage) ---- */
(function () {
  const sel = document.getElementById('theme');
  const saved = localStorage.getItem('vc-theme') || 'midnight';
  const apply = (t) => {
    if (t === 'midnight') document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme', t);
  };
  sel.value = saved;
  apply(saved);
  sel.addEventListener('change', () => {
    localStorage.setItem('vc-theme', sel.value);
    apply(sel.value);
  });
})();

const board = document.getElementById('board');
const consoleEl = document.getElementById('console');
const drop = document.getElementById('drop');
const fileInput = document.getElementById('fileInput');
const busy = new Set();
// Stage-5 live-render readiness (creds + per-reference-type locators), from /api/forms.
let previewCfg = { configured: false, tenant: null, locators: {} };

function log(msg, cls) {
  const row = document.createElement('div');
  row.className = 'row';
  const t = new Date().toTimeString().slice(0, 8);
  row.innerHTML = `<span class="t mono">${t}</span><span class="${cls || ''}">${msg}</span>`;
  consoleEl.appendChild(row);
  consoleEl.scrollTop = consoleEl.scrollHeight;
  syncConsolePad();
}

// Reserve page space equal to the fixed console's real height so the last
// document card always clears it and the full board is scrollable into view.
function syncConsolePad() {
  document.body.style.paddingBottom = (consoleEl.offsetHeight + 40) + 'px';
}
window.addEventListener('resize', syncConsolePad);

function toggleConsole() {
  const collapsed = document.body.classList.toggle('console-collapsed');
  const btn = document.getElementById('console-toggle');
  btn.textContent = collapsed ? 'Show ▴' : 'Hide ▾';
  btn.setAttribute('aria-expanded', String(!collapsed));
  if (!collapsed) consoleEl.scrollTop = consoleEl.scrollHeight;
  syncConsolePad();
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  return res.json();
}

function esc(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
function kb(n) { return n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB'; }

function stepPill(label, state) {
  // state: 'done' | 'next' | 'warn' | 'pending' | 'stale'
  return `<span class="pill pill--${state}" title="${esc(label)}">${label}</span>`;
}

function pipelinePills(f) {
  const intakeDone = f.pathReview || f.conditionalForm;
  const pathsState = f.pathUnfilled > 0 ? 'warn'
    : f.pathsStale ? 'stale'
    : f.pathMap ? 'done'
    : (f.pathReview ? 'next' : 'pending');
  const ingestState = f.ingested ? (f.pathsStale ? 'stale' : 'done')
    : ((f.pathReview && f.pathUnfilled === 0) ? 'next' : 'pending');
  // Only unfilled conditions in an up-to-date registry are a true "to fill" state;
  // a filled-but-unparsed CSV is "next" (Generate will parse it), not a blank.
  const condsBlocking = f.registry && !f.formStale && f.unfilled > 0;
  const conditionsState = !f.ingested ? 'pending'
    : condsBlocking ? 'warn'
    : f.formStale ? 'stale'
    : f.registry ? 'done'
    : (f.conditionalForm ? 'next' : 'pending');
  const conditionsDone = f.registry && f.unfilled === 0 && !f.formStale;
  const templateState = f.template ? (f.unfilled > 0 ? 'warn' : 'done')
    : (f.ingested && conditionsDone ? 'next' : 'pending');
  const pluginState = f.plugin ? (f.unfilled > 0 ? 'warn' : 'done')
    : (f.template && f.unfilled === 0 ? 'next' : 'pending');
  return [
    stepPill('Intake', intakeDone ? 'done' : 'next'),
    stepPill(f.pathUnfilled > 0 ? `Paths (${f.pathUnfilled} to fill)` : 'Paths', pathsState),
    stepPill('Ingest', ingestState),
    stepPill(condsBlocking ? `Conditions (${f.unfilled} to fill)` : 'Conditions', conditionsState),
    stepPill('Template', templateState),
    stepPill('Plugin', pluginState),
  ].join('<span class="pill-sep" aria-hidden="true">›</span>');
}

function nextStep(f) {
  if (!f.pathReview && !f.conditionalForm)
    return { text: 'Run intake to start', severity: 'next' };
  if (f.pathUnfilled > 0)
    return {
      text: `Confirm ${f.pathUnfilled} accessor${f.pathUnfilled > 1 ? 's' : ''} in ${f.stem}.path-review.md`,
      severity: 'warn',
      highlightFile: `${f.stem}.path-review.md`,
    };
  if (!f.ingested)
    return { text: 'Resolve paths & ingest (Leg -1 apply → Leg 0)', severity: 'next' };
  if (f.pathsStale)
    return { text: 'Path review changed — re-run “Resolve & ingest”', severity: 'hot' };
  if (f.registry && !f.formStale && f.unfilled > 0)
    return {
      text: `Fill ${f.unfilled} condition${f.unfilled > 1 ? 's' : ''} in ${f.stem}.variants.csv`,
      severity: 'warn',
      highlightFile: `${f.stem}.variants.csv`,
    };
  if (f.formStale)
    return { text: 'Variants CSV changed — re-parse before generating', severity: 'hot' };
  if (!f.registry)
    return { text: 'Generate the template (parses conditions first)', severity: 'next' };
  if (!f.template)
    return { text: 'Generate template (Leg 2 + 3)', severity: 'next' };
  if (!f.plugin)
    return { text: 'Generate plugin (Leg 4)', severity: 'next' };
  return { text: 'Pipeline complete', severity: 'done' };
}

const chkState = new Map();

function render(forms) {
  document.getElementById('empty').hidden = forms.length > 0;
  board.innerHTML = '';
  for (const f of forms) {
    const card = document.createElement('div');
    card.className = 'card';
    card.dataset.stem = f.stem;
    card.dataset.dir = f.dir;
    const isBusy = busy.has(f.stem);
    const plugChecked = chkState.has(f.stem) ? chkState.get(f.stem) : f.plugin;
    const step = nextStep(f);

    const fileRows = f.files.map(file => {
      const fill = /\.(path-review\.md|variants\.csv)$/.test(file.name);
      const key = file.name.endsWith('.final.vm') || file.name.endsWith('.mapping.yaml');
      const urgent = step.highlightFile && file.name === step.highlightFile;
      return `<div class="file ${fill ? 'fill' : ''} ${key ? 'key' : ''} ${urgent ? 'urgent' : ''}" data-path="${esc(file.path)}" title="Click to view / edit · double-click to open natively">
        <span class="nm mono">${esc(file.name)}</span><span class="sz">${kb(file.size)}</span></div>`;
    }).join('');

    // Stage-appropriate primary action.
    let primary = '';
    if (!f.ingested || f.pathsStale) {
      const blocked = f.pathUnfilled > 0;
      const blockTitle = blocked ? ` title="Confirm the path-review accessors first"` : '';
      primary = `<button class="btn-primary" data-act="resolve" ${isBusy || blocked ? 'disabled' : ''}${blockTitle}>
        ${isBusy ? '<span class="spin"></span>Running…' : (f.pathsStale && f.ingested ? 'Re-resolve &amp; ingest' : 'Resolve &amp; ingest')}
      </button>`;
    }
    let generate = '';
    if (f.ingested) {
      // Only genuinely-unfilled conditions in an up-to-date registry block Generate.
      // A filled-but-unparsed (or stale) CSV must NOT block — Generate's pre-flight
      // parses it first, and a real blank fails the parse with a clear message.
      const blocked = f.registry && !f.formStale && f.unfilled > 0;
      const blockTitle = blocked ? ` title="Fill ${f.unfilled} condition${f.unfilled > 1 ? 's' : ''} first"` : '';
      generate = `<button class="btn-primary" data-act="generate" ${isBusy || blocked ? 'disabled' : ''}${blockTitle}>
          ${isBusy ? '<span class="spin"></span>Running…' : (f.formStale && !blocked ? 'Re-parse &amp; generate' : (f.template ? 'Regenerate template' : 'Generate template'))}
        </button>
        <label class="chk"><input type="checkbox" data-chk="plugin" ${plugChecked ? 'checked' : ''}> + plugin (Leg 4)</label>
        <button class="btn-ghost" data-act="plugin" ${isBusy || blocked ? 'disabled' : ''}${blockTitle}>Plugin only</button>`;
    }

    // Stage 5 — live render preview (only once a .final.vm exists).
    let renderRow = '';
    if (f.template) {
      const rtype = f.renderType || '';
      const loc = (previewCfg.locators && previewCfg.locators[rtype]) || '';
      let disabled = isBusy, title = '';
      if (!previewCfg.configured) {
        disabled = true;
        title = ' title="Set up .env.ai-documents (creds) at the repo root to enable the live render"';
      } else if (!rtype) {
        disabled = true;
        title = ' title="No reference type in the stem — rename the document like Foo(quote) to render"';
      }
      const locLabel = rtype ? `Preview against <b>${esc(rtype)}</b>` : 'Preview <i>(no reference type in stem)</i>';
      renderRow = `<div class="render-row">
          <span class="render-label">${locLabel}</span>
          <input class="render-loc mono" data-loc type="text" spellcheck="false"
                 placeholder="${rtype ? esc(rtype) + ' locator' + (loc ? '' : ' (or set in .env)') : 'reference locator'}"
                 value="${esc(loc)}" ${previewCfg.configured && rtype ? '' : 'disabled'}>
          <button class="btn-ghost" data-act="render" ${disabled ? 'disabled' : ''}${title}>Render preview</button>
        </div>`;
    }

    card.innerHTML = `
      <h3>${esc(f.stem)}</h3>
      <div class="next-step next-step--${step.severity}">→ ${esc(step.text)}</div>
      <div class="pills">${pipelinePills(f)}</div>
      <div class="files">${fileRows}</div>
      <div class="hint">Click a fill file to edit it in-browser — double-click any file to open it natively</div>
      <div class="actions">
        ${primary}
        ${generate}
        <span style="flex:1"></span>
        <button class="btn-ghost iconbtn" data-act="folder" title="Open output folder">📂</button>
        <button class="btn-ghost iconbtn" data-act="reset" title="Delete generated outputs + fill files for this form">🗑</button>
      </div>
      ${renderRow}`;
    board.appendChild(card);
  }
}

let lastSnapshot = '';
let formStems = [];
async function refresh() {
  const data = await api('/api/forms');
  if (!data.ok) return;
  previewCfg = data.preview || previewCfg;
  formStems = data.forms.map(f => f.stem);
  const toolbar = document.getElementById('toolbar');
  toolbar.hidden = data.forms.length < 2;
  if (!toolbar.hidden) {
    const unfilled = data.forms.reduce((n, f) =>
      n + ((f.registry && !f.formStale ? f.unfilled : 0) || 0) + (f.pathUnfilled || 0), 0);
    document.getElementById('toolbar-label').innerHTML =
      `${data.forms.length} forms` +
      (unfilled ? ` · <span style="color:var(--danger)">${unfilled} blanks still to fill</span>` : ' · all blanks filled');
  }
  const snap = JSON.stringify(data.forms) + '|' + [...busy].join() + '|' + JSON.stringify(previewCfg);
  if (snap === lastSnapshot) return;
  lastSnapshot = snap;
  render(data.forms);
}

let samplePaths = [];
async function loadSamples() {
  const r = await api('/api/samples');
  const el = document.getElementById('samples');
  if (!r.ok || !r.samples.length) { el.innerHTML = ''; samplePaths = []; return; }
  samplePaths = r.samples.map(s => s.path);
  el.innerHTML = '<span class="chips-label">or run intake on a sample</span>' + r.samples.map(s =>
    `<span class="chip" data-path="${esc(s.path)}" title="${s.ingested ? 'Already started — click to re-run intake' : 'Click to run intake (Leg -1 + Leg 0 scan)'}">${s.ingested ? '<span class="tick">✓</span> ' : ''}${esc(s.name)}</span>`
  ).join('') + (r.samples.length > 1
    ? `<span class="chip" data-all="1" title="Run intake over every sample document"><span class="tick">⚡</span> Intake all (${r.samples.length})</span>`
    : '');
}

async function intakeSample(path) {
  const name = path.split('/').pop();
  drop.innerHTML = `<span class="spin"></span>Intake <b>${esc(name)}</b> (Leg -1 + Leg 0 scan)…`;
  log(`Intake <b>${esc(name)}</b> → Leg -1 (suggest) + Leg 0 (scan)…`);
  const r = await api('/api/intake', { method: 'POST', body: JSON.stringify({ path }) });
  if (r.ok) {
    log(`✓ Intake <b>${esc(r.stem)}</b> → ${(r.artifacts || []).length} fill files in <span class="mono">workspace/action-needed/</span>`, 'ok');
    log(`Next: open the <b>path-review</b> and <b>variants</b> files in the card, fill them, save.`, 'warn');
  } else {
    log(`✗ ${esc(r.error || 'Intake failed')}`, 'err');
  }
  await refresh();
}

document.getElementById('samples').addEventListener('click', async (e) => {
  const chip = e.target.closest('.chip');
  if (!chip) return;
  const paths = chip.dataset.all ? samplePaths : [chip.dataset.path];
  drop.classList.add('busy');
  if (chip.dataset.all) log(`<b>Multi-intake</b> — running intake over ${paths.length} documents…`);
  for (const p of paths) await intakeSample(p);
  if (chip.dataset.all) log(`<b>Multi-intake complete</b> — ${paths.length} forms ready to fill.`, 'warn');
  drop.classList.remove('busy');
  drop.innerHTML = 'Drop a <b>.docx</b> / <b>.pdf</b> here<br>or click to browse';
  loadSamples();
});

/* ---- batch toolbar ---- */
document.getElementById('gen-all').addEventListener('click', async () => {
  const stems = [...formStems];
  log(`<b>Generate all</b> — ${stems.length} forms (Leg 2 → 3 each)…`);
  let okCount = 0;
  for (const stem of stems) {
    busy.add(stem); refresh();
    if (await generateForm(stem, false)) okCount++;
    busy.delete(stem);
  }
  await refresh();
  log(`<b>Generate all finished</b> — ${okCount}/${stems.length} templates written.`, okCount === stems.length ? 'ok' : 'warn');
});

document.getElementById('plugin-all').addEventListener('click', async () => {
  const stems = [...formStems];
  log(`<b>Combined plugin</b> — merging ${stems.length} forms into one DocumentDataSnapshotPlugin (Leg 4)…`);
  stems.forEach(s => busy.add(s)); refresh();
  const r = await api('/api/plugin-all', { method: 'POST', body: JSON.stringify({ stems }) });
  stems.forEach(s => busy.delete(s));
  if (r.ok) {
    log(`✓ Combined plugin built from ${r.stems.length} forms → landed in <span class="mono">${esc(r.landed_in)}/</span>`, 'ok');
    for (const a of (r.artifacts || [])) log(`&nbsp;&nbsp;<span class="mono">${esc(a)}</span>`, 'ok');
  } else {
    log(esc(r.error || 'Combined plugin failed'), 'err');
  }
  await refresh();
});

/* ---- preview panel (with in-place editing of fill + config files) ---- */
const previewEl = document.getElementById('preview');
const previewBody = document.getElementById('preview-body');
const previewTa = document.getElementById('preview-ta');
const previewEditBtn = document.getElementById('preview-edit');
const previewSaveBtn = document.getElementById('preview-save');
let previewPath = null;

const isFill = (path) => /\/(.*)\.(path-review\.md|variants\.csv)$/.test(path);
const isConfig = (path) => path.startsWith('socotra-config/') && path.endsWith('.json');
const isEditable = (path, truncated) => !truncated && (isFill(path) || isConfig(path));

function exitEditMode() {
  previewTa.hidden = true;
  previewBody.hidden = false;
  previewSaveBtn.hidden = true;
  previewEditBtn.hidden = !previewPath || !isEditable(previewPath, false);
}

async function openNative(path) {
  log(`Opening <span class="mono">${esc(path)}</span> …`);
  const r = await api('/api/open', { method: 'POST', body: JSON.stringify({ path }) });
  if (!r.ok) log(r.error || 'Open failed', 'err');
}

async function openPreview(path) {
  const name = path.split('/').pop();
  if (/\.(docx|pdf)$/i.test(name)) { openNative(path); return; }
  const r = await api('/api/file?path=' + encodeURIComponent(path));
  if (!r.ok) { log(r.error || 'Preview failed', 'err'); return; }
  previewPath = path;
  document.getElementById('preview-name').textContent = name;
  previewBody.textContent = r.content + (r.truncated ? '\n\n… (truncated)' : '');
  previewEditBtn.hidden = !isEditable(path, r.truncated);
  previewTa.hidden = true; previewBody.hidden = false; previewSaveBtn.hidden = true;
  previewEl.hidden = false;
}

previewEditBtn.addEventListener('click', () => {
  previewTa.value = previewBody.textContent;
  previewBody.hidden = true;
  previewTa.hidden = false;
  previewEditBtn.hidden = true;
  previewSaveBtn.hidden = false;
  previewTa.focus();
});

previewSaveBtn.addEventListener('click', async () => {
  const endpoint = isFill(previewPath) ? '/api/save-fill' : '/api/save-config';
  const r = await api(endpoint, {
    method: 'POST',
    body: JSON.stringify({ path: previewPath, content: previewTa.value }),
  });
  if (!r.ok) { log(esc(r.error || 'Save failed'), 'err'); return; }
  previewBody.textContent = previewTa.value;
  exitEditMode();
  log(`✓ Saved <span class="mono">${esc(previewPath)}</span>`, 'ok');
  if (isFill(previewPath)) {
    await refresh();
  } else if (r.status && !r.status.inSync) {
    log('Config changed — path registry is now <b>stale</b>. Rebuild it from the ⚙ System panel.', 'warn');
    applyConfigStatus(r.status);
  } else {
    applyConfigStatus(r.status);
  }
});

document.getElementById('preview-close').addEventListener('click', () => { previewEl.hidden = true; });
document.getElementById('preview-open').addEventListener('click', () => { if (previewPath) openNative(previewPath); });
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  if (!previewEl.hidden) { previewEl.hidden = true; return; }
  systemEl.hidden = true;
});

/* ---- system drawer ---- */
const systemEl = document.getElementById('system');

function applyConfigStatus(c) {
  if (!c) return;
  document.getElementById('gear-dot').hidden = c.inSync;
  document.getElementById('sys-product').textContent = c.product || '—';
  document.getElementById('sys-dir').textContent = c.configDir;
  document.getElementById('sys-sync').innerHTML = c.inSync
    ? '<span class="sync-badge good">Registry in sync</span>'
    : '<span class="sync-badge bad">Registry stale — rebuild needed</span>';
  document.getElementById('sys-fp').innerHTML =
    `registry ${esc((c.embedded || '—').slice(0, 12))} · config ${esc((c.live || '—').slice(0, 12))}` +
    (c.generatedAt ? `<br>generated ${esc(c.generatedAt.slice(0, 19).replace('T', ' '))}` : '');
}

async function loadConfig(withFiles) {
  const c = await api('/api/config');
  if (!c.ok) return;
  applyConfigStatus(c);
  if (withFiles) {
    document.getElementById('sys-files').innerHTML = c.files.map(f =>
      `<div class="file" data-path="${esc(f.path)}" title="Click to view / edit">
        <span class="nm mono">${esc(f.name)}</span><span class="sz">${kb(f.size)}</span></div>`
    ).join('');
  }
}

document.getElementById('gear').addEventListener('click', () => {
  systemEl.hidden = !systemEl.hidden;
  if (!systemEl.hidden) loadConfig(true);
});
document.getElementById('system-close').addEventListener('click', () => { systemEl.hidden = true; });
document.getElementById('sys-openconfig').addEventListener('click', () => openNative('socotra-config'));
document.getElementById('sys-files').addEventListener('click', (e) => {
  const fileEl = e.target.closest('.file');
  if (fileEl) openPreview(fileEl.dataset.path);
});

document.getElementById('sys-rebuild').addEventListener('click', async () => {
  const btn = document.getElementById('sys-rebuild');
  btn.disabled = true;
  btn.innerHTML = '<span class="spin"></span>Rebuilding…';
  log('Rebuilding path registry from <span class="mono">socotra-config/</span> …');
  const r = await api('/api/rebuild-registry', { method: 'POST', body: '{}' });
  btn.disabled = false;
  btn.textContent = 'Rebuild registry';
  if (!r.ok) { log(esc(r.error || 'Rebuild failed'), 'err'); return; }
  log(`✓ Registry rebuilt${r.backup ? ` — previous saved to <span class="mono">${esc(r.backup)}</span>` : ''}`, 'ok');
  if (r.preserved && r.preserved.length) {
    log(`Preserved hand-curated sections: ${r.preserved.map(esc).join(', ')}`, 'warn');
  }
  applyConfigStatus(r.status);
});

async function resolveForm(stem) {
  log(`<b>${esc(stem)}</b> — resolving paths (Leg -1 apply) + ingest (Leg 0)…`);
  const r = await api('/api/resolve-ingest', { method: 'POST', body: JSON.stringify({ stem }) });
  for (const s of (r.steps || [])) {
    log(`${s.ok ? '✓' : '✗'} ${esc(s.step)}`, s.ok ? 'ok' : 'err');
    if (s.stderr && s.stderr.trim()) log(esc(s.stderr.trim()).slice(0, 600), s.ok ? 'warn' : 'err');
  }
  log(r.ok ? `<b>${esc(stem)}</b> — ingested ✦ now fill the conditions, then Generate.` : esc(r.error || 'Resolve & ingest failed'), r.ok ? 'ok' : 'err');
  return r.ok;
}

async function generateForm(stem, withPlugin) {
  log(`<b>${esc(stem)}</b> — generating template${withPlugin ? ' + plugin' : ''} (Leg 2 → 3${withPlugin ? ' → 4' : ''})…`);
  const r = await api('/api/generate', { method: 'POST', body: JSON.stringify({ stem, plugin: withPlugin }) });
  for (const s of (r.steps || [])) {
    log(`${s.ok ? '✓' : '✗'} ${esc(s.step)}${s.artifacts ? ' → ' + s.artifacts.map(a => `<span class="mono">${esc(a)}</span>`).join(', ') : ''}`,
        s.ok ? 'ok' : 'err');
    if (s.stderr && s.stderr.trim()) log(esc(s.stderr.trim()).slice(0, 600), s.ok ? 'warn' : 'err');
  }
  log(r.ok ? `<b>${esc(stem)}</b> — template ready ✦` : esc(r.error || 'Generation failed'), r.ok ? 'ok' : 'err');
  return r.ok;
}

async function renderForm(stem, locator) {
  log(`<b>${esc(stem)}</b> — rendering preview against the live tenant${locator ? ` (${esc(locator)})` : ''}…`);
  const r = await api('/api/render-preview', {
    method: 'POST',
    body: JSON.stringify({ stem, referenceLocator: locator }),
  });
  if (r.ok) {
    log(`✓ Rendered <b>${esc(r.referenceType)}=${esc(r.referenceLocator)}</b> → `
      + `<span class="mono">${esc(r.out)}</span> (${kb(r.size)} · ${esc(r.contentType)})`
      + (r.opened ? ' · opened in viewer' : ' · open it from the card'), 'ok');
  } else {
    log(esc((r.error || 'Render preview failed').slice(0, 800)), 'err');
  }
  return r.ok;
}

board.addEventListener('dblclick', (e) => {
  const fileEl = e.target.closest('.file');
  if (fileEl) openNative(fileEl.dataset.path);
});

board.addEventListener('change', (e) => {
  if (e.target.matches('[data-chk=plugin]')) {
    chkState.set(e.target.closest('.card').dataset.stem, e.target.checked);
  }
});

board.addEventListener('click', async (e) => {
  const fileEl = e.target.closest('.file');
  if (fileEl) { openPreview(fileEl.dataset.path); return; }
  const btn = e.target.closest('button[data-act]');
  if (!btn) return;
  const card = btn.closest('.card');
  const stem = card.dataset.stem;
  const act = btn.dataset.act;
  const plugChk = card.querySelector('[data-chk=plugin]');
  const withPlugin = plugChk ? plugChk.checked : false;

  if (act === 'folder') { openNative(card.dataset.dir); return; }
  if (act === 'reset') {
    if (!confirm(`Delete all generated outputs and fill files for "${stem}"?\n(${card.dataset.dir} + action-needed/${stem}.* — the source document in workspace/inbox/ is kept.)`)) return;
    const r = await api('/api/reset', { method: 'POST', body: JSON.stringify({ stem }) });
    log(r.ok ? `Reset <b>${esc(stem)}</b> — output + fill files removed.` : (r.error || 'Reset failed'), r.ok ? 'warn' : 'err');
    await refresh();
    loadSamples();
    return;
  }
  busy.add(stem);
  refresh();

  if (act === 'resolve') {
    await resolveForm(stem);
  } else if (act === 'generate') {
    await generateForm(stem, withPlugin);
  } else if (act === 'plugin') {
    log(`<b>${esc(stem)}</b> — generating snapshot plugin (Leg 4)…`);
    const r = await api('/api/plugin', { method: 'POST', body: JSON.stringify({ stem }) });
    if (r.ok) {
      log(`✓ Plugin written → ${(r.artifacts || []).map(a => `<span class="mono">${esc(a)}</span>`).join(', ')}`, 'ok');
    } else {
      log(r.error || (r.stderr || 'Leg 4 failed').slice(0, 600), 'err');
    }
  } else if (act === 'render') {
    const locEl = card.querySelector('[data-loc]');
    await renderForm(stem, locEl ? locEl.value.trim() : '');
  }
  busy.delete(stem);
  await refresh();
  const fresh = board.querySelector(`.card[data-stem="${CSS.escape(stem)}"]`);
  if (fresh) fresh.classList.add('flash');
});

async function uploadFiles(files) {
  for (const file of files) {
    drop.classList.add('busy');
    drop.innerHTML = `<span class="spin"></span>Intake <b>${esc(file.name)}</b> (Leg -1 + Leg 0 scan)…`;
    log(`Uploading <b>${esc(file.name)}</b> → intake (Leg -1 + Leg 0 scan)…`);
    try {
      const r = await api('/api/upload', {
        method: 'POST',
        headers: { 'X-Filename': encodeURIComponent(file.name) },
        body: file,
      });
      if (r.ok) {
        log(`✓ Intake <b>${esc(r.stem)}</b> → ${(r.artifacts || []).length} fill files in <span class="mono">workspace/action-needed/</span>`, 'ok');
        log(`Next: open the <b>path-review</b> / <b>variants</b> files, fill them, save — then <b>Resolve &amp; ingest</b>.`, 'warn');
      } else {
        log(`✗ ${esc(r.error || 'Intake failed')}`, 'err');
      }
    } catch (err) {
      log('Upload failed: ' + err, 'err');
    }
    drop.classList.remove('busy');
    drop.innerHTML = 'Drop a <b>.docx</b> / <b>.pdf</b> here<br>or click to browse';
    await refresh();
    loadSamples();
  }
}

drop.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => { uploadFiles([...fileInput.files]); fileInput.value = ''; });
['dragover', 'dragenter'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('armed'); }));
['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('armed'); }));
drop.addEventListener('drop', e => uploadFiles([...e.dataTransfer.files]));

log('Intake console online.', 'ok');
refresh();
loadSamples();
loadConfig(false);
syncConsolePad();
setInterval(refresh, 4000);                     // pick up files edited outside the UI
setInterval(() => loadConfig(!systemEl.hidden), 8000);  // keep the ⚙ stale dot honest
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Velocity Converter demo UI")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    server = None
    for port in range(args.port, args.port + 10):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if server is None:
        sys.exit(f"No free port in {args.port}-{args.port + 9}.")
    url = f"http://localhost:{port}"
    print(f"Velocity Converter demo UI → {url}   (Ctrl-C to stop)")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
