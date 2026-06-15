#!/usr/bin/env python3
"""
Leg 0 — Document Ingestion (PDF / Word → raw HTML) + Field/Conditional Extraction

Converts a customer's source document (PDF or Word) into a rough HTML file
suitable for the existing Leg 1 pipeline, then extracts {field_name} tokens,
[[conditional]] blocks, and [Name]...[/Name] loop sections, annotates them,
and writes all pipeline-ready artifacts. Loop section names must exactly match
a registry iterable name (e.g. [Item] ... [/Item]); fields inside become the
loop's fields in the mapping and the markers become a #foreach scaffold.

Usage:
    python3 -m velocity_converter.leg0_ingest --input <path.docx|path.pdf> [--output-dir <dir>]
    python3 -m velocity_converter.leg0_ingest --parse-conditional-form <filled-form.md> --output-dir <dir>

Outputs (normal mode):
    {stem}.raw.html           — raw converted HTML (pre-annotation)
    {stem}.annotated.html     — HTML with {field} → $TBD_field, [[cond]] → $doc.condN
    {stem}.mapping.yaml       — leg2-compatible mapping (pipeline input; enriched in-place by Leg 2)
    {stem}.conditional-form.md — customer-facing conditional form

Output (--parse-conditional-form mode):
    {stem}.conditional-registry.yaml — parsed conditional registry for Leg 4

Exit codes:
    0  success
    1  any error (file not found, unsupported format, import failure)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

from velocity_converter.models import ConditionalRegistry, MappingDoc, validate_contract
from velocity_converter.workspace import action_needed_file

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _derive_accessor(velocity: str, category: str) -> str:
    """Derive clean accessor from velocity path + category."""
    v = (velocity or "").strip()
    cat = (category or "").strip()
    if cat == "system":
        return "policy." + v[len("$data."):] if v.startswith("$data.") else v
    if cat == "quote_system":
        return "quote." + v[len("$data."):] if v.startswith("$data.") else v
    if cat == "policy_data":
        return "policy." + v[len("$data."):] if v.startswith("$data.") else v
    if v.startswith("$data."):
        return v[len("$data."):]
    if v.startswith("$"):
        return v[1:]
    return v


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


# ---------------------------------------------------------------------------
# Word (.docx) → HTML
# ---------------------------------------------------------------------------

def convert_docx(docx_path: Path) -> str:
    try:
        from docx import Document
    except ImportError:
        sys.exit(
            "Missing dependency python-docx.\n"
            "Install with: pip install python-docx --break-system-packages"
        )

    doc = Document(str(docx_path))
    parts: list[str] = []

    def _paragraph_html(para) -> str | None:
        text = para.text.strip()
        if not text:
            return None
        style_name = (para.style.name or "").lower()
        if "heading 1" in style_name:
            return f"<h1>{_escape(text)}</h1>"
        if "heading 2" in style_name or "heading 3" in style_name:
            return f"<h2>{_escape(text)}</h2>"
        if "heading" in style_name:
            return f"<h2>{_escape(text)}</h2>"
        runs_with_text = [r for r in para.runs if r.text.strip()]
        if runs_with_text and all(r.bold for r in runs_with_text):
            return f"<p><strong>{_escape(text)}</strong></p>"
        return f"<p>{_escape(text)}</p>"

    def _table_html(table) -> str:
        rows = ["<table>"]
        for row in table.rows:
            cells = "".join(
                f"<td>{_escape(cell.text.strip())}</td>" for cell in row.cells
            )
            rows.append(f"  <tr>{cells}</tr>")
        rows.append("</table>")
        return "\n".join(rows)

    from docx.oxml.ns import qn  # noqa: F401,PLC0415

    for child in doc.element.body:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

        if tag == "p":
            from docx.text.paragraph import Paragraph  # noqa: PLC0415
            para = Paragraph(child, doc)
            html = _paragraph_html(para)
            if html:
                parts.append(html)

        elif tag == "tbl":
            from docx.table import Table  # noqa: PLC0415
            table = Table(child, doc)
            parts.append(_table_html(table))

    body_content = "\n".join(parts)
    return f"<html>\n<body>\n{body_content}\n</body>\n</html>\n"


# ---------------------------------------------------------------------------
# PDF → HTML
# ---------------------------------------------------------------------------

def convert_pdf(pdf_path: Path) -> str:
    try:
        import pdfplumber
    except ImportError:
        sys.exit(
            "Missing dependency pdfplumber.\n"
            "Install with: pip install pdfplumber --break-system-packages"
        )

    parts: list[str] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            if page_num > 0:
                parts.append("<!-- page break -->")

            table_bboxes: list[tuple] = []
            try:
                tables = page.extract_tables()
                for table_data in (tables or []):
                    if not table_data:
                        continue
                    rows = ["<table>"]
                    for row in table_data:
                        cells = "".join(
                            f"<td>{_escape((cell or '').strip())}</td>"
                            for cell in (row or [])
                        )
                        rows.append(f"  <tr>{cells}</tr>")
                    rows.append("</table>")
                    parts.append("\n".join(rows))
                for t_obj in (page.find_tables() or []):
                    table_bboxes.append(t_obj.bbox)
            except Exception:
                pass

            try:
                chars = page.chars or []
                if chars:
                    avg_height = sum(c.get("height", 0) for c in chars) / len(chars)
                else:
                    avg_height = 0

                def _in_table(c) -> bool:
                    x0, y0, x1, y1 = c.get("x0", 0), c.get("top", 0), c.get("x1", 0), c.get("bottom", 0)
                    for tx0, ty0, tx1, ty1 in table_bboxes:
                        if x0 >= tx0 and x1 <= tx1 and y0 >= ty0 and y1 <= ty1:
                            return True
                    return False

                text_chars = [c for c in chars if not _in_table(c)]

                lines: dict[float, list] = {}
                for c in text_chars:
                    top = round(c.get("top", 0), 1)
                    lines.setdefault(top, []).append(c)

                for top_pos in sorted(lines):
                    line_chars = sorted(lines[top_pos], key=lambda c: c.get("x0", 0))
                    line_text = "".join(c.get("text", "") for c in line_chars).strip()
                    if not line_text:
                        continue
                    line_avg_h = sum(c.get("height", 0) for c in line_chars) / len(line_chars)
                    if avg_height > 0 and line_avg_h > avg_height * 1.2:
                        parts.append(f"<h2>{_escape(line_text)}</h2>")
                    else:
                        parts.append(f"<p>{_escape(line_text)}</p>")

            except Exception:
                raw = page.extract_text() or ""
                for line in raw.splitlines():
                    line = line.strip()
                    if line:
                        parts.append(f"<p>{_escape(line)}</p>")

    body_content = "\n".join(parts)
    return f"<html>\n<body>\n{body_content}\n</body>\n</html>\n"


# ---------------------------------------------------------------------------
# Field extraction (E-T1)
# ---------------------------------------------------------------------------

# Group 1: optional occurrence symbol ($ optional, + one-or-more, * zero-or-more;
# bare = required). Group 2: field name. See models.OCCURRENCE_SYMBOLS.
_FIELD_RE = re.compile(r"\{([$+*]?)([a-zA-Z_][a-zA-Z0-9_.]*)\}")


def extract_fields(html: str, registry_path=None) -> list[dict]:
    """Extract {field_name} tokens from HTML (on plain text). Deduplicates.

    An occurrence symbol may prefix the name — {$x} optional, {x} required,
    {+x} one or more, {*x} zero or more — and is recorded as a normalized
    ``occurrence`` value on the field. The canonical token never carries the
    symbol ($TBD_x for all four forms). Conflicting symbols for the same name
    keep the first one seen and warn on stderr.

    When registry_path is provided, dotted-path placeholders (e.g. {account.data.firstName})
    are resolved against the registry and their velocity path written into data_source.
    Unresolved dotted names get data_source = "UNRESOLVED:<name>" and a stderr warning.
    """
    from velocity_converter.models import OCCURRENCE_SYMBOLS

    try:
        from bs4 import BeautifulSoup
        text = BeautifulSoup(html, "html.parser").get_text()
    except ImportError:
        text = re.sub(r"<[^>]+>", " ", html)

    seen: dict[str, list[int]] = {}
    occurrences: dict[str, str] = {}
    conflicts: list[str] = []
    for i, m in enumerate(re.finditer(_FIELD_RE, text)):
        symbol, name = m.group(1), m.group(2)
        seen.setdefault(name, []).append(i)
        if name not in occurrences:
            occurrences[name] = OCCURRENCE_SYMBOLS[symbol]
        elif occurrences[name] != OCCURRENCE_SYMBOLS[symbol]:
            conflicts.append(name)

    lookup: dict = {}
    meta_lookup: dict = {}
    if registry_path and any("." in name for name in seen):
        try:
            _scripts = str(Path(__file__).parent)
            if _scripts not in sys.path:
                sys.path.insert(0, _scripts)
            from agent_tools import build_velocity_lookup, build_velocity_meta_lookup  # noqa: PLC0415
            lookup = build_velocity_lookup(registry_path)
            meta_lookup = build_velocity_meta_lookup(registry_path)
        except Exception:
            pass

    unresolved: list[str] = []
    fields: list[dict] = []
    for name in seen:
        candidate = None
        if "." in name and lookup:
            velocity = lookup.get(name)
            if velocity:
                data_source = velocity
                # DataFetcher-sourced paths (e.g. account.data.firstName →
                # getAccount) share their velocity path with a phantom direct
                # row, so the path alone can't drive the fetch. Stamp a
                # candidate block here so Leg 4 wires the DataFetcher call.
                meta = meta_lookup.get(name)
                if meta and meta.get("source") == "datafetcher":
                    candidate = {
                        "path": meta.get("velocity") or velocity,
                        "match_step": "exact",
                        "source": "datafetcher",
                        "datafetcher_method": meta.get("datafetcher_method", ""),
                        "datafetcher_arg": meta.get("datafetcher_arg"),
                        "datafetcher_key": meta.get("datafetcher_key", ""),
                    }
                    if meta.get("valid_roots"):
                        candidate["valid_roots"] = meta["valid_roots"]
            else:
                data_source = f"UNRESOLVED:{name}"
                unresolved.append(name)
        else:
            data_source = ""
        field = {
            "name": name,
            "token": f"$TBD_{name}",
            "data_source": data_source,
            "confidence": "",
            "occurrence": occurrences.get(name, "required"),
        }
        if candidate:
            field["candidate"] = candidate
        fields.append(field)

    if conflicts:
        print(
            "WARNING: conflicting occurrence symbols for: "
            f"{', '.join(sorted(set(conflicts)))} — first symbol seen wins",
            file=sys.stderr,
        )
    if unresolved:
        print(
            f"WARNING: unresolved dotted placeholders: {', '.join(unresolved)}",
            file=sys.stderr,
        )

    return fields


def apply_path_map(html: str, path_map_path: Path) -> str:
    """Rewrite bare ``{leaf}`` → ``{accessor}`` using a Leg -1 path-map.

    The map (``<stem>.path-map.yaml``) is the human-validated leaf→accessor
    resolution from Leg -1. Occurrence symbols are preserved. Leaves with an
    empty/absent ``chosen`` are left untouched. Returns the rewritten HTML.
    """
    try:
        data = yaml.safe_load(path_map_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: could not read path-map {path_map_path}: {exc}", file=sys.stderr)
        return html
    mapping = {
        f["leaf"]: f["chosen"]
        for f in (data.get("fields") or [])
        if f.get("leaf") and f.get("chosen")
    }
    if not mapping:
        return html

    applied: set[str] = set()

    def _repl(m: re.Match) -> str:
        symbol, name = m.group(1), m.group(2)
        if name in mapping:
            applied.add(name)
            return "{" + symbol + mapping[name] + "}"
        return m.group(0)

    result = _FIELD_RE.sub(_repl, html)
    print(f"Applied path-map: rewrote {len(applied)}/{len(mapping)} leaf placeholder(s).")
    return result


def annotate_fields(html: str, fields: list[dict]) -> str:
    """Replace {field_name} → $TBD_field_name in the HTML string.

    Occurrence symbols are accepted and stripped: {$x}, {+x}, {*x} all become
    the same canonical token as {x}.
    """
    tokens = {f["name"]: f["token"] for f in fields}
    return _FIELD_RE.sub(lambda m: tokens.get(m.group(2), m.group(0)), html)


# ---------------------------------------------------------------------------
# Conditional block extraction (E-T2)
# ---------------------------------------------------------------------------

def _find_top_level_brackets(text: str) -> list[tuple[int, int, str]]:
    """Find top-level [[...]] blocks, skipping nested ones.
    Returns list of (start, end, inner_content) tuples.
    Handles cases like [[ outer [[inner]] still outer ]] correctly.
    """
    results = []
    i = 0
    n = len(text)
    while i < n - 1:
        if text[i : i + 2] == "[[":
            depth = 1
            start = i
            i += 2
            while i < n - 1 and depth > 0:
                if text[i : i + 2] == "[[":
                    depth += 1
                    i += 2
                elif text[i : i + 2] == "]]":
                    depth -= 1
                    if depth == 0:
                        results.append((start, i + 2, text[start + 2 : i]))
                    i += 2
                else:
                    i += 1
            if depth > 0:
                i = start + 2  # unclosed — skip
        else:
            i += 1
    return results


# A *variant* block tokenises its content with a single bare $identifier:
# [[$stateClause]] (the 50-state feature). The leading $ + single-token (no
# spaces/punctuation) discriminates it from a binary [[literal text]] block.
_VARIANT_TOKEN_RE = re.compile(r"^\$([A-Za-z_]\w*)$")


def _variant_placeholder(source_text: str) -> str | None:
    """Return the placeholder name if ``source_text`` is a variant token.

    ``[[$stateClause]]`` → ``stateClause``. Content that starts with ``$`` but
    is not a single clean identifier (``$state clause``) warns and is treated as
    a binary literal block (returns None).
    """
    s = (source_text or "").strip()
    m = _VARIANT_TOKEN_RE.match(s)
    if m:
        return m.group(1)
    # Starts like a token attempt (one leading $word) but isn't a clean
    # identifier — warn and fall through to literal-binary treatment.
    if re.match(r"^\$\S", s) and not s.startswith("$TBD_"):
        print(
            f"WARNING: [[{s}]] starts with '$' but is not a single bare "
            "identifier — treated as literal text, not a variant placeholder",
            file=sys.stderr,
        )
    return None


def extract_conditionals(html: str) -> list[dict]:
    """Extract [[conditional text]] blocks including nested ones.

    Nested [[...]] inside a block become child blocks with their own IDs.
    Parent source_text references children via $doc.<key>.
    IDs are pre-order (parent lower than children); list is sorted at return.
    Each block carries top_level=True/False so annotate_conditionals can
    restrict HTML replacement to top-level blocks only.

    §1a named keys: every block carries a string ``key`` — the author ``$token``
    for a variant block (``variant=True``, ``placeholder`` set), else a stable
    auto-name ``cond<id>`` for a binary block. The key is the join key used by
    annotation, Leg 3, and Leg 4 (binary keys stay ``cond<id>`` → byte-identical
    to the old positional behaviour).
    """
    try:
        from bs4 import BeautifulSoup
        text = BeautifulSoup(html, "html.parser").get_text()
    except ImportError:
        text = re.sub(r"<[^>]+>", " ", html)

    blocks: list[dict] = []
    next_id = [1]

    def _make_block(block_id: int, source: str, raw: str, top_level: bool) -> dict:
        ph = _variant_placeholder(source)
        return {
            "id": block_id,
            "key": ph if ph else f"cond{block_id}",
            "placeholder": ph,
            "variant": bool(ph),
            "source_text": source,
            "raw_text": raw,
            "top_level": top_level,
        }

    def _process_children(content: str) -> str:
        nested = _find_top_level_brackets(content)
        if not nested:
            return content.strip()
        result = content
        offset = 0
        for start, end, inner in nested:
            child_id = next_id[0]
            next_id[0] += 1
            child_source = _process_children(inner)
            child = _make_block(child_id, child_source, inner, top_level=False)
            blocks.append(child)
            ref = f"$doc.{child['key']}"
            result = result[: start + offset] + ref + result[end + offset :]
            offset += len(ref) - (end - start)
        return result.strip()

    for _start, _end, content in _find_top_level_brackets(text):
        outer_id = next_id[0]
        next_id[0] += 1
        source = _process_children(content)
        blocks.append(_make_block(outer_id, source, content, top_level=True))

    blocks.sort(key=lambda b: b["id"])
    _dedupe_block_keys(blocks)
    return blocks


def _dedupe_block_keys(blocks: list[dict]) -> None:
    """Enforce unique join keys (§1a). A colliding variant token warns and falls
    back to its positional ``cond<id>`` so the registry never has two blocks
    fighting over one key."""
    seen: dict[str, int] = {}
    for b in blocks:
        key = b["key"]
        if key in seen:
            fallback = f"cond{b['id']}"
            print(
                f"WARNING: duplicate conditional key '{key}' "
                f"(blocks {seen[key]} and {b['id']}) — block {b['id']} falls back to '{fallback}'",
                file=sys.stderr,
            )
            b["key"] = fallback
            b["variant"] = False
            b["placeholder"] = None
            seen[fallback] = b["id"]
        else:
            seen[key] = b["id"]


def annotate_conditionals(html: str, blocks: list[dict]) -> str:
    """Replace [[...]] → [[...]]$doc.<key> for all blocks (top-level and nested).

    Top-level blocks are matched by character position (right-to-left).
    Child blocks are matched by a naive string replace on their raw_text;
    this works as long as the child content contains no HTML tags. Binary blocks
    keep key ``cond<id>`` so their annotation is byte-identical to the previous
    positional behaviour (§1a); variant blocks emit ``$doc.<token>``.
    """
    regions = _find_top_level_brackets(html)
    top_level = [b for b in blocks if b.get("top_level", True)]

    if len(regions) != len(top_level):
        result = html
        for b in top_level:
            original = "[[" + b.get("raw_text", b["source_text"]) + "]]"
            result = result.replace(original, f"{original}$doc.{b['key']}")
    else:
        result = html
        for (start, end, content), b in zip(reversed(regions), reversed(top_level)):
            label = f"[[{content}]]"
            result = result[:start] + f"{label}$doc.{b['key']}" + result[end:]

    # Second pass: annotate nested child blocks within the already-annotated HTML.
    for b in [b for b in blocks if not b.get("top_level", True)]:
        raw = b.get("raw_text", b["source_text"])
        original = f"[[{raw}]]"
        result = result.replace(original, f"{original}$doc.{b['key']}")

    return result


# ---------------------------------------------------------------------------
# Loop section extraction ([Name] ... [/Name])
# ---------------------------------------------------------------------------

# Single-bracket loop markers: [Name] opens a repeating section, [/Name]
# closes it. Lookarounds exclude [[conditional]] double brackets. The name
# must exactly match a registry iterable name (e.g. [Item]) — Leg 2 resolves
# loop roots by exact name only.
_LOOP_MARKER_RE = re.compile(r"(?<!\[)\[(/?)([A-Za-z_]\w*)\](?!\])")

# A directive that ended up as the sole content of a paragraph or a table row
# (other cells empty) collapses to a bare line so Leg 3's line-level #foreach
# replacement applies.
_DIRECTIVE_LINE_CLEANUP = [
    (re.compile(r"^(\s*)<p>(#foreach \([^)]*\)|#end)</p>$", re.M), r"\1\2"),
    (re.compile(r"^(\s*)<tr><td>(#foreach \([^)]*\)|#end)</td>(?:<td></td>)*</tr>$", re.M), r"\1\2"),
]


def _annotated_cond_spans(html: str) -> list[tuple[int, int, int | None]]:
    """Spans of [[...]]$doc.condN regions (incl. nested) in annotated HTML.

    Returns [(start, end, cond_id)]; end includes the ]]$doc.condN suffix.
    cond_id is None when the closing ]] carries no annotation. Mirrors Leg 3's
    _cond_block_spans so both legs agree on block boundaries.
    """
    spans: list[tuple[int, int, int | None]] = []
    stack: list[int] = []
    i, n = 0, len(html)
    while i < n - 1:
        two = html[i : i + 2]
        if two == "[[":
            stack.append(i)
            i += 2
        elif two == "]]":
            if stack:
                start = stack.pop()
                m = re.match(r"\$doc\.cond(\d+)", html[i + 2 :])
                end = i + 2 + (m.end() if m else 0)
                spans.append((start, end, int(m.group(1)) if m else None))
            i += 2
        else:
            i += 1
    return spans


def extract_loops(
    html: str, fields: list[dict], cond_blocks: list[dict] | None = None
) -> tuple[str, list[dict], list[dict]]:
    """Detect [Name]...[/Name] repeating sections in annotated HTML.

    Returns (html, top_level_fields, loops):
      - markers become ``#foreach ($<name> in $TBD_<Name>)`` / ``#end``
        scaffold lines (Leg 2 supplies the real directive, Leg 3 swaps it in);
      - a field whose every occurrence falls inside one section moves from
        the top level into that loop's ``fields`` list;
      - loops is a list of {name, token, iterator, fields} dicts.

    Interaction with [[conditional]] blocks (cond_blocks from
    extract_conditionals, mutated in place):
      - a section fully inside a top-level block flips that block to
        ``render: template`` — the block becomes ``#if($doc.condN)``…``#end``
        in the HTML (content, loop included, stays in the template; the
        plugin supplies condN as a Boolean instead of a rendered string);
      - a section crossing a block boundary, or inside a *nested* block,
        is refused: warning, markers left as literal text;
      - a block fully inside a section is allowed but warned — conditions
        are document-scoped, so it renders identically for every item.

    Unmatched markers warn on stderr and stay as literal text.
    """
    pairs: list[tuple[int, int, int, int, str]] = []
    pending: dict[str, tuple[int, int]] = {}
    for m in _LOOP_MARKER_RE.finditer(html):
        name = m.group(2)
        if m.group(1) != "/":
            if name in pending:
                print(
                    f"WARNING: loop [{name}] reopened before [/{name}] — earlier opener ignored",
                    file=sys.stderr,
                )
            pending[name] = (m.start(), m.end())
        elif name in pending:
            o_start, o_end = pending.pop(name)
            pairs.append((o_start, o_end, m.start(), m.end(), name))
        else:
            print(f"WARNING: [/{name}] closer without opener — left as literal text", file=sys.stderr)
    for name in pending:
        print(f"WARNING: loop [{name}] never closed — left as literal text", file=sys.stderr)
    if not pairs:
        return html, fields, []

    # Classify each pair against conditional block spans.
    cond_spans = _annotated_cond_spans(html)
    blocks_by_id = {b["id"]: b for b in (cond_blocks or [])}
    template_spans: dict[int, tuple[int, int]] = {}  # cond_id -> (start, end)
    kept_pairs: list[tuple[int, int, int, int, str]] = []
    for pair in pairs:
        o_start, o_end, c_start, c_end, name = pair
        overlapping = [s for s in cond_spans if s[0] < c_end and o_start < s[1]]
        containing = [s for s in overlapping if s[0] <= o_start and c_end <= s[1]]
        inside = [s for s in overlapping if o_end <= s[0] and s[1] <= c_start]
        crossing = [s for s in overlapping if s not in containing and s not in inside]
        if crossing:
            print(
                f"WARNING: loop [{name}] crosses a [[conditional]] block boundary — "
                "markers left as literal text; restructure the document",
                file=sys.stderr,
            )
            continue
        if len(containing) > 1:
            print(
                f"WARNING: loop [{name}] sits inside a nested [[conditional]] — only "
                "top-level blocks support loops; markers left as literal text",
                file=sys.stderr,
            )
            continue
        if inside:
            print(
                f"WARNING: [[conditional]] block(s) inside loop [{name}] are document-scoped — "
                "the same text renders for every item",
                file=sys.stderr,
            )
        if containing:
            b_start, b_end, cond_id = containing[0]
            if cond_id is None or cond_id not in blocks_by_id:
                print(
                    f"WARNING: loop [{name}] is inside an unannotated [[conditional]] — "
                    "markers left as literal text",
                    file=sys.stderr,
                )
                continue
            template_spans[cond_id] = (b_start, b_end)
            blocks_by_id[cond_id]["render"] = "template"
        kept_pairs.append(pair)
    pairs = kept_pairs
    if not pairs:
        return html, fields, []

    loop_field_lists: dict[str, list[dict]] = {p[4]: [] for p in pairs}
    top_fields: list[dict] = []
    for f in fields:
        token_re = re.compile(re.escape(f["token"]) + r"(?![\w.])")
        positions = [t.start() for t in token_re.finditer(html)]
        target = None
        for o_start, o_end, c_start, _c_end, name in pairs:
            if positions and all(o_end <= p < c_start for p in positions):
                target = name
                break
        if target is None:
            top_fields.append(f)
        else:
            loop_field_lists[target].append(f)

    # Replace marker spans in reverse offset order so earlier offsets stay valid.
    # Template-rendered blocks unwrap in the same pass: their [[ opener and
    # ]]$doc.condN tail become #if($doc.condN) / #end guard lines (disjoint
    # from the marker spans, which sit strictly inside the block content).
    spans: list[tuple[int, int, str]] = []
    for o_start, o_end, c_start, c_end, name in pairs:
        spans.append((o_start, o_end, f"#foreach (${name.lower()} in $TBD_{name})"))
        spans.append((c_start, c_end, "#end"))
    for cond_id, (b_start, b_end) in template_spans.items():
        tail_len = 2 + len(f"$doc.cond{cond_id}")  # ]]$doc.condN
        spans.append((b_start, b_start + 2, f"#if($doc.cond{cond_id})\n"))
        spans.append((b_end - tail_len, b_end, "\n#end"))
    for start, end, text in sorted(spans, reverse=True):
        html = html[:start] + text + html[end:]
    for pattern, repl in _DIRECTIVE_LINE_CLEANUP:
        html = pattern.sub(repl, html)

    loops = [
        {
            "name": name,
            "token": f"$TBD_{name}",
            "iterator": f"${name.lower()}",
            "fields": loop_field_lists[name],
        }
        for _os, _oe, _cs, _ce, name in pairs
    ]
    return html, top_fields, loops


def _normalise_for_leg2(fields: list[dict], source_name: str, loops: list[dict] | None = None) -> dict:
    """Convert fields list to a leg2-compatible .mapping.yaml dict (uses placeholder)."""
    import datetime as dt

    def _variable(f: dict, loop_name: str | None = None) -> dict:
        context: dict = {
            "parent_tag": "p",
            "line": None,
            "nearest_label": "",
        }
        if loop_name:
            context["loop"] = loop_name
        var = {
            "name": f["name"],
            "placeholder": f["token"],
            "type": "loop_field" if loop_name else "variable",
            "context": context,
            "data_source": f.get("data_source", ""),
            "occurrence": f.get("occurrence", "required"),
        }
        if f.get("candidate"):
            var["candidate"] = f["candidate"]
        return var

    loop_entries = [
        {
            "name": loop["name"],
            "placeholder": loop["token"],
            "type": "loop",
            "iterator": loop["iterator"],
            "detection": "marker",
            "context": {},
            "data_source": "",
            "fields": [_variable(f, loop_name=loop["name"]) for f in loop["fields"]],
        }
        for loop in (loops or [])
    ]
    return {
        "schema_version": "1.0",
        "source": source_name,
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "variables": [_variable(f) for f in fields],
        "loops": loop_entries,
    }


def write_leg2_mapping(
    fields: list[dict], source_name: str, output_path: Path, loops: list[dict] | None = None
) -> None:
    """Write {stem}.mapping.yaml — leg2-compatible format with placeholder field."""
    data = _normalise_for_leg2(fields, source_name, loops=loops)
    validate_contract(data, MappingDoc, artifact="mapping.yaml", path=output_path)
    output_path.write_text(
        yaml.dump(data, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Write conditional form (E-T4)
# ---------------------------------------------------------------------------

_TBD_DISPLAY_RE = re.compile(r"\$TBD_([A-Za-z_][\w.]*)")


def _tbd_to_braces(text: str) -> str:
    """Display conversion: $TBD_name → {name} (customer-facing form only).

    Trailing dots are sentence punctuation, not part of the field name —
    `$TBD_amount.` becomes `{amount}.`, not `{amount.}`.
    """
    def _repl(m: re.Match) -> str:
        name = m.group(1)
        stripped = name.rstrip(".")
        return "{" + stripped + "}" + name[len(stripped):]
    return _TBD_DISPLAY_RE.sub(_repl, text)


def _braces_to_tbd(text: str) -> str:
    """Inverse of _tbd_to_braces: {name} → $TBD_name (canonical machine form).

    No-op on text already in $TBD_ form, so forms written before the {field}
    display change still parse. Occurrence symbols ({$x}, {+x}, {*x}) are
    accepted and dropped — the canonical token never carries them.
    """
    return _FIELD_RE.sub(lambda m: "$TBD_" + m.group(2), text)


def write_conditional_form(blocks: list[dict], stem: str, output_path: Path) -> None:
    """Write {stem}.conditional-form.md — customer-facing conditional form."""
    lines = [
        f"# Conditional Text Review — {stem}",
        "",
        "For each block below, fill in the condition that controls when this text appears.",
        "Use accessor path format — dot notation without `$` or `()` syntax:",
        "",
        "| Root | Example accessor | Meaning |",
        "|------|-----------------|---------|",
        "| `quote` | `quote.quoteNumber` | Quote-level system fields |",
        "| `quote` | `quote.data.coolingOffPeriod` | Quote custom fields |",
        "| `account` | `account.data.firstName` | Policyholder fields |",
        "| `policy` | `policy.data.riderType` | Custom policy fields |",
        "| `item` | `item.data.vin` | Per-exposure fields (within a loop) |",
        "",
        "Comparison examples: `quote.quoteNumber != null` · `quote.data.coolingOffPeriod != null` · `account.data.state == \"CA\"`",
        "",
        "Run `python3 -m velocity_converter.list_paths` to see all available accessors.",
        "Return this file to your implementation contact when complete.",
        "",
    ]
    has_variants = any(b.get("variant") for b in blocks)
    if has_variants:
        lines += [
            f"> **Variant blocks** (e.g. `[[$token]]`) are filled in the companion "
            f"`{stem}.variants.csv`, not here — one row per condition + a default row. "
            f"This form only carries the binary (present/absent) blocks below.",
            "",
        ]
    for b in blocks:
        lines += [
            "---",
            "",
            f"## Block {b['id']}",
            "",
            f"> {_tbd_to_braces(b['source_text'])}",
            "",
        ]
        if b.get("variant"):
            lines += [
                f"Variant placeholder: `${b['placeholder']}` — fill "
                f"`{stem}.variants.csv` (one row per condition, plus a default row). "
                "No `Condition:` line needed here.",
                "",
            ]
            continue
        if b.get("render") == "template":
            lines += [
                "Rendering: template (contains a repeating section — the text stays in "
                "the template and the condition switches it on/off as a whole)",
                "",
            ]
        lines += [
            "Condition: ",
            "",
        ]
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_variants_csv_stub(blocks: list[dict], stem: str, output_path: Path) -> None:
    """Write ``{stem}.variants.csv`` — a pre-filled stub for the variant blocks.

    One example conditioned row + one default row per ``$token`` the document
    declared, under a commented instructions header. The customer fills it in
    Excel ("Save As → CSV UTF-8") and returns it; Phase 3's parse step picks up
    the sibling CSV automatically. Does nothing if there are no variant blocks.
    """
    variant_blocks = [b for b in blocks if b.get("variant")]
    if not variant_blocks:
        return
    lines = [
        "# Variant text — one row per condition, plus a default row, per placeholder.",
        "#   placeholder : the $token from the document (pre-filled — do not rename).",
        "#   when        : a condition, e.g.  state == \"CA\"   ·   premium > 500",
        "#                 (first matching row wins — drag rows to reorder priority).",
        "#                 leave blank (or write * / else) for the DEFAULT row used",
        "#                 when nothing else matches — exactly one per placeholder.",
        "#   text        : the variant text (may contain {field} placeholders).",
        "placeholder,when,text",
    ]
    for b in variant_blocks:
        ph = b["placeholder"]
        lines += [
            f'{ph},"state == ""CA""","Example text for California — edit me."',
            f'{ph},,"Default text used when no condition matches — edit me."',
        ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Parse filled conditional form → conditional-registry.yaml (E-T5)
# ---------------------------------------------------------------------------

# A variant pointer block in the form carries "Variant placeholder: `$token`"
# instead of a Condition: line (its rows live in the sibling .variants.csv).
_VARIANT_FORM_RE = re.compile(
    r"##\s+Block\s+(\d+)\s*\n+>\s+(.+?)\s*\n+Variant placeholder:\s*`\$([A-Za-z_]\w*)`",
    re.DOTALL,
)


def parse_conditional_form(
    md_path: Path,
    *,
    variants_csv: Path | None = None,
    registry: dict | None = None,
    classpath: str | None = None,
    product: str | None = None,
) -> list[dict]:
    """Parse a customer-filled conditional form. Returns list of block dicts.

    Binary and template blocks parse from their ``Condition:`` line as before.
    Variant blocks (``Variant placeholder: `$token```) carry no condition here —
    their rows come from the sibling ``<stem>.variants.csv`` (or ``variants_csv``
    override), normalised via :func:`condition_dsl.parse_variants_csv` and merged
    in by placeholder. Any CSV/DSL validation error raises :class:`ValueError`
    so the caller never writes a half-valid registry (§1a / Phase 3).
    """
    from velocity_converter.condition_dsl import parse_variants_csv  # noqa: PLC0415

    text = md_path.read_text(encoding="utf-8")
    blocks = []

    block_re = re.compile(
        r"##\s+Block\s+(\d+)\s*\n+>\s+(.+?)\s*\n+(Rendering:\s*template[^\n]*\n+)?Condition:\s*([^\n]*)",
        re.DOTALL,
    )
    for m in block_re.finditer(text):
        block_id = int(m.group(1))
        source_text = _braces_to_tbd(m.group(2).strip())
        raw_condition = m.group(4).strip()
        # Take only the first line of the condition (customer may add notes below)
        condition_line = raw_condition.splitlines()[0].strip() if raw_condition else ""
        conditions = [condition_line] if condition_line else []
        block = {
            "id": block_id,
            "source_text": source_text,
            "conditions": conditions,
            "operator": "AND",
        }
        if m.group(3):
            block["render"] = "template"
        blocks.append(block)

    # Variant pointer blocks (no Condition: line — filled via the CSV).
    variant_blocks: dict[str, dict] = {}
    for m in _VARIANT_FORM_RE.finditer(text):
        block_id = int(m.group(1))
        placeholder = m.group(3)
        block = {
            "id": block_id,
            "key": placeholder,
            "placeholder": placeholder,
            "variant": True,
            "source_text": _braces_to_tbd(m.group(2).strip()),
        }
        blocks.append(block)
        variant_blocks[placeholder] = block

    blocks.sort(key=lambda b: b["id"])

    # Merge the sibling variants.csv into the variant blocks.
    csv_path = variants_csv
    if csv_path is None:
        stem = md_path.name
        if stem.endswith(".conditional-form.md"):
            stem = stem[: -len(".conditional-form.md")]
        sibling = md_path.parent / f"{stem}.variants.csv"
        if sibling.is_file():
            csv_path = sibling

    if variant_blocks and csv_path is None:
        raise ValueError(
            f"the form declares variant block(s) {sorted(variant_blocks)} but no "
            f"variants CSV was found next to {md_path.name} — provide --variants-csv"
        )

    if csv_path is not None:
        result = parse_variants_csv(csv_path, registry, classpath=classpath, product=product)
        errors = list(result.errors)
        for ph, data in result.placeholders.items():
            b = variant_blocks.get(ph)
            if b is None:
                errors.append(
                    f"variants CSV placeholder '{ph}' has no matching [[${ph}]] block in the form"
                )
                continue
            b["variants"] = data["variants"]
            b["default"] = data["default"]
            b["scope"] = data["scope"]
        for ph, b in variant_blocks.items():
            if ph not in result.placeholders:
                errors.append(f"variant block [[${ph}]] has no rows in the variants CSV")
        if errors:
            raise ValueError(
                "variant CSV validation failed (registry NOT written):\n  - "
                + "\n  - ".join(errors)
            )

    return blocks


def write_conditional_registry(blocks: list[dict], output_path: Path) -> None:
    """Write {stem}.conditional-registry.yaml for Leg 4."""
    validate_contract(
        blocks, ConditionalRegistry, artifact="conditional-registry.yaml", path=output_path
    )
    output_path.write_text(
        yaml.dump(blocks, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Output writer
# ---------------------------------------------------------------------------

def write_output(html: str, input_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{input_path.stem}.raw.html"
    output_path.write_text(html, encoding="utf-8")
    print(f"Wrote {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _discover_registry(start: Path) -> Path | None:
    """Walk up from ``start`` looking for a path-registry.yaml (shared by the
    convert and parse-conditional-form modes)."""
    cur = start.resolve()
    for _ in range(8):
        for rel in ("registry/path-registry.yaml", "path-registry.yaml"):
            candidate = cur / rel
            if candidate.is_file():
                return candidate
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Leg 0: convert PDF/Word to raw HTML and extract fields/conditionals."
    )
    parser.add_argument("--input", default=None, help="Path to .docx or .pdf file")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: input's parent)")
    parser.add_argument(
        "--path-map",
        default=None,
        metavar="PATH_MAP.yaml",
        help="Apply a Leg -1 path-map (bare {leaf} → full accessor) before extraction",
    )
    parser.add_argument(
        "--parse-conditional-form",
        default=None,
        metavar="FILLED_FORM.md",
        help="Parse a filled-in conditional form → conditional-registry.yaml",
    )
    parser.add_argument(
        "--variants-csv",
        default=None,
        metavar="VARIANTS.csv",
        help="Override the variants CSV location (default: sibling <stem>.variants.csv)",
    )
    args = parser.parse_args()

    # --- Mode: parse filled conditional form ---
    if args.parse_conditional_form:
        form_path = Path(args.parse_conditional_form)
        if not form_path.exists():
            print(f"Error: file not found: {form_path}", file=sys.stderr)
            return 1
        output_dir = Path(args.output_dir) if args.output_dir else form_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        stem = form_path.stem
        if stem.endswith(".conditional-form"):
            stem = stem[: -len(".conditional-form")]

        from velocity_converter.condition_dsl import load_registry_dict  # noqa: PLC0415

        reg_path = _discover_registry(form_path.parent)
        registry = load_registry_dict(reg_path) if reg_path else None
        try:
            blocks = parse_conditional_form(
                form_path,
                variants_csv=Path(args.variants_csv) if args.variants_csv else None,
                registry=registry,
            )
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        registry_path = output_dir / f"{stem}.conditional-registry.yaml"
        write_conditional_registry(blocks, registry_path)
        print(f"Wrote {registry_path}")
        return 0

    # --- Mode: convert document ---
    if not args.input:
        print("Error: --input is required (unless using --parse-conditional-form)", file=sys.stderr)
        return 1

    input_path = Path(args.input)

    if not input_path.exists():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        return 1

    suffix = input_path.suffix.lower()

    if suffix == ".doc":
        print(
            "Error: legacy .doc format is not supported.\n"
            "Open the file in Microsoft Word → File → Save As → .docx, then re-run.",
            file=sys.stderr,
        )
        return 1

    if suffix not in (".docx", ".pdf"):
        print(
            f"Error: unsupported format '{suffix}'. Accepted: .docx, .pdf",
            file=sys.stderr,
        )
        return 1

    output_dir = Path(args.output_dir) if args.output_dir else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem

    # Find registry for explicit path resolution (walk up from input dir)
    registry_path = _discover_registry(input_path.parent)

    # Convert to raw HTML
    if suffix == ".docx":
        raw_html = convert_docx(input_path)
    else:
        raw_html = convert_pdf(input_path)

    # Apply a Leg -1 path-map (bare {leaf} → full accessor) if supplied, so the
    # author's friendly leaves resolve before extraction. Source doc is untouched.
    if args.path_map:
        pm = Path(args.path_map)
        if not pm.exists():
            print(f"Error: path-map not found: {pm}", file=sys.stderr)
            return 1
        raw_html = apply_path_map(raw_html, pm)

    # Write raw HTML
    raw_path = output_dir / f"{stem}.raw.html"
    raw_path.write_text(raw_html, encoding="utf-8")
    print(f"Wrote {raw_path}")

    # Extract + annotate fields
    fields = extract_fields(raw_html, registry_path=registry_path)
    annotated = annotate_fields(raw_html, fields)

    # Extract + annotate conditionals
    blocks = extract_conditionals(annotated)
    annotated = annotate_conditionals(annotated, blocks)

    # Extract [Name]...[/Name] loop sections (after field annotation so loop
    # membership is decided on $TBD_* token positions). Blocks containing a
    # loop flip to render: template (#if guard stays in the template).
    annotated, fields, loops = extract_loops(annotated, fields, cond_blocks=blocks)

    # Write annotated HTML (pipeline input for Leg 1 / Leg 3)
    annotated_path = output_dir / f"{stem}.annotated.html"
    annotated_path.write_text(annotated, encoding="utf-8")
    print(f"Wrote {annotated_path}")

    # Write leg2-compatible mapping
    mapping_path = output_dir / f"{stem}.mapping.yaml"
    write_leg2_mapping(fields, f"{stem}.annotated.html", mapping_path, loops=loops)
    print(f"Wrote {mapping_path}")

    # Write conditional form (only if there are conditionals). The form — and its
    # companion variants.csv — are human-fill files, so they live in the flat
    # action-needed/ space rather than alongside the machine artifacts.
    if blocks:
        form_path = action_needed_file(output_dir, f"{stem}.conditional-form.md")
        write_conditional_form(blocks, stem, form_path)
        print(f"Wrote {form_path}")
        if any(b.get("variant") for b in blocks):
            csv_path = action_needed_file(output_dir, f"{stem}.variants.csv")
            write_variants_csv_stub(blocks, stem, csv_path)
            print(f"Wrote {csv_path}")
    else:
        print("No [[conditional]] blocks found — skipping conditional form.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
