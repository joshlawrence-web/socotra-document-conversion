# Plan: Nested Conditional Block Extraction

**Status:** Ready to implement
**Created:** 2026-06-05
**Predecessor:** [conditional-blocks](../CompletedPlans/conditional-blocks/00-plan.md)

---

## Context

`extract_conditional_blocks()` currently runs a single pass using `COND_BLOCK_RE = r'\[([^\[\]\n]{4,})\]'`. The `[^\[\]]` char class deliberately excludes nested brackets, so any `[outer [inner] text]` pattern silently fails — the outer wrapper is never extracted. Real insurance rider documents contain multi-level nested optional clauses (e.g., `[, and (2) such Insured has not, [within the last [2-10] years] prior to...]`). This plan replaces the single pass with an N-pass loop (terminates when the document stops changing), adds parent-child linkage via post-processing, and propagates the hierarchy through the CSV and Leg 4 report.

## Key insight

`COND_BLOCK_RE` already matches only innermost brackets (by design). Wrapping it in a loop is sufficient — each iteration peels one nesting layer, innermost-first. After all passes, a post-processing step scans each block's `source_text` for `$doc.condN` references left by prior passes. Any such reference means: "this block is a child of the block whose source_text contains this `$doc.condN` token."

---

## Files to change

1. `.cursor/skills/html-to-velocity/scripts/convert.py` — extraction loop, block dict shape, CSV write, ref HTML rework
2. `scripts/leg4_generate_plugin.py` — CSV load, Java rendering TODO comments, report table
3. `scripts/agent_tools.py` — **no change needed** (`_predict_writes()` already lists the CSV and ref HTML)

---

## T1 — Block dict shape (convert.py)

Extend the appended dict to include `parent_id` and `depth`, defaulting to `None`/`0`:

```python
mapping.conditional_blocks.append({
    "id": block_id,
    "source_text": source_text,
    "parent_id": None,
    "depth": 0,
})
```

---

## T2 — N-pass loop in `extract_conditional_blocks()` (convert.py ~line 1045)

Replace the current single-pass body with a `while True` outer loop. Stop when a full pass finds no new matches.

```python
def extract_conditional_blocks(soup, mapping: Mapping) -> None:
    counter = len(mapping.conditional_blocks) + 1
    while True:
        changed = False
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
                changed = True
                source_text = content.strip()
                mapping.conditional_blocks.append({
                    "id": block_id,
                    "source_text": source_text,
                    "parent_id": None,
                    "depth": 0,
                })
                replacement = f"$doc.cond{block_id}"
                adj_start = m.start() + offset
                adj_end = m.end() + offset
                new_s = new_s[:adj_start] + replacement + new_s[adj_end:]
                offset += len(replacement) - (m.end() - m.start())
            if new_s != s:
                text_node.replace_with(NavigableString(new_s))
        if not changed:
            break
    _link_cond_parents(mapping.conditional_blocks)
```

---

## T3 — Post-processing parent linkage (convert.py — new helper)

Add `_link_cond_parents()` directly after `extract_conditional_blocks()`. Scans each block's `source_text` for `$doc.condN` refs (those are its children), then walks up the parent chain to compute depth.

```python
_COND_REF_RE = re.compile(r'\$doc\.cond(\d+)')

def _link_cond_parents(blocks: list[dict]) -> None:
    id_map = {b["id"]: b for b in blocks}
    for block in blocks:
        for m in _COND_REF_RE.finditer(block["source_text"]):
            child_id = int(m.group(1))
            if child_id in id_map:
                id_map[child_id]["parent_id"] = block["id"]
    for block in blocks:
        depth = 0
        pid = block["parent_id"]
        while pid is not None:
            depth += 1
            pid = id_map.get(pid, {}).get("parent_id")
        block["depth"] = depth
```

---

## T4 — CSV schema update (convert.py `write_conditional_registry()`)

Add `parent_id` and `depth` columns between `source_text` and `conditions`:

```python
writer.writerow(["id", "source_text", "parent_id", "depth", "conditions", "operator", "notes"])
for b in blocks:
    writer.writerow([
        b["id"], b["source_text"],
        b.get("parent_id", ""), b.get("depth", 0),
        "", "", ""
    ])
```

---

## T5 — Rework `write_conditional_ref_html()` (convert.py)

**Problem:** Current implementation searches the original HTML for `[source_text]`. For nested blocks (depth ≥ 1), `source_text` contains `$doc.condN` refs which never appear in the original HTML — search silently fails and those blocks are unannotated.

**Fix:** Annotate the `.vm` text instead of the original HTML. The `.vm` is what humans review anyway. Replace each `$doc.condN` with an annotated version and wrap in a minimal HTML shell.

Update the function signature and implementation:

```python
def write_conditional_ref_html(vm_text: str, blocks: list[dict], ref_path: Path) -> None:
    result = vm_text
    # Replace in reverse-ID order to avoid cond1 matching inside cond10
    for b in sorted(blocks, key=lambda x: x["id"], reverse=True):
        token = f"$doc.cond{b['id']}"
        label = f'$doc.cond<sup title="id={b["id"]} depth={b["depth"]}">{b["id"]}</sup>'
        result = result.replace(token, label)
    ref_path.write_text(
        f"<html><body><pre>{result}</pre></body></html>",
        encoding="utf-8"
    )
```

Update the call site in `convert()`: pass `vm_text` (capture the string written to `vm_path` before writing, or read it back; the latter is simpler since `vm_path` is already written at that point).

---

## T6 — `load_conditional_registry()` in leg4_generate_plugin.py (~line 303)

Add `parent_id` and `depth` to the returned dict:

```python
blocks.append({
    "id": int(row["id"]),
    "source_text": row["source_text"],
    "parent_id": int(row["parent_id"]) if row.get("parent_id") else None,
    "depth": int(row.get("depth") or 0),
    "conditions": conditions,
    "operator": operator,
})
```

---

## T7 — `render_conditional_puts()` in leg4_generate_plugin.py (~line 322)

No nested Java rendering yet — conditions are human-filled, so nesting is their responsibility once they wire the CSV. But for TODO stubs, include a `parent_id` note so the human knows this block must be guarded inside its parent's condition:

```python
parent_note = f" — child of cond{b['parent_id']}, guard inside parent if-block" if b.get("parent_id") else ""
# TODO: fill conditions for cond{bid}{parent_note}
```

Add the same note to wired blocks that have a parent.

---

## T8 — `write_report()` in leg4_generate_plugin.py (~line 387)

Add `depth` and `parent_id` columns to the conditional blocks table:

```
| id | depth | parent_id | source_text | conditions | status |
|---|---|---|---|---|---|
```

---

## Verification

**Step 1 — Flat doc regression (no nesting):**
```bash
python3 scripts/agent.py --yes "RUN_PIPELINE leg1 input=samples/input/Simple-form(quote).html output=samples/output"
```
Verify: CSV has new `parent_id` and `depth` columns, both empty/0. Ref HTML renders `.vm` with `<sup>` markers.

**Step 2 — Nested doc (3 levels):**

Create `samples/input/nested-test.html` with:
```html
<p>[outer [middle [inner text] rest of middle] rest of outer]</p>
```

Run Leg 1. Verify CSV:
```
id,source_text,parent_id,depth,...
1,inner text,,,
2,middle $doc.cond1 rest of middle,1,1,
3,outer $doc.cond2 rest of outer,2,2,
```

**Step 3 — Leg 4 TODO stubs include parent notes:**
```bash
python3 scripts/leg4_generate_plugin.py --suggested samples/output/nested-test/nested-test.suggested.yaml
```
Verify Java TODO comments for `cond2` and `cond3` include `child of condN` notes.
