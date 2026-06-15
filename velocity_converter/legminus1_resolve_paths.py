#!/usr/bin/env python3
"""Leg -1: resolve bare ``{leaf}`` placeholders to full accessor paths.

Business problem: making document authors learn the exact accessor path
(``account.data.firstName``) before Leg 0 is too much. Leg -1 lets them write a
bare leaf (``{firstName}``) and does the registry lookup for them, emitting a
human-validated artifact *before* Leg 0 runs.

Modes::

    # 1. Suggest — doc → editable review + machine map + before/after audit
    python3 -m velocity_converter.legminus1_resolve_paths \
        --input <doc.docx|.pdf|.html> --registry registry/path-registry.yaml \
        --output-dir samples/output

    # 2. Apply — read the human-corrected review → final map + resolved doc
    python3 -m velocity_converter.legminus1_resolve_paths \
        --parse-path-review samples/output/<stem>/<stem>.path-review.md \
        --output-dir samples/output/<stem>

Outputs (under ``<output-dir>/<stem>/``):
    <stem>.path-review.md    — editable: one block per leaf, edit the Final line
    <stem>.path-map.yaml     — machine map (leaf → chosen accessor) for Leg 0
    <stem>.path-changes.md   — before/after audit, one row per field
    <stem>.resolved.<ext>    — (apply mode) doc copy with full accessors baked in

Matching is **registry-only** — no compiled SDK is consulted, so a "resolved"
leaf is registry-matched, not JAR-verified. Leg 2 still verifies paths against
the rendering root downstream.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

import yaml

from velocity_converter.leg0_ingest import (
    _FIELD_RE,
    _LOOP_MARKER_RE,
    convert_docx,
    convert_pdf,
)
from velocity_converter.models import OCCURRENCE_SYMBOLS
from velocity_converter.registry_match import (
    build_candidate_index,
    match_leaf,
    parse_rendering_roots,
    suggest_loop_root,
)

_INPUT_COMMENT_RE = re.compile(r"<!--\s*legminus1 input:\s*(.+?)\s*-->")
_SOURCE_COMMENT_RE = re.compile(r"<!--\s*legminus1 source:\s*(.+?)\s*-->")
_LEAF_RE = re.compile(r"\{[$+*]?([A-Za-z_][\w.]*)\}")
_FINAL_RE = re.compile(r"(?m)^Final:\s*(.*)$")
_SCOPE_RE = re.compile(r"(?m)^-\s*Scope:\s*(.*)$")


# ---------------------------------------------------------------------------
# Input → plain text
# ---------------------------------------------------------------------------

def _doc_to_text(input_path: Path) -> str:
    """Convert a .docx/.pdf/.html(.htm) document to plain text for scanning."""
    suffix = input_path.suffix.lower()
    if suffix == ".docx":
        html = convert_docx(input_path)
    elif suffix == ".pdf":
        html = convert_pdf(input_path)
    elif suffix in (".html", ".htm"):
        html = input_path.read_text(encoding="utf-8")
    else:
        raise ValueError(f"unsupported format '{suffix}'. Accepted: .docx, .pdf, .html")
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser").get_text()
    except ImportError:
        return re.sub(r"<[^>]+>", " ", html)


# ---------------------------------------------------------------------------
# Loop membership (mirrors leg0's [Name]...[/Name] marker pairing)
# ---------------------------------------------------------------------------

def _loop_spans(text: str) -> list[tuple[int, int, str]]:
    """Return (inner_start, inner_end, name) for each matched [Name]...[/Name]."""
    pending: dict[str, int] = {}
    spans: list[tuple[int, int, str]] = []
    for m in _LOOP_MARKER_RE.finditer(text):
        name = m.group(2)
        if m.group(1) != "/":
            pending[name] = m.end()
        elif name in pending:
            spans.append((pending.pop(name), m.start(), name))
    return spans


def _loop_for_position(pos: int, spans: list[tuple[int, int, str]]) -> str | None:
    for start, end, name in spans:
        if start <= pos < end:
            return name
    return None


def collect_placeholders(text: str) -> list[dict]:
    """Extract unique ``{leaf}`` tokens with occurrence + loop membership.

    A leaf is treated as a loop field only when *every* occurrence sits inside
    the same loop (mirrors Leg 0's loop-field classification); otherwise it is
    document-level.
    """
    spans = _loop_spans(text)
    order: list[str] = []
    occ: dict[str, str] = {}
    loops_seen: dict[str, set] = {}
    for m in _FIELD_RE.finditer(text):
        symbol, name = m.group(1), m.group(2)
        if name not in occ:
            occ[name] = OCCURRENCE_SYMBOLS[symbol]
            order.append(name)
        loops_seen.setdefault(name, set()).add(_loop_for_position(m.start(), spans))

    fields: list[dict] = []
    for name in order:
        seen = loops_seen[name]
        # All occurrences inside one and the same loop → loop field.
        loop = next(iter(seen)) if len(seen) == 1 else None
        fields.append({"leaf": name, "occurrence": occ[name], "loop": loop})
    return fields


# ---------------------------------------------------------------------------
# Suggest mode
# ---------------------------------------------------------------------------

def resolve_fields(fields: list[dict], reg: dict, roots: list[str]) -> list[dict]:
    """Match each placeholder against the registry, attaching the verdict."""
    candidates = build_candidate_index(reg, roots=roots)
    iterables = {str(i.get("name") or "").lower() for i in reg.get("iterables") or []}
    results: list[dict] = []
    for f in fields:
        loop = f["loop"]
        warn = ""
        if loop and loop.lower() not in iterables:
            warn = f"loop `{loop}` is not a registry iterable — treating leaf as document-level"
            loop = None
        verdict = match_leaf(f["leaf"], loop, candidates)
        results.append({**f, "loop": loop, "warn": warn, **verdict})
    return results


def _scope_label(loop: str | None) -> str:
    return f"loop: {loop}" if loop else "document-level"


def write_path_review(results: list[dict], stem: str, source: str,
                      input_path: Path, roots: list[str], out: Path) -> None:
    roots_str = ", ".join(roots) if roots else "(none declared in filename)"
    lines = [
        f"# Path Review — {stem}",
        "",
        f"<!-- legminus1 input: {input_path.resolve()} -->",
        f"<!-- legminus1 source: {source} -->",
        "",
        "The author wrote bare `{leaf}` tokens. Each was matched against the path "
        "registry below. **Edit the `Final:` line** to the accessor you want "
        "(leave a resolved one as-is), then re-run:",
        "",
        f"    python3 -m velocity_converter.legminus1_resolve_paths \\",
        f"        --parse-path-review {out.name} --output-dir {out.parent}",
        "",
        f"- Rendering root(s): {roots_str}",
        "- Accessors are **registry-matched only** — NOT verified against the "
        "compiled SDK (Leg 2 does that downstream).",
        "- Run `python3 -m velocity_converter.list_paths` to browse every accessor.",
        "",
    ]
    for r in results:
        lines += ["---", "", f"## Field: {{{r['leaf']}}}", ""]
        lines.append(f"- Scope: {_scope_label(r['loop'])}")
        lines.append(f"- Occurrence: {r['occurrence']}")
        if r["status"] == "resolved":
            lines.append(f"- Status: resolved ({r['match']})")
            lines.append(f"- Suggested: {r['chosen']}")
        elif r["status"] == "ambiguous":
            lines.append("- Status: AMBIGUOUS — pick one and put it on the Final line")
        else:
            lines.append("- Status: NO MATCH in registry — supply an accessor or fix the token")
        if r.get("scope_note"):
            lines.append(f"- Note: {r['scope_note']}")
        if r.get("warn"):
            lines.append(f"- Warning: {r['warn']}")
        if r["alternatives"]:
            lines.append("- Alternatives:")
            for a in r["alternatives"]:
                extra = ""
                if a.get("options"):
                    extra = f" — allowed: {', '.join(str(o) for o in a['options'][:6])}"
                if a.get("source") == "datafetcher":
                    extra += " — DataFetcher-sourced"
                lines.append(f"  - {a['accessor']} — {a['why']}{extra}")
        lines.append(f"Final: {r['chosen']}")
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def _datafetcher_for(accessor: str, results_alts: list[dict]) -> dict | None:
    for a in results_alts:
        if a["accessor"] == accessor and a.get("source") == "datafetcher":
            return a.get("datafetcher")
    return None


def write_path_map(results: list[dict], stem: str, source: str, input_path: Path,
                   roots: list[str], out: Path) -> None:
    fields = []
    for r in results:
        entry = {
            "leaf": r["leaf"],
            "occurrence": r["occurrence"],
            "scope": _scope_label(r["loop"]),
            "chosen": r["chosen"],
            "status": r["status"],
            "match": r["match"],
        }
        df = _datafetcher_for(r["chosen"], r["alternatives"]) if r["chosen"] else None
        if df:
            entry["datafetcher"] = df
        fields.append(entry)
    data = {
        "schema_version": "1.0",
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "source": source,
        "input_path": str(input_path.resolve()),
        "rendering_roots": roots,
        "fields": fields,
    }
    out.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True),
                   encoding="utf-8")


def write_path_changes(results: list[dict], stem: str, out: Path,
                        chosen_by: dict[str, str] | None = None) -> None:
    """Before/after audit. ``chosen_by`` maps leaf → 'legMinus1 (suggested)' |
    'human (override)' | 'human (selection)'; defaults to suggested/needs-human."""
    lines = [
        f"# Path Changes — {stem}",
        "",
        "Before/after record of every `{leaf}` the author wrote and the full "
        "accessor it resolved to. This is the traceability anchor — the original "
        "document is never modified.",
        "",
        "| Field (before) | Accessor (after) | Scope | Basis | Decided by |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        after = r["chosen"] or "— (unresolved)"
        if r["status"] == "resolved":
            basis = "human-chosen" if r["match"] == "human" else f"{r['match']} match"
        elif r["status"] == "ambiguous":
            basis = f"{len(r['alternatives'])} candidates"
        else:
            basis = "no registry match"
        if chosen_by is not None:
            decided = chosen_by.get(r["leaf"], "—")
        else:
            decided = "legMinus1 (suggested)" if r["status"] == "resolved" else "needs human"
        lines.append(
            f"| `{{{r['leaf']}}}` | `{after}` | {_scope_label(r['loop'])} | {basis} | {decided} |"
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_suggest(input_path: Path, registry_path: Path, output_dir: Path) -> int:
    text = _doc_to_text(input_path)
    source = input_path.name
    roots, root_err = parse_rendering_roots(source)
    if root_err:
        print(f"WARNING: {root_err}", file=sys.stderr)
    reg = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}

    fields = collect_placeholders(text)
    if not fields:
        print("No {leaf} placeholders found in the document.", file=sys.stderr)
        return 1
    results = resolve_fields(fields, reg, roots)

    stem = input_path.stem
    out_dir = output_dir / stem
    out_dir.mkdir(parents=True, exist_ok=True)
    review = out_dir / f"{stem}.path-review.md"
    pmap = out_dir / f"{stem}.path-map.yaml"
    changes = out_dir / f"{stem}.path-changes.md"

    write_path_review(results, stem, source, input_path, roots, review)
    write_path_map(results, stem, source, input_path, roots, pmap)
    write_path_changes(results, stem, changes)

    n_res = sum(1 for r in results if r["status"] == "resolved")
    n_amb = sum(1 for r in results if r["status"] == "ambiguous")
    n_none = sum(1 for r in results if r["status"] == "unmatched")
    for p in (review, pmap, changes):
        print(f"Wrote {p}")
    print(f"\n{len(results)} field(s): {n_res} resolved, {n_amb} ambiguous, {n_none} unmatched.")
    if n_amb or n_none:
        print(f"Edit the Final lines in {review.name}, then re-run with --parse-path-review.")
    return 0


# ---------------------------------------------------------------------------
# Apply mode (--parse-path-review)
# ---------------------------------------------------------------------------

def parse_path_review(md_path: Path) -> tuple[list[dict], Path | None, str]:
    """Parse a (possibly human-edited) review → (entries, input_path, source).

    Each entry: {leaf, scope, chosen}. ``chosen`` is the Final-line value. The
    file is split on ``## Field:`` headers so each block is parsed in isolation.
    """
    text = md_path.read_text(encoding="utf-8")
    im = _INPUT_COMMENT_RE.search(text)
    sm = _SOURCE_COMMENT_RE.search(text)
    input_path = Path(im.group(1)) if im else None
    source = sm.group(1) if sm else md_path.stem.replace(".path-review", "")
    entries: list[dict] = []
    for block in re.split(r"(?m)^##\s+Field:\s*", text)[1:]:
        lm = _LEAF_RE.match(block.strip())
        if not lm:
            continue
        fm = _FINAL_RE.search(block)
        scm = _SCOPE_RE.search(block)
        entries.append({
            "leaf": lm.group(1),
            "scope": (scm.group(1).strip() if scm else ""),
            "chosen": (fm.group(1).strip() if fm else ""),
        })
    return entries, input_path, source


def _sub_text(text: str, mapping: dict[str, str], replaced: set | None = None) -> str:
    """Rewrite ``{leaf}`` → ``{accessor}`` preserving any occurrence symbol."""
    def repl(m: re.Match) -> str:
        symbol, name = m.group(1), m.group(2)
        if name in mapping and mapping[name]:
            if replaced is not None:
                replaced.add(name)
            return "{" + symbol + mapping[name] + "}"
        return m.group(0)
    return _FIELD_RE.sub(repl, text)


def _rewrite_docx(src: Path, dst: Path, mapping: dict[str, str]) -> set:
    from docx import Document
    doc = Document(str(src))
    replaced: set = set()

    def fix_paragraph(p) -> None:
        for run in p.runs:
            new = _sub_text(run.text, mapping, replaced)
            if new != run.text:
                run.text = new
        joined = "".join(r.text for r in p.runs)
        # Placeholder split across runs → flatten into the first run.
        if any(n in mapping and mapping[n] for _, n in _FIELD_RE.findall(joined)):
            new = _sub_text(joined, mapping, replaced)
            if new != joined and p.runs:
                p.runs[0].text = new
                for r in p.runs[1:]:
                    r.text = ""

    def walk_tables(tables) -> None:
        for t in tables:
            for row in t.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        fix_paragraph(p)
                    walk_tables(cell.tables)

    for p in doc.paragraphs:
        fix_paragraph(p)
    walk_tables(doc.tables)
    doc.save(str(dst))
    return replaced


def write_resolved_doc(input_path: Path, mapping: dict[str, str],
                       out_dir: Path, stem: str) -> tuple[Path | None, list[str]]:
    """Write a resolved copy of the source with full accessors baked in.

    Returns (path, missed_leaves). PDF input cannot be rewritten cleanly, so a
    resolved HTML is emitted instead with a warning.
    """
    suffix = input_path.suffix.lower()
    wanted = {leaf for leaf, acc in mapping.items() if acc}
    if suffix == ".docx":
        dst = out_dir / f"{stem}.resolved.docx"
        replaced = _rewrite_docx(input_path, dst, mapping)
        return dst, sorted(wanted - replaced)
    if suffix in (".html", ".htm"):
        dst = out_dir / f"{stem}.resolved{suffix}"
        original = input_path.read_text(encoding="utf-8")
        replaced: set = set()
        dst.write_text(_sub_text(original, mapping, replaced), encoding="utf-8")
        return dst, sorted(wanted - replaced)
    if suffix == ".pdf":
        dst = out_dir / f"{stem}.resolved.html"
        replaced: set = set()
        html = convert_pdf(input_path)
        dst.write_text(_sub_text(html, mapping, replaced), encoding="utf-8")
        print("WARNING: PDF input cannot be rewritten in place — wrote resolved HTML "
              f"({dst.name}) instead of a resolved PDF.", file=sys.stderr)
        return dst, sorted(wanted - replaced)
    return None, sorted(wanted)


def _scope_to_loop(scope: str) -> str | None:
    return scope.split(":", 1)[1].strip() if scope.startswith("loop:") else None


def run_apply(review_path: Path, output_dir: Path | None) -> int:
    entries, input_path, source = parse_path_review(review_path)
    out_dir = output_dir or review_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = source.rsplit(".", 1)[0] if "." in source else source

    final_by_leaf = {e["leaf"]: e["chosen"] for e in entries}
    scope_by_leaf = {e["leaf"]: e["scope"] for e in entries}

    # The suggest-mode path-map carries the structured state (scope, occurrence,
    # original suggestion, status) — read it so the audit can show suggested-vs-
    # override provenance instead of flattening everything to "human".
    prior = out_dir / f"{stem}.path-map.yaml"
    prior_fields: list[dict] = []
    roots: list[str] = []
    if prior.exists():
        prior_data = yaml.safe_load(prior.read_text(encoding="utf-8")) or {}
        prior_fields = prior_data.get("fields") or []
        roots = prior_data.get("rendering_roots") or []
        if input_path is None and prior_data.get("input_path"):
            input_path = Path(prior_data["input_path"])
    prior_by_leaf = {f["leaf"]: f for f in prior_fields}

    # Iterate the prior field order if available, else the review order.
    leaves = [f["leaf"] for f in prior_fields] or list(final_by_leaf)

    results: list[dict] = []
    decided: dict[str, str] = {}
    for leaf in leaves:
        orig = prior_by_leaf.get(leaf, {})
        final = final_by_leaf.get(leaf, orig.get("chosen", ""))
        scope = scope_by_leaf.get(leaf) or orig.get("scope", "document-level")
        loop = _scope_to_loop(scope)
        orig_status = orig.get("status", "")
        orig_chosen = orig.get("chosen", "")
        if not final:
            decided[leaf] = "needs human"
            match = ""
        elif orig_status == "resolved" and final == orig_chosen:
            decided[leaf] = "legMinus1 (suggested)"
            match = orig.get("match", "exact")
        elif orig_status == "resolved" and final != orig_chosen:
            decided[leaf] = "human (override)"
            match = "human"
        else:  # ambiguous / unmatched originally → human picked/supplied
            decided[leaf] = "human (selection)"
            match = "human"
        results.append({
            "leaf": leaf, "occurrence": orig.get("occurrence", "required"),
            "loop": loop, "chosen": final,
            "status": "resolved" if final else "unmatched",
            "match": match, "alternatives": [], "scope_note": "", "warn": "",
        })

    mapping = {r["leaf"]: r["chosen"] for r in results}
    unresolved = [r["leaf"] for r in results if not r["chosen"]]

    pmap = out_dir / f"{stem}.path-map.yaml"
    changes = out_dir / f"{stem}.path-changes.md"
    write_path_map(results, stem, source, input_path or Path(source), roots, pmap)
    write_path_changes(results, stem, changes, chosen_by=decided)
    print(f"Wrote {pmap}")
    print(f"Wrote {changes}")

    if unresolved:
        print(f"WARNING: {len(unresolved)} field(s) still have an empty Final line: "
              f"{', '.join(unresolved)} — they will be left as-is for Leg 0.",
              file=sys.stderr)

    if input_path and input_path.exists():
        resolved, missed = write_resolved_doc(input_path, mapping, out_dir, stem)
        if resolved:
            print(f"Wrote {resolved}")
        if missed:
            print(f"WARNING: {len(missed)} placeholder(s) not found in the source "
                  f"document (not substituted): {', '.join(missed)}", file=sys.stderr)
    else:
        print("Note: original document not found — wrote map + audit only "
              "(leg0 can still consume the path-map).", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _find_registry(start: Path) -> Path | None:
    cur = start.resolve()
    for _ in range(8):
        for rel in ("registry/path-registry.yaml", "path-registry.yaml"):
            cand = cur / rel
            if cand.is_file():
                return cand
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Leg -1: resolve bare {leaf} placeholders to full accessor paths."
    )
    parser.add_argument("--input", default=None, help="Path to .docx/.pdf/.html document")
    parser.add_argument("--registry", default=None, help="Path to path-registry.yaml")
    parser.add_argument("--output-dir", default=None, help="Output directory")
    parser.add_argument("--parse-path-review", default=None, metavar="REVIEW.md",
                        help="Parse a (human-edited) review → final map + resolved doc")
    args = parser.parse_args()

    if args.parse_path_review:
        review = Path(args.parse_path_review)
        if not review.exists():
            print(f"Error: file not found: {review}", file=sys.stderr)
            return 1
        out_dir = Path(args.output_dir) if args.output_dir else None
        return run_apply(review, out_dir)

    if not args.input:
        print("Error: --input is required (unless using --parse-path-review)", file=sys.stderr)
        return 1
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        return 1

    registry_path = Path(args.registry) if args.registry else _find_registry(input_path.parent)
    if not registry_path or not registry_path.exists():
        print("Error: registry not found — pass --registry registry/path-registry.yaml",
              file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir) if args.output_dir else input_path.parent
    return run_suggest(input_path, registry_path, output_dir)


if __name__ == "__main__":
    sys.exit(main())
