#!/usr/bin/env python3
"""Leg 3 — Substitution Writer.

Reads:
  - <stem>.vm          (Leg 1) — template with $TBD_* placeholders and #if guards
  - <stem>.suggested.yaml  (Leg 2) — confirmed data_source paths

Writes:
  - <stem>.final.vm        — production-ready Velocity template
  - <stem>.leg3-report.md  — remedy form listing resolved and unresolved tokens

Design decisions (DD — recorded here and in SCHEMA.md):
  DD-1: #if($TBD_*) guards are stripped from the final output. Tradeoff:
        readability over null-safety. Guards can be added manually or by a
        future leg when the full data contract is known.
  DD-2: Unresolved tokens ($TBD_* with empty data_source) are preserved
        as-is so the template remains parseable.
  DD-3: Lenient mode — substitute every resolved token, report the rest.
        Never aborts on low-confidence or empty data_source entries.
  DD-4: High-only mode (--high-only flag) — only substitute tokens whose
        confidence == 'high'. Medium/low entries with a data_source are
        placed in a "Deferred" bucket: they remain as $TBD_* in the output
        and get their own report section. Rationale: lets users ship a
        partial template while fuzzy/unconfirmed matches await human review.
        Re-run without --high-only once deferred entries are confirmed in
        the .suggested.yaml.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    """Walk up from this script until a .cursor/ directory is found."""
    p = Path(__file__).resolve().parent
    for candidate in [p, *p.parents]:
        if (candidate / ".cursor").is_dir():
            return candidate
    return Path(__file__).resolve().parent.parent


def _rel(path: Path, base: Path) -> str:
    """Return path relative to base, or absolute string if not possible."""
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def _load_yaml(path: Path) -> dict:
    """Load YAML, tolerating # comment-header lines Leg 2 writes."""
    lines = path.read_text(encoding="utf-8").splitlines()
    body = "\n".join(ln for ln in lines if not ln.startswith("#"))
    data = yaml.safe_load(body)
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# Build substitution tables from suggested.yaml
# ---------------------------------------------------------------------------


def build_substitution_map(suggested: dict, high_only: bool = False) -> dict[str, str]:
    """
    {placeholder: data_source} for every variable and loop field.
    Entries with empty data_source map to '' — caller decides what to do.
    When high_only=True, non-high-confidence entries also map to '' (DD-4).
    """
    smap: dict[str, str] = {}
    for v in suggested.get("variables") or []:
        ph = v.get("placeholder") or ""
        if ph:
            if high_only and v.get("confidence") != "high":
                smap[ph] = ""
            else:
                smap[ph] = v.get("data_source") or ""
    for loop in suggested.get("loops") or []:
        ph = loop.get("placeholder") or ""
        if ph:
            if high_only and loop.get("confidence") != "high":
                smap[ph] = ""
            else:
                smap[ph] = loop.get("data_source") or ""
        for fld in loop.get("fields") or []:
            fph = fld.get("placeholder") or ""
            if fph:
                if high_only and fld.get("confidence") != "high":
                    smap[fph] = ""
                else:
                    smap[fph] = fld.get("data_source") or ""
    return smap


def build_foreach_map(suggested: dict, high_only: bool = False) -> dict[str, str]:
    """
    {loop_placeholder: foreach_directive} for loops that have both
    a data_source and a foreach directive from Leg 2.
    When high_only=True, only high-confidence loops are included (DD-4).
    """
    fmap: dict[str, str] = {}
    for loop in suggested.get("loops") or []:
        ph = loop.get("placeholder") or ""
        foreach = loop.get("foreach") or ""
        ds = loop.get("data_source") or ""
        conf = loop.get("confidence") or ""
        if ph and foreach and ds:
            if not high_only or conf == "high":
                fmap[ph] = foreach
    return fmap


# ---------------------------------------------------------------------------
# Template processor
# ---------------------------------------------------------------------------

_TBD_TOKEN_RE = re.compile(r"\$TBD_\w+")
_GUARD_OPEN_RE = re.compile(r"^\s*#if\(\$TBD_\w+\)\s*$")
_IF_OR_FOREACH_RE = re.compile(r"^\s*#(if|foreach)\b")
_END_RE = re.compile(r"^\s*#end\s*$")
_FOREACH_LINE_RE = re.compile(r"^\s*#foreach\b")


def _substitute_tokens(line: str, smap: dict[str, str]) -> str:
    """Replace resolved $TBD_* tokens; leave unresolved ones as-is (DD-2)."""
    def replacer(m: re.Match) -> str:
        token = m.group(0)
        ds = smap.get(token)
        return ds if ds else token
    return _TBD_TOKEN_RE.sub(replacer, line)


def _find_tbd_token(line: str) -> str | None:
    m = _TBD_TOKEN_RE.search(line)
    return m.group(0) if m else None


def process_vm(
    vm_text: str,
    smap: dict[str, str],
    foreach_map: dict[str, str],
) -> str:
    """
    Apply Leg 3 transformations to a .vm template:
      - Strip #if($TBD_*) ... #end guard wrappers (DD-1)
      - Substitute resolved $TBD_* tokens in content lines (DD-3)
      - Preserve unresolved $TBD_* tokens as-is (DD-2)
      - Replace #foreach with TBD collection with real directive when available
    """
    lines = vm_text.splitlines(keepends=True)
    out: list[str] = []
    in_guard = False       # currently inside a stripped #if($TBD_*) block
    guard_inner_depth = 0  # nested #if/#foreach depth inside the guard

    for raw in lines:
        line = raw.rstrip("\n\r")
        nl = raw[len(line):]  # preserve original line endings

        if in_guard:
            if _IF_OR_FOREACH_RE.match(line):
                # Nested control block inside the guard — keep it, track depth
                guard_inner_depth += 1
                out.append(_substitute_tokens(line, smap) + nl)
            elif _END_RE.match(line):
                if guard_inner_depth > 0:
                    # End of a nested block inside the guard — keep it
                    guard_inner_depth -= 1
                    out.append(line + nl)
                else:
                    # End of the TBD guard itself — strip it, exit guard mode (DD-1)
                    in_guard = False
            else:
                out.append(_substitute_tokens(line, smap) + nl)

        else:
            if _GUARD_OPEN_RE.match(line):
                # #if($TBD_*) opener — strip the line, enter guard mode (DD-1)
                in_guard = True
                guard_inner_depth = 0

            elif _FOREACH_LINE_RE.match(line):
                # #foreach line — replace with real directive when available
                tbd_ph = _find_tbd_token(line)
                if tbd_ph and tbd_ph in foreach_map:
                    out.append(foreach_map[tbd_ph] + nl)
                else:
                    out.append(_substitute_tokens(line, smap) + nl)

            else:
                out.append(_substitute_tokens(line, smap) + nl)

    return "".join(out)


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------


def _label(entry: dict) -> str:
    ctx = entry.get("context") or {}
    return ctx.get("nearest_label") or ctx.get("nearest_heading") or ""


def _src_line(entry: dict) -> int | str:
    ctx = entry.get("context") or {}
    return ctx.get("line") or "?"


def _next_action(reasoning: str) -> str:
    m = re.search(r"next-action:\s*([a-z-]+)", reasoning)
    return m.group(1) if m else ""


def _strip_next_action(reasoning: str) -> str:
    return re.sub(r"\s*—\s*next-action:\s*[a-z-]+", "", reasoning).strip()


_ACTION_GUIDANCE: dict[str, str] = {
    "supply-from-plugin": (
        "This path does not exist in the registry. "
        "A plugin (DocumentDataSnapshotPlugin or equivalent) must supply it as a scalar — "
        "e.g. `$data.data.myField`. Add the field in your Socotra config, "
        "regenerate the registry, re-run Leg 2, then re-run Leg 3."
    ),
    "restructure-template": (
        "A registry path exists but this variable needs to be inside a "
        "`#foreach` block. Add the foreach wrapper in the source HTML, "
        "re-run Leg 1, then Leg 2, then Leg 3."
    ),
    "pick-one": (
        "Multiple registry paths are equally plausible. "
        "Review the candidates in the .suggested.yaml, set `data_source` "
        "to the correct one, then re-run Leg 3."
    ),
    "confirm-assumption": (
        "Leg 2 made a fuzzy match — confirm the suggested path is correct "
        "before deploying. Edit `data_source` in the .suggested.yaml if needed, "
        "then re-run Leg 3."
    ),
    "delete-from-template": (
        "This field has no business purpose in this document. "
        "Remove the placeholder from the source HTML and re-run Leg 1."
    ),
}


def write_report(
    report_path: Path,
    *,
    stem: str,
    vm_path: Path,
    suggested_path: Path,
    out_vm_path: Path,
    resolved_vars: list[dict],
    unresolved_vars: list[dict],
    resolved_loops: list[dict],
    unresolved_loops: list[dict],
    deferred_vars: list[dict] | None = None,
    deferred_loops: list[dict] | None = None,
    high_only: bool = False,
    generated_at: str,
    repo_root: Path,
) -> None:
    deferred_vars = deferred_vars or []
    deferred_loops = deferred_loops or []
    total_all = (
        len(resolved_vars) + len(unresolved_vars)
        + len(resolved_loops) + len(unresolved_loops)
        + len(deferred_vars) + len(deferred_loops)
    )
    resolved_all = len(resolved_vars) + len(resolved_loops)
    deferred_all = len(deferred_vars) + len(deferred_loops)
    unresolved_all = len(unresolved_vars) + len(unresolved_loops)

    if total_all == 0:
        status = "EMPTY — no placeholders found"
    elif unresolved_all == 0 and deferred_all == 0:
        status = f"COMPLETE — all {total_all} token(s) resolved"
    elif resolved_all == 0 and deferred_all == 0:
        status = f"BLOCKED — 0 of {total_all} resolved"
    elif high_only and deferred_all > 0 and unresolved_all == 0:
        status = f"HIGH-ONLY — {resolved_all} substituted, {deferred_all} deferred for review"
    else:
        status = f"PARTIAL — {resolved_all} of {total_all} resolved, {unresolved_all} need attention"
        if high_only and deferred_all > 0:
            status += f", {deferred_all} deferred"

    suggested_rel = _rel(suggested_path, repo_root)

    lines: list[str] = [
        "<!-- leg3_schema_version: 1.0 -->",
        "",
        f"# Leg 3 Substitution Report — {stem}",
        "",
        "| | |",
        "|---|---|",
        f"| **Status** | {status} |",
        f"| **Source template** | `{vm_path.name}` |",
        f"| **Mapping used** | `{suggested_path.name}` |",
        f"| **Output template** | `{out_vm_path.name}` |",
        f"| **Mode** | {'high-only (DD-4)' if high_only else 'standard'} |",
        f"| **Generated** | {generated_at} |",
        "",
        "---",
        "",
    ]

    # ---- §1 Resolved ---------------------------------------------------------
    lines += [
        f"## Resolved ({resolved_all})",
        "",
    ]
    if resolved_vars or resolved_loops:
        lines += [
            "These tokens have been substituted in the output template.",
            "",
            "| Type | Placeholder | Label | Velocity Path | Confidence |",
            "|---|---|---|---|---|",
        ]
        for v in resolved_vars:
            ph = v.get("placeholder") or ""
            ds = v.get("data_source") or ""
            label = _label(v)
            conf = v.get("confidence") or ""
            lines.append(f"| variable | `{ph}` | {label} | `{ds}` | {conf} |")
        for L in resolved_loops:
            ph = L.get("placeholder") or ""
            ds = L.get("data_source") or ""
            conf = L.get("confidence") or ""
            lines.append(f"| loop | `{ph}` | — | `{ds}` | {conf} |")
    else:
        lines.append("_Nothing resolved this run._")
    lines += ["", "---", ""]

    # ---- §2 Deferred (high-only mode) ----------------------------------------
    if high_only:
        lines += [
            f"## Deferred — medium/low confidence ({deferred_all})",
            "",
        ]
        if deferred_all == 0:
            lines += ["No deferred entries. All entries with data_source were high confidence.", "", "---", ""]
        else:
            lines += [
                "These entries have a suggested path but were **not substituted** because",
                "confidence is medium or low. Confirm each path in the `.suggested.yaml`,",
                "then re-run Leg 3 without `high_only=true` to apply them.",
                "",
                "| Type | Placeholder | Label | Suggested path | Confidence | Reasoning |",
                "|---|---|---|---|---|---|",
            ]
            for v in deferred_vars:
                ph = v.get("placeholder") or ""
                ds = v.get("data_source") or ""
                label = _label(v)
                conf = v.get("confidence") or ""
                reasoning = _strip_next_action(v.get("reasoning") or "")
                lines.append(f"| variable | `{ph}` | {label} | `{ds}` | {conf} | {reasoning} |")
            for L in deferred_loops:
                ph = L.get("placeholder") or ""
                ds = L.get("data_source") or ""
                conf = L.get("confidence") or ""
                reasoning = _strip_next_action(L.get("reasoning") or "")
                lines.append(f"| loop | `{ph}` | — | `{ds}` | {conf} | {reasoning} |")
            lines += [
                "",
                "> **To apply deferred entries:** review and confirm `data_source` values above,",
                "> then re-run: `RUN_PIPELINE leg3 suggested=<path>`",
                "",
                "---",
                "",
            ]

    # ---- §3 Unresolved -------------------------------------------------------
    lines += [
        f"## Unresolved ({unresolved_all})",
        "",
    ]
    if unresolved_all == 0:
        lines += ["All tokens resolved. No action needed.", "", "---", ""]
    else:
        lines += [
            "These tokens remain as `$TBD_*` in the output template.",
            f"For each one: find the correct Velocity path, update `{suggested_path.name}`,",
            "then re-run Leg 3.",
            "",
        ]

        all_unresolved: list[tuple[str, dict]] = (
            [("variable", v) for v in unresolved_vars]
            + [("loop", L) for L in unresolved_loops]
        )

        for kind, entry in all_unresolved:
            ph = entry.get("placeholder") or entry.get("name") or ""
            name = entry.get("name") or ph.lstrip("$").lstrip("TBD_")
            label = _label(entry)
            src_line = _src_line(entry)
            reasoning = entry.get("reasoning") or ""
            na = _next_action(reasoning)
            display_reason = _strip_next_action(reasoning)
            guidance = _ACTION_GUIDANCE.get(na, "")

            lines += [
                f"### `{ph}`",
                "",
                "| | |",
                "|---|---|",
            ]
            if label:
                lines.append(f'| **Label** | "{label}" |')
            lines += [
                f"| **Source line** | {src_line} |",
                f"| **Type** | {kind} |",
            ]
            if na:
                lines.append(f"| **Action needed** | `{na}` |")
            if display_reason:
                lines.append(f"| **Leg 2 note** | {display_reason} |")
            lines.append("")

            if guidance:
                lines += [
                    f"> {guidance}",
                    "",
                ]

            lines += [
                "```yaml",
                f"# In {suggested_path.name} — fill in data_source, then re-run Leg 3",
                f"- name: {name}",
                f"  placeholder: {ph}",
                f'  data_source: ""   # <-- replace with the correct Velocity path',
                "```",
                "",
            ]

        lines += ["---", ""]

    # ---- §4 Next steps -------------------------------------------------------
    lines += ["## Next steps", ""]

    if unresolved_all > 0:
        lines += [
            f"1. Fill in `data_source` for each **Unresolved** token in `{suggested_path.name}`",
            "2. Re-run Leg 3:",
            "   ```",
            f"   RUN_PIPELINE leg3 suggested={suggested_rel}",
            "   ```",
            "3. If the path doesn't exist in the registry yet:",
            "   - Add the field to your Socotra config",
            "   - Regenerate the registry: `python3 .cursor/skills/mapping-suggester/scripts/extract_paths.py`",
            "   - Re-run Leg 2 to update the suggested mapping",
            "   - Then re-run Leg 3",
            "",
        ]
    else:
        lines += [
            f"Template is fully resolved. Review `{out_vm_path.name}` and deploy.",
            "",
        ]

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--suggested", type=Path, required=True,
        help=".suggested.yaml produced by Leg 2",
    )
    ap.add_argument(
        "--vm", type=Path, default=None,
        help=".vm from Leg 1 (default: <stem>.vm in same dir as --suggested)",
    )
    ap.add_argument(
        "--out", type=Path, default=None,
        help="Output path for final .vm (default: <stem>.final.vm in same dir)",
    )
    ap.add_argument(
        "--report-out", type=Path, default=None,
        help="Output path for the report (default: <stem>.leg3-report.md in same dir)",
    )
    ap.add_argument(
        "--high-only", action="store_true", default=False,
        help="Only substitute high-confidence tokens; defer medium/low to review (DD-4)",
    )
    args = ap.parse_args()

    # --- Resolve paths --------------------------------------------------------
    suggested_path = args.suggested.resolve()
    if not suggested_path.exists():
        print(f"ERROR: suggested file not found: {suggested_path}", file=sys.stderr)
        return 1

    stem = suggested_path.name
    for suffix in (".suggested.yaml", ".yaml"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break

    out_dir = suggested_path.parent
    vm_path = args.vm.resolve() if args.vm else (out_dir / f"{stem}.vm")
    if not vm_path.exists():
        print(f"ERROR: .vm file not found: {vm_path}", file=sys.stderr)
        return 1

    out_vm_path = args.out.resolve() if args.out else (out_dir / f"{stem}.final.vm")
    report_path = (
        args.report_out.resolve() if args.report_out
        else (out_dir / f"{stem}.leg3-report.md")
    )

    repo_root = _repo_root()

    high_only = args.high_only

    # --- Load ----------------------------------------------------------------
    suggested = _load_yaml(suggested_path)
    vm_text = vm_path.read_text(encoding="utf-8")

    # --- Build maps ----------------------------------------------------------
    smap = build_substitution_map(suggested, high_only=high_only)
    foreach_map = build_foreach_map(suggested, high_only=high_only)

    # --- Process -------------------------------------------------------------
    final_vm = process_vm(vm_text, smap, foreach_map)

    # --- Categorise entries (DD-4: split deferred bucket when high_only) -----
    variables = suggested.get("variables") or []
    loops = suggested.get("loops") or []

    if high_only:
        resolved_vars = [v for v in variables if v.get("data_source") and v.get("confidence") == "high"]
        deferred_vars = [v for v in variables if v.get("data_source") and v.get("confidence") != "high"]
        unresolved_vars = [v for v in variables if not v.get("data_source")]
        resolved_loops = [L for L in loops if L.get("data_source") and L.get("confidence") == "high"]
        deferred_loops = [L for L in loops if L.get("data_source") and L.get("confidence") != "high"]
        unresolved_loops = [L for L in loops if not L.get("data_source")]
    else:
        resolved_vars = [v for v in variables if v.get("data_source")]
        deferred_vars = []
        unresolved_vars = [v for v in variables if not v.get("data_source")]
        resolved_loops = [L for L in loops if L.get("data_source")]
        deferred_loops = []
        unresolved_loops = [L for L in loops if not L.get("data_source")]

    # --- Write ---------------------------------------------------------------
    out_dir.mkdir(parents=True, exist_ok=True)
    out_vm_path.write_text(final_vm, encoding="utf-8")

    generated_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_report(
        report_path,
        stem=stem,
        vm_path=vm_path,
        suggested_path=suggested_path,
        out_vm_path=out_vm_path,
        resolved_vars=resolved_vars,
        unresolved_vars=unresolved_vars,
        resolved_loops=resolved_loops,
        unresolved_loops=unresolved_loops,
        deferred_vars=deferred_vars,
        deferred_loops=deferred_loops,
        high_only=high_only,
        generated_at=generated_at,
        repo_root=repo_root,
    )

    print(f"Wrote {out_vm_path}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
