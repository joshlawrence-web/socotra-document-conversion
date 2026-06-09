# History — Leg 0 Document Ingestion

Append-only. One entry per session. Most recent at top.

---

## 2026-06-08 — Implementation complete

All tasks I-T1 through I-T6 implemented in a single session.

- Created `scripts/leg0_ingest.py` with full CLI, `convert_docx()`, `convert_pdf()`,
  `write_output()`, and `_escape()` helper.
- Word path: iterates `doc.element.body` in document order, handles paragraphs
  (heading styles → `<h1>`/`<h2>`, bold-only → `<strong>`, normal → `<p>`, empty skipped)
  and tables → `<table><tr><td>`.
- PDF path: per-page table extraction first (pdfplumber), then char-level text grouping
  by top-coordinate into lines; heading heuristic (line avg height > page avg * 1.2 → `<h2>`);
  fallback to `page.extract_text()` on exception.
- Error handling: `.doc` → clear upgrade instruction; unknown extension; file not found;
  import failure with install instructions.  Exit 0/1.
- Added `python-docx>=1.1` and `pdfplumber>=0.11` to `requirements.txt`.

Successor plan (`Leg0-extraction-pipeline-wiring`) is ready to begin.

---

## 2026-06-08 — Plan created

Plan drafted from guided discovery session. Decisions I1–I8 locked. Tasks I-T1 through
I-T6 defined. No implementation started.
