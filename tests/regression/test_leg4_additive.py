"""Regression tests — leg4 additive merge (no JARs required)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from leg4_generate_plugin import _append_to_plugin, _diff_keys  # noqa: E402

# Minimal 2-overload plugin fixture — matches the return-marker _append_to_plugin looks for
VALID_PLUGIN_JAVA = """\
public class TestProductDocumentDataSnapshotPluginImpl {

    public DocumentDataSnapshot dataSnapshot(TestProductQuoteRequest request) {
        HashMap<String, Object> renderingData = new HashMap<>();
        renderingData.put("quote", quote);
        renderingData.put("pricing", enhancedPricing);
        renderingData.put("productType", "TestProduct");
        return DocumentDataSnapshot.builder()
                .renderingData(renderingData)
                .build();
    }

    public DocumentDataSnapshot dataSnapshot(TestProductRequest request) {
        HashMap<String, Object> renderingData = new HashMap<>();
        renderingData.put("policy", policy);
        renderingData.put("productType", "TestProduct");
        return DocumentDataSnapshot.builder()
                .renderingData(renderingData)
                .build();
    }
}
"""

# Plugin that already has one DataFetcher key
PLUGIN_WITH_SOME_KEYS = """\
public class TestProductDocumentDataSnapshotPluginImpl {

    public DocumentDataSnapshot dataSnapshot(TestProductQuoteRequest request) {
        HashMap<String, Object> renderingData = new HashMap<>();
        renderingData.put("quote", quote);
        renderingData.put("existingKey", "something");
        return DocumentDataSnapshot.builder()
                .renderingData(renderingData)
                .build();
    }

    public DocumentDataSnapshot dataSnapshot(TestProductRequest request) {
        HashMap<String, Object> renderingData = new HashMap<>();
        renderingData.put("policy", policy);
        renderingData.put("existingKey", "something");
        return DocumentDataSnapshot.builder()
                .renderingData(renderingData)
                .build();
    }
}
"""

_DF_CALL = {
    "key": "agentInfo",
    "method": "getAgentInfo",
    "arg": "segment.locator()",
    "return_type": "Object",
    "return_fqcn": "",
}


# ---------------------------------------------------------------------------
# _diff_keys — computes which keys / cond IDs are missing
# ---------------------------------------------------------------------------


def test_existing_keys_not_duplicated():
    required = {"key1": "segment", "key2": "segment"}
    missing_vars, _ = _diff_keys(required, existing_keys={"key1"}, cond_high_water=0)
    assert "key1" not in missing_vars
    assert "key2" in missing_vars


def test_empty_existing_all_keys_included():
    required = {"alpha": "segment", "beta": "segment"}
    missing_vars, _ = _diff_keys(required, existing_keys=set(), cond_high_water=0)
    assert set(missing_vars.keys()) == {"alpha", "beta"}


def test_cond_counter_continues_from_high_water():
    required = {"cond1": "cond", "cond2": "cond"}
    _, missing_conds = _diff_keys(required, existing_keys=set(), cond_high_water=5)
    global_ids = {g for _, g in missing_conds}
    assert 6 in global_ids
    assert 7 in global_ids


def test_cond_not_placed_in_missing_vars():
    required = {"cond1": "cond"}
    missing_vars, missing_conds = _diff_keys(required, existing_keys=set(), cond_high_water=0)
    assert "cond1" not in missing_vars
    assert len(missing_conds) == 1


# ---------------------------------------------------------------------------
# _append_to_plugin — modifies the .java file in-place
# ---------------------------------------------------------------------------


def test_new_keys_added(tmp_path):
    java = tmp_path / "TestProductDocumentDataSnapshotPluginImpl.java"
    java.write_text(VALID_PLUGIN_JAVA, encoding="utf-8")
    _append_to_plugin(java, [_DF_CALL], [], [])
    assert 'put("agentInfo"' in java.read_text(encoding="utf-8")


def test_bak_written(tmp_path):
    java = tmp_path / "TestProductDocumentDataSnapshotPluginImpl.java"
    java.write_text(VALID_PLUGIN_JAVA, encoding="utf-8")
    _append_to_plugin(java, [_DF_CALL], [], [])
    bak = java.with_suffix(".java.bak")
    assert bak.exists()
    assert bak.read_text(encoding="utf-8") == VALID_PLUGIN_JAVA


def test_no_modification_if_nothing_to_add(tmp_path):
    java = tmp_path / "TestProductDocumentDataSnapshotPluginImpl.java"
    java.write_text(VALID_PLUGIN_JAVA, encoding="utf-8")
    _append_to_plugin(java, [], [], [])
    assert not (java.with_suffix(".java.bak")).exists()
    assert java.read_text(encoding="utf-8") == VALID_PLUGIN_JAVA


def test_plugin_with_some_keys_keeps_existing(tmp_path):
    java = tmp_path / "TestProductDocumentDataSnapshotPluginImpl.java"
    java.write_text(PLUGIN_WITH_SOME_KEYS, encoding="utf-8")
    _append_to_plugin(java, [_DF_CALL], [], [])
    content = java.read_text(encoding="utf-8")
    assert 'put("agentInfo"' in content
    assert 'put("existingKey"' in content


def test_empty_existing_plugin_gets_new_key(tmp_path):
    # Plugin with 0 DataFetcher keys — additive should add all
    java = tmp_path / "TestProductDocumentDataSnapshotPluginImpl.java"
    java.write_text(VALID_PLUGIN_JAVA, encoding="utf-8")
    _append_to_plugin(java, [_DF_CALL], [], [])
    assert 'put("agentInfo"' in java.read_text(encoding="utf-8")
