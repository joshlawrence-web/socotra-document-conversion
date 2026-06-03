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


# --- 2.0 per-root helpers ---------------------------------------------------


def _root_ids(suggested: dict) -> list[str]:
    rids = suggested.get("_root_ids")
    if rids:
        return list(rids)
    return [r.get("id") for r in (suggested.get("rendering_roots") or []) if r.get("id")]


def _verdict(entry: dict, root_id: str) -> dict:
    return (entry.get("verdicts") or {}).get(root_id) or {}


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

    roots = _root_ids(suggested) or ["(none)"]
    primary = roots[0]

    # Per-root confidence counts.
    def _counts(root_id: str) -> tuple[int, int, int]:
        hi = me = lo = 0
        for e in all_e:
            c = _verdict(e, root_id).get("confidence")
            if c == "high":
                hi += 1
            elif c == "medium":
                me += 1
            elif c == "low":
                lo += 1
        return hi, me, lo

    # Next-action counts on the primary root.
    na_counts: dict[str, int] = {}
    for e in all_e:
        na = _extract_na(_verdict(e, primary).get("reasoning") or "")
        if na:
            na_counts[na] = na_counts.get(na, 0) + 1

    rr = suggested.get("rendering_roots") or []
    roots_label = ", ".join(
        f"`{r.get('id')}`" + (" (primary)" if r.get("primary") else "")
        for r in rr
    ) or ", ".join(f"`{r}`" for r in roots)

    lines: list[str] = [
        "<!-- schema_version: 2.0 -->",
        "",
        f"# Mapping review — {stem}",
        "",
        f"- Run id: `{suggested.get('run_id', '')}`",
        f"- Mode: **{suggested.get('mode', 'terse')}**",
        f"- Source mapping: `{mapping_path}`",
        f"- Suggested output: `{suggested_path}`",
        f"- Path registry: `{registry_path}`",
        f"- Product: **{suggested.get('product', '')}**",
        f"- Rendering roots: {roots_label}",
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
    if escape_note:
        lines += ["", f"> **{escape_note}**", ""]
    lines += [
        f"- Schema: 2.0 (mapping {suggested.get('input_mapping_version')}, "
        f"registry {suggested.get('input_registry_version')})",
        "",
        "> Confidence is graded per **(placeholder × rendering root)**, grounded in the "
        "compiled JARs. A field can be `high` on one root and a blocker on another.",
        "",
        "---",
        "",
    ]

    # §2 Summary — per rendering root.
    lines += [
        "## Summary (per rendering root)",
        "",
        f"- Variables: {len(variables)}  ·  Loops: {len(loops)}",
        "",
        "| Root | Primary | high | medium | low |",
        "|---|---|---|---|---|",
    ]
    primary_set = {r.get("id"): r.get("primary") for r in rr}
    for root_id in roots:
        hi, me, lo = _counts(root_id)
        is_primary = "yes" if primary_set.get(root_id) or root_id == primary else "no"
        lines.append(f"| `{root_id}` | {is_primary} | {hi} | {me} | {lo} |")
    lines += [
        "",
        f"### Next-action breakdown (primary root: `{primary}`)",
        "",
        "| next-action | Count |",
        "|---|---|",
    ]
    for code in ("pick-one", "supply-from-plugin", "restructure-template",
                 "confirm-assumption", "delete-from-template"):
        lines.append(f"| {code} | {na_counts.get(code, 0)} |")
    lines.append("")

    # §3 Blockers — one row per (placeholder, root) with low confidence.
    lines += ["---", "", "## Blockers (low confidence, per root)", ""]
    blocker_pairs: list[tuple[dict, str]] = []
    for e in sorted(all_e, key=_fmt_line):
        for root_id in roots:
            if _verdict(e, root_id).get("confidence") == "low":
                blocker_pairs.append((e, root_id))
    if not blocker_pairs:
        lines.append("No blockers.")
    elif mode == "terse":
        lines += [
            "| Placeholder | Line | Root | sdk_status | next-action |",
            "|---|---|---|---|---|",
        ]
        for e, root_id in blocker_pairs:
            ph = e.get("placeholder") or e.get("name") or ""
            ln = _fmt_line(e)
            vd = _verdict(e, root_id)
            na = _extract_na(vd.get("reasoning") or "") or "supply-from-plugin"
            lines.append(
                f"| `{ph}` | {ln} | `{root_id}` | {vd.get('sdk_status', '')} | {na} |"
            )
    else:
        for e, root_id in blocker_pairs:
            ph = e.get("placeholder") or e.get("name") or ""
            ctx = e.get("context") or {}
            ln = ctx.get("line") or "?"
            vd = _verdict(e, root_id)
            reasoning = vd.get("reasoning") or ""
            na = _extract_na(reasoning) or "supply-from-plugin"
            cands = _extract_candidates(reasoning)
            lines += [
                f"### {ph} · root `{root_id}`  _(line {ln})_",
                "",
                f"- **parent_tag:** `{ctx.get('parent_tag') or '—'}`",
                f"- **nearest_label:** \"{ctx.get('nearest_label') or ''}\"",
                f"- **sdk_status:** `{vd.get('sdk_status', '')}`",
            ]
            if vd.get("sibling_hint"):
                lines.append(f"- **sibling_hint:** `{vd['sibling_hint']}`")
            if cands:
                lines.append("- **candidates:**")
                for c in cands:
                    lines.append(f"  - `{c}`")
            lines += [
                f"- **next-action:** `{na}`",
                f"- **suggested resolution:** {_RESOLUTION.get(na, '')}",
                f"- **reasoning:** {reasoning}",
                "",
            ]
    lines.append("")

    # §4 Assumptions to confirm — medium-confidence verdicts, per root.
    lines += ["---", "", "## Assumptions to confirm (medium confidence, per root)", ""]
    assumption_pairs: list[tuple[dict, str]] = []
    for e in sorted(all_e, key=_fmt_line):
        for root_id in roots:
            if _verdict(e, root_id).get("confidence") == "medium":
                assumption_pairs.append((e, root_id))
    if not assumption_pairs:
        lines.append("No assumptions to confirm.")
    elif mode == "terse":
        lines.append(f"{len(assumption_pairs)} assumption(s) to confirm — see .suggested.yaml")
    else:
        for e, root_id in assumption_pairs:
            ph = e.get("placeholder") or e.get("name") or ""
            vd = _verdict(e, root_id)
            ds = vd.get("data_source") or ""
            ln = (e.get("context") or {}).get("line") or "?"
            lines += [
                f"- [ ] `{ph}` · root `{root_id}` (line {ln}) → `{ds}`",
                f"  - {vd.get('reasoning') or ''}",
            ]
    lines.append("")

    # §5 Cross-scope warnings — scanned on the primary root.
    lines += ["---", "", "## Cross-scope warnings", ""]
    scope_warns = sorted(
        [
            e for e in all_e
            if "scope violation" in (_verdict(e, primary).get("reasoning") or "").lower()
            or (
                "restructure-template" in (_verdict(e, primary).get("reasoning") or "")
                and "registry candidate" in (_verdict(e, primary).get("reasoning") or "")
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
            reasoning = _verdict(e, primary).get("reasoning") or ""
            cand_m = _CANDIDATE_RE.search(reasoning)
            matched_path = cand_m.group(1) if cand_m else ""
            req_m = re.search(r"`(#foreach[^`]+)`", reasoning)
            req_scope = req_m.group(1) if req_m else "—"
            lines.append(f"| `{ph}` | `{matched_path}` | `{req_scope}` | restructure-template |")
    lines.append("")

    # §6 Done — high-confidence verdicts, per root.
    lines += ["---", "", "## Done (high confidence, per root)", ""]
    done_pairs: list[tuple[dict, str]] = []
    for e in all_e:
        for root_id in roots:
            if _verdict(e, root_id).get("confidence") == "high":
                done_pairs.append((e, root_id))
    lines += [
        "<details>",
        f"<summary><strong>{len(done_pairs)}</strong> high-confidence (placeholder × root) verdict(s)</summary>",
        "",
    ]
    for e, root_id in done_pairs:
        ph = e.get("placeholder") or e.get("name") or ""
        vd = _verdict(e, root_id)
        ds = vd.get("data_source") or ""
        if mode == "terse":
            lines.append(f"- `{ph}` · `{root_id}` → `{ds}`")
        else:
            lines.append(f"- `{ph}` · `{root_id}` → `{ds}`  _{vd.get('reasoning') or ''}_")
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
