"""Regression tests — DataFetcher resolution for account custom fields (Option B).

Account custom data is an untyped Map, so it is absent from the schema index and
Leg 2's name-matcher can never reach the registry's getAccount entry. The direct
`account_paths` row and the `datafetcher_paths` row share an identical velocity
path (`$data.account.data.firstName`), so the path alone cannot drive the fetch.

These tests lock in the fix: the meta lookup prefers the DataFetcher entry on
that collision, and Leg 0 stamps a `candidate` block so Leg 4 wires getAccount.
Without it the plugin omits `account` from renderingData and the template NPEs on
`$data.account.*`. No JARs required.
"""

from __future__ import annotations

from pathlib import Path

from velocity_converter.agent_tools import build_velocity_lookup, build_velocity_meta_lookup
from velocity_converter.leg0_ingest import _normalise_for_leg2, extract_fields
from velocity_converter.leg4_generate_plugin import _collect_datafetcher_calls

REPO = Path(__file__).resolve().parent.parent.parent
REGISTRY = REPO / "registry" / "path-registry.yaml"


def test_meta_lookup_prefers_datafetcher_on_velocity_collision():
    """account.data.firstName collides with a phantom direct row — DataFetcher wins."""
    meta = build_velocity_meta_lookup(REGISTRY)

    fn = meta["account.data.firstName"]
    assert fn["source"] == "datafetcher"
    assert fn["datafetcher_method"] == "getAccount"
    assert fn["datafetcher_key"] == "account"
    # Per-root arg map: locator accessor differs by overload.
    assert fn["datafetcher_arg"]["quote"] == "quote.accountLocator()"
    assert fn["datafetcher_arg"]["segment"] == "policy.accountLocator()"


def test_meta_lookup_binding_is_object_level_not_per_field():
    """Any $data.account.* path inherits getAccount — no per-field row needed.

    email/primaryPhone have only a direct account_paths row (no datafetcher_paths
    entry), yet a single getAccount serves them, so they must still resolve to the
    DataFetcher via the account key's object-level spec.
    """
    meta = build_velocity_meta_lookup(REGISTRY)
    for accessor in ("account.data.email", "account.data.primaryPhone"):
        e = meta[accessor]
        assert e["source"] == "datafetcher", accessor
        assert e["datafetcher_method"] == "getAccount", accessor
        assert e["datafetcher_key"] == "account", accessor


def test_meta_lookup_carries_valid_roots():
    """Quote-only fetches (getQuotePricing) declare valid_roots=[quote]."""
    meta = build_velocity_meta_lookup(REGISTRY)
    assert meta["account.data.firstName"]["valid_roots"] == ["quote", "segment"]
    assert meta["pricing.premiumTotal"]["valid_roots"] == ["quote"]


def test_meta_lookup_velocity_matches_string_lookup():
    """The DataFetcher preference must not change the resolved velocity path."""
    lookup = build_velocity_lookup(REGISTRY)
    meta = build_velocity_meta_lookup(REGISTRY)

    for name in ("account.data.firstName", "account.data.lastName", "quote.quoteNumber"):
        assert meta[name]["velocity"] == lookup[name]


def test_non_datafetcher_path_carries_no_wiring():
    """A plain registry path resolves with an empty source (no spurious fetch)."""
    meta = build_velocity_meta_lookup(REGISTRY)
    assert meta["quote.quoteNumber"]["source"] == ""


def test_leg0_stamps_datafetcher_candidate_on_account_field():
    """extract_fields tags account.data.firstName with a DataFetcher candidate."""
    html = "<p>Dear {account.data.firstName} {account.data.lastName},</p>"
    fields = {f["name"]: f for f in extract_fields(html, registry_path=str(REGISTRY))}

    fn = fields["account.data.firstName"]
    assert fn["data_source"] == "$data.account.data.firstName"
    cand = fn.get("candidate")
    assert cand is not None
    assert cand["source"] == "datafetcher"
    assert cand["datafetcher_method"] == "getAccount"
    assert cand["datafetcher_key"] == "account"


def test_leg0_no_candidate_for_plain_path():
    """A non-DataFetcher dotted path gets a data_source but no candidate block."""
    html = "<p>Ref {quote.quoteNumber}</p>"
    fields = {f["name"]: f for f in extract_fields(html, registry_path=str(REGISTRY))}

    qn = fields["quote.quoteNumber"]
    assert qn["data_source"] == "$data.quote.quoteNumber"
    assert "candidate" not in qn


def test_leg4_valid_roots_gate_blocks_wrong_overload():
    """A quote-only fetch (valid_roots=[quote]) is collected for quote, not segment."""
    suggested = {
        "variables": [
            {
                "name": "pricing.premiumTotal",
                "data_source": "$data.pricing.premiumTotal",
                "candidate": {
                    "source": "datafetcher",
                    "datafetcher_method": "getQuotePricing",
                    "datafetcher_arg": "quote.locator()",
                    "datafetcher_key": "pricingX",
                    "valid_roots": ["quote"],
                },
            }
        ]
    }
    # classpath "" → javap unavailable → return type falls back to Object; the
    # gate decision is what we are asserting, not the resolved type.
    assert _collect_datafetcher_calls(suggested, "quote", "") != []
    assert _collect_datafetcher_calls(suggested, "segment", "") == []


def test_leg4_account_fetch_wired_on_both_roots():
    """account (valid_roots=[quote, segment]) is collected for both overloads."""
    suggested = {
        "variables": [
            {
                "name": "account.data.firstName",
                "data_source": "$data.account.data.firstName",
                "candidate": {
                    "source": "datafetcher",
                    "datafetcher_method": "getAccount",
                    "datafetcher_arg": {
                        "quote": "quote.accountLocator()",
                        "segment": "policy.accountLocator()",
                    },
                    "datafetcher_key": "account",
                    "valid_roots": ["quote", "segment"],
                },
            }
        ]
    }
    quote_calls = _collect_datafetcher_calls(suggested, "quote", "")
    seg_calls = _collect_datafetcher_calls(suggested, "segment", "")
    assert quote_calls[0]["arg"] == "quote.accountLocator()"
    assert seg_calls[0]["arg"] == "policy.accountLocator()"


def test_normalise_threads_candidate_into_mapping():
    """The candidate block survives into the leg2-compatible mapping variable."""
    html = "<p>{account.data.firstName} and {quote.quoteNumber}</p>"
    fields = extract_fields(html, registry_path=str(REGISTRY))
    mapping = _normalise_for_leg2(fields, "src.annotated.html")

    by_name = {v["name"]: v for v in mapping["variables"]}
    assert by_name["account.data.firstName"]["candidate"]["source"] == "datafetcher"
    assert "candidate" not in by_name["quote.quoteNumber"]
