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

from suggester_state import (
    compute_delta_change_set,
    entry_locked,
    evaluate_registry_config_gate,
    sha256_bytes,
    sha256_file,
)

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

    for section in ("system_paths", "account_paths", "policy_data"):
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


def _step1_exact(name_camel: str, label: str | None, idx: dict) -> list[dict]:
    hits: list[dict] = []
    for e in idx["by_field"].get(name_camel.lower(), []):
        if e.get("field") == name_camel and e not in hits:
            hits.append(e)
    if label:
        for e in idx["by_display_name"].get(label.lower(), []):
            if e.get("display_name") == label and e not in hits:
                hits.append(e)
    return hits


def _step2_ci(name_camel: str, label: str | None, idx: dict) -> list[dict]:
    hits: list[dict] = []
    for e in idx["by_field"].get(name_camel.lower(), []):
        if e not in hits:
            hits.append(e)
    if label:
        for e in idx["by_display_name"].get(label.lower(), []):
            if e not in hits:
                hits.append(e)
    return hits


def _step3_terminology(
    name_snake: str, label: str | None, idx: dict, terminology: dict
) -> list[tuple[dict, str]]:
    """Returns (entry, alias_used) pairs from terminology synonyms."""
    syns = terminology.get("synonyms") or {}
    aliases_map = terminology.get("display_name_aliases") or {}
    hits: list[tuple[dict, str]] = []

    for canonical, aliases in (syns.get("fields") or {}).items():
        for alias in aliases:
            if alias.lower() in (name_snake.lower(), (label or "").lower()):
                for e in idx["by_field"].get(canonical.lower(), []):
                    if (e, alias) not in hits:
                        hits.append((e, alias))

    for canonical_dn, aliases in aliases_map.items():
        for alias in aliases:
            if alias.lower() in (name_snake.lower(), (label or "").lower()):
                for e in idx["by_display_name"].get(canonical_dn.lower(), []):
                    if (e, alias) not in hits:
                        hits.append((e, alias))

    return hits


def _step4_fuzzy(name_snake: str, label: str | None, idx: dict) -> list[dict]:
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

    hits = _step1_exact(name_camel, label, idx)
    if hits:
        return hits, "exact", None

    hits = _step2_ci(name_camel, label, idx)
    if hits:
        return hits, "ci", None

    if terminology:
        term_hits = _step3_terminology(name_snake, label, idx, terminology)
        if term_hits:
            return [e for e, _ in term_hits], "terminology", term_hits[0][1]

    hits = _step4_fuzzy(name_snake, label, idx)
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


def _confidence_from_step(step: str) -> str:
    if step in ("exact", "ci", "terminology"):
        return "high"
    if step == "fuzzy":
        return "medium"
    return "low"


def suggest_variable(
    v: dict, idx: dict, terminology: dict | None
) -> tuple[str, str, str]:
    """Returns (data_source, confidence, reasoning)."""
    name = v.get("name") or ""
    context = v.get("context") or {}
    label = context.get("nearest_label") or None

    entries, step, alias = match_name(name, label, idx, terminology)

    name_snake = normalize_mapping_field_name(name)
    name_camel = snake_to_camel(name_snake)

    if not entries:
        return "", "low", f"no registry match for {name_camel} — next-action: supply-from-plugin"

    # Apply scope filter
    ok: list[dict] = []
    violated: list[tuple[dict, str]] = []
    for e in entries:
        s = check_scope(e, context, idx)
        if s in ("not_required", "satisfied"):
            ok.append(e)
        else:
            violated.append((e, s))

    if not ok:
        # All matches are scope violations
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
        return "", "low", reason

    # Multiple unambiguous matches → pick-one
    if len(ok) > 1:
        paths = " | ".join(e.get("velocity") or e.get("velocity_amount") or "" for e in ok)
        return "", "medium", f"{name_camel} has multiple registry candidates — next-action: pick-one: {paths}"

    # Single match
    e = ok[0]
    vel = e.get("velocity") or ""
    if not vel:
        vel = _charge_path(e, label)

    confidence = _confidence_from_step(step)
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
        reason = (
            f"matched via terminology.yaml synonym `{alias}` → canonical `{field}` → {vel}"
        )
    elif step == "fuzzy":
        reason = f"fuzzy match: {name_camel} → {vel} — next-action: confirm-assumption"
    else:
        reason = f"no match for {name_camel} — next-action: supply-from-plugin"

    reason += _quantifier_note(e)
    return vel, confidence, reason


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
    Returns (data_source, confidence, reasoning, iterator, foreach, available_coverages).
    available_coverages is a list (may be empty).
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
            "", "low",
            f"loop `{loop_name}` has no matching iterable in registry — next-action: supply-from-plugin",
            None, None, [],
        )

    list_vel = str(it.get("list_velocity") or "")
    iterator = str(it.get("iterator") or "")
    foreach = str(it.get("foreach") or "")
    it_name = str(it.get("name") or "")
    confidence = "high" if step in ("exact", "ci", "terminology") else "medium"

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

    return list_vel, confidence, reasoning, iterator, foreach, cov_manifest


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
    m = re.match(r"\$(\w+)\.TBD_(\w+)", ph)
    if not m:
        return "", "low", "unparseable loop_field placeholder — next-action: needs-skill-update"

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
        return "", "low", f"iterator `{it_raw}` not mapped to any iterable — next-action: supply-from-plugin"

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
        return vel, "high", f"{fld_snake} → {vel} ({it_name} exposure)"

    # Step 4: fuzzy last token on exposure data fields
    tokens = fld_snake.split("_")
    if tokens and tokens[-1] in exp_fields:
        e = exp_fields[tokens[-1]]
        vel = e.get("velocity") or ""
        return vel, "medium", f"{fld_snake} → {vel} ({it_name} exposure, fuzzy) — next-action: confirm-assumption"

    # Coverage field fallback: decompose '<prefix>_<field>' against any coverage
    cov_result = _match_coverage_field(fld_snake, exp_coverages)
    if cov_result:
        vel, cov_q, cov_name = cov_result
        note = _quantifier_note({"quantifier": cov_q, "velocity": vel.rsplit(".data.", 1)[0] if ".data." in vel else vel})
        return vel, "high", f"{fld_snake} → {vel} ({it_name} {cov_name} coverage){note}"

    return "", "low", f"{fld_snake} not found in {it_name} exposure — next-action: supply-from-plugin"


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
        "product", "tooling", "delta_changes",
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


def annotate_mapping(
    mapping: dict,
    reg: dict,
    path_registry_rel: str,
    terminology: dict | None = None,
) -> dict:
    idx = build_registry_index(reg)

    out = copy.deepcopy(mapping)
    out["schema_version"] = out.get("schema_version") or "1.0"
    out["input_mapping_version"] = str(out.get("schema_version", "1.0"))
    out["input_registry_version"] = str(reg.get("schema_version", "1.0"))
    out["path_registry"] = path_registry_rel
    out["product"] = str((reg.get("meta") or {}).get("product", ""))

    for v in out.get("variables") or []:
        ds, conf, reason = suggest_variable(v, idx, terminology)
        v["data_source"] = ds
        v["confidence"] = conf
        v["reasoning"] = reason

    for loop in out.get("loops") or []:
        ln = loop["name"]
        ds, conf, reason, iterator, foreach, cov_manifest = suggest_loop_root(
            ln, idx, terminology, reg
        )
        loop["data_source"] = ds
        loop["confidence"] = conf
        loop["reasoning"] = reason
        loop["type"] = "loop"
        if iterator:
            loop["iterator"] = iterator
        if foreach:
            loop["foreach"] = foreach
        if cov_manifest:
            loop["available_coverages"] = cov_manifest

        for fld in loop.get("fields") or []:
            ph = fld.get("placeholder") or ""
            fds, fconf, freason = suggest_loop_field(ph, ln, idx, reg)
            fld["data_source"] = fds
            fld["confidence"] = fconf
            fld["reasoning"] = freason

    # Stash index metadata for review generation (stripped before write)
    out["_idx"] = idx
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
# Review.md helpers
# ---------------------------------------------------------------------------

_NA_RE = re.compile(r"next-action:\s*([a-z-]+)")
_CANDIDATE_RE = re.compile(r"registry candidate `([^`]+)`")

_RESOLUTION = {
    "supply-from-plugin": (
        "No registry path exists for this field. "
        "A plugin (DocumentDataSnapshotPlugin or equivalent) must supply it as a scalar on `$data.data.*`."
    ),
    "restructure-template": (
        "A registry path exists but the template is missing the required `#foreach` wrapper. "
        "Add the foreach block shown in `requires_scope` and move this variable inside it."
    ),
    "pick-one": (
        "Multiple registry paths are equally plausible. "
        "Review the candidates and set `data_source` to the correct one before running Leg 3."
    ),
    "delete-from-template": "This field has no business purpose in this document. Remove the placeholder.",
    "confirm-assumption": "",  # medium only — appears in §4 not §3
}


def _extract_na(reasoning: str) -> str | None:
    m = _NA_RE.search(reasoning)
    return m.group(1) if m else None


def _extract_candidates(reasoning: str) -> list[str]:
    """Parse 'pick-one: $a | $b | $c' or similar from reasoning."""
    m = re.search(r"pick-one:\s*(.+)", reasoning)
    if m:
        return [p.strip() for p in m.group(1).split("|") if p.strip()]
    return []


def _fmt_line(entry: dict) -> int:
    return (entry.get("context") or {}).get("line") or 999


def _all_entries(suggested: dict) -> list[dict]:
    return list(suggested.get("variables") or []) + list(suggested.get("loops") or [])


# ---------------------------------------------------------------------------
# Full review.md writer (all 7 sections)
# ---------------------------------------------------------------------------


def _write_review_md(
    review_path: Path,
    *,
    stem: str,
    suggested_path: Path,
    suggested: dict,
    mapping_path: Path,
    registry_path: Path,
    gate_label: str,
    escape_note: str,
    mode: str = "terse",
) -> None:
    idx: dict = suggested.get("_idx") or {}
    variables = suggested.get("variables") or []
    loops = suggested.get("loops") or []
    all_e = list(variables) + list(loops)

    high_v = sum(1 for v in variables if v.get("confidence") == "high")
    med_v = sum(1 for v in variables if v.get("confidence") == "medium")
    low_v = sum(1 for v in variables if v.get("confidence") == "low")
    high_l = sum(1 for L in loops if L.get("confidence") == "high")
    med_l = sum(1 for L in loops if L.get("confidence") == "medium")
    low_l = sum(1 for L in loops if L.get("confidence") == "low")
    high = high_v + high_l
    med = med_v + med_l
    low = low_v + low_l

    # Next-action counts
    na_counts: dict[str, int] = {}
    for e in all_e:
        na = _extract_na(e.get("reasoning") or "")
        if na:
            na_counts[na] = na_counts.get(na, 0) + 1

    dc = suggested.get("delta_changes") or {}

    lines: list[str] = [
        "<!-- schema_version: 1.1 -->",
        "",
        f"# Mapping review — {stem}",
        "",
        f"- Run id: `{suggested.get('run_id', '')}`",
        f"- Mode: **{suggested.get('mode', 'terse')}**",
        f"- Source mapping: `{mapping_path}`",
        f"- Suggested output: `{suggested_path}`",
        f"- Path registry: `{registry_path}`",
        f"- Product: **{suggested.get('product', '')}**",
        f"- Generated at: {suggested.get('generated_at', '')}",
        (
            f"- Inputs: mapping sha256 `{suggested.get('input_mapping_sha256', '')[:16]}…`, "
            f"registry sha256 `{suggested.get('input_registry_sha256', '')[:16]}…`"
        ),
        (
            f"- Registry lineage: generated `{suggested.get('registry_generated_at', '')}`, "
            f"config_dir `{suggested.get('registry_config_dir', '')}`"
        ),
        (
            f"- Registry config check: **{gate_label}** "
            f"(verified={'yes' if suggested.get('registry_config_verified') else 'no'})"
        ),
    ]
    if suggested.get("mode") == "delta":
        lines.append(
            f"- Base suggested: `{suggested.get('base_suggested_sha256', '')[:16]}…` "
            f"(previous_run_id `{suggested.get('previous_run_id', '')}`)"
        )
    if escape_note:
        lines += ["", f"> **{escape_note}**", ""]
    lines += [
        f"- Schema: 1.1 (mapping {suggested.get('input_mapping_version')}, "
        f"registry {suggested.get('input_registry_version')})",
        "",
        "---",
        "",
    ]

    # §1 already written above. §2 State summary + counts.
    lines += [
        "## State summary",
        "",
        f"- `run_id`: `{suggested.get('run_id', '')}`",
        f"- `registry_config_check`: {suggested.get('registry_config_check', '')}",
    ]
    if suggested.get("mode") == "delta":
        lines.append(
            f"- Delta: changed={len(dc.get('changed') or [])}, "
            f"cleared={len(dc.get('cleared') or [])}, "
            f"re-suggested={len(dc.get('re_suggested_unconfirmed') or [])}, "
            f"carried_confirmed={dc.get('carried_forward_count', 0)}"
        )
    lines += [
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "|---|---|",
        f"| Variables (total) | {len(variables)} |",
        f"| Loops (total) | {len(loops)} |",
        f"| high | {high} |",
        f"| medium | {med} |",
        f"| low | {low} |",
        "",
        "### Next-action breakdown",
        "",
        "| next-action | Count |",
        "|---|---|",
    ]
    for code in ("pick-one", "supply-from-plugin", "restructure-template",
                 "confirm-assumption", "delete-from-template"):
        cnt = na_counts.get(code, 0)
        lines.append(f"| {code} | {cnt} |")
    lines.append("")

    # Per-confidence breakdown (subsections of Summary)
    for conf_label, conf_key in (("High", "high"), ("Medium", "medium"), ("Low", "low")):
        conf_loops = [L for L in loops if L.get("confidence") == conf_key]
        conf_vars = [v for v in variables if v.get("confidence") == conf_key]
        if not conf_loops and not conf_vars:
            continue
        lines += [
            f"### {conf_label} confidence",
            "",
            "| Type | Count |",
            "|---|---|",
            f"| Loops | {len(conf_loops)} |",
            f"| Fields | {len(conf_vars)} |",
            "",
        ]
        if conf_loops:
            lines += ["**Loop names**", "", "| Name | Velocity Path |", "|---|---|"]
            for L in conf_loops:
                ph = L.get("placeholder") or L.get("name") or ""
                vel = L.get("data_source") or "—"
                lines.append(f"| `{ph}` | `{vel}` |")
            lines.append("")
        if conf_vars:
            lines += ["**Field names**", "", "| Name | Velocity Path |", "|---|---|"]
            for v in conf_vars:
                ph = v.get("placeholder") or v.get("name") or ""
                vel = v.get("data_source") or "—"
                lines.append(f"| `{ph}` | `{vel}` |")
            lines.append("")

    # §3 Blockers
    lines += ["---", "", "## Blockers", ""]
    blockers = sorted([e for e in all_e if e.get("confidence") == "low"], key=_fmt_line)
    if not blockers:
        lines.append("No blockers.")
    elif mode == "terse":
        lines += [
            "| Placeholder | Line | next-action |",
            "|---|---|---|",
        ]
        for e in blockers:
            ph = e.get("placeholder") or e.get("name") or ""
            ln = _fmt_line(e)
            na = _extract_na(e.get("reasoning") or "") or "supply-from-plugin"
            lines.append(f"| `{ph}` | {ln} | {na} |")
    else:
        for e in blockers:
            ph = e.get("placeholder") or e.get("name") or ""
            ctx = e.get("context") or {}
            ln = ctx.get("line") or "?"
            parent_tag = ctx.get("parent_tag") or "—"
            nearest_label = ctx.get("nearest_label") or ""
            loop_ctx = ctx.get("loop") or "—"
            reasoning = e.get("reasoning") or ""
            na = _extract_na(reasoning) or "supply-from-plugin"
            cands = _extract_candidates(reasoning)
            lines += [
                f"### {ph}  _(line {ln})_",
                "",
                f"- **parent_tag:** `{parent_tag}`",
                f"- **nearest_label:** \"{nearest_label}\"",
                f"- **loop:** `{loop_ctx}`",
            ]
            if cands:
                lines.append("- **candidates:**")
                for c in cands:
                    lines.append(f"  - `{c}`")
            lines += [
                f"- **next-action:** `{na}`",
                f"- **suggested resolution:** {_RESOLUTION.get(na, '')}",
                "",
            ]
    lines.append("")

    # §4 Assumptions to confirm
    lines += ["---", "", "## Assumptions to confirm", ""]
    assumptions = sorted(
        [e for e in all_e if e.get("confidence") == "medium" and "confirm-assumption" in (e.get("reasoning") or "")],
        key=_fmt_line,
    )
    if not assumptions:
        lines.append("No assumptions to confirm.")
    elif mode == "terse":
        lines.append(f"{len(assumptions)} assumption(s) to confirm — see .suggested.yaml")
    else:
        for e in assumptions:
            ph = e.get("placeholder") or e.get("name") or ""
            ds = e.get("data_source") or ""
            ctx = e.get("context") or {}
            ln = ctx.get("line") or "?"
            reasoning = e.get("reasoning") or ""
            m = re.search(r"confirm-assumption:\s*(.+?)(?:\s*—|$)", reasoning)
            assumption_text = m.group(1).strip() if m else reasoning
            lines += [
                f"- [ ] **{assumption_text}**",
                f"  - `{ph}` (line {ln}) → `{ds}`",
            ]
    lines.append("")

    # §5 Cross-scope warnings
    lines += ["---", "", "## Cross-scope warnings", ""]
    scope_warns = sorted(
        [
            e for e in all_e
            if "scope violation" in (e.get("reasoning") or "").lower()
            or (
                "restructure-template" in (e.get("reasoning") or "")
                and "registry candidate" in (e.get("reasoning") or "")
            )
        ],
        key=_fmt_line,
    )
    if not scope_warns:
        lines.append("No cross-scope warnings.")
    else:
        lines += [
            "| Placeholder | Matched path | Requires scope | Fix |",
            "|---|---|---|---|",
        ]
        for e in scope_warns:
            ph = e.get("placeholder") or e.get("name") or ""
            reasoning = e.get("reasoning") or ""
            cand_m = _CANDIDATE_RE.search(reasoning)
            matched_path = cand_m.group(1) if cand_m else ""
            req_m = re.search(r"`(#foreach[^`]+)`", reasoning)
            req_scope = req_m.group(1) if req_m else "—"
            lines.append(f"| `{ph}` | `{matched_path}` | `{req_scope}` | restructure-template |")
    lines.append("")

    # §6 Done
    lines += ["---", "", "## Done", ""]
    done = [e for e in all_e if e.get("confidence") == "high"]
    if mode == "terse":
        lines += [
            "<details>",
            f"<summary><strong>{len(done)}</strong> high-confidence mapping(s)</summary>",
            "",
        ]
        for e in done:
            ph = e.get("placeholder") or e.get("name") or ""
            ds = e.get("data_source") or ""
            lines.append(f"- `{ph}` → `{ds}`")
        lines += ["", "</details>"]
    else:
        lines += [
            "<details>",
            f"<summary><strong>{len(done)}</strong> high-confidence mapping(s)</summary>",
            "",
        ]
        for e in done:
            ph = e.get("placeholder") or e.get("name") or ""
            ds = e.get("data_source") or ""
            reason = e.get("reasoning") or ""
            lines.append(f"- `{ph}` → `{ds}`  _{reason}_")
        lines += ["", "</details>"]
    lines.append("")

    # §7 Unrecognised inputs
    lines += ["---", "", "## Unrecognised inputs", ""]
    refusal_flags = idx.get("refusal_flags") or []
    partial_flags = idx.get("partial_flags") or []
    reg_minor = _check_minor_mismatch(suggested)

    unrecognised_rows: list[tuple[str, str, str, str]] = []
    if reg_minor:
        unrecognised_rows.append((
            "registry",
            f"schema_version MINOR={reg_minor}",
            "all entries",
            "needs-skill-update: registry schema MINOR version exceeds supported MINOR",
        ))
    for flag in refusal_flags:
        unrecognised_rows.append((
            "registry",
            f"feature_support.{flag}",
            "all variables",
            f"needs-skill-update: refusal flag `{flag}` is true; affected entries may need manual handling",
        ))
    for flag in partial_flags:
        unrecognised_rows.append((
            "registry",
            f"feature_support.{flag}",
            "all variables",
            f"needs-skill-update: partial-support flag `{flag}` is true; verify coverage",
        ))

    if not unrecognised_rows:
        lines.append("No unrecognised inputs.")
    else:
        lines += [
            "| Source | Key | Seen on | Next-action |",
            "|---|---|---|---|",
        ]
        for source, key, seen, na in unrecognised_rows:
            lines.append(f"| {source} | `{key}` | {seen} | {na} |")
    lines.append("")

    review_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _check_minor_mismatch(suggested: dict) -> str | None:
    """Return the registry MINOR version string if it exceeds 1.1, else None."""
    rv = str(suggested.get("registry_schema_version") or "1.0")
    parts = rv.split(".")
    try:
        if len(parts) >= 2 and int(parts[1]) > 1:
            return rv
    except ValueError:
        pass
    return None


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
    candidates.append(Path(__file__).resolve().parent.parent / "terminology.yaml")

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
# Legacy index functions (used by suggester_state / emit_telemetry)
# ---------------------------------------------------------------------------


def index_registry(reg: dict) -> tuple[dict[str, list[str]], list[dict]]:
    """field_camel_lower → [velocity,...] for unscoped entries (legacy path)."""
    flat: dict[str, list[str]] = {}
    iterables: list[dict] = list(reg.get("iterables") or [])

    def consider(obj: object) -> None:
        if isinstance(obj, list):
            for item in obj:
                consider(item)
            return
        if not isinstance(obj, dict):
            return
        req = obj.get("requires_scope") or []
        vel = obj.get("velocity")
        field = obj.get("field")
        if isinstance(vel, str) and isinstance(field, str) and not req:
            k = field.lower()
            flat.setdefault(k, []).append(vel)
        for v in obj.values():
            if isinstance(v, (dict, list)):
                consider(v)

    consider(reg)
    return flat, iterables


def exposure_field_index(reg: dict) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for exp in reg.get("exposures") or []:
        ename = str(exp.get("name", "")).lower()
        for f in exp.get("fields") or []:
            fn = str(f.get("field", "")).lower()
            vel = f.get("velocity")
            if isinstance(vel, str):
                out[(ename, fn)] = vel
    return out


def iterables_by_iterator(reg: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for it in reg.get("iterables") or []:
        it_name = str(it.get("iterator", "")).removeprefix("$").lower()
        if it_name:
            out[it_name] = it
    return out


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
             "'delta' requires --base-suggested.",
    )
    ap.add_argument("--base-suggested", type=Path, default=None)
    ap.add_argument("--config-dir", type=Path, default=None)
    ap.add_argument("--allow-stale-registry", action="store_true")
    ap.add_argument("--allow-missing-registry-fingerprint", action="store_true")
    ap.add_argument("--require-registry-config-check", action="store_true")
    ap.add_argument("--telemetry-log", type=Path, default=None)
    ap.add_argument("--review-out", type=Path, default=None)
    ap.add_argument("--delta-sidecar", type=Path, default=None)
    ap.add_argument(
        "--terminology", type=Path, default=None,
        help="Path to terminology.yaml (default: repo-root or registry sibling).",
    )
    args = ap.parse_args()

    mapping_text = args.mapping.read_text(encoding="utf-8")
    registry_text = args.registry.read_text(encoding="utf-8")
    mapping = yaml.safe_load(mapping_text)
    reg = yaml.safe_load(registry_text)
    meta = reg.get("meta") if isinstance(reg.get("meta"), dict) else {}

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

    if args.mode == "delta" and base_suggested is not None:
        suggested = merge_delta(base_suggested, mapping, reg, path_registry_rel, terminology)
    else:
        suggested = annotate_mapping(mapping, reg, path_registry_rel, terminology)

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

    suggested["schema_version"] = "1.1"
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

    # Re-attach idx for review generation (not written to YAML)
    suggested["_idx"] = idx_for_review

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
