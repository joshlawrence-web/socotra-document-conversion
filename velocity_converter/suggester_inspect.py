#!/usr/bin/env python3
"""Inspect mapping-suggester JSONL logs and correlate runs (State-improvement plan Workstream C)."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def cmd_list_runs(log_path: Path) -> int:
    rows = load_jsonl(log_path)
    summaries = [r for r in rows if r.get("kind") == "summary"]
    if not summaries:
        print("(no summary records)")
        return 0
    print("run_id\tts\tmode\tregistry_check\tverified\thigh\tmed\tlow")
    for s in summaries:
        cc = s.get("registry_config_check", "")
        ver = s.get("registry_config_verified", "")
        counts = s.get("confidence_counts") or {}
        print(
            "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}".format(
                s.get("run_id", ""),
                s.get("ts", ""),
                s.get("mode", ""),
                cc,
                ver,
                counts.get("high", 0),
                counts.get("medium", 0),
                counts.get("low", 0),
            )
        )
    return 0


def cmd_show_run(log_path: Path, run_id: str) -> int:
    rows = [r for r in load_jsonl(log_path) if r.get("run_id") == run_id]
    if not rows:
        print("No records for run_id={}".format(run_id), file=sys.stderr)
        return 1
    summaries = [r for r in rows if r.get("kind") == "summary"]
    if summaries:
        s = summaries[-1]
        print("=== summary ===")
        print(json.dumps(s, indent=2, sort_keys=True))
    ph = [r for r in rows if r.get("kind") == "placeholder"]
    print("\n=== placeholders: {} rows ===".format(len(ph)))
    return 0


def cmd_diff_runs(log_path: Path, a: str, b: str) -> int:
    rows = load_jsonl(log_path)
    by_run: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        rid = r.get("run_id")
        if isinstance(rid, str):
            by_run[rid].append(r)

    def chosen_map(run_id: str) -> dict[str, str | None]:
        out: dict[str, str | None] = {}
        for r in by_run.get(run_id, []):
            if r.get("kind") != "placeholder":
                continue
            ph = r.get("placeholder")
            if isinstance(ph, str):
                out[ph] = r.get("chosen_match")
        return out

    ma, mb = chosen_map(a), chosen_map(b)
    keys = sorted(set(ma) | set(mb))
    print("placeholder\tmatch_a\tmatch_b")
    for k in keys:
        va, vb = ma.get(k), mb.get(k)
        if va != vb:
            print("{}\t{}\t{}".format(k, va, vb))
    return 0


def cmd_registry_lineage(log_path: Path, run_id: str) -> int:
    rows = [r for r in load_jsonl(log_path) if r.get("run_id") == run_id and r.get("kind") == "summary"]
    if not rows:
        print("No summary for run_id={}".format(run_id), file=sys.stderr)
        return 1
    s = rows[-1]
    print("input_registry_sha256:\t{}".format(s.get("input_registry_sha256", "")))
    print("registry_source_config_sha256 (embedded):\t{}".format(s.get("registry_source_config_sha256", "")))
    print("live_source_config_sha256:\t{}".format(s.get("live_source_config_sha256", "")))
    print("registry_config_check:\t{}".format(s.get("registry_config_check", "")))
    print("registry_config_verified:\t{}".format(s.get("registry_config_verified", "")))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list-runs", help="List summary rows in a log file")
    p_list.add_argument("log", type=Path, help="Path to <stem>.suggester-log.jsonl")

    p_show = sub.add_parser("show-run", help="Dump summary JSON for one run_id")
    p_show.add_argument("log", type=Path)
    p_show.add_argument("--run-id", required=True)

    p_diff = sub.add_parser("diff-runs", help="Diff chosen_match between two run_ids")
    p_diff.add_argument("log", type=Path)
    p_diff.add_argument("--a", required=True, dest="run_a")
    p_diff.add_argument("--b", required=True, dest="run_b")

    p_lin = sub.add_parser("registry-lineage", help="Print registry fingerprint fields from summary")
    p_lin.add_argument("log", type=Path)
    p_lin.add_argument("--run-id", required=True)

    args = ap.parse_args()
    if args.cmd == "list-runs":
        return cmd_list_runs(args.log)
    if args.cmd == "show-run":
        return cmd_show_run(args.log, args.run_id)
    if args.cmd == "diff-runs":
        return cmd_diff_runs(args.log, args.run_a, args.run_b)
    if args.cmd == "registry-lineage":
        return cmd_registry_lineage(args.log, args.run_id)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
