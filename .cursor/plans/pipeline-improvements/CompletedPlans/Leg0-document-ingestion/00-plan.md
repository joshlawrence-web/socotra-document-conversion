# Leg 0 — Document Ingestion (PDF / Word → HTML)

**Status:** Complete  
**Created:** 2026-06-08  
**Successor:** [Leg0-extraction-pipeline-wiring](../Leg0-extraction-pipeline-wiring/00-plan.md)  
**History:** [history.md](./history.md) (append-only)

---

## START HERE (implementing agent)

This plan creates a new standalone script `scripts/leg0_ingest.py` that converts a
customer's source document (PDF or Word) into a rough HTML file suitable for the
existing pipeline.

**Scope of this plan:** document conversion only. Field extraction (`{field_name}`,
`[[conditional]]`) is handled in the successor plan. This plan's output is a single
`.raw.html` file — nothing more.

**Read in this order:**

1. This file — §2 (decisions), §3 (task list)
2. `.cursor/skills/html-to-velocity/scripts/convert.py` — existing Leg 1 HTML parser
   (understand what HTML structure Leg 1 expects as input)
3. `scripts/agent_tools.py` — `run_leg1()` — understand how HTML is passed into pipeline

**Do not** wire the output into the pipeline yet — that is Plan 3.

---

## 1. Background

The pipeline currently requires an HTML file as input. Customers typically have Word
documents (`.docx`) or PDFs. Some customers will convert PDF → Word themselves before
submitting; others will submit PDF directly.

This script handles both. The output is rough HTML — no CSS, no layout fidelity required.
The goal is structural fidelity: paragraphs as `<p>`, tables as `<table>`, headings as
`<h1>`/`<h2>`, line breaks preserved. The pipeline's Leg 1 parser is tolerant of rough HTML.

---

## 2. Decisions

| # | Topic | Decision |
|---|--------|----------|
| I1 | Word library | `python-docx` (`docx` package). Pure Python, no system dependencies, handles `.docx` only (not `.doc`). If `.doc` is submitted, emit a clear error: "Convert to .docx first." |
| I2 | PDF library | `pdfplumber`. Pure Python, no binary dependencies, good text + table extraction. Fallback: emit a warning if layout is complex (multi-column detected). |
| I3 | Layout fidelity | None required. Multi-column PDFs are linearised (top-to-bottom, left-to-right). Images are skipped (emit `<!-- image skipped -->`). |
| I4 | Output filename | `{stem}.raw.html` in `--output-dir` (default: same dir as input). The `.raw.html` suffix distinguishes it from pipeline-processed `.vm` outputs. |
| I5 | Heading detection in PDF | Heuristic: text runs with font size > body average → `<h2>`. Bold-only → `<strong>`. No `<h1>` from PDF (title detection is unreliable). |
| I6 | Table handling | Word: `python-docx` native table iteration → `<table><tr><td>`. PDF: `pdfplumber` table extraction → same HTML shape. If table extraction fails, emit rows as `<p>` with `|` separators. |
| I7 | Encoding | Always write UTF-8. Strip non-UTF-8 bytes from PDF text extraction with `errors='replace'`. |
| I8 | `.doc` (legacy Word) | Not supported. Emit a clear error with instruction to save as `.docx` in Microsoft Word. |

---

## 3. Task list

Check boxes when done; append a handoff to [history.md](./history.md).

---

### [x] I-T1 — Script skeleton + argument parser

**Goal:** Create `scripts/leg0_ingest.py` with:

```
leg0_ingest.py --input <path.docx|path.pdf> [--output-dir <dir>]
```

- Detects format from file extension (`.docx` → Word path, `.pdf` → PDF path)
- Validates input exists
- Resolves output dir (default: input file's parent)
- Stub `convert_docx()` and `convert_pdf()` functions (raise NotImplementedError)

**Files:**
- `scripts/leg0_ingest.py` (new)

---

### [x] I-T2 — Word (.docx) → HTML conversion

**Goal:** Implement `convert_docx(docx_path: Path) -> str` returning HTML string.

Iterate `document.paragraphs` and `document.tables` in document order:

- Paragraph with heading style → `<h1>` or `<h2>` based on level
- Paragraph with bold run only → `<p><strong>text</strong></p>`
- Normal paragraph → `<p>text</p>`
- Empty paragraph → skip
- Table → `<table>` with `<tr>/<td>` for each cell; preserve cell text

Wrap output in `<html><body>...</body></html>`.

**Dependency:** `python-docx` — add to `requirements.txt` if one exists, else note in plan.

**Definition of done:**
- Run against a sample `.docx` — output is valid HTML with structure preserved
- Tables appear as `<table>` elements
- Headings appear as `<h2>` elements

---

### [x] I-T3 — PDF → HTML conversion

**Goal:** Implement `convert_pdf(pdf_path: Path) -> str` returning HTML string.

Use `pdfplumber`:

1. For each page:
   - Extract tables first via `page.extract_tables()` — emit as `<table>`
   - Extract remaining text via `page.extract_text()` — split on newlines → `<p>`
   - Detect headings: if a text line's average char height > page average * 1.2 → `<h2>`
2. Separate pages with `<!-- page break -->`
3. Skip images entirely (`<!-- image skipped -->`)

**Dependency:** `pdfplumber` — note in plan.

**Definition of done:**
- Run against a sample PDF — output is parseable HTML
- Multi-column PDF: text is linearised, no garbled runs

---

### [x] I-T4 — Output writer

**Goal:** Implement `write_output(html: str, input_path: Path, output_dir: Path) -> Path`.

- Filename: `{input_path.stem}.raw.html`
- Write UTF-8
- Print: `Wrote {output_path}`
- Return `output_path`

**Files:**
- `scripts/leg0_ingest.py`

---

### [x] I-T5 — CLI wiring + error handling

**Goal:** Wire `convert_docx` / `convert_pdf` into `main()`. Handle:

- `.doc` extension → print error "Convert to .docx first. Open in Word → Save As → .docx"
- Unknown extension → print error "Unsupported format. Accepted: .docx, .pdf"
- File not found → print error
- `pdfplumber` or `python-docx` import failure → print error with install instruction

Exit code 0 on success, 1 on any error.

**Files:**
- `scripts/leg0_ingest.py`

---

### [x] I-T6 — Dependency documentation

**Goal:** Document required packages. If `requirements.txt` exists, add entries. If not,
create a `requirements-leg0.txt` in the repo root listing:

```
python-docx>=1.1
pdfplumber>=0.11
```

**Files:**
- `requirements-leg0.txt` (new, or update existing `requirements.txt`)

---

## 4. Recommended order

1. **I-T1** — skeleton (unblocks parallel work on T2 and T3)
2. **I-T2** — Word path (higher customer priority, easier to test)
3. **I-T3** — PDF path
4. **I-T4** — output writer
5. **I-T5** — CLI wiring
6. **I-T6** — dependency docs

T2 and T3 can be worked in parallel once T1 is done.

---

## 5. Repo signposting

| Path | Role |
|------|------|
| `scripts/leg0_ingest.py` | New script — created by this plan |
| `.cursor/skills/html-to-velocity/scripts/convert.py` | Existing Leg 1 HTML parser — understand expected input shape |
| `scripts/agent_tools.py` | Will be extended in Plan 3 to call `leg0_ingest.py` |
| `samples/input/` | Place test `.docx` / `.pdf` samples here |

---

## 6. Out of scope for this plan

- `{field_name}` extraction — Plan 3
- `[[conditional]]` extraction — Plan 3
- Pipeline wiring (`agent.py`, `agent_tools.py`) — Plan 3
- CSS or layout fidelity — deferred, iterative
- `.doc` legacy Word format support — deferred
