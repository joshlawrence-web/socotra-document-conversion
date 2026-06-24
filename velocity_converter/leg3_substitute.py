#!/usr/bin/env python3
"""Leg 3 — Substitution Writer.

Reads:
  - <stem>.vm           (Leg 1) — template with $TBD_* placeholders and #if guards
  - <stem>.mapping.yaml (Leg 2) — enriched mapping with confirmed data_source paths

Writes:
  - <stem>.final.vm        — production-ready Velocity template
  - <stem>.leg3-report.md  — remedy form listing resolved and unresolved tokens

Design decisions (DD — recorded here and in docs/SCHEMA.md):
  DD-1: #if($TBD_*) guards are stripped from the final output. Tradeoff:
        readability over null-safety. Guards can be added manually or by a
        future leg when the full data contract is known.
  DD-2: Unresolved tokens ($TBD_* with empty data_source) are preserved
        as-is so the template remains parseable.
  DD-3: Lenient mode — substitute every resolved token, report the rest.
        Never aborts on empty data_source entries.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

import yaml

from velocity_converter.models import (
    ConditionalRegistry,
    ContractError,
    SuggestedDoc,
    block_key,
    load_contract,
    validate_contract,
)


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


def _load_cond_registry(path: Path) -> list[dict]:
    """Load a conditional-registry.yaml; return [] if absent or invalid.

    Conditional substitution is an optional enrichment here, so a malformed
    registry degrades with a warning instead of halting (Leg 4, which needs
    the blocks, halts).
    """
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        validate_contract(data, ConditionalRegistry, artifact="conditional-registry.yaml", path=path)
        return data
    except ContractError as exc:
        print(f"WARNING: ignoring invalid conditional registry\n{exc}", file=sys.stderr)
        return []
    except Exception:
        return []


def _condition_to_velocity(condition: str) -> str:
    """Convert 'quote.quoteNumber != null' → '$quote.quoteNumber != null'."""
    condition = condition.strip()
    if condition and not condition.startswith("$"):
        condition = "$" + condition
    return condition


def build_cond_map(cond_blocks: list[dict]) -> dict[str, str]:
    """Map '$doc.<key>' → '${data.<key>}' — the plugin owns the conditional logic.

    §1a: keyed by the block's named key (``cond<id>`` for binary blocks, the
    author ``$token`` for variant blocks), so the join key is stable across edits.
    """
    return {
        f"$doc.{block_key(b)}": f"${{data.{block_key(b)}}}"
        for b in cond_blocks
        if b.get("id") is not None or b.get("key")
    }


def apply_cond_substitutions(vm_text: str, cond_map: dict[str, str]) -> str:
    """Replace [[text]]$doc.condN with ${data.condN}; multi-pass for nesting.

    The plugin owns conditional text — it puts the resolved string (or "") into
    renderingData under "condN". The template just outputs ${data.condN}.

    Three phases:
      0. Rewrite #if($doc.condN) guards → #if($data.condN). These come from
         Leg 0's render-template blocks (a [[conditional]] containing a loop):
         the content stays in the template and the plugin puts condN as a
         Boolean, so only the guard token needs renaming.
      1. Resolve [[...]]$doc.condN blocks innermost-first (repeated until stable).
         Bare $doc.condN tokens are left untouched so outer blocks can still match
         on the next pass.
      2. Replace any remaining bare $doc.condN tokens (e.g. inside a cond block's
         source_text that the annotator left un-bracketed).
    """
    # Phase 0: template-rendered conditional guards
    vm_text = re.sub(r"#if\(\$doc\.([A-Za-z_]\w*)\)", r"#if($data.\1)", vm_text)
    # Phase 1: peel [[...]]$doc.<key> from innermost outward
    for _ in range(10):
        new_text = _COND_BLOCK_RE.sub(
            lambda m: f"${{data.{m.group(2)}}}",
            vm_text,
        )
        if new_text == vm_text:
            break
        vm_text = new_text
    # Phase 2: bare $doc.condN tokens not wrapped in [[...]]
    for token, replacement in cond_map.items():
        vm_text = vm_text.replace(token, replacement)
    return vm_text


def _cond_block_spans(vm_text: str) -> list[tuple[int, int, str]]:
    """Spans of [[...]] regions (incl. nested) with their trailing $doc.condN id.

    Returns [(start, end, cond_id_str)]; end includes the ]]$doc.condN suffix.
    cond_id_str is "" when a closing ]] has no $doc.condN annotation.
    """
    spans: list[tuple[int, int, str]] = []
    stack: list[int] = []
    i, n = 0, len(vm_text)
    while i < n - 1:
        two = vm_text[i: i + 2]
        if two == "[[":
            stack.append(i)
            i += 2
        elif two == "]]":
            if stack:
                start = stack.pop()
                m = re.match(r"\$doc\.([A-Za-z_]\w*)", vm_text[i + 2:])
                end = i + 2 + (m.end() if m else 0)
                spans.append((start, end, m.group(1) if m else ""))
            i += 2
        else:
            i += 1
    return spans


def split_delegated(vm_text: str, entries: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split entries whose placeholder occurs ONLY inside [[...]]$doc.condN blocks (D9).

    Those tokens are removed from the template by apply_cond_substitutions — the
    plugin's conditional string carries their value instead, so reporting them as
    template-resolved would be a lie. Each delegated entry gains a `_cond_ids`
    list (innermost containing block per occurrence).
    Returns (template_entries, delegated_entries).
    """
    spans = _cond_block_spans(vm_text)
    kept: list[dict] = []
    delegated: list[dict] = []
    for v in entries:
        ph = v.get("placeholder") or ""
        occs = []
        for m in re.finditer(re.escape(ph), vm_text):
            # Reject prefix matches of a longer token ($TBD_a inside $TBD_ab,
            # $TBD_x.y inside $TBD_x.y.z); a bare trailing dot is sentence punctuation.
            tail = vm_text[m.end(): m.end() + 2]
            if tail[:1].isalnum() or tail[:1] == "_":
                continue
            if tail[:1] == "." and (tail[1:2].isalnum() or tail[1:2] == "_"):
                continue
            occs.append(m)
        if not ph or not occs or not spans:
            kept.append(v)
            continue
        cond_ids: set[str] = set()
        all_inside = True
        for m in occs:
            containing = [s for s in spans if s[0] <= m.start() and m.end() <= s[1]]
            if not containing:
                all_inside = False
                break
            innermost = max(containing, key=lambda s: s[0])
            if innermost[2]:
                cond_ids.add(innermost[2])
        if all_inside:
            delegated.append({**v, "_cond_ids": sorted(cond_ids)})
        else:
            kept.append(v)
    return kept, delegated


def _primary_root_id(suggested: dict) -> str | None:
    """Return the primary rendering root id from a schema 2.0 suggested.yaml, else None."""
    roots = suggested.get("rendering_roots") or []
    for r in roots:
        if r.get("primary"):
            return r.get("id")
    if roots:
        return roots[0].get("id")
    return None


def _flatten_to_primary_root(suggested: dict) -> dict:
    """Normalise schema 2.0 per-root verdicts to flat scalar fields on each entry.

    Uses the primary rendering root (first entry with primary:true, or first overall).
    For schema 1.x files (no rendering_roots), returns the dict unchanged.
    The returned dict shares the input's top-level keys; only variable/loop entries
    are shallow-copied with the verdict fields promoted.
    """
    root_id = _primary_root_id(suggested)
    if not root_id:
        return suggested

    def _promote(entry: dict) -> dict:
        verdict = (entry.get("verdicts") or {}).get(root_id) or {}
        return {
            **entry,
            "data_source": verdict.get("data_source") or entry.get("data_source") or "",
            "confidence": verdict.get("confidence") or entry.get("confidence") or "",
            "reasoning": verdict.get("reasoning") or entry.get("reasoning") or "",
        }

    new_vars = [_promote(v) for v in (suggested.get("variables") or [])]
    new_loops = []
    for loop in (suggested.get("loops") or []):
        new_fields = [_promote(f) for f in (loop.get("fields") or [])]
        new_loops.append({**_promote(loop), "fields": new_fields})

    return {**suggested, "variables": new_vars, "loops": new_loops}


# ---------------------------------------------------------------------------
# Build substitution tables from suggested.yaml
# ---------------------------------------------------------------------------


def build_substitution_map(suggested: dict) -> dict[str, str]:
    """
    {placeholder: data_source} for every variable and loop field.
    Entries with empty data_source map to '' — caller decides what to do.
    Accepts both schema 1.x (flat fields) and 2.0 (per-root verdicts).
    """
    suggested = _flatten_to_primary_root(suggested)
    smap: dict[str, str] = {}
    def _clean_data_source(value: str) -> str:
        ds = (value or "").strip()
        return "" if ds.startswith("UNRESOLVED:") else ds

    def _resolve(entry: dict) -> str:
        """data_source for one entry, made null-safe when the field is optional.

        Occurrence is declared in the source document ({$x} optional). The plugin
        emits a guard only for `required`/`one_or_more`, so an absent OPTIONAL
        scalar reaches the renderer as a bare `$data.x` reference and Socotra's
        strict renderer aborts on the null. Wrapping optional refs as a Velocity
        quiet reference (`$!{...}`) renders empty instead — the template-side
        mirror of the plugin guard. Collections (`zero_or_more`) are driven by
        #foreach and need no scalar guard.
        """
        ds = _clean_data_source(entry.get("data_source") or "")
        occ = (entry.get("occurrence") or "required").strip() or "required"
        return _to_quiet_ref(ds) if (ds and occ == "optional") else ds

    for v in suggested.get("variables") or []:
        ph = v.get("placeholder") or ""
        if ph:
            smap[ph] = _resolve(v)
    for loop in suggested.get("loops") or []:
        ph = loop.get("placeholder") or ""
        if ph:
            smap[ph] = _clean_data_source(loop.get("data_source") or "")
        coverages = loop.get("available_coverages") or []
        for fld in loop.get("fields") or []:
            fph = fld.get("placeholder") or ""
            if not fph:
                continue
            val = _resolve(fld)
            # A field reached THROUGH an optional coverage (e.g.
            # `$item.AccidentalDamage.data.labourCovered`, AccidentalDamage =
            # zero_or_one) navigates a nullable intermediate. A quiet ref
            # (`$!{...}`) doesn't help — the strict renderer aborts the moment it
            # calls `.data` on a null coverage (error 216041). Guard the whole
            # reference on the coverage's presence so absent coverages render empty.
            cov_vel = _optional_coverage_prefix(
                _clean_data_source(fld.get("data_source") or ""), coverages)
            if val and cov_vel:
                val = f"#if({cov_vel}){val}#end"
            smap[fph] = val
    return smap


def _optional_coverage_prefix(ds: str, coverages: list[dict]) -> str | None:
    """If ``ds`` traverses an OPTIONAL coverage (``zero_or_one``/``zero_or_more``,
    i.e. quantifier ``?``/``*``), return that coverage's velocity prefix (the
    nullable intermediate to guard); else None. ``exactly_one`` coverages (``!``)
    are always present and need no guard."""
    for cov in coverages:
        vel = (cov.get("velocity") or "").strip()
        if not vel:
            continue
        card = (cov.get("cardinality") or "").strip()
        quant = (cov.get("quantifier") or "").strip()
        optional = card in {"zero_or_one", "zero_or_more"} or quant in {"?", "*"}
        if optional and (ds == vel or ds.startswith(vel + ".")):
            return vel
    return None


def _to_quiet_ref(ds: str) -> str:
    """Turn a Velocity reference into a quiet (null-safe) one: `$x`/`${x}` -> `$!{x}`.

    Idempotent — an already-quiet `$!...` ref is returned unchanged. Non-reference
    strings (no leading `$`) pass through untouched.
    """
    if ds.startswith("$!"):
        return ds
    if ds.startswith("${") and ds.endswith("}"):
        return "$!{" + ds[2:-1] + "}"
    if ds.startswith("$"):
        return "$!{" + ds[1:] + "}"
    return ds


def build_foreach_map(suggested: dict) -> dict[str, str]:
    """
    {loop_placeholder: foreach_directive} for loops that have both
    a data_source and a foreach directive from Leg 2.
    Accepts both schema 1.x (flat fields) and 2.0 (per-root verdicts).

    The stored ``foreach`` carries the registry-default, unprefixed collection
    (e.g. ``$data.items``), but the loop iterates the list the plugin actually
    populates — the rendering-root object — which the verified per-root
    ``data_source`` names (``$data.quote.items`` / ``$data.segment.items``).
    There is no top-level ``items`` key in renderingData, so emitting the raw
    ``foreach`` makes every loop iterate nothing. Splice ``data_source`` into
    the directive's collection slot so it matches what the plugin exposes.
    """
    suggested = _flatten_to_primary_root(suggested)
    fmap: dict[str, str] = {}
    for loop in suggested.get("loops") or []:
        ph = loop.get("placeholder") or ""
        foreach = loop.get("foreach") or ""
        ds = loop.get("data_source") or ""
        if ph and foreach and ds:
            m = _FOREACH_COLLECTION_RE.search(foreach)
            fmap[ph] = (m.group(1) + ds + m.group(2)) if m else foreach
    return fmap


# Captures a #foreach directive's prefix (`#foreach ($item in `) and its
# closing paren, leaving the collection expression in between for replacement.
_FOREACH_COLLECTION_RE = re.compile(r"(#foreach\s*\(\s*\$?\w+\s+in\s+).+?(\))")


# ---------------------------------------------------------------------------
# Template processor
# ---------------------------------------------------------------------------

# A placeholder path is TBD_<seg>(.<seg>)* — it never ends in a dot. The old
# `[\w.]+` tail greedily swallowed a sentence-ending period (e.g. "...is
# $TBD_quote.data.discountType." captured the trailing "."), so the token no
# longer matched the substitution map and was left unresolved. Anchoring on
# `\w+(?:\.\w+)*` stops at a bare trailing dot (sentence punctuation).
_TBD_TOKEN_RE = re.compile(r"\$(?:\w+\.)?TBD_\w+(?:\.\w+)*")
_GUARD_OPEN_RE = re.compile(r"^\s*#if\(\$TBD_[\w.]+\)\s*$")
_IF_OR_FOREACH_RE = re.compile(r"^\s*#(if|foreach)\b")
_END_RE = re.compile(r"^\s*#end\s*$")
_FOREACH_LINE_RE = re.compile(r"^\s*#foreach\b")
_BRACE_REF_RE = re.compile(r"\{\$([a-zA-Z_][a-zA-Z0-9_.]*)\}")
# Matches [[content]]$doc.condN where content contains no nested brackets.
# Used in multi-pass to resolve innermost conditional blocks first.
_COND_BLOCK_RE = re.compile(r"\[\[([^\[\]]*)\]\]\$doc\.([A-Za-z_]\w*)", re.DOTALL)


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

    result = "".join(out)
    # Normalise {$expr} → ${expr} (invalid Velocity brace notation from source docs)
    result = _BRACE_REF_RE.sub(r"${\1}", result)
    return result


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
        "Review the candidates in the .mapping.yaml, set `data_source` "
        "to the correct one, then re-run Leg 3."
    ),
    "confirm-assumption": (
        "Leg 2 made a fuzzy match — confirm the suggested path is correct "
        "before deploying. Edit `data_source` in the .mapping.yaml if needed, "
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
    delegated_vars: list[dict] | None = None,
    generated_at: str,
    repo_root: Path,
    cond_blocks: list[dict] | None = None,
) -> None:
    delegated_vars = delegated_vars or []
    cond_blocks = cond_blocks or []
    cond_count = len(cond_blocks)
    total_all = (
        len(resolved_vars) + len(unresolved_vars)
        + len(resolved_loops) + len(unresolved_loops)
        + len(delegated_vars)
    )
    resolved_all = len(resolved_vars) + len(resolved_loops)
    unresolved_all = len(unresolved_vars) + len(unresolved_loops)
    delegated_all = len(delegated_vars)

    cond_suffix = f", {cond_count} conditional block(s) applied" if cond_count else ""
    if delegated_all:
        cond_suffix += f", {delegated_all} token(s) delegated to plugin"
    if total_all == 0 and cond_count == 0:
        status = "EMPTY — no placeholders found"
    elif total_all == 0 and cond_count > 0:
        status = f"CONDITIONAL-ONLY — {cond_count} conditional block(s) applied"
    elif unresolved_all == 0:
        status = f"COMPLETE — all {total_all} token(s) {'handled' if delegated_all else 'resolved'}{cond_suffix}"
    elif resolved_all == 0 and delegated_all == 0:
        status = f"BLOCKED — 0 of {total_all} resolved{cond_suffix}"
    else:
        status = f"PARTIAL — {resolved_all} of {total_all} resolved, {unresolved_all} need attention{cond_suffix}"

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
        f"| **Generated** | {generated_at} |",
        "",
        "---",
        "",
    ]

    # ---- §0 Conditional blocks -----------------------------------------------
    if cond_count > 0:
        lines += [f"## Conditional Blocks Applied ({cond_count})", ""]
        lines += [
            "| # | Token | Condition | Source text preview |",
            "|---|---|---|---|",
        ]
        for blk in cond_blocks:
            bid = blk.get("id", "?")
            key = block_key(blk)
            conds = blk.get("conditions") or []
            if blk.get("variant"):
                cond_expr = f"{len(blk.get('variants') or [])} variants + default"
            else:
                vel_conds = [_condition_to_velocity(c) for c in conds]
                joiner = " && " if blk.get("operator", "AND") == "AND" else " || "
                cond_expr = joiner.join(vel_conds)
            preview = (blk.get("source_text") or "")[:60].replace("|", "\\|")
            if len(blk.get("source_text") or "") > 60:
                preview += "…"
            lines.append(f"| {bid} | `$doc.{key}` | `{cond_expr}` | {preview} |")
        lines += ["", "---", ""]

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

    # ---- §1b Delegated to plugin (D9, plan 10) --------------------------------
    if delegated_vars:
        lines += [
            f"## Delegated to plugin ({len(delegated_vars)})",
            "",
            "These tokens occur **only inside `[[...]]` conditional blocks**. The block",
            "text (including these field values) is built by the Leg 4 plugin and emitted",
            "via `${data.condN}` — the tokens are not substituted in this template.",
            "Run Leg 4 to wire them; see the plugin report for their status.",
            "",
            "| Placeholder | Velocity Path | Conditional block(s) |",
            "|---|---|---|",
        ]
        for v in delegated_vars:
            ph = v.get("placeholder") or ""
            ds = v.get("data_source") or ""
            conds = ", ".join(v.get("_cond_ids") or []) or "?"
            lines.append(f"| `{ph}` | `{ds}` | {conds} |")
        lines += ["", "---", ""]

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
            "   - Regenerate the registry: `python3 -m velocity_converter.extract_paths`",
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
# Public functional API (usable without file I/O, for tests and programmatic use)
# ---------------------------------------------------------------------------


def substitute(suggested: dict, vm_text: str) -> str:
    """Apply leg-3 substitution in memory and return the final .vm text."""
    smap = build_substitution_map(suggested)
    foreach_map = build_foreach_map(suggested)
    return process_vm(vm_text, smap, foreach_map)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--suggested", type=Path, required=True,
        help=".mapping.yaml (enriched by Leg 2) or legacy .suggested.yaml",
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
    args = ap.parse_args()

    # --- Resolve paths --------------------------------------------------------
    suggested_path = args.suggested.resolve()
    if not suggested_path.exists():
        print(f"ERROR: suggested file not found: {suggested_path}", file=sys.stderr)
        return 1

    stem = suggested_path.name
    for suffix in (".suggested.yaml", ".mapping.yaml", ".yaml"):
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

    # --- Load ----------------------------------------------------------------
    try:
        load_contract(
            suggested_path, SuggestedDoc, artifact="suggested.yaml",
            expected_versions=("1.0", "2.0"), strip_comment_header=True,
        )
    except ContractError as exc:
        print(exc, file=sys.stderr)
        return 1
    suggested = _flatten_to_primary_root(_load_yaml(suggested_path))
    vm_text = vm_path.read_text(encoding="utf-8")

    # --- Build maps ----------------------------------------------------------
    smap = build_substitution_map(suggested)
    foreach_map = build_foreach_map(suggested)
    cond_registry_path = out_dir / f"{stem}.conditional-registry.yaml"
    cond_blocks = _load_cond_registry(cond_registry_path)
    cond_map = build_cond_map(cond_blocks)

    # --- Process -------------------------------------------------------------
    final_vm = process_vm(vm_text, smap, foreach_map)
    final_vm = apply_cond_substitutions(final_vm, cond_map)

    # --- Categorise entries ---------------------------------------------------
    variables = suggested.get("variables") or []
    loops = suggested.get("loops") or []

    def _is_resolved(entry: dict) -> bool:
        ds = (entry.get("data_source") or "").strip()
        return bool(ds) and not ds.startswith("UNRESOLVED:")

    resolved_vars = [v for v in variables if _is_resolved(v)]
    unresolved_vars = [v for v in variables if not _is_resolved(v)]
    resolved_loops = [L for L in loops if _is_resolved(L)]
    unresolved_loops = [L for L in loops if not _is_resolved(L)]

    # Tokens living only inside [[...]]$doc.condN blocks are wired by the Leg 4
    # plugin, not this template — report them separately (D9, plan 10).
    resolved_vars, delegated_vars = split_delegated(vm_text, resolved_vars)

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
        delegated_vars=delegated_vars,
        generated_at=generated_at,
        repo_root=repo_root,
        cond_blocks=cond_blocks,
    )

    print(f"Wrote {out_vm_path}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
