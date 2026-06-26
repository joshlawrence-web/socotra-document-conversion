#!/usr/bin/env python3
"""
Full-pipeline test runner — Leg 0 → variants.csv fill → parse → Leg 2+3 → Leg 4.

Usage:
    # Interactive: pauses after each Leg 0 run so you can fill the variants.csv manually
    python3 tests/pipeline/run_test_pipeline.py

    # Automated: builds the filled variants.csv from condition_seeds.yaml (CI-friendly)
    python3 tests/pipeline/run_test_pipeline.py --auto

    # Run only one fixture (by stem, no extension)
    python3 tests/pipeline/run_test_pipeline.py --only "TestItemCert(segment)"

    # Regenerate DOCX fixtures first, then run
    python3 tests/pipeline/run_test_pipeline.py --regen --auto

    # Also render each .final.vm against a live tenant (ad-hoc rendering)
    python3 tests/pipeline/run_test_pipeline.py --auto --render-preview

Output lands in:  tests/pipeline/output/<stem>/
Plugin output in: tests/pipeline/output/<first_stem>/ZenCoverDocumentDataSnapshotPluginImpl.java
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
from velocity_converter.workspace import action_needed_dir  # noqa: E402
FIXTURES_DIR = REPO / "tests" / "pipeline" / "fixtures"
OUTPUT_DIR = REPO / "tests" / "pipeline" / "output"
SEEDS_FILE = REPO / "tests" / "pipeline" / "condition_seeds.yaml"
REGISTRY = REPO / "registry" / "path-registry.yaml"

ALL_FIXTURES = [
    "TestQuoteSummary(quote).docx",
    "TestItemCert(segment).docx",
    "TestRenewalNotice(segment).docx",
    "TestItemsSchedule(segment).docx",
    "TestGiftSchedule(segment).docx",
    "TestStateDisclosure(segment).docx",
    "TestVariantThenBinary(segment).docx",
    "TestVariantBareLeaf(segment).docx",
    "TestNestedVariantLabel(segment).docx",
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


def _read_csv_rows_simple(path: Path) -> list[list[str]]:
    """Read a variants.csv into raw row lists, dropping ``#`` comment lines."""
    import csv  # noqa: PLC0415
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines()
             if not ln.lstrip().startswith("#")]
    return list(csv.reader(lines))


def _build_filled_csv(csv_path: Path, sidecar_path: Path, seeds: dict) -> None:
    """Build a filled ``<stem>.variants.csv`` from Leg 0's stub + sidecar + seeds.

    The variants-only analogue of the old ``_autofill_form``: every block kind
    flows through one CSV. Per block (keyed by the sidecar's join ``key``):
      - **variant**: emit the seed's ``[{when, text}, …]`` rows verbatim.
      - **template** (``render: template``): one ``when``-only row (text blank).
      - **binary**: a conditioned row (seed ``when`` + the stub's prefilled text)
        plus an empty-default row.
    """
    import csv  # noqa: PLC0415
    import io  # noqa: PLC0415
    sidecar = yaml.safe_load(sidecar_path.read_text(encoding="utf-8")) or []
    # Recover each binary block's prefilled text from the stub's row that
    # carries it (the stub leaves every `when` blank, so key off non-blank text).
    stub_text: dict[str, str] = {}
    for row in _read_csv_rows_simple(csv_path)[1:]:
        if len(row) >= 3 and row[2].strip():
            stub_text.setdefault(row[0], row[2])

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["placeholder", "when", "text"])
    for b in sidecar:
        key = b.get("key")
        seed = seeds.get(key)
        if b.get("variant"):
            if not isinstance(seed, list):
                raise SystemExit(f"seed for variant block {key!r} must be a list of rows")
            for r in seed:
                w.writerow([key, r.get("when", ""), r.get("text", "")])
        elif b.get("render") == "template":
            if not seed:
                raise SystemExit(f"missing `when` seed for template block {key!r}")
            w.writerow([key, seed, ""])
        else:  # binary → one-real-row + empty-default fold
            if not seed:
                raise SystemExit(f"missing `when` seed for binary block {key!r}")
            w.writerow([key, seed, stub_text.get(key, "")])
            w.writerow([key, "", ""])
    # Nested-only labels: seed placeholders referenced via [[$x]] from another row's
    # text, with no document marker (so absent from the sidecar). Emit their rows so
    # the parse step can synthesize their blocks.
    sidecar_keys = {b.get("key") for b in sidecar}
    extra = 0
    for key, seed in seeds.items():
        if key in sidecar_keys:
            continue
        if not isinstance(seed, list):
            raise SystemExit(f"nested-only seed {key!r} must be a list of rows")
        for r in seed:
            w.writerow([key, r.get("when", ""), r.get("text", "")])
        extra += 1
    csv_path.write_text(buf.getvalue(), encoding="utf-8")
    print(f"    built filled variants.csv ({len(sidecar)} block(s)"
          + (f" + {extra} nested-only" if extra else "") + ")")


def _wait_for_csv(csv_path: Path, stem: str) -> None:
    print(f"\n  {'='*60}")
    print(f"  PAUSE — fill the variants CSV for: {stem}")
    print(f"  CSV: {csv_path}")
    print(f"  {'='*60}")
    print(f"\n  Fill the `when` column (and variant `text` rows) using the condition DSL.")
    print(f"  Examples: quote.quoteNumber present  |  state == \"CA\"  |  premium > 500")
    print(f"  Run `python3 -m velocity_converter.list_paths` to see all available accessors.")
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
            sys.executable, "-m", "velocity_converter.leg0_ingest",
            "--input", str(input_path),
            "--output-dir", str(output_dir),
        ],
        "Leg 0",
    )
    if r0.returncode != 0:
        errors.append("Leg 0 failed")
        return {"stem": stem, "mapping_path": None, "success": False, "errors": errors}

    # --- Variants CSV (single human-fill file; lives in action-needed/) ---
    csv_path = action_needed_dir(output_dir) / f"{stem}.variants.csv"
    sidecar_path = output_dir / f"{stem}.conditional-blocks.yaml"
    has_blocks = csv_path.exists() and sidecar_path.exists()

    registry_path = output_dir / f"{stem}.conditional-registry.yaml"
    if has_blocks:
        print(f"\n[2/4] Variants CSV — {'auto-fill' if auto else 'manual fill'}")
        if auto:
            doc_seeds = seeds_data.get(stem, {})
            if not doc_seeds:
                print(f"    WARNING: no seeds for {stem!r}")
            _build_filled_csv(csv_path, sidecar_path, doc_seeds)
        else:
            _wait_for_csv(csv_path, stem)

        # --- Parse variants CSV (+ sidecar) → conditional-registry.yaml ---
        print(f"\n[3/4] Parse variants CSV → conditional-registry.yaml")
        r_parse = _run(
            [
                sys.executable, "-m", "velocity_converter.leg0_ingest",
                "--parse-variants-csv", str(csv_path),
                "--output-dir", str(output_dir),
            ],
            "parse-variants-csv",
        )
        if r_parse.returncode != 0:
            errors.append("parse-variants-csv failed")
            return {"stem": stem, "mapping_path": None, "success": False, "errors": errors}
        if not registry_path.exists():
            errors.append(f"conditional-registry.yaml not written at {registry_path}")
            return {"stem": stem, "mapping_path": None, "success": False, "errors": errors}
    else:
        print(f"\n[2/4] No conditional blocks for {stem} — skipping variants CSV + parse.")

    # --- Leg 2 + Leg 3 ---
    print(f"\n[4/4] Leg 2+3 — fill mapping + generate template")
    mapping_path = output_dir / f"{stem}.mapping.yaml"
    r23 = _run(
        [
            sys.executable, "-m", "velocity_converter.agent", "--yes",
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

    # A written .final.vm is not enough — unresolved $TBD_* tokens mean Leg 2
    # never mapped those fields, and the template will fail under Velocity's
    # strict rendering (errorCode 216041: "Variable $TBD_x has not been set").
    # The Leg 4 plugin already gets this check (literal $TBD_ guard); the
    # template deserves the same bar.
    tbd_lines = [
        f"line {n}: {line.strip()}"
        for n, line in enumerate(vm_path.read_text(encoding="utf-8").splitlines(), 1)
        if "$TBD_" in line
    ]
    if tbd_lines:
        errors.append(
            f"{len(tbd_lines)} unresolved $TBD_ token(s) in {vm_path.name} "
            f"(Leg 2 left fields unmapped):"
        )
        errors.extend(f"  {tl}" for tl in tbd_lines)
        return {"stem": stem, "mapping_path": str(mapping_path), "success": False, "errors": errors}

    print(f"\n  OK — template: {vm_path.relative_to(REPO)}")
    return {"stem": stem, "mapping_path": str(mapping_path), "success": True, "errors": []}


# ---------------------------------------------------------------------------
# Leg 4 — single plugin from all mappings
# ---------------------------------------------------------------------------

def _find_build_jars() -> tuple[str, str] | None:
    """Return (customer_jar, datamodel_jar) if both are present in build/, else None."""
    build = REPO / "build"
    customer = build / "customer-config.jar"
    datamodels = sorted(build.glob("core-datamodel-*.jar"))
    datamodels = [j for j in datamodels if "-sources" not in j.name and "-javadoc" not in j.name]
    if customer.is_file() and datamodels:
        return str(customer), str(datamodels[0])
    return None


def _compile_check_variant_fixtures(mapping_paths: list[str]) -> bool:
    """Regenerate each variant-block fixture's plugin standalone with
    --compile-check and assert it compiles against the real jars.

    Done per-fixture (not on the combined plugin) so it verifies the new N-way
    codegen without being gated on the legacy binary fixtures' conditions. A
    no-op when the build jars are missing (CI without jars).
    """
    jars = _find_build_jars()
    if jars is None:
        print("  (compile-check skipped — build/ jars not found)")
        return True
    customer_jar, datamodel_jar = jars

    variant_mappings = []
    for mp in mapping_paths:
        cond_reg = Path(mp).parent / f"{Path(mp).parent.name}.conditional-registry.yaml"
        if not cond_reg.exists():
            continue
        blocks = yaml.safe_load(cond_reg.read_text(encoding="utf-8")) or []
        if any(b.get("variant") or b.get("variants") for b in blocks):
            variant_mappings.append(mp)

    if not variant_mappings:
        return True

    ok = True
    for mp in variant_mappings:
        stem = Path(mp).parent.name
        tmp_out = OUTPUT_DIR / stem / "_compile_check"
        if tmp_out.exists():
            shutil.rmtree(tmp_out)
        tmp_out.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable, "-m", "velocity_converter.leg4_generate_plugin",
            "--suggested", mp,
            "--customer-jar", customer_jar,
            "--datamodel-jar", datamodel_jar,
            "--output-dir", str(tmp_out),
            "--compile-check",
        ]
        r = _run(cmd, f"compile-check {stem}")
        passed = r.returncode == 0 and "compile=PASS" in (r.stdout or "")
        if passed:
            print(f"  OK — variant plugin compiles: {stem}")
        else:
            print(f"  FAIL — variant plugin did not compile: {stem}")
            ok = False
        shutil.rmtree(tmp_out, ignore_errors=True)
    return ok


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

    cmd = [sys.executable, "-m", "velocity_converter.leg4_generate_plugin"]
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
    # a single-form plugin passing silently was the multi-form regression. Keys
    # are named (§1a): cond<id> for binary blocks, the $token for variant blocks.
    plugin_text = java_files[0].read_text(encoding="utf-8")
    expected_keys: set[str] = set()
    for mp in mapping_paths:
        cond_reg = Path(mp).parent / f"{Path(mp).parent.name}.conditional-registry.yaml"
        if cond_reg.exists():
            for blk in yaml.safe_load(cond_reg.read_text(encoding="utf-8")) or []:
                expected_keys.add(str(blk.get("key") or f"cond{blk.get('id')}"))
    missing_keys = {k for k in expected_keys if f'renderingData.put("{k}"' not in plugin_text}
    if missing_keys:
        print(f"  FAIL — combined plugin missing conditional key(s) {sorted(missing_keys)} "
              f"(expected {len(expected_keys)} across {len(mapping_paths)} form(s))")
        return False
    print(f"  OK — combined plugin carries {len(expected_keys)} conditional key(s) "
          f"from {len(mapping_paths)} form(s)")

    # Compile-check the N-way variant fixtures against the real jars (the DSL is
    # the reason this can be turned on — the if/else-if chain with field
    # concatenation must compile). Skipped when the build jars are absent.
    if not _compile_check_variant_fixtures(mapping_paths):
        return False

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
# Ad-hoc rendering preview — render each .final.vm against a live tenant
# ---------------------------------------------------------------------------

def run_render_preview(results: list[dict]) -> dict[str, str]:
    """POST each successful fixture's .final.vm to the ad-hoc render endpoint.

    Opt-in (--render-preview): settings come from AI_DOCUMENTS_* env vars or the
    gitignored .env.ai-documents at the repo root (copy .env.ai-documents.example).
    The reference type is parsed from the fixture stem — TestQuoteSummary(quote)
    renders against AI_DOCUMENTS_REFERENCE_QUOTE. The tenant must already carry
    the deployed DocumentDataSnapshotPlugin (it supplies $data at render time).

    Returns {stem: "PASS" | "SKIP" | "FAIL"}.
    """
    from velocity_converter.render_preview import (
        ENV_PREFIX, RenderPreviewError, load_env, render_template, require_settings,
    )

    _banner("Render preview — ad-hoc rendering against live tenant")
    print("  NOTE: deploy the generated SnapshotPlugin to the tenant first —")
    print("  the renderer calls it to build $data (conditionals included).")

    env = load_env(REPO)
    try:
        api_url, tenant_locator, token = require_settings(env)
    except RenderPreviewError as exc:
        print(f"  FAIL — {exc}")
        return {r["stem"]: "FAIL" for r in results if r["success"]}

    statuses: dict[str, str] = {}
    for r in results:
        if not r["success"]:
            continue
        stem = r["stem"]
        ref_match = re.search(r"\((\w+)\)$", stem)
        ref_type = ref_match.group(1) if ref_match else None
        ref_locator = env.get(f"{ENV_PREFIX}REFERENCE_{(ref_type or '').upper()}")
        if not ref_locator:
            print(f"  SKIP — {stem}: {ENV_PREFIX}REFERENCE_{(ref_type or '?').upper()} not set")
            statuses[stem] = "SKIP"
            continue

        vm_path = OUTPUT_DIR / stem / f"{stem}.final.vm"
        print(f"\n  Rendering {stem} against {ref_type} {ref_locator} ...")
        try:
            rendered, content_type = render_template(
                api_url=api_url,
                tenant_locator=tenant_locator,
                token=token,
                template_text=vm_path.read_text(encoding="utf-8"),
                reference_type=ref_type,
                reference_locator=ref_locator,
                product_name=env.get(f"{ENV_PREFIX}PRODUCT_NAME"),
            )
        except RenderPreviewError as exc:
            print(f"  FAIL — {stem}: {exc}")
            if exc.body:
                for line in exc.body[:500].splitlines():
                    print(f"         {line}")
            statuses[stem] = "FAIL"
            continue

        is_pdf = rendered.startswith(b"%PDF")
        preview_path = OUTPUT_DIR / stem / f"{stem}.preview.{'pdf' if is_pdf else 'html'}"
        preview_path.write_bytes(rendered)

        if not rendered.strip():
            print(f"  FAIL — {stem}: render returned empty output")
            statuses[stem] = "FAIL"
            continue
        # Text output must not leak unresolved pipeline tokens; PDF bytes
        # can't be grepped, so a 200 + non-empty body is the bar there.
        if not is_pdf:
            text = rendered.decode("utf-8", errors="replace")
            leaks = [tok for tok in ("$TBD_", "$doc.cond") if tok in text]
            if leaks:
                print(f"  FAIL — {stem}: rendered output contains {', '.join(leaks)}")
                statuses[stem] = "FAIL"
                continue
        print(f"  OK — preview ({content_type or 'unknown type'}): "
              f"{preview_path.relative_to(REPO)}")
        statuses[stem] = "PASS"
    return statuses


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
    parser.add_argument(
        "--render-preview",
        action="store_true",
        help="Render each .final.vm against a live tenant via the ad-hoc "
             "rendering endpoint (settings from AI_DOCUMENTS_* env vars or "
             ".env.ai-documents; deploy the SnapshotPlugin first)",
    )
    args = parser.parse_args()

    # --- Optional: regen fixtures ---
    if args.regen:
        _banner("Regenerating fixtures")
        r = _run(
            [sys.executable, "tools/generate_test_fixtures.py",
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
        print("\nRun first:  python3 tools/generate_test_fixtures.py")
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

    # --- Render preview (opt-in, live tenant) ---
    preview_statuses: dict[str, str] = {}
    if args.render_preview and successful_mappings:
        preview_statuses = run_render_preview(results)

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

    for stem, status in preview_statuses.items():
        print(f"  [{status}] render preview — {stem}")
        if status == "FAIL":
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
