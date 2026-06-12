"""Regression tests for quote-root catalog accessors."""

from __future__ import annotations

from pathlib import Path

from velocity_converter.agent_tools import build_velocity_lookup
from velocity_converter.list_paths import render_catalog

REPO = Path(__file__).resolve().parent.parent.parent
REGISTRY = REPO / "registry" / "path-registry.yaml"


def test_velocity_lookup_maps_quote_accessors_under_quote_root():
    lookup = build_velocity_lookup(REGISTRY)

    assert lookup["quote.quoteNumber"] == "$data.quote.quoteNumber"
    assert lookup["quote.data.coolingOffPeriod"] == "$data.quote.data.coolingOffPeriod"
    assert lookup["quote.data.newBusinessWaitPeriod"] == "$data.quote.data.newBusinessWaitPeriod"


def test_field_catalog_lists_quote_custom_data_paths():
    catalog = render_catalog(str(REGISTRY))

    assert "## Quote Custom Fields" in catalog
    assert "`quote.data.coolingOffPeriod`" in catalog
    assert "`$data.quote.data.coolingOffPeriod`" in catalog
    assert "`$data.quote.quoteNumber`" in catalog
