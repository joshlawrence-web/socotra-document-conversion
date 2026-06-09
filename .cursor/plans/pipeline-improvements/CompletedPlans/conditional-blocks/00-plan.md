# Conditional Block Extraction — Leg 1 + Leg 4

**Status:** Ready to implement  
**Created:** 2026-06-05  
**Predecessor:** [Leg4-renderingData-alignment](../Leg4-renderingData-alignment/00-plan.md)

---

## START HERE (implementing agent)

HTML input templates now contain two distinct `[...]` syntaxes:

| Syntax | Example | What it is |
|---|---|---|
| Loop token (existing) | `[vehicles]...[/vehicles]` | Matched pair, simple identifier, handled by `MUSTACHE_RE` |
| Conditional block (new) | `[prose text with spaces]` | No closer, free-form text, NOT matched by `MUSTACHE_RE` |

Conditional blocks map to Java runtime conditions in the `DocumentDataSnapshotPlugin`. The `.vm` gets a `$doc.condN` variable; the plugin sets it to the text or `""` based on Java conditions. **Conditions are business rules filled by humans — the pipeline only extracts and scaffolds.**

Two new artifacts per Leg 1 run:
- `<stem>.conditional-registry.csv` — id + source_text auto-populated; conditions/operator/notes blank
- `<stem>.conditional-ref.html` — annotated original HTML with `[text]<sup>N</sup>` markers so humans can look up what CSV row N refers to

---

## Read These Files First

1. `.cursor/skills/html-to-velocity/scripts/convert.py` — full Leg 1 script; all changes go here
2. `scripts/leg4_generate_plugin.py` — `JAVA_TEMPLATE` + `render_java()` + `write_report()`
3. `scripts/agent_tools.py` — `_predict_writes()` function
4. `samples/input/Simple-form(quote).html` — the one conditional block currently: line 14

---

## Disambiguation: loop tokens vs conditional blocks

- `MUSTACHE_RE = re.compile(r"\[\s*(/?)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\]")` already exists — matches `[identifier]` / `[/identifier]` only
- Conditional text contains spaces → `MUSTACHE_RE` will never match it
- By the time the new extraction step runs (step 5.5), all loop tokens are already replaced with `#foreach`/`#end` — double safe

---

## Task List

### T1 — convert.py: add regex + helper

Add after the `MUSTACHE_RE` line (~line 64):

```python
COND_BLOCK_RE = re.compile(r'\[([^\[\]\n]{4,})\]')

def _is_loop_token(content: str) -> bool:
    """True if content is a simple identifier — a loop token, not a conditional block."""
    return bool(re.fullmatch(r'/?[a-zA-Z_][a-zA-Z0-9_]*', content.strip()))
```

---

### T2 — convert.py: extend `Mapping` dataclass

Add field to the `Mapping` dataclass (~line 264):

```python
conditional_blocks: list[dict] = field(default_factory=list)
```

Entry shape: `{"id": 1, "source_text": "..."}`

---

### T3 — convert.py: add `extract_conditional_blocks(soup, mapping)`

```python
def extract_conditional_blocks(soup, mapping: Mapping) -> None:
    """Replace [prose text] blocks with $doc.condN; record to mapping.conditional_blocks."""
    counter = len(mapping.conditional_blocks) + 1
    for text_node in list(soup.find_all(string=COND_BLOCK_RE)):
        s = str(text_node)
        new_s = s
        offset = 0
        for m in COND_BLOCK_RE.finditer(s):
            content = m.group(1)
            if _is_loop_token(content):
                continue
            block_id = counter
            counter += 1
            source_text = content.strip()
            mapping.conditional_blocks.append({"id": block_id, "source_text": source_text})
            replacement = f"$doc.cond{block_id}"
            # Adjust for replacements already made in this node
            adj_start = m.start() + offset
            adj_end = m.end() + offset
            new_s = new_s[:adj_start] + replacement + new_s[adj_end:]
            offset += len(replacement) - (m.end() - m.start())
        if new_s != s:
            text_node.replace_with(NavigableString(new_s))
```

---

### T4 — convert.py: add `write_conditional_registry(blocks, csv_path)`

```python
def write_conditional_registry(blocks: list[dict], csv_path: Path) -> None:
    import csv as _csv
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = _csv.writer(f, quoting=_csv.QUOTE_MINIMAL)
        writer.writerow(["id", "source_text", "conditions", "operator", "notes"])
        for b in blocks:
            writer.writerow([b["id"], b["source_text"], "", "", ""])
```

Always writes the file even if `blocks` is empty (header-only CSV is valid).

---

### T5 — convert.py: add `write_conditional_ref_html(original_html, blocks, ref_path)`

```python
def write_conditional_ref_html(original_html: str, blocks: list[dict], ref_path: Path) -> None:
    result = original_html
    for b in blocks:
        needle = f'[{b["source_text"]}]'
        replacement = f'[{b["source_text"]}]<sup>{b["id"]}</sup>'
        result = result.replace(needle, replacement, 1)
    ref_path.write_text(result, encoding="utf-8")
```

---

### T6 — convert.py: wire into `convert()` function

**Insert as step 5.5** (between "leftover Mustache token check" and "annotate_loop_hints"):

```python
# Step 5.5 — extract conditional blocks ([prose text] → $doc.condN)
extract_conditional_blocks(soup, mapping)
```

**After computing `target_dir` and `stem`**, add artifact writes before the return:

```python
csv_path = target_dir / f"{stem}.conditional-registry.csv"
write_conditional_registry(mapping.conditional_blocks, csv_path)

ref_path = None
if mapping.conditional_blocks:
    ref_path = target_dir / f"{stem}.conditional-ref.html"
    write_conditional_ref_html(html, mapping.conditional_blocks, ref_path)
```

**In `main()`, after the existing `print(f"Wrote {vm_path}")` lines**, add:

```python
print(f"Wrote {csv_path}")
if ref_path:
    print(f"Wrote {ref_path}  ({len(mapping.conditional_blocks)} conditional blocks)")
```

Make `csv_path` and `ref_path` local variables visible at the `main()` print site. The `convert()` function can return them, or compute the paths in `main()` after the `convert()` call — the latter is simpler (paths are deterministic from `stem` and `out_dir`).

**Recommended approach:** compute paths in `main()` after `convert()` returns, same way `vm_path` etc. are already computed. No signature change to `convert()`.

---

### T7 — leg4_generate_plugin.py: add `load_conditional_registry(csv_path)`

```python
def load_conditional_registry(csv_path: Path) -> list[dict]:
    """Load conditional-registry.csv. Returns [] if absent or empty."""
    import csv as _csv
    if not csv_path.exists():
        return []
    blocks = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        for row in _csv.DictReader(f):
            raw_conds = row.get("conditions", "").strip()
            conditions = [c.strip() for c in raw_conds.split("|") if c.strip()]
            operator = row.get("operator", "").strip().upper() or "AND"
            blocks.append({
                "id": int(row["id"]),
                "source_text": row["source_text"],
                "conditions": conditions,
                "operator": operator,
            })
    return blocks
```

---

### T8 — leg4_generate_plugin.py: add `render_conditional_puts(blocks)`

```python
def render_conditional_puts(blocks: list[dict]) -> str:
    """Generate renderingData.put(...) lines for conditional blocks."""
    if not blocks:
        return ""
    lines = []
    for b in blocks:
        bid = b["id"]
        src = b["source_text"].replace("\\", "\\\\").replace('"', '\\"')
        truncated = b["source_text"][:60] + ("..." if len(b["source_text"]) > 60 else "")
        if b["conditions"]:
            joiner = " || " if b["operator"] == "OR" else " && "
            java_cond = joiner.join(b["conditions"])
            lines.append(
                f'        // Conditional block {bid}: {truncated}\n'
                f'        String cond{bid} = "";\n'
                f'        if ({java_cond}) {{\n'
                f'            cond{bid} = "{src}";\n'
                f'        }}\n'
                f'        renderingData.put("cond{bid}", cond{bid});'
            )
        else:
            lines.append(
                f'        // TODO: fill conditions for cond{bid} in conditional-registry.csv\n'
                f'        // {truncated}\n'
                f'        renderingData.put("cond{bid}", "");'
            )
    return "\n".join(lines)
```

---

### T9 — leg4_generate_plugin.py: add placeholders to `JAVA_TEMPLATE`

In `JAVA_TEMPLATE`, insert `%(quote_conditional_puts)s` after `%(quote_datafetcher_extras)s` and before the `return` statement in the quote handler. Same for `%(policy_conditional_puts)s` in the policy handler.

Exact insertion points:
```java
%(quote_datafetcher_extras)s
%(quote_conditional_puts)s        ← ADD
        return DocumentDataSnapshot.builder()
```

```java
%(policy_datafetcher_extras)s
%(policy_conditional_puts)s       ← ADD
        return DocumentDataSnapshot.builder()
```

---

### T10 — leg4_generate_plugin.py: update `render_java()` signature + body

```python
def render_java(
    product: str,
    suggested_name: str,
    quote_df_calls: list[dict] | None = None,
    policy_df_calls: list[dict] | None = None,
    cond_blocks: list[dict] | None = None,   # ← ADD
) -> str:
    ...
    cond_puts = render_conditional_puts(cond_blocks or [])
    return JAVA_TEMPLATE % {
        ...
        "quote_conditional_puts": ("\n" + cond_puts) if cond_puts else "",
        "policy_conditional_puts": ("\n" + cond_puts) if cond_puts else "",
    }
```

---

### T11 — leg4_generate_plugin.py: auto-discover CSV in `main()`

After `stem` is derived, before `render_java()` is called:

```python
cond_csv = out_dir / f"{stem}.conditional-registry.csv"
cond_blocks = load_conditional_registry(cond_csv)
```

Pass `cond_blocks=cond_blocks` to `render_java()`.

---

### T12 — leg4_generate_plugin.py: add conditional blocks section to `write_report()`

Add after the compile check section:

```python
lines += ["", "---", "", f"## Conditional blocks ({len(cond_blocks)} total)", ""]
if cond_blocks:
    lines += ["| id | source_text | conditions | status |", "|---|---|---|---|"]
    for b in cond_blocks:
        truncated = b["source_text"][:60] + ("..." if len(b["source_text"]) > 60 else "")
        status = "wired" if b["conditions"] else "TODO"
        conds = " \\| ".join(b["conditions"]) if b["conditions"] else "(empty)"
        lines.append(f"| {b['id']} | {truncated} | `{conds}` | **{status}** |")
else:
    lines.append("_No conditional-registry.csv found alongside this .suggested.yaml._")
lines += [""]
```

Update `write_report()` signature to accept `cond_blocks: list[dict]`.

---

### T13 — agent_tools.py: update `_predict_writes()`

In the Leg 1 block (~line 176), after the existing `writes +=` for `.vm`, `.mapping.yaml`, `.report.md`:

```python
writes += [
    f"{base}/{stem}.conditional-registry.csv",
    f"{base}/{stem}.conditional-ref.html",
]
```

---

## CSV format (for reference)

```csv
id,source_text,conditions,operator,notes
1,"this is some boiler plate text that will be included if the coverage selected is breakdown",,,
```

Human fills `conditions` with pipe-delimited Java expressions once business rules are known:
```csv
1,"this is some boiler plate text...",policy.getCoverage("breakdown") != null,AND,from underwriting
```

---

## Verification Steps

**Step 1 — Leg 1 produces new artifacts:**
```bash
python3 scripts/agent.py --yes "RUN_PIPELINE leg1 input=samples/input/Simple-form(quote).html output=samples/output"
```
Verify:
- `samples/output/Simple-form(quote)/Simple-form(quote).conditional-registry.csv` — 1 row, source_text is the boilerplate sentence, conditions/operator/notes empty
- `samples/output/Simple-form(quote)/Simple-form(quote).conditional-ref.html` — open in browser; `<sup>1</sup>` appears after `[...text...]`
- `samples/output/Simple-form(quote)/Simple-form(quote).vm` — contains `$doc.cond1` where the `[...]` was; the always-included text is still present after it

**Step 2 — Leg 4 generates TODO stub when conditions blank:**
```bash
python3 scripts/leg4_generate_plugin.py \
  --suggested samples/output/Simple-form(quote)/Simple-form(quote).suggested.yaml \
  --compile-check
```
Verify:
- Java has `renderingData.put("cond1", "");` with a TODO comment
- `plugin-report.md` has a "Conditional blocks" section showing 1 TODO block
- Compile check passes

**Step 3 — Leg 4 generates wired if-block when conditions present:**
Manually edit the CSV to add: `1,"...",policy.getCoverage("breakdown") != null,AND,test`

Re-run Leg 4. Verify:
- Java has `if (policy.getCoverage("breakdown") != null) { cond1 = "..."; }` in both handlers
- `plugin-report.md` shows 1 wired block
- Compile check passes (or fails only on existing issues)

**Step 4 — Full pipeline regression check:**
```bash
python3 scripts/agent.py --yes "RUN_PIPELINE leg1+leg2+leg3+leg4 input=samples/input/Simple-form(quote).html registry=registry/path-registry.yaml output=samples/output"
```
All legs complete; existing fields still resolve; new CSV + ref HTML present.
