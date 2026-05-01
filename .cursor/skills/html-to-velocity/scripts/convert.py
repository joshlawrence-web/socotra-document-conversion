#!/usr/bin/env python3
"""
html-to-velocity: convert a Mustache-style HTML template into a Socotra-flavored
Velocity template, a YAML variable mapping file, and a human-readable sanity
report.

Usage:
    python3 convert.py path/to/input.html [--output-dir DIR] [--no-conditionals]
                                          [--auto-detect-loops]
                                          [--registry path/to/registry.yaml]

Outputs (written next to the input unless --output-dir is given):
    <stem>.vm
    <stem>.mapping.yaml
    <stem>.report.md

Philosophy:
    The skill DOES NOT auto-fix anything it finds suspicious. Every sanity
    concern (unlabeled variables, fragile blocks, apparent hardcoded amounts,
    etc.) is surfaced in the report.md for a human to triage. This is
    deliberate — the skill's job is to make template intent explicit, not to
    guess at customer-specific semantics.

Loop hints (Phase 4):
    When a registry YAML is available, every loop field gets an explicit
    context.loop: <loopname> and every top-level variable whose name starts
    with a registered iterable prefix (e.g. `vehicle_*` → Vehicle) gets
    context.loop_hint: <IterableName>. Loop hints flag likely scope
    violations to Leg 2 without claiming scope satisfaction — the mapping
    suggester treats loop_hint as a reasoning aid, not a scope proof.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from bs4 import BeautifulSoup, NavigableString, Tag
except ImportError:
    sys.exit(
        "Missing dependency beautifulsoup4. Install with: "
        "pip install beautifulsoup4 --break-system-packages"
    )

try:
    import yaml
except ImportError:
    sys.exit(
        "Missing dependency PyYAML. Install with: "
        "pip install pyyaml --break-system-packages"
    )


# ---------------------------------------------------------------------------
# Patterns + tag sets
# ---------------------------------------------------------------------------

VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")
MUSTACHE_RE = re.compile(r"\{\{\s*([#/])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

# Containers eligible to auto-detect a loop (opt-in only).
LOOP_CONTAINER_TAGS = {"tbody", "ul", "ol", "table", "section", "div"}

# Block-level tags we may wrap with #if to guard optional variables.
BLOCK_TAGS = {"p", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "div", "section"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def singularize(name: str) -> str:
    """Rough English singular for loop iterator naming. Human can override in YAML."""
    lower = name.lower()
    if lower.endswith("ies") and len(lower) > 3:
        return name[:-3] + "y"
    if lower.endswith(("ses", "xes", "zes", "ches", "shes")):
        return name[:-2]
    if lower.endswith("s") and not lower.endswith("ss") and len(lower) > 1:
        return name[:-1]
    return f"{name}_item"


def slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", (text or "").strip().lower()).strip("_")


def line_of(node) -> Optional[int]:
    return getattr(node, "sourceline", None)


def _clean_label(txt: str) -> str:
    txt = (txt or "").strip().rstrip(":").strip()
    # Reject placeholders, already-rewritten tokens, and Mustache-style text —
    # none of those are useful as "the label that identifies this variable".
    if not txt or "TBD_" in txt or "$" in txt or "{{" in txt:
        return ""
    return txt[:80]


def label_from_node(node) -> str:
    """Nearest non-empty previous sibling text (text node or tag)."""
    prev = node.previous_sibling
    while prev is not None:
        if isinstance(prev, NavigableString):
            cleaned = _clean_label(str(prev))
            if cleaned:
                return cleaned
        elif isinstance(prev, Tag):
            cleaned = _clean_label(prev.get_text(" ", strip=True))
            if cleaned:
                return cleaned
        prev = prev.previous_sibling
    return ""


def nearest_label(tag: Tag) -> str:
    cur = tag
    for _ in range(5):
        if cur is None:
            break
        label = label_from_node(cur)
        if label:
            return label
        cur = cur.parent
    return ""


def nearest_heading(tag: Tag) -> str:
    h = tag.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
    return h.get_text(" ", strip=True) if h else ""


def nearest_column_header(td: Tag) -> str:
    if td.name != "td":
        return ""
    tr = td.find_parent("tr")
    if not tr:
        return ""
    try:
        idx = [c for c in tr.children if isinstance(c, Tag)].index(td)
    except ValueError:
        return ""
    table = td.find_parent("table")
    if not table:
        return ""
    scope = table.find("thead") or table
    header_row = scope.find("tr")
    if not header_row:
        return ""
    ths = [c for c in header_row.children if isinstance(c, Tag) and c.name in ("th", "td")]
    if idx < len(ths):
        return ths[idx].get_text(" ", strip=True)
    return ""


def block_parent(node) -> Optional[Tag]:
    cur = node.parent if isinstance(node, NavigableString) else node
    while cur is not None:
        if isinstance(cur, Tag) and cur.name in BLOCK_TAGS:
            return cur
        cur = cur.parent
    return None


# ---------------------------------------------------------------------------
# Iterable registry loader (Phase 4 — loop_hint / explicit loop context)
# ---------------------------------------------------------------------------

def _default_registry_path(input_path: Path) -> Optional[Path]:
    """Search input dir and ancestors for ``registry/path-registry.yaml`` then ``path-registry.yaml``."""
    cur = input_path.parent.resolve()
    for _ in range(8):
        for rel in ("registry/path-registry.yaml", "path-registry.yaml"):
            candidate = cur / rel
            if candidate.is_file():
                return candidate
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def load_iterables(registry_path: Optional[Path]) -> list[dict]:
    """Return a list of iterables from the registry YAML, enriched with
    precomputed match keys.

    Each returned dict has:
        name:          registry `name` (canonical, e.g. "Vehicle")
        display_name:  registry `display_name`
        prefix:        lowercase prefix for name-based variable matching
                       (e.g. "vehicle_") — includes the trailing underscore
        keys:          set of lowercase tokens that identify this iterable
                       (name, iterator stem, simple plural) — used for
                       documentation / future heading heuristics, not for
                       the current prefix-only matcher.

    If registry_path is None or unreadable, returns [] (graceful degrade —
    Phase 4 loop hints are simply not emitted).
    """
    if registry_path is None or not registry_path.is_file():
        return []
    try:
        data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    raw = data.get("iterables") or []
    out: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        name_lc = name.lower()
        iterator = (entry.get("iterator") or "").lstrip("$").strip().lower()
        keys = {name_lc}
        if iterator:
            keys.add(iterator)
        # Simple plural — just for heuristic logging / future fallback.
        if name_lc and not name_lc.endswith("s"):
            keys.add(name_lc + "s")
        out.append(
            {
                "name": name,
                "display_name": entry.get("display_name") or name,
                "prefix": name_lc + "_",
                "keys": keys,
            }
        )
    # Sort by longest prefix first so a more specific iterable wins on tie.
    out.sort(key=lambda it: len(it["prefix"]), reverse=True)
    return out


def _match_loop_hint(var_name: str, iterables: list[dict]) -> Optional[str]:
    """Return the iterable `name` whose prefix matches the variable name, or None.

    Current rule (Phase 4, conservative): require the variable name to begin
    with `<iterable_name_lowercased>_`. This hits the canonical `vehicle_*`
    and `driver_*` test cases cleanly and avoids false positives for
    claim-level variables that happen to share a heading with an iterable
    block (e.g. `estimated_damage` under "Insured vehicle").
    """
    if not var_name or not iterables:
        return None
    lc = var_name.lower()
    for it in iterables:
        if lc.startswith(it["prefix"]):
            return it["name"]
    return None


# ---------------------------------------------------------------------------
# Mapping data structures
# ---------------------------------------------------------------------------

@dataclass
class Mapping:
    source: str
    variables: list[dict] = field(default_factory=list)
    loops: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_yaml_dict(self) -> dict:
        out = {
            "schema_version": "1.0",
            "source": self.source,
            "generated_at": _dt.datetime.now(_dt.timezone.utc)
            .replace(microsecond=0)
            .isoformat(),
            "variables": self.variables,
            "loops": self.loops,
        }
        if self.warnings:
            out["warnings"] = self.warnings
        return out


def _record_var(
    name: str,
    placeholder: str,
    anchor: Optional[Tag],
    mapping: Mapping,
    in_loop: bool,
    loop_fields: Optional[list[dict]],
    override_label: str = "",
    loop_name: Optional[str] = None,
):
    context: dict = {}
    if isinstance(anchor, Tag):
        context["parent_tag"] = anchor.name
        line = line_of(anchor)
        if line:
            context["line"] = line
        label = override_label or nearest_label(anchor)
        if label:
            context["nearest_label"] = label
        if anchor.name == "td":
            col = nearest_column_header(anchor)
            if col:
                context["column_header"] = col

    # Phase 4: loop fields carry an explicit `loop:` tag so Leg 2's Rule 2
    # can treat scope satisfaction uniformly without walking YAML nesting.
    if in_loop and loop_name:
        context["loop"] = loop_name

    entry = {
        "name": name,
        "placeholder": placeholder,
        "type": "loop_field" if in_loop else "variable",
        "context": context,
        "data_source": "",
    }
    bucket = loop_fields if in_loop and loop_fields is not None else mapping.variables
    for existing in bucket:
        if existing["name"] == name:
            return
    bucket.append(entry)


# ---------------------------------------------------------------------------
# Variable rewriting
# ---------------------------------------------------------------------------

def rewrite_vars_in_string(
    text: str, prefix: str, found: list[tuple[str, str]]
) -> str:
    def repl(m: re.Match) -> str:
        name = m.group(1)
        placeholder = f"{prefix}{name}"
        found.append((name, placeholder))
        return placeholder

    return VAR_RE.sub(repl, text)


def rewrite_vars_in_subtree(
    root,
    prefix: str,
    mapping: Mapping,
    *,
    in_loop: bool = False,
    loop_fields: Optional[list[dict]] = None,
    loop_name: Optional[str] = None,
) -> None:
    """Rewrite {{var}} tokens in text nodes and attribute values under root.

    `root` may be a Tag or a BeautifulSoup. Loop-scoped tokens are collected
    into `loop_fields`; others go into mapping.variables.
    """
    # Text nodes
    for text_node in list(root.find_all(string=VAR_RE)):
        parent_tag = text_node.parent if isinstance(text_node, NavigableString) else None
        pre_label = (
            label_from_node(text_node) if isinstance(text_node, NavigableString) else ""
        )
        found: list[tuple[str, str]] = []
        new_text = rewrite_vars_in_string(str(text_node), prefix, found)
        if new_text != str(text_node):
            text_node.replace_with(NavigableString(new_text))
            for name, placeholder in found:
                _record_var(
                    name=name,
                    placeholder=placeholder,
                    anchor=parent_tag,
                    mapping=mapping,
                    in_loop=in_loop,
                    loop_fields=loop_fields,
                    override_label=pre_label,
                    loop_name=loop_name,
                )

    # Attribute values
    for tag in root.find_all(True):
        for attr, value in list(tag.attrs.items()):
            if isinstance(value, list):
                new_list = []
                for v in value:
                    found = []
                    new_v = rewrite_vars_in_string(v, prefix, found)
                    new_list.append(new_v)
                    for name, placeholder in found:
                        _record_var(
                            name, placeholder, tag, mapping, in_loop, loop_fields,
                            loop_name=loop_name,
                        )
                tag.attrs[attr] = new_list
            elif isinstance(value, str):
                found = []
                new_v = rewrite_vars_in_string(value, prefix, found)
                if new_v != value:
                    tag.attrs[attr] = new_v
                    for name, placeholder in found:
                        _record_var(
                            name, placeholder, tag, mapping, in_loop, loop_fields,
                            loop_name=loop_name,
                        )


# ---------------------------------------------------------------------------
# Mustache loop processing ({{#name}} ... {{/name}})
# ---------------------------------------------------------------------------

def _collect_mustache_tokens(soup) -> list[dict]:
    tokens = []
    for node in soup.find_all(string=MUSTACHE_RE):
        s = str(node)
        for m in MUSTACHE_RE.finditer(s):
            tokens.append(
                {
                    "node": node,
                    "start": m.start(),
                    "end": m.end(),
                    "kind": m.group(1),
                    "name": m.group(2),
                }
            )
    return tokens


def _find_innermost_pair(soup) -> Optional[tuple[dict, dict]]:
    """Return (opener, closer) for an innermost Mustache section.

    An innermost section is an opener with a matching closer where no other
    opener appears between them (in DOM-order token stream).
    """
    tokens = _collect_mustache_tokens(soup)
    for i, t in enumerate(tokens):
        if t["kind"] != "#":
            continue
        for j in range(i + 1, len(tokens)):
            tj = tokens[j]
            if tj["kind"] == "#":
                break
            if tj["kind"] == "/" and tj["name"] == t["name"]:
                return (t, tj)
    return None


def _replace_token_in_text(node: NavigableString, start: int, end: int, replacement: str):
    s = str(node)
    new_s = s[:start] + replacement + s[end:]
    node.replace_with(NavigableString(new_s))


def _process_mustache_pair(
    soup, pair: tuple[dict, dict], mapping: Mapping
) -> None:
    opener, closer = pair
    name = opener["name"]
    iterator = singularize(name)
    foreach_text = f"\n#foreach (${iterator} in $TBD_{name})\n"
    end_text = "\n#end\n"

    op_node, cl_node = opener["node"], closer["node"]

    # Case 1: opener and closer in the same text node.
    if op_node is cl_node:
        s = str(op_node)
        before = s[: opener["start"]]
        body_text = s[opener["end"] : closer["start"]]
        after = s[closer["end"] :]
        # Rewrite vars inside the body text
        found: list[tuple[str, str]] = []
        rewritten = rewrite_vars_in_string(body_text, f"${iterator}.TBD_", found)
        loop_fields: list[dict] = []
        for fname, fplaceholder in found:
            _record_var(
                name=fname,
                placeholder=fplaceholder,
                anchor=op_node.parent if isinstance(op_node, NavigableString) else None,
                mapping=mapping,
                in_loop=True,
                loop_fields=loop_fields,
                loop_name=name,
            )
        mapping.loops.append(
            _loop_entry(name, iterator, op_node.parent, loop_fields, detection="mustache")
        )
        op_node.replace_with(
            NavigableString(f"{before}{foreach_text}{rewritten}{end_text}{after}")
        )
        return

    # Case 2: opener and closer must share a parent for v1.
    if op_node.parent is None or cl_node.parent is None:
        mapping.warnings.append(
            f"Loop '{name}': opener or closer is detached; skipped."
        )
        return
    if op_node.parent is not cl_node.parent:
        mapping.warnings.append(
            f"Loop '{name}' at line {line_of(op_node.parent)}: opener and closer "
            "live in different parent elements. Left unconverted. Wrap the loop "
            "body in a single container to resolve."
        )
        return

    parent = op_node.parent
    children = list(parent.children)
    try:
        i_op = children.index(op_node)
        i_cl = children.index(cl_node)
    except ValueError:
        mapping.warnings.append(f"Loop '{name}': could not locate tokens in parent; skipped.")
        return
    if i_op >= i_cl:
        mapping.warnings.append(f"Loop '{name}': closer precedes opener; skipped.")
        return

    body_nodes = children[i_op + 1 : i_cl]
    loop_fields: list[dict] = []

    def _record_found(found_list, anchor):
        for fname, fplaceholder in found_list:
            _record_var(
                name=fname,
                placeholder=fplaceholder,
                anchor=anchor,
                mapping=mapping,
                in_loop=True,
                loop_fields=loop_fields,
                loop_name=name,
            )

    # Body text inside the opener's text node (after the `{{#name}}` token) and
    # inside the closer's text node (before the `{{/name}}` token) is part of
    # the loop body and must be rewritten with the iterator prefix. This is
    # common in real templates (e.g. `{{#vehicles}} {{year}} {{make}} ...`).
    op_s = str(op_node)
    op_before = op_s[: opener["start"]]
    op_tail = op_s[opener["end"]:]
    op_tail_found: list[tuple[str, str]] = []
    op_tail_rewritten = rewrite_vars_in_string(op_tail, f"${iterator}.TBD_", op_tail_found)
    _record_found(op_tail_found, parent)

    for child in body_nodes:
        if isinstance(child, NavigableString):
            found: list[tuple[str, str]] = []
            new_text = rewrite_vars_in_string(str(child), f"${iterator}.TBD_", found)
            if new_text != str(child):
                child.replace_with(NavigableString(new_text))
                _record_found(found, parent)
        elif isinstance(child, Tag):
            rewrite_vars_in_subtree(
                child,
                prefix=f"${iterator}.TBD_",
                mapping=mapping,
                in_loop=True,
                loop_fields=loop_fields,
                loop_name=name,
            )

    cl_s = str(cl_node)
    cl_head = cl_s[: closer["start"]]
    cl_after = cl_s[closer["end"]:]
    cl_head_found: list[tuple[str, str]] = []
    cl_head_rewritten = rewrite_vars_in_string(cl_head, f"${iterator}.TBD_", cl_head_found)
    _record_found(cl_head_found, parent)

    mapping.loops.append(
        _loop_entry(name, iterator, parent, loop_fields, detection="mustache")
    )

    op_node.replace_with(
        NavigableString(f"{op_before}{foreach_text}{op_tail_rewritten}")
    )
    cl_node.replace_with(
        NavigableString(f"{cl_head_rewritten}{end_text}{cl_after}")
    )


def _loop_entry(name, iterator, container, fields, detection) -> dict:
    ctx = {}
    if isinstance(container, Tag):
        heading = nearest_heading(container)
        if heading:
            ctx["nearest_heading"] = heading
        line = line_of(container)
        if line:
            ctx["line"] = line
        ctx["container"] = container.name
    return {
        "name": name,
        "placeholder": f"$TBD_{name}",
        "iterator": f"${iterator}",
        "detection": detection,
        "context": ctx,
        "data_source": "",
        "fields": fields,
    }


def process_all_mustache_loops(soup, mapping: Mapping):
    """Convert all {{#name}}...{{/name}} pairs, innermost first."""
    # Safety cap so a malformed template can't spin forever.
    for _ in range(1000):
        pair = _find_innermost_pair(soup)
        if not pair:
            return
        _process_mustache_pair(soup, pair, mapping)


# ---------------------------------------------------------------------------
# Optional: auto-detect loops from sibling repetition (off by default)
# ---------------------------------------------------------------------------

def _guess_loop_name(container: Tag) -> str:
    h = container.find_previous(["h1", "h2", "h3", "h4", "h5", "h6"])
    if h:
        n = slugify(h.get_text(" ", strip=True))
        if n:
            return n if n.endswith("s") else f"{n}s"
    cls = container.get("class")
    if cls:
        n = slugify("_".join(cls))
        if n:
            return n
    return ""


def auto_detect_loops(soup, mapping: Mapping):
    for container in soup.find_all(list(LOOP_CONTAINER_TAGS)):
        tag_children = [c for c in container.children if isinstance(c, Tag)]
        if len(tag_children) < 2:
            continue
        if len({c.name for c in tag_children}) != 1:
            continue
        first = tag_children[0]
        if container.name == "table" and first.name in ("thead", "tbody", "tfoot"):
            continue
        name = _guess_loop_name(container) or "items"
        iterator = singularize(name)
        # Remove sibling copies; keep the first
        for sib in tag_children[1:]:
            if sib.name == first.name:
                sib.extract()
        loop_fields: list[dict] = []
        rewrite_vars_in_subtree(
            first,
            prefix=f"${iterator}.TBD_",
            mapping=mapping,
            in_loop=True,
            loop_fields=loop_fields,
            loop_name=name,
        )
        mapping.loops.append(
            _loop_entry(name, iterator, container, loop_fields, detection="auto")
        )
        first.insert_before(NavigableString(f"\n#foreach (${iterator} in $TBD_{name})\n"))
        first.insert_after(NavigableString("\n#end\n"))


# ---------------------------------------------------------------------------
# #if wrapping for optional block variables
# ---------------------------------------------------------------------------

def wrap_conditionals(soup, mapping: Mapping):
    tbd_pattern = re.compile(r"\$TBD_([a-zA-Z_][a-zA-Z0-9_]*)")
    seen: set[int] = set()
    # Find all text nodes containing a $TBD_ token that isn't $iter.TBD_
    for text_node in list(soup.find_all(string=tbd_pattern)):
        # Skip if this text is a $iter.TBD_ reference (loop-scoped)
        if re.search(r"\$[a-zA-Z_][a-zA-Z0-9_]*\.TBD_", str(text_node)):
            continue
        block = block_parent(text_node)
        if block is None or id(block) in seen:
            continue
        if _inside_foreach(block):
            continue
        seen.add(id(block))
        block_text = "".join(str(t) for t in block.find_all(string=True))
        # Collect only standalone (non-iter-scoped) names
        standalone = []
        for m in tbd_pattern.finditer(block_text):
            nm = m.group(1)
            if re.search(r"\$[a-zA-Z_][a-zA-Z0-9_]*\.TBD_" + re.escape(nm), block_text):
                continue
            if nm not in standalone:
                standalone.append(nm)
        if not standalone:
            continue
        # Use Velocity's `and` keyword rather than `&&` because BeautifulSoup
        # HTML-encodes `&` on serialization, which would break the directive.
        cond = (
            f"$TBD_{standalone[0]}"
            if len(standalone) == 1
            else " and ".join(f"$TBD_{n}" for n in standalone)
        )
        block.insert_before(NavigableString(f"\n#if({cond})\n"))
        block.insert_after(NavigableString("\n#end\n"))


def _inside_foreach(tag: Tag) -> bool:
    cur = tag
    while cur is not None:
        prev = cur.previous_sibling
        while prev is not None:
            if isinstance(prev, NavigableString) and "#foreach" in str(prev):
                return True
            prev = prev.previous_sibling
        cur = cur.parent
    return False


# ---------------------------------------------------------------------------
# Sanity report
# ---------------------------------------------------------------------------

SUSPICIOUS_TOKEN_RE = re.compile(r"\b(XXXX+|X{3,}|TBD|TODO|FIXME)\b")
DOLLAR_AMOUNT_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?")


@dataclass
class Finding:
    category: str
    message: str
    line: Optional[int] = None
    severity: str = "info"  # info | warn | error


@dataclass
class SanityReport:
    source: str
    findings: list[Finding] = field(default_factory=list)

    def add(self, **kwargs):
        self.findings.append(Finding(**kwargs))

    def to_markdown(self) -> str:
        lines = [f"# Sanity report — {self.source}", ""]
        if not self.findings:
            lines.append("No issues found.")
            return "\n".join(lines) + "\n"
        # Summary
        by_cat: dict[str, list[Finding]] = {}
        for f in self.findings:
            by_cat.setdefault(f.category, []).append(f)
        lines.append(
            f"{len(self.findings)} findings across {len(by_cat)} categories. "
            "Review before mapping; this skill never auto-fixes what it flags."
        )
        lines.append("")
        for cat in sorted(by_cat):
            lines.append(f"## {cat}")
            lines.append("")
            for f in by_cat[cat]:
                prefix = f"**L{f.line}** — " if f.line else "- "
                if f.line:
                    lines.append(f"- {prefix}{f.message}")
                else:
                    lines.append(f"{prefix}{f.message}")
            lines.append("")
        return "\n".join(lines)


def build_sanity_report(raw_html: str, soup: BeautifulSoup, source_name: str) -> SanityReport:
    """Inspect the raw HTML and the original soup (before transforms) for common issues.

    This runs on the original soup, not the transformed one, so lines, labels,
    and Mustache tokens are all still in place.
    """
    report = SanityReport(source=source_name)

    # --- Line-based checks on raw HTML --------------------------------------
    for lineno, line in enumerate(raw_html.splitlines(), start=1):
        # Suspicious placeholder tokens in static text
        if SUSPICIOUS_TOKEN_RE.search(line) and not VAR_RE.search(line):
            token = SUSPICIOUS_TOKEN_RE.search(line).group(0)
            report.add(
                category="Suspicious placeholder tokens",
                message=f"`{token}` appears in static text: `{line.strip()[:120]}`",
                line=lineno,
                severity="warn",
            )
        # Hardcoded dollar amounts in text (but skip CSS-ish lines with `:`)
        if DOLLAR_AMOUNT_RE.search(line) and not VAR_RE.search(line):
            if "<style" in line or line.strip().startswith(("//", "/*", "*/")):
                continue
            if re.search(r"[a-z-]+\s*:\s*\$", line):
                continue
            for m in DOLLAR_AMOUNT_RE.finditer(line):
                found_amt = m.group(0).rstrip(",.")
                report.add(
                    category="Potentially hardcoded dollar amounts",
                    message=(
                        f"Found `{found_amt}` in static text. Consider making this a "
                        "variable if product/state dependent."
                    ),
                    line=lineno,
                    severity="info",
                )

    # --- DOM-based checks on the original soup ------------------------------

    # (a) Mustache sections with body containing <li> but no <ul>/<ol> ancestor
    tokens = _collect_mustache_tokens(soup)
    openers = {(t["name"], id(t["node"])): t for t in tokens if t["kind"] == "#"}
    for t in tokens:
        if t["kind"] != "#":
            continue
        parent = t["node"].parent
        # Find the closer with same name in same parent
        closer = None
        for tc in tokens:
            if (
                tc["kind"] == "/"
                and tc["name"] == t["name"]
                and tc["node"].parent is parent
            ):
                closer = tc
                break
        if closer is None:
            continue
        children = list(parent.children) if parent else []
        try:
            i_op = children.index(t["node"])
            i_cl = children.index(closer["node"])
        except ValueError:
            continue
        body = children[i_op + 1 : i_cl]
        has_li = any(isinstance(c, Tag) and c.name == "li" for c in body) or any(
            isinstance(c, Tag) and c.find("li") for c in body if isinstance(c, Tag)
        )
        if has_li:
            # Check ancestor is ul/ol
            anc = parent
            found_list_anc = False
            while anc is not None:
                if isinstance(anc, Tag) and anc.name in ("ul", "ol"):
                    found_list_anc = True
                    break
                anc = anc.parent
            if not found_list_anc:
                report.add(
                    category="Structural",
                    message=(
                        f"Loop `{{{{#{t['name']}}}}}` body contains `<li>` but has no "
                        "`<ul>`/`<ol>` ancestor; it will render as loose list items."
                    ),
                    line=line_of(t["node"]) or line_of(parent),
                    severity="warn",
                )

    # (b) Single-variable block elements (entire content is one {{var}})
    for tag in soup.find_all(True):
        if tag.name not in BLOCK_TAGS | {"span", "strong", "em"}:
            continue
        txt = tag.get_text(" ", strip=True)
        if not txt:
            continue
        m = VAR_RE.fullmatch(txt)
        if m:
            report.add(
                category="Fragile single-variable blocks",
                message=(
                    f"`<{tag.name}>` content is the single variable `{{{{{m.group(1)}}}}}`. "
                    "If the data is missing, this element will render empty. Consider a "
                    "fallback label or wrap with `#if`."
                ),
                line=line_of(tag),
                severity="info",
            )

    # (c) Unlabeled variables — a variable is "unlabeled" when there is no
    #     human-readable text IMMEDIATELY before it (in the same text node, or
    #     in the previous sibling). We keep this deliberately local so it
    #     catches the real pain cases (rows of bare tokens like `{{agent_code}}`
    #     on their own lines) without complaining about every variable whose
    #     label lives a few tags away.
    seen_unlabeled: set[tuple[str, int]] = set()
    for text_node in soup.find_all(string=VAR_RE):
        s = str(text_node)
        for m in VAR_RE.finditer(s):
            vname = m.group(1)
            parent = text_node.parent if isinstance(text_node, NavigableString) else None
            line = (line_of(parent) if parent is not None else None) or line_of(text_node)

            # Is there human text BEFORE the token on the same text node?
            before_in_node = s[: m.start()]
            # Strip any earlier {{...}} tokens from before_in_node — another
            # variable on the same line does not count as a label.
            cleaned = VAR_RE.sub("", before_in_node).strip()
            if cleaned:
                continue

            # Otherwise, check the text node's immediate previous sibling.
            pre = (
                label_from_node(text_node)
                if isinstance(text_node, NavigableString)
                else ""
            )
            if pre:
                continue

            key = (vname, line or 0)
            if key in seen_unlabeled:
                continue
            seen_unlabeled.add(key)
            report.add(
                category="Unlabeled variables",
                message=(
                    f"`{{{{{vname}}}}}` has no label immediately before it. "
                    "Confirm the label is conveyed by layout, or add `<strong>...:</strong>` style tag."
                ),
                line=line,
                severity="info",
            )

    # (d) Cross-scope variable name reuse (same var name used in multiple Mustache
    #     loops). Informational, since Mustache semantics make this legal.
    loop_scopes: dict[str, set[str]] = {}
    # Walk Mustache sections and record inner variables per loop
    pair_tokens = _collect_mustache_tokens(soup)
    # Pair up via stack
    stack: list[dict] = []
    for tok in pair_tokens:
        if tok["kind"] == "#":
            stack.append(tok)
        elif tok["kind"] == "/":
            # Pop the matching opener
            for i in range(len(stack) - 1, -1, -1):
                if stack[i]["name"] == tok["name"]:
                    opener = stack.pop(i)
                    if opener["node"].parent is tok["node"].parent and opener["node"].parent is not None:
                        parent = opener["node"].parent
                        children = list(parent.children)
                        try:
                            i_op = children.index(opener["node"])
                            i_cl = children.index(tok["node"])
                        except ValueError:
                            break
                        body = children[i_op + 1 : i_cl]
                        text_blob = "".join(
                            str(c.get_text(" ", strip=True) if isinstance(c, Tag) else c)
                            for c in body
                        )
                        names = {m.group(1) for m in VAR_RE.finditer(text_blob)}
                        loop_scopes.setdefault(opener["name"], set()).update(names)
                    break
    if loop_scopes:
        # var → list of loops it appears in
        var_to_loops: dict[str, list[str]] = {}
        for loop_name, var_names in loop_scopes.items():
            for vn in var_names:
                var_to_loops.setdefault(vn, []).append(loop_name)
        for vn, loops in sorted(var_to_loops.items()):
            if len(loops) >= 2:
                report.add(
                    category="Cross-scope variable name reuse",
                    message=(
                        f"`{{{{{vn}}}}}` appears inside {len(loops)} loop scopes: "
                        + ", ".join(f"`{l}`" for l in sorted(loops))
                        + ". Each will need its own data source during mapping."
                    ),
                    severity="info",
                )

    # (e) Unmatched Mustache tokens (opener without closer or vice versa)
    openers_list = [t for t in _collect_mustache_tokens(soup) if t["kind"] == "#"]
    closers_list = [t for t in _collect_mustache_tokens(soup) if t["kind"] == "/"]
    unmatched_openers = []
    stack2: list[dict] = []
    for t in _collect_mustache_tokens(soup):
        if t["kind"] == "#":
            stack2.append(t)
        else:
            for i in range(len(stack2) - 1, -1, -1):
                if stack2[i]["name"] == t["name"]:
                    stack2.pop(i)
                    break
            else:
                report.add(
                    category="Unmatched Mustache tokens",
                    message=f"`{{{{/{t['name']}}}}}` has no matching opener.",
                    line=line_of(t["node"]),
                    severity="error",
                )
    for t in stack2:
        report.add(
            category="Unmatched Mustache tokens",
            message=f"`{{{{#{t['name']}}}}}` has no matching closer.",
            line=line_of(t["node"]),
            severity="error",
        )

    return report


# ---------------------------------------------------------------------------
# YAML emission
# ---------------------------------------------------------------------------

def _yaml_safe(data):
    if isinstance(data, dict):
        return {k: _yaml_safe(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_yaml_safe(x) for x in data]
    if isinstance(data, set):
        return sorted(data)
    return data


def dump_yaml(mapping: Mapping) -> str:
    data = _yaml_safe(mapping.to_yaml_dict())
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def annotate_loop_hints(mapping: Mapping, iterables: list[dict]) -> None:
    """Walk mapping.variables (top-level only) and set context.loop_hint where
    the variable name matches a registered iterable prefix.

    This is a post-pass so it sees the final deduplicated variable list. Loop
    fields already carry context.loop from _record_var; no loop_hint is
    emitted on them.
    """
    if not iterables:
        return
    for entry in mapping.variables:
        name = entry.get("name") or ""
        hint = _match_loop_hint(name, iterables)
        if hint:
            ctx = entry.setdefault("context", {})
            ctx["loop_hint"] = hint


def convert(
    input_path: Path,
    output_dir: Optional[Path],
    with_conditionals: bool = True,
    auto_detect: bool = False,
    registry_path: Optional[Path] = None,
    iterables: Optional[list[dict]] = None,
):
    html = input_path.read_text(encoding="utf-8")

    # Build the sanity report against a FRESH parse so nothing is transformed.
    sanity_soup = BeautifulSoup(html, "html.parser")
    report = build_sanity_report(html, sanity_soup, input_path.name)

    soup = BeautifulSoup(html, "html.parser")
    mapping = Mapping(source=input_path.name)

    # Load iterables for loop-hint tagging. In batch mode, iterables are
    # pre-loaded once by the caller and passed in to avoid redundant file reads.
    if iterables is None:
        resolved_registry = registry_path or _default_registry_path(input_path)
        iterables = load_iterables(resolved_registry)

    # 1. Process Mustache loops (innermost first — handles nesting)
    process_all_mustache_loops(soup, mapping)

    # 2. Optional: auto-detect loops from sibling repetition (opt-in only)
    if auto_detect:
        auto_detect_loops(soup, mapping)

    # 3. Rewrite remaining {{var}} tokens outside loops → $TBD_var
    rewrite_vars_in_subtree(soup, prefix="$TBD_", mapping=mapping, in_loop=False)

    # 4. Wrap blocks containing $TBD_* with #if
    if with_conditionals:
        wrap_conditionals(soup, mapping)

    # 5. Any leftover Mustache tokens are a warning (couldn't convert)
    for t in _collect_mustache_tokens(soup):
        mapping.warnings.append(
            f"Unconverted Mustache token `{{{{{t['kind']}{t['name']}}}}}` at line {line_of(t['node'])}."
        )

    # 6. Annotate context.loop_hint on top-level variables (Phase 4).
    annotate_loop_hints(mapping, iterables)

    # 7. Serialize
    vm_text = str(soup)
    yaml_text = dump_yaml(mapping)
    report_text = report.to_markdown()

    target_dir = output_dir or input_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = input_path.stem
    vm_path = target_dir / f"{stem}.vm"
    yaml_path = target_dir / f"{stem}.mapping.yaml"
    report_path = target_dir / f"{stem}.report.md"
    vm_path.write_text(vm_text, encoding="utf-8")
    yaml_path.write_text(yaml_text, encoding="utf-8")
    report_path.write_text(report_text, encoding="utf-8")
    return vm_path, yaml_path, report_path, len(mapping.variables), len(mapping.loops)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=None,
        help="Path to the HTML input file (omit when using --batch)",
    )
    parser.add_argument(
        "--batch",
        nargs="+",
        metavar="FILE",
        type=Path,
        help=(
            "Process multiple HTML files in one pass. "
            "--output-dir is treated as the parent directory; each file "
            "writes to <output-dir>/<stem>/. "
            "The registry file is loaded once and shared across all inputs. "
            "Incompatible with the single-file positional argument."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for outputs (default: next to input)",
    )
    parser.add_argument(
        "--no-conditionals",
        action="store_true",
        help="Do not wrap variable-bearing blocks with #if/#end",
    )
    parser.add_argument(
        "--auto-detect-loops",
        action="store_true",
        help="Also convert sibling-repetition loops (off by default; Mustache-only is safer).",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help=(
            "Path to registry YAML (Phase 4). Drives loop_hint tagging "
            "on top-level variables. If omitted, the script searches the "
            "input's directory and its ancestors for registry/path-registry.yaml "
            "then path-registry.yaml; if none is found, loop hints are not emitted."
        ),
    )
    args = parser.parse_args(argv)

    if args.batch:
        # Load registry YAML exactly once for the entire batch.
        registry_path = args.registry
        if registry_path is None:
            registry_path = _default_registry_path(args.batch[0])
        iterables = load_iterables(registry_path)

        total_vars = 0
        total_loops = 0
        processed = 0
        for html_path in args.batch:
            if not html_path.is_file():
                print(f"Skipping {html_path}: file not found", file=sys.stderr)
                continue
            stem = html_path.stem
            out_dir = (args.output_dir / stem) if args.output_dir else None
            vm_path, yaml_path, report_path, var_count, loop_count = convert(
                html_path,
                out_dir,
                with_conditionals=not args.no_conditionals,
                auto_detect=args.auto_detect_loops,
                iterables=iterables,
            )
            target_dir = vm_path.parent
            print(f"✓ {stem:<20} → {target_dir}/  ({var_count} vars, {loop_count} loops)")
            total_vars += var_count
            total_loops += loop_count
            processed += 1

        print(f"Batch complete: {processed} files, {total_vars} vars, {total_loops} loops")
        return 0

    if args.input:
        if not args.input.is_file():
            print(f"Input not found: {args.input}", file=sys.stderr)
            return 2

        out_dir = (args.output_dir / args.input.stem) if args.output_dir else None
        vm_path, yaml_path, report_path, _vars, _loops = convert(
            args.input,
            out_dir,
            with_conditionals=not args.no_conditionals,
            auto_detect=args.auto_detect_loops,
            registry_path=args.registry,
        )
        print(f"Wrote {vm_path}")
        print(f"Wrote {yaml_path}")
        print(f"Wrote {report_path}")
        return 0

    parser.error("Provide an input file or use --batch.")


if __name__ == "__main__":
    raise SystemExit(main())
