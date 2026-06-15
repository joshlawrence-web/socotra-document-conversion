from __future__ import annotations

import re
from pathlib import Path

_NA_RE = re.compile(r"next-action:\s*([a-z-]+)")
_CANDIDATE_RE = re.compile(r"registry candidate `([^`]+)`")

def _extract_na(reasoning: str) -> str | None:
    m = _NA_RE.search(reasoning)
    return m.group(1) if m else None


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
    """Read per-root verdict; falls back to flat schema 1.x fields when verdicts absent."""
    v = (entry.get("verdicts") or {}).get(root_id)
    if v is not None:
        return v
    # Schema 1.x fallback: flat confidence/data_source/reasoning on the entry itself.
    if "confidence" in entry or "data_source" in entry:
        return {
            "confidence": entry.get("confidence") or "",
            "data_source": entry.get("data_source") or "",
            "reasoning": entry.get("reasoning") or "",
        }
    return {}


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
) -> None:
    idx: dict = suggested.get("_idx") or {}
    variables = suggested.get("variables") or []
    loops = suggested.get("loops") or []
    all_e = list(variables) + list(loops)

    roots = _root_ids(suggested) or ["(none)"]
    primary = roots[0]

    # Per-root confidence counts (includes `none` for old-format / schema-miss).
    def _counts(root_id: str) -> tuple[int, int, int, int]:
        hi = me = lo = no = 0
        for e in all_e:
            c = _verdict(e, root_id).get("confidence")
            if c == "high":
                hi += 1
            elif c == "medium":
                me += 1
            elif c == "low":
                lo += 1
            elif c == "none":
                no += 1
        return hi, me, lo, no

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
    ]
    lines += [
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

    # §1b State summary — always present; compact counts for programmatic parsing.
    lines += [
        "## State summary",
        "",
        f"- Variables: {len(variables)}  ·  Loops: {len(loops)}",
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
        "| Root | Primary | high | medium | low | none |",
        "|---|---|---|---|---|---|",
    ]
    primary_set = {r.get("id"): r.get("primary") for r in rr}
    for root_id in roots:
        hi, me, lo, no = _counts(root_id)
        is_primary = "yes" if primary_set.get(root_id) or root_id == primary else "no"
        lines.append(f"| `{root_id}` | {is_primary} | {hi} | {me} | {lo} | {no} |")
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

    # §3 Blockers — one row per (placeholder, root) with low confidence (non-lifecycle).
    all_low_pairs: list[tuple[dict, str]] = [
        (e, root_id)
        for e in sorted(all_e, key=_fmt_line)
        for root_id in roots
        if _verdict(e, root_id).get("confidence") == "low"
    ]
    lifecycle_pairs = [(e, r) for e, r in all_low_pairs
                       if _verdict(e, r).get("sdk_status") == "lifecycle_violation"]
    feature_gated_pairs = [(e, r) for e, r in all_low_pairs
                           if _verdict(e, r).get("sdk_status") == "feature_gated"]
    blocker_pairs = [(e, r) for e, r in all_low_pairs
                     if _verdict(e, r).get("sdk_status")
                     not in ("lifecycle_violation", "feature_gated")]

    lines += ["---", "", "## Lifecycle violations (DataFetcher method unavailable on root)", ""]
    if not lifecycle_pairs:
        lines.append("No lifecycle violations.")
    else:
        lines += [
            "These fields matched a DataFetcher registry entry but the DataFetcher method is "
            "not available on that rendering root (e.g. `getQuotePricing()` on a segment root). "
            "They are low confidence on that root only — check the valid_roots annotation.",
            "",
            "| Placeholder | Line | Root | Method | Reasoning |",
            "|---|---|---|---|---|",
        ]
        for e, root_id in lifecycle_pairs:
            ph = e.get("placeholder") or e.get("name") or ""
            ln = _fmt_line(e)
            vd = _verdict(e, root_id)
            cand = e.get("candidate") or {}
            method = cand.get("datafetcher_method", "—")
            reasoning = (vd.get("reasoning") or "")[:120]
            lines.append(f"| `{ph}` | {ln} | `{root_id}` | `{method}` | {reasoning} |")
    lines.append("")

    lines += ["---", "", "## Blockers (low confidence, per root)", ""]
    if not blocker_pairs:
        lines.append("No blockers.")
    else:
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
    lines.append("")

    # §3c Feature-gated paths — SDK method exists but its feature_support flag is off.
    lines += ["---", "", "## Feature-gated paths (disabled feature_support)", ""]
    if not feature_gated_pairs:
        lines.append("No feature-gated paths.")
    else:
        lines += [
            "These placeholders matched an SDK method that exists on the rendering root, "
            "but the field is only populated when a `feature_support` flag is enabled — "
            "and that flag is currently **disabled** in the registry. They were demoted "
            "(not auto-filled): the path would evaluate to null at render time. Supply the "
            "value from the plugin, or remove it from the template.",
            "",
            "| Placeholder | Line | Root | feature_support flag | next-action |",
            "|---|---|---|---|---|",
        ]
        for e, root_id in feature_gated_pairs:
            ph = e.get("placeholder") or e.get("name") or ""
            ln = _fmt_line(e)
            vd = _verdict(e, root_id)
            flag = vd.get("feature_gate") or "—"
            lines.append(
                f"| `{ph}` | {ln} | `{root_id}` | `{flag}` | confirm-assumption |"
            )
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
    else:
        lines.append(f"{len(assumption_pairs)} assumption(s) to confirm — see .mapping.yaml")
    lines.append("")

    # §4b Token Format Errors — old-format or schema-miss tokens (confidence: none).
    old_format_vars = [
        e for e in sorted(all_e, key=_fmt_line)
        if (e.get("candidate") or {}).get("match_step") in ("old-format", "none")
    ]
    lines += ["---", "", "## Token Format Errors", ""]
    if not old_format_vars:
        lines.append("No token format errors.")
    else:
        lines += [
            "These placeholders use the old `{{FIELDNAME}}` format or reference an entity/field "
            "not found in `registry/sdk-schema-index.yaml`. Rename them to "
            "`{{EntityType.fieldName}}` using the schema index.",
            "",
            "| Token | Line | match_step | next-action |",
            "|---|---|---|---|",
        ]
        for e in old_format_vars:
            ph = e.get("placeholder") or e.get("name") or ""
            ln = _fmt_line(e)
            ms = (e.get("candidate") or {}).get("match_step", "")
            lines.append(f"| `{ph}` | {ln} | `{ms}` | fix-token |")
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
        lines.append(f"- `{ph}` · `{root_id}` → `{ds}`")
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
