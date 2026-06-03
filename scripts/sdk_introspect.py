#!/usr/bin/env python3
"""Shared SDK introspection — the single source of compiled-JAR truth.

Factored out of ``scripts/leg4_generate_plugin.py`` (Leg 2 plan P1.1/P1.2) so
that **Leg 2** (the mapping-suggester / confidence rater) and **Leg 4** (the
plugin generator) decide "does this ``$data.*`` path exist on the rendering
root?" the *same* way and cannot drift.

The authority is the compiled ``build/*.jar`` set, read via ``javap`` — not the
config-only ``registry/path-registry.yaml`` (Leg 2 plan D1). A document renders
against the concrete Java type named in its filename brackets
(``<stem>(<root>).html`` — D2); the reachable type differs per root:

    quote   → com.socotra.deployment.customer.{Product}Quote
    segment → com.socotra.deployment.customer.{Product}Segment
    invoice → (deferred — D5)

The functions ``_javap`` / ``_zero_arg_methods`` / ``_unwrap_type`` /
``validate_path`` / ``_default_datamodel_jar`` are moved here **unchanged in
behaviour**; Leg 4 imports them back. New here: ``roots_for_product``,
``sibling_probe`` and the Leg-2-oriented ``classify_path``.
"""

from __future__ import annotations

import re
import subprocess
from functools import lru_cache
from pathlib import Path

CUSTOMER_PACKAGE = "com.socotra.deployment.customer"
PLUGIN_INTERFACE = f"{CUSTOMER_PACKAGE}.DocumentDataSnapshotPlugin"
INVOICE_REQUEST = "InvoiceDetailsRequest"

# Roots a document may render against (Leg 2 plan §5). Invoice is enumerable in
# the filename but not resolved yet (D5).
ALLOWED_ROOTS: tuple[str, ...] = ("quote", "segment", "invoice")


# ---------------------------------------------------------------------------
# JAR discovery
# ---------------------------------------------------------------------------


def _version_key(jar: Path) -> tuple:
    """Sort key from a core-datamodel-vX.Y.Z.jar filename."""
    m = re.search(r"v(\d+)\.(\d+)\.(\d+)", jar.name)
    return tuple(int(g) for g in m.groups()) if m else (0, 0, 0)


def _default_datamodel_jar(repo_root: Path) -> Path | None:
    """Newest core-datamodel-v*.jar under build/ (excluding sources/javadoc)."""
    build = repo_root / "build"
    candidates = [
        j for j in build.glob("core-datamodel-v*.jar")
        if "-sources" not in j.name and "-javadoc" not in j.name
    ]
    return max(candidates, key=_version_key) if candidates else None


# ---------------------------------------------------------------------------
# JAR introspection via javap
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def _javap(classpath: str, fqcn: str, public_only: bool = True) -> tuple[int, str]:
    """Run javap on a class; return (returncode, stdout). $ marks nested types.

    Memoised per (classpath, fqcn) within a process — Leg 2 walks the same root
    types repeatedly (plan §10 "Caching")."""
    cmd = ["javap", "-classpath", classpath]
    if public_only:
        cmd.append("-public")
    cmd.append(fqcn)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def _class_exists(classpath: str, fqcn: str) -> bool:
    rc, _ = _javap(classpath, fqcn)
    return rc == 0


_ZERO_ARG_METHOD_RE = re.compile(
    r"^\s*public\s+(?:static\s+|final\s+|abstract\s+|default\s+)*"
    r"(?:<[^>]*>\s+)?"
    r"([\w.$<>?,\s]+?)\s+"   # return type
    r"(\w+)\(\s*\)\s*;"      # zero-arg method name
)


@lru_cache(maxsize=None)
def _zero_arg_methods(classpath: str, fqcn: str) -> dict[str, str]:
    """Map {methodName: returnTypeString} for public zero-arg accessors.

    When a name has covariant/bridge overloads (e.g. record `data()`), prefer
    the most specific (non java.lang.Object) return type.
    """
    rc, out = _javap(classpath, fqcn)
    methods: dict[str, str] = {}
    if rc != 0:
        return methods
    for line in out.splitlines():
        m = _ZERO_ARG_METHOD_RE.match(line)
        if not m:
            continue
        ret, name = m.group(1).strip(), m.group(2)
        if name in methods and methods[name] != "java.lang.Object":
            continue  # keep the more specific return type already recorded
        methods[name] = ret
    return methods


def _unwrap_type(ret: str) -> str | None:
    """Strip Optional<>/Collection<>/List<> wrappers; return inner FQCN or None
    for primitives / java.lang scalars that cannot be navigated further."""
    inner = ret.strip()
    m = re.match(r"[\w.]*(?:Optional|Collection|List|Set|Iterable)<(.+)>$", inner)
    if m:
        inner = m.group(1).strip()
    inner = re.sub(r"<.*>$", "", inner).strip()
    if "." not in inner or inner.startswith("java."):
        return None
    return inner


def _short_name(fqcn: str) -> str:
    """Human-friendly class name: drop package + outer$nested prefix."""
    return fqcn.rsplit(".", 1)[-1].rsplit("$", 1)[-1]


def _lookup_method(methods: dict[str, str], part: str) -> tuple[str, str] | None:
    """Resolve ``part`` to a (canonicalName, returnType) accessor, matching the
    way Apache Velocity resolves ``$x.Foo`` — case-insensitively against the
    bean property / accessor name. Exact match wins; otherwise the first
    case-insensitive hit. Returns ``None`` if absent.

    Used only by the Leg-2 :func:`classify_path` / :func:`resolve_element_type`;
    the Leg-4 :func:`validate_path` stays strict to preserve its report bytes.
    """
    if part in methods:
        return part, methods[part]
    pl = part.lower()
    for name, ret in methods.items():
        if name.lower() == pl:
            return name, ret
    return None


# ---------------------------------------------------------------------------
# Path validation (report-only, non-fatal — Leg 4 contract, unchanged)
# ---------------------------------------------------------------------------


def validate_path(classpath: str, segment_fqcn: str, data_source: str) -> tuple[str, str]:
    """Walk a `$data.*` path against the segment type. Returns (status, detail)
    where status is 'ok', 'warning', or 'skipped'. Never raises.

    This is the **Leg 4** contract — kept byte-for-byte so the plugin report is
    unchanged. Leg 2 uses the richer :func:`classify_path` instead."""
    src = (data_source or "").strip()
    if not src.startswith("$data"):
        return "skipped", f"not a $data path: {src or '(empty)'}"
    rest = src[len("$data"):].lstrip(".")
    if not rest:
        return "ok", "resolves to renderingData root"
    parts = rest.split(".")
    current = segment_fqcn
    for i, part in enumerate(parts):
        methods = _zero_arg_methods(classpath, current)
        if not methods:
            return "warning", f"could not introspect {current}"
        if part not in methods:
            short = _short_name(current)
            return "warning", f"{short} has no method {part}()"
        ret = methods[part]
        if i == len(parts) - 1:
            return "ok", f"{part}() → {ret}"
        nxt = _unwrap_type(ret)
        if nxt is None:
            return "warning", f"{part}() returns {ret}; cannot navigate to '{parts[i + 1]}'"
        current = nxt
    return "ok", "resolved"


# ---------------------------------------------------------------------------
# Rendering-root resolution (Leg 2 plan §5, D3)
# ---------------------------------------------------------------------------


def request_fqcn(request_simple: str) -> str:
    """Nested FQCN for a plugin request type, e.g. ItemCareRequest →
    com...DocumentDataSnapshotPlugin$ItemCareRequest."""
    return f"{PLUGIN_INTERFACE}${request_simple}"


def roots_for_product(product: str, root_ids: list[str]) -> list[dict]:
    """Resolve declared root ids to {id, java_type, request} descriptors using
    the naming convention shared with Leg 4 (plan D3).

    ``java_type`` is ``None`` for invoice (deferred — D5). Order is preserved;
    callers mark the first as primary.
    """
    out: list[dict] = []
    for rid in root_ids:
        if rid == "quote":
            out.append({
                "id": "quote",
                "java_type": f"{CUSTOMER_PACKAGE}.{product}Quote",
                "request": f"{product}QuoteRequest",
            })
        elif rid == "segment":
            out.append({
                "id": "segment",
                "java_type": f"{CUSTOMER_PACKAGE}.{product}Segment",
                "request": f"{product}Request",
            })
        elif rid == "invoice":
            out.append({
                "id": "invoice",
                "java_type": None,
                "request": INVOICE_REQUEST,
            })
        else:
            raise ValueError(f"unknown root id: {rid!r} (allowed: {', '.join(ALLOWED_ROOTS)})")
    return out


def sibling_probe(
    classpath: str, request_fqcn_value: str, root_fqcn: str, field: str
) -> str | None:
    """Look for ``field`` on a sibling reachable from the request type but not on
    the rendering root (plan §5 step 3). Returns a hint like
    ``Policy.policyNumber()`` or ``None``.

    Walks the request's zero-arg accessors (``policy()``, ``transaction()``,
    ``segment()``, …), unwraps each return type, skips the root itself, and
    returns the first sibling whose type declares a zero-arg ``field()``.
    """
    req_methods = _zero_arg_methods(classpath, request_fqcn_value)
    for _accessor, ret in req_methods.items():
        inner = _unwrap_type(ret)
        if inner is None or inner == root_fqcn:
            continue
        hit = _lookup_method(_zero_arg_methods(classpath, inner), field)
        if hit:
            return f"{_short_name(inner)}.{hit[0]}()"
    return None


# ---------------------------------------------------------------------------
# Leg-2 classification — richer than validate_path (plan §6.3)
# ---------------------------------------------------------------------------


def resolve_element_type(classpath: str, root_fqcn: str, list_velocity: str) -> str | None:
    """Resolve a loop's iterator element type from the root (plan §6.4).

    e.g. ``ItemCareSegment`` + ``$data.items`` → ``items()`` returns
    ``Collection<ItemPolicy>`` → element ``...ItemPolicy``. Returns the element
    FQCN, or ``None`` if the list path isn't navigable / isn't a collection.
    """
    src = (list_velocity or "").strip()
    if not src.startswith("$data"):
        return None
    rest = src[len("$data"):].lstrip(".")
    if not rest:
        return None
    parts = rest.split(".")
    current = root_fqcn
    for i, part in enumerate(parts):
        hit = _lookup_method(_zero_arg_methods(classpath, current), part)
        if hit is None:
            return None
        ret = hit[1]
        if i == len(parts) - 1:
            return _unwrap_type(ret)
        nxt = _unwrap_type(ret)
        if nxt is None:
            return None
        current = nxt
    return None


def classify_path(
    classpath: str,
    root_fqcn: str,
    data_source: str,
    request_fqcn_value: str | None = None,
    root_prefix: str = "$data",
) -> tuple[str, str, str | None]:
    """Classify a ``$data.*`` (or other ``root_prefix.*``) candidate against a
    rendering root / iterator element type.

    Returns ``(sdk_status, detail, sibling_hint)`` where ``sdk_status`` is one of
    the plan §6.3 enum: ``verified`` | ``not_found`` | ``sibling_only`` |
    ``not_navigable`` | ``skipped``. ``sibling_hint`` is set only for
    ``sibling_only``. ``root_prefix`` lets loop fields be walked from the
    resolved iterator element type (e.g. ``$item``). Never raises.
    """
    src = (data_source or "").strip()
    if not src.startswith(root_prefix):
        return "skipped", f"no candidate {root_prefix} path ({src or 'empty'})", None
    rest = src[len(root_prefix):].lstrip(".")
    if not rest:
        return "verified", f"resolves to {root_prefix} root", None

    parts = rest.split(".")
    current = root_fqcn
    for i, part in enumerate(parts):
        methods = _zero_arg_methods(classpath, current)
        if not methods:
            return "not_navigable", f"could not introspect {current}", None
        hit = _lookup_method(methods, part)
        if hit is None:
            short = _short_name(current)
            # Sibling probe only makes sense for the first hop off the root.
            if i == 0 and request_fqcn_value:
                sib = sibling_probe(classpath, request_fqcn_value, root_fqcn, part)
                if sib:
                    return (
                        "sibling_only",
                        f"{short} has no {part}(); field exists on sibling {sib}",
                        sib,
                    )
            return "not_found", f"{short} has no {part}()", None
        name, ret = hit
        if i == len(parts) - 1:
            return "verified", f"{name}() → {ret}", None
        nxt = _unwrap_type(ret)
        if nxt is None:
            return (
                "not_navigable",
                f"{name}() returns {ret}; cannot navigate to '{parts[i + 1]}'",
                None,
            )
        current = nxt
    return "verified", "resolved", None
