#!/usr/bin/env python3
"""Splice a table from one .docx into another, self-contained.

OOXML formatting is inherited from the *containing* document's styles.xml
(docDefaults / Normal), so a byte-for-byte table copy silently restyles in the
target (row heights double, fonts swap). This tool bakes the source document's
effective defaults (spacing, justification, font, size) into every paragraph
and run of the copied table, copies referenced style definitions, checks the
table fits the target's printable width, and verifies its own output.

Usage:
  python3 tools/splice_docx_table.py \
      --source <src.docx> --table-contains "CPT Codes" \
      --target <dst.docx> [--before-text "ZenCover Limited"] \
      [--heading "Concussion Medical Expense Benefit — CPT Code Schedule"]

The target is modified in place (git is the undo). Run Leg 0 afterwards.
"""
import argparse
import re
import sys
import zipfile

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def die(msg):
    sys.exit(f"ERROR: {msg}")


def read_part(path, name):
    with zipfile.ZipFile(path) as z:
        return z.read(name).decode("utf-8")


def para_text(xml_fragment):
    return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml_fragment))


def top_level_tables(doc_xml):
    """Spans of top-level <w:tbl> elements (nesting-aware)."""
    events = sorted(
        [(m.start(), 1) for m in re.finditer(r"<w:tbl>", doc_xml)]
        + [(m.end(), -1) for m in re.finditer(r"</w:tbl>", doc_xml)]
    )
    depth, start, spans = 0, None, []
    for pos, d in events:
        if d == 1:
            if depth == 0:
                start = pos
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                spans.append((start, pos))
    return spans


def find_table(doc_xml, needle):
    hits = [
        (s, e) for s, e in top_level_tables(doc_xml)
        if needle in para_text(doc_xml[s:e])
    ]
    if not hits:
        die(f"no table in source contains {needle!r}")
    if len(hits) > 1:
        die(f"{len(hits)} tables contain {needle!r} — use a more specific "
            "--table-contains")
    s, e = hits[0]
    return doc_xml[s:e]


def theme_minor_font(path):
    try:
        theme = read_part(path, "word/theme/theme1.xml")
        m = re.search(r"<a:minorFont>.*?<a:latin[^>]*typeface=\"([^\"]+)\"",
                      theme, re.S)
        return m.group(1) if m else None
    except KeyError:
        return None


def effective_defaults(path):
    """Source doc's effective paragraph/run defaults (docDefaults + Normal)."""
    styles = read_part(path, "word/styles.xml")
    out = {"spacing": '<w:spacing w:after="0" w:before="0" w:line="240" '
                      'w:lineRule="auto"/>',  # Word's built-in default
           "jc": None, "font": None, "sz": None}
    scopes = []
    dd = re.search(r"<w:docDefaults>.*?</w:docDefaults>", styles, re.S)
    if dd:
        scopes.append(dd.group(0))
    normal = re.search(
        r'<w:style [^>]*w:styleId="Normal"[^>]*>.*?</w:style>', styles, re.S)
    if normal:
        scopes.append(normal.group(0))  # Normal overrides docDefaults
    for scope in scopes:
        m = re.search(r"<w:spacing [^/]*/>", scope)
        if m:
            out["spacing"] = m.group(0)
        m = re.search(r'<w:jc w:val="([^"]+)"/>', scope)
        if m:
            out["jc"] = m.group(0)
        m = re.search(r'<w:rFonts [^/]*w:ascii="([^"]+)"[^/]*/>', scope)
        if m:
            out["font"] = m.group(1)
        elif "w:asciiTheme=" in scope:
            out["font"] = theme_minor_font(path)
        m = re.search(r'<w:sz w:val="([^"]+)"/>', scope)
        if m:
            out["sz"] = m.group(1)
    return out


def bake_defaults(table, defaults):
    """Make every paragraph/run carry the source's effective formatting."""
    spacing = defaults["spacing"]
    jc = defaults["jc"]

    def fix_ppr(m):
        ppr = m.group(0)
        if "<w:spacing" not in ppr:
            # schema order: ... tabs < spacing < ind < ... < jc < rPr
            anchor = re.search(r"<w:ind |<w:jc |<w:rPr[ />]|</w:pPr>", ppr)
            i = anchor.start()
            ppr = ppr[:i] + spacing + ppr[i:]
        if jc and "<w:jc " not in ppr:
            anchor = re.search(r"<w:rPr[ />]|</w:pPr>", ppr)
            i = anchor.start()
            ppr = ppr[:i] + jc + ppr[i:]
        return ppr

    table = re.sub(r"<w:pPr>.*?</w:pPr>", fix_ppr, table, flags=re.S)
    # paragraphs with no pPr at all
    table = re.sub(r"(<w:p(?: [^>]*)?>)(?!<w:pPr)",
                   lambda m: m.group(1) + "<w:pPr>" + spacing + "</w:pPr>",
                   table)

    run_props = ""
    if defaults["font"]:
        f = defaults["font"]
        run_props += (f'<w:rFonts w:ascii="{f}" w:hAnsi="{f}" w:cs="{f}" '
                      f'w:eastAsia="{f}"/>')
    if defaults["sz"]:
        run_props += (f'<w:sz w:val="{defaults["sz"]}"/>'
                      f'<w:szCs w:val="{defaults["sz"]}"/>')
    if run_props:
        def fix_rpr(m):
            rpr = m.group(0)
            add = ""
            if defaults["font"] and "<w:rFonts" not in rpr:
                f = defaults["font"]
                add += (f'<w:rFonts w:ascii="{f}" w:hAnsi="{f}" w:cs="{f}" '
                        f'w:eastAsia="{f}"/>')
            if defaults["sz"] and "<w:sz " not in rpr:
                # rFonts first, then sz — insert sz before </w:rPr>
                rpr = rpr.replace(
                    "</w:rPr>",
                    f'<w:sz w:val="{defaults["sz"]}"/>'
                    f'<w:szCs w:val="{defaults["sz"]}"/></w:rPr>', 1)
            return rpr.replace("<w:rPr>", "<w:rPr>" + add, 1)

        # only run-level rPr (inside <w:r>), not paragraph-mark rPr in pPr:
        # paragraph-mark props don't affect layout of the text runs.
        table = re.sub(r"<w:rPr>.*?</w:rPr>", fix_rpr, table, flags=re.S)
        table = table.replace("<w:rPr/>", "<w:rPr>" + run_props + "</w:rPr>")
    return table


def reject_unsupported(table):
    for pat, what in [(r"<w:drawing", "images/drawings"),
                      (r"<w:numPr>", "numbered/bulleted lists"),
                      (r"<w:hyperlink", "hyperlinks"),
                      (r'r:(?:id|embed)="', "relationship references"),
                      (r"<w:footnoteReference", "footnotes"),
                      (r"<w:commentR", "comments")]:
        if re.search(pat, table):
            # ponytail: rel-parts copying (media, rels, numbering) not built;
            # add when a real doc needs it
            die(f"table contains {what} — not supported by this splicer")


def printable_width(doc_xml):
    pg = re.search(r'<w:pgSz [^/]*w:w="(\d+)"', doc_xml)
    left = re.search(r'<w:pgMar [^/]*w:left="(\d+)"', doc_xml)
    right = re.search(r'<w:pgMar [^/]*w:right="(\d+)"', doc_xml)
    if not (pg and left and right):
        return None
    return int(pg.group(1)) - int(left.group(1)) - int(right.group(1))


def fit_to_page(table, target_doc):
    avail = printable_width(target_doc)
    m = re.search(r'<w:tblW w:w="([\d.]+)" w:type="dxa"/>', table)
    if not (avail and m):
        return table
    width = float(m.group(1))
    ind = re.search(r'<w:tblInd w:w="([\d.]+)" w:type="dxa"/>', table)
    indent = float(ind.group(1)) if ind else 0.0
    if width + indent > avail and indent > 0:
        print(f"note: dropped table indent {indent:g} twips (source-doc "
              f"context) so the table fits the target page")
        table = table.replace(ind.group(0), '<w:tblInd w:w="0" w:type="dxa"/>',
                              1)
        indent = 0.0
    if width + indent > avail:
        die(f"table is {width + indent:g} twips wide but target printable "
            f"width is {avail} — widen target margins or shrink the table")
    return table


def copy_styles(table, src_path, target_styles):
    """Copy style defs the table references (basedOn chain included)."""
    src_styles = read_part(src_path, "word/styles.xml")
    wanted = set(re.findall(
        r'<w:(?:tblStyle|pStyle|rStyle) w:val="([^"]+)"', table))
    copied, renames = [], {}
    while wanted:
        sid = wanted.pop()
        m = re.search(
            rf'<w:style [^>]*w:styleId="{re.escape(sid)}".*?</w:style>',
            src_styles, re.S)
        if not m:
            continue  # built-in (TableNormal etc.) — target has its own
        sdef = m.group(0)
        existing = re.search(
            rf'<w:style [^>]*w:styleId="{re.escape(sid)}"[^>]*>.*?</w:style>',
            target_styles, re.S)
        if existing:
            if existing.group(0) == sdef:
                continue  # identical — nothing to do
            new_id = sid + "Spliced"
            renames[sid] = new_id
            sdef = sdef.replace(f'w:styleId="{sid}"', f'w:styleId="{new_id}"')
        for based in re.findall(r'<w:basedOn w:val="([^"]+)"/>', sdef):
            if (based not in renames
                    and f'w:styleId="{based}"' not in target_styles):
                wanted.add(based)
        copied.append(sdef)
    for old, new in renames.items():
        table = table.replace(f'w:val="{old}"', f'w:val="{new}"')
        print(f"note: style '{old}' already exists in target with a different "
              f"definition — copied as '{new}'")
    if copied:
        target_styles = target_styles.replace(
            "</w:styles>", "".join(copied) + "</w:styles>")
    return table, target_styles


def verify(doc_xml, needle):
    """Re-check the written table: fully explicit formatting, on-page."""
    table = find_table(doc_xml, needle)
    bad_p = [p for p in re.findall(r"<w:p[ >].*?</w:p>", table, re.S)
             if "<w:spacing" not in p]
    if bad_p:
        die(f"verify: {len(bad_p)} paragraph(s) still inherit spacing")
    avail = printable_width(doc_xml)
    m = re.search(r'<w:tblW w:w="([\d.]+)" w:type="dxa"/>', table)
    ind = re.search(r'<w:tblInd w:w="([\d.]+)" w:type="dxa"/>', table)
    if avail and m:
        total = float(m.group(1)) + (float(ind.group(1)) if ind else 0)
        if total > avail:
            die(f"verify: table ({total:g} twips) overflows page ({avail})")
    rows = len(re.findall(r"<w:tr[ >]", table))
    print(f"verified: table present, {rows} rows, "
          "all paragraphs carry explicit spacing, fits printable width")


def main():
    ap = argparse.ArgumentParser(
        description="Splice a table between .docx files, self-contained")
    ap.add_argument("--source", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--table-contains", required=True,
                    help="text that uniquely identifies the source table")
    ap.add_argument("--before-text",
                    help="insert before the target paragraph containing this "
                         "text (default: end of document)")
    ap.add_argument("--heading", help="bold heading paragraph above the table")
    ap.add_argument("--wrap-region", metavar="NAME",
                    help="wrap the spliced block in [NAME?] … [/NAME] "
                         "conditional row-region markers (Leg 0 turns them "
                         "into a plugin-driven #if; fill the when-only row "
                         "in variants.csv)")
    args = ap.parse_args()
    if args.wrap_region and not re.fullmatch(r"[A-Za-z_]\w*", args.wrap_region):
        die(f"--wrap-region {args.wrap_region!r} must be a bare name "
            "([A-Za-z_]\\w*)")

    src_doc = read_part(args.source, "word/document.xml")
    table = find_table(src_doc, args.table_contains)
    reject_unsupported(table)

    defaults = effective_defaults(args.source)
    print(f"source effective defaults: spacing={defaults['spacing']!r} "
          f"jc={defaults['jc']!r} font={defaults['font']!r} "
          f"sz={defaults['sz']!r}")
    table = bake_defaults(table, defaults)

    with zipfile.ZipFile(args.target) as z:
        target_doc = z.read("word/document.xml").decode("utf-8")
        target_styles = z.read("word/styles.xml").decode("utf-8")
        items = z.infolist()
        data = {i.filename: z.read(i.filename) for i in items}

    # namespace prefixes used by the table must exist on the target root
    root = re.search(r"<w:document[^>]*>", target_doc).group(0)
    for pfx in set(re.findall(r"</?(\w+):", table)) - {"w"}:
        if f"xmlns:{pfx}=" not in root:
            die(f"table uses namespace prefix '{pfx}:' the target document "
                "does not declare")

    table = fit_to_page(table, target_doc)
    table, target_styles = copy_styles(table, args.source, target_styles)

    block = table + "<w:p/>"
    if args.heading:
        block = ('<w:p><w:pPr><w:rPr><w:b/></w:rPr></w:pPr><w:r><w:rPr>'
                 f'<w:b/></w:rPr><w:t>{args.heading}</w:t></w:r></w:p>'
                 + block)
    if args.wrap_region:
        def marker(text):
            return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"
        block = (marker(f"[{args.wrap_region}?]") + block
                 + marker(f"[/{args.wrap_region}]"))
        print(f"wrapped in [{args.wrap_region}?] region — after Leg 0, fill "
              f"its when-only row in variants.csv (blank = always render)")
    if args.before_text:
        paras = [(m.start(), m.group(0))
                 for m in re.finditer(r"<w:p[ >].*?</w:p>", target_doc, re.S)
                 if args.before_text in para_text(m.group(0))]
        if not paras:
            die(f"no target paragraph contains {args.before_text!r}")
        pos = paras[0][0]
    else:
        pos = target_doc.rindex("<w:sectPr")
    target_doc = target_doc[:pos] + block + target_doc[pos:]

    with zipfile.ZipFile(args.target, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in items:
            payload = data[item.filename]
            if item.filename == "word/document.xml":
                payload = target_doc.encode("utf-8")
            elif item.filename == "word/styles.xml":
                payload = target_styles.encode("utf-8")
            zout.writestr(item, payload)

    verify(read_part(args.target, "word/document.xml"), args.table_contains)
    print(f"spliced into {args.target} — if the file is open in Word, close "
          "WITHOUT saving; then re-run Leg 0")


if __name__ == "__main__":
    main()
