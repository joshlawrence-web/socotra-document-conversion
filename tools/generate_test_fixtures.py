#!/usr/bin/env python3
"""
Generate the canonical test DOCX fixtures for the pipeline test suite.

Usage:
    python3 scripts/generate_test_fixtures.py [--out-dir tests/pipeline/fixtures]

Each document uses real registry accessor paths in {field} tokens and
[[conditional]] blocks so Leg 0 + Leg 2 produce high-confidence matches.

Documents:
    TestQuoteSummary(quote).docx      — quote-level fields, 2 conditionals
    TestItemCert(segment).docx        — item/coverage fields, 3 conditionals
    TestRenewalNotice(segment).docx   — policy renewal fields, 3 conditionals
    TestItemsSchedule(segment).docx   — [Item] loop over the items array, 1 conditional
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _require_docx():
    try:
        from docx import Document
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        return Document, Pt, WD_ALIGN_PARAGRAPH
    except ImportError:
        sys.exit(
            "Missing dependency python-docx.\n"
            "Install with: pip install python-docx --break-system-packages"
        )


def _heading(doc, text: str, level: int = 1):
    doc.add_heading(text, level=level)


def _para(doc, text: str, bold: bool = False):
    p = doc.add_paragraph(text)
    if bold:
        for run in p.runs:
            run.bold = True
    return p


def _table_row(table, label: str, value_token: str):
    row = table.add_row()
    row.cells[0].text = label
    row.cells[1].text = value_token


# ---------------------------------------------------------------------------
# Document 1: TestQuoteSummary(quote)
# ---------------------------------------------------------------------------

def _build_quote_summary(doc):
    _heading(doc, "ZenCover Quote Summary")

    _para(doc, "Dear {account.data.firstName} {account.data.lastName},")
    _para(doc, "")
    _para(doc, "Thank you for requesting a quote from ZenCover. "
               "Please review the details below.")
    _para(doc, "")

    _heading(doc, "Quote Details", level=2)
    tbl = doc.add_table(rows=1, cols=2)
    tbl.rows[0].cells[0].text = "Field"
    tbl.rows[0].cells[1].text = "Value"
    _table_row(tbl, "Quote Reference", "{quoteNumber}")
    _table_row(tbl, "Cover Start Date", "{startTime}")
    _table_row(tbl, "Cover End Date", "{endTime}")
    _table_row(tbl, "Jurisdiction", "{jurisdiction}")
    _para(doc, "")

    _heading(doc, "Coverage", level=2)
    _para(doc, "Breakdown Cover is included as standard in your plan.")
    _para(doc, "")
    _para(doc,
          "[[Accidental Damage cover is included in your plan. "
          "Your item is protected against unexpected physical damage.]]")
    _para(doc, "")
    _para(doc,
          "[[Theft cover is included in your plan. "
          "You are protected if your item is lost or stolen.]]")
    _para(doc, "")

    _heading(doc, "Premium Summary", level=2)
    tbl2 = doc.add_table(rows=1, cols=2)
    tbl2.rows[0].cells[0].text = "Charge"
    tbl2.rows[0].cells[1].text = "Amount"
    _table_row(tbl2, "Total Monthly Premium", "{quotePremiumTotal}")
    _table_row(tbl2, "Other Charges", "{quoteOtherTotal}")
    _para(doc, "")

    _para(doc, "This quote is valid for 30 days from the date of issue.")
    _para(doc, "")
    _para(doc, "ZenCover Customer Services")


# ---------------------------------------------------------------------------
# Document 2: TestItemCert(segment)
# ---------------------------------------------------------------------------

def _build_item_cert(doc):
    _heading(doc, "Item Protection Certificate")

    _para(doc, "This certificate confirms the coverage in force for the item detailed below.")
    _para(doc, "")

    _heading(doc, "Policy Details", level=2)
    tbl = doc.add_table(rows=1, cols=2)
    tbl.rows[0].cells[0].text = "Field"
    tbl.rows[0].cells[1].text = "Value"
    _table_row(tbl, "Policy Number", "{policyNumber}")
    _table_row(tbl, "Certificate Holder", "{account.data.firstName} {account.data.lastName}")
    _table_row(tbl, "Email", "{account.data.email}")
    _table_row(tbl, "Phone", "{account.data.primaryPhone}")
    _para(doc, "")

    _heading(doc, "Covered Item", level=2)
    tbl2 = doc.add_table(rows=1, cols=2)
    tbl2.rows[0].cells[0].text = "Field"
    tbl2.rows[0].cells[1].text = "Value"
    _table_row(tbl2, "Item Type", "{item.data.itemTypeCode}")
    _table_row(tbl2, "Purchase Date", "{item.data.purchaseDate}")
    _table_row(tbl2, "Purchase Price", "{item.data.purchasePrice}")
    _table_row(tbl2, "Serial Number", "{item.data.serialNumber}")
    _para(doc, "")

    _heading(doc, "Item Status at Inception", level=2)
    _para(doc,
          "[[This item was confirmed to be within the manufacturer warranty period "
          "at the date of policy inception.]]")
    _para(doc, "")
    _para(doc,
          "[[This item was confirmed to be in full working order "
          "at the date of policy inception.]]")
    _para(doc, "")

    _heading(doc, "Coverage Summary", level=2)
    _para(doc, "Breakdown Cover is included as standard. Labour and parts are covered.")
    _para(doc, "")
    _para(doc,
          "[[Accidental Damage Cover applies to this policy. "
          "Your item is protected against accidental physical damage.]]")
    _para(doc, "")

    _para(doc, "ZenCover Limited")


# ---------------------------------------------------------------------------
# Document 3: TestRenewalNotice(segment)
# ---------------------------------------------------------------------------

def _build_renewal_notice(doc):
    _heading(doc, "Policy Renewal Notice")

    _para(doc, "Dear {account.data.firstName} {account.data.lastName},")
    _para(doc, "")
    _para(doc, "Your ZenCover policy is due for renewal. "
               "Please review the details below.")
    _para(doc, "")

    _heading(doc, "Renewal Details", level=2)
    tbl = doc.add_table(rows=1, cols=2)
    tbl.rows[0].cells[0].text = "Field"
    tbl.rows[0].cells[1].text = "Value"
    _table_row(tbl, "Policy Number", "{policyNumber}")
    _table_row(tbl, "Current Policy End Date", "{policy.data.contractTermEndDate}")
    _table_row(tbl, "Renewal Date", "{policy.data.expectedRenewalDate}")
    _para(doc, "")

    _heading(doc, "Renewal Charges", level=2)
    tbl2 = doc.add_table(rows=1, cols=2)
    tbl2.rows[0].cells[0].text = "Charge"
    tbl2.rows[0].cells[1].text = "Amount"
    _table_row(tbl2, "Total Renewal Amount", "{termChargesTotal}")
    _table_row(tbl2, "Settlement Period", "{policy.data.settlementPeriod}")
    _para(doc, "")

    _heading(doc, "Discounts and Adjustments", level=2)
    _para(doc,
          "[[A loyalty discount of {policy.data.discountAmount} has been applied "
          "to your renewal premium (discount type: {policy.data.discountType}).]]")
    _para(doc, "")

    _heading(doc, "Your Rights", level=2)
    _para(doc,
          "[[A cooling-off period applies to this renewal. "
          "You have the right to cancel within the cooling-off window.]]")
    _para(doc, "")
    _para(doc,
          "[[A grace period may apply if your renewal payment is not received "
          "by the due date. Please contact us for details.]]")
    _para(doc, "")

    _para(doc, "Thank you for choosing ZenCover.")
    _para(doc, "")
    _para(doc, "ZenCover Customer Services")


# ---------------------------------------------------------------------------
# Document 4: TestItemsSchedule(segment) — [Item] loop over the items array
# ---------------------------------------------------------------------------

def _build_items_schedule(doc):
    _heading(doc, "Covered Items Schedule")

    _para(doc, "Dear {account.data.firstName} {account.data.lastName},")
    _para(doc, "")
    _para(doc, "The items covered under your ZenCover policy are listed below.")
    _para(doc, "")

    _heading(doc, "Your Covered Items", level=2)
    # [Item]/[/Item] rows mark the repeating section — Leg 0 turns them into
    # a #foreach scaffold so each item renders one row; the header stays once.
    tbl = doc.add_table(rows=1, cols=4)
    tbl.rows[0].cells[0].text = "Item Type"
    tbl.rows[0].cells[1].text = "Purchase Date"
    tbl.rows[0].cells[2].text = "Purchase Price"
    tbl.rows[0].cells[3].text = "Serial Number"
    tbl.add_row().cells[0].text = "[Item]"
    row = tbl.add_row()
    row.cells[0].text = "{item.data.itemTypeCode}"
    row.cells[1].text = "{item.data.purchaseDate}"
    row.cells[2].text = "{item.data.purchasePrice}"
    row.cells[3].text = "{item.data.serialNumber}"
    tbl.add_row().cells[0].text = "[/Item]"
    _para(doc, "")

    _heading(doc, "Coverage Notes", level=2)
    _para(doc, "Breakdown Cover is included as standard for every listed item.")
    _para(doc, "")
    _para(doc,
          "[[Accidental Damage Cover applies to the items listed above. "
          "Each item is protected against unexpected physical damage.]]")
    _para(doc, "")

    _para(doc, "ZenCover Limited")


# ---------------------------------------------------------------------------
# Document 5: TestGiftSchedule(segment) — [Item] loop inside a [[conditional]]
# ---------------------------------------------------------------------------

def _build_gift_schedule(doc):
    _heading(doc, "Promotional Gift Schedule")

    _para(doc, "Dear {account.data.firstName} {account.data.lastName},")
    _para(doc, "")

    # The whole gift section (including the repeating item list) only appears
    # when the condition holds — Leg 0 flips this block to render: template
    # (#if guard stays in the .vm; the plugin puts the condition as a Boolean).
    _para(doc, "[[The following promotional gift items are included with your policy:")
    _para(doc, "[Item]")
    _para(doc, "Gift: {item.data.itemTypeCode} valued at {item.data.purchasePrice}")
    _para(doc, "[/Item]")
    _para(doc, "Gift items are subject to availability.]]")
    _para(doc, "")

    _para(doc, "[[Theft cover is included in your plan.]]")
    _para(doc, "")
    _para(doc, "ZenCover Limited")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

FIXTURES = [
    ("TestQuoteSummary(quote).docx", _build_quote_summary),
    ("TestItemCert(segment).docx", _build_item_cert),
    ("TestRenewalNotice(segment).docx", _build_renewal_notice),
    ("TestItemsSchedule(segment).docx", _build_items_schedule),
    ("TestGiftSchedule(segment).docx", _build_gift_schedule),
]


def generate(out_dir: Path) -> list[Path]:
    Document, Pt, _ = _require_docx()
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for filename, builder in FIXTURES:
        doc = Document()
        builder(doc)
        dest = out_dir / filename
        doc.save(str(dest))
        print(f"  wrote {dest}")
        written.append(dest)
    return written


def main():
    parser = argparse.ArgumentParser(description="Generate pipeline test fixture DOCX files.")
    parser.add_argument(
        "--out-dir",
        default="tests/pipeline/fixtures",
        help="Directory to write fixture files (default: tests/pipeline/fixtures)",
    )
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    print(f"Generating test fixtures → {out_dir}/")
    written = generate(out_dir)
    print(f"\nDone — {len(written)} fixture(s) written.")


if __name__ == "__main__":
    main()
