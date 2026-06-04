#!/usr/bin/env python3
"""Fill Leg-2 suggested mapping from path-registry (generic heuristic matcher).

Implements Rules 1-6 from SKILL-matching.md for any product whose registry
follows the path-registry.yaml schema.  The CommercialAuto `specials` dict
has been replaced by the generic 4-step name-match + scope-check engine.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import importlib.util
import json
import os
import re
import sys
import uuid
from pathlib import Path

import yaml

from leg2_review_writer import _write_review_md
from sdk_introspect import (
    ALLOWED_ROOTS,
    _class_exists,
    _default_datamodel_jar,
    classify_path,
    datafetcher_return_type,
    jar_candidate,
    request_fqcn,
    resolve_element_type,
    roots_for_product,
)
from suggester_state import (
    compute_delta_change_set,
    entry_locked,
    evaluate_registry_config_gate,
    sha256_bytes,
    sha256_file,
)

# ---------------------------------------------------------------------------
# Root-prefix helpers (A4/A5 from renderingData-alignment plan)
# ---------------------------------------------------------------------------

_ROOT_VEL_PREFIX: dict[str, str] = {
    "quote": "$data.quote",
    "segment": "$data.segment",
}

_SIBLING_ROOT: dict[str, str] = {
    "policy": "$data.policy",
    "transaction": "$data.transaction",
    "account": "$data.account",
}


def _vel_prefix(root_id: str) -> str:
    return _ROOT_VEL_PREFIX.get(root_id, "$data")


def _reprefix(path: str, new_prefix: str) -> str:
    """Rewrite a $data.* registry path to use the root-specific prefix."""
    if path == "$data":
        return new_prefix
    if path.startswith("$data."):
        return new_prefix + path[5:]  # len("$data") = 5
    return path


def _sibling_data_source(hint: str | None) -> str:
    """Convert a sibling hint like 'Policy.policyNumber()' → '$data.policy.policyNumber'."""
    if not hint:
        return ""
    m = re.match(r"(\w+)\.(\w+)\(\)", hint)
    if not m:
        return ""
    cls, method = m.group(1).lower(), m.group(2)
    prefix = _SIBLING_ROOT.get(cls)
    if not prefix:
        return ""
    return f"{prefix}.{method}"


# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------


def normalize_mapping_field_name(name: str) -> str:
    """SCREAMING_SNAKE → snake_case.  Leg 1 preserves placeholder casing."""
    if re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
        return name.lower()
    return name


def snake_to_camel(s: str) -> str:
    parts = s.split("_")
    if not parts:
        return s
    return parts[0] + "".join(p[:1].upper() + p[1:] if p else "" for p in parts[1:])


# ---------------------------------------------------------------------------
# Feature-flag constants
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# DataFetcher constants (plan DF-BLOCK / lifecycle table)
# ---------------------------------------------------------------------------

_DF_BLOCKED_METHODS: frozenset[str] = frozenset({"getQuote", "getSegment"})

_DF_LIFECYCLE_MESSAGES: dict[str, str] = {
    "getPolicy:quote": (
        "getPolicy() is not available on quote root — no policy exists at quote stage; "
        "next-action: supply-from-plugin"
    ),
    "getTermCharges:quote": (
        "getTermCharges() is not available on quote root — no term exists at quote stage; "
        "next-action: supply-from-plugin"
    ),
    "getTermSubsegmentSummaries:quote": (
        "getTermSubsegmentSummaries() is not available on quote root — no term at quote stage; "
        "next-action: supply-from-plugin"
    ),
    "getTransaction:quote": (
        "getTransaction() is not available on quote root — no transaction at quote stage; "
        "next-action: supply-from-plugin"
    ),
    "getTransactionPricing:quote": (
        "getTransactionPricing() is not available on quote root — no transaction at quote stage; "
        "next-action: supply-from-plugin"
    ),
    "getQuotePricing:segment": (
        "getQuotePricing() is not available on segment root — no quote locator on segment request; "
        "next-action: supply-from-plugin"
    ),
    "getQuoteUnderwritingFlags:segment": (
        "getQuoteUnderwritingFlags() is not available on segment root; "
        "next-action: supply-from-plugin"
    ),
    "getSegmentDocuments:quote": (
        "getSegmentDocuments() is not available on quote root; "
        "next-action: supply-from-plugin"
    ),
}


def _validate_datafetcher_entry(e: dict) -> str | None:
    """Validate a registry entry with source: datafetcher. Returns error string or None."""
    field = e.get("field", "(unnamed)")
    method = e.get("datafetcher_method", "")
    if not method:
        return f"datafetcher entry '{field}': missing datafetcher_method"
    if not e.get("datafetcher_arg"):
        return f"datafetcher entry '{field}': missing datafetcher_arg"
    if not e.get("datafetcher_key"):
        return f"datafetcher entry '{field}': missing datafetcher_key"
    if not e.get("valid_roots"):
        return f"datafetcher entry '{field}': missing valid_roots"
    if method in _DF_BLOCKED_METHODS:
        return (
            f"datafetcher entry '{field}': method {method}() is blocked (collision guard "
            f"— it returns the same entity as the rendering root as a less-specific type)"
        )
    vel = e.get("velocity", "")
    key = e.get("datafetcher_key", "")
    if vel and key and not vel.startswith(f"$data.{key}"):
        return (
            f"datafetcher entry '{field}': velocity '{vel}' must start with '$data.{key}' "
            f"(datafetcher_key/velocity mismatch)"
        )
    return None


REFUSAL_FLAGS: frozenset[str] = frozenset({
    "nested_iterables",
    "custom_data_types",
    "recursive_cdts",
    "jurisdictional_scopes",
    "peril_based",
    "multi_product",
    "default_option_prefix",
})

PARTIAL_FLAGS: frozenset[str] = frozenset({"array_data_extensions"})

# ---------------------------------------------------------------------------
# Registry index
# ---------------------------------------------------------------------------


def _collect_entries(reg: dict) -> list[dict]:
    """Return every dict with (field + velocity) anywhere in the registry."""
    out: list[dict] = []

    def _add(obj: dict) -> None:
        if obj.get("field") and (obj.get("velocity") or obj.get("velocity_amount")):
            out.append(obj)

    def _walk(lst: object) -> None:
        if not isinstance(lst, list):
            return
        for item in lst:
            if not isinstance(item, dict):
                continue
            _add(item)
            for v in item.values():
                if isinstance(v, list):
                    _walk(v)

    for section in ("system_paths", "account_paths", "policy_data", "datafetcher_paths"):
        _walk(reg.get(section))

    for exp in reg.get("exposures") or []:
        if not isinstance(exp, dict):
            continue
        _walk(exp.get("system_fields"))
        _walk(exp.get("fields"))
        for cov in exp.get("coverages") or []:
            if isinstance(cov, dict):
                if cov.get("velocity") or cov.get("velocity_amount"):
                    _add(cov)
                _walk(cov.get("fields"))

    return out


def build_registry_index(reg: dict) -> dict:
    """Build all lookup tables needed by the matcher."""
    entries = _collect_entries(reg)

    df_errors = [
        err for e in entries
        if e.get("source") == "datafetcher"
        for err in [_validate_datafetcher_entry(e)]
        if err
    ]
    if df_errors:
        raise ValueError(
            "Registry DataFetcher validation errors:\n"
            + "\n".join(f"  - {e}" for e in df_errors)
        )

    by_field: dict[str, list[dict]] = {}
    by_display_name: dict[str, list[dict]] = {}
    for e in entries:
        f = e.get("field") or ""
        dn = e.get("display_name") or ""
        if f:
            by_field.setdefault(f.lower(), []).append(e)
        if dn:
            by_display_name.setdefault(dn.lower(), []).append(e)

    iterables: list[dict] = list(reg.get("iterables") or [])
    iby_name: dict[str, dict] = {}
    iby_display: dict[str, dict] = {}
    iby_plural: dict[str, dict] = {}
    iby_iterator: dict[str, dict] = {}
    for it in iterables:
        name = str(it.get("name") or "")
        dn = str(it.get("display_name") or name)
        iter_raw = str(it.get("iterator") or "")
        iter_key = iter_raw.lstrip("$").lower()
        if name:
            iby_name[name.lower()] = it
        if dn:
            iby_display[dn.lower()] = it
        if iter_key:
            iby_iterator[iter_key] = it
        if name and "_" not in name and " " not in name:
            iby_plural[name.lower() + "s"] = it

    feature_support = dict(reg.get("feature_support") or {})
    refusal_flags = [k for k, v in feature_support.items() if v and k in REFUSAL_FLAGS]
    partial_flags = [k for k, v in feature_support.items() if v and k in PARTIAL_FLAGS]

    return {
        "entries": entries,
        "by_field": by_field,
        "by_display_name": by_display_name,
        "iterables": iterables,
        "iterables_by_name": iby_name,
        "iterables_by_display_name": iby_display,
        "iterables_by_plural": iby_plural,
        "iterables_by_iterator": iby_iterator,
        "feature_support": feature_support,
        "refusal_flags": refusal_flags,
        "partial_flags": partial_flags,
    }


# ---------------------------------------------------------------------------
# Scope checking (Rule 2)
# ---------------------------------------------------------------------------


def check_scope(entry: dict, context: dict, idx: dict) -> str:
    """Returns 'not_required' | 'satisfied' | 'violated_with_hint' | 'violated_no_hint'."""
    req = entry.get("requires_scope") or []
    if not req:
        return "not_required"

    outermost = req[0] if isinstance(req[0], dict) else {}
    outermost_iter = str(outermost.get("iterator") or "").lstrip("$").lower()

    def _matches(loop_name: str) -> bool:
        ln = loop_name.lower()
        # Direct iterator name match
        if ln == outermost_iter:
            return True
        # Lookup by iterable name/plural → compare iterators
        for mapping in (idx["iterables_by_name"], idx["iterables_by_plural"]):
            it = mapping.get(ln)
            if it:
                it_iter = str(it.get("iterator") or "").lstrip("$").lower()
                if it_iter == outermost_iter:
                    return True
        return False

    loop = str(context.get("loop") or "")
    loop_hint = str(context.get("loop_hint") or "")

    if loop and _matches(loop):
        return "satisfied"
    if loop_hint and _matches(loop_hint):
        return "violated_with_hint"
    return "violated_no_hint"


# ---------------------------------------------------------------------------
# 4-step name matching
# ---------------------------------------------------------------------------


def _step1_exact(name_camel: str, idx: dict) -> list[dict]:
    hits: list[dict] = []
    for e in idx["by_field"].get(name_camel.lower(), []):
        if e.get("field") == name_camel and e not in hits:
            hits.append(e)
    return hits


def _step2_ci(name_camel: str, idx: dict) -> list[dict]:
    hits: list[dict] = []
    for e in idx["by_field"].get(name_camel.lower(), []):
        if e not in hits:
            hits.append(e)
    return hits


def _step3_terminology(
    name_snake: str, idx: dict, terminology: dict
) -> list[tuple[dict, str]]:
    """Returns (entry, alias_used) pairs from terminology synonyms."""
    syns = terminology.get("synonyms") or {}
    hits: list[tuple[dict, str]] = []

    for canonical, aliases in (syns.get("fields") or {}).items():
        for alias in aliases:
            if alias.lower() == name_snake.lower():
                for e in idx["by_field"].get(canonical.lower(), []):
                    if (e, alias) not in hits:
                        hits.append((e, alias))

    return hits


def _step4_fuzzy(name_snake: str, idx: dict) -> list[dict]:
    """Fuzzy: last-token of name matches a field key."""
    hits: list[dict] = []
    tokens = [t for t in name_snake.split("_") if t]
    if not tokens:
        return hits
    last = tokens[-1].lower()
    for e in idx["by_field"].get(last, []):
        if e not in hits:
            hits.append(e)
    return hits


def match_name(
    name: str,
    label: str | None,
    idx: dict,
    terminology: dict | None,
) -> tuple[list[dict], str, str | None]:
    """
    4-step name match.
    Returns (entries, step_name, alias_if_step3).
    step_name: 'exact' | 'ci' | 'terminology' | 'fuzzy' | 'none'
    """
    name_snake = normalize_mapping_field_name(name)
    name_camel = snake_to_camel(name_snake)

    hits = _step1_exact(name_camel, idx)
    if hits:
        return hits, "exact", None

    hits = _step2_ci(name_camel, idx)
    if hits:
        return hits, "ci", None

    if terminology:
        term_hits = _step3_terminology(name_snake, idx, terminology)
        if term_hits:
            return [e for e, _ in term_hits], "terminology", term_hits[0][1]

    hits = _step4_fuzzy(name_snake, idx)
    if hits:
        return hits, "fuzzy", None

    return [], "none", None


# ---------------------------------------------------------------------------
# Rules 4 & 5: quantifier annotation
# ---------------------------------------------------------------------------


def _quantifier_note(entry: dict) -> str:
    q = entry.get("quantifier") or ""
    vel = entry.get("velocity") or entry.get("velocity_amount") or ""
    if q == "?":
        return f" requires #if({vel}) guard before access (element is zero-or-one)"
    if q == "!":
        return " element is auto-created on validation; always present (no #if guard needed)"
    return ""


# ---------------------------------------------------------------------------
# Rule 6: charge disambiguation
# ---------------------------------------------------------------------------

_AMOUNT_KEYWORDS = frozenset({"amount", "premium", "fee", "tax", "price", "cost", "total"})


def _charge_path(entry: dict, label: str | None) -> str:
    lbl = (label or "").lower()
    if any(kw in lbl for kw in _AMOUNT_KEYWORDS):
        return entry.get("velocity_amount") or entry.get("velocity_object") or ""
    return entry.get("velocity_object") or entry.get("velocity_amount") or ""


# ---------------------------------------------------------------------------
# Variable suggestion (Rule 2 scope-aware)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Rendering-root parsing (Leg 2 plan §8, D2) + confidence grading (§6.3, D8)
# ---------------------------------------------------------------------------


_ROOT_BRACKET_RE = re.compile(r"\(([^()]*)\)")


def parse_rendering_roots(source: str | None) -> tuple[list[str], str | None]:
    """Parse declared rendering roots from a filename like
    ``Simple-form(segment).html`` or ``X(quote,segment).html`` (plan §8, D2).

    Returns ``(root_ids, error)``. ``error`` is a human-readable blocker string
    when brackets are missing or a token is unknown; ``root_ids`` is then empty.
    No inference — absence of brackets is an explicit blocker.
    """
    name = (source or "").strip()
    if not name:
        return [], (
            "rendering root not declared — no source filename to parse; "
            "rename input to <stem>(segment).html"
        )
    # Strip a trailing extension so '(segment)' in 'X(segment).html' is found.
    stem = name.rsplit("/", 1)[-1]
    matches = _ROOT_BRACKET_RE.findall(stem)
    if not matches:
        return [], (
            f"rendering root not declared in filename `{name}` — "
            "rename to <stem>(segment).html (allowed roots: "
            f"{', '.join(ALLOWED_ROOTS)})"
        )
    tokens = [t.strip().lower() for t in matches[-1].split(",") if t.strip()]
    if not tokens:
        return [], (
            f"empty rendering-root bracket in filename `{name}` — "
            f"declare one of: {', '.join(ALLOWED_ROOTS)}"
        )
    unknown = [t for t in tokens if t not in ALLOWED_ROOTS]
    if unknown:
        return [], (
            f"unknown rendering root(s) {unknown} in filename `{name}` — "
            f"allowed roots: {', '.join(ALLOWED_ROOTS)}"
        )
    # De-dupe, preserve order (first listed = primary).
    seen: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.append(t)
    return seen, None


# next-action vocabulary is closed (plan D9) — no new codes.
NEXT_ACTION_FOR_STATUS: dict[str, str] = {
    "not_found": "supply-from-plugin",
    "sibling_only": "supply-from-plugin",
    "not_navigable": "confirm-assumption",
}


def confidence_grade(match_step: str, sdk_status: str) -> str:
    """Grade a (placeholder × root) verdict (plan §6.3, D8). The JAR can only
    *demote*: a strong name-match needs `verified` to stay `high`, and SDK truth
    never promotes a weak (fuzzy) match above `medium`."""
    if sdk_status == "verified":
        return "high" if match_step in ("exact", "ci", "terminology") else "medium"
    return "low"


# ---------------------------------------------------------------------------
# Root-independent candidate derivation (name-match only — plan §5 step 1)
# ---------------------------------------------------------------------------


def derive_variable_candidate(
    v: dict, idx: dict, terminology: dict | None
) -> dict:
    """Name-match a variable to a registry candidate path (root-independent).

    Returns a dict: ``{path, match_step, registry_field, base_reason, terminal,
    fallback_confidence}``. ``terminal`` candidates carry no single $data path
    (no match / scope violation / ambiguous) — there is nothing for the JAR to
    check, so the same verdict is replicated across roots with
    ``sdk_status: skipped``.
    """
    name = v.get("name") or ""
    context = v.get("context") or {}
    label = context.get("nearest_label") or None

    entries, step, alias = match_name(name, label, idx, terminology)

    name_snake = normalize_mapping_field_name(name)
    name_camel = snake_to_camel(name_snake)

    def cand(path="", match_step="none", registry_field="", base_reason="",
             terminal=False, fallback="low") -> dict:
        return {
            "path": path, "match_step": match_step, "registry_field": registry_field,
            "base_reason": base_reason, "terminal": terminal,
            "fallback_confidence": fallback,
        }

    if not entries:
        c = cand(
            base_reason=f"no registry match for {name_camel} — next-action: supply-from-plugin",
            terminal=True, fallback="low",
        )
        c.update({"jar_fallback_ok": True, "name_camel": name_camel, "label": label})
        return c

    ok: list[dict] = []
    violated: list[tuple[dict, str]] = []
    for e in entries:
        s = check_scope(e, context, idx)
        if s in ("not_required", "satisfied"):
            ok.append(e)
        else:
            violated.append((e, s))

    if not ok:
        e, scope_stat = violated[0]
        vel = e.get("velocity") or ""
        req = e.get("requires_scope") or []
        foreach_str = req[0].get("foreach", "") if req and isinstance(req[0], dict) else ""
        if scope_stat == "violated_with_hint":
            reason = (
                f"registry candidate `{vel}` — scope implied by loop_hint "
                f"`{context.get('loop_hint', '')}` but variable is not inside "
                f"`{foreach_str}`; scope violation — next-action: restructure-template"
            )
        else:
            reason = (
                f"registry candidate `{vel}` requires scope `{foreach_str}` "
                f"but no loop signal in Leg 1 output — next-action: restructure-template"
            )
        return cand(base_reason=reason, terminal=True, fallback="low")

    if len(ok) > 1:
        paths = " | ".join(e.get("velocity") or e.get("velocity_amount") or "" for e in ok)
        return cand(
            base_reason=f"{name_camel} has multiple registry candidates — next-action: pick-one: {paths}",
            terminal=True, fallback="medium",
        )

    e = ok[0]
    vel = e.get("velocity") or ""
    if not vel:
        vel = _charge_path(e, label)

    field = e.get("field") or ""
    dn = e.get("display_name") or ""

    if step == "exact":
        if label and e.get("display_name") == label:
            reason = f"exact label match: \"{label}\" → display_name \"{dn}\" → {vel}"
        else:
            reason = f"exact match: {name_camel} → {vel}"
    elif step == "ci":
        if label and label.lower() == dn.lower():
            reason = f"case-insensitive label match: \"{label}\" → display_name \"{dn}\" → {vel}"
        else:
            reason = f"case-insensitive match: {name_camel} → {vel}"
    elif step == "terminology":
        reason = f"matched via terminology.yaml synonym `{alias}` → canonical `{field}` → {vel}"
    elif step == "fuzzy":
        reason = f"fuzzy match: {name_camel} → {vel}"
    else:
        reason = f"no match for {name_camel}"

    reason += _quantifier_note(e)
    result = cand(path=vel, match_step=step, registry_field=field, base_reason=reason)
    if e.get("source") == "datafetcher":
        result["source"] = "datafetcher"
        result["datafetcher_method"] = e.get("datafetcher_method", "")
        result["datafetcher_arg"] = e.get("datafetcher_arg", "")
        result["datafetcher_key"] = e.get("datafetcher_key", "")
        result["valid_roots"] = list(e.get("valid_roots") or [])
    return result


def _last_segment(path: str) -> str:
    return (path or "").rstrip(".").rsplit(".", 1)[-1]


def _datafetcher_verdict(candidate: dict, rid: str, classpath: str) -> dict:
    """Verdict for a DataFetcher-sourced registry candidate (DF3).

    1. Lifecycle gate — fails fast on invalid root.
    2. JAR probe — classify sub-path against DataFetcher return type (N4 option a).
    3. Fallback to medium if return type not verifiable via JAR (N4 option b).
    """
    valid_roots = candidate.get("valid_roots") or []
    method = candidate.get("datafetcher_method", "")
    key = candidate.get("datafetcher_key", "")
    vel = candidate["path"]  # $data.<key>.<field> — no reprefixing for DataFetcher paths

    if rid not in valid_roots:
        msg = _DF_LIFECYCLE_MESSAGES.get(
            f"{method}:{rid}",
            f"{method}() is not available on {rid} root — next-action: supply-from-plugin",
        )
        return {"data_source": "", "confidence": "low", "sdk_status": "lifecycle_violation",
                "reasoning": msg}

    arg_raw = candidate.get("datafetcher_arg", "")
    arg_str = arg_raw.get(rid, "") if isinstance(arg_raw, dict) else str(arg_raw)

    df_fqcn = datafetcher_return_type(classpath, method)
    if df_fqcn:
        key_prefix = f"$data.{key}"
        rest = vel[len(key_prefix):].lstrip(".")
        if rest:
            _probe = "$__df"
            status, detail, _ = classify_path(
                classpath, df_fqcn, f"{_probe}.{rest}", None, root_prefix=_probe
            )
        else:
            status, detail = "verified", f"resolves to {method}() return root"
        grade = confidence_grade(candidate["match_step"], status)
        df_short = df_fqcn.rsplit(".", 1)[-1]
        if status == "verified":
            reasoning = (
                f"DataFetcher: {method}({arg_str}) → {df_short}.{rest}() "
                f"— verified on {rid} root"
            )
        else:
            reasoning = (
                f"DataFetcher: {method}({arg_str}) on {rid} root — {df_short} has no {rest}() "
                f"(N4 JAR probe: {detail}) — next-action: supply-from-plugin"
            )
        return {
            "data_source": vel if status == "verified" else "",
            "confidence": grade,
            "sdk_status": status,
            "reasoning": reasoning,
        }

    return {
        "data_source": vel,
        "confidence": "medium",
        "sdk_status": "trusted",
        "reasoning": (
            f"DataFetcher: {method}({arg_str}) on {rid} root — return type not verifiable "
            f"via JAR (trusted from registry, cap: medium)"
        ),
    }


def variable_verdict_for_root(candidate: dict, root: dict, classpath: str) -> dict:
    """Build one ``(variable × root)`` verdict from a candidate + the root's
    compiled Java type (plan §6.2/§6.3). SDK truth can only demote (D8)."""
    rid = root["id"]
    java_type = root.get("java_type")
    base = candidate["base_reason"]
    rp = _vel_prefix(rid)

    # Invoice / unresolved root (D5): schema can hold it, Leg 2 does not resolve.
    if java_type is None:
        return {
            "data_source": "",
            "confidence": "low",
            "sdk_status": "skipped",
            "reasoning": f"root `{rid}` not resolved (D5: invoice deferred); {base}",
        }

    # DataFetcher lifecycle gate (DF3) — bypasses direct-path JAR probing.
    if candidate.get("source") == "datafetcher":
        return _datafetcher_verdict(candidate, rid, classpath)

    # No single path to check — try JAR fallback first, then replicate.
    if candidate["terminal"]:
        if candidate.get("jar_fallback_ok") and java_type:
            jc = jar_candidate(
                classpath, java_type,
                candidate.get("name_camel", ""),
                candidate.get("label"),
                root_prefix=rp,
            )
            if jc:
                grade = confidence_grade(jc["match_step"], "verified")
                short = java_type.rsplit(".", 1)[-1]
                return {
                    "data_source": jc["path"],
                    "confidence": grade,
                    "sdk_status": "verified",
                    "reasoning": (
                        f"no registry entry for {candidate['name_camel']}; "
                        f"JAR probe: {short}.{jc['method_name']}() — "
                        f"{jc['match_step']} match → {jc['path']}"
                    ),
                }
        return {
            "data_source": "",
            "confidence": candidate["fallback_confidence"],
            "sdk_status": "skipped",
            "reasoning": base,
        }

    path = _reprefix(candidate["path"], rp)
    req = request_fqcn(root["request"])
    status, detail, hint = classify_path(classpath, java_type, path, req, root_prefix=rp)
    grade = confidence_grade(candidate["match_step"], status)
    short = java_type.rsplit(".", 1)[-1]
    last = _last_segment(path)
    step = candidate["match_step"]

    if status == "verified":
        reasoning = f"{base} — verified {last}() on {short}"
    elif status == "sibling_only":
        sib_path = _sibling_data_source(hint)
        reasoning = (
            f"name-match {step} ({candidate['registry_field']}), but {short} has no "
            f"{last}(); field exists on sibling {hint}"
            + (f" → {sib_path}" if sib_path else " — next-action: supply-from-plugin")
        )
    elif status == "not_found":
        reasoning = (
            f"{short} has no {last}() (name-match {step}: {path}) "
            "— next-action: supply-from-plugin"
        )
    elif status == "not_navigable":
        reasoning = f"{detail} (name-match {step}: {path}) — next-action: confirm-assumption"
    else:  # skipped (no candidate path reached classify)
        reasoning = base

    if status == "verified":
        data_source = path
    elif status == "sibling_only":
        data_source = _sibling_data_source(hint)
    else:
        data_source = ""

    out = {
        "data_source": data_source,
        "confidence": grade if status == "verified" else ("medium" if status == "sibling_only" and data_source else "low"),
        "sdk_status": status,
        "reasoning": reasoning,
    }
    if hint:
        out["sibling_hint"] = hint
    return out


# ---------------------------------------------------------------------------
# Loop root suggestion (Rule 1, generic)
# ---------------------------------------------------------------------------


def suggest_loop_root(
    loop_name: str,
    idx: dict,
    terminology: dict | None,
    reg: dict,
) -> tuple[str, str, str, str | None, str | None, list[dict]]:
    """
    Returns (list_velocity, match_step, reasoning, iterator, foreach, available_coverages).
    ``match_step`` is one of exact|ci|terminology|fuzzy|none (root-independent;
    the per-root SDK verdict is graded later). available_coverages may be empty.
    """
    ln = loop_name.lower()
    iby_name = idx["iterables_by_name"]
    iby_plural = idx["iterables_by_plural"]
    iby_display = idx["iterables_by_display_name"]

    it: dict | None = None
    step = "none"
    alias: str | None = None

    # Step 1: exact name
    cand = iby_name.get(ln)
    if cand and cand.get("name") == loop_name:
        it, step = cand, "exact"
    elif cand:
        it, step = cand, "ci"
    elif ln in iby_plural:
        it, step = iby_plural[ln], "ci"
    elif ln in iby_display and iby_display[ln].get("display_name", "").lower() == ln:
        it, step = iby_display[ln], "ci"
    else:
        # Step 3: terminology exposures
        if terminology:
            for canonical, aliases in ((terminology.get("synonyms") or {}).get("exposures") or {}).items():
                for a in aliases:
                    if a.lower() == ln:
                        cand = iby_name.get(canonical.lower())
                        if cand:
                            it, step, alias = cand, "terminology", a
                            break
                if it:
                    break

    if it is None:
        return (
            "", "none",
            f"loop `{loop_name}` has no matching iterable in registry — next-action: supply-from-plugin",
            None, None, [],
        )

    list_vel = str(it.get("list_velocity") or "")
    iterator = str(it.get("iterator") or "")
    foreach = str(it.get("foreach") or "")
    it_name = str(it.get("name") or "")

    if step == "terminology":
        reasoning = f"matched via terminology.yaml synonym `{alias}` → canonical `{it_name}` → {list_vel}"
    else:
        reasoning = f"loop `{loop_name}` → iterable `{it_name}` → {list_vel}"

    # Collect available_coverages from the registry
    cov_manifest: list[dict] = []
    for exp in reg.get("exposures") or []:
        if str(exp.get("name") or "").lower() == it_name.lower():
            for cov in exp.get("coverages") or []:
                if isinstance(cov, dict):
                    cov_manifest.append({
                        "name": cov.get("name"),
                        "velocity": cov.get("velocity"),
                        "quantifier": cov.get("quantifier", ""),
                        "cardinality": cov.get("cardinality", ""),
                    })
            break

    return list_vel, step, reasoning, iterator, foreach, cov_manifest


# ---------------------------------------------------------------------------
# Coverage field matching (generic prefix decomposition)
# ---------------------------------------------------------------------------


def _match_coverage_field(
    fld_snake: str,
    exp_coverages: list[dict],
) -> tuple[str, str, str] | None:
    """
    Try to match fld_snake against a named coverage's fields using prefix
    decomposition.  e.g. 'medpay_limit' → coverage 'MedPay' → field 'limit'.
    Works for any product registry — no product-specific names are assumed.

    Returns (field_velocity, coverage_quantifier, coverage_name) or None.
    """
    if not exp_coverages:
        return None

    # Build coverage lookup keyed by squashed lowercase name
    # ('MedPay' → 'medpay', 'Med Pay' → 'medpay', 'my_cov' → 'mycov')
    cov_by_key: dict[str, dict] = {}
    for cov in exp_coverages:
        raw = str(cov.get("name") or "")
        if not raw:
            continue
        key = re.sub(r"[_ ]", "", raw.lower())
        cov_by_key[key] = cov

    tokens = fld_snake.split("_")
    # Try progressively longer prefixes so multi-word names resolve first
    for prefix_len in range(1, len(tokens)):
        prefix_key = "".join(tokens[:prefix_len])
        cov = cov_by_key.get(prefix_key)
        if cov is None:
            continue

        cov_name = str(cov.get("name") or "")
        remaining_snake = "_".join(tokens[prefix_len:])
        remaining_camel = snake_to_camel(remaining_snake)

        cov_fields: dict[str, dict] = {}
        for f in cov.get("fields") or []:
            fn = str(f.get("field") or "").lower()
            if fn:
                cov_fields[fn] = f

        # Exact / CI match on remaining tokens
        target = remaining_camel.lower()
        if target in cov_fields:
            f = cov_fields[target]
            return str(f.get("velocity") or ""), str(cov.get("quantifier") or ""), cov_name

        # Fuzzy last token of remaining
        r_tokens = remaining_snake.split("_")
        if r_tokens and r_tokens[-1] in cov_fields:
            f = cov_fields[r_tokens[-1]]
            return str(f.get("velocity") or ""), str(cov.get("quantifier") or ""), cov_name

    return None


# ---------------------------------------------------------------------------
# Loop field suggestion (generic)
# ---------------------------------------------------------------------------


def suggest_loop_field(
    ph: str,
    loop_name: str,
    idx: dict,
    reg: dict,
) -> tuple[str, str, str]:
    """Returns (velocity, match_step, reasoning). ``match_step`` is
    exact|fuzzy|none (root-independent; per-root SDK verdict graded later)."""
    m = re.match(r"\$(\w+)\.TBD_(\w+)", ph)
    if not m:
        return "", "none", "unparseable loop_field placeholder — next-action: needs-skill-update"

    it_raw, fld_raw = m.group(1), m.group(2)
    fld_snake = normalize_mapping_field_name(fld_raw)
    fld_camel = snake_to_camel(fld_snake)

    # Identify the iterable from iterator name or loop name
    ibi = idx["iterables_by_iterator"]
    iby_name = idx["iterables_by_name"]
    iby_plural = idx["iterables_by_plural"]

    it_entry = (
        ibi.get(it_raw.lower())
        or iby_name.get(loop_name.lower())
        or iby_plural.get(loop_name.lower())
    )
    if it_entry is None:
        return "", "none", f"iterator `{it_raw}` not mapped to any iterable — next-action: supply-from-plugin"

    it_name = str(it_entry.get("name") or "")

    # Build a field lookup and collect coverages for this exposure
    exp_fields: dict[str, dict] = {}
    exp_coverages: list[dict] = []
    for exp in reg.get("exposures") or []:
        if str(exp.get("name") or "").lower() != it_name.lower():
            continue
        for f in (exp.get("fields") or []) + (exp.get("system_fields") or []):
            fn = str(f.get("field") or "").lower()
            if fn:
                exp_fields[fn] = f
        exp_coverages = exp.get("coverages") or []
        break

    # Step 1/2: exact or CI field match on exposure data fields
    target = fld_camel.lower()
    if target in exp_fields:
        e = exp_fields[target]
        vel = e.get("velocity") or ""
        return vel, "exact", f"{fld_snake} → {vel} ({it_name} exposure)"

    # Step 4: fuzzy last token on exposure data fields
    tokens = fld_snake.split("_")
    if tokens and tokens[-1] in exp_fields:
        e = exp_fields[tokens[-1]]
        vel = e.get("velocity") or ""
        return vel, "fuzzy", f"{fld_snake} → {vel} ({it_name} exposure, fuzzy)"

    # Coverage field fallback: decompose '<prefix>_<field>' against any coverage
    cov_result = _match_coverage_field(fld_snake, exp_coverages)
    if cov_result:
        vel, cov_q, cov_name = cov_result
        note = _quantifier_note({"quantifier": cov_q, "velocity": vel.rsplit(".data.", 1)[0] if ".data." in vel else vel})
        return vel, "exact", f"{fld_snake} → {vel} ({it_name} {cov_name} coverage){note}"

    return "", "none", f"{fld_snake} not found in {it_name} exposure — next-action: supply-from-plugin"


# ---------------------------------------------------------------------------
# Key-order helper
# ---------------------------------------------------------------------------


def reorder_top_keys(d: dict) -> dict:
    head = [
        "schema_version", "run_id", "mode", "generated_at",
        "input_mapping_sha256", "input_registry_sha256",
        "registry_schema_version", "registry_generated_at",
        "registry_config_dir", "registry_source_config_sha256",
        "live_source_config_sha256", "registry_config_verified",
        "registry_config_check", "previous_run_id",
        "base_suggested_sha256", "input_mapping_version",
        "input_registry_version", "source", "path_registry",
        "product", "rendering_roots", "tooling", "delta_changes",
    ]
    out: dict = {}
    for k in head:
        if k in d:
            out[k] = d[k]
    for k, v in d.items():
        if k not in out:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# annotate_mapping (generic)
# ---------------------------------------------------------------------------


def loop_root_verdict_for_root(
    list_vel: str, match_step: str, base_reason: str, root: dict, classpath: str
) -> dict:
    """Verdict for a loop's list root (e.g. ``$segment.items``) on one root (§6.4)."""
    rid = root["id"]
    jt = root.get("java_type")
    rp = _vel_prefix(rid)
    if jt is None:
        return {"data_source": "", "confidence": "low", "sdk_status": "skipped",
                "reasoning": f"root `{rid}` not resolved (D5: invoice deferred); {base_reason}"}
    if match_step == "none" or not list_vel:
        return {"data_source": "", "confidence": "low", "sdk_status": "skipped",
                "reasoning": base_reason}
    list_vel_rp = _reprefix(list_vel, rp)
    status, detail, _ = classify_path(classpath, jt, list_vel_rp, root_prefix=rp)
    grade = confidence_grade(match_step, status)
    short = jt.rsplit(".", 1)[-1]
    last = _last_segment(list_vel_rp)
    if status == "verified":
        reasoning = f"{base_reason} — verified {last}() on {short}"
    elif status == "not_found":
        reasoning = f"{short} has no {last}() ({base_reason}) — next-action: supply-from-plugin"
    elif status == "not_navigable":
        reasoning = f"{detail} — next-action: confirm-assumption"
    else:
        reasoning = base_reason
    return {"data_source": list_vel_rp if status == "verified" else "",
            "confidence": grade, "sdk_status": status, "reasoning": reasoning}


def loop_field_verdict_for_root(
    field_vel: str, match_step: str, base_reason: str, iterator: str,
    list_vel: str, root: dict, classpath: str, elem_cache: dict,
) -> dict:
    """Verdict for a loop field (e.g. ``$item.data.purchasePrice``) validated
    against the iterator element type resolved from the root (§6.4)."""
    rid = root["id"]
    jt = root.get("java_type")
    if jt is None:
        return {"data_source": "", "confidence": "low", "sdk_status": "skipped",
                "reasoning": f"root `{rid}` not resolved (D5: invoice deferred); {base_reason}"}
    if match_step == "none" or not field_vel:
        return {"data_source": "", "confidence": "low", "sdk_status": "skipped",
                "reasoning": base_reason}

    rp = _vel_prefix(rid)
    list_vel_rp = _reprefix(list_vel, rp)
    key = (jt, list_vel_rp)
    if key not in elem_cache:
        elem_cache[key] = resolve_element_type(classpath, jt, list_vel_rp, root_prefix=rp) or ""
    elem = elem_cache[key]
    short = jt.rsplit(".", 1)[-1]
    if not elem:
        return {"data_source": "", "confidence": "low", "sdk_status": "not_navigable",
                "reasoning": f"cannot resolve iterator element type from {list_vel} on {short} "
                             f"({base_reason}) — next-action: confirm-assumption"}

    prefix = iterator if iterator.startswith("$") else f"${iterator}"
    status, detail, _ = classify_path(classpath, elem, field_vel, None, root_prefix=prefix)
    grade = confidence_grade(match_step, status)
    elem_short = elem.rsplit(".", 1)[-1]
    last = _last_segment(field_vel)
    if status == "verified":
        reasoning = f"{base_reason} — verified {last}() on {elem_short}"
    elif status == "not_found":
        reasoning = f"{elem_short} has no {last}() ({base_reason}) — next-action: supply-from-plugin"
    elif status == "not_navigable":
        reasoning = f"{detail} ({base_reason}) — next-action: confirm-assumption"
    else:
        reasoning = base_reason
    return {"data_source": field_vel if status == "verified" else "",
            "confidence": grade, "sdk_status": status, "reasoning": reasoning}


def annotate_mapping(
    mapping: dict,
    reg: dict,
    path_registry_rel: str,
    terminology: dict | None = None,
    *,
    roots: list[dict],
    classpath: str,
) -> dict:
    """Produce the ``.suggested.yaml`` **2.0** shape: top-level ``rendering_roots``
    plus, per variable/loop, a root-independent ``candidate`` and a per-root
    ``verdicts`` map grounded in the compiled JARs (plan §6)."""
    idx = build_registry_index(reg)

    out = copy.deepcopy(mapping)
    out["schema_version"] = "2.0"
    out["input_mapping_version"] = str(mapping.get("schema_version", "1.0"))
    out["input_registry_version"] = str(reg.get("schema_version", "1.0"))
    out["path_registry"] = path_registry_rel
    out["product"] = str((reg.get("meta") or {}).get("product", ""))

    out["rendering_roots"] = [
        {
            "id": r["id"],
            "java_type": r.get("java_type"),
            "request": r.get("request"),
            "primary": (i == 0),
        }
        for i, r in enumerate(roots)
    ]

    root_ids = [r["id"] for r in roots]

    for v in out.get("variables") or []:
        cand = derive_variable_candidate(v, idx, terminology)
        v.pop("data_source", None)
        v.pop("confidence", None)
        v.pop("reasoning", None)
        cand_block: dict = {
            "path": cand["path"],
            "match_step": cand["match_step"],
            "registry_field": cand["registry_field"],
        }
        if cand.get("source") == "datafetcher":
            cand_block["source"] = "datafetcher"
            cand_block["datafetcher_method"] = cand.get("datafetcher_method", "")
            cand_block["datafetcher_arg"] = cand.get("datafetcher_arg", "")
            cand_block["datafetcher_key"] = cand.get("datafetcher_key", "")
        v["candidate"] = cand_block
        v["verdicts"] = {
            r["id"]: variable_verdict_for_root(cand, r, classpath) for r in roots
        }

    elem_cache: dict = {}
    for loop in out.get("loops") or []:
        ln = loop["name"]
        list_vel, lstep, lreason, iterator, foreach, cov_manifest = suggest_loop_root(
            ln, idx, terminology, reg
        )
        loop.pop("data_source", None)
        loop.pop("confidence", None)
        loop.pop("reasoning", None)
        loop["type"] = "loop"
        if iterator:
            loop["iterator"] = iterator
        if foreach:
            loop["foreach"] = foreach
        loop["candidate"] = {
            "list_velocity": list_vel,
            "match_step": lstep,
        }
        loop["verdicts"] = {
            r["id"]: loop_root_verdict_for_root(list_vel, lstep, lreason, r, classpath)
            for r in roots
        }
        if cov_manifest:
            loop["available_coverages"] = cov_manifest

        for fld in loop.get("fields") or []:
            ph = fld.get("placeholder") or ""
            fvel, fstep, freason = suggest_loop_field(ph, ln, idx, reg)
            fld.pop("data_source", None)
            fld.pop("confidence", None)
            fld.pop("reasoning", None)
            fld["candidate"] = {"velocity": fvel, "match_step": fstep}
            fld["verdicts"] = {
                r["id"]: loop_field_verdict_for_root(
                    fvel, fstep, freason, iterator or "", list_vel, r, classpath, elem_cache
                )
                for r in roots
            }

    # Stash index + root metadata for review generation (stripped before write)
    out["_idx"] = idx
    out["_root_ids"] = root_ids
    return out


# ---------------------------------------------------------------------------
# Delta merge
# ---------------------------------------------------------------------------


def merge_delta(
    base: dict, mapping: dict, reg: dict, path_registry_rel: str,
    terminology: dict | None = None,
) -> dict:
    proposed = annotate_mapping(mapping, reg, path_registry_rel, terminology)
    out = copy.deepcopy(base)

    pvars = {v["name"]: v for v in proposed.get("variables") or []}
    vars_out = list(out.get("variables") or [])
    for i, v in enumerate(vars_out):
        if entry_locked(v):
            continue
        p = pvars.get(v["name"])
        if not p:
            continue
        v["data_source"] = p.get("data_source", "")
        v["confidence"] = p.get("confidence")
        v["reasoning"] = p.get("reasoning")
        vars_out[i] = v
    base_names = {v["name"] for v in vars_out}
    for v in proposed.get("variables") or []:
        if v["name"] not in base_names:
            vars_out.append(copy.deepcopy(v))
    out["variables"] = vars_out

    ploops = {L["name"]: L for L in proposed.get("loops") or []}
    loops_out = list(out.get("loops") or [])
    for i, loop in enumerate(loops_out):
        if entry_locked(loop):
            continue
        p = ploops.get(loop["name"])
        if not p:
            continue
        for key in ("data_source", "confidence", "reasoning", "iterator", "foreach", "available_coverages", "type"):
            if key in p:
                loop[key] = copy.deepcopy(p[key])
        pfields = {f.get("placeholder"): f for f in (p.get("fields") or [])}
        new_fields = []
        for fld in loop.get("fields") or []:
            if entry_locked(fld):
                new_fields.append(fld)
                continue
            pf = pfields.get(fld.get("placeholder"))
            if pf:
                nf = copy.deepcopy(fld)
                nf["data_source"] = pf.get("data_source", "")
                nf["confidence"] = pf.get("confidence")
                nf["reasoning"] = pf.get("reasoning")
                new_fields.append(nf)
            else:
                new_fields.append(fld)
        loop["fields"] = new_fields
        loops_out[i] = loop
    base_loop_names = {L["name"] for L in loops_out}
    for L in proposed.get("loops") or []:
        if L["name"] not in base_loop_names:
            loops_out.append(copy.deepcopy(L))
    out["loops"] = loops_out
    out["_idx"] = proposed.get("_idx")
    return out



# ---------------------------------------------------------------------------
# Terminology loader
# ---------------------------------------------------------------------------


def load_terminology(path: Path | None, registry_path: Path | None = None) -> dict | None:
    """Load terminology.yaml following the resolution order from SKILL.md."""
    candidates: list[Path] = []
    if path:
        candidates.append(path)
    if registry_path:
        candidates.append(registry_path.parent / "terminology.yaml")
    candidates.append(Path(__file__).resolve().parent.parent / "registry" / "terminology.yaml")

    for p in candidates:
        if p.exists():
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    return None


# ---------------------------------------------------------------------------
# Plumbing: repo root, emit_telemetry loader
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_emit_telemetry():
    path = _repo_root() / ".cursor" / "skills" / "mapping-suggester" / "scripts" / "emit_telemetry.py"
    spec = importlib.util.spec_from_file_location("emit_telemetry_mod", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"emit_telemetry not found at {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Generic Leg-2 heuristic matcher — any product registry.",
    )
    ap.add_argument("--mapping", type=Path, required=True)
    ap.add_argument("--registry", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--mode",
        choices=("full", "terse", "delta", "batch"),
        default="terse",
        help="Output mode. 'terse' emits condensed review; 'full' adds narrative. "
             "'delta' is not supported for schema 2.0 (see Leg2 plan D10).",
    )
    ap.add_argument("--base-suggested", type=Path, default=None)
    ap.add_argument(
        "--customer-jar", type=Path, default=None,
        help="customer-config.jar with {Product}Quote/{Product}Segment + request types "
             "(default: build/customer-config.jar).",
    )
    ap.add_argument(
        "--datamodel-jar", type=Path, default=None,
        help="core-datamodel-v*.jar (default: newest under build/).",
    )
    ap.add_argument("--config-dir", type=Path, default=None)
    ap.add_argument("--allow-stale-registry", action="store_true")
    ap.add_argument("--allow-missing-registry-fingerprint", action="store_true")
    ap.add_argument("--require-registry-config-check", action="store_true")
    ap.add_argument("--telemetry-log", type=Path, default=None)
    ap.add_argument("--review-out", type=Path, default=None)
    ap.add_argument("--delta-sidecar", type=Path, default=None)
    ap.add_argument(
        "--terminology", type=Path, default=None,
        help="Path to terminology.yaml (default: registry sibling or registry/terminology.yaml).",
    )
    args = ap.parse_args()

    # Delta mode is shape-incompatible with the 2.0 per-root verdicts (D10) —
    # fail loud rather than silently mis-merge a 1.x base.
    if args.mode == "delta":
        print(
            "ERROR: delta mode not supported for schema 2.0 yet (see Leg2 plan D10); "
            "use --mode full/terse/batch",
            file=sys.stderr,
        )
        return 2

    repo_root_early = _repo_root().resolve()
    customer_jar = (
        args.customer_jar.resolve() if args.customer_jar
        else (repo_root_early / "build" / "customer-config.jar")
    )
    if not customer_jar.exists():
        print(f"ERROR: customer jar not found: {customer_jar}", file=sys.stderr)
        return 1
    datamodel_jar = (
        args.datamodel_jar.resolve() if args.datamodel_jar
        else _default_datamodel_jar(repo_root_early)
    )
    if datamodel_jar is None or not datamodel_jar.exists():
        print("ERROR: no core-datamodel jar found (pass --datamodel-jar)", file=sys.stderr)
        return 1
    classpath = f"{customer_jar}:{datamodel_jar}"

    mapping_text = args.mapping.read_text(encoding="utf-8")
    registry_text = args.registry.read_text(encoding="utf-8")
    mapping = yaml.safe_load(mapping_text)
    reg = yaml.safe_load(registry_text)
    meta = reg.get("meta") if isinstance(reg.get("meta"), dict) else {}

    # --- Rendering roots from the filename brackets (D2, §8) -----------------
    product = str(meta.get("product", "")).strip()
    source_value = mapping.get("source") if isinstance(mapping, dict) else None
    if not source_value:
        source_value = args.mapping.name
    root_ids, root_err = parse_rendering_roots(source_value)

    out_stem = args.out.name.replace(".suggested.yaml", "").replace(".yaml", "")
    if root_err or not product:
        blocker = root_err or "registry meta.product is empty — cannot resolve rendering roots"
        review_path = args.review_out or (args.out.parent / f"{out_stem}.review.md")
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(
            f"# {out_stem}.review.md\n\n"
            "## Blockers\n\n"
            f"- **Rendering root**: {blocker}\n\n"
            "No verdicts were produced. SDK-grounded confidence requires a declared "
            "rendering root (plan D2/§8). Rename the source to `<stem>(segment).html` "
            "(or quote/invoice) and re-run.\n",
            encoding="utf-8",
        )
        print(f"BLOCKER: {blocker}", file=sys.stderr)
        print(f"Wrote {review_path}", file=sys.stderr)
        return 2

    roots = roots_for_product(product, root_ids)
    missing_types = [
        r["java_type"] for r in roots
        if r.get("java_type") and not _class_exists(classpath, r["java_type"])
    ]
    if missing_types:
        print(
            "ERROR: declared rendering root type(s) not found in JARs: "
            + ", ".join(missing_types),
            file=sys.stderr,
        )
        return 1

    gate = evaluate_registry_config_gate(
        config_dir=args.config_dir,
        registry_meta=meta,
        require_registry_config_check=args.require_registry_config_check,
        allow_stale_registry=args.allow_stale_registry,
        allow_missing_registry_fingerprint=args.allow_missing_registry_fingerprint,
    )
    escape_note = ""
    if gate.stderr_banner:
        sys.stderr.write(gate.stderr_banner)
        if "ESCAPE HATCH" in gate.stderr_banner:
            escape_note = "ESCAPE HATCH — this run is not registry↔config verified."

    out_parent = args.out.parent.resolve()
    reg_abs = args.registry.resolve()
    repo_root = _repo_root().resolve()
    try:
        out_parent.relative_to(repo_root)
        under_repo = True
    except ValueError:
        under_repo = False
    path_registry_rel = (
        os.path.relpath(reg_abs, out_parent) if under_repo else str(reg_abs)
    )

    # Load terminology
    terminology = load_terminology(args.terminology, args.registry)

    base_suggested: dict | None = None
    base_bytes: bytes | None = None
    if args.mode == "delta":
        if not args.base_suggested:
            print("ERROR: --base-suggested required for mode=delta", file=sys.stderr)
            return 2
        base_bytes = args.base_suggested.read_bytes()
        base_suggested = yaml.safe_load(base_bytes.decode("utf-8"))

    suggested = annotate_mapping(
        mapping, reg, path_registry_rel, terminology,
        roots=roots, classpath=classpath,
    )

    # Strip volatile keys before stamping
    for k in (
        "run_id", "mode", "generated_at",
        "input_mapping_sha256", "input_registry_sha256",
        "registry_schema_version", "registry_generated_at",
        "registry_config_dir", "registry_source_config_sha256",
        "live_source_config_sha256", "registry_config_verified",
        "registry_config_check", "previous_run_id",
        "base_suggested_sha256", "tooling", "delta_changes",
    ):
        suggested.pop(k, None)

    run_id = str(uuid.uuid4())
    gen_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prev_run = None
    base_sha = None
    if base_suggested is not None and base_bytes is not None:
        prev_run = base_suggested.get("run_id")
        if not isinstance(prev_run, str):
            prev_run = None
        base_sha = sha256_bytes(base_bytes)

    prior_reg_sha = None
    prior_src_fp = None
    if base_suggested is not None:
        prior_reg_sha = base_suggested.get("input_registry_sha256")
        if not isinstance(prior_reg_sha, str):
            prior_reg_sha = None
        prior_src_fp = base_suggested.get("registry_source_config_sha256")
        if not isinstance(prior_src_fp, str):
            prior_src_fp = None

    inp_map_sha = sha256_bytes(mapping_text.encode("utf-8"))
    inp_reg_sha = sha256_bytes(registry_text.encode("utf-8"))

    delta_changes = None
    if args.mode == "delta":
        delta_changes = compute_delta_change_set(
            base=base_suggested,
            merged=suggested,
            prior_input_registry_sha256=prior_reg_sha,
            prior_registry_source_config_sha256=prior_src_fp,
            current_input_registry_sha256=inp_reg_sha,
            current_registry_source_config_sha256=gate.registry_source_config_sha256,
        )
        suggested["delta_changes"] = delta_changes

    emb_fp = meta.get("source_config_sha256")
    if isinstance(emb_fp, str):
        emb_fp = emb_fp.strip() or None
    else:
        emb_fp = None

    suggested["schema_version"] = "2.0"
    suggested["run_id"] = run_id
    suggested["mode"] = args.mode
    suggested["generated_at"] = gen_at
    suggested["input_mapping_sha256"] = inp_map_sha
    suggested["input_registry_sha256"] = inp_reg_sha
    suggested["registry_schema_version"] = str(reg.get("schema_version", "1.0"))
    suggested["registry_generated_at"] = str(meta.get("generated_at", ""))
    suggested["registry_config_dir"] = str(meta.get("config_dir", ""))
    suggested["registry_source_config_sha256"] = emb_fp
    suggested["live_source_config_sha256"] = gate.live_source_config_sha256
    suggested["registry_config_verified"] = gate.registry_config_verified
    suggested["registry_config_check"] = gate.registry_config_check
    if prev_run is not None:
        suggested["previous_run_id"] = prev_run
    if base_sha is not None:
        suggested["base_suggested_sha256"] = base_sha
    suggested["tooling"] = {
        "mapping_suggester": {
            "version": "leg2_fill_mapping.py",
            "ruleset_id": "generic_registry_v2",
        }
    }
    suggested = reorder_top_keys(suggested)

    # Strip internal index from YAML output
    idx_for_review = suggested.pop("_idx", {})
    root_ids_for_review = suggested.pop("_root_ids", root_ids)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    stem = args.out.name.replace(".suggested.yaml", "").replace(".yaml", "")
    header = (
        f"# {stem}.suggested.yaml\n"
        "# Suggested mapping — review and confirm each data_source before running the\n"
        "# substitution step. Edit any data_source value, then save as policy-template.mapping.yaml.\n\n"
    )
    body = yaml.dump(
        suggested, sort_keys=False, allow_unicode=True,
        default_flow_style=False, width=120,
    )
    args.out.write_text(header + body, encoding="utf-8")
    result_sha = sha256_file(args.out)

    # Re-attach idx + root ids for review generation (not written to YAML)
    suggested["_idx"] = idx_for_review
    suggested["_root_ids"] = root_ids_for_review

    review_path = args.review_out or (args.out.parent / f"{stem}.review.md")
    _write_review_md(
        review_path,
        stem=stem,
        suggested_path=args.out,
        suggested=suggested,
        mapping_path=args.mapping,
        registry_path=args.registry,
        gate_label=gate.registry_config_check,
        escape_note=escape_note,
        mode=args.mode,
    )

    if args.delta_sidecar and delta_changes is not None:
        args.delta_sidecar.parent.mkdir(parents=True, exist_ok=True)
        args.delta_sidecar.write_text(
            json.dumps(delta_changes, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    if args.telemetry_log:
        emit = _load_emit_telemetry()
        ts = gen_at
        records = emit.derive_run(args.out, args.registry, run_id=run_id, ts=ts)
        summ = records[-1]
        summ["result_suggested_sha256"] = result_sha
        emit.append_jsonl(args.telemetry_log, records)

    print(f"Wrote {args.out}")
    print(f"Wrote {review_path}")
    if args.telemetry_log:
        print(f"Appended telemetry to {args.telemetry_log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
