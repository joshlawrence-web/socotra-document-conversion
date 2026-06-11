"""Validate emit_telemetry records against the frozen suggester-log JSON Schema.

conformance/schemas/suggester-log.schema.json is the authoritative contract
(SCHEMA.md); until now nothing enforced it. Records are derived from the
committed itemcare-jar goldens so the test runs without JARs or prior
pipeline output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

from velocity_converter.emit_telemetry import derive_run  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = REPO / "conformance" / "schemas" / "suggester-log.schema.json"
GOLDEN_DIR = REPO / "conformance" / "fixtures" / "itemcare-jar" / "golden"
SUGGESTED = GOLDEN_DIR / "suggested.yaml"
REGISTRY = GOLDEN_DIR / "path-registry.yaml"


@pytest.fixture(scope="module")
def records():
    assert SUGGESTED.exists() and REGISTRY.exists(), "itemcare-jar goldens missing"
    return derive_run(
        SUGGESTED, REGISTRY,
        run_id="00000000-0000-0000-0000-000000000000",
        ts="2026-01-01T00:00:00Z",
    )


@pytest.fixture(scope="module")
def validator():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def test_every_record_validates(records, validator):
    assert records, "derive_run produced no records"
    for i, record in enumerate(records):
        errors = sorted(validator.iter_errors(record), key=lambda e: list(e.path))
        assert not errors, (
            f"record {i} (kind={record.get('kind')}) violates suggester-log schema:\n"
            + "\n".join(f"  - {'/'.join(map(str, e.path)) or '(root)'}: {e.message}" for e in errors[:5])
        )


def test_exactly_one_summary_record(records):
    kinds = [r.get("kind") for r in records]
    assert kinds.count("summary") == 1
    assert kinds[-1] == "summary"
