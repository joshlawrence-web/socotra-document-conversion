#!/usr/bin/env python3
"""Guided story stepper for the ZenCover Protection Letter demo.

Walks the eight steps of docs/zencover-protection-demo.md, top to bottom, each one
running the REAL pipeline script. It reuses tools/demo_ui.py's backend wholesale
(do_intake / do_resolve_ingest / parse_variants / do_generate / do_render_preview)
and adds only the two bits that story has and the free-form console doesn't:
Leg -1 pass 2 (fold the variant-text leaf) and inlining the conditional text into
the .final.vm (this demo ships no plugin).

    python3 tools/zencover_demo.py            # serves http://localhost:8770
    python3 tools/zencover_demo.py --port 9001
    python3 tools/zencover_demo.py --selfcheck  # run the transform asserts, exit

ponytail: hardcoded to one document on purpose — it's a scripted story, not the
free-form console (that's tools/demo_ui.py). Generalise only if a second story shows up.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tools/ → import demo_ui
import demo_ui  # noqa: E402  (also puts REPO_ROOT on sys.path)

REPO_ROOT = demo_ui.REPO_ROOT
PY = sys.executable

STEM = "ZenCoverProtectionLetter(segment)"
SRC = f"workspace/inbox/{STEM}.docx"
REGISTRY = "registry/path-registry.yaml"

# The two notices are named [[$token]] variant blocks, so the scan emits a 2-row
# stub per block (conditioned row + blank default). The hand-fill supplies the
# conditioned row's `when` (condition DSL, document-scoped policy.* accessors for a
# segment doc) and its shown `text`; the blank default row = "show nothing otherwise".
CONDITIONS = {
    "discountNote": "policy.data.discountAmount present",
    "coolingOffNote": "policy.data.coolingOffPeriod present",
}
NOTE_TEXT = {
    "discountNote": "you have a discount",
    "coolingOffNote": "you have a cooling off period of {coolingOffPeriod} days",
}

# Intake runs suggestions=off, so the path-review.csv arrives with blank
# suggested/final columns — this is the customer's hand-mapping of every accessor
# (the story's "no machine guesses" beat). Pass 2 then shows the suggester paying
# off for the one leaf added later.
FINALS = {
    "{firstName}": "account.data.firstName",
    "{lastName}": "account.data.lastName",
    "{policyNumber}": "policy.policyNumber",
    "{email}": "account.data.email",
    "{contractTermEndDate}": "policy.data.contractTermEndDate",
    "{expectedRenewalDate}": "policy.data.expectedRenewalDate",
    "{itemTypeCode}": "item.data.itemTypeCode",
    "{purchaseDate}": "item.data.purchaseDate",
    "{purchasePrice}": "item.data.purchasePrice",
    "{serialNumber}": "item.data.serialNumber",
}

# Step 7 — inline the plugin-owned notice text as real #if blocks. Segment custom
# fields render under $data.segment.data.* (the same splice Leg 2 used for the body).
INLINE = {
    "discountNote": (
        "$data.segment.data.discountAmount",
        "you have a discount",
    ),
    "coolingOffNote": (
        "$data.segment.data.coolingOffPeriod",
        "you have a cooling off period of $data.segment.data.coolingOffPeriod days",
    ),
}


def _variants_csv() -> Path:
    return demo_ui.action_needed_dir(demo_ui.OUTPUT_DIR / STEM) / f"{STEM}.variants.csv"


def _final_vm() -> Path:
    return demo_ui.OUTPUT_DIR / STEM / f"{STEM}.final.vm"


# --------------------------------------------------------------------------
# The two custom step bodies (everything else delegates to demo_ui)
# --------------------------------------------------------------------------

def step_pass2() -> dict:
    """Leg -1 pass 2: fold the variant-text leaf ({coolingOffPeriod}) into path-review."""
    if not _variants_csv().exists():
        return {"ok": False, "error": "variants.csv missing — run Intake first."}
    cmd = [
        PY, "-m", "velocity_converter.legminus1_resolve_paths",
        "--input", SRC, "--registry", REGISTRY, "--output-dir", "workspace/output",
        "--variants-csv", str(_variants_csv()),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    return {
        "ok": r.returncode == 0,
        "log": (r.stdout or "") + (r.stderr or ""),
        "error": r.stderr if r.returncode else None,
        "artifacts": [_rel_artifact(demo_ui.action_needed_dir(demo_ui.OUTPUT_DIR / STEM)
                                    / f"{STEM}.path-review.csv")],
    }


def fill_conditions(text: str) -> str:
    """Fill each notice's conditioned row (when + shown text) in the variants.csv.

    Each [[$token]] block is a 2-row stub: the FIRST row is the conditioned variant
    (gets when + text), the second stays blank (the default = show nothing). Pure and
    testable — only the file I/O lives in :func:`step_fill`.
    """
    rows = list(csv.DictReader(io.StringIO(text)))
    fields = ["placeholder", "when", "text"]
    filled: set[str] = set()
    for row in rows:
        ph = row["placeholder"]
        if ph in CONDITIONS and ph not in filled:  # first row of the block = conditioned
            row["when"] = CONDITIONS[ph]
            row["text"] = NOTE_TEXT[ph]
            filled.add(ph)
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    for row in rows:
        w.writerow({k: row.get(k, "") for k in fields})
    return out.getvalue()


def fill_finals(text: str) -> str:
    """Fill the blank `final` column of the no-suggest path-review.csv (pure)."""
    rows = list(csv.DictReader(io.StringIO(text)))
    fields = ["field", "suggested", "final"]
    for row in rows:
        if not row.get("final"):
            row["final"] = FINALS.get(row["field"], "")
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    for row in rows:
        w.writerow({k: row.get(k, "") for k in fields})
    return out.getvalue()


def _path_review_csv() -> Path:
    return demo_ui.action_needed_dir(demo_ui.OUTPUT_DIR / STEM) / f"{STEM}.path-review.csv"


def step_fill() -> dict:
    csv_path = _variants_csv()
    if not csv_path.exists():
        return {"ok": False, "error": "variants.csv missing — run Intake first."}
    csv_path.write_text(fill_conditions(csv_path.read_text(encoding="utf-8")), encoding="utf-8")
    review = _path_review_csv()
    if not review.exists():
        return {"ok": False, "error": "path-review.csv missing — run Intake first."}
    review.write_text(fill_finals(review.read_text(encoding="utf-8")), encoding="utf-8")
    return {
        "ok": True,
        "log": "Filled `when` for: " + ", ".join(f"{k} → {v}" for k, v in CONDITIONS.items())
               + f"\nHand-mapped {len(FINALS)} accessors into path-review.csv (finals "
                 "were blank — intake ran suggestions=off).",
        "artifacts": [_rel_artifact(csv_path), _rel_artifact(review)],
    }


def inline_conditionals(vm: str) -> tuple[str, list[str]]:
    """Replace `<p…>${data.<tok>}</p>` with a real #if block (pure, testable).

    The ``p`` may carry class/style attributes (LibreOffice XHTML export) and a
    trailing space inside the tag — match those, keep the attributes on the
    replacement so spacing/fonts survive the inline.
    """
    import re
    missing = []
    for tok, (cond, body) in INLINE.items():
        pat = re.compile(rf"<p([^>]*)>\$\{{data\.{re.escape(tok)}\}}\s*</p>")
        repl = rf"#if({cond})<p\1>{body}</p>#end"
        vm2, n = pat.subn(repl, vm, count=1)
        if n:
            vm = vm2
        else:
            missing.append(tok)
    return vm, missing


def shape_check(vm: str) -> list[str]:
    """renderingData done-gate: return offending lines (empty = clean)."""
    import re
    bad = re.compile(r"\$data\.data\.|\$data\.(policyNumber|firstName|lastName|email|"
                     r"contractTermEndDate|expectedRenewalDate)")
    return [ln.strip() for ln in vm.splitlines() if bad.search(ln)]


def step_inline() -> dict:
    vm_path = _final_vm()
    if not vm_path.exists():
        return {"ok": False, "error": "final.vm missing — run Generate first."}
    vm, missing = inline_conditionals(vm_path.read_text(encoding="utf-8"))
    if missing:
        return {"ok": False, "error": f"tokens not found in final.vm: {missing} "
                "(re-run Generate — Leg 3 emits the ${{data.<tok>}} form)."}
    vm_path.write_text(vm, encoding="utf-8")
    bad = shape_check(vm)
    return {
        "ok": True,
        "log": "Inlined: " + ", ".join(INLINE)
               + ("\n\nrenderingData shape: CLEAN ✓" if not bad
                  else "\n\nrenderingData shape: BAD ✗\n" + "\n".join(bad)),
        "artifacts": [_rel_artifact(vm_path)],
    }


def _rel_artifact(p: Path) -> dict:
    binary = p.suffix.lower() in {".pdf", ".docx"}
    return {"name": p.name, "path": demo_ui._rel(p), "binary": binary,
            "exists": p.exists()}


def _adapt(result: dict, extra_artifacts: list[Path] | None = None) -> dict:
    """Fold a demo_ui result (stdout/stderr/steps/out) into our uniform shape."""
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error") or result.get("stderr")
                or "step failed", "log": _collect_log(result)}
    arts = [_rel_artifact(p) for p in (extra_artifacts or [])]
    for a in result.get("artifacts") or []:
        arts.append(_rel_artifact(REPO_ROOT / a))
    if result.get("out"):
        arts.append(_rel_artifact(REPO_ROOT / result["out"]))
    return {"ok": True, "log": _collect_log(result), "artifacts": arts}


def _collect_log(result: dict) -> str:
    parts = []
    for s in result.get("steps") or []:
        parts.append(f"=== {s.get('step', '')} ===")
        parts.append((s.get("stdout") or "") + (s.get("stderr") or ""))
    parts.append((result.get("stdout") or "") + (result.get("stderr") or ""))
    if result.get("out"):
        parts.append(f"→ wrote {result['out']} "
                     f"({result.get('size', '?')} bytes, {result.get('contentType', '')})")
    return "\n".join(p for p in parts if p.strip())


# --------------------------------------------------------------------------
# Step registry — id → (title, blurb, runner)
# --------------------------------------------------------------------------

def _chain(*runners):
    """Run several step bodies as one button; stop at the first failure."""
    def run():
        arts: list[dict] = []
        logs: list[str] = []
        for r in runners:
            res = r()
            logs.append(res.get("log") or "")
            arts += res.get("artifacts") or []
            if not res.get("ok"):
                return {"ok": False, "error": res.get("error"),
                        "log": "\n".join(logs), "artifacts": arts}
        return {"ok": True, "log": "\n".join(logs), "artifacts": arts}
    return run


STEPS = [
    ("intake", "Prepare the customer pack",
     "Read the Word letter and produce the two fill-in spreadsheets — one for what each "
     "field means in the product, one for the conditional notices.",
     lambda: _adapt(demo_ui.do_intake(SRC, no_suggest=True))),
    ("fill", "Customer fills in the spreadsheets",
     "The field meanings, the conditions and the notice wording are written in — "
     "the only human step in the process.",
     step_fill),
    ("pass2", "Pick up the new field",
     "One field only exists inside the notice wording the customer just wrote — "
     "fold it into the pack, this time with a suggested mapping.",
     step_pass2),
    ("build", "Generate the template",
     "Apply the customer's answers to the document and build the Velocity template.",
     _chain(lambda: _adapt(demo_ui.do_resolve_ingest(STEM)),
            lambda: _adapt(demo_ui.parse_variants(STEM),
                           [demo_ui.OUTPUT_DIR / STEM / f"{STEM}.conditional-registry.yaml"]),
            lambda: _adapt(demo_ui.do_generate(STEM, False)))),
    ("preview", "Render the preview",
     "Finish the template and render it live against the test tenant — "
     "the PDF opens when it's ready.",
     _chain(step_inline,
            lambda: _adapt(demo_ui.do_render_preview(STEM, "segment", "")))),
]
STEP_INDEX = {s[0]: s for s in STEPS}


def run_step(step_id: str) -> dict:
    if step_id not in STEP_INDEX:
        return {"ok": False, "error": f"unknown step {step_id!r}"}
    try:
        return STEP_INDEX[step_id][3]()
    except Exception as exc:  # surface to the UI, don't break the pipe
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def reset() -> dict:
    return demo_ui.do_reset(STEM) if (demo_ui.OUTPUT_DIR / STEM).is_dir() else {"ok": True}


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _json(self, payload, status=200):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            data = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif parsed.path == "/api/file":
            q = urllib.parse.parse_qs(parsed.query)
            self._json(demo_ui.read_file(q.get("path", [""])[0]))
        else:
            self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            payload = json.loads(self._body() or b"{}")
            if path == "/api/step":
                self._json(run_step(payload.get("id", "")))
            elif path == "/api/open":
                self._json(demo_ui.do_open(payload.get("path", "")))
            elif path == "/api/reset":
                self._json(reset())
            else:
                self._json({"ok": False, "error": "not found"}, 404)
        except Exception as exc:
            self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)


def _steps_json():
    return [{"id": s[0], "title": s[1], "blurb": s[2]} for s in STEPS]


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ZenCover Protection Letter — Demo Walkthrough</title>
<style>
  :root { --bg:#0a1228; --bg2:#050a18; --card:#0f1c3d; --line:rgba(127,147,180,.18);
    --teal:#16e0cf; --lime:#c3f53c; --text:#d7e3f4; --dim:#7f93b4; --ok:#4ade80; --bad:#ff5d7a;
    --h1a:#eaf6ff; --stepbg:linear-gradient(165deg,rgba(22,38,79,.7),rgba(10,18,40,.9));
    --inset:rgba(3,8,20,.6); --outbg:#050a18; --outfg:#b9c9e4; }
  body.light { --bg:#f2f6fb; --bg2:#e7edf6; --card:#ffffff; --line:rgba(30,50,80,.18);
    --teal:#0b8f84; --lime:#7aa800; --text:#1c2a3f; --dim:#5b6b84; --ok:#15803d; --bad:#d63a5a;
    --h1a:#1c2a3f; --stepbg:linear-gradient(165deg,#ffffff,#f0f4fa);
    --inset:rgba(20,40,70,.06); --outbg:#f6f8fc; --outfg:#324a68; }
  * { box-sizing:border-box; } body { margin:0; background:
      radial-gradient(1000px 460px at 82% -8%, rgba(22,224,207,.10), transparent 60%),
      linear-gradient(180deg,var(--bg2),var(--bg) 45%,var(--bg2));
    color:var(--text); font:15px/1.5 -apple-system,"Segoe UI",system-ui,sans-serif;
    padding:34px 24px 80px; }
  .mono { font-family:"SF Mono",ui-monospace,Menlo,monospace; }
  header { max-width:900px; margin:0 auto 6px; }
  h1 { margin:0; font-size:22px; letter-spacing:.12em; text-transform:uppercase;
    background:linear-gradient(90deg,var(--h1a),var(--teal) 60%,var(--lime));
    -webkit-background-clip:text; background-clip:text; color:transparent; }
  .sub { color:var(--dim); font-size:13px; margin:6px 0 18px; }
  .bar { max-width:900px; margin:0 auto 20px; display:flex; gap:10px; }
  button { font:inherit; cursor:pointer; border-radius:9px; border:1px solid var(--line);
    background:var(--card); color:var(--text); padding:8px 16px; }
  button:hover:not(:disabled) { border-color:var(--teal); }
  button:disabled { opacity:.4; cursor:default; }
  .primary { background:linear-gradient(135deg,var(--teal),var(--lime)); color:#04101f;
    border:none; font-weight:650; }
  .steps { max-width:900px; margin:0 auto; display:flex; flex-direction:column; gap:14px; }
  .step { background:var(--stepbg);
    border:1px solid var(--line); border-radius:13px; padding:16px 18px; }
  .step.done { border-color:rgba(74,222,128,.4); }
  .step.err { border-color:rgba(255,93,122,.5); }
  .step.busy { opacity:.75; }
  .head { display:flex; align-items:center; gap:12px; }
  .num { width:27px; height:27px; flex:none; border-radius:7px; display:flex;
    align-items:center; justify-content:center; font-weight:700; color:#04101f;
    background:linear-gradient(135deg,var(--teal),var(--lime)); }
  .step.done .num::after { content:"✓"; } .step.done .num { font-size:0; }
  .title { font-size:14px; font-weight:620; letter-spacing:.04em; }
  .blurb { color:var(--dim); font-size:13px; margin:8px 0 10px; }
  .run { padding:5px 14px; font-size:13px; }
  .spin { width:13px; height:13px; border:2px solid var(--line); border-top-color:var(--teal);
    border-radius:50%; display:inline-block; animation:sp .8s linear infinite;
    vertical-align:-2px; margin-right:7px; }
  @keyframes sp { to { transform:rotate(360deg); } }
  pre.out { margin:10px 0 0; background:var(--outbg); border:1px solid var(--line);
    border-radius:8px; padding:10px 12px; font-size:11.5px; max-height:280px;
    overflow:auto; white-space:pre-wrap; color:var(--outfg); display:none; }
  .arts { margin-top:10px; display:flex; flex-wrap:wrap; gap:7px; }
  .art { font-size:11.5px; padding:3px 10px; border-radius:999px; cursor:pointer;
    border:1px solid var(--line); background:var(--inset); color:var(--teal); }
  .art:hover { border-color:var(--teal); }
  .status { margin-left:auto; font-size:11px; color:var(--dim); }
  .status.ok { color:var(--ok); } .status.bad { color:var(--bad); }
  a { color:var(--teal); }
</style></head><body>
<header>
  <h1>ZenCover Protection Letter</h1>
  <div class="sub">Five steps: Word document in, live-rendered document out.</div>
</header>
<div class="bar">
  <button class="primary" id="runAll">▶ Run all</button>
  <button id="reset">↺ Reset demo</button>
  <button id="theme" style="margin-left:auto"></button>
</div>
<div class="steps" id="steps"></div>
<script>
const STEPS = __STEPS__;
const el = document.getElementById('steps');
STEPS.forEach((s,i)=>{
  const d=document.createElement('div'); d.className='step'; d.id='s-'+s.id;
  d.innerHTML=`<div class="head"><div class="num">${i+1}</div>
    <div class="title">${s.title}</div><div class="status" id="st-${s.id}"></div></div>
    <div class="blurb">${s.blurb}</div>
    <button class="run" data-id="${s.id}">Run this step</button>
    <div class="arts" id="ar-${s.id}"></div>
    <pre class="out" id="out-${s.id}"></pre>`;
  el.appendChild(d);
});
async function post(url,body){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});return r.json();}
async function openArt(a){
  if(a.binary){ await post('/api/open',{path:a.path}); return; }
  const r=await fetch('/api/file?path='+encodeURIComponent(a.path)); const j=await r.json();
  const out=document.getElementById('out-active-view')||null;
  alert(a.name+'\n\n'+(j.ok?j.content:j.error));
}
function renderArts(id,arts){
  const box=document.getElementById('ar-'+id); box.innerHTML='';
  (arts||[]).forEach(a=>{ if(!a.exists) return;
    const b=document.createElement('span'); b.className='art'; b.textContent=(a.binary?'📄 ':'')+a.name;
    b.onclick=()=>openArt(a); box.appendChild(b); });
}
const PHRASES=['Working…','Reading the document…','Putting the pieces together…',
  'Checking the results…','Nearly there…'];
async function runStep(id){
  const step=document.getElementById('s-'+id), st=document.getElementById('st-'+id),
        out=document.getElementById('out-'+id);
  step.className='step busy'; st.className='status';
  let i=0; st.innerHTML='<span class="spin"></span>'+PHRASES[0];
  const tick=setInterval(()=>{st.innerHTML='<span class="spin"></span>'+PHRASES[++i%PHRASES.length];},1600);
  const j=await post('/api/step',{id});
  clearInterval(tick);
  out.style.display='none';
  if(j.ok){ step.className='step done'; st.className='status ok'; st.textContent='✓ Done'; renderArts(id,j.artifacts); }
  else { step.className='step err'; st.className='status bad'; st.textContent='✗ Failed';
    out.style.display='block'; out.textContent=(j.error||'step failed'); }
  return j.ok;
}
const tb=document.getElementById('theme');
function setTheme(light){ document.body.classList.toggle('light',light);
  tb.textContent=light?'☾ Dark':'☀ Light'; localStorage.zcTheme=light?'light':'dark'; }
setTheme(localStorage.zcTheme==='light');
tb.onclick=()=>setTheme(!document.body.classList.contains('light'));
document.querySelectorAll('.run').forEach(b=>b.onclick=()=>runStep(b.dataset.id));
document.getElementById('runAll').onclick=async()=>{
  for(const s of STEPS){ const ok=await runStep(s.id); if(!ok) break; }
};
document.getElementById('reset').onclick=async()=>{
  await post('/api/reset',{});
  STEPS.forEach(s=>{document.getElementById('s-'+s.id).className='step';
    document.getElementById('st-'+s.id).textContent='';
    document.getElementById('out-'+s.id).style.display='none';
    document.getElementById('ar-'+s.id).innerHTML='';});
};
</script></body></html>
"""
PAGE = PAGE.replace("__STEPS__", json.dumps(_steps_json()))


def _selfcheck():
    # fill_conditions fills ONLY the conditioned (first) row of each [[$token]] block
    # with when + text, and leaves the default (second) row blank.
    src = ("placeholder,when,text\n"
           "discountNote,,\n" "discountNote,,\n"
           "coolingOffNote,,\n" "coolingOffNote,,\n")
    lines = fill_conditions(src).strip().splitlines()
    assert lines[1] == "discountNote,policy.data.discountAmount present,you have a discount", lines
    assert lines[2] == "discountNote,,", lines  # default row stays blank
    assert lines[3].startswith("coolingOffNote,policy.data.coolingOffPeriod present,"), lines
    assert "{coolingOffPeriod} days" in lines[3]  # shown text supplied (leaf for pass 2)
    assert lines[4] == "coolingOffNote,,", lines  # default row stays blank
    # fill_finals fills every blank final from FINALS, leaves unknown fields blank
    pr = "field,suggested,final\n{firstName},,\n{mystery},,\n"
    got = fill_finals(pr).strip().splitlines()
    assert got[1] == "{firstName},,account.data.firstName", got
    assert got[2] == "{mystery},,", got
    # inline_conditionals swaps the token <p> for an #if block; none missing
    vm = "<p>${data.discountNote}</p>\n<p>${data.coolingOffNote}</p>\n"
    out, missing = inline_conditionals(vm)
    assert not missing, missing
    assert "#if($data.segment.data.discountAmount)<p>you have a discount</p>#end" in out, out
    assert "${data.discountNote}" not in out
    # XHTML-style <p class=…> with a trailing space still matches
    vm_x = '<p class="paragraph-Standard">${data.discountNote} </p>\n<p class="paragraph-Standard">${data.coolingOffNote}</p>\n'
    out_x, missing_x = inline_conditionals(vm_x)
    assert not missing_x, missing_x
    assert 'class="paragraph-Standard"' in out_x
    assert "${data.discountNote}" not in out_x
    # a missing token is reported, not silently dropped
    _, missing2 = inline_conditionals("<p>nothing here</p>")
    assert set(missing2) == set(INLINE), missing2
    # shape_check flags a bad path and passes a clean one
    assert shape_check("<p>$data.data.foo</p>")
    assert not shape_check("<p>$data.segment.data.foo</p>")
    print("selfcheck OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--selfcheck", action="store_true", help="run transform asserts and exit")
    args = ap.parse_args()
    if args.selfcheck:
        _selfcheck()
        return
    url = f"http://localhost:{args.port}"
    print(f"ZenCover Protection Letter demo → {url}  (Ctrl-C to stop)")
    if not args.no_open:
        webbrowser.open(url)
    ThreadingHTTPServer(("localhost", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
