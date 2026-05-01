#!/usr/bin/env python3
"""Telemetry helper for the mapping-suggester (Leg 2) Step 4c.

Derives one run's worth of `<stem>.suggester-log.jsonl` records from
an already-authored pair of `<stem>.suggested.yaml` + `path-registry.yaml`
and appends them to the log file. Emits one `kind: placeholder`
record per mapping entry (variables first, then loops, in file order),
terminated by one `kind: summary` record.

Intended use:

- After the suggester finishes writing `<stem>.suggested.yaml` and
  `<stem>.review.md`, the agent invokes this script with those paths
  plus the registry and the log's target location. The script derives
  the JSONL batch and appends it to the log.
- A fresh `--run-id` (UUID) is generated per invocation unless one is
  explicitly supplied. `--ts` defaults to the current UTC time.
- The log file is append-only across runs; this script never rewrites
  existing lines.

Contract:
- Output records validate against the JSON Schema at
  `conformance/schemas/suggester-log.schema.json`.
- `rejected_candidates` is left empty because the suggested YAML does
  not preserve per-candidate rejection reasons; when a live Leg 2 run
  knows those reasons in-memory, it MAY author the JSONL directly
  instead of invoking this helper.
- Originally landed in Phase D session D1 (2026-04-22) as the D1
  catch-up helper for claim-form; promoted to a permanent tool once
  it demonstrated schema-clean output on two verification runs.
"""

from __future__ import annotations

import argparse
import json
import re
import uuid
import datetime as dt
from pathlib import Path

import yaml

V1_RECOGNISED_CONTEXT_KEYS = {
    "parent_tag",
    "nearest_label",
    "nearest_heading",
    "line",
    "loop",
    "loop_hint",
    "column_header",
    "container",
    "detection",
}

NEXT_ACTION_CODES = {
    "pick-one",
    "supply-from-plugin",
    "restructure-template",
    "delete-from-template",
    "confirm-assumption",
    "needs-skill-update",
}

NEXT_ACTION_RE = re.compile(r"next-action:\s*([a-z-]+)")


def extract_next_action(reasoning: str, confidence: str) -> str | None:
    if not reasoning:
        return None if confidence == "high" else None
    match = NEXT_ACTION_RE.search(reasoning)
    if match and match.group(1) in NEXT_ACTION_CODES:
        return match.group(1)
    return None


def build_placeholder_record(entry: dict, *, ts: str, run_id: str) -> dict:
    ctx = entry.get("context") or {}
    unknown = sorted(k for k in ctx.keys() if k not in V1_RECOGNISED_CONTEXT_KEYS)
    data_source = entry.get("data_source")
    chosen = data_source if (isinstance(data_source, str) and data_source) else None
    confidence = entry.get("confidence", "low")
    next_action = extract_next_action(entry.get("reasoning", "") or "", confidence)
    return {
        "ts": ts,
        "run_id": run_id,
        "kind": "placeholder",
        "name": entry["name"],
        "placeholder": entry["placeholder"],
        "type": entry.get("type", "variable"),
        "context": dict(ctx),
        "chosen_match": chosen,
        "confidence": confidence,
        "next_action": next_action,
        # Rejection data is not preserved in the suggested YAML; a future
        # live run captures these directly in Step 4c. Leave empty on
        # catch-up derivations.
        "rejected_candidates": [],
        "unknown_context_keys": unknown,
    }


def collect_registry_paths(registry: dict) -> list[str]:
    """Return a flat list of every Velocity path declared by the registry."""
    paths: set[str] = set()

    def _walk(obj):
        if isinstance(obj, dict):
            if "velocity" in obj and isinstance(obj["velocity"], str):
                paths.add(obj["velocity"])
            if "velocity_object" in obj and isinstance(obj["velocity_object"], str):
                paths.add(obj["velocity_object"])
            if "velocity_amount" in obj and isinstance(obj["velocity_amount"], str):
                paths.add(obj["velocity_amount"])
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)

    _walk(registry)
    return sorted(paths)


def build_summary_record(
    *,
    ts: str,
    run_id: str,
    suggested: dict,
    registry_paths: list[str],
    placeholder_records: list[dict],
) -> dict:
    variables = suggested.get("variables") or []
    loops = suggested.get("loops") or []

    conf_counts = {"high": 0, "medium": 0, "low": 0}
    action_counts: dict[str, int] = {}
    chosen_paths: list[str] = []
    unknown_union: set[str] = set()

    for rec in placeholder_records:
        conf_counts[rec["confidence"]] = conf_counts.get(rec["confidence"], 0) + 1
        if rec["next_action"] is not None:
            action_counts[rec["next_action"]] = action_counts.get(rec["next_action"], 0) + 1
        if rec["chosen_match"] is not None:
            chosen_paths.append(rec["chosen_match"])
        for k in rec["unknown_context_keys"]:
            unknown_union.add(k)

    chosen_set = set(chosen_paths)
    registry_set = set(registry_paths)

    dead_paths = sorted(registry_set - chosen_set)
    if len(dead_paths) > 50:
        dead_paths = dead_paths[:50]

    from collections import Counter

    match_counts = Counter(chosen_paths)
    hot_paths = sorted(p for p, c in match_counts.items() if c >= 2)

    meta_product = "unknown"
    # Product name lives in the registry meta, not the suggested YAML.
    meta_product = suggested.get("product") or meta_product

    summary: dict = {
        "ts": ts,
        "run_id": run_id,
        "kind": "summary",
        "source": suggested.get("source", ""),
        "product": meta_product,
        "totals": {"variables": len(variables), "loops": len(loops)},
        "confidence_counts": conf_counts,
        "next_actions": action_counts,
        "dead_registry_paths": dead_paths,
        "hot_registry_paths": hot_paths,
        "unknown_context_keys_seen": sorted(unknown_union),
    }
    provenance_keys = (
        "mode",
        "input_mapping_sha256",
        "input_registry_sha256",
        "registry_schema_version",
        "registry_generated_at",
        "registry_config_dir",
        "registry_source_config_sha256",
        "live_source_config_sha256",
        "registry_config_verified",
        "registry_config_check",
        "base_suggested_sha256",
        "previous_run_id",
        "result_suggested_sha256",
    )
    for key in provenance_keys:
        if key in suggested:
            summary[key] = suggested[key]
    if "delta_changes" in suggested:
        summary["delta_changes"] = suggested["delta_changes"]
    return summary


def derive_run(
    suggested_path: Path,
    registry_path: Path,
    *,
    run_id: str,
    ts: str,
) -> list[dict]:
    suggested = yaml.safe_load(suggested_path.read_text())
    registry = yaml.safe_load(registry_path.read_text())

    placeholder_records: list[dict] = []
    for entry in suggested.get("variables") or []:
        placeholder_records.append(
            build_placeholder_record(entry, ts=ts, run_id=run_id)
        )
    for entry in suggested.get("loops") or []:
        placeholder_records.append(
            build_placeholder_record(entry, ts=ts, run_id=run_id)
        )

    summary = build_summary_record(
        ts=ts,
        run_id=run_id,
        suggested=suggested,
        registry_paths=collect_registry_paths(registry),
        placeholder_records=placeholder_records,
    )
    return placeholder_records + [summary]


def append_jsonl(log_path: Path, records: list[dict]) -> None:
    with log_path.open("a") as f:
        for rec in records:
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suggested", required=True, type=Path)
    ap.add_argument("--registry", required=True, type=Path)
    ap.add_argument("--log", required=True, type=Path)
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--ts", default=None, help="UTC timestamp; defaults to now")
    args = ap.parse_args()

    run_id = args.run_id or str(uuid.uuid4())
    ts = args.ts or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    records = derive_run(args.suggested, args.registry, run_id=run_id, ts=ts)
    append_jsonl(args.log, records)
    print(f"Appended {len(records)} records to {args.log} (run_id={run_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
