#!/usr/bin/env python3
"""Standalone validator for DocumentDataSnapshotPluginImpl.java files.

Usage:
  python3 -m velocity_converter.validate_plugin <path-to-plugin.java> [--json] [--keys]

Exit codes:
  0 — VALID (or --keys used)
  1 — INVALID or file not found
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from velocity_converter.leg4_generate_plugin import parse_plugin_keys


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("java_file", type=Path, help="Path to the plugin .java file")
    ap.add_argument("--json", dest="as_json", action="store_true",
                    help="Machine-readable JSON output")
    ap.add_argument("--keys", action="store_true",
                    help="List all existing keys (one per line)")
    args = ap.parse_args()

    java_path = args.java_file.resolve()
    if not java_path.exists():
        if args.as_json:
            print(json.dumps({"error": f"File not found: {java_path}", "is_valid": False}))
        else:
            print(f"ERROR: File not found: {java_path}", file=sys.stderr)
        return 1

    result = parse_plugin_keys(java_path)

    if args.keys:
        for key in sorted(result["existing_keys"]):
            print(key)
        return 0 if result["is_valid"] else 1

    if args.as_json:
        out = {
            "plugin": java_path.name,
            "keys": len(result["existing_keys"]),
            "cond_high_water": result["cond_high_water"],
            "is_valid": result["is_valid"],
            "errors": result["errors"],
        }
        print(json.dumps(out, indent=2))
        return 0 if result["is_valid"] else 1

    print(f"Plugin: {java_path.name}")
    if result["errors"]:
        for err in result["errors"]:
            print(f"ERROR: {err}")
        n = len(result["errors"])
        print(f"Status: INVALID ({n} error{'s' if n != 1 else ''})")
        return 1

    print(f"Keys: {len(result['existing_keys'])}")
    print(f"Highest condN: {result['cond_high_water']}")
    print("Status: VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
