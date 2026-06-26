#!/usr/bin/env python3
"""Condition DSL — small grammar, validate early, codegen from structure.

The remaining raw-string path through the pipeline was conditions: a customer's
``Condition:`` line landed verbatim in the registry and a pair of regexes in
Leg 4 turned it into Java that did not always compile (bare identifiers), used
String reference-equality (``==``), and never null-stepped. This module replaces
that path with a parse → validate → codegen pipeline shared by binary ``[[…]]``
blocks and the N-way variant blocks (the 50-state feature).

Grammar (no dependency, ~one screen)::

    condition := comparison (("and" | "or") comparison)*
    comparison := path op literal?
    path       := identifier ("." identifier)*
    op         := == | != | >= | <= | > | < | present | absent | in
    literal    := string | number | boolean | "[" literal ("," literal)* "]"

``and``/``or`` may not be mixed in a single condition (mirrors the registry's
single ``operator`` field). ``present``/``absent`` take no literal; ``in`` takes
a bracketed list.

Three public entry points:

- :func:`parse_condition` — text → :class:`ConditionAST` (raises
  :class:`ConditionError` on bad syntax).
- :func:`validate_condition` — AST vs path-registry (+ optional javap walk):
  path exists, root legal for the block's scope, leaf type vs literal type.
  Returns a list of human-readable error strings (empty == valid).
- :func:`condition_to_java` — AST → one boolean Java expression: null-safe
  accessor stepping, ``Objects.equals`` for equality (enum/String safe),
  ``compareTo`` for ordering, ``present``/``absent`` → null checks, ``in`` →
  ``List.of(...).contains(...)``.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# AST
# ---------------------------------------------------------------------------

# Comparison operators that take a single literal operand.
_VALUE_OPS = {"==", "!=", ">", ">=", "<", "<="}
# Operators that take no operand.
_UNARY_OPS = {"present", "absent"}
# Operator that takes a bracketed list.
_IN_OP = "in"
ALL_OPS = _VALUE_OPS | _UNARY_OPS | {_IN_OP}

# Ordering operators (need compareTo, not Objects.equals).
_ORDER_OPS = {">", ">=", "<", "<="}


class ConditionError(ValueError):
    """A condition string failed to parse (bad syntax / unknown operator)."""


@dataclass
class Comparison:
    """One ``<path> <op> <literal?>`` triple.

    value is ``None`` for present/absent, a list for ``in``, else a scalar
    (str/int/float/bool). raw keeps the source slice for debuggability.
    """

    path: str
    op: str
    value: object = None
    raw: str = ""


@dataclass
class ConditionAST:
    """A condition: one or more comparisons joined by a single AND/OR."""

    comparisons: list[Comparison] = field(default_factory=list)
    join: str = "AND"  # "AND" | "OR"
    raw: str = ""


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
      (?P<ws>\s+)
    | (?P<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
    | (?P<op>==|!=|>=|<=|>|<)
    | (?P<lbrack>\[)
    | (?P<rbrack>\])
    | (?P<comma>,)
    | (?P<number>-?\d+(?:\.\d+)?)
    | (?P<ident>[A-Za-z_][\w.]*)
    """,
    re.VERBOSE,
)


@dataclass
class _Tok:
    kind: str
    text: str
    pos: int


def _tokenize(text: str) -> list[_Tok]:
    toks: list[_Tok] = []
    i = 0
    n = len(text)
    while i < n:
        m = _TOKEN_RE.match(text, i)
        if not m:
            raise ConditionError(f"unexpected character {text[i]!r} at position {i} in {text!r}")
        i = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        toks.append(_Tok(kind, m.group(), m.start()))
    return toks


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_KEYWORD_OPS = {"present", "absent", "in"}
_JOINS = {"and": "AND", "or": "OR"}


def _parse_literal_token(tok: _Tok) -> object:
    if tok.kind == "string":
        body = tok.text[1:-1]
        # Unescape the two sequences the tokeniser allowed.
        return body.replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")
    if tok.kind == "number":
        return float(tok.text) if ("." in tok.text) else int(tok.text)
    if tok.kind == "ident":
        low = tok.text.lower()
        if low == "true":
            return True
        if low == "false":
            return False
        if low in ("null", "nil", "none"):
            raise ConditionError(
                "use `present`/`absent` for null checks, not `!= null` "
                "(e.g. `quote.quoteNumber present`)"
            )
        raise ConditionError(f"expected a literal, found bare word {tok.text!r}")
    raise ConditionError(f"expected a literal, found {tok.text!r}")


# Forgiving normalisation: `x != null` ≡ `x present`, `x == null` ≡ `x absent`.
# Authors (and most other DSLs) reach for ==/!= against null; rather than reject
# with a teaching error, rewrite to the canonical unary form. A quoted "null"
# is left alone — the `"` sits between the operator and the word, so `==\s*null`
# never matches it.
_NULLCHECK_RE = re.compile(r"(==|!=)\s*(?:null|nil|none)\b", re.IGNORECASE)


def _normalize_nullchecks(text: str) -> str:
    return _NULLCHECK_RE.sub(
        lambda m: " present" if m.group(1) == "!=" else " absent", text
    )


def parse_condition(text: str) -> ConditionAST:
    """Parse one condition string into a :class:`ConditionAST`.

    Raises :class:`ConditionError` on any syntax error (unknown operator,
    missing operand, mixed and/or, trailing junk). ``x != null`` / ``x == null``
    are forgivingly rewritten to ``x present`` / ``x absent`` first.
    """
    raw = _normalize_nullchecks((text or "").strip())
    if not raw:
        raise ConditionError("empty condition")
    toks = _tokenize(raw)
    pos = 0
    comparisons: list[Comparison] = []
    join: str | None = None

    def peek() -> _Tok | None:
        return toks[pos] if pos < len(toks) else None

    while True:
        start_pos = pos
        # path
        t = peek()
        if t is None or t.kind != "ident" or t.text.lower() in _KEYWORD_OPS or t.text.lower() in _JOINS:
            raise ConditionError(f"expected a field path in {raw!r}")
        path = t.text
        pos += 1
        # op
        t = peek()
        if t is None:
            raise ConditionError(f"expected an operator after {path!r} in {raw!r}")
        if t.kind == "op":
            op = t.text
            pos += 1
        elif t.kind == "ident" and t.text.lower() in _KEYWORD_OPS:
            op = t.text.lower()
            pos += 1
        else:
            raise ConditionError(f"expected an operator after {path!r}, found {t.text!r}")

        value: object = None
        if op in _UNARY_OPS:
            pass
        elif op == _IN_OP:
            t = peek()
            if t is None or t.kind != "lbrack":
                raise ConditionError(f"'in' must be followed by a [list] in {raw!r}")
            pos += 1
            items: list[object] = []
            while True:
                t = peek()
                if t is None:
                    raise ConditionError(f"unterminated [list] in {raw!r}")
                if t.kind == "rbrack":
                    pos += 1
                    break
                if items:
                    if t.kind != "comma":
                        raise ConditionError(f"expected ',' or ']' in list in {raw!r}")
                    pos += 1
                    t = peek()
                    if t is None:
                        raise ConditionError(f"unterminated [list] in {raw!r}")
                items.append(_parse_literal_token(t))
                pos += 1
            if not items:
                raise ConditionError(f"'in' list is empty in {raw!r}")
            value = items
        else:  # value op
            t = peek()
            if t is None:
                raise ConditionError(f"expected a value after {op!r} in {raw!r}")
            value = _parse_literal_token(t)
            pos += 1

        comparisons.append(Comparison(path=path, op=op, value=value, raw=raw[toks[start_pos].pos : (toks[pos].pos if pos < len(toks) else len(raw))].strip()))

        # join or end
        t = peek()
        if t is None:
            break
        if t.kind == "ident" and t.text.lower() in _JOINS:
            this_join = _JOINS[t.text.lower()]
            if join is not None and join != this_join:
                raise ConditionError(
                    f"cannot mix 'and'/'or' in one condition: {raw!r} "
                    f"(split into separate rows or parenthesise — not supported in v1)"
                )
            join = this_join
            pos += 1
            continue
        raise ConditionError(f"unexpected token {t.text!r} after a comparison in {raw!r}")

    return ConditionAST(comparisons=comparisons, join=(join or "AND"), raw=raw)


# ---------------------------------------------------------------------------
# Registry index (validation) — accessor → entry, no jar needed
# ---------------------------------------------------------------------------

# base_type (registry) → DSL literal kind.
_BASE_TYPE_KIND = {
    "string": "string",
    "decimal": "number",
    "int": "number",
    "boolean": "boolean",
    "date": "date",
    "datetime": "date",
    "object": "object",
}

# Legal accessor roots per block scope. policy.data.* (custom policy fields)
# resolves on the segment type in Java but is *written* policy.data by the author.
_SCOPE_ROOTS = {
    "quote": {"quote"},
    "policy": {"policy"},
}


def _derive_condition_accessor(velocity: str, category: str) -> str:
    """velocity + category → the accessor form a condition path uses.

    Mirrors leg4._derive_accessor for the categories that can appear in a
    document-scoped conditional (quote_system → quote.x, system/policy_data →
    policy.x / policy.data.x). Other categories return "" (not addressable).
    """
    v = (velocity or "").strip()
    cat = (category or "").strip()
    tail = v[len("$data."):] if v.startswith("$data.") else v
    if cat == "quote_system":
        return "quote." + tail
    if cat == "system":
        return "policy." + tail
    if cat == "policy_data":
        # registry velocity is $data.data.<field>; condition path is policy.data.<field>
        return "policy." + tail
    return ""


def _accessor_scope(accessor: str) -> str | None:
    root = accessor.split(".", 1)[0]
    if root == "quote":
        return "quote"
    if root == "policy":
        return "policy"
    return None


def build_registry_index(registry: dict | None) -> dict[str, dict]:
    """Build {condition-accessor: {base_type, category, scope}} from a registry dict.

    Only categories addressable in a document-scoped conditional are indexed
    (quote_system, system, policy_data). DataFetcher / per-exposure paths are
    deliberately absent so they surface as "not found" during validation.
    """
    index: dict[str, dict] = {}
    if not isinstance(registry, dict):
        return index

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            vel, cat = node.get("velocity"), node.get("category")
            if vel and cat:
                base_type = str(node.get("base_type") or node.get("type") or "")
                acc = _derive_condition_accessor(str(vel), str(cat))
                if acc:
                    index[acc] = {
                        "base_type": base_type,
                        "category": str(cat),
                        "scope": _accessor_scope(acc),
                    }
                # Gap 4: custom fields are stored as policy_data ($data.data.<f>)
                # and derive a policy.data.<f> accessor — so a quote-scoped doc
                # could only condition on quote *system* fields. Index a
                # quote.data.<f> alias too, letting quote-scoped conditions reach
                # custom fields. (Usable only at quote scope; the policy-scope
                # check rejects a `quote.` root before the path-exists check.)
                if str(cat) == "policy_data":
                    tail = str(vel)[len("$data."):] if str(vel).startswith("$data.") else str(vel)
                    index["quote." + tail] = {
                        "base_type": base_type,
                        "category": str(cat),
                        "scope": "quote",
                        # Reachable only by the full `quote.data.<f>` accessor — kept
                        # out of bare-leaf resolution so a leaf like `discountType`
                        # stays single-candidate (policy.data.<f>) and unambiguous.
                        "alias": True,
                    }
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(registry)
    return index


def _literal_kind(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_condition(
    ast: ConditionAST,
    registry: dict | None,
    scope: str,
    *,
    classpath: str | None = None,
    product: str | None = None,
) -> list[str]:
    """Validate ``ast`` against the path-registry (and optionally javap).

    Returns a list of human-readable error strings; empty means valid. Checks,
    in order, per comparison:

    1. root legal for ``scope`` (a quote field in a policy doc → error);
    2. path exists in the registry (addressable accessor);
    3. leaf base_type vs literal type (string op on a number → error);
    4. (when classpath+product given) the accessor chain resolves in Java via
       :func:`leg4_generate_plugin._walk_java_chain`.
    """
    errors: list[str] = []
    index = build_registry_index(registry)
    legal_roots = _SCOPE_ROOTS.get(scope, set())

    for cmp in ast.comparisons:
        root = cmp.path.split(".", 1)[0]
        if legal_roots and root not in legal_roots:
            errors.append(
                f"{cmp.path!r}: root {root!r} is not valid in a {scope}-scoped block "
                f"(allowed: {', '.join(sorted(legal_roots))})"
            )
            continue

        info = index.get(cmp.path)
        if info is None:
            # The registry is a curated subset: when a jar is available and the
            # accessor resolves against the real model, accept it (no registry
            # entry to type-check against, so the type check is skipped — Leg 4's
            # --compile-check is the final arbiter). Without a jar, stay strict.
            if classpath and product and not _javap_check(cmp.path, scope, classpath, product):
                continue
            errors.append(f"{cmp.path!r}: not found in the path registry")
            continue

        # Scope of the path itself must match the block scope.
        if info["scope"] and scope and info["scope"] != scope:
            errors.append(
                f"{cmp.path!r}: is a {info['scope']} field, not valid in a {scope}-scoped block"
            )
            continue

        # Type check: literal kind vs leaf base_type.
        leaf_kind = _BASE_TYPE_KIND.get(info["base_type"], "")
        if cmp.op in _VALUE_OPS and leaf_kind and leaf_kind != "object":
            lit_kind = _literal_kind(cmp.value)
            if cmp.op in _ORDER_OPS and leaf_kind not in ("number", "date"):
                errors.append(
                    f"{cmp.path!r}: ordering operator {cmp.op!r} needs a numeric/date "
                    f"field, but it is {info['base_type']!r}"
                )
            elif leaf_kind == "number" and lit_kind != "number":
                errors.append(
                    f"{cmp.path!r}: {info['base_type']!r} field compared to non-numeric "
                    f"value {cmp.value!r}"
                )
            elif leaf_kind == "boolean" and lit_kind != "boolean":
                errors.append(
                    f"{cmp.path!r}: boolean field compared to non-boolean value {cmp.value!r}"
                )
            elif leaf_kind in ("string", "date") and lit_kind == "number":
                errors.append(
                    f"{cmp.path!r}: {info['base_type']!r} field compared to numeric "
                    f"value {cmp.value!r}"
                )
        elif cmp.op == _IN_OP and leaf_kind == "number":
            if any(_literal_kind(v) != "number" for v in (cmp.value or [])):
                errors.append(f"{cmp.path!r}: numeric field with a non-numeric value in 'in' list")

        # Optional javap walk (defense in depth; needs a jar + product).
        if classpath and product:
            errors.extend(_javap_check(cmp.path, scope, classpath, product))

    return errors


def _javap_check(path: str, scope: str, classpath: str, product: str) -> list[str]:
    """Walk the accessor chain in Java; lazy import keeps Leg 4 import acyclic."""
    from velocity_converter.leg4_generate_plugin import (  # noqa: PLC0415
        _CORE_POLICY_FQCN,
        _walk_java_chain,
    )
    from velocity_converter.sdk_introspect import CUSTOMER_PACKAGE  # noqa: PLC0415

    root_var, parts = _path_to_chain(_rewrite_for_scope(path, scope))
    fqcn = {
        "quote": f"{CUSTOMER_PACKAGE}.{product}Quote",
        "policy": _CORE_POLICY_FQCN,
        "segment": f"{CUSTOMER_PACKAGE}.{product}Segment",
    }.get(root_var)
    if not fqcn or not parts:
        return []
    _ret, fail = _walk_java_chain(classpath, fqcn, parts)
    return [f"{path!r}: does not resolve in Java ({fail})"] if fail else []


# ---------------------------------------------------------------------------
# Codegen
# ---------------------------------------------------------------------------


def _rewrite_for_scope(path: str, scope: str) -> str:
    """policy.data.<x> → segment.data.<x> in the policy overload (custom fields
    live on the segment type; core Policy has no data()). Mirrors
    leg4._rewrite_condition_root."""
    if scope == "policy":
        return re.sub(r"\bpolicy\.data\.", "segment.data.", path)
    return path


def _path_to_chain(path: str) -> tuple[str, list[str]]:
    segs = path.split(".")
    return segs[0], segs[1:]


def _full_accessor(root_var: str, parts: list[str]) -> str:
    return root_var + "".join(f".{p}()" for p in parts)


def _null_guards(root_var: str, parts: list[str], *, include_leaf: bool) -> list[str]:
    """``== null`` checks for each step of the chain (so the chain never NPEs)."""
    guards = [f"{root_var} == null"]
    expr = root_var
    stop = len(parts) if include_leaf else len(parts) - 1
    for p in parts[:stop]:
        expr += f".{p}()"
        guards.append(f"{expr} == null")
    return guards


def _null_safe_value(root_var: str, parts: list[str]) -> str:
    """A null-safe expression yielding the leaf value or ``null``."""
    full = _full_accessor(root_var, parts)
    guards = _null_guards(root_var, parts, include_leaf=False)
    if len(guards) == 1 and guards[0] == f"{root_var} == null" and not parts[:-1]:
        return f"({root_var} == null ? null : {full})"
    return f"({' || '.join(guards)} ? null : {full})"


def _java_string_literal(value: object) -> str:
    s = str(value)
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    return f'"{s}"'


def _numeric_compare_java(full: str, not_null: str, value: object, jop: str, java_type: str | None) -> str:
    """Render a null-guarded numeric comparison, type-correct for the leaf.

    ``jop`` is the Java operator (``>``/``>=``/``<``/``<=``/``==``). Integral and
    floating leaves autounbox (``leaf > 0``); BigDecimal/BigInteger leaves use
    ``compareTo(...) <op> 0``. The leaf is null-guarded either way.
    """
    strat = _numeric_strategy(java_type)
    if strat == "unbox":
        return f"(!({not_null}) && {full} {jop} {_java_number_literal(value)})"
    lit = _java_biginteger_literal(value) if strat == "biginteger" else _java_bigdecimal_literal(value)
    return f"(!({not_null}) && {full}.compareTo({lit}) {jop} 0)"


def _comparison_to_java(cmp: Comparison, scope: str, leaf_types: dict[str, str] | None = None) -> str:
    root_var, parts = _path_to_chain(_rewrite_for_scope(cmp.path, scope))
    if not parts:
        # Bare root reference — degenerate, treat as present check.
        return f"{root_var} != null"

    full = _full_accessor(root_var, parts)
    val = _null_safe_value(root_var, parts)
    # Leaf types are keyed by the author-written path (pre scope-rewrite).
    java_type = (leaf_types or {}).get(cmp.path)

    if cmp.op == "present":
        return f"{val} != null"
    if cmp.op == "absent":
        return f"{val} == null"

    if cmp.op == _IN_OP:
        items = ", ".join(_java_string_literal(v) for v in (cmp.value or []))
        # Compare as strings (enum/String safe). null value → contains(null) = false.
        norm = _null_safe_tostring(root_var, parts)
        return f"java.util.List.of({items}).contains({norm})"

    if cmp.op in _ORDER_OPS:
        # Numeric/date ordering, fully null-guarded. BigDecimal compareTo for
        # decimal leaves; autounboxed operator for int/float leaves.
        jop = {">": ">", ">=": ">=", "<": "<", "<=": "<="}[cmp.op]
        not_null = " || ".join(_null_guards(root_var, parts, include_leaf=True))
        return _numeric_compare_java(full, not_null, cmp.value, jop, java_type)

    # Equality / inequality.
    kind = _literal_kind(cmp.value)
    if kind == "boolean":
        java_eq = f"Objects.equals({val}, {'true' if cmp.value else 'false'})"
    elif kind == "number":
        not_null = " || ".join(_null_guards(root_var, parts, include_leaf=True))
        java_eq = _numeric_compare_java(full, not_null, cmp.value, "==", java_type)
    else:  # string — toString-normalise so enum and String both work
        norm = _null_safe_tostring(root_var, parts)
        java_eq = f"Objects.equals({norm}, {_java_string_literal(cmp.value)})"
    return f"!({java_eq})" if cmp.op == "!=" else java_eq


def _null_safe_tostring(root_var: str, parts: list[str]) -> str:
    """Null-safe ``Objects.toString(leaf, null)`` — enum→name(), String→itself."""
    full = _full_accessor(root_var, parts)
    guards = _null_guards(root_var, parts, include_leaf=False)
    return f"({' || '.join(guards)} ? null : Objects.toString({full}, null))"


def _java_bigdecimal_literal(value: object) -> str:
    return f'new java.math.BigDecimal("{value}")'


def _java_biginteger_literal(value: object) -> str:
    return f'new java.math.BigInteger("{value}")'


def _java_number_literal(value: object) -> str:
    """A bare Java numeric literal (for autounboxed comparison of int/float leaves)."""
    return str(value)


# Leaf Java types whose comparisons can use autounboxed relational/equality
# operators directly (``leaf > 0``), rather than ``compareTo``. Integer.compareTo
# only accepts an Integer, so emitting a BigDecimal there does not compile — the
# bug this branch fixes. Anything not listed (notably BigDecimal) keeps compareTo.
_UNBOX_JAVA_TYPES = {
    "int", "long", "short", "byte", "double", "float",
    "java.lang.Integer", "java.lang.Long", "java.lang.Short",
    "java.lang.Byte", "java.lang.Double", "java.lang.Float",
}


def _numeric_strategy(java_type: str | None) -> str:
    """Pick numeric-comparison codegen for a leaf's Java type.

    ``"unbox"`` → autounboxed operator (Integer/Long/Short/Byte/Double/Float and
    their primitives); ``"biginteger"`` → ``compareTo(new BigInteger(...))``;
    ``"bigdecimal"`` → ``compareTo(new BigDecimal(...))``. ``"bigdecimal"`` is also
    the fallback when the type is unknown (no javap context, e.g. unit tests), so
    the pre-existing decimal codegen and its golden tests are preserved.
    """
    t = (java_type or "").strip()
    if t in _UNBOX_JAVA_TYPES:
        return "unbox"
    if t == "java.math.BigInteger":
        return "biginteger"
    return "bigdecimal"


def condition_to_java(ast: ConditionAST, scope: str, leaf_types: dict[str, str] | None = None) -> str:
    """Render an AST to a single boolean Java expression.

    Equality uses ``Objects.equals`` on a null-safe ``toString`` (so String and
    enum leaves both compare correctly, killing the ``==`` reference-equality
    bug); numeric ordering/equality is null-guarded and **type-aware** —
    ``compareTo`` for BigDecimal/BigInteger leaves, autounboxed operators for
    int/float leaves (``Integer.compareTo(BigDecimal)`` does not compile);
    present/absent are null checks; ``in`` is ``List.of(...).contains(...)``.
    Every accessor step is null-guarded so the expression cannot NPE.

    ``leaf_types`` maps an author-written condition path to its resolved Java
    return type (e.g. ``{"quote.data.coolingOffPeriod": "java.lang.Integer"}``),
    typically from a javap walk. When omitted or a leaf is absent, numeric
    codegen falls back to ``BigDecimal.compareTo`` (the prior behaviour).
    """
    if not ast.comparisons:
        return "true"
    joiner = " || " if ast.join == "OR" else " && "
    parts = [_comparison_to_java(c, scope, leaf_types) for c in ast.comparisons]
    if len(parts) == 1:
        return parts[0]
    return joiner.join(f"({p})" for p in parts)


# ---------------------------------------------------------------------------
# Convenience: load a registry dict for validation
# ---------------------------------------------------------------------------


def load_registry_dict(registry_path: str | Path | None) -> dict | None:
    if not registry_path:
        return None
    p = Path(registry_path)
    if not p.is_file():
        return None
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# AST <-> dict serialisation (for variants[].when in conditional-registry.yaml)
# ---------------------------------------------------------------------------


def ast_to_dict(ast: ConditionAST) -> dict:
    """Serialise an AST to the registry ``when`` shape.

    Single-comparison conditions use the flat ``{path, op, value, raw}`` form the
    plan sketches; multi-comparison conditions add ``join`` + ``comparisons``.
    """
    comps = [
        {k: v for k, v in (("path", c.path), ("op", c.op), ("value", c.value)) if v is not None or k != "value"}
        for c in ast.comparisons
    ]
    if len(comps) == 1:
        return {**comps[0], "raw": ast.raw}
    return {"join": ast.join, "comparisons": comps, "raw": ast.raw}


def ast_from_dict(d: dict) -> ConditionAST:
    """Rebuild an AST from a registry ``when`` dict (inverse of :func:`ast_to_dict`).

    Falls back to re-parsing ``raw`` when the structured form is absent (old or
    hand-edited registries) — ``raw`` is the source of truth.
    """
    if "comparisons" in d:
        comps = [
            Comparison(path=c.get("path", ""), op=c.get("op", "=="), value=c.get("value"), raw=str(c.get("raw", "")))
            for c in d.get("comparisons") or []
        ]
        return ConditionAST(comparisons=comps, join=str(d.get("join", "AND")).upper(), raw=str(d.get("raw", "")))
    if "path" in d and "op" in d:
        return ConditionAST(
            comparisons=[Comparison(path=d["path"], op=d["op"], value=d.get("value"), raw=str(d.get("raw", "")))],
            join="AND",
            raw=str(d.get("raw", "")),
        )
    return parse_condition(str(d.get("raw", "")))


# ---------------------------------------------------------------------------
# Bare-leaf resolution — let the author write `state == "CA"` not the accessor
# ---------------------------------------------------------------------------


def _build_leaf_map(
    index: dict[str, dict], *, include_alias: bool = False
) -> dict[str, list[str]]:
    """leaf name → [accessor, …] from a registry index (for bare-leaf resolution).

    By default the ``quote.data.<f>`` aliases (Gap 4) are full-accessor-only and
    excluded, so a bare leaf stays single-candidate (``policy.data.<f>``). With
    ``include_alias`` the aliases are included too — used when the document's
    rendering root is known, so a bare leaf in a *quote* document resolves to the
    quote accessor (the scope filter in :func:`_resolve_path` then disambiguates).
    """
    leaf_map: dict[str, list[str]] = {}
    for acc, entry in index.items():
        if entry.get("alias") and not include_alias:  # full-accessor-only (Gap 4)
            continue
        leaf_map.setdefault(acc.split(".")[-1], []).append(acc)
    return leaf_map


def _resolve_path(
    path: str, index: dict[str, dict], leaf_map: dict[str, list[str]], scope: str | None
) -> tuple[str | None, str | None]:
    """Resolve a (possibly bare) condition path to a full accessor + its scope.

    Returns ``(accessor, scope)`` or ``(None, reason)``. A path already in the
    index passes through; a bare leaf resolves if exactly one registry accessor
    (in scope, when scope is known) ends with it.
    """
    if path in index:
        return path, index[path]["scope"]
    if "." in path:
        return None, f"{path!r} is not a known accessor"
    candidates = leaf_map.get(path, [])
    if scope:
        candidates = [a for a in candidates if index[a]["scope"] == scope]
    if not candidates:
        return None, f"{path!r} did not resolve to any registry field"
    if len(candidates) > 1:
        return None, f"{path!r} is ambiguous ({', '.join(sorted(candidates))}) — write the full accessor"
    return candidates[0], index[candidates[0]]["scope"]


# ---------------------------------------------------------------------------
# CSV normaliser — customer's <stem>.variants.csv → structured variants
# ---------------------------------------------------------------------------

_DEFAULT_WHEN = {"", "*", "else", "default"}
_CSV_COLUMNS = ("placeholder", "when", "text")

# A nested reference inside a variant's text cell: [[$otherRow]] points at another
# placeholder in the same sheet. Peel it to the machine form $doc.<key> that the
# downstream codegen ($doc.<key> → " + key + " in _source_text_to_java) and the
# topo-sort already understand — so a label conditional composes into its parent.
_NESTED_REF_RE = re.compile(r"\[\[\$([A-Za-z_]\w*)\]\]")


def _peel_nested_refs(text: str) -> str:
    """``[[$x]]`` → ``$doc.x`` in a variant text/default cell (no-op without one)."""
    return _NESTED_REF_RE.sub(r"$doc.\1", text or "")


@dataclass
class VariantParseResult:
    """Per-placeholder normalised variants + the computed scope + any errors."""

    placeholders: dict[str, dict] = field(default_factory=dict)  # name -> {variants, default, scope}
    errors: list[str] = field(default_factory=list)


def _read_csv_rows(text: str) -> list[dict]:
    """Read CSV rows, sniffing the delimiter and skipping ``#`` comment lines."""
    # Drop a UTF-8 BOM and full-line comments before the header.
    lines = [ln for ln in text.replace("﻿", "").splitlines() if not ln.lstrip().startswith("#")]
    if not lines:
        return []
    body = "\n".join(lines)
    try:
        dialect = csv.Sniffer().sniff(body[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(body), dialect=dialect)
    rows = []
    for raw in reader:
        rows.append({(k or "").strip().lower(): (v or "").strip() for k, v in raw.items() if k})
    return rows


def parse_variants_csv(
    path: str | Path,
    registry: dict | None = None,
    *,
    classpath: str | None = None,
    product: str | None = None,
    template_placeholders: set[str] | None = None,
    doc_scope: str | None = None,
) -> VariantParseResult:
    """Normalise a customer ``<stem>.variants.csv`` into structured variants.

    Columns: ``placeholder, when, text`` (row order = priority, first match
    wins). A blank/``*``/``else`` ``when`` is the default (else) row. Per
    placeholder this validates: exactly one default, ≥1 conditioned row, every
    ``when`` parses + (with a registry) validates, and a single shared scope.
    Bare leaf names in ``when`` are resolved against the registry.

    ``template_placeholders`` (variants-only plan §2.3, Decision A): keys for
    loop-bearing ``render: template`` blocks. Such a block carries a single
    ``when`` and **no** text/default (its wording stays in the document), so the
    default-row and N-way validations are skipped for it; >1 conditioned row is
    rejected (the unsupported per-variant-loop edge).

    ``doc_scope`` is the document's rendering-root scope (``"quote"`` or
    ``"policy"``). When given, bare leaves resolve to that scope — so a custom
    field in a ``(quote)`` document resolves to ``quote.data.<f>`` rather than the
    ``policy.data.<f>`` home, keeping the conditional in the quote overload. When
    omitted, resolution stays scope-blind (single ``policy.data.<f>`` candidate).
    """
    template_placeholders = template_placeholders or set()
    result = VariantParseResult()
    p = Path(path)
    if not p.is_file():
        result.errors.append(f"variants CSV not found: {p}")
        return result
    rows = _read_csv_rows(p.read_text(encoding="utf-8"))
    if not rows:
        result.errors.append(f"variants CSV is empty: {p}")
        return result

    index = build_registry_index(registry) if registry else {}
    # When the rendering root is known, include the quote.data.<f> aliases so a
    # bare leaf resolves to the document's scope (the scope filter disambiguates).
    leaf_map = _build_leaf_map(index, include_alias=bool(doc_scope))

    # Group rows by placeholder, preserving order.
    grouped: dict[str, list[dict]] = {}
    for i, row in enumerate(rows):
        ph = row.get("placeholder", "")
        if not ph:
            result.errors.append(f"row {i + 2}: missing placeholder")
            continue
        grouped.setdefault(ph, []).append(row)

    for ph, prows in grouped.items():
        variants: list[dict] = []
        default: str | None = None
        scopes: set[str] = set()
        errors: list[str] = []
        default_count = 0
        for row in prows:
            when = row.get("when", "").strip()
            # Peel nested [[$x]] refs to $doc.x before storing — composes downstream.
            text = _peel_nested_refs(row.get("text", ""))
            if when.lower() in _DEFAULT_WHEN:
                default_count += 1
                default = text
                continue
            try:
                ast = parse_condition(when)
            except ConditionError as exc:
                errors.append(f"{ph}: bad condition {when!r}: {exc}")
                continue
            # Resolve bare leaves → full accessors; track scope.
            resolved_ok = True
            for cmp in ast.comparisons:
                acc, sc = _resolve_path(cmp.path, index, leaf_map, doc_scope) if index else (cmp.path, _accessor_scope(cmp.path))
                if acc is None:
                    # Jar-as-authority: the curated registry is a subset (and can
                    # lag the real model). If a jar was supplied and the author's
                    # fully-qualified path resolves against the real classes, trust
                    # it over the registry rather than rejecting a valid accessor.
                    jar_sc = _accessor_scope(cmp.path)
                    if (classpath and product and "." in cmp.path and jar_sc
                            and not _javap_check(cmp.path, jar_sc, classpath, product)):
                        scopes.add(jar_sc)  # full accessor taken as authored
                    else:
                        errors.append(f"{ph}: {sc}")
                        resolved_ok = False
                    continue
                cmp.path = acc
                if sc:
                    scopes.add(sc)
            if not resolved_ok:
                continue
            variants.append({"when": ast_to_dict(ast), "text": text, "_ast": ast})

        is_template = ph in template_placeholders
        if is_template:
            if default_count:
                errors.append(f"{ph}: template (loop) block takes a single `when` only — "
                              "remove the default/blank-when row(s)")
            if len(variants) > 1:
                errors.append(f"{ph}: template (loop) block has {len(variants)} conditioned rows — "
                              "an N-way block whose variants each carry a loop is unsupported")
            if not variants and not errors:
                errors.append(f"{ph}: template (loop) block has no `when` row — fill the condition")
        else:
            if default_count == 0:
                if len(variants) == 1:
                    # Binary show/hide: one conditioned row, no default → render
                    # the text when the condition holds, nothing otherwise. The
                    # implicit empty default gives the exact downstream shape the
                    # binary fold already produces (one real row + empty default),
                    # so authors needn't hand-write a blank default row per block.
                    default = ""
                else:
                    errors.append(
                        f"{ph}: no default row (blank/*/else 'when') — an N-way block with "
                        f"{len(variants)} variants needs an explicit default; a single-row "
                        f"show/hide block does not"
                    )
            elif default_count > 1:
                errors.append(f"{ph}: {default_count} default rows (expected exactly one)")
            # A default-only block (exactly one default, no conditioned rows) is
            # valid: it always renders the default text. Empty `variants` + a
            # `default` flows downstream as an unconditional value.
        if len(scopes) > 1:
            errors.append(f"{ph}: variants mix scopes ({', '.join(sorted(scopes))}) — all must be one scope")

        scope = next(iter(scopes)) if len(scopes) == 1 else ""

        # Registry validation pass (now that scope is known).
        if registry and scope:
            for v in variants:
                for e in validate_condition(v["_ast"], registry, scope, classpath=classpath, product=product):
                    errors.append(f"{ph}: {e}")

        # Strip the transient _ast before returning the serialisable structure.
        for v in variants:
            v.pop("_ast", None)

        result.placeholders[ph] = {"variants": variants, "default": default, "scope": scope}
        result.errors.extend(errors)

    return result
