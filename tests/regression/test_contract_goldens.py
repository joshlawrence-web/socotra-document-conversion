"""Calibration: every real artifact in the repo validates against its model.

Round-trips all conformance goldens, fixture mappings, the live registry,
and any samples/tests pipeline outputs through the contract models. Guards
against over-strict models (a Literal or required field that real artifacts
violate) before any pipeline leg is gated on validation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from velocity_converter.models import (
    ConditionalRegistry,
    MappingDoc,
    PathRegistry,
    SuggestedDoc,
    validate_contract,
)

REPO = Path(__file__).resolve().parent.parent.parent


def _strip_comment_header(text: str) -> str:
    lines = text.splitlines()
    while lines and lines[0].startswith("#"):
        lines.pop(0)
    return "\n".join(lines)


def _load(path: Path):
    return yaml.safe_load(_strip_comment_header(path.read_text(encoding="utf-8")))


def _collect(pattern: str) -> list[Path]:
    return sorted(REPO.glob(pattern))


def _keys_recursive(obj, prefix=""):
    out = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(f"{prefix}{k}")
            out |= _keys_recursive(v, f"{prefix}{k}.")
    elif isinstance(obj, list):
        for item in obj:
            out |= _keys_recursive(item, f"{prefix}[].")
    return out


REGISTRY_FILES = (
    _collect("registry/path-registry.yaml")
    + _collect("conformance/fixtures/*/golden/path-registry.yaml")
)

MAPPING_FILES = _collect("conformance/fixtures/*/mapping.yaml")

SUGGESTED_FILES = (
    _collect("tests/regression/fixtures/*.suggested.yaml")
    + _collect("samples/output/*/*.mapping.yaml")
    + _collect("tests/pipeline/output/*/*.mapping.yaml")
)

COND_REGISTRY_FILES = (
    _collect("samples/output/*/*.conditional-registry.yaml")
    + _collect("tests/pipeline/output/*/*.conditional-registry.yaml")
)


@pytest.mark.parametrize("path", REGISTRY_FILES, ids=lambda p: str(p.relative_to(REPO)))
def test_registry_validates(path):
    data = _load(path)
    model = validate_contract(data, PathRegistry, artifact="path-registry.yaml", path=path)
    assert _keys_recursive(model.model_dump()) >= _keys_recursive(data)


@pytest.mark.parametrize("path", MAPPING_FILES, ids=lambda p: str(p.relative_to(REPO)))
def test_mapping_validates(path):
    data = _load(path)
    model = validate_contract(data, MappingDoc, artifact="mapping.yaml", path=path)
    assert _keys_recursive(model.model_dump()) >= _keys_recursive(data)


@pytest.mark.parametrize("path", SUGGESTED_FILES, ids=lambda p: str(p.relative_to(REPO)))
def test_suggested_validates(path):
    data = _load(path)
    model = validate_contract(data, SuggestedDoc, artifact="suggested.yaml", path=path)
    assert _keys_recursive(model.model_dump()) >= _keys_recursive(data)


@pytest.mark.parametrize(
    "path", COND_REGISTRY_FILES, ids=lambda p: str(p.relative_to(REPO))
)
def test_conditional_registry_validates(path):
    data = _load(path)
    validate_contract(
        data, ConditionalRegistry, artifact="conditional-registry.yaml", path=path
    )


def test_collected_something():
    assert REGISTRY_FILES and MAPPING_FILES and SUGGESTED_FILES
