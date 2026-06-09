#!/usr/bin/env python3
"""Render registry/path-registry.yaml into a human-readable Markdown field catalog.

Usage:
    python3 scripts/list_paths.py
    python3 scripts/list_paths.py --registry registry/path-registry.yaml
    python3 scripts/list_paths.py --registry registry/path-registry.yaml --out samples/output/field-catalog.md
"""

import argparse
from pathlib import Path

import yaml


def _derive_accessor(velocity: str, category: str) -> str:
    """Derive clean accessor from velocity path + category."""
    v = (velocity or "").strip()
    cat = (category or "").strip()
    if cat == "system":
        return "policy." + v[len("$data."):] if v.startswith("$data.") else v
    if cat == "quote_system":
        return "quote." + v[len("$data."):] if v.startswith("$data.") else v
    if cat == "policy_data":
        # $data.data.X → policy.data.X
        return "policy." + v[len("$data."):] if v.startswith("$data.") else v
    if v.startswith("$data."):
        return v[len("$data."):]
    if v.startswith("$"):
        return v[1:]
    return v


def _required_cell(entry: dict) -> str:
    q = entry.get("quantifier", "")
    if q in ("?",):
        return ""
    return "✓"


def _options_cell(entry: dict) -> str:
    opts = entry.get("options", [])
    if not opts:
        return ""
    truncated = [f"`{o}`" for o in opts[:5]]
    suffix = ", …" if len(opts) > 5 else ""
    return ", ".join(truncated) + suffix


def _field_rows(entries: list, include_values: bool = True) -> list[str]:
    has_values = include_values and any(e.get("options") for e in entries)
    lines = []
    if has_values:
        lines.append("| Field | Accessor | Velocity Path | Type | Required | Values |")
        lines.append("|-------|----------|---------------|------|----------|--------|")
        for e in entries:
            name = e.get("display_name") or e.get("field", "")
            acc = f'`{_derive_accessor(e.get("velocity", ""), e.get("category", ""))}`'
            path = f'`{e.get("velocity", "")}`'
            typ = e.get("type", "")
            req = _required_cell(e)
            vals = _options_cell(e)
            lines.append(f"| {name} | {acc} | {path} | {typ} | {req} | {vals} |")
    else:
        lines.append("| Field | Accessor | Velocity Path | Type | Required |")
        lines.append("|-------|----------|---------------|------|----------|")
        for e in entries:
            name = e.get("display_name") or e.get("field", "")
            acc = f'`{_derive_accessor(e.get("velocity", ""), e.get("category", ""))}`'
            path = f'`{e.get("velocity", "")}`'
            typ = e.get("type", "")
            req = _required_cell(e)
            lines.append(f"| {name} | {acc} | {path} | {typ} | {req} |")
    return lines


def _charge_rows(charges: list) -> list[str]:
    lines = [
        "| Charge | Amount path | Object path |",
        "|--------|-------------|-------------|",
    ]
    for c in charges:
        name = c.get("name", "")
        amt = f'`{c.get("velocity_amount", "")}`'
        obj = f'`{c.get("velocity_object", "")}`'
        lines.append(f"| {name} | {amt} | {obj} |")
    return lines


def render_catalog(registry_path: str) -> str:
    """Read the registry YAML and return the full Markdown catalog."""
    reg = Path(registry_path)
    data = yaml.safe_load(reg.read_text(encoding="utf-8"))

    product = (data.get("meta") or {}).get("display_name", "Product")
    generated_at = (data.get("meta") or {}).get("generated_at", "")
    date_str = generated_at[:10] if generated_at else ""
    date_suffix = f" · {date_str}" if date_str else ""

    out: list[str] = []

    out.append(f"# {product} — Available Paths")
    out.append("")
    out.append(f"> Generated from `{registry_path}`{date_suffix}")
    out.append("")

    # System Fields
    system = data.get("system_paths", [])
    if system:
        out.append("## System Fields")
        out.append("")
        out.extend(_field_rows(system, include_values=False))
        out.append("")

    # Quote System Fields
    quote = data.get("quote_paths", [])
    if quote:
        out.append("## Quote System Fields")
        out.append("")
        out.append("> Only available when the document operation is `quote`.")
        out.append("")
        out.extend(_field_rows(quote, include_values=False))
        out.append("")

    # Account Fields
    account = data.get("account_paths", [])
    if account:
        out.append("## Account Fields (Policyholder)")
        out.append("")
        out.extend(_field_rows(account, include_values=False))
        out.append("")

    # Policy Custom Fields
    policy_data = data.get("policy_data", [])
    if policy_data:
        out.append("## Policy Custom Fields")
        out.append("")
        out.extend(_field_rows(policy_data, include_values=True))
        out.append("")

    # Policy Charges
    policy_charges = data.get("policy_charges", [])
    if policy_charges:
        out.append("## Policy Charges")
        out.append("")
        out.extend(_charge_rows(policy_charges))
        out.append("")

    # Exposures
    for exp in data.get("exposures", []):
        exp_name = exp.get("display_name") or exp.get("name", "")
        foreach = exp.get("foreach", "")

        out.append(f"## {exp_name} Fields")
        out.append("")
        if foreach:
            out.append(f"> Loop: `{foreach}`")
            out.append("")

        sys_fields = exp.get("system_fields", [])
        if sys_fields:
            out.append("### System")
            out.append("")
            out.extend(_field_rows(sys_fields, include_values=False))
            out.append("")

        fields = exp.get("fields", [])
        if fields:
            out.append("### Custom Data")
            out.append("")
            out.extend(_field_rows(fields, include_values=True))
            out.append("")

        for cov in exp.get("coverages", []):
            cov_display = cov.get("display_name") or cov.get("name", "")
            cov_key = cov.get("name", "")
            cov_fields = cov.get("fields", [])
            cov_charges = cov.get("charges", [])

            if cov_fields:
                out.append(f"### Coverage: {cov_display}")
                out.append("")
                out.append(f"> Guard: `#if($item.{cov_key})`")
                out.append("")
                out.extend(_field_rows(cov_fields, include_values=True))
                out.append("")

            if cov_charges:
                out.append(f"### Coverage Charges: {cov_display}")
                out.append("")
                out.extend(_charge_rows(cov_charges))
                out.append("")

    # DataFetcher Paths
    df_paths = data.get("datafetcher_paths", [])
    if df_paths:
        out.append("## DataFetcher Paths")
        out.append("")
        out.append("| Field | Accessor | Velocity Path | Type | Valid roots | Fetcher method |")
        out.append("|-------|----------|---------------|------|-------------|----------------|")
        for e in df_paths:
            name = e.get("display_name") or e.get("field", "")
            acc = f'`{_derive_accessor(e.get("velocity", ""), e.get("category", ""))}`'
            path = f'`{e.get("velocity", "")}`'
            typ = e.get("type", "")
            roots = ", ".join(e.get("valid_roots") or [])
            method = f'`{e.get("datafetcher_method", "")}`'
            out.append(f"| {name} | {acc} | {path} | {typ} | {roots} | {method} |")
        out.append("")

    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        default="registry/path-registry.yaml",
        help="Path to path-registry.yaml",
    )
    parser.add_argument(
        "--out",
        default="samples/output/field-catalog.md",
        help="Output file (default: samples/output/field-catalog.md)",
    )
    args = parser.parse_args()

    catalog = render_catalog(args.registry)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(catalog, encoding="utf-8")
    print(f"Field catalog written to {args.out}")


if __name__ == "__main__":
    main()
