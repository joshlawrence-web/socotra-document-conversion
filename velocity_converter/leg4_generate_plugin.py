#!/usr/bin/env python3
"""Leg 4 — Document Data Snapshot Plugin Generator.

Reads:
  - <stem>.mapping.yaml  (Leg 2, enriched) — provides `product:` and `variables:`
  - build/customer-config.jar       — plugin interface + {Product}* request types
  - build/core-datamodel-*.jar      — DocumentDataSnapshot, Policy, Transaction, ...

Writes:
  - {Product}DocumentDataSnapshotPluginImpl.java  — one plugin class per product
  - <stem>.plugin-report.md                        — path-validation + ignored fields

Deterministic Java codegen (no LLM). renderingData is a HashMap<String, Object>
with named keys per request type:

  quote request   → keys: "quote" ($data.quote.*), "pricing" (enriched), "productType"
  policy request  → keys: "policy" ($data.policy.*), "transaction" ($data.transaction.*),
                          "segment" ($data.segment.*), "todayAsString", "productType"

Only high-confidence variables are validated; medium/low are reported as ignored (D5).
Missing segment on a policy request fails soft — logs an error, segment key is null.
See the Leg 4 renderingData-alignment plan for the decisions behind these choices.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

import yaml

from velocity_converter.condition_dsl import ast_from_dict, condition_to_java
from velocity_converter.models import (
    ConditionalRegistry,
    ContractError,
    PathRegistry,
    block_key,
    validate_contract,
)
from velocity_converter.workspace import action_needed_dir

# Shared SDK-introspection helpers (Leg 2 plan P1.1 — single source of JAR truth).
from velocity_converter.sdk_introspect import (
    CUSTOMER_PACKAGE,
    DATAFETCHER_INTERFACE,
    INVOICE_REQUEST,
    PLUGIN_INTERFACE,
    _class_exists,
    _default_datamodel_jar,
    _default_slf4j_jar,
    _method_return_type,
    _unwrap_type,
    _zero_arg_methods,
    validate_path,
)


# ---------------------------------------------------------------------------
# Helpers (mirrors velocity_converter/leg3_substitute.py)
# ---------------------------------------------------------------------------


def _derive_accessor(velocity: str, category: str) -> str:
    """Derive clean accessor from velocity path + category."""
    v = (velocity or "").strip()
    cat = (category or "").strip()
    if cat == "system":
        return "policy." + v[len("$data."):] if v.startswith("$data.") else v
    if cat == "quote_system":
        return "quote." + v[len("$data."):] if v.startswith("$data.") else v
    if cat == "policy_data":
        return "policy." + v[len("$data."):] if v.startswith("$data.") else v
    if v.startswith("$data."):
        return v[len("$data."):]
    if v.startswith("$"):
        return v[1:]
    return v


def _accessor_to_java(expr: str) -> str:
    """Translate an accessor-style condition expression to a Java expression.

    Adds () to each non-root segment of any accessor chain found in the expression.
    Examples:
      quote.quoteNumber != null      →  quote.quoteNumber() != null
      account.data.lastName          →  account.data().lastName()
      policy.data.riderType == "X"   →  policy.data().riderType() == "X"
    """
    import re as _re
    def _translate_chain(m: "_re.Match") -> str:
        chain = m.group(0)
        parts = chain.split(".")
        if len(parts) <= 1:
            return chain
        result = parts[0]
        for p in parts[1:]:
            result += f".{p}()"
        return result
    # Match accessor chains (2+ dot-separated identifiers) NOT already followed by (
    return _re.sub(
        r'\b([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+)(?!\s*\()',
        _translate_chain,
        expr,
    )


# ---------------------------------------------------------------------------
# Field tokens inside conditional blocks (plan 10-conditional-field-tokens)
# ---------------------------------------------------------------------------

# Categories whose accessors live on a local variable of the matching overload.
# Everything else (account, exposure/coverage/charge paths, …) has no local in a
# document-scoped conditional put and is flagged as unsupported (D4).
# category → (scope, local Java variable). Policy custom fields ($data.data.*)
# live on the segment type in Java, not on core Policy.
_CATEGORY_WIRING = {
    "quote_system": ("quote", "quote"),
    "quote_data": ("quote", "quote"),
    "system": ("policy", "policy"),
    "policy_data": ("policy", "segment"),
}
_CORE_POLICY_FQCN = "com.socotra.coremodel.Policy"

_FIELD_TOKEN_FALLBACK_RE = re.compile(r"[A-Za-z_][\w.]*")
_TBD_PREVIEW_RE = re.compile(r"\$TBD_([A-Za-z_][\w.]*)")


def _tbd_preview(text: str) -> str:
    """Display $TBD_name tokens as {name} in generated comments (never in code)."""
    def _repl(m: re.Match) -> str:
        name = m.group(1)
        stripped = name.rstrip(".")
        return "{" + stripped + "}" + name[len(stripped):]
    return _TBD_PREVIEW_RE.sub(_repl, text)


def _load_velocity_categories(registry_path: Path | None) -> dict[str, str]:
    """Build {velocity_path: category} from path-registry.yaml. {} if unreadable."""
    if not registry_path or not Path(registry_path).is_file():
        return {}
    try:
        data = yaml.safe_load(Path(registry_path).read_text(encoding="utf-8")) or {}
        validate_contract(data, PathRegistry, artifact="path-registry.yaml", path=Path(registry_path))
    except ContractError as exc:
        print(f"WARNING: ignoring invalid registry (category lookup disabled)\n{exc}", file=sys.stderr)
        return {}
    except Exception:
        return {}
    out: dict[str, str] = {}

    def _walk(node) -> None:
        if isinstance(node, dict):
            vel, cat = node.get("velocity"), node.get("category")
            if vel and cat:
                out[str(vel)] = str(cat)
                if cat == "quote_system" and str(vel).startswith("$data."):
                    out["$data.quote." + str(vel)[len("$data."):]] = str(cat)
                if cat == "policy_data" and str(vel).startswith("$data.data."):
                    out["$data.quote." + str(vel)[len("$data."):]] = "quote_data"
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(data)
    return out


def _rewrite_condition_root(cond: str, scope: str) -> str:
    """Rewrite customer accessor roots to the overload's actual Java locals.

    The form convention is `policy.data.<field>` for custom policy fields, but
    in Java those live on the segment type — core Policy has no data() method.
    """
    if scope == "policy":
        return re.sub(r"\bpolicy\.data\.", "segment.data.", cond)
    return cond


def _walk_java_chain(classpath: str, fqcn: str, parts: list[str]) -> tuple[str | None, str]:
    """javap-walk parts against fqcn. Returns (final_return_type, "") or (None, reason)."""
    current = fqcn
    ret = ""
    for i, part in enumerate(parts):
        methods = _zero_arg_methods(classpath, current)
        short = current.rsplit(".", 1)[-1].rsplit("$", 1)[-1]
        if not methods:
            return None, f"could not introspect {short}"
        if part not in methods:
            return None, f"{short} has no method {part}()"
        ret = methods[part]
        if i < len(parts) - 1:
            nxt = _unwrap_type(ret)
            if nxt is None:
                return None, f"{part}() returns {ret}; cannot navigate further"
            current = nxt
    return ret, ""


def _build_cond_field_lookup(
    suggested_flat: dict,
    vel_to_cat: dict[str, str],
    classpath: str | None = None,
    product: str | None = None,
) -> dict[str, dict]:
    """Map variable name → wiring info for field tokens inside conditional blocks.

    Each entry: {data_source, scope: 'quote'|'policy'|None, java_expr, unsupported_reason}.
    Empty data_source (or UNRESOLVED:*) → unresolved, the caller hard-fails (D5).
    Loop fields and DataFetcher-sourced variables are resolved-but-unsupported (D4).

    With classpath+product the accessor chain is javap-verified against the
    overload's local type and Optional<> returns are unwrapped; without them
    (unit tests) the chain is emitted unverified with an Objects.toString wrap.
    """
    root_fqcns = {
        "quote": f"{CUSTOMER_PACKAGE}.{product}Quote" if product else None,
        "policy": _CORE_POLICY_FQCN,
        "segment": f"{CUSTOMER_PACKAGE}.{product}Segment" if product else None,
    }
    lookup: dict[str, dict] = {}
    for v in suggested_flat.get("variables") or []:
        name = (v.get("name") or "").strip()
        if not name:
            continue
        ds = (v.get("data_source") or "").strip()
        info = {"data_source": ds, "scope": None, "java_expr": "", "unsupported_reason": ""}
        cand = v.get("candidate") or {}
        cat = vel_to_cat.get(ds)
        if not ds or ds.startswith("UNRESOLVED:"):
            info["data_source"] = ""
        elif cand.get("source") == "datafetcher":
            info["unsupported_reason"] = (
                "DataFetcher-sourced (deferred — needs a fetch before the conditional block)"
            )
        elif cat in _CATEGORY_WIRING:
            scope, root_var = _CATEGORY_WIRING[cat]
            if not ds.startswith("$data."):
                info["unsupported_reason"] = f"unexpected velocity shape: {ds}"
            else:
                prefix = f"$data.{root_var}."
                if ds.startswith(prefix):
                    parts = ds[len(prefix):].split(".")
                else:
                    parts = ds[len("$data."):].split(".")
                expr = root_var + "".join(f".{p}()" for p in parts)
                fqcn = root_fqcns.get(root_var)
                final_ret = ""
                if classpath and fqcn:
                    final_ret, fail = _walk_java_chain(classpath, fqcn, parts)
                    if final_ret is None:
                        info["unsupported_reason"] = f"path does not resolve in Java ({fail})"
                if not info["unsupported_reason"]:
                    info["scope"] = scope
                    info["guard"] = {
                        "root_var": root_var,
                        "parts": parts,
                        "final_ret": final_ret or "",
                    }
                    if final_ret and final_ret.startswith("java.util.Optional"):
                        info["java_expr"] = f'{expr}.map(Object::toString).orElse("")'
                    else:
                        info["java_expr"] = f'Objects.toString({expr}, "")'
        elif cat is None:
            info["unsupported_reason"] = "path not found in registry (cannot derive Java accessor)"
        else:
            info["unsupported_reason"] = (
                f"category '{cat}' has no local accessor in a document-scoped conditional"
            )
        lookup[name] = info
    for loop in suggested_flat.get("loops") or []:
        for f in loop.get("fields") or []:
            name = (f.get("name") or "").strip()
            if name and name not in lookup:
                lookup[name] = {
                    "data_source": (f.get("data_source") or "").strip(),
                    "scope": None,
                    "java_expr": "",
                    "unsupported_reason": (
                        "per-exposure (loop) field — conditional puts are document-scoped"
                    ),
                }
    return lookup


def _registry_accessor_to_velocity(registry_path: Path | None) -> dict[str, str]:
    """Build {condition-accessor: velocity} from the registry (inverse of
    _derive_accessor) so variant-text field tokens (written as full accessors,
    e.g. {quote.quoteNumber}) can be resolved to a velocity + wired."""
    if not registry_path or not Path(registry_path).is_file():
        return {}
    try:
        data = yaml.safe_load(Path(registry_path).read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    out: dict[str, str] = {}

    def _walk(node) -> None:
        if isinstance(node, dict):
            vel, cat = node.get("velocity"), node.get("category")
            if vel and cat:
                acc = _derive_accessor(str(vel), str(cat))
                if acc:
                    out.setdefault(acc, str(vel))
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(data)
    return out


def _scope_velocity_to_root(vel: str, doc_scope: str | None) -> str:
    """Rewrite a custom-field velocity to the document's rendering-root scope.

    A custom field's home velocity is ``$data.data.<f>`` (policy_data → segment in
    Java). In a *quote* document the same field is reached as
    ``$data.quote.data.<f>`` (→ ``quote_data`` wiring → ``quote.data().<f>()``), so
    a variant-text token resolves into the quote overload alongside its
    quote-scoped condition — not stranded as a policy-scoped TODO. No-op for any
    non-quote root (the policy.data home is already correct there).
    """
    if doc_scope == "quote" and vel.startswith("$data.data."):
        return "$data.quote.data." + vel[len("$data.data."):]
    return vel


def _augment_field_lookup_for_variants(
    field_lookup: dict[str, dict],
    cond_blocks: list[dict],
    vel_to_cat: dict[str, str],
    registry_path: Path | None,
    classpath: str | None,
    product: str | None,
    doc_scope: str | None = None,
) -> dict[str, dict]:
    """Add wiring for field tokens that appear only inside variant text/default.

    These aren't mapping variables (they came from the CSV, not the annotated
    HTML), so synthesize a pseudo-variable per distinct accessor and run it
    through _build_cond_field_lookup — reusing the exact category/javap wiring the
    binary path uses. Existing entries are never overwritten.

    ``doc_scope`` is the document's rendering-root scope; when ``"quote"`` a
    custom-field token resolves to the quote accessor (see
    :func:`_scope_velocity_to_root`) so it wires into the quote overload.
    """
    names: set[str] = set()
    for b in cond_blocks:
        if not b.get("variants") and not b.get("default"):
            continue
        texts = [v.get("text") or "" for v in (b.get("variants") or [])]
        texts.append(b.get("default") or "")
        for t in texts:
            for m in _FIELD_BRACE_RE.finditer(t):
                names.add(m.group(1))
    names -= set(field_lookup)
    if not names:
        return field_lookup
    acc_to_vel = _registry_accessor_to_velocity(registry_path)
    # Decision B (variants-only plan §2.4): a variant-text token may be a bare
    # leaf (`{discountAmount}`), not the full accessor — mirror Leg -1's leaf →
    # accessor resolution so a bare leaf no longer silently degrades to a TODO.
    # A leaf that ends exactly one registry accessor resolves; >1 (ambiguous) or
    # 0 (unmatched) is routed to the human via Leg -1 pass 2 (path-review),
    # reported here as a WARN row — never a hard fail (variant text is not
    # path-validated at parse time the way a `when` condition is).
    leaf_to_accs: dict[str, list[str]] = {}
    for acc in acc_to_vel:
        leaf_to_accs.setdefault(acc.split(".")[-1], []).append(acc)

    synth_vars: list[dict] = []
    extra: dict[str, dict] = {}
    for n in names:
        if n in acc_to_vel:
            synth_vars.append({"name": n, "data_source": _scope_velocity_to_root(acc_to_vel[n], doc_scope)})
            continue
        accs = leaf_to_accs.get(n, []) if "." not in n else []
        if len(accs) == 1:
            synth_vars.append({"name": n, "data_source": _scope_velocity_to_root(acc_to_vel[accs[0]], doc_scope)})
            continue
        if accs:
            reason = (
                f"ambiguous bare leaf — matches {', '.join(sorted(accs))}; write the "
                "full accessor in the variant text, or resolve it via path-review (Leg -1 pass 2)"
            )
        else:
            reason = (
                "not found in registry (cannot derive Java accessor for variant text) — "
                "resolve via path-review (Leg -1 pass 2) or write the full accessor"
            )
        extra[n] = {
            "data_source": "",
            "scope": None,
            "java_expr": "",
            "unsupported_reason": reason,
        }
    if synth_vars:
        synth = _build_cond_field_lookup(
            {"variables": synth_vars, "loops": []}, vel_to_cat,
            classpath=classpath, product=product,
        )
    else:
        synth = {}
    merged = dict(field_lookup)
    for n, info in {**synth, **extra}.items():
        merged.setdefault(n, info)
    return merged


def _find_field_tokens(text: str, known_names: set[str]) -> list[tuple[int, int, str]]:
    """Find $TBD_<name> tokens in text. Returns [(start, end, name)] in order.

    Longest-match against known_names (D8) so sentence punctuation after a token
    is not swallowed (`$TBD_name.` → name, not `name.`). Names absent from the
    mapping fall back to a regex match with trailing dots stripped.
    """
    out: list[tuple[int, int, str]] = []
    for m in re.finditer(r"\$TBD_", text):
        rest = text[m.end():]
        best: str | None = None
        for name in known_names:
            if rest.startswith(name) and (best is None or len(name) > len(best)):
                nxt = rest[len(name): len(name) + 1]
                if not nxt or not (nxt.isalnum() or nxt == "_"):
                    best = name
        if best is None:
            m2 = _FIELD_TOKEN_FALLBACK_RE.match(rest)
            if not m2:
                continue
            best = m2.group(0).rstrip(".")
            if not best:
                continue
        out.append((m.start(), m.end() + len(best), best))
    return out


def _analyse_cond_fields(
    cond_blocks: list[dict], field_lookup: dict[str, dict]
) -> tuple[list[dict], list[dict], list[int]]:
    """Classify field tokens inside conditional blocks.

    Returns (unresolved, unsupported, mixed_scope_block_ids):
      unresolved:  [{block_id, name}]          — no data_source; caller hard-fails (D5)
      unsupported: [{block_id, name, reason}]  — resolved but not wireable (D4)
      mixed_scope_block_ids: blocks mixing quote- and policy-scoped fields —
                   such a block renders empty in BOTH overloads.
    """
    unresolved: list[dict] = []
    unsupported: list[dict] = []
    mixed: list[int] = []
    known = set(field_lookup)
    for b in cond_blocks:
        if b.get("render") == "template":
            # Content (loop included) stays in the template — fields resolve
            # there via Leg 3, not in the plugin's conditional string.
            continue
        # N-way variant block: classify the field tokens in its variant texts +
        # default (brace form) for the report. Unsupported → WARN row; never a
        # hard fail (variant text is not path-validated at parse time).
        if b.get("variants") or b.get("default"):
            for t in [v.get("text") or "" for v in (b.get("variants") or [])] + [b.get("default") or ""]:
                for m in _FIELD_BRACE_RE.finditer(t):
                    info = field_lookup.get(m.group(1))
                    if info and info.get("unsupported_reason"):
                        unsupported.append(
                            {"block_id": b.get("id"), "name": m.group(1), "reason": info["unsupported_reason"]}
                        )
            continue
        scopes: set[str] = set()
        for _s, _e, name in _find_field_tokens(b.get("source_text") or "", known):
            info = field_lookup.get(name)
            if info is None:
                unresolved.append({"block_id": b["id"], "name": name})
            elif info.get("unsupported_reason"):
                unsupported.append(
                    {"block_id": b["id"], "name": name, "reason": info["unsupported_reason"]}
                )
            elif not info.get("data_source"):
                unresolved.append({"block_id": b["id"], "name": name})
            else:
                scopes.add(info["scope"])
        if {"quote", "policy"} <= scopes:
            mixed.append(b["id"])
    return unresolved, unsupported, mixed


# ---------------------------------------------------------------------------
# Occurrence guards — {field} occurrence symbols ($ optional, bare required,
# + one-or-more, * zero-or-more) enforced in the plugin, never the template.
# ---------------------------------------------------------------------------

_GUARD_MARKER = "// occurrence-guard:"
_COLLECTION_RETURNS = ("java.util.List", "java.util.Collection", "java.util.Set")


def _occurrence_check_exprs(guard: dict, occurrence: str) -> str:
    """Build the ||-joined null/empty checks for one guarded field.

    Each step of the accessor chain is null-checked so the guard itself can
    never NPE (segment may legitimately be null in the policy overload).
    one_or_more on a collection return adds an isEmpty() check; on a
    single-valued return a present value satisfies "1 or more" (registry
    alignment — single-valued still matches one_or_more).
    """
    root_var = guard["root_var"]
    final_ret = guard.get("final_ret") or ""
    conds = [f"{root_var} == null"]
    expr = root_var
    for p in guard["parts"]:
        expr += f".{p}()"
        conds.append(f"{expr} == null")
    if final_ret.startswith("java.util.Optional"):
        conds.append(f"{expr}.isEmpty()")
    elif occurrence == "one_or_more" and final_ret.startswith(_COLLECTION_RETURNS):
        conds.append(f"{expr}.isEmpty()")
    return " || ".join(conds)


def render_occurrence_guards(
    variables: list[dict],
    field_lookup: dict[str, dict],
    scope: str,
    list_var: str = "missingRequired",
    skip_names: set[str] | None = None,
) -> str:
    """Generate the Java occurrence-guard block for one overload.

    required and one_or_more fields wired to this scope get a null/empty
    check; any failure is collected and thrown as one IllegalStateException
    before renderingData is returned — document generation fails fast instead
    of rendering with missing required data. optional and zero_or_more fields
    need no guard (existing null-safe rendering covers them).
    """
    skip_names = skip_names or set()
    checks: list[str] = []
    for v in variables or []:
        occ = (v.get("occurrence") or "required").strip() or "required"
        if occ not in ("required", "one_or_more"):
            continue
        name = (v.get("name") or "").strip()
        if not name or name in skip_names:
            continue
        info = (field_lookup or {}).get(name) or {}
        guard = info.get("guard")
        if not guard or info.get("scope") != scope:
            continue
        checks.append(
            f"        {_GUARD_MARKER} {name} ({occ})\n"
            f"        if ({_occurrence_check_exprs(guard, occ)}) {{\n"
            f'            {list_var}.add("{name} ({occ})");\n'
            f"        }}"
        )
    if not checks:
        return ""
    header = (
        "        // Occurrence guards — declared {field} occurrence in the source document.\n"
        f"        java.util.List<String> {list_var} = new java.util.ArrayList<>();"
    )
    footer = (
        f"        if (!{list_var}.isEmpty()) {{\n"
        "            throw new IllegalStateException(\n"
        f'                    "Document data missing for required fields: "\n'
        f"                            + String.join(\", \", {list_var}));\n"
        "        }"
    )
    return "\n".join([header, *checks, footer])


def occurrence_report_rows(
    variables: list[dict], field_lookup: dict[str, dict]
) -> list[dict]:
    """Per-variable occurrence-guard status rows for the plugin report."""
    rows: list[dict] = []
    for v in variables or []:
        name = (v.get("name") or "").strip()
        if not name:
            continue
        occ = (v.get("occurrence") or "required").strip() or "required"
        info = (field_lookup or {}).get(name) or {}
        ds = (v.get("data_source") or "").strip()
        if occ in ("optional", "zero_or_more"):
            status = f"no guard needed ({occ})"
        elif not ds or ds.startswith("UNRESOLVED:"):
            status = "WARN: no guard — unresolved data_source"
        elif info.get("unsupported_reason"):
            status = f"WARN: no guard — {info['unsupported_reason']}"
        elif info.get("guard"):
            status = f"guarded ({info.get('scope')})"
        else:
            status = "WARN: no guard — not wireable"
        rows.append({"name": name, "occurrence": occ, "data_source": ds, "status": status})
    return rows


def _repo_root() -> Path:
    """Walk up from this script until a .cursor/ directory is found."""
    p = Path(__file__).resolve().parent
    for candidate in [p, *p.parents]:
        if (candidate / ".cursor").is_dir():
            return candidate
    return Path(__file__).resolve().parent.parent


def _rel(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def _load_yaml(path: Path) -> dict:
    """Load YAML, tolerating # comment-header lines Leg 2 writes."""
    lines = path.read_text(encoding="utf-8").splitlines()
    body = "\n".join(ln for ln in lines if not ln.startswith("#"))
    data = yaml.safe_load(body)
    return data if isinstance(data, dict) else {}


def _flatten_to_segment_root(suggested: dict) -> dict:
    """Normalise schema 2.0 per-root verdicts to flat scalar fields using the segment root.

    Leg 4 specifically validates paths against the segment root (D5 — MVP). For schema
    1.x files (no rendering_roots), returns the dict unchanged.
    """
    roots = suggested.get("rendering_roots") or []
    if not roots:
        return suggested

    seg_id = next((r.get("id") for r in roots if r.get("id") == "segment"), None)
    if seg_id is None:
        seg_id = roots[0].get("id")
    if not seg_id:
        return suggested

    def _promote(entry: dict) -> dict:
        verdict = (entry.get("verdicts") or {}).get(seg_id) or {}
        return {
            **entry,
            "data_source": verdict.get("data_source") or entry.get("data_source") or "",
            "confidence": verdict.get("confidence") or entry.get("confidence") or "",
            "reasoning": verdict.get("reasoning") or entry.get("reasoning") or "",
        }

    new_vars = [_promote(v) for v in (suggested.get("variables") or [])]
    return {**suggested, "variables": new_vars}


# JAR introspection (_javap / _zero_arg_methods / _unwrap_type / validate_path /
# _default_datamodel_jar / _class_exists) now lives in velocity_converter/sdk_introspect.py
# and is imported above — single source of truth shared with Leg 2 (plan P1.1).


# ---------------------------------------------------------------------------
# Java codegen
# ---------------------------------------------------------------------------


JAVA_TEMPLATE = """package com.socotra.deployment.customer;

import com.socotra.coremodel.Charge;
import com.socotra.coremodel.DocumentDataSnapshot;
import com.socotra.coremodel.Policy;
import com.socotra.coremodel.QuotePricing;
import com.socotra.coremodel.Transaction;
import com.socotra.deployment.DataFetcherFactory;
%(dynamic_imports)simport com.socotra.deployment.customer.DocumentDataSnapshotPlugin.%(invoice_request)s;
import com.socotra.deployment.customer.DocumentDataSnapshotPlugin.%(quote_request)s;
import com.socotra.deployment.customer.DocumentDataSnapshotPlugin.%(policy_request)s;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DateFormat;
import java.text.DecimalFormat;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Collections;
import java.util.Date;
import java.util.HashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Generated by velocity_converter/leg4_generate_plugin.py from %(suggested_name)s — review
 * before deploying to Socotra.
 * renderingData is a HashMap<String, Object> with named keys per request type.
 */
public class %(class_name)s implements DocumentDataSnapshotPlugin {

    private static final Logger log =
            LoggerFactory.getLogger(%(class_name)s.class);

    @Override
    public DocumentDataSnapshot dataSnapshot(%(quote_request)s request) {
        %(quote_type)s quote = request.quote();
        QuotePricing pricing = null;
        try {
            pricing = DataFetcherFactory.get().getQuotePricing(quote.locator());
        } catch (Exception e) {
            log.warn("Could not fetch quote pricing for locator={}", quote.locator(), e);
        }

        HashMap<String, Object> renderingData = new HashMap<>();
        DecimalFormat df = new DecimalFormat("0.00");
        BigDecimal premiumTotal = BigDecimal.ZERO;
        BigDecimal otherTotal = BigDecimal.ZERO;

        if (pricing != null && pricing.items() != null) {
            for (Charge item : pricing.items()) {
                if ("premium".equalsIgnoreCase(item.chargeCategory().toString())) {
                    premiumTotal = premiumTotal.add(item.amount());
                } else if (!"nonFinancial".equalsIgnoreCase(item.chargeCategory().toString())) {
                    otherTotal = otherTotal.add(item.amount());
                }
            }
        }

        BigDecimal totalBillable = premiumTotal.add(otherTotal);
        HashMap<String, Object> enhancedPricing = new HashMap<>();
        enhancedPricing.put("premiumTotal", df.format(premiumTotal));
        enhancedPricing.put("otherTotal", df.format(otherTotal));
        enhancedPricing.put("totalBillable", df.format(totalBillable));

        renderingData.put("quote", quote);
        renderingData.put("pricing", enhancedPricing);
        renderingData.put("productType", "%(product)s");
%(quote_datafetcher_extras)s%(quote_conditional_puts)s%(quote_occurrence_guards)s
        return DocumentDataSnapshot.builder()
                .renderingData(renderingData)
                .build();
    }

    @Override
    public DocumentDataSnapshot dataSnapshot(%(policy_request)s request) {
        Policy policy = request.policy();
        Transaction transaction = request.transaction();
        %(segment_type)s segment = request.segment().orElse(null);

        if (segment == null) {
            log.error("Segment is missing in the %(product)s request");
        }

        HashMap<String, Object> renderingData = new HashMap<>();
        String pattern = "MM/dd/yyyy";
        DateFormat dateFormatter = new SimpleDateFormat(pattern);
        Date today = Calendar.getInstance().getTime();
        String todayAsString = dateFormatter.format(today);

        renderingData.put("todayAsString", todayAsString);
        renderingData.put("policy", policy);
        renderingData.put("transaction", transaction);
        renderingData.put("segment", segment);
        renderingData.put("productType", "%(product)s");
%(policy_datafetcher_extras)s%(policy_conditional_puts)s%(policy_occurrence_guards)s
        return DocumentDataSnapshot.builder()
                .renderingData(renderingData)
                .build();
    }

    @Override
    public DocumentDataSnapshot dataSnapshot(%(invoice_request)s request) {
        // TODO: invoice-scoped renderingData when invoice documents use this pipeline
        log.warn("Invoice document data snapshot not implemented — returning empty renderingData");
        return DocumentDataSnapshot.builder()
                .renderingData(Collections.emptyMap())
                .build();
    }
}
"""


_LEGACY_PRICING_KEYS = frozenset({"pricing"})


# ---------------------------------------------------------------------------
# Additive plugin update helpers (plan Leg4-additive-plugin-update)
# ---------------------------------------------------------------------------


def _parse_existing_plugin_keys(java_path: Path) -> set[str]:
    """Extract all renderingData.put("key", ...) literal keys from an existing Java file."""
    if not java_path.exists():
        return set()
    return set(re.findall(r'renderingData\.put\("([^"]+)"', java_path.read_text(encoding="utf-8")))


def parse_plugin_keys(java_path: Path) -> dict:
    """Parse and validate an existing SnapshotPlugin .java file.

    Returns a dict with:
      existing_keys: set[str]  — string literals from renderingData.put("key", ...) calls
      cond_high_water: int     — highest condN index found (0 if none)
      is_valid: bool           — False if structure is unrecognisable or has errors
      errors: list[str]        — human-readable validation errors
    """
    errors: list[str] = []

    try:
        text = java_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return {
            "existing_keys": set(),
            "cond_high_water": 0,
            "is_valid": False,
            "errors": [f"File is not valid UTF-8: {exc}"],
        }

    if not text.strip():
        return {
            "existing_keys": set(),
            "cond_high_water": 0,
            "is_valid": False,
            "errors": ["File is empty"],
        }

    # The generated template uses DocumentDataSnapshot.builder(), not renderingData.builder()
    if "DocumentDataSnapshot.builder()" not in text:
        errors.append("Builder pattern not found: missing 'DocumentDataSnapshot.builder()'")
    if ".build()" not in text:
        errors.append("Builder pattern not found: missing '.build()'")

    put_re = re.compile(r'renderingData\.put\(\s*"([^"]+)"')
    bad_put_re = re.compile(r'renderingData\.put\(\s*(?!")')

    all_seen_keys: set[str] = set()
    bad_lines: list[int] = []

    # Duplicate detection is per renderingData scope — each overload has its own HashMap
    # so identical keys across overloads are intentional (not duplicates).
    current_scope: dict[str, list[int]] = {}
    scope_active = False

    for lineno, line in enumerate(text.splitlines(), 1):
        if "renderingData" in line and "new HashMap<>()" in line:
            if scope_active:
                for key, lnos in current_scope.items():
                    if len(lnos) > 1:
                        errors.append(
                            f'Duplicate key "{key}" on lines {" and ".join(str(n) for n in lnos)}'
                        )
            current_scope = {}
            scope_active = True
            continue

        for m in put_re.finditer(line):
            key = m.group(1)
            all_seen_keys.add(key)
            if scope_active:
                current_scope.setdefault(key, []).append(lineno)

        for _ in bad_put_re.finditer(line):
            bad_lines.append(lineno)

    if scope_active:
        for key, lnos in current_scope.items():
            if len(lnos) > 1:
                errors.append(
                    f'Duplicate key "{key}" on lines {" and ".join(str(n) for n in lnos)}'
                )

    if not all_seen_keys and not bad_lines:
        errors.append("No renderingData.put() calls found")

    for lineno in bad_lines:
        errors.append(f"put() call on line {lineno} has wrong argument format (not a quoted key)")

    cond_nums = [int(k[4:]) for k in all_seen_keys if re.fullmatch(r"cond\d+", k)]
    cond_high_water = max(cond_nums, default=0)

    return {
        "existing_keys": all_seen_keys,
        "cond_high_water": cond_high_water,
        "is_valid": len(errors) == 0,
        "errors": errors,
    }


def _required_keys(suggested: dict, cond_blocks: list[dict]) -> dict[str, str]:
    """Return {key: root_id | "cond"} for DataFetcher variables and conditional blocks.

    Uses local conditional IDs; offsetting happens in _diff_keys.
    """
    result: dict[str, str] = {}
    rendering_roots = suggested.get("rendering_roots") or []
    root_ids = [r.get("id") for r in rendering_roots] if rendering_roots else ["segment"]

    for v in (suggested.get("variables") or []):
        cand = v.get("candidate") or {}
        if cand.get("source") != "datafetcher":
            continue
        key = cand.get("datafetcher_key", "")
        if not key:
            continue
        root_id = root_ids[0] if root_ids else "segment"
        for rid in root_ids:
            verdict = (v.get("verdicts") or {}).get(rid) or {}
            if verdict.get("data_source"):
                root_id = rid
                break
        result[key] = root_id

    # Positional binary blocks only — named variant blocks (incl. default-only
    # ones, which carry a placeholder) merge by name at the additive site
    # (§1a: named keys don't collide by position, no renumber).
    for b in cond_blocks:
        if not b.get("variants") and not b.get("placeholder"):
            result[f"cond{b['id']}"] = "cond"

    return result


def _diff_keys(
    required: dict[str, str],
    existing_keys: set[str],
    cond_high_water: int,
) -> tuple[dict[str, str], list[tuple[int, int]]]:
    """Compute missing variable keys and offset conditional IDs.

    Returns:
        missing_vars: {key: root_id} for non-conditional keys absent from existing_keys.
        missing_conds: [(local_id, global_id), ...] — all new form's cond blocks with
                       global IDs = cond_high_water + local_id (always added; form-local).
    """
    missing_vars: dict[str, str] = {}
    missing_conds: list[tuple[int, int]] = []

    for key, root_id in required.items():
        if root_id == "cond":
            local_id = int(key[4:])
            missing_conds.append((local_id, cond_high_water + local_id))
        elif key not in existing_keys:
            missing_vars[key] = root_id

    return missing_vars, missing_conds


def _append_to_plugin(
    java_path: Path,
    missing_quote_df: list[dict],
    missing_policy_df: list[dict],
    offset_cond_blocks: list[dict],
    field_lookup: dict[str, dict] | None = None,
    quote_guard_code: str = "",
    policy_guard_code: str = "",
) -> None:
    """Write a backup then insert missing puts before each overload's builder return.

    Quote DataFetcher calls → quote overload.
    Policy DataFetcher calls → policy overload.
    Conditional puts → both overloads (document-scoped, decision A4).
    Occurrence guards (pre-rendered with deduped names/list var) go last so the
    throw stays adjacent to the builder return.
    Also inserts any new dynamic imports needed for new DataFetcher return types,
    and java.util.Objects when conditional field concatenation is generated.
    """
    quote_df_code = _generate_datafetcher_extras(missing_quote_df)
    policy_df_code = _generate_datafetcher_extras(missing_policy_df)
    quote_cond_code = render_conditional_puts(offset_cond_blocks, scope="quote", field_lookup=field_lookup)
    policy_cond_code = render_conditional_puts(offset_cond_blocks, scope="policy", field_lookup=field_lookup)

    if not any((quote_df_code, policy_df_code, quote_cond_code,
                quote_guard_code, policy_guard_code)):
        return

    bak = java_path.with_suffix(".java.bak")
    bak.write_bytes(java_path.read_bytes())

    text = java_path.read_text(encoding="utf-8")

    # Insert missing dynamic imports for new DataFetcher return types.
    new_imports = _generate_dynamic_imports(missing_quote_df + missing_policy_df)
    if "Objects.toString(" in quote_cond_code + policy_cond_code:
        new_imports = (new_imports + "\n" if new_imports else "") + "import java.util.Objects;"
    if new_imports:
        for imp_line in new_imports.splitlines():
            if imp_line and imp_line not in text:
                # Insert before the first 'import' line in the file.
                first_import = text.find("\nimport ")
                if first_import != -1:
                    text = text[: first_import + 1] + imp_line + "\n" + text[first_import + 1 :]

    RETURN_MARKER = "        return DocumentDataSnapshot.builder()"
    positions: list[int] = []
    start = 0
    while True:
        pos = text.find(RETURN_MARKER, start)
        if pos == -1:
            break
        positions.append(pos)
        start = pos + 1

    if len(positions) < 2:
        raise RuntimeError(
            f"Expected ≥2 'return DocumentDataSnapshot.builder()' in {java_path.name}; "
            f"found {len(positions)}. Cannot append safely."
        )

    def _join_inserts(*parts: str) -> str:
        joined = "\n".join(p for p in parts if p)
        return ("\n" + joined + "\n") if joined else ""

    quote_insert = _join_inserts(quote_df_code, quote_cond_code, quote_guard_code)
    policy_insert = _join_inserts(policy_df_code, policy_cond_code, policy_guard_code)

    # Insert policy first (later in file) so positions[0] stays valid.
    if policy_insert:
        text = text[: positions[1]] + policy_insert + text[positions[1] :]
    if quote_insert:
        text = text[: positions[0]] + quote_insert + text[positions[0] :]

    java_path.write_text(text, encoding="utf-8")


def _collect_datafetcher_calls(
    suggested: dict, root_id: str, classpath: str, skip_keys: frozenset = frozenset()
) -> list[dict]:
    """Return deduplicated DataFetcher calls for the given root from the suggested mapping.

    Only includes entries where candidate.source == 'datafetcher' AND the verdict for
    root_id is high or medium confidence. Keys in skip_keys are excluded (used to avoid
    duplicating legacy hardcoded puts like 'pricing').
    """
    seen: dict[str, dict] = {}
    for v in (suggested.get("variables") or []):
        cand = v.get("candidate") or {}
        if cand.get("source") != "datafetcher":
            continue
        # Object-level fetch is only valid on the roots the registry declares
        # (e.g. getQuotePricing is quote-only) — never wire it into an overload
        # whose locals can't supply the arg.
        valid_roots = cand.get("valid_roots")
        if valid_roots and root_id not in valid_roots:
            continue
        verdict = (v.get("verdicts") or {}).get(root_id) or {}
        if not (v.get("data_source") or "").strip():
            continue
        key = cand.get("datafetcher_key", "")
        method = cand.get("datafetcher_method", "")
        arg_raw = cand.get("datafetcher_arg", "")
        arg = arg_raw.get(root_id, "") if isinstance(arg_raw, dict) else str(arg_raw)
        if key and method and key not in seen and key not in skip_keys:
            seen[key] = {"key": key, "method": method, "arg": arg}

    result = []
    for info in seen.values():
        raw_ret = _method_return_type(classpath, DATAFETCHER_INTERFACE, info["method"])
        fqcn = _unwrap_type(raw_ret) if raw_ret else None
        short = fqcn.rsplit(".", 1)[-1] if fqcn else "Object"
        result.append({
            "key": info["key"],
            "method": info["method"],
            "arg": info["arg"],
            "return_type": short,
            "return_fqcn": fqcn or "",
        })
    return result


def _generate_datafetcher_extras(calls: list[dict]) -> str:
    """Generate null-guarded DataFetcher put blocks (indented 8 spaces)."""
    if not calls:
        return ""
    blocks = []
    for c in calls:
        key, method, arg, ret = c["key"], c["method"], c["arg"], c["return_type"]
        blocks.append(
            f"        {ret} {key} = null;\n"
            f"        try {{\n"
            f"            {key} = DataFetcherFactory.get().{method}({arg});\n"
            f"        }} catch (Exception e) {{\n"
            f"            log.warn(\"Could not fetch {key} for locator={{}}\", {arg}, e);\n"
            f"        }}\n"
            f"        if ({key} != null) {{\n"
            f"            renderingData.put(\"{key}\", {key});\n"
            f"        }}"
        )
    return "\n".join(blocks)


def _generate_dynamic_imports(all_calls: list[dict]) -> str:
    fqcns = sorted({
        c["return_fqcn"] for c in all_calls
        if c["return_fqcn"] and c["return_type"] != "Object"
    })
    return "\n".join(f"import {fqcn};" for fqcn in fqcns)


def load_conditional_registry(yaml_path: Path) -> list[dict]:
    """Load + validate conditional-registry.yaml. Returns [] if absent or empty.

    Raises models.ContractError (with the offending entries named) on a
    malformed registry instead of a bare KeyError.
    """
    if not yaml_path.exists():
        return []
    rows = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or []
    registry = validate_contract(
        rows, ConditionalRegistry, artifact="conditional-registry.yaml", path=yaml_path
    )
    out: list[dict] = []
    for b in registry.root:
        block = {
            "id": b.id,
            "source_text": b.source_text,
            "parent_id": b.parent_id,
            "depth": b.depth,
            "conditions": b.conditions,
            "operator": b.operator,
            "render": b.render,
        }
        # §1a / N-way: carry the named key + variant payload when present. A
        # binary block keeps no explicit key so block_key() falls back to
        # cond<id> (and additive offsetting can rewrite its id freely).
        if b.variants or b.placeholder:
            block["key"] = b.key
            block["placeholder"] = b.placeholder
            block["variant"] = True
            block["scope"] = b.scope
            block["default"] = b.default
            block["variants"] = [
                {"when": dict(v.when), "text": v.text} for v in (b.variants or [])
            ]
        out.append(block)
    return out


def _count_annotated_conditionals(out_dir: Path, stem: str) -> int:
    """Count unique $doc.condN markers in {stem}.annotated.html. Returns 0 if file absent."""
    annotated = out_dir / f"{stem}.annotated.html"
    if not annotated.exists():
        return 0
    return len(set(re.findall(r'\$doc\.[A-Za-z_]\w*', annotated.read_text(encoding="utf-8"))))


def _topo_sort_cond_blocks(blocks: list[dict]) -> list[dict]:
    """Return blocks sorted so dependencies (referenced via $doc.<key>) come first.

    Keyed by the block's named key (§1a) so it is robust to variant blocks that
    carry a token key instead of a numeric id.
    """
    key_map = {block_key(b): b for b in blocks}
    visited: set[str] = set()
    result: list[dict] = []

    def _deps(block: dict) -> list[str]:
        return re.findall(r'\$doc\.([A-Za-z_]\w*)', block.get("source_text") or "")

    def visit(key: str) -> None:
        if key in visited:
            return
        visited.add(key)
        b = key_map.get(key)
        if b:
            for dep_key in _deps(b):
                visit(dep_key)
            result.append(b)

    for b in blocks:
        visit(block_key(b))
    return result


def _source_text_to_java(source_text: str, field_exprs: dict[str, str] | None = None) -> str:
    """Escape source_text for a Java string literal, replacing $doc.condN refs with concat.

    field_exprs maps a field name to its Java expression; matching $TBD_<name>
    tokens become string concatenation (`" + <expr> + "`). Tokens for names not
    in field_exprs are left literal (the caller flags them in the report).
    """
    escaped = source_text.replace("\\", "\\\\").replace('"', '\\"')
    if field_exprs:
        # Escaping never alters $TBD_ tokens, so spans found here are stable.
        spans = _find_field_tokens(escaped, set(field_exprs))
        for start, end, name in reversed(spans):
            expr = field_exprs.get(name)
            if expr:
                escaped = escaped[:start] + f'" + {expr} + "' + escaped[end:]
    # Replace $doc.<key> with Java variable concatenation (the local is named
    # after the key; binary keys are cond<id> → byte-identical to before).
    result = re.sub(r'\$doc\.([A-Za-z_]\w*)', lambda m: f'" + {m.group(1)} + "', escaped)
    result = '"' + result + '"'
    # Drop empty string segments produced by refs at string boundaries
    result = re.sub(r'"" \+ ', '', result)
    result = re.sub(r' \+ ""', '', result)
    return result


# Variant text from the CSV carries {field} braces (the customer never sees the
# $TBD_ machine form). Normalise to the $TBD_ tokens the field wiring expects;
# occurrence symbols ({$x}/{+x}/{*x}) are stripped like Leg 0 does.
_FIELD_BRACE_RE = re.compile(r"\{[$+*]?([A-Za-z_][\w.]*)\}")


def _braces_to_tbd_text(text: str) -> str:
    return _FIELD_BRACE_RE.sub(lambda m: "$TBD_" + m.group(1), text or "")


def _classify_text_fields(
    text: str, field_lookup: dict[str, dict], scope: str
) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """Split a baked text's $TBD_ tokens into wired field_exprs vs TODO literals.

    Mirrors render_conditional_puts' binary-block classification so variant text
    wires the same way: in-scope supported field → Java accessor concat; anything
    else (unsupported, unresolved, other-scope) stays a literal {token} with a
    TODO reason (D4 parity).
    """
    field_exprs: dict[str, str] = {}
    todo: list[tuple[str, str]] = []
    for _s, _e, name in _find_field_tokens(text or "", set(field_lookup)):
        info = field_lookup.get(name)
        if info is None or not (info.get("data_source") or info.get("unsupported_reason")):
            todo.append((name, "unresolved data_source"))
        elif info.get("unsupported_reason"):
            todo.append((name, info["unsupported_reason"]))
        elif info.get("scope") != scope:
            todo.append((name, f"{info.get('scope')}-scoped field, n/a in {scope} context"))
        else:
            field_exprs[name] = info["java_expr"]
    return field_exprs, todo


def _render_variant_puts(block: dict, scope: str, field_lookup: dict[str, dict] | None) -> str:
    """Render an N-way variant block to an if/else-if chain (the 50-state feature).

    First-match-wins: each variant's ``when`` AST becomes a null-safe boolean via
    condition_to_java; the matching body bakes that variant's text (field tokens
    wired per variant, exactly like the binary path); a trailing ``else`` bakes
    the default. A block whose scope is the *other* overload emits an empty put
    so the generated Java never references locals absent from this scope (D6).
    """
    field_lookup = field_lookup or {}
    key = block_key(block)
    bid = block.get("id", key)
    placeholder = block.get("placeholder") or key
    variants = block.get("variants") or []
    block_scope = (block.get("scope") or "").strip()

    if block_scope and block_scope != scope:
        return (
            f'        // Conditional block {bid} (variant ${placeholder}): '
            f'{block_scope}-scoped, n/a in {scope} context\n'
            f'        renderingData.put("{key}", "");'
        )

    todo_all: list[tuple[str, str]] = []
    branches: list[str] = []
    for i, v in enumerate(variants):
        ast = ast_from_dict(v.get("when") or {})
        java_cond = condition_to_java(ast, scope)
        text_tbd = _braces_to_tbd_text(v.get("text") or "")
        field_exprs, todo = _classify_text_fields(text_tbd, field_lookup, scope)
        todo_all.extend(todo)
        java_val = _source_text_to_java(text_tbd, field_exprs)
        keyword = "if" if i == 0 else "} else if"
        branches.append(f"        {keyword} ({java_cond}) {{\n            {key} = {java_val};")

    default_text = block.get("default")
    if default_text:
        default_tbd = _braces_to_tbd_text(default_text)
        d_exprs, d_todo = _classify_text_fields(default_tbd, field_lookup, scope)
        todo_all.extend(d_todo)
        java_default = _source_text_to_java(default_tbd, d_exprs)
        if variants:
            branches.append(f"        }} else {{\n            {key} = {java_default};")
        else:
            # Default-only block (no conditioned rows): assign the text
            # unconditionally — there is no if-chain to attach an `else` to.
            branches.append(f"        {key} = {java_default};")

    todo_comment = "".join(
        f'        // TODO: field {name} not wired — {reason}\n'
        for name, reason in dict(todo_all).items()
    )
    chain = "\n".join(branches)
    # Only the conditioned (if/else-if) chain opens a brace block to close.
    close = "        }" if variants else ""
    return (
        f'        // Conditional block {bid} (variant ${placeholder}): '
        f'{len(variants)} variant(s) + default\n'
        f'{todo_comment}'
        f'        String {key} = "";\n'
        f'{chain}\n'
        f'{close}\n'
        f'        renderingData.put("{key}", {key});'
    )


def _render_template_put(block: dict, scope: str, bid, key: str, truncated: str) -> str:
    """Render a ``render: template`` block to a single Boolean put.

    The loop/prose stays in the template under ``#if($data.<key>)`` — the plugin
    only supplies the Boolean. Condition source: the variants-only flow carries a
    single ``when`` AST in ``variants[0]`` (scope computed at parse time); legacy
    registries carry ``conditions[]``/``operator``. A scope-blocked or unfilled
    condition puts ``false`` (an empty string is truthy in Velocity's ``#if``).
    """
    variants = block.get("variants") or []
    if variants:  # variants-only flow: a single resolved `when` AST.
        block_scope = (block.get("scope") or "").strip()
        if block_scope and block_scope != scope:
            return (
                f'        // Conditional block {bid} (template-rendered): '
                f'{block_scope}-scoped, n/a in {scope} context\n'
                f'        renderingData.put("{key}", false);'
            )
        ast = ast_from_dict(variants[0].get("when") or {})
        java_cond = condition_to_java(ast, scope)
        return (
            f'        // Conditional block {bid} (template-rendered): {truncated}\n'
            f'        renderingData.put("{key}", {java_cond});'
        )

    # Legacy conditions[]/operator path (old registries, pre-variants-only).
    raw_conds = block.get("conditions") or []
    quote_scoped = any(c.strip().startswith("quote.") for c in raw_conds)
    policy_scoped = any(c.strip().startswith("policy.") for c in raw_conds)
    if raw_conds and scope == "policy" and quote_scoped:
        return (
            f'        // Conditional block {bid} (template-rendered): quote-scoped, n/a in policy context\n'
            f'        renderingData.put("{key}", false);'
        )
    if raw_conds and scope == "quote" and policy_scoped:
        return (
            f'        // Conditional block {bid} (template-rendered): policy-scoped condition(s), n/a in quote context\n'
            f'        renderingData.put("{key}", false);'
        )
    if raw_conds:
        joiner = " || " if block.get("operator") == "OR" else " && "
        java_cond = joiner.join(
            _accessor_to_java(_rewrite_condition_root(c, scope)) for c in raw_conds
        )
        return (
            f'        // Conditional block {bid} (template-rendered): {truncated}\n'
            f'        renderingData.put("{key}", {java_cond});'
        )
    return (
        f'        // TODO: fill conditions for {key} in conditional-registry.yaml\n'
        f'        // (template-rendered) {truncated}\n'
        f'        renderingData.put("{key}", false);'
    )


def render_conditional_puts(
    blocks: list[dict], scope: str = "quote", field_lookup: dict[str, dict] | None = None
) -> str:
    """Generate renderingData.put(...) lines for conditional blocks.

    scope: "quote" emits full if-conditions; "policy" emits empty puts for any
    condition that references quote.* (which is out of scope in that overload).
    field_lookup (plan 10) wires $TBD_<name> tokens in source_text to Java
    accessor concatenation. A block whose fields belong to the *other* overload
    gets an empty put (mirror of the quote-scoped-condition treatment, D6);
    unsupported fields stay literal with a TODO comment (D4).
    Blocks are topologically sorted so any $doc.condN reference in source_text
    points to a Java variable already declared earlier in the method.
    """
    if not blocks:
        return ""
    field_lookup = field_lookup or {}
    known_names = set(field_lookup)
    sorted_blocks = _topo_sort_cond_blocks(blocks)
    lines = []
    for b in sorted_blocks:
        bid = b["id"]
        key = block_key(b)
        preview = _tbd_preview(b["source_text"])
        truncated = preview[:60] + ("..." if len(preview) > 60 else "")
        raw_conds = b.get("conditions") or []

        # Template-rendered block (contains a loop): the loop/prose stays in the
        # template under #if($data.<key>); the plugin supplies only the Boolean.
        # Checked before the variants branch — the new flow carries the single
        # `when` as a one-entry variants payload, so order matters.
        if b.get("render") == "template":
            lines.append(_render_template_put(b, scope, bid, key, truncated))
            continue

        # N-way variant block (the 50-state feature) + folded binary blocks: an
        # if/else-if chain selecting one text by data, with a trailing default.
        # A default-only named variant (placeholder set, no conditioned rows)
        # also routes here — it renders its default text unconditionally.
        if b.get("variants") or b.get("placeholder"):
            lines.append(_render_variant_puts(b, scope, field_lookup))
            continue

        quote_scoped = any(c.strip().startswith("quote.") for c in raw_conds)
        policy_scoped = any(c.strip().startswith("policy.") for c in raw_conds)

        # Classify this block's field tokens for the current scope.
        field_exprs: dict[str, str] = {}
        todo_fields: list[tuple[str, str]] = []
        other_scope_fields: list[str] = []
        for _s, _e, name in _find_field_tokens(b.get("source_text") or "", known_names):
            info = field_lookup.get(name)
            if info is None or not (info.get("data_source") or info.get("unsupported_reason")):
                # Unresolved — main hard-fails before rendering; keep literal defensively.
                todo_fields.append((name, "unresolved data_source"))
            elif info.get("unsupported_reason"):
                todo_fields.append((name, info["unsupported_reason"]))
            elif info["scope"] != scope:
                other_scope_fields.append(name)
            else:
                field_exprs[name] = info["java_expr"]

        # A block belongs to one overload: the other gets an empty put so the
        # generated Java never references locals that don't exist in its scope.
        blocked_reason = ""
        if raw_conds and scope == "policy" and quote_scoped:
            blocked_reason = "quote-scoped, n/a in policy context"
        elif raw_conds and scope == "quote" and policy_scoped:
            blocked_reason = "policy-scoped condition(s), n/a in quote context"
        elif raw_conds and other_scope_fields:
            other = "policy" if scope == "quote" else "quote"
            blocked_reason = (
                f"contains {other}-scoped field(s) "
                f'({", ".join(sorted(set(other_scope_fields)))}), n/a in {scope} context'
            )

        if raw_conds and not blocked_reason:
            joiner = " || " if b["operator"] == "OR" else " && "
            java_cond = joiner.join(
                _accessor_to_java(_rewrite_condition_root(c, scope)) for c in raw_conds
            )
            java_val = _source_text_to_java(b["source_text"], field_exprs)
            todo_comment = "".join(
                f'        // TODO: field {name} not wired — {reason}\n'
                for name, reason in todo_fields
            )
            lines.append(
                f'        // Conditional block {bid}: {truncated}\n'
                f'{todo_comment}'
                f'        String {key} = "";\n'
                f'        if ({java_cond}) {{\n'
                f'            {key} = {java_val};\n'
                f'        }}\n'
                f'        renderingData.put("{key}", {key});'
            )
        elif raw_conds:
            lines.append(
                f'        // Conditional block {bid}: {blocked_reason}\n'
                f'        renderingData.put("{key}", "");'
            )
        else:
            parent_note = f" — child of cond{b['parent_id']}, guard inside parent if-block" if b.get("parent_id") else ""
            lines.append(
                f'        // TODO: fill conditions for {key} in conditional-registry.yaml{parent_note}\n'
                f'        // {truncated}\n'
                f'        renderingData.put("{key}", "");'
            )
    return "\n".join(lines)


def render_java(
    product: str,
    suggested_name: str,
    quote_df_calls: list[dict] | None = None,
    policy_df_calls: list[dict] | None = None,
    cond_blocks: list[dict] | None = None,
    field_lookup: dict[str, dict] | None = None,
    variables: list[dict] | None = None,
) -> str:
    quote_extras = _generate_datafetcher_extras(quote_df_calls or [])
    policy_extras = _generate_datafetcher_extras(policy_df_calls or [])
    all_calls = (quote_df_calls or []) + (policy_df_calls or [])
    dyn_imports = _generate_dynamic_imports(all_calls)
    quote_cond_puts = render_conditional_puts(cond_blocks or [], scope="quote", field_lookup=field_lookup)
    policy_cond_puts = render_conditional_puts(cond_blocks or [], scope="policy", field_lookup=field_lookup)
    quote_guards = render_occurrence_guards(variables or [], field_lookup or {}, scope="quote")
    policy_guards = render_occurrence_guards(variables or [], field_lookup or {}, scope="policy")
    if "Objects.toString(" in quote_cond_puts + policy_cond_puts:
        dyn_imports = (dyn_imports + "\n" if dyn_imports else "") + "import java.util.Objects;"
    if dyn_imports:
        dyn_imports = dyn_imports + "\n"
    return JAVA_TEMPLATE % {
        "class_name": f"{product}DocumentDataSnapshotPluginImpl",
        "quote_request": f"{product}QuoteRequest",
        "quote_type": f"{product}Quote",
        "policy_request": f"{product}Request",
        "invoice_request": INVOICE_REQUEST,
        "segment_type": f"{product}Segment",
        "product": product,
        "suggested_name": suggested_name,
        "quote_datafetcher_extras": ("\n" + quote_extras) if quote_extras else "",
        "policy_datafetcher_extras": ("\n" + policy_extras) if policy_extras else "",
        "quote_conditional_puts": ("\n" + quote_cond_puts) if quote_cond_puts else "",
        "policy_conditional_puts": ("\n" + policy_cond_puts) if policy_cond_puts else "",
        "quote_occurrence_guards": ("\n" + quote_guards) if quote_guards else "",
        "policy_occurrence_guards": ("\n" + policy_guards) if policy_guards else "",
        "dynamic_imports": dyn_imports,
    }


# ---------------------------------------------------------------------------
# Report writer (plan §13)
# ---------------------------------------------------------------------------


def write_report(
    report_path: Path,
    *,
    stem: str,
    product: str,
    suggested_path: Path,
    java_path: Path,
    high_results: list[tuple[dict, str, str]],
    ignored_vars: list[dict],
    compile_status: str | None,
    compile_detail: str,
    generated_at: str,
    cond_blocks: list[dict] | None = None,
    additive_summary: dict | None = None,
    cond_field_rows: list[dict] | None = None,
    occurrence_rows: list[dict] | None = None,
) -> None:
    seg = f"{product}Segment"
    quote = f"{product}Quote"
    lines: list[str] = [
        "<!-- leg4_schema_version: 1.0 -->",
        "",
        f"# Leg 4 Plugin Report — {stem}",
        "",
        "| | |",
        "|---|---|",
        f"| **Product** | {product} |",
        f"| **Suggested mapping** | `{suggested_path.name}` |",
        f"| **Generated Java** | `{java_path.name}` |",
        f"| **Generated** | {generated_at} |",
        "",
        "---",
        "",
    ]
    if additive_summary is not None:
        preflight = additive_summary.get("preflight") or {}
        pf_errors = preflight.get("errors") or []
        pf_key_count = len(preflight.get("existing_keys") or set())
        pf_cond_hw = preflight.get("cond_high_water", 0)
        builder_ok = not any("DocumentDataSnapshot.builder()" in e for e in pf_errors)
        dup_errors = [e for e in pf_errors if e.startswith("Duplicate key")]
        lines += [
            "## Pre-flight validation (additive mode)",
            "",
            "| Check | Result |",
            "|-------|--------|",
            f"| Builder pattern found | {'✓' if builder_ok else '✗'} |",
            f"| Duplicate keys | {'None' if not dup_errors else '; '.join(dup_errors)} |",
            f"| Existing keys | {pf_key_count} |",
            f"| Highest condN | {pf_cond_hw} |",
            "",
            "---",
            "",
        ]
    lines += [
        "## Rendering strategy",
        "",
        f"renderingData is a `HashMap<String, Object>` with named keys per request type:",
        "",
        f"- **Quote request** — `\"quote\"` (`{quote}`), `\"pricing\"` (enriched totals), `\"productType\"`",
        f"  Velocity: `$data.quote.*`, `$data.pricing.*`",
        f"- **Policy request** — `\"policy\"` (`Policy`), `\"transaction\"` (`Transaction`), "
        f"`\"segment\"` (`{seg}`), `\"todayAsString\"`, `\"productType\"`",
        f"  Velocity: `$data.policy.*`, `$data.transaction.*`, `$data.segment.*`",
        "",
        "---",
        "",
        f"## Resolved paths (validated against `{seg}` or `{quote}`) ({len(high_results)})",
        "",
    ]
    if high_results:
        lines += [
            "| Variable | data_source | javap | detail |",
            "|---|---|---|---|",
        ]
        for v, status, detail in high_results:
            name = v.get("name") or ""
            ds = v.get("data_source") or ""
            lines.append(f"| {name} | `{ds}` | {status} | {detail} |")
        if any(s == "warning" for _, s, _ in high_results):
            lines += [
                "",
                "> **Warnings are non-fatal.** A warning means the path was not found via "
                "`javap`. The field may exist on the live model but not be visible through "
                "javap introspection, or must be supplied by a future plugin enhancement "
                "(`next-action: supply-from-plugin`).",
            ]
    else:
        lines.append("_No resolved variables with a data_source._")
    lines += ["", "---", ""]

    lines += [
        f"## Unresolved — no data_source ({len(ignored_vars)})",
        "",
        "These variables have no data_source and were not wired into the plugin. "
        "Assign a path in the `.mapping.yaml` and re-run Leg 4.",
        "",
        "| Variable | data_source |",
        "|---|---|",
    ]
    for v in ignored_vars:
        name = v.get("name") or ""
        ds = v.get("data_source") or ""
        lines.append(f"| {name} | `{ds or '(empty)'}` |")
    lines += ["", "---", ""]

    lines += ["## Compile check", ""]
    if compile_status is None:
        lines.append("_Skipped — re-run with `--compile-check` to verify against the JARs._")
    else:
        lines.append(f"**{compile_status}**")
        if compile_detail:
            lines += ["", "```", compile_detail.strip(), "```"]
    lines += [""]

    if additive_summary is not None:
        added_keys = sorted(additive_summary.get("keys_added") or [])
        new_cond_ids = sorted(additive_summary.get("new_cond_ids") or [])
        cond_range = (
            f"{new_cond_ids[0]}–{new_cond_ids[-1]}"
            if len(new_cond_ids) > 1
            else (str(new_cond_ids[0]) if new_cond_ids else "none")
        )
        lines += [
            "---",
            "",
            "## Additive update summary",
            "",
            "| | |",
            "|---|---|",
            f"| Keys already present | {additive_summary.get('keys_already_present', 0)} |",
            f"| Keys added this run | {len(added_keys)} |",
            f"| Conditional high water before | {additive_summary.get('cond_high_water_before', 0)} |",
            f"| New conditional IDs assigned | {cond_range} |",
            "",
        ]
        if added_keys:
            lines += ["**Newly added keys:** " + ", ".join(f"`{k}`" for k in added_keys), ""]

    cond_blocks = cond_blocks or []
    lines += ["---", "", f"## Conditional blocks ({len(cond_blocks)} total)", ""]
    if cond_blocks:
        lines += ["| id | depth | parent_id | source_text | conditions | status |", "|---|---|---|---|---|---|"]
        for b in cond_blocks:
            truncated = b["source_text"][:60] + ("..." if len(b["source_text"]) > 60 else "")
            status = "wired" if b["conditions"] else "TODO"
            conds = " \\| ".join(b["conditions"]) if b["conditions"] else "(empty)"
            parent_id = b.get("parent_id") or ""
            depth = b.get("depth", 0)
            lines.append(f"| {b['id']} | {depth} | {parent_id} | {truncated} | `{conds}` | **{status}** |")
    else:
        report_out_dir = report_path.parent
        n_conds = _count_annotated_conditionals(report_out_dir, stem)
        if n_conds > 0:
            csv_path = action_needed_dir(report_out_dir) / f"{stem}.variants.csv"
            if csv_path.exists():
                fix_cmd = (
                    f"python3 -m velocity_converter.leg0_ingest "
                    f"--parse-variants-csv {csv_path} "
                    f"--output-dir {report_out_dir}"
                )
            else:
                fix_cmd = "(variants.csv not found — re-run Leg 0 first)"
            lines.append(
                f"> ⚠ WARNING: {n_conds} conditional(s) detected in `{stem}.annotated.html` "
                f"but no `conditional-registry.yaml` was found — all conditionals were omitted from the plugin.\n"
                f"> Fix: `{fix_cmd}`"
            )
        else:
            lines.append("_No conditional-registry.yaml found alongside this .mapping.yaml._")
    lines += [""]

    cond_field_rows = cond_field_rows or []
    if cond_field_rows:
        warn_count = sum(1 for r in cond_field_rows if r["status"].startswith("WARN"))
        lines += [
            "---",
            "",
            f"## Field tokens inside conditional blocks ({len(cond_field_rows)})",
            "",
            "Fields referenced inside `[[...]]` blocks are concatenated into the plugin's",
            "conditional strings (the template only outputs `${data.condN}`). Java renders",
            "values via `Objects.toString(...)` — formatted fields (BigDecimal, dates) may",
            "need a custom format call.",
            "",
            "| Block | Field | data_source | Status |",
            "|---|---|---|---|",
        ]
        for r in cond_field_rows:
            ds = r.get("data_source") or "(empty)"
            status = r["status"]
            if status.startswith("WARN"):
                status = f"⚠ **{status}**"
            lines.append(f"| {r['block_id']} | {r['name']} | `{ds}` | {status} |")
        if warn_count:
            lines += [
                "",
                f"> ⚠ {warn_count} field(s) were **not wired** — the literal `$TBD_*` token "
                "remains in the plugin string and will appear verbatim in rendered documents "
                "until addressed.",
            ]
        lines += [""]

    occurrence_rows = occurrence_rows or []
    if occurrence_rows:
        guarded = sum(1 for r in occurrence_rows if r["status"].startswith("guarded"))
        warn_count = sum(1 for r in occurrence_rows if r["status"].startswith("WARN"))
        lines += [
            "---",
            "",
            f"## Occurrence guards ({guarded} guarded, {warn_count} warnings)",
            "",
            "Occurrence declared per field in the source document — `{x}` required,",
            "`{$x}` optional, `{+x}` one or more, `{*x}` zero or more. required and",
            "one_or_more fields get a null/empty guard in the plugin; a missing value",
            "throws `IllegalStateException` before the snapshot is built, so documents",
            "never render with absent required data (and the template never NPEs).",
            "",
            "| Field | Occurrence | data_source | Guard |",
            "|---|---|---|---|",
        ]
        for r in occurrence_rows:
            status = r["status"]
            if status.startswith("WARN"):
                status = f"⚠ **{status}**"
            lines.append(
                f"| {r['name']} | {r['occurrence']} | `{r['data_source'] or '(empty)'}` | {status} |"
            )
        lines += [""]

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Compile check (plan §14)
# ---------------------------------------------------------------------------


def compile_check(
    java_path: Path,
    customer_jar: Path,
    datamodel_jar: Path,
    slf4j_jar: Path,
    out_dir: Path,
) -> tuple[bool, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cp = ":".join(str(p) for p in (customer_jar, datamodel_jar, slf4j_jar))
    cmd = [
        "javac", "-encoding", "UTF-8",
        "-cp", cp,
        "-d", str(out_dir),
        str(java_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    detail = (proc.stdout + proc.stderr).strip() or f"javac -cp {cp}"
    return proc.returncode == 0, detail


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    repo_root = _repo_root()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--suggested", type=Path, action="append", required=True,
                    help=".mapping.yaml (enriched by Leg 2) or legacy .suggested.yaml. "
                         "Repeatable — forms are processed sequentially into one plugin: "
                         "the first form writes (or additively updates) the .java, "
                         "subsequent forms are always merged additively.")
    ap.add_argument("--output-dir", type=Path, default=None,
                    help="Where to write the .java (default: dir of the first --suggested)")
    ap.add_argument("--customer-jar", type=Path,
                    default=repo_root / "build" / "customer-config.jar",
                    help="customer-config.jar with the plugin interface + request types")
    ap.add_argument("--datamodel-jar", type=Path, default=None,
                    help="core-datamodel-v*.jar (default: newest under build/)")
    ap.add_argument("--slf4j-jar", type=Path,
                    default=None,
                    help="slf4j-api jar for the compile check (default: auto-discover build/slf4j-api-*.jar)")
    ap.add_argument("--registry", type=Path, default=None,
                    help="path-registry.yaml for deriving Java accessors of fields inside "
                         "conditional blocks (default: mapping's path_registry, then "
                         "<repo>/registry/path-registry.yaml)")
    ap.add_argument("--compile-check", action="store_true", default=False,
                    help="Run javac against the JARs after generating")
    ap.add_argument("--validate-only", action="store_true", default=False,
                    help="Parse and validate existing plugin file only; no files written")
    args = ap.parse_args()

    suggested_paths = [sp.resolve() for sp in args.suggested]
    out_dir = (args.output_dir.resolve() if args.output_dir
               else suggested_paths[0].parent)
    for suggested_path in suggested_paths:
        rc = _process_form(suggested_path, out_dir, args, repo_root)
        if rc != 0:
            return rc
    return 0


def _process_form(
    suggested_path: Path, out_dir: Path, args: argparse.Namespace, repo_root: Path
) -> int:
    """Process one mapping into the shared plugin at out_dir (fresh or additive).

    Per-form artifacts (conditional registry lookup, plugin report) stay in the
    form's own directory; only the .java is shared across forms.
    """
    if not suggested_path.exists():
        print(f"ERROR: suggested file not found: {suggested_path}", file=sys.stderr)
        return 1

    stem = suggested_path.name
    for suffix in (".suggested.yaml", ".mapping.yaml", ".yaml"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break

    form_dir = suggested_path.parent

    suggested_raw = _load_yaml(suggested_path)
    product = (suggested_raw.get("product") or "").strip()
    if not product:
        print(f"ERROR: 'product' missing from {suggested_path.name}", file=sys.stderr)
        return 1

    # --validate-only: parse existing plugin file and exit without writing anything
    if args.validate_only:
        _vonly_class = f"{product}DocumentDataSnapshotPluginImpl"
        _vonly_java = out_dir / f"{_vonly_class}.java"
        if not _vonly_java.exists():
            print(f"No existing plugin file: {_vonly_java.name}")
            return 0
        _vonly_result = parse_plugin_keys(_vonly_java)
        print(f"Plugin: {_vonly_java.name}")
        if _vonly_result["errors"]:
            for _err in _vonly_result["errors"]:
                print(f"ERROR: {_err}")
            _n = len(_vonly_result["errors"])
            print(f"Status: INVALID ({_n} error{'s' if _n != 1 else ''})")
            return 1
        print(f"Keys: {len(_vonly_result['existing_keys'])}")
        print(f"Highest condN: {_vonly_result['cond_high_water']}")
        print("Status: VALID")
        return 0

    customer_jar = args.customer_jar.resolve()
    if not customer_jar.exists():
        print(f"ERROR: customer jar not found: {customer_jar}", file=sys.stderr)
        return 1

    datamodel_jar = (
        args.datamodel_jar.resolve() if args.datamodel_jar
        else (_default_datamodel_jar(repo_root) or None)
    )
    if datamodel_jar is None or not datamodel_jar.exists():
        print("ERROR: no core-datamodel jar found (pass --datamodel-jar)", file=sys.stderr)
        return 1

    slf4j_jar = (
        args.slf4j_jar.resolve() if args.slf4j_jar
        else (_default_slf4j_jar(repo_root) or None)
    )
    if slf4j_jar is None or not slf4j_jar.exists():
        print("ERROR: no slf4j-api jar found (pass --slf4j-jar)", file=sys.stderr)
        return 1

    classpath = f"{customer_jar}:{datamodel_jar}"

    # Collect DataFetcher calls before flattening — needs per-root verdicts.
    # Skip "pricing" key for quote handler (handled by the legacy pricing computation block).
    quote_df_calls = _collect_datafetcher_calls(
        suggested_raw, "quote", classpath, skip_keys=_LEGACY_PRICING_KEYS
    )
    policy_df_calls = _collect_datafetcher_calls(
        suggested_raw, "segment", classpath, skip_keys=frozenset()
    )

    suggested = _flatten_to_segment_root(suggested_raw)

    # --- Verify interface + nested request types via javap (fail fast) -------
    if not _class_exists(classpath, PLUGIN_INTERFACE):
        print(f"ERROR: {PLUGIN_INTERFACE} not found in {customer_jar.name}", file=sys.stderr)
        return 1

    required_nested = {
        "quote request": f"{PLUGIN_INTERFACE}${product}QuoteRequest",
        "policy request": f"{PLUGIN_INTERFACE}${product}Request",
        "invoice request": f"{PLUGIN_INTERFACE}${INVOICE_REQUEST}",
    }
    missing = [f"{label} ({fqcn})" for label, fqcn in required_nested.items()
               if not _class_exists(classpath, fqcn)]
    if missing:
        print("ERROR: required plugin types not found in JAR:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 1

    segment_fqcn = f"{CUSTOMER_PACKAGE}.{product}Segment"
    segment_ok = _class_exists(classpath, segment_fqcn)

    # Determine primary root for validation — prefer segment, fall back to quote.
    _vel_prefix_map = {"quote": "$data.quote", "segment": "$data.segment"}
    roots_list = suggested.get("rendering_roots") or []
    primary_root_id = next(
        (r["id"] for r in roots_list if r.get("id") in ("segment", "quote")),
        "segment",
    )
    root_vel_prefix = _vel_prefix_map.get(primary_root_id, "$data")
    if primary_root_id == "quote":
        validate_fqcn = f"{CUSTOMER_PACKAGE}.{product}Quote"
        validate_ok = _class_exists(classpath, validate_fqcn)
    else:
        validate_fqcn = segment_fqcn
        validate_ok = segment_ok

    # --- Load conditional registry (Leg 1 artifact) --------------------------
    cond_yaml = form_dir / f"{stem}.conditional-registry.yaml"
    try:
        cond_blocks = load_conditional_registry(cond_yaml)
    except ContractError as exc:
        print(exc, file=sys.stderr)
        return 1
    if not cond_yaml.exists():
        n_conds = _count_annotated_conditionals(form_dir, stem)
        if n_conds > 0:
            csv_path = action_needed_dir(form_dir) / f"{stem}.variants.csv"
            if csv_path.exists():
                fix_cmd = (
                    f"python3 -m velocity_converter.leg0_ingest "
                    f"--parse-variants-csv {csv_path} "
                    f"--output-dir {form_dir}"
                )
            else:
                fix_cmd = "(variants.csv not found — re-run Leg 0 first)"
            print(
                f"WARNING: {n_conds} conditional(s) detected in {stem}.annotated.html "
                f"but no conditional-registry.yaml found.\nRun: {fix_cmd}",
                file=sys.stderr,
            )

    # --- Field tokens inside conditional blocks (plan 10) ---------------------
    registry_path = args.registry.resolve() if args.registry else None
    if registry_path is None:
        pr = str(suggested_raw.get("path_registry") or "").strip()
        if pr:
            cand = (suggested_path.parent / pr).resolve()
            if cand.is_file():
                registry_path = cand
    if registry_path is None:
        cand = repo_root / "registry" / "path-registry.yaml"
        if cand.is_file():
            registry_path = cand

    vel_to_cat = _load_velocity_categories(registry_path)
    field_lookup = _build_cond_field_lookup(
        suggested, vel_to_cat, classpath=classpath, product=product,
    )
    field_lookup = _augment_field_lookup_for_variants(
        field_lookup, cond_blocks, vel_to_cat, registry_path, classpath, product,
        doc_scope="quote" if primary_root_id == "quote" else "policy",
    )
    unresolved_fields, unsupported_fields, mixed_scope_ids = _analyse_cond_fields(
        cond_blocks, field_lookup
    )
    if unresolved_fields:
        print(
            "ERROR: conditional block(s) reference fields with no resolved data_source:",
            file=sys.stderr,
        )
        for u in unresolved_fields:
            print(f"  - block {u['block_id']}: {u['name']}", file=sys.stderr)
        print(
            "Run Leg 2 first to enrich the mapping "
            f"(RUN_PIPELINE leg2 mapping={suggested_path}), or fill data_source "
            "manually, then re-run Leg 4. No plugin was written.",
            file=sys.stderr,
        )
        return 1
    for u in unsupported_fields:
        print(
            f"WARNING: conditional block {u['block_id']} field {u['name']} not wired — {u['reason']}",
            file=sys.stderr,
        )
    for bid in mixed_scope_ids:
        print(
            f"WARNING: conditional block {bid} mixes quote- and policy-scoped fields — "
            "it renders empty in both overloads",
            file=sys.stderr,
        )

    cond_field_rows: list[dict] = []
    for b in cond_blocks:
        for _s, _e, name in _find_field_tokens(b.get("source_text") or "", set(field_lookup)):
            info = field_lookup.get(name) or {}
            if info.get("unsupported_reason"):
                status = f"WARN: {info['unsupported_reason']}"
            elif b["id"] in mixed_scope_ids:
                status = "WARN: mixed-scope block — empty in both overloads"
            else:
                status = f"wired ({info.get('scope')})"
            cond_field_rows.append({
                "block_id": b["id"],
                "name": name,
                "data_source": info.get("data_source", ""),
                "status": status,
            })

    # --- Render + write Java (additive if file exists, fresh otherwise) ------
    class_name = f"{product}DocumentDataSnapshotPluginImpl"
    java_path = out_dir / f"{class_name}.java"
    out_dir.mkdir(parents=True, exist_ok=True)

    additive_mode = java_path.exists()
    additive_summary: dict | None = None
    occurrence_rows = occurrence_report_rows(suggested.get("variables") or [], field_lookup)

    if additive_mode:
        preflight = parse_plugin_keys(java_path)
        if preflight["errors"]:
            for _pf_err in preflight["errors"]:
                print(f"Pre-flight warning: {_pf_err}", file=sys.stderr)
        existing_keys = preflight["existing_keys"]
        cond_high_water = preflight["cond_high_water"]

        required = _required_keys(suggested_raw, cond_blocks)
        missing_vars, missing_conds = _diff_keys(required, existing_keys, cond_high_water)

        missing_quote_df = [c for c in quote_df_calls if c["key"] in missing_vars]
        missing_policy_df = [c for c in policy_df_calls if c["key"] in missing_vars]

        local_to_global = {local_id: global_id for local_id, global_id in missing_conds}
        offset_cond_blocks = [
            {**b, "id": local_to_global[b["id"]]}
            for b in cond_blocks
            if not b.get("variants") and not b.get("placeholder") and b["id"] in local_to_global
        ]
        # Named variant blocks merge by name (set-union, no positional offset) —
        # this includes default-only variants (placeholder set, no conditioned
        # rows). A name already in the plugin is a conflict to report, not a renumber.
        named_cond_keys: list[str] = []
        for b in cond_blocks:
            if not b.get("variants") and not b.get("placeholder"):
                continue
            bkey = block_key(b)
            if bkey in existing_keys:
                print(
                    f"Additive: conditional key '{bkey}' already in the plugin — "
                    "skipped (named keys are not renumbered)",
                    file=sys.stderr,
                )
                continue
            offset_cond_blocks.append(b)
            named_cond_keys.append(bkey)

        # Occurrence guards: skip fields a previous run already guarded; give
        # this run's guard list a fresh local name so methods stay compilable.
        existing_text = java_path.read_text(encoding="utf-8")
        guarded_names = set(re.findall(r"// occurrence-guard: (\S+)", existing_text))
        suffixes = [
            int(s or "0")
            for s in re.findall(r"java\.util\.List<String> missingRequired(\d*) =", existing_text)
        ]
        list_var = "missingRequired" if not suffixes else f"missingRequired{max(suffixes) + 2}"
        quote_guard_code = render_occurrence_guards(
            suggested.get("variables") or [], field_lookup, scope="quote",
            list_var=list_var, skip_names=guarded_names,
        )
        policy_guard_code = render_occurrence_guards(
            suggested.get("variables") or [], field_lookup, scope="policy",
            list_var=list_var, skip_names=guarded_names,
        )

        _append_to_plugin(java_path, missing_quote_df, missing_policy_df, offset_cond_blocks,
                          field_lookup=field_lookup,
                          quote_guard_code=quote_guard_code,
                          policy_guard_code=policy_guard_code)

        added_keys = {c["key"] for c in missing_quote_df + missing_policy_df}
        additive_summary = {
            "keys_already_present": len(existing_keys),
            "keys_added": added_keys,
            "cond_high_water_before": cond_high_water,
            "new_cond_ids": [global_id for _, global_id in missing_conds] + named_cond_keys,
            "preflight": preflight,
        }
        print(
            f"Additive mode: {len(added_keys)} key(s) added, "
            f"{len(missing_conds) + len(named_cond_keys)} conditional(s) added "
            f"(high-water was {cond_high_water})"
        )
    else:
        java_path.write_text(
            render_java(product, suggested_path.name,
                        quote_df_calls=quote_df_calls, policy_df_calls=policy_df_calls,
                        cond_blocks=cond_blocks, field_lookup=field_lookup,
                        variables=suggested.get("variables") or []),
            encoding="utf-8",
        )

    # --- Categorise + validate variables -------------------------------------
    variables = suggested.get("variables") or []
    resolved_vars = [
        v for v in variables
        if (v.get("data_source") or "").strip()
        and not (v.get("data_source") or "").strip().startswith("UNRESOLVED:")
    ]
    unresolved_vars = [v for v in variables if v not in resolved_vars]

    high_results: list[tuple[dict, str, str]] = []
    for v in resolved_vars:
        if validate_ok:
            status, detail = validate_path(
                classpath, validate_fqcn, v.get("data_source") or "",
                root_prefix=root_vel_prefix,
            )
        else:
            status, detail = "warning", f"type {validate_fqcn} not found in JAR"
        high_results.append((v, status, detail))

    # --- Optional compile check ----------------------------------------------
    compile_status: str | None = None
    compile_detail = ""
    compile_ok = True
    if args.compile_check:
        compile_ok, compile_detail = compile_check(
            java_path, customer_jar, datamodel_jar, slf4j_jar,
            repo_root / "build" / "tmp" / "leg4-compile",
        )
        compile_status = "PASS" if compile_ok else "FAIL"

    # --- Report --------------------------------------------------------------
    report_path = form_dir / f"{stem}.plugin-report.md"
    generated_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_report(
        report_path,
        stem=stem,
        product=product,
        suggested_path=suggested_path,
        java_path=java_path,
        high_results=high_results,
        ignored_vars=unresolved_vars,
        compile_status=compile_status,
        compile_detail=compile_detail,
        generated_at=generated_at,
        cond_blocks=cond_blocks,
        additive_summary=additive_summary,
        cond_field_rows=cond_field_rows,
        occurrence_rows=occurrence_rows,
    )

    print(f"Wrote {_rel(java_path, repo_root)}")
    print(f"Wrote {_rel(report_path, repo_root)}")
    print(
        f"Product={product}  resolved={len(high_results)}  unresolved={len(unresolved_vars)}"
        + (f"  compile={compile_status}" if compile_status else "")
    )

    if args.compile_check and not compile_ok:
        print("ERROR: compile check failed:\n" + compile_detail, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
