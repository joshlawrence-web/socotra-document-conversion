#!/usr/bin/env python3
"""Shared registry matching for Leg -1 (and reusable by other legs).

Leg 2's token matcher expects the strict ``EntityType.fieldName`` dotted form
(see ``leg2_fill_mapping.match_token``). Leg -1 has the *opposite* problem: an
author writes a **bare leaf token** like ``{firstName}`` and we must find the
full accessor (``account.data.firstName``) the registry would expect.

This module owns that bare-leaf → accessor matching. It is **registry-only** —
no compiled JAR, no SDK introspection — so its verdicts are weaker than Leg 2's
JAR-graded confidence and are deliberately labelled differently (``exact`` /
``ambiguous`` / ``name-similar`` / ``unmatched``) to avoid implying a path was
verified to navigate on the rendering root. Leg 2 still does that downstream.

The genuinely shared pieces — rendering-root parsing and the iterable index —
are imported from ``leg2_fill_mapping`` so the two legs cannot drift.
"""

from __future__ import annotations

import re
from pathlib import Path

# Reuse Leg 2's helpers so root parsing / iterable lookup stay in lockstep.
from velocity_converter.leg2_fill_mapping import (  # noqa: F401
    build_registry_index,
    parse_rendering_roots,
    suggest_loop_root,
)


def _velocity_to_accessor(velocity: str, category: str) -> str:
    """Derive the shorthand accessor a user would write from a velocity path.

    Mirrors ``agent_tools._velocity_to_accessor`` / ``leg0_ingest._derive_accessor``
    so the emitted accessor is a key Leg 0's ``build_velocity_lookup`` resolves.
    """
    v = (velocity or "").strip()
    cat = (category or "").strip()
    if cat in ("system", "policy_data"):
        return "policy." + v[len("$data."):] if v.startswith("$data.") else v.lstrip("$")
    if cat == "quote_system":
        return "quote." + v[len("$data."):] if v.startswith("$data.") else v.lstrip("$")
    if v.startswith("$data."):
        return v[len("$data."):]
    if v.startswith("$"):
        return v[1:]
    return v


def _norm(s: str) -> str:
    """Normalise a name/label for loose comparison: lowercase, alnum only."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def build_candidate_index(reg: dict, roots: list[str] | None = None) -> list[dict]:
    """Walk the registry into a flat list of accessor candidates.

    Each candidate is a dict::

        {leaf, field, display, accessor, velocity, category, exposure,
         quantifier, options, source, datafetcher}

    ``exposure`` is ``None`` for document-level entries and the iterable name
    (e.g. ``"Item"``) for fields/coverages inside an exposure — this is what
    lets Leg -1 scope a bare leaf by loop membership.

    When ``roots`` contains ``"quote"``, policy custom-data fields additionally
    yield a ``quote.data.<field>`` candidate (ranked ahead of the policy form on
    quote documents), matching ``build_velocity_lookup``'s quote-data aliases.
    On a **quote-only** document (``quote`` declared, no policy-side ``segment``
    root) the ``policy.data.<field>`` form is suppressed entirely: there is no
    policy at quote time in the policy lifecycle, so emitting it would manufacture
    a false ambiguity between the quote and policy accessors of the same field.
    """
    roots = roots or []
    quote_root = "quote" in roots
    # The policy.data.* accessor only exists once a policy/segment exists. On a
    # quote-only document the policy doesn't exist yet, so suppress that form and
    # keep only the quote alias (avoids a bogus quote-vs-policy ambiguity).
    quote_only = quote_root and "segment" not in roots
    out: list[dict] = []

    def _add(entry: dict, exposure: str | None, *, accessor: str | None = None,
             velocity: str | None = None, df: dict | None = None) -> None:
        field = str(entry.get("field") or "")
        if not field:
            return
        vel = velocity if velocity is not None else str(entry.get("velocity") or "")
        cat = str(entry.get("category") or "")
        acc = accessor if accessor is not None else _velocity_to_accessor(vel, cat)
        out.append({
            "leaf": field.lower(),
            "field": field,
            "display": str(entry.get("display_name") or ""),
            "accessor": acc,
            "velocity": vel,
            "category": cat,
            "exposure": exposure,
            "quantifier": str(entry.get("quantifier") or ""),
            "options": list(entry.get("options") or []),
            "source": str(entry.get("source") or ""),
            "datafetcher": df,
        })

    for section in ("system_paths", "quote_paths", "account_paths", "quote_data"):
        for e in reg.get(section) or []:
            if isinstance(e, dict):
                _add(e, None)

    # Datafetcher entries carry their wiring forward for Leg 4.
    for e in reg.get("datafetcher_paths") or []:
        if isinstance(e, dict):
            df = {
                "datafetcher_method": e.get("datafetcher_method", ""),
                "datafetcher_arg": e.get("datafetcher_arg"),
                "datafetcher_key": e.get("datafetcher_key", ""),
                "valid_roots": list(e.get("valid_roots") or []),
            }
            _add(e, None, df=df)

    # Policy custom data — on a quote document the accessor lives under $data.quote.
    for e in reg.get("policy_data") or []:
        if not isinstance(e, dict):
            continue
        vel = str(e.get("velocity") or "")
        has_quote_alias = quote_root and vel.startswith("$data.data.")
        if has_quote_alias:
            _add(e, None, accessor="quote." + vel[len("$data."):],
                 velocity="$data.quote." + vel[len("$data."):])
        # On a quote-only doc, skip the policy form once we've emitted the quote
        # alias — the field is still offered (as the quote accessor), just not
        # duplicated as a non-existent policy accessor.
        if has_quote_alias and quote_only:
            continue
        _add(e, None)

    # Policy charges have name/velocity_amount, not field/velocity — bridge them.
    for c in reg.get("policy_charges") or []:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "")
        amount = str(c.get("velocity_amount") or "")
        if name and amount:
            out.append({
                "leaf": name.lower(), "field": name, "display": f"{name} charge",
                "accessor": _velocity_to_accessor(amount, "charge"),
                "velocity": amount, "category": "policy_charge", "exposure": None,
                "quantifier": "", "options": [], "source": "", "datafetcher": None,
            })

    for exp in reg.get("exposures") or []:
        if not isinstance(exp, dict):
            continue
        exp_name = str(exp.get("name") or "")
        for e in (exp.get("fields") or []) + (exp.get("system_fields") or []):
            if isinstance(e, dict):
                _add(e, exp_name)
        for cov in exp.get("coverages") or []:
            if not isinstance(cov, dict):
                continue
            for e in cov.get("fields") or []:
                if isinstance(e, dict):
                    _add(e, exp_name)
            for ch in cov.get("charges") or []:
                if isinstance(ch, dict):
                    cname = str(ch.get("name") or "")
                    amount = str(ch.get("velocity_amount") or "")
                    if cname and amount:
                        out.append({
                            "leaf": cname.lower(), "field": cname,
                            "display": f"{cov.get('name')} {cname} charge",
                            "accessor": _velocity_to_accessor(amount, "charge"),
                            "velocity": amount, "category": "coverage_charge",
                            "exposure": exp_name, "quantifier": "", "options": [],
                            "source": "", "datafetcher": None,
                        })

    return out


def match_leaf(leaf: str, loop_name: str | None, candidates: list[dict]) -> dict:
    """Resolve a bare leaf token against the candidate index.

    ``loop_name`` is the iterable name the placeholder sits inside (from loop
    markers) or ``None`` for document-level. Returns::

        {status, match, chosen, alternatives, scope_note}

    ``status`` ∈ {resolved, ambiguous, unmatched}; ``match`` ∈
    {exact, name-similar, ""}. ``alternatives`` is the full ranked candidate
    list (each {accessor, velocity, why, exposure, quantifier, datafetcher}).
    """
    nl = _norm(leaf)
    in_scope = [c for c in candidates if c["exposure"] == loop_name]
    scope_note = ""
    if loop_name and not in_scope:
        # Leaf inside a loop but only document-level matches exist — surface
        # them, but flag that the registry has no in-exposure field by this name.
        in_scope = [c for c in candidates if c["exposure"] is None]
        scope_note = (
            f"no field named `{leaf}` inside exposure `{loop_name}` — "
            "showing document-level matches; confirm scope"
        )

    exact = [c for c in in_scope if c["leaf"] == leaf.lower()]
    if not exact:
        exact = [c for c in in_scope if _norm(c["field"]) == nl]
    similar = [
        c for c in in_scope
        if c not in exact and (_norm(c["display"]) == nl or nl and nl in _norm(c["display"]))
    ]

    def _alt(c: dict, why: str) -> dict:
        return {
            "accessor": c["accessor"], "velocity": c["velocity"], "why": why,
            "exposure": c["exposure"], "quantifier": c["quantifier"],
            "options": c["options"], "datafetcher": c["datafetcher"],
            "source": c["source"],
        }

    # Rank exact before name-similar, then DEDUPE by accessor: two registry rows
    # that resolve to the same accessor (e.g. an account field also mirrored as a
    # DataFetcher row) are one choice, not an ambiguity. Exact wins the dedupe.
    ranked: list[dict] = []
    seen_acc: set = set()
    exact_accs: list[str] = []
    similar_accs: list[str] = []
    for c in exact:
        why = (f"exact registry field `{c['field']}`"
               + (f" ({c['exposure']} exposure)" if c["exposure"] else "")
               + f" [{c['category']}]")
        if c["accessor"] not in seen_acc:
            seen_acc.add(c["accessor"]); exact_accs.append(c["accessor"]); ranked.append(_alt(c, why))
    for c in similar:
        if c["accessor"] not in seen_acc:
            seen_acc.add(c["accessor"]); similar_accs.append(c["accessor"])
            ranked.append(_alt(c, f"name-similar to display `{c['display']}` [{c['category']}]"))

    if not ranked:
        return {"status": "unmatched", "match": "", "chosen": "",
                "alternatives": [], "scope_note": scope_note}
    # A single exact accessor wins even if looser name-similar rows also exist.
    if len(exact_accs) == 1:
        return {"status": "resolved", "match": "exact",
                "chosen": exact_accs[0], "alternatives": ranked, "scope_note": scope_note}
    if not exact_accs and len(similar_accs) == 1:
        return {"status": "resolved", "match": "name-similar",
                "chosen": similar_accs[0], "alternatives": ranked, "scope_note": scope_note}
    # >1 distinct accessor with no single exact winner — the human must pick.
    return {"status": "ambiguous", "match": "exact" if exact_accs else "name-similar",
            "chosen": "", "alternatives": ranked, "scope_note": scope_note}
