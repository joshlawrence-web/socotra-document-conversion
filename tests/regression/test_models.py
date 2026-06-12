"""Unit tests for velocity_converter.models — version gate, defaults, errors."""

from __future__ import annotations

from pathlib import Path

import pytest

from velocity_converter.models import (
    ConditionalBlock,
    ConditionalRegistry,
    ContractError,
    MappingDoc,
    PathRegistry,
    SuggestedDoc,
    check_contract_version,
    load_contract,
    validate_contract,
)


# ---------------------------------------------------------------------------
# Version gate
# ---------------------------------------------------------------------------


def test_major_mismatch_halts():
    with pytest.raises(ContractError) as exc:
        check_contract_version("2.0", ("1.1",), artifact="path-registry.yaml")
    assert "schema_version 2.0 is incompatible" in str(exc.value)
    assert "1.x" in str(exc.value)


def test_minor_ahead_warns_not_halts(capsys):
    check_contract_version("1.2", ("1.1",), artifact="path-registry.yaml")
    assert "WARNING" in capsys.readouterr().err


def test_exact_version_silent(capsys):
    check_contract_version("1.1", ("1.1",), artifact="path-registry.yaml")
    assert capsys.readouterr().err == ""


def test_absent_version_treated_as_1_0():
    check_contract_version(None, ("1.0", "2.0"), artifact="mapping.yaml")
    with pytest.raises(ContractError):
        check_contract_version(None, ("2.0",), artifact="suggested.yaml")


def test_dual_major_tolerance():
    check_contract_version("1.0", ("1.0", "2.0"), artifact="mapping.yaml")
    check_contract_version("2.0", ("1.0", "2.0"), artifact="mapping.yaml")


# ---------------------------------------------------------------------------
# Defaults vs partial documents (mirrors inline test-fixture shapes)
# ---------------------------------------------------------------------------


def test_minimal_mapping_validates():
    doc = MappingDoc.model_validate(
        {"variables": [{"name": "x"}], "loops": []}
    )
    assert doc.variables[0].placeholder == ""
    assert doc.schema_version == "1.0"


def test_minimal_registry_validates():
    reg = PathRegistry.model_validate(
        {"system_paths": [{"field": "policyNumber", "velocity": "$data.policyNumber"}]}
    )
    assert reg.system_paths[0].iterable is False


def test_unknown_keys_preserved():
    doc = MappingDoc.model_validate({"variables": [], "my_custom_key": 42})
    assert doc.model_dump()["my_custom_key"] == 42


def test_suggested_accepts_v1_shape():
    # leg3/leg4 validate both 1.0 and 2.0 docs against SuggestedDoc
    doc = SuggestedDoc.model_validate(
        {"schema_version": "1.0", "variables": [{"name": "a", "data_source": "$data.a"}]}
    )
    assert doc.run_id == ""


# ---------------------------------------------------------------------------
# Conditional registry — the leg4 KeyError fix
# ---------------------------------------------------------------------------


def test_conditional_block_requires_id_and_source_text():
    with pytest.raises(ContractError) as exc:
        validate_contract(
            [{"conditions": ["x != null"]}],
            ConditionalRegistry,
            artifact="conditional-registry.yaml",
        )
    msg = str(exc.value)
    assert "id: Field required" in msg
    assert "source_text: Field required" in msg


def test_conditional_block_normalises():
    block = ConditionalBlock.model_validate(
        {"id": "3", "source_text": "t", "operator": " and ", "conditions": [" a ", "", None]}
    )
    assert block.id == 3
    assert block.operator == "AND"
    assert block.conditions == ["a"]


# ---------------------------------------------------------------------------
# Error rendering
# ---------------------------------------------------------------------------


def test_error_block_format():
    with pytest.raises(ContractError) as exc:
        validate_contract(
            {"system_paths": [{"velocity": "$data.x"}]},
            PathRegistry,
            artifact="path-registry.yaml",
            path=Path("registry/path-registry.yaml"),
        )
    msg = str(exc.value)
    assert msg.startswith("ERROR: path-registry.yaml contract violation: registry/")
    assert "- system_paths.0.field: Field required" in msg
    assert 'See docs/SCHEMA.md, section "Artifact: path-registry.yaml".' in msg


def test_error_truncation():
    bad = {"system_paths": [{"velocity": f"$data.x{i}"} for i in range(12)]}
    with pytest.raises(ContractError) as exc:
        validate_contract(bad, PathRegistry, artifact="path-registry.yaml")
    assert "... and 4 more" in str(exc.value)


# ---------------------------------------------------------------------------
# load_contract
# ---------------------------------------------------------------------------


def test_load_contract_strips_comment_header(tmp_path):
    p = tmp_path / "x.mapping.yaml"
    p.write_text(
        "# banner line\n# another\nschema_version: '1.0'\nvariables: []\nloops: []\n",
        encoding="utf-8",
    )
    doc = load_contract(
        p, MappingDoc, artifact="mapping.yaml",
        expected_versions=("1.0",), strip_comment_header=True,
    )
    assert doc.schema_version == "1.0"


def test_load_contract_version_halt(tmp_path):
    p = tmp_path / "reg.yaml"
    p.write_text("schema_version: '9.0'\n", encoding="utf-8")
    with pytest.raises(ContractError):
        load_contract(
            p, PathRegistry, artifact="path-registry.yaml", expected_versions=("1.1",)
        )


# ---------------------------------------------------------------------------
# leg4 integration — malformed conditional registry yields ContractError
# ---------------------------------------------------------------------------


def test_leg4_load_conditional_registry_clean_error(tmp_path):
    from velocity_converter.leg4_generate_plugin import load_conditional_registry

    bad = tmp_path / "x.conditional-registry.yaml"
    bad.write_text("- conditions: ['a != null']\n  operator: AND\n", encoding="utf-8")
    with pytest.raises(ContractError) as exc:
        load_conditional_registry(bad)
    assert "source_text: Field required" in str(exc.value)
    assert "KeyError" not in str(exc.value)


def test_leg4_load_conditional_registry_valid(tmp_path):
    from velocity_converter.leg4_generate_plugin import load_conditional_registry

    good = tmp_path / "x.conditional-registry.yaml"
    good.write_text(
        "- id: 1\n  source_text: Some text\n  conditions: ['a != null']\n  operator: and\n",
        encoding="utf-8",
    )
    blocks = load_conditional_registry(good)
    assert blocks == [{
        "id": 1, "source_text": "Some text", "parent_id": None,
        "depth": 0, "conditions": ["a != null"], "operator": "AND",
        "render": "plugin",
    }]
