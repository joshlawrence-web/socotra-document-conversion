#!/usr/bin/env python3
"""
Full-pipeline test runner — Leg 0 → conditional-form pause → Leg 2+3 → Leg 4.

Usage:
    # Interactive: pauses after each Leg 0 run so you can fill the form manually
    python3 tests/pipeline/run_test_pipeline.py

    # Automated: auto-fills conditions from condition_seeds.yaml (CI-friendly)
    python3 tests/pipeline/run_test_pipeline.py --auto

    # Run only one fixture (by stem, no extension)
    python3 tests/pipeline/run_test_pipeline.py --only "TestItemCert(segment)"

    # Regenerate DOCX fixtures first, then run
    python3 tests/pipeline/run_test_pipeline.py --regen --auto

Output lands in:  tests/pipeline/output/<stem>/
Plugin output in: tests/pipeline/output/<first_stem>/ZenCoverDocumentDataSnapshotPluginImpl.java
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = REPO / "tests" / "pipeline" / "fixtures"
OUTPUT_DIR = REPO / "tests" / "pipeline" / "output"
SEEDS_FILE = REPO / "tests" / "pipeline" / "condition_seeds.yaml"
REGISTRY = REPO / "registry" / "path-registry.yaml"

ALL_FIXTURES = [
    "TestQuoteSummary(quote).docx",
    "TestItemCert(segment).docx",
    "TestRenewalNotice(segment).docx",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], label: str) -> subprocess.CompletedProcess:
    print(f"\n  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    if result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            print(f"    {line}")
    if result.returncode != 0:
        print(f"\n  ERROR in {label}:")
        for line in (result.stderr or result.stdout or "").strip().splitlines():
            print(f"    {line}")
    return result


def _stem(filename: str) -> str:
    return Path(filename).stem


def _autofill_form(form_path: Path, seeds: dict[int, str]) -> None:
    """Replace 'Condition: ' placeholders with seeded expressions."""
    text = form_path.read_text(encoding="utf-8")
    block_re = re.compile(r"(##\s+Block\s+(\d+).*?Condition:) *(\n)", re.DOTALL)

    def replacer(m):
        block_id = int(m.group(2))
        condition = seeds.get(block_id, "quote.quoteNumber != null")
        return f"{m.group(1)} {condition}{m.group(3)}"

    new_text = block_re.sub(replacer, text)
    form_path.write_text(new_text, encoding="utf-8")
    print(f"    auto-filled {len(seeds)} condition(s) in {form_path.name}")


def _wait_for_form(form_path: Path, stem: str) -> None:
    print(f"\n  {'='*60}")
    print(f"  PAUSE — fill the conditional form for: {stem}")
    print(f"  Form: {form_path}")
    print(f"  {'='*60}")
    print(f"\n  Fill in each 'Condition:' line using accessor-path expressions.")
    print(f"  Examples: quote.quoteNumber != null  |  policy.data.discountAmount != null")
    print(f"  Run `python3 scripts/list_paths.py` to see all available accessors.")
    print(f"\n  Press ENTER when done (or Ctrl+C to abort)...")
    try:
        input()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)


def _banner(text: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Per-fixture pipeline
# ---------------------------------------------------------------------------

def run_fixture(fixture_file: str, auto: bool, seeds_data: dict) -> dict:
    """Run Leg 0 → fill form → parse form → Leg 2+3 for one fixture.

    Returns a result dict: {stem, mapping_path, success, errors}.
    """
    stem = _stem(fixture_file)
    _banner(f"Processing: {fixture_file}")

    input_path = FIXTURES_DIR / fixture_file
    output_dir = OUTPUT_DIR / stem
    output_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []

    # --- Leg 0 ---
    print(f"\n[1/4] Leg 0 — ingest document")
    r0 = _run(
        [
            sys.executable, "scripts/leg0_ingest.py",
            "--input", str(input_path),
            "--output-dir", str(output_dir),
        ],
        "Leg 0",
    )
    if r0.returncode != 0:
        errors.append("Leg 0 failed")
        return {"stem": stem, "mapping_path": None, "success": False, "errors": errors}

    # --- Fill conditional form ---
    form_path = output_dir / f"{stem}.conditional-form.md"
    if not form_path.exists():
        errors.append(f"conditional-form.md not found at {form_path}")
        return {"stem": stem, "mapping_path": None, "success": False, "errors": errors}

    print(f"\n[2/4] Conditional form — {'auto-fill' if auto else 'manual fill'}")
    if auto:
        doc_seeds = seeds_data.get(stem, {})
        if not doc_seeds:
            print(f"    WARNING: no seeds for {stem!r}, using fallback condition")
        _autofill_form(form_path, {int(k): v for k, v in doc_seeds.items()})
    else:
        _wait_for_form(form_path, stem)

    # --- Parse conditional form ---
    print(f"\n[3/4] Parse conditional form → conditional-registry.yaml")
    r_parse = _run(
        [
            sys.executable, "scripts/leg0_ingest.py",
            "--parse-conditional-form", str(form_path),
            "--output-dir", str(output_dir),
        ],
        "parse-conditional-form",
    )
    if r_parse.returncode != 0:
        errors.append("parse-conditional-form failed")
        return {"stem": stem, "mapping_path": None, "success": False, "errors": errors}

    registry_path = output_dir / f"{stem}.conditional-registry.yaml"
    if not registry_path.exists():
        errors.append(f"conditional-registry.yaml not written at {registry_path}")
        return {"stem": stem, "mapping_path": None, "success": False, "errors": errors}

    # --- Leg 2 + Leg 3 ---
    print(f"\n[4/4] Leg 2+3 — fill mapping + generate template")
    mapping_path = output_dir / f"{stem}.mapping.yaml"
    r23 = _run(
        [
            sys.executable, "scripts/agent.py", "--yes",
            f"RUN_PIPELINE leg2+leg3 mapping={mapping_path} "
            f"registry={REGISTRY}",
        ],
        "Leg 2+3",
    )
    if r23.returncode != 0:
        errors.append("Leg 2+3 failed")
        return {"stem": stem, "mapping_path": str(mapping_path), "success": False, "errors": errors}

    vm_path = output_dir / f"{stem}.final.vm"
    if not vm_path.exists():
        errors.append(f".final.vm not written at {vm_path}")
        return {"stem": stem, "mapping_path": str(mapping_path), "success": False, "errors": errors}

    print(f"\n  OK — template: {vm_path.relative_to(REPO)}")
    return {"stem": stem, "mapping_path": str(mapping_path), "success": True, "errors": []}


# ---------------------------------------------------------------------------
# Leg 4 — single plugin from all mappings
# ---------------------------------------------------------------------------

def run_leg4(mapping_paths: list[str]) -> bool:
    _banner("Leg 4 — generate DocumentDataSnapshotPlugin")

    if not mapping_paths:
        print("  No mapping paths — skipping Leg 4.")
        return False

    first_stem = Path(mapping_paths[0]).parent.name
    plugin_output_dir = OUTPUT_DIR / first_stem

    # Remove plugin output from previous suite runs — a stale .java flips Leg 4
    # into additive mode and the run stops testing fresh generation.
    for mp in mapping_paths:
        for stale in list(Path(mp).parent.glob("*.java")) + list(Path(mp).parent.glob("*.java.bak")):
            stale.unlink()
            print(f"  cleaned stale {stale.relative_to(REPO)}")

    cmd = [sys.executable, "scripts/leg4_generate_plugin.py"]
    for mp in mapping_paths:
        cmd += ["--suggested", mp]
    # No --customer-jar / --datamodel-jar — compile check skipped in test runner
    print(f"\n  Generating plugin from {len(mapping_paths)} mapping(s)...")
    r = _run(cmd, "Leg 4")
    if r.returncode != 0:
        return False

    java_files = list(plugin_output_dir.glob("*.java"))
    if not java_files:
        print(f"  FAIL — no combined plugin written to {plugin_output_dir.relative_to(REPO)}")
        return False
    stray = [
        jf for mp in mapping_paths[1:] for jf in Path(mp).parent.glob("*.java")
    ]
    if stray:
        for jf in stray:
            print(f"  FAIL — stray per-form plugin: {jf.relative_to(REPO)} "
                  "(all forms must merge into the first form's plugin)")
        return False
    for jf in java_files:
        print(f"\n  OK — plugin: {jf.relative_to(REPO)}")

    # Every form must contribute its conditional keys to the combined plugin —
    # a single-form plugin passing silently was the multi-form regression.
    plugin_text = java_files[0].read_text(encoding="utf-8")
    n_expected_conds = 0
    for mp in mapping_paths:
        cond_reg = Path(mp).parent / f"{Path(mp).parent.name}.conditional-registry.yaml"
        if cond_reg.exists():
            n_expected_conds += cond_reg.read_text(encoding="utf-8").count("- id:")
    n_plugin_conds = len(set(
        re.findall(r'renderingData\.put\("(cond\d+)"', plugin_text)
    ))
    if n_plugin_conds < n_expected_conds:
        print(f"  FAIL — combined plugin has {n_plugin_conds} distinct conditional key(s), "
              f"expected {n_expected_conds} across {len(mapping_paths)} form(s)")
        return False
    print(f"  OK — combined plugin carries {n_plugin_conds} conditional key(s) "
          f"from {len(mapping_paths)} form(s)")

    # Fields inside conditional blocks must be concatenated, never left as
    # literal $TBD_* in the plugin strings (plan 10-conditional-field-tokens).
    leaked = False
    for jf in java_files:
        for lineno, line in enumerate(jf.read_text(encoding="utf-8").splitlines(), 1):
            if "$TBD_" in line:
                print(f"  FAIL — literal $TBD_ token in {jf.relative_to(REPO)}:{lineno}")
                print(f"         {line.strip()}")
                leaked = True
    if leaked:
        return False

    return r.returncode == 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Full-pipeline test runner: Leg0 → form fill → Leg2+3 → Leg4."
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-fill conditions from condition_seeds.yaml (no pause)",
    )
    parser.add_argument(
        "--only",
        metavar="STEM",
        help="Run only the fixture matching this stem (no extension)",
    )
    parser.add_argument(
        "--regen",
        action="store_true",
        help="Regenerate DOCX fixtures before running (calls generate_test_fixtures.py)",
    )
    parser.add_argument(
        "--no-leg4",
        action="store_true",
        help="Skip Leg 4 plugin generation",
    )
    args = parser.parse_args()

    # --- Optional: regen fixtures ---
    if args.regen:
        _banner("Regenerating fixtures")
        r = _run(
            [sys.executable, "scripts/generate_test_fixtures.py",
             "--out-dir", str(FIXTURES_DIR)],
            "generate_test_fixtures",
        )
        if r.returncode != 0:
            print("ERROR: fixture generation failed. Aborting.")
            sys.exit(1)

    # --- Check fixtures exist ---
    fixtures_to_run = ALL_FIXTURES
    if args.only:
        fixtures_to_run = [
            f for f in ALL_FIXTURES if _stem(f) == args.only or args.only in f
        ]
        if not fixtures_to_run:
            print(f"ERROR: no fixture matching {args.only!r}")
            print(f"Available: {[_stem(f) for f in ALL_FIXTURES]}")
            sys.exit(1)

    missing = [f for f in fixtures_to_run if not (FIXTURES_DIR / f).exists()]
    if missing:
        print(f"ERROR: fixture file(s) missing:\n  " + "\n  ".join(
            str(FIXTURES_DIR / f) for f in missing
        ))
        print("\nRun first:  python3 scripts/generate_test_fixtures.py")
        sys.exit(1)

    # --- Load seeds ---
    seeds_data: dict = {}
    if SEEDS_FILE.exists():
        seeds_data = yaml.safe_load(SEEDS_FILE.read_text(encoding="utf-8")) or {}

    # --- Run each fixture ---
    results = []
    for fixture_file in fixtures_to_run:
        result = run_fixture(fixture_file, auto=args.auto, seeds_data=seeds_data)
        results.append(result)

    # --- Leg 4 (all successful mappings together) ---
    successful_mappings = [
        r["mapping_path"] for r in results
        if r["success"] and r["mapping_path"]
    ]

    if not args.no_leg4 and successful_mappings:
        leg4_ok = run_leg4(successful_mappings)
    else:
        leg4_ok = None

    # --- Summary ---
    _banner("Test Pipeline Summary")
    all_ok = True
    for r in results:
        icon = "PASS" if r["success"] else "FAIL"
        print(f"  [{icon}] {r['stem']}")
        for err in r["errors"]:
            print(f"         ! {err}")
        if not r["success"]:
            all_ok = False

    if leg4_ok is not None:
        icon = "PASS" if leg4_ok else "FAIL"
        print(f"  [{icon}] Leg 4 — plugin generation")
        if not leg4_ok:
            all_ok = False

    print()
    if all_ok:
        print("  All steps passed.")
        sys.exit(0)
    else:
        print("  One or more steps FAILED. See output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
