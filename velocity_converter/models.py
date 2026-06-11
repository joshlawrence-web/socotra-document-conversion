"""Typed contract models + boundary validation for pipeline YAML artifacts.

docs/SCHEMA.md remains the authoritative prose contract; each model's
docstring cites the SCHEMA.md section it implements. Models are
**validators, not data carriers**: read boundaries validate the loaded
dict and pass the *original* dict downstream; write boundaries validate
the dict about to be dumped and then dump that same dict. Output bytes
are never produced from a model, so pydantic can never reorder keys.

All models allow unknown keys (``extra="allow"``) per the SCHEMA.md
compatibility rule: unrecognised keys are always preserved verbatim.
Required fields are identity keys only; everything else is optional with
defaults so partial documents (test fixtures, hand-authored mappings)
validate cleanly.

Enum strictness is deliberately conservative: ``Literal`` is used only
for vocabularies that are closed in code (``quantifier``/``cardinality``
from extract_paths). Sets that look closed in SCHEMA.md but drift in real
artifacts (``match_step: old-format``, ``confidence: none``) stay ``str``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, RootModel, ValidationError, field_validator

M = TypeVar("M", bound=BaseModel)

_SCHEMA_DOC = "docs/SCHEMA.md"


class ContractError(RuntimeError):
    """A pipeline artifact failed its contract (version or structure)."""


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# mapping.yaml (v1.0) — SCHEMA.md "Artifact: <stem>.mapping.yaml"
# ---------------------------------------------------------------------------


class VariableContext(_ContractModel):
    """Leg 1 extraction context. All keys optional (SCHEMA.md context table)."""

    parent_tag: str | None = None
    nearest_label: str | None = None
    line: int | None = None
    loop: str | None = None
    loop_hint: str | None = None
    column_header: str | None = None
    container: str | None = None
    detection: str | None = None


class Candidate(_ContractModel):
    """Root-independent match (suggested 2.0). match_step is open vocab —
    real artifacts carry values like ``old-format`` beyond the documented set."""

    path: str = ""
    match_step: str = ""
    registry_field: str | None = None


class Verdict(_ContractModel):
    """Per-root grading (suggested 2.0). confidence/sdk_status open vocab —
    real artifacts carry ``confidence: none``."""

    data_source: str = ""
    confidence: str = ""
    sdk_status: str = ""
    sibling_hint: str | None = None
    reasoning: str = ""


class MappingVariable(_ContractModel):
    """SCHEMA.md "Variable entry" (1.0) + optional 2.0 enrichment keys."""

    name: str
    placeholder: str = ""
    type: str = "variable"
    context: VariableContext | None = None
    data_source: str = ""
    # Suggested 2.0 enrichment (absent in 1.0 docs):
    candidate: Candidate | None = None
    verdicts: dict[str, Verdict] = Field(default_factory=dict)


class MappingLoop(MappingVariable):
    """SCHEMA.md "Loop entry"."""

    iterator: str = ""
    detection: str = ""
    fields: list[MappingVariable] = Field(default_factory=list)


class RenderingRoot(_ContractModel):
    """SCHEMA.md "rendering_roots" (suggested 2.0)."""

    id: str
    java_type: str | None = None
    request: str = ""
    primary: bool = False


class MappingDoc(_ContractModel):
    """SCHEMA.md "Artifact: <stem>.mapping.yaml" (1.0)."""

    schema_version: str = "1.0"
    source: str = ""
    generated_at: str = ""
    variables: list[MappingVariable] = Field(default_factory=list)
    loops: list[MappingLoop] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SuggestedDoc(MappingDoc):
    """SCHEMA.md "Artifact: <stem>.suggested.yaml" (2.0) — Leg 2 enriched
    mapping. Superset of MappingDoc with v1-safe defaults, so legs 3/4 can
    validate either shape against this one model."""

    run_id: str = ""
    input_mapping_sha256: str = ""
    input_registry_sha256: str = ""
    input_mapping_version: str = ""
    input_registry_version: str = ""
    registry_schema_version: str = ""
    registry_generated_at: str = ""
    registry_config_dir: str = ""
    registry_source_config_sha256: str | None = None
    live_source_config_sha256: str | None = None
    registry_config_verified: bool | None = None
    registry_config_check: str = ""
    product: str = ""
    path_registry: str = ""
    rendering_roots: list[RenderingRoot] = Field(default_factory=list)
    tooling: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# path-registry.yaml (v1.1) — SCHEMA.md "Artifact: path-registry.yaml"
# ---------------------------------------------------------------------------

Quantifier = Literal["", "!", "?", "+", "*"]
Cardinality = Literal["exactly_one", "exactly_one_auto", "zero_or_one", "one_or_more", "any"]


class ScopeRequirement(_ContractModel):
    """One ``#foreach`` step in a requires_scope chain."""

    iterator: str = ""
    foreach: str = ""


class RegistryEntry(_ContractModel):
    """SCHEMA.md "Entry keys" (registry 1.1). ``category`` is open vocab
    (system/account/policy_data/… plus charge categories premium/tax/fee/...)."""

    field: str
    display_name: str = ""
    type: str = ""
    base_type: str = ""
    quantifier: Quantifier = ""
    cardinality: Cardinality | Literal[""] = ""
    iterable: bool = False
    category: str = ""
    velocity: str = ""
    requires_scope: list[ScopeRequirement] = Field(default_factory=list)
    options: list | None = None
    custom_type_ref: str | None = None
    # DataFetcher entries (source: datafetcher) — structural only; semantic
    # checks stay in leg2_fill_mapping._validate_datafetcher_entry.
    source: str | None = None
    datafetcher_method: str | None = None
    # Either a single accessor expression or a per-root map of them.
    datafetcher_arg: str | dict[str, str] | None = None
    datafetcher_key: str | None = None
    valid_roots: list[str] | None = None


class ChargeEntry(_ContractModel):
    """Charge path entry (policy_charges / coverage charges)."""

    name: str
    category: str = ""
    velocity_amount: str = ""
    velocity_object: str = ""
    requires_scope: list[ScopeRequirement] = Field(default_factory=list)


class IterableEntry(_ContractModel):
    """SCHEMA.md "iterables" index entry."""

    name: str
    display_name: str = ""
    kind: str = ""
    list_velocity: str = ""
    iterator: str = ""
    foreach: str = ""
    quantifier: Quantifier = ""
    cardinality: Cardinality | Literal[""] = ""


class CoverageEntry(_ContractModel):
    """Coverage block under an exposure."""

    name: str
    display_name: str = ""
    velocity: str = ""
    quantifier: Quantifier = ""
    cardinality: Cardinality | Literal[""] = ""
    iterable: bool = False
    note: str | None = None
    requires_scope: list[ScopeRequirement] = Field(default_factory=list)
    fields: list[RegistryEntry] = Field(default_factory=list)
    charges: list[ChargeEntry] = Field(default_factory=list)


class ExposureEntry(_ContractModel):
    """Exposure block (Vehicle, Item, …)."""

    name: str
    display_name: str = ""
    list_velocity: str = ""
    iterator: str = ""
    foreach: str = ""
    raw_contents: list | None = None
    quantifier: Quantifier = ""
    cardinality: Cardinality | Literal[""] = ""
    iterable: bool = False
    system_fields: list[RegistryEntry] = Field(default_factory=list)
    fields: list[RegistryEntry] = Field(default_factory=list)
    coverages: list[CoverageEntry] = Field(default_factory=list)
    charges: list[ChargeEntry] = Field(default_factory=list)


class RegistryMeta(_ContractModel):
    """SCHEMA.md registry ``meta`` block."""

    config_dir: str = ""
    product: str = ""
    display_name: str = ""
    generated_at: str = ""
    source_config_sha256: str | None = None
    note: str = ""


class PathRegistry(_ContractModel):
    """SCHEMA.md "Artifact: path-registry.yaml" (1.1)."""

    schema_version: str = "1.1"
    meta: RegistryMeta = Field(default_factory=RegistryMeta)
    feature_support: dict[str, bool] = Field(default_factory=dict)
    iterables: list[IterableEntry] = Field(default_factory=list)
    system_paths: list[RegistryEntry] = Field(default_factory=list)
    quote_paths: list[RegistryEntry] = Field(default_factory=list)
    account_paths: list[RegistryEntry] = Field(default_factory=list)
    policy_data: list[RegistryEntry] = Field(default_factory=list)
    policy_charges: list[ChargeEntry] = Field(default_factory=list)
    exposures: list[ExposureEntry] = Field(default_factory=list)
    datafetcher_paths: list[RegistryEntry] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# conditional-registry.yaml (unversioned) — SCHEMA.md
# "Artifact: <stem>.conditional-registry.yaml"
# ---------------------------------------------------------------------------


class ConditionalBlock(_ContractModel):
    """One customer-confirmed conditional block."""

    id: int
    source_text: str
    operator: str = "AND"
    conditions: list[str] = Field(default_factory=list)
    parent_id: int | None = None
    depth: int = 0

    @field_validator("operator")
    @classmethod
    def _upper_operator(cls, v: str) -> str:
        return (v or "AND").strip().upper() or "AND"

    @field_validator("conditions", mode="before")
    @classmethod
    def _clean_conditions(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(c).strip() for c in v if c is not None and str(c).strip()]


class ConditionalRegistry(RootModel[list[ConditionalBlock]]):
    """List-of-blocks document written by leg0 --parse-conditional-form."""


# ---------------------------------------------------------------------------
# Loader / validation boundary helpers
# ---------------------------------------------------------------------------


def _major(version: str) -> str:
    return version.split(".", 1)[0]


def check_contract_version(
    found: str | None,
    expected: tuple[str, ...],
    *,
    artifact: str,
    path: Path | None = None,
) -> None:
    """Enforce the SCHEMA.md rule: halt on MAJOR mismatch, warn on MINOR drift.

    An absent version is treated as "1.0" (wild artifacts predate versioning;
    the conditional registry has none at all).
    """
    if not expected:
        return
    version = str(found) if found else "1.0"
    majors = {_major(e) for e in expected}
    where = f": {path}" if path else ""
    if _major(version) not in majors:
        understood = ", ".join(sorted(f"{m}.x" for m in majors))
        raise ContractError(
            f"ERROR: {artifact} contract violation{where}\n"
            f"  schema_version {version} is incompatible (this tool understands {understood})\n"
            f"  See {_SCHEMA_DOC}."
        )
    if version not in expected and any(
        _major(version) == _major(e) and version > e for e in expected
    ):
        newest = max(e for e in expected if _major(e) == _major(version))
        print(
            f"WARNING: {artifact} declares schema {version}; this tool was written "
            f"for {newest} — unknown keys will be preserved.",
            file=sys.stderr,
        )


def validate_contract(
    data: object,
    model: type[M],
    *,
    artifact: str,
    path: Path | None = None,
    max_errors: int = 8,
) -> M:
    """Validate ``data`` against ``model``; raise ContractError on failure.

    The returned model is for inspection only — callers keep operating on the
    original dict (see module docstring).
    """
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        where = f": {path}" if path else ""
        lines = [f"ERROR: {artifact} contract violation{where}"]
        for err in exc.errors()[:max_errors]:
            loc = ".".join(str(p) for p in err["loc"]) or "(document)"
            lines.append(f"  - {loc}: {err['msg']}")
        extra = len(exc.errors()) - max_errors
        if extra > 0:
            lines.append(f"  ... and {extra} more")
        lines.append(f'  See {_SCHEMA_DOC}, section "Artifact: {artifact}".')
        raise ContractError("\n".join(lines)) from exc


def load_contract(
    path: Path,
    model: type[M],
    *,
    artifact: str,
    expected_versions: tuple[str, ...] = (),
    strip_comment_header: bool = False,
) -> M:
    """Read + parse + version-check + validate a YAML contract file.

    strip_comment_header drops leading ``#`` lines (leg2 writes a comment
    banner above the suggested YAML; mirrors leg3_substitute._load_yaml).
    """
    text = Path(path).read_text(encoding="utf-8")
    if strip_comment_header:
        body_lines = []
        in_header = True
        for line in text.splitlines():
            if in_header and line.startswith("#"):
                continue
            in_header = False
            body_lines.append(line)
        text = "\n".join(body_lines)
    data = yaml.safe_load(text)
    if isinstance(data, dict):
        check_contract_version(
            data.get("schema_version"), expected_versions, artifact=artifact, path=path
        )
    return validate_contract(data, model, artifact=artifact, path=path)
