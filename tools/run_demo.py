#!/usr/bin/env python3
"""Headless back-to-front demo runner — the idiot-proof path.

The legs must run in ONE specific order, and two of the six steps are easy to
skip or misorder (the path-map re-ingest, the parse-variants step). This wraps
them so an agent runs two commands with one human-judgment step between:

    1. python3 tools/run_demo.py intake "workspace/inbox/<stem>.docx"
         → runs Leg -1 suggest + Leg 0 scan → the two fill files.

    2.  [HUMAN JUDGEMENT]  fill the two files in workspace/action-needed/:
          <stem>.path-review.csv  — confirm each `final` accessor (registry-grounded)
          <stem>.variants.csv     — write each `when` (condition DSL; see
                                    docs/writing-conditions.md)

    3. python3 tools/run_demo.py finalize "<stem>"
         → apply Leg -1 → Leg 0 ingest (with path-map) → parse variants
           → Leg 2+3 → VALIDATE. Stops at the first failure.

`finalize` always ends by running tools/validate_demo.py. If that prints PASS
you are done; if MISMATCH, fix the data_source / fill and re-run finalize. Never
hand-declare success — the gate decides.

No plugin (Leg 4) here — a demo template doesn't need one; conditional prose
lives in the variants.csv / conditional-registry. Add Leg 4 only if asked.
"""
import argparse
import csv
import subprocess
import sys
from pathlib import Path

PY = sys.executable
REGISTRY = "registry/path-registry.yaml"
OUTPUT = "workspace/output"
ACTION = "workspace/action-needed"


def run(cmd, label):
    print(f"\n=== {label} ===")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit(f"\nFAILED at: {label} (exit {r.returncode}). Fix the cause and re-run.")


def _stem_from(path: str) -> str:
    return Path(path).stem


def _find_source(stem: str) -> Path:
    for ext in (".docx", ".pdf"):
        p = Path("workspace/inbox") / f"{stem}{ext}"
        if p.is_file():
            return p
    sys.exit(f"No source doc workspace/inbox/{stem}.docx|.pdf — put the doc there first.")


def _saved_path_review_fills(stem: str) -> dict:
    """Human-filled `final` accessors from an existing path-review.csv (re-intake
    would otherwise clobber them; variants.csv already has its own merge guard)."""
    pr = Path(ACTION) / f"{stem}.path-review.csv"
    if not pr.is_file():
        return {}
    return {row["field"]: row["final"].strip()
            for row in csv.DictReader(pr.open())
            if (row.get("final") or "").strip()}


def _restore_path_review_fills(stem: str, saved: dict):
    pr = Path(ACTION) / f"{stem}.path-review.csv"
    if not saved or not pr.is_file():
        return
    rows = list(csv.DictReader(pr.open()))
    fieldnames = rows[0].keys() if rows else ("field", "suggested", "final")
    restored = []
    for row in rows:
        prev = saved.get(row["field"])
        if prev and prev != (row.get("final") or "").strip():
            row["final"] = prev
            restored.append(row["field"])
    with pr.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    if restored:
        print(f"\nPreserved your earlier `final` fills for: {', '.join(restored)}")


def intake(doc: str):
    src = Path(doc)
    if src.suffix.lower() not in (".docx", ".pdf"):
        sys.exit("intake needs a .docx or .pdf (the scan reads the document).")
    if src.suffix.lower() == ".docx":
        from velocity_converter.leg0_ingest import _find_soffice_binary, _SOFFICE_HINT
        if _find_soffice_binary() is None:
            sys.exit(_SOFFICE_HINT)
    stem = src.stem
    saved = _saved_path_review_fills(stem)
    run([PY, "-m", "velocity_converter.agent", "--yes",
         f"RUN_PIPELINE intake input={src} registry={REGISTRY} output={OUTPUT}"],
        "Leg -1 suggest + Leg 0 scan (intake)")
    _restore_path_review_fills(stem, saved)
    print(f"\nNEXT — fill these two files (human judgement), then run: "
          f"python3 tools/run_demo.py finalize \"{stem}\"")
    print(f"  {ACTION}/{stem}.path-review.csv   (confirm each `final` accessor)")
    print(f"  {ACTION}/{stem}.variants.csv      (write each `when` condition)")


def _fold_variant_text_leaves(stem: str, src: Path):
    """Leg -1 pass 2: a {leaf} typed only inside a variants.csv `text` cell is
    invisible to the intake scan. Fold net-new leaves into path-review.csv
    (with registry suggestions) and stop so the human confirms them — never
    auto-accept a new accessor. Idempotent: no new leaves → straight through."""
    pr = Path(ACTION) / f"{stem}.path-review.csv"
    vr = Path(ACTION) / f"{stem}.variants.csv"
    if not pr.is_file() or not vr.is_file():
        return
    before = {row["field"] for row in csv.DictReader(pr.open())}
    run([PY, "-m", "velocity_converter.legminus1_resolve_paths", "--input", str(src),
         "--registry", REGISTRY, "--output-dir", OUTPUT, "--variants-csv", str(vr)],
        "Leg -1 pass 2 (fold variant-text fields into path-review)")
    new = [row["field"] for row in csv.DictReader(pr.open()) if row["field"] not in before]
    if new:
        sys.exit(f"\nvariants.csv text mentions new field(s): {', '.join(new)} — "
                 f"rows appended to {pr}.\nConfirm each new `final` accessor, "
                 f"then re-run: python3 tools/run_demo.py finalize \"{stem}\"")


def _check_fills(stem: str):
    pr = Path(ACTION) / f"{stem}.path-review.csv"
    vr = Path(ACTION) / f"{stem}.variants.csv"
    if not pr.is_file() or not vr.is_file():
        sys.exit(f"Missing fill file(s). Run `intake` first, then fill:\n  {pr}\n  {vr}")
    blanks = [row["field"] for row in csv.DictReader(pr.open())
              if not (row.get("final") or "").strip()]
    if blanks:
        sys.exit(f"path-review.csv has blank `final` for: {', '.join(blanks)} — "
                 "fill every accessor (registry-grounded) before finalizing.")
    vrows = list(csv.DictReader(vr.open()))
    if vrows and not any((row.get("when") or "").strip() for row in vrows):
        # ponytail: warn-only — blank `when` is legal (unconditional loop / default row)
        print("NOTE: every `when` in variants.csv is blank, so all blocks render "
              "unconditionally. Fine for plain loops/defaults; if a [[$token]] block "
              "was meant to be conditional, fill its `when` before finalizing.")


def finalize(stem: str):
    src = _find_source(stem)
    _fold_variant_text_leaves(stem, src)
    _check_fills(stem)
    out_dir = f"{OUTPUT}/{stem}"
    path_map = f"{out_dir}/{stem}.path-map.yaml"

    run([PY, "-m", "velocity_converter.agent", "--yes",
         f"RUN_PIPELINE legminus1_apply review={ACTION}/{stem}.path-review.csv"],
        "Leg -1 apply (fold path-review → path-map)")
    run([PY, "-m", "velocity_converter.leg0_ingest", "--input", str(src),
         "--path-map", path_map, "--output-dir", out_dir],
        "Leg 0 ingest (with path-map → mapping + conditional-blocks sidecar)")
    run([PY, "-m", "velocity_converter.leg0_ingest",
         "--parse-variants-csv", f"{ACTION}/{stem}.variants.csv", "--output-dir", out_dir + "/"],
        "Parse variants.csv → conditional-registry")
    run([PY, "-m", "velocity_converter.agent", "--yes",
         f"RUN_PIPELINE leg2+leg3 mapping={out_dir}/{stem}.mapping.yaml registry={REGISTRY}"],
        "Leg 2 + Leg 3 (resolve paths → .final.vm)")
    run([PY, "tools/validate_demo.py", stem, "--registry", REGISTRY],
        "VALIDATE (doc coverage + renderingData shape) — the done-gate")
    print(f"\nDONE — {out_dir}/{stem}.final.vm is validated.")


def main():
    ap = argparse.ArgumentParser(description="Headless back-to-front demo runner.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("intake", help="Leg -1 suggest + Leg 0 scan → fill files")
    pi.add_argument("doc", help="workspace/inbox/<stem>.docx|.pdf")
    pf = sub.add_parser("finalize", help="apply → ingest → parse → Leg 2+3 → validate")
    pf.add_argument("stem", help="the doc stem, e.g. ZenCoverProtectionLetter(segment)")
    args = ap.parse_args()
    if args.cmd == "intake":
        intake(args.doc)
    else:
        finalize(args.stem)


if __name__ == "__main__":
    main()
