"""renderingData-shape splice: rendering-root-entity fields must carry the
entity key the plugin .put()s them under ($data.policy / $data.segment /
$data.quote), never a bare $data.<field> / $data.data.<field>.

Guards the fix where Leg 0 baked the registry's root-relative velocity verbatim,
producing template paths ($data.data.x, $data.policyNumber) that resolve to
nothing at render time. See docs/RenderingDataConfigRelated.md.
"""
from pathlib import Path

from velocity_converter.agent_tools import render_root_velocity as r
from velocity_converter.leg0_ingest import extract_fields

REGISTRY = Path(__file__).resolve().parents[2] / "registry" / "path-registry.yaml"


def test_segment_splits_system_to_policy_custom_to_segment():
    # custom field (typed Segment record)
    assert r("$data.data.contractTermEndDate", "segment") == "$data.segment.data.contractTermEndDate"
    # system field (core Policy)
    assert r("$data.policyNumber", "segment") == "$data.policy.policyNumber"


def test_quote_keeps_everything_on_quote():
    assert r("$data.quoteNumber", "quote") == "$data.quote.quoteNumber"
    assert r("$data.data.coolingOffPeriod", "quote") == "$data.quote.data.coolingOffPeriod"


def test_idempotent_and_foreign_keys_left_alone():
    # already prefixed with an entity key
    assert r("$data.segment.items", "segment") == "$data.segment.items"
    assert r("$data.quote.data.x", "quote") == "$data.quote.data.x"
    # account / DataFetcher name their own key — never re-rooted
    assert r("$data.account.data.email", "segment") == "$data.account.data.email"
    # no root / unknown root -> unchanged
    assert r("$data.data.x", None) == "$data.data.x"
    assert r("$item.data.vin", "segment") == "$item.data.vin"


def test_leg0_extract_fields_applies_split_for_segment():
    if not REGISTRY.is_file():
        return  # registry is the demo's; skip if absent
    html = (
        "<p>{policy.policyNumber}</p>"
        "<p>{policy.data.contractTermEndDate}</p>"
        "<p>{account.data.firstName}</p>"
    )
    by_name = {f["name"]: f["data_source"] for f in extract_fields(
        html, registry_path=str(REGISTRY), rendering_root="segment")}
    assert by_name["policy.policyNumber"] == "$data.policy.policyNumber"
    assert by_name["policy.data.contractTermEndDate"] == "$data.segment.data.contractTermEndDate"
    assert by_name["account.data.firstName"] == "$data.account.data.firstName"  # untouched
