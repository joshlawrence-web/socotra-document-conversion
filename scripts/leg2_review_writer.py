from __future__ import annotations

import re
from pathlib import Path

_NA_RE = re.compile(r"next-action:\s*([a-z-]+)")
_CANDIDATE_RE = re.compile(r"registry candidate `([^`]+)`")

_RESOLUTION = {
    "supply-from-plugin": (
        "No registry path exists for this field. "
        "A plugin (DocumentDataSnapshotPlugin or equivalent) must supply it as a scalar on `$data.data.*`."
    ),
    "restructure-template": (
        "A registry path exists but the template is missing the required `#foreach` wrapper. "
        "Add the foreach block shown in `requires_scope` and move this variable inside it."
    ),
    "pick-one": (
        "Multiple registry paths are equally plausible. "
        "Review the candidates and set `data_source` to the correct one before running Leg 3."
    ),
    "delete-from-template": "This field has no business purpose in this document. Remove the placeholder.",
    "confirm-assumption": "",  # medium only — appears in §4 not §3
}


def _extract_na(reasoning: str) -> str | None:
    m = _NA_RE.search(reasoning)
    return m.group(1) if m else None


def _extract_candidates(reasoning: str) -> list[str]:
    m = re.search(r"pick-one:\s*(.+)", reasoning)
    if m:
        return [p.strip() for p in m.group(1).split("|") if p.strip()]
    return []


def _fmt_line(entry: dict) -> int:
    return (entry.get("context") or {}).get("line") or 999


def _all_entries(suggested: dict) -> list[dict]:
    return list(suggested.get("variables") or []) + list(suggested.get("loops") or [])


def _check_minor_mismatch(suggested: dict) -> str | None:
    """Return the registry MINOR version string if it exceeds 1.1, else None."""
    rv = str(suggested.get("registry_schema_version") or "1.0")
    parts = rv.split(".")
    try:
        if len(parts) >= 2 and int(parts[1]) > 1:
            return rv
    except ValueError:
        pass
    return None


def _write_review_md(
    review_path: Path,
    *,
    stem: str,
    suggested_path: Path,
    suggested: dict,
    mapping_path: Path,
    registry_path: Path,
    gate_label: str,
    escape_note: str,
    mode: str = "terse",
) -> None:
    idx: dict = suggested.get("_idx") or {}
    variables = suggested.get("variables") or []
    loops = suggested.get("loops") or []
    all_e = list(variables) + list(loops)

    high_v = sum(1 for v in variables if v.get("confidence") == "high")
    med_v = sum(1 for v in variables if v.get("confidence") == "medium")
    low_v = sum(1 for v in variables if v.get("confidence") == "low")
    high_l = sum(1 for L in loops if L.get("confidence") == "high")
    med_l = sum(1 for L in loops if L.get("confidence") == "medium")
    low_l = sum(1 for L in loops if L.get("confidence") == "low")
    high = high_v + high_l
    med = med_v + med_l
    low = low_v + low_l

    # Next-action counts
    na_counts: dict[str, int] = {}
    for e in all_e:
        na = _extract_na(e.get("reasoning") or "")
        if na:
            na_counts[na] = na_counts.get(na, 0) + 1

    dc = suggested.get("delta_changes") or {}

    lines: list[str] = [
        "<!-- schema_version: 1.1 -->",
        "",
        f"# Mapping review — {stem}",
        "",
        f"- Run id: `{suggested.get('run_id', '')}`",
        f"- Mode: **{suggested.get('mode', 'terse')}**",
        f"- Source mapping: `{mapping_path}`",
        f"- Suggested output: `{suggested_path}`",
        f"- Path registry: `{registry_path}`",
        f"- Product: **{suggested.get('product', '')}**",
        f"- Generated at: {suggested.get('generated_at', '')}",
        (
            f"- Inputs: mapping sha256 `{suggested.get('input_mapping_sha256', '')[:16]}…`, "
            f"registry sha256 `{suggested.get('input_registry_sha256', '')[:16]}…`"
        ),
        (
            f"- Registry lineage: generated `{suggested.get('registry_generated_at', '')}`, "
            f"config_dir `{suggested.get('registry_config_dir', '')}`"
        ),
        (
            f"- Registry config check: **{gate_label}** "
            f"(verified={'yes' if suggested.get('registry_config_verified') else 'no'})"
        ),
    ]
    if suggested.get("mode") == "delta":
        lines.append(
            f"- Base suggested: `{suggested.get('base_suggested_sha256', '')[:16]}…` "
            f"(previous_run_id `{suggested.get('previous_run_id', '')}`)"
        )
    if escape_note:
        lines += ["", f"> **{escape_note}**", ""]
    lines += [
        f"- Schema: 1.1 (mapping {suggested.get('input_mapping_version')}, "
        f"registry {suggested.get('input_registry_version')})",
        "",
        "---",
        "",
    ]

    # §1 already written above. §2 State summary + counts.
    lines += [
        "## State summary",
        "",
        f"- `run_id`: `{suggested.get('run_id', '')}`",
        f"- `registry_config_check`: {suggested.get('registry_config_check', '')}",
    ]
    if suggested.get("mode") == "delta":
        lines.append(
            f"- Delta: changed={len(dc.get('changed') or [])}, "
            f"cleared={len(dc.get('cleared') or [])}, "
            f"re-suggested={len(dc.get('re_suggested_unconfirmed') or [])}, "
            f"carried_confirmed={dc.get('carried_forward_count', 0)}"
        )
    lines += [
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|---|---|",
        f"| Variables (total) | {len(variables)} |",
        f"| Loops (total) | {len(loops)} |",
        f"| high | {high} |",
        f"| medium | {med} |",
        f"| low | {low} |",
        "",
        "### Next-action breakdown",
        "",
        "| next-action | Count |",
        "|---|---|",
    ]
    for code in ("pick-one", "supply-from-plugin", "restructure-template",
                 "confirm-assumption", "delete-from-template"):
        cnt = na_counts.get(code, 0)
        lines.append(f"| {code} | {cnt} |")
    lines.append("")

    # Per-confidence breakdown (subsections of Summary)
    for conf_label, conf_key in (("High", "high"), ("Medium", "medium"), ("Low", "low")):
        conf_loops = [L for L in loops if L.get("confidence") == conf_key]
        conf_vars = [v for v in variables if v.get("confidence") == conf_key]
        if not conf_loops and not conf_vars:
            continue
        lines += [
            f"### {conf_label} confidence",
            "",
            "| Type | Count |",
            "|---|---|",
            f"| Loops | {len(conf_loops)} |",
            f"| Fields | {len(conf_vars)} |",
            "",
        ]
        if conf_loops:
            lines += ["**Loop names**", "", "| Name | Velocity Path |", "|---|---|"]
            for L in conf_loops:
                ph = L.get("placeholder") or L.get("name") or ""
                vel = L.get("data_source") or "—"
                lines.append(f"| `{ph}` | `{vel}` |")
            lines.append("")
        if conf_vars:
            lines += ["**Field names**", "", "| Name | Velocity Path |", "|---|---|"]
            for v in conf_vars:
                ph = v.get("placeholder") or v.get("name") or ""
                vel = v.get("data_source") or "—"
                lines.append(f"| `{ph}` | `{vel}` |")
            lines.append("")

    # §3 Blockers
    lines += ["---", "", "## Blockers", ""]
    blockers = sorted([e for e in all_e if e.get("confidence") == "low"], key=_fmt_line)
    if not blockers:
        lines.append("No blockers.")
    elif mode == "terse":
        lines += [
            "| Placeholder | Line | next-action |",
            "|---|---|---|",
        ]
        for e in blockers:
            ph = e.get("placeholder") or e.get("name") or ""
            ln = _fmt_line(e)
            na = _extract_na(e.get("reasoning") or "") or "supply-from-plugin"
            lines.append(f"| `{ph}` | {ln} | {na} |")
    else:
        for e in blockers:
            ph = e.get("placeholder") or e.get("name") or ""
            ctx = e.get("context") or {}
            ln = ctx.get("line") or "?"
            parent_tag = ctx.get("parent_tag") or "—"
            nearest_label = ctx.get("nearest_label") or ""
            loop_ctx = ctx.get("loop") or "—"
            reasoning = e.get("reasoning") or ""
            na = _extract_na(reasoning) or "supply-from-plugin"
            cands = _extract_candidates(reasoning)
            lines += [
                f"### {ph}  _(line {ln})_",
                "",
                f"- **parent_tag:** `{parent_tag}`",
                f"- **nearest_label:** \"{nearest_label}\"",
                f"- **loop:** `{loop_ctx}`",
            ]
            if cands:
                lines.append("- **candidates:**")
                for c in cands:
                    lines.append(f"  - `{c}`")
            lines += [
                f"- **next-action:** `{na}`",
                f"- **suggested resolution:** {_RESOLUTION.get(na, '')}",
                "",
            ]
    lines.append("")

    # §4 Assumptions to confirm
    lines += ["---", "", "## Assumptions to confirm", ""]
    assumptions = sorted(
        [e for e in all_e if e.get("confidence") == "medium" and "confirm-assumption" in (e.get("reasoning") or "")],
        key=_fmt_line,
    )
    if not assumptions:
        lines.append("No assumptions to confirm.")
    elif mode == "terse":
        lines.append(f"{len(assumptions)} assumption(s) to confirm — see .suggested.yaml")
    else:
        for e in assumptions:
            ph = e.get("placeholder") or e.get("name") or ""
            ds = e.get("data_source") or ""
            ctx = e.get("context") or {}
            ln = ctx.get("line") or "?"
            reasoning = e.get("reasoning") or ""
            m = re.search(r"confirm-assumption:\s*(.+?)(?:\s*—|$)", reasoning)
            assumption_text = m.group(1).strip() if m else reasoning
            lines += [
                f"- [ ] **{assumption_text}**",
                f"  - `{ph}` (line {ln}) → `{ds}`",
            ]
    lines.append("")

    # §5 Cross-scope warnings
    lines += ["---", "", "## Cross-scope warnings", ""]
    scope_warns = sorted(
        [
            e for e in all_e
            if "scope violation" in (e.get("reasoning") or "").lower()
            or (
                "restructure-template" in (e.get("reasoning") or "")
                and "registry candidate" in (e.get("reasoning") or "")
            )
        ],
        key=_fmt_line,
    )
    if not scope_warns:
        lines.append("No cross-scope warnings.")
    else:
        lines += [
            "| Placeholder | Matched path | Requires scope | Fix |",
            "|---|---|---|---|",
        ]
        for e in scope_warns:
            ph = e.get("placeholder") or e.get("name") or ""
            reasoning = e.get("reasoning") or ""
            cand_m = _CANDIDATE_RE.search(reasoning)
            matched_path = cand_m.group(1) if cand_m else ""
            req_m = re.search(r"`(#foreach[^`]+)`", reasoning)
            req_scope = req_m.group(1) if req_m else "—"
            lines.append(f"| `{ph}` | `{matched_path}` | `{req_scope}` | restructure-template |")
    lines.append("")

    # §6 Done
    lines += ["---", "", "## Done", ""]
    done = [e for e in all_e if e.get("confidence") == "high"]
    if mode == "terse":
        lines += [
            "<details>",
            f"<summary><strong>{len(done)}</strong> high-confidence mapping(s)</summary>",
            "",
        ]
        for e in done:
            ph = e.get("placeholder") or e.get("name") or ""
            ds = e.get("data_source") or ""
            lines.append(f"- `{ph}` → `{ds}`")
        lines += ["", "</details>"]
    else:
        lines += [
            "<details>",
            f"<summary><strong>{len(done)}</strong> high-confidence mapping(s)</summary>",
            "",
        ]
        for e in done:
            ph = e.get("placeholder") or e.get("name") or ""
            ds = e.get("data_source") or ""
            reason = e.get("reasoning") or ""
            lines.append(f"- `{ph}` → `{ds}`  _{reason}_")
        lines += ["", "</details>"]
    lines.append("")

    # §7 Unrecognised inputs
    lines += ["---", "", "## Unrecognised inputs", ""]
    refusal_flags = idx.get("refusal_flags") or []
    partial_flags = idx.get("partial_flags") or []
    reg_minor = _check_minor_mismatch(suggested)

    unrecognised_rows: list[tuple[str, str, str, str]] = []
    if reg_minor:
        unrecognised_rows.append((
            "registry",
            f"schema_version MINOR={reg_minor}",
            "all entries",
            "needs-skill-update: registry schema MINOR version exceeds supported MINOR",
        ))
    for flag in refusal_flags:
        unrecognised_rows.append((
            "registry",
            f"feature_support.{flag}",
            "all variables",
            f"needs-skill-update: refusal flag `{flag}` is true; affected entries may need manual handling",
        ))
    for flag in partial_flags:
        unrecognised_rows.append((
            "registry",
            f"feature_support.{flag}`",
            "all variables",
            f"needs-skill-update: partial-support flag `{flag}` is true; verify coverage",
        ))

    if not unrecognised_rows:
        lines.append("No unrecognised inputs.")
    else:
        lines += [
            "| Source | Key | Seen on | Next-action |",
            "|---|---|---|---|",
        ]
        for source, key, seen, na in unrecognised_rows:
            lines.append(f"| {source} | `{key}` | {seen} | {na} |")
    lines.append("")

    review_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
