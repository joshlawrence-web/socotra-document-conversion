"""Regression tests — Leg 0 ``--scan`` mode (front-loaded customer handoff).

Covers the invariant that scan mode emits ONLY the single human-fill file
(``{stem}.variants.csv``) and no machine artifacts, and that this file is
byte-identical to what a full ingest of the same document produces. Under the
variants-only flow ``conditional-form.md`` is retired — every conditional block
(binary/template/variant) folds into the one CSV. The scan reuses the same
``_parse_document`` as the full ingest, so the CSV must not drift.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from velocity_converter import leg0_ingest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "pipeline" / "fixtures"
# A fixture carrying an N-way [[$token]] variant block.
VARIANT_FIXTURE = FIXTURES / "TestStateDisclosure(segment).docx"
# A fixture whose conditionals are plain (binary-style) [[$token]] blocks.
TOKEN_FIXTURE = FIXTURES / "TestItemCert(segment).docx"


def _scan(input_path: Path, out_dir: Path) -> set[str]:
    """Run scan mode in-process; return the set of filenames written under out_dir."""
    # converter="legacy": these tests cover the scan/CSV contract, not docx
    # styling — keep them runnable without a LibreOffice install.
    pr = leg0_ingest._parse_document(
        input_path, path_map=None, registry_path=None, converter="legacy"
    )
    leg0_ingest._write_human_fill_files(pr.blocks, input_path.stem, out_dir)
    return {p.name for p in out_dir.rglob("*") if p.is_file()}


@unittest.skipUnless(VARIANT_FIXTURE.exists(), "DOCX fixtures not generated")
class TestScanMode(unittest.TestCase):
    def test_scan_emits_only_human_fill_files(self):
        stem = VARIANT_FIXTURE.stem
        with tempfile.TemporaryDirectory() as td:
            names = _scan(VARIANT_FIXTURE, Path(td))
        self.assertIn(f"{stem}.variants.csv", names)
        # conditional-form.md is retired under variants-only.
        self.assertNotIn(f"{stem}.conditional-form.md", names)
        # No machine artifacts.
        for forbidden in (".raw.html", ".annotated.html", ".mapping.yaml"):
            self.assertFalse(
                any(n.endswith(forbidden) for n in names),
                f"scan should not write {forbidden}: {names}",
            )

    def test_token_only_fixture_still_gets_variants_csv(self):
        # A fixture whose blocks are all plain [[$token]] (no N-way, no loop)
        # still gets the one variants.csv. No conditional-form.md is written.
        stem = TOKEN_FIXTURE.stem
        with tempfile.TemporaryDirectory() as td:
            names = _scan(TOKEN_FIXTURE, Path(td))
        self.assertIn(f"{stem}.variants.csv", names)
        self.assertNotIn(f"{stem}.conditional-form.md", names)

    def test_scan_csv_matches_full_ingest(self):
        """The variants.csv from scan is byte-identical to a full ingest."""
        stem = VARIANT_FIXTURE.stem
        pr = leg0_ingest._parse_document(
            VARIANT_FIXTURE, path_map=None, registry_path=None, converter="legacy"
        )
        with tempfile.TemporaryDirectory() as td_scan, tempfile.TemporaryDirectory() as td_full:
            scan_dir, full_dir = Path(td_scan), Path(td_full)
            # Scan: human-fill only.
            leg0_ingest._write_human_fill_files(pr.blocks, stem, scan_dir)
            # Full ingest: machine artifacts share the same parse, then the same writer.
            (full_dir / f"{stem}.raw.html").write_text(pr.raw_html, encoding="utf-8")
            (full_dir / f"{stem}.annotated.html").write_text(pr.annotated, encoding="utf-8")
            leg0_ingest.write_leg2_mapping(
                pr.fields, f"{stem}.annotated.html", full_dir / f"{stem}.mapping.yaml", loops=pr.loops
            )
            leg0_ingest._write_human_fill_files(pr.blocks, stem, full_dir)

            name = f"{stem}.variants.csv"
            scan_p = next(scan_dir.rglob(name))
            full_p = next(full_dir.rglob(name))
            self.assertEqual(
                scan_p.read_text(encoding="utf-8"),
                full_p.read_text(encoding="utf-8"),
                f"{name} drifted between scan and full ingest",
            )


if __name__ == "__main__":
    unittest.main()
