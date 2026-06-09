#!/usr/bin/env python3
"""Leg 4 — Document Data Snapshot Plugin Generator.

Reads:
  - <stem>.suggested.yaml  (Leg 2) — provides `product:` and `variables:`
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

# Shared SDK-introspection helpers (Leg 2 plan P1.1 — single source of JAR truth).
from sdk_introspect import (
    CUSTOMER_PACKAGE,
    DATAFETCHER_INTERFACE,
    INVOICE_REQUEST,
    PLUGIN_INTERFACE,
    _class_exists,
    _default_datamodel_jar,
    _default_slf4j_jar,
    _method_return_type,
    _unwrap_type,
    validate_path,
)


# ---------------------------------------------------------------------------
# Helpers (mirrors scripts/leg3_substitute.py)
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
            "data_source": verdict.get("data_source") or "",
            "confidence": verdict.get("confidence") or "",
            "reasoning": verdict.get("reasoning") or "",
        }

    new_vars = [_promote(v) for v in (suggested.get("variables") or [])]
    return {**suggested, "variables": new_vars}


# JAR introspection (_javap / _zero_arg_methods / _unwrap_type / validate_path /
# _default_datamodel_jar / _class_exists) now lives in scripts/sdk_introspect.py
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
 * Generated by scripts/leg4_generate_plugin.py from %(suggested_name)s — review
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
%(quote_datafetcher_extras)s%(quote_conditional_puts)s
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
%(policy_datafetcher_extras)s%(policy_conditional_puts)s
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


def _parse_existing_cond_high_water(java_path: Path) -> int:
    """Return the highest condN key in an existing plugin (e.g. cond50 → 50), or 0 if none."""
    if not java_path.exists():
        return 0
    matches = re.findall(r'renderingData\.put\("cond(\d+)"', java_path.read_text(encoding="utf-8"))
    return max((int(m) for m in matches), default=0)


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

    for b in cond_blocks:
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
) -> None:
    """Write a backup then insert missing puts before each overload's builder return.

    Quote DataFetcher calls → quote overload.
    Policy DataFetcher calls → policy overload.
    Conditional puts → both overloads (document-scoped, decision A4).
    Also inserts any new dynamic imports needed for new DataFetcher return types.
    """
    quote_df_code = _generate_datafetcher_extras(missing_quote_df)
    policy_df_code = _generate_datafetcher_extras(missing_policy_df)
    quote_cond_code = render_conditional_puts(offset_cond_blocks, scope="quote")
    policy_cond_code = render_conditional_puts(offset_cond_blocks, scope="policy")

    if not quote_df_code and not policy_df_code and not quote_cond_code:
        return

    bak = java_path.with_suffix(".java.bak")
    bak.write_bytes(java_path.read_bytes())

    text = java_path.read_text(encoding="utf-8")

    # Insert missing dynamic imports for new DataFetcher return types.
    new_imports = _generate_dynamic_imports(missing_quote_df + missing_policy_df)
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

    quote_insert = _join_inserts(quote_df_code, quote_cond_code)
    policy_insert = _join_inserts(policy_df_code, policy_cond_code)

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
        verdict = (v.get("verdicts") or {}).get(root_id) or {}
        if verdict.get("confidence") not in ("high", "medium"):
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
    """Load conditional-registry.yaml. Returns [] if absent or empty."""
    if not yaml_path.exists():
        return []
    rows = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or []
    blocks = []
    for row in rows:
        conditions = [str(c).strip() for c in (row.get("conditions") or []) if str(c).strip()]
        operator = (row.get("operator") or "AND").strip().upper()
        blocks.append({
            "id": int(row["id"]),
            "source_text": row["source_text"],
            "parent_id": row.get("parent_id"),
            "depth": int(row.get("depth") or 0),
            "conditions": conditions,
            "operator": operator,
        })
    return blocks


def render_conditional_puts(blocks: list[dict], scope: str = "quote") -> str:
    """Generate renderingData.put(...) lines for conditional blocks.

    scope: "quote" emits full if-conditions; "policy" emits empty puts for any
    condition that references quote.* (which is out of scope in that overload).
    """
    if not blocks:
        return ""
    lines = []
    for b in blocks:
        bid = b["id"]
        src = b["source_text"].replace("\\", "\\\\").replace('"', '\\"')
        truncated = b["source_text"][:60] + ("..." if len(b["source_text"]) > 60 else "")
        raw_conds = b["conditions"]
        quote_scoped = any(c.strip().startswith("quote.") for c in raw_conds)
        if raw_conds and not (scope == "policy" and quote_scoped):
            joiner = " || " if b["operator"] == "OR" else " && "
            java_cond = joiner.join(_accessor_to_java(c) for c in raw_conds)
            lines.append(
                f'        // Conditional block {bid}: {truncated}\n'
                f'        String cond{bid} = "";\n'
                f'        if ({java_cond}) {{\n'
                f'            cond{bid} = "{src}";\n'
                f'        }}\n'
                f'        renderingData.put("cond{bid}", cond{bid});'
            )
        elif scope == "policy" and quote_scoped:
            lines.append(
                f'        // Conditional block {bid}: quote-scoped, n/a in policy context\n'
                f'        renderingData.put("cond{bid}", "");'
            )
        else:
            parent_note = f" — child of cond{b['parent_id']}, guard inside parent if-block" if b.get("parent_id") else ""
            lines.append(
                f'        // TODO: fill conditions for cond{bid} in conditional-registry.yaml{parent_note}\n'
                f'        // {truncated}\n'
                f'        renderingData.put("cond{bid}", "");'
            )
    return "\n".join(lines)


def render_java(
    product: str,
    suggested_name: str,
    quote_df_calls: list[dict] | None = None,
    policy_df_calls: list[dict] | None = None,
    cond_blocks: list[dict] | None = None,
) -> str:
    quote_extras = _generate_datafetcher_extras(quote_df_calls or [])
    policy_extras = _generate_datafetcher_extras(policy_df_calls or [])
    all_calls = (quote_df_calls or []) + (policy_df_calls or [])
    dyn_imports = _generate_dynamic_imports(all_calls)
    if dyn_imports:
        dyn_imports = dyn_imports + "\n"
    quote_cond_puts = render_conditional_puts(cond_blocks or [], scope="quote")
    policy_cond_puts = render_conditional_puts(cond_blocks or [], scope="policy")
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
        f"## High-confidence paths (validated against `{seg}` or `{quote}`) ({len(high_results)})",
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
        lines.append("_No high-confidence variables with a data_source._")
    lines += ["", "---", ""]

    lines += [
        f"## Ignored — medium / low confidence ({len(ignored_vars)})",
        "",
        "Not validated in this run (D5). Promote to `high` in the `.suggested.yaml` "
        "to include in future validation runs.",
        "",
        "| Variable | confidence | data_source |",
        "|---|---|---|",
    ]
    for v in ignored_vars:
        name = v.get("name") or ""
        conf = v.get("confidence") or ""
        ds = v.get("data_source") or ""
        lines.append(f"| {name} | {conf} | `{ds or '(empty)'}` |")
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
        lines.append("_No conditional-registry.yaml found alongside this .suggested.yaml._")
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
    ap.add_argument("--suggested", type=Path, required=True,
                    help=".suggested.yaml produced by Leg 2")
    ap.add_argument("--output-dir", type=Path, default=None,
                    help="Where to write the .java (default: dir of --suggested)")
    ap.add_argument("--customer-jar", type=Path,
                    default=repo_root / "build" / "customer-config.jar",
                    help="customer-config.jar with the plugin interface + request types")
    ap.add_argument("--datamodel-jar", type=Path, default=None,
                    help="core-datamodel-v*.jar (default: newest under build/)")
    ap.add_argument("--slf4j-jar", type=Path,
                    default=None,
                    help="slf4j-api jar for the compile check (default: auto-discover build/slf4j-api-*.jar)")
    ap.add_argument("--compile-check", action="store_true", default=False,
                    help="Run javac against the JARs after generating")
    args = ap.parse_args()

    suggested_path = args.suggested.resolve()
    if not suggested_path.exists():
        print(f"ERROR: suggested file not found: {suggested_path}", file=sys.stderr)
        return 1

    stem = suggested_path.name
    for suffix in (".suggested.yaml", ".yaml"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break

    out_dir = (args.output_dir.resolve() if args.output_dir else suggested_path.parent)

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

    suggested_raw = _load_yaml(suggested_path)
    product = (suggested_raw.get("product") or "").strip()
    if not product:
        print(f"ERROR: 'product' missing from {suggested_path.name}", file=sys.stderr)
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
    cond_yaml = out_dir / f"{stem}.conditional-registry.yaml"
    cond_blocks = load_conditional_registry(cond_yaml)

    # --- Render + write Java (additive if file exists, fresh otherwise) ------
    class_name = f"{product}DocumentDataSnapshotPluginImpl"
    java_path = out_dir / f"{class_name}.java"
    out_dir.mkdir(parents=True, exist_ok=True)

    additive_mode = java_path.exists()
    additive_summary: dict | None = None

    if additive_mode:
        existing_keys = _parse_existing_plugin_keys(java_path)
        cond_high_water = _parse_existing_cond_high_water(java_path)

        required = _required_keys(suggested_raw, cond_blocks)
        missing_vars, missing_conds = _diff_keys(required, existing_keys, cond_high_water)

        missing_quote_df = [c for c in quote_df_calls if c["key"] in missing_vars]
        missing_policy_df = [c for c in policy_df_calls if c["key"] in missing_vars]

        local_to_global = {local_id: global_id for local_id, global_id in missing_conds}
        offset_cond_blocks = [
            {**b, "id": local_to_global[b["id"]]}
            for b in cond_blocks
            if b["id"] in local_to_global
        ]

        _append_to_plugin(java_path, missing_quote_df, missing_policy_df, offset_cond_blocks)

        added_keys = {c["key"] for c in missing_quote_df + missing_policy_df}
        additive_summary = {
            "keys_already_present": len(existing_keys),
            "keys_added": added_keys,
            "cond_high_water_before": cond_high_water,
            "new_cond_ids": [global_id for _, global_id in missing_conds],
        }
        print(
            f"Additive mode: {len(added_keys)} key(s) added, "
            f"{len(missing_conds)} conditional(s) added (high-water was {cond_high_water})"
        )
    else:
        java_path.write_text(
            render_java(product, suggested_path.name,
                        quote_df_calls=quote_df_calls, policy_df_calls=policy_df_calls,
                        cond_blocks=cond_blocks),
            encoding="utf-8",
        )

    # --- Categorise + validate variables -------------------------------------
    variables = suggested.get("variables") or []
    high_vars = [
        v for v in variables
        if (v.get("confidence") or "").lower() == "high"
        and (v.get("data_source") or "").strip()
    ]
    ignored_vars = [v for v in variables if v not in high_vars]

    high_results: list[tuple[dict, str, str]] = []
    for v in high_vars:
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
    report_path = suggested_path.parent / f"{stem}.plugin-report.md"
    generated_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_report(
        report_path,
        stem=stem,
        product=product,
        suggested_path=suggested_path,
        java_path=java_path,
        high_results=high_results,
        ignored_vars=ignored_vars,
        compile_status=compile_status,
        compile_detail=compile_detail,
        generated_at=generated_at,
        cond_blocks=cond_blocks,
        additive_summary=additive_summary,
    )

    print(f"Wrote {_rel(java_path, repo_root)}")
    print(f"Wrote {_rel(report_path, repo_root)}")
    print(
        f"Product={product}  high={len(high_results)}  ignored={len(ignored_vars)}"
        + (f"  compile={compile_status}" if compile_status else "")
    )

    if args.compile_check and not compile_ok:
        print("ERROR: compile check failed:\n" + compile_detail, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
