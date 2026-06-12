#!/usr/bin/env python3
"""Demo UI for the Velocity Converter pipeline.

Single-file local web app (stdlib only — no Flask):

    python3 tools/demo_ui.py            # serves http://localhost:8765
    python3 tools/demo_ui.py --port 9000

Flow:
  1. Drag/drop or pick a .docx/.pdf  -> saved to samples/input/, Leg 0 runs.
  2. Output files listed per form    -> double-click any file to open it
     natively (fill the conditional form there).
  3. "Generate template" runs the conditional-form parse (if needed) +
     Leg 2 + Leg 3; optional toggle also runs Leg 4 (plugin).
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
    run_leg0,
    run_leg2,
    run_leg3,
    run_leg4,
)
from velocity_converter.models import (  # noqa: E402
    ContractError,
    PathRegistry,
    validate_contract,
)
from velocity_converter.socotra_config_fingerprint import (  # noqa: E402
    compute_source_config_sha256,
    iter_tracked_config_json_files,
)

INPUT_DIR = REPO_ROOT / "samples" / "input"
OUTPUT_DIR = REPO_ROOT / "samples" / "output"
CONFIG_DIR = REPO_ROOT / "socotra-config"
PATH_REGISTRY = "registry/path-registry.yaml"
CUSTOMER_JAR = "build/customer-config.jar"
DATAMODEL_JAR = "build/core-datamodel-v1.7.61.jar"

ALLOWED_UPLOAD_SUFFIXES = {".docx", ".pdf"}


# --------------------------------------------------------------------------
# Pipeline helpers
# --------------------------------------------------------------------------

def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def form_status(form_dir: Path) -> dict:
    stem = form_dir.name
    files = sorted(f for f in form_dir.iterdir() if f.is_file() and not f.name.startswith("."))
    plugin = sorted(form_dir.glob("*DocumentDataSnapshotPluginImpl.java"))

    registry_f = form_dir / f"{stem}.conditional-registry.yaml"
    form_f = form_dir / f"{stem}.conditional-form.md"
    form_stale = (
        registry_f.exists()
        and form_f.exists()
        and form_f.stat().st_mtime > registry_f.stat().st_mtime
    )
    # Count conditions the customer still has to fill in — from the form when
    # it is the freshest source of truth, otherwise from the parsed registry.
    if form_f.exists() and (not registry_f.exists() or form_stale):
        unfilled = len(re.findall(r"^Condition:\s*$", form_f.read_text(encoding="utf-8"), re.M))
    elif registry_f.exists():
        unfilled = len(unfilled_conditions(stem))
    else:
        unfilled = 0

    return {
        "stem": stem,
        "dir": _rel(form_dir),
        "files": [
            {"name": f.name, "path": _rel(f), "size": f.stat().st_size}
            for f in files
        ],
        "ingested": (form_dir / f"{stem}.mapping.yaml").exists(),
        "conditionalForm": form_f.exists(),
        "registry": registry_f.exists(),
        "template": (form_dir / f"{stem}.final.vm").exists(),
        "plugin": bool(plugin),
        "unfilled": unfilled,
        "formStale": form_stale,
    }


def list_forms() -> list[dict]:
    if not OUTPUT_DIR.is_dir():
        return []
    forms = [form_status(d) for d in sorted(OUTPUT_DIR.iterdir()) if d.is_dir()]
    return [f for f in forms if f["files"]]


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

    stem = dest.stem
    result = run_leg0(
        input_path=_rel(dest),
        output_dir=f"samples/output/{stem}",
    )
    result["stem"] = stem
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


def do_ingest(rel_path: str) -> dict:
    """Run Leg 0 on a file already sitting in samples/input/."""
    src = (REPO_ROOT / rel_path).resolve()
    if not str(src).startswith(str(INPUT_DIR.resolve())) or not src.is_file():
        return {"ok": False, "error": "File must live in samples/input/."}
    result = run_leg0(input_path=_rel(src), output_dir=f"samples/output/{src.stem}")
    result["stem"] = src.stem
    return result


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
    """Delete a form's generated output folder (samples/output/<stem>/)."""
    target = (OUTPUT_DIR / stem).resolve()
    if (
        not stem
        or target == OUTPUT_DIR.resolve()
        or not str(target).startswith(str(OUTPUT_DIR.resolve()))
        or not target.is_dir()
    ):
        return {"ok": False, "error": "Form output folder not found."}
    shutil.rmtree(target)
    return {"ok": True}


def parse_conditional_form(stem: str) -> dict:
    form_dir = OUTPUT_DIR / stem
    form = form_dir / f"{stem}.conditional-form.md"
    if not form.exists():
        return {"ok": False, "error": f"{form.name} not found."}
    cmd = [
        sys.executable, "-m", "velocity_converter.leg0_ingest",
        "--parse-conditional-form", str(form),
        "--output-dir", str(form_dir),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    return {
        "ok": r.returncode == 0,
        "stdout": r.stdout,
        "stderr": r.stderr,
        "error": r.stderr if r.returncode != 0 else None,
    }


def unfilled_conditions(stem: str) -> list[int]:
    """Return ids of registry conditions left blank / placeholder by the customer."""
    registry = OUTPUT_DIR / stem / f"{stem}.conditional-registry.yaml"
    if not registry.exists():
        return []
    import yaml

    entries = yaml.safe_load(registry.read_text(encoding="utf-8")) or []
    bad = []
    for e in entries:
        conds = [str(c).strip() for c in (e.get("conditions") or [])]
        if not conds or any(c in ("", "---", "TBD", "None") for c in conds):
            bad.append(e.get("id"))
    return bad


def preflight_conditions(stem: str) -> dict | None:
    """Parse the conditional form if the registry is missing or stale. None = fine."""
    form_dir = OUTPUT_DIR / stem
    registry = form_dir / f"{stem}.conditional-registry.yaml"
    form = form_dir / f"{stem}.conditional-form.md"
    stale = registry.exists() and form.exists() and form.stat().st_mtime > registry.stat().st_mtime
    if form.exists() and (not registry.exists() or stale):
        r = parse_conditional_form(stem)
        if not r["ok"]:
            return {"ok": False, "error": f"{stem}: conditional form parse failed.", **r}
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
                f"Unfilled conditions — open each conditional-form.md, fill them in, "
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
        suggested=[f"samples/output/{s}/{s}.mapping.yaml" for s in stems],
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
    mapping = f"samples/output/{stem}/{stem}.mapping.yaml"
    if not (REPO_ROOT / mapping).exists():
        return {"ok": False, "error": f"{stem}.mapping.yaml not found — run ingest first."}

    steps: list[dict] = []

    # Mandatory pre-flight: parse the conditional form if the registry is
    # missing or the form was edited after the registry was last written.
    err = preflight_conditions(stem)
    if err:
        return {"ok": False, "steps": steps, **err}

    r2 = run_leg2(
        mapping=mapping,
        registry=PATH_REGISTRY,
        out=mapping,
        review_out=f"samples/output/{stem}/{stem}.review.md",
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
        out=f"samples/output/{stem}/{stem}.final.vm",
        report_out=f"samples/output/{stem}/{stem}.leg3-report.md",
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
    mapping = f"samples/output/{stem}/{stem}.mapping.yaml"
    if not (REPO_ROOT / mapping).exists():
        return {"ok": False, "error": f"{stem}.mapping.yaml not found."}

    # Same pre-flight as generate: pick up a freshly edited conditional form.
    err = preflight_conditions(stem)
    if err:
        return err

    r4 = safe_leg4(stem)
    r4["form"] = form_status(form_dir)
    return r4


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
            self._json({"ok": True, "forms": list_forms()})
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
            elif path == "/api/generate":
                self._json(do_generate(payload.get("stem", ""), bool(payload.get("plugin"))))
            elif path == "/api/plugin":
                self._json(do_plugin(payload.get("stem", "")))
            elif path == "/api/parse-form":
                self._json(parse_conditional_form(payload.get("stem", "")))
            elif path == "/api/ingest":
                self._json(do_ingest(payload.get("path", "")))
            elif path == "/api/reset":
                self._json(do_reset(payload.get("stem", "")))
            elif path == "/api/plugin-all":
                self._json(do_plugin_all(payload.get("stems") or []))
            elif path == "/api/rebuild-registry":
                self._json(rebuild_registry())
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
<title>Velocity Converter — Pipeline Console</title>
<style>
  :root {
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
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; min-height: 100%; }
  body {
    background:
      radial-gradient(1100px 500px at 80% -10%, rgba(22, 224, 207, .10), transparent 60%),
      radial-gradient(900px 500px at 5% 110%, rgba(195, 245, 60, .06), transparent 60%),
      linear-gradient(180deg, var(--navy-0), var(--navy-1) 45%, var(--navy-0));
    color: var(--text);
    font: 15px/1.5 -apple-system, "SF Pro Text", "Segoe UI", system-ui, sans-serif;
    padding: 32px 28px 120px;
  }
  .mono { font-family: "SF Mono", ui-monospace, Menlo, monospace; }

  /* ---- header ---- */
  header { max-width: 1180px; margin: 0 auto 30px; display: flex; align-items: baseline; gap: 16px; }
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
  #gear { margin-left: auto; align-self: center; position: relative; font-size: 16px; }
  #gear-dot {
    position: absolute; top: 3px; right: 3px; width: 8px; height: 8px; border-radius: 50%;
    background: var(--danger); box-shadow: 0 0 8px var(--danger);
  }

  /* ---- pipeline rail ---- */
  .rail { max-width: 1180px; margin: 0 auto 18px; display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 26px; position: relative; }
  .rail::before {
    content: ""; position: absolute; top: 34px; left: 8%; right: 8%; height: 1px; z-index: 0;
    background: linear-gradient(90deg, transparent, var(--teal-dim), var(--chartreuse), transparent);
    opacity: .5;
  }
  .stage {
    position: relative; z-index: 1;
    background: linear-gradient(165deg, rgba(22, 38, 79, .75), rgba(10, 18, 40, .92));
    border: 1px solid rgba(22, 224, 207, .18);
    border-radius: var(--radius);
    padding: 20px 20px 22px;
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
  .stage h2 { display: inline; font-size: 14px; letter-spacing: .18em; text-transform: uppercase; font-weight: 600; }
  .stage p { color: var(--text-dim); font-size: 13px; margin: 12px 0 0; }

  /* ---- dropzone ---- */
  .drop {
    margin-top: 14px; padding: 26px 14px; text-align: center; cursor: pointer;
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

  /* ---- forms board ---- */
  .board { max-width: 1180px; margin: 26px auto 0; display: grid; grid-template-columns: 1fr; gap: 22px; }
  .card {
    background: linear-gradient(170deg, rgba(15, 28, 61, .85), rgba(8, 14, 32, .95));
    border: 1px solid rgba(127, 147, 180, .16);
    border-radius: var(--radius); padding: 18px 18px 16px;
    box-shadow: 0 12px 34px rgba(2, 6, 18, .5);
  }
  .card.flash { animation: flash 1.2s ease; }
  @keyframes flash { 0% { border-color: var(--chartreuse); box-shadow: 0 0 30px rgba(195,245,60,.35); } 100% {} }
  .card h3 { margin: 0 0 10px; font-size: 16px; font-weight: 650; color: #eaf3ff; word-break: break-all; }
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
  .file.key .nm { color: var(--chartreuse); }
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
  }
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
  <div class="sub">Socotra &middot; document pipeline console</div>
  <button class="btn-ghost iconbtn" id="gear" title="System — Socotra config &amp; path registry">⚙<span id="gear-dot" hidden></span></button>
</header>

<div class="rail">
  <div class="stage">
    <span class="stage-num">1</span><h2>Ingest</h2>
    <p>Upload a Word or PDF document. Leg&nbsp;0 extracts fields, annotates conditionals and emits the customer conditional form.</p>
    <div class="drop" id="drop">Drop a <b>.docx</b> / <b>.pdf</b> here<br>or click to browse</div>
    <input type="file" id="fileInput" accept=".docx,.pdf" multiple hidden>
    <div class="chips" id="samples"></div>
  </div>
  <div class="stage">
    <span class="stage-num">2</span><h2>Conditions</h2>
    <p>Double-click the <b style="color:var(--chartreuse)">conditional-form.md</b> in a form card to open it and fill in the Velocity expressions, then save.</p>
  </div>
  <div class="stage">
    <span class="stage-num">3</span><h2>Generate</h2>
    <p>Run Legs&nbsp;2&nbsp;+&nbsp;3 to resolve paths and write the production <b style="color:var(--teal)">.final.vm</b>. Optionally generate &amp; compile the snapshot plugin (Leg&nbsp;4).</p>
  </div>
</div>

<div class="toolbar" id="toolbar" hidden>
  <span class="chips-label" style="width:auto" id="toolbar-label"></span>
  <span style="flex:1"></span>
  <button class="btn-primary" id="gen-all">Generate all templates</button>
  <button class="btn-ghost" id="plugin-all" title="One combined DocumentDataSnapshotPlugin from every form (Leg 4 multi-form)">Build combined plugin</button>
</div>

<div class="board" id="board"></div>
<div class="empty" id="empty" hidden>No forms ingested yet — drop a document above to begin.</div>

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

<div id="console"><div id="console-title">Pipeline log</div></div>

<script>
const board = document.getElementById('board');
const consoleEl = document.getElementById('console');
const drop = document.getElementById('drop');
const fileInput = document.getElementById('fileInput');
const busy = new Set();

function log(msg, cls) {
  const row = document.createElement('div');
  row.className = 'row';
  const t = new Date().toTimeString().slice(0, 8);
  row.innerHTML = `<span class="t mono">${t}</span><span class="${cls || ''}">${msg}</span>`;
  consoleEl.appendChild(row);
  consoleEl.scrollTop = consoleEl.scrollHeight;
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
  const conditionsDone = f.registry && f.unfilled === 0 && !f.formStale;
  const conditionsState = f.unfilled > 0 ? 'warn'
    : f.formStale ? 'stale'
    : f.registry ? 'done'
    : (f.conditionalForm ? 'next' : 'pending');
  const templateState = f.template ? (f.unfilled > 0 ? 'warn' : 'done')
    : (conditionsDone ? 'next' : 'pending');
  const pluginState = f.plugin ? (f.unfilled > 0 ? 'warn' : 'done')
    : (f.template && f.unfilled === 0 ? 'next' : 'pending');
  return [
    stepPill('Ingested', f.ingested ? 'done' : 'next'),
    stepPill('Form', f.conditionalForm ? 'done' : 'pending'),
    stepPill(
      f.unfilled > 0 ? `Conditions (${f.unfilled} to fill)` : 'Conditions',
      conditionsState
    ),
    stepPill('Template', templateState),
    stepPill('Plugin', pluginState),
  ].join('<span class="pill-sep" aria-hidden="true">›</span>');
}

function nextStep(f) {
  if (!f.ingested)
    return { text: 'Ingest a document to start', severity: 'next' };
  if (f.unfilled > 0)
    return {
      text: `Fill ${f.unfilled} condition${f.unfilled > 1 ? 's' : ''} in ${f.stem}.conditional-form.md`,
      severity: 'warn',
      highlightFile: `${f.stem}.conditional-form.md`,
    };
  if (f.formStale)
    return { text: 'Conditional form changed — re-parse before generating', severity: 'hot' };
  if (!f.registry)
    return { text: 'Parse the conditional form', severity: 'next' };
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
    const blocked = f.unfilled > 0;
    const blockTitle = blocked
      ? ` title="Fill ${f.unfilled} condition${f.unfilled > 1 ? 's' : ''} first"`
      : '';
    const fileRows = f.files.map(file => {
      const key = file.name.endsWith('.conditional-form.md') || file.name.endsWith('.final.vm');
      const urgent = step.highlightFile && file.name === step.highlightFile;
      return `<div class="file ${key ? 'key' : ''} ${urgent ? 'urgent' : ''}" data-path="${esc(file.path)}" title="Click to preview · double-click to open">
        <span class="nm mono">${esc(file.name)}</span><span class="sz">${kb(file.size)}</span></div>`;
    }).join('');
    card.innerHTML = `
      <h3>${esc(f.stem)}</h3>
      <div class="next-step next-step--${step.severity}">→ ${esc(step.text)}</div>
      <div class="pills">${pipelinePills(f)}</div>
      <div class="files">${fileRows}</div>
      <div class="hint">Click a file to preview it — double-click to open natively</div>
      <div class="actions">
        <button class="btn-primary" data-act="generate" ${isBusy || blocked ? 'disabled' : ''}${blockTitle}>
          ${isBusy ? '<span class="spin"></span>Running…' : (f.formStale && !blocked ? 'Re-parse &amp; generate' : (f.template ? 'Regenerate template' : 'Generate template'))}
        </button>
        <label class="chk"><input type="checkbox" data-chk="plugin" ${plugChecked ? 'checked' : ''}> + plugin (Leg 4)</label>
        <button class="btn-ghost" data-act="plugin" ${isBusy || blocked ? 'disabled' : ''}${blockTitle}>Plugin only</button>
        <span style="flex:1"></span>
        <button class="btn-ghost iconbtn" data-act="folder" title="Open output folder">📂</button>
        <button class="btn-ghost iconbtn" data-act="reset" title="Delete generated outputs for this form">🗑</button>
      </div>`;
    board.appendChild(card);
  }
}

let lastSnapshot = '';
let formStems = [];
async function refresh() {
  const data = await api('/api/forms');
  if (!data.ok) return;
  formStems = data.forms.map(f => f.stem);
  const toolbar = document.getElementById('toolbar');
  toolbar.hidden = data.forms.length < 2;
  if (!toolbar.hidden) {
    const unfilled = data.forms.reduce((n, f) => n + (f.unfilled || 0), 0);
    document.getElementById('toolbar-label').innerHTML =
      `${data.forms.length} forms` +
      (unfilled ? ` · <span style="color:var(--danger)">${unfilled} conditions still to fill</span>` : ' · all conditions filled');
  }
  const snap = JSON.stringify(data.forms) + '|' + [...busy].join();
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
  el.innerHTML = '<span class="chips-label">or ingest a sample</span>' + r.samples.map(s =>
    `<span class="chip" data-path="${esc(s.path)}" title="${s.ingested ? 'Already ingested — click to re-run Leg 0' : 'Click to run Leg 0'}">${s.ingested ? '<span class="tick">✓</span> ' : ''}${esc(s.name)}</span>`
  ).join('') + (r.samples.length > 1
    ? `<span class="chip" data-all="1" title="Run Leg 0 over every sample document"><span class="tick">⚡</span> Ingest all (${r.samples.length})</span>`
    : '');
}

async function ingestSample(path) {
  const name = path.split('/').pop();
  drop.innerHTML = `<span class="spin"></span>Ingesting <b>${esc(name)}</b> (Leg 0)…`;
  log(`Ingesting sample <b>${esc(name)}</b> → Leg 0…`);
  const r = await api('/api/ingest', { method: 'POST', body: JSON.stringify({ path }) });
  if (r.ok) {
    log(`✓ Ingested <b>${esc(r.stem)}</b> → ${(r.artifacts || []).length} artifacts in <span class="mono">samples/output/${esc(r.stem)}/</span>`, 'ok');
  } else {
    log(`✗ ${esc(r.error || r.stderr || 'Leg 0 failed')}`, 'err');
  }
  await refresh();
}

document.getElementById('samples').addEventListener('click', async (e) => {
  const chip = e.target.closest('.chip');
  if (!chip) return;
  const paths = chip.dataset.all ? samplePaths : [chip.dataset.path];
  drop.classList.add('busy');
  if (chip.dataset.all) log(`<b>Multi-ingest</b> — running Leg 0 over ${paths.length} documents…`);
  for (const p of paths) await ingestSample(p);
  if (chip.dataset.all) log(`<b>Multi-ingest complete</b> — ${paths.length} forms ready. Fill each conditional form, then “Generate all templates”.`, 'warn');
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

/* ---- preview panel (with in-place config editing) ---- */
const previewEl = document.getElementById('preview');
const previewBody = document.getElementById('preview-body');
const previewTa = document.getElementById('preview-ta');
const previewEditBtn = document.getElementById('preview-edit');
const previewSaveBtn = document.getElementById('preview-save');
let previewPath = null;

const isEditable = (path, truncated) =>
  path.startsWith('socotra-config/') && path.endsWith('.json') && !truncated;

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
  const r = await api('/api/save-config', {
    method: 'POST',
    body: JSON.stringify({ path: previewPath, content: previewTa.value }),
  });
  if (!r.ok) { log(esc(r.error || 'Save failed'), 'err'); return; }
  previewBody.textContent = previewTa.value;
  exitEditMode();
  log(`✓ Saved <span class="mono">${esc(previewPath)}</span>`, 'ok');
  if (r.status && !r.status.inSync) {
    log('Config changed — path registry is now <b>stale</b>. Rebuild it from the ⚙ System panel.', 'warn');
  }
  applyConfigStatus(r.status);
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
  const withPlugin = card.querySelector('[data-chk=plugin]').checked;

  if (act === 'folder') { openNative(card.dataset.dir); return; }
  if (act === 'reset') {
    if (!confirm(`Delete all generated outputs for "${stem}"?\n(${card.dataset.dir} — the source document in samples/input/ is kept.)`)) return;
    const r = await api('/api/reset', { method: 'POST', body: JSON.stringify({ stem }) });
    log(r.ok ? `Reset <b>${esc(stem)}</b> — output folder removed.` : (r.error || 'Reset failed'), r.ok ? 'warn' : 'err');
    await refresh();
    loadSamples();
    return;
  }
  busy.add(stem);
  refresh();

  if (act === 'generate') {
    await generateForm(stem, withPlugin);
  } else if (act === 'plugin') {
    log(`<b>${esc(stem)}</b> — generating snapshot plugin (Leg 4)…`);
    const r = await api('/api/plugin', { method: 'POST', body: JSON.stringify({ stem }) });
    if (r.ok) {
      log(`✓ Plugin written → ${(r.artifacts || []).map(a => `<span class="mono">${esc(a)}</span>`).join(', ')}`, 'ok');
    } else {
      log(r.error || (r.stderr || 'Leg 4 failed').slice(0, 600), 'err');
    }
  }
  busy.delete(stem);
  await refresh();
  const fresh = board.querySelector(`.card[data-stem="${CSS.escape(stem)}"]`);
  if (fresh) fresh.classList.add('flash');
});

async function uploadFiles(files) {
  for (const file of files) {
    drop.classList.add('busy');
    drop.innerHTML = `<span class="spin"></span>Ingesting <b>${esc(file.name)}</b> (Leg 0)…`;
    log(`Uploading <b>${esc(file.name)}</b> → Leg 0 ingest…`);
    try {
      const r = await api('/api/upload', {
        method: 'POST',
        headers: { 'X-Filename': encodeURIComponent(file.name) },
        body: file,
      });
      if (r.ok) {
        log(`✓ Ingested <b>${esc(r.stem)}</b> → ${(r.artifacts || []).length} artifacts in <span class="mono">samples/output/${esc(r.stem)}/</span>`, 'ok');
        log(`Next: open <span class="mono">${esc(r.stem)}.conditional-form.md</span>, fill the conditions, save — then hit <b>Generate template</b>.`, 'warn');
      } else {
        log(`✗ ${esc(r.error || r.stderr || 'Leg 0 failed')}`, 'err');
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

log('Pipeline console online.', 'ok');
refresh();
loadSamples();
loadConfig(false);
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
