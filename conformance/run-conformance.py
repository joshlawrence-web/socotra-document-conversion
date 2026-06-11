#!/usr/bin/env python3
"""
run-conformance.py  —  Conformance fixture runner for the
HTML → Velocity pipeline.

Phase C of PIPELINE_EVOLUTION_PLAN.md. Each fixture under
conformance/fixtures/<name>/ pairs a minimal socotra-config/ tree with a
hand-authored mapping.yaml and frozen goldens under golden/.

Pipeline split (important):

- Leg 2a — `extract_paths.py`        deterministic Python → fully automated here
- Leg 2  — mapping-suggester skill   agent-executed → human-in-the-loop

What the runner automates
-------------------------

Per fixture, the runner:

1. Deletes any stale <fixture>/actual/path-registry.yaml.
2. Runs extract_paths.py on <fixture>/socotra-config/ and writes the
   result to <fixture>/actual/path-registry.yaml.
3. Canonicalises both the actual and the golden registries (strips
   volatile fields — see IGNORED_REGISTRY_PATHS below) and diffs.
4. JAR-backed fixtures only (those with a leg2.json marker): runs
   leg2_fill_mapping.py deterministically against the frozen
   golden registry + the build/*.jar set, writing actual/suggested.yaml
   + actual/review.md. This is the schema-2.0, SDK-grounded confidence
   path (Leg2-root-aware-confidence plan, D1) — it needs the compiled
   product JARs, which only exist for the real ItemCare product, so it
   is opt-in rather than run on every (synthetic) fixture.
5. If actual/suggested.yaml and/or actual/review.md exist (from step 4
   or left by an agent), diffs them against their goldens (suggested is
   canonicalised against a volatile-key list; review is text-diffed with
   the volatile bullets — run id, paths, sha, timestamps, registry
   lineage — normalised).
6. Reports pass/fail and exits non-zero on any diff.

What the runner does NOT automate
---------------------------------

The runner never invokes the mapping-suggester skill's *narrative* (full
step. For non-JAR fixtures it does not run Leg 2 at all. To refresh
suggested/review goldens for a fixture without a leg2.json marker:

1. Have an agent run the suggester on a fixture's mapping.yaml with
   the fixture's golden path-registry.yaml.
2. Save the agent's outputs to <fixture>/actual/suggested.yaml and
   <fixture>/actual/review.md.
3. Run this script; confirm the diffs are intentional.
4. Run with --update-goldens to copy actual/ → golden/.

The --update-goldens flag refuses to overwrite a golden whose actual
counterpart is missing (guards against zeroing out frozen artifacts).

Exit codes
----------

- 0 — every fixture passed (registry and, where applicable,
  suggested + review).
- 1 — one or more fixtures produced a diff.
- 2 — runner invocation / configuration error (missing files,
  extract_paths.py not found, etc.).
"""

from __future__ import annotations

import argparse
import copy
import difflib
import importlib.util
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml is required.  Run: pip install pyyaml --break-system-packages")
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "conformance" / "fixtures"
EXTRACT_MODULE = "velocity_converter.extract_paths"
LEG2_MODULE = "velocity_converter.leg2_fill_mapping"
LEGACY_ROOT_REGISTRY = REPO_ROOT / "path-registry.yaml"

# A fixture opts in to a JAR-backed Leg 2 run (schema 2.0, SDK-grounded
# confidence) by dropping a leg2.json marker beside its mapping. The runner
# then runs leg2_fill_mapping.py deterministically against the
# build/*.jar set and diffs the actual suggested/review against the 2.0
# goldens. Fixtures without the marker keep registry-only behaviour: their
# suggested/review goldens are only compared if an agent leaves an actual/.
LEG2_MARKER = "leg2.json"


# ---------------------------------------------------------------------------
# Volatile-key filters
# ---------------------------------------------------------------------------

# Registry keys that drift between runs and must be excluded from the diff.
# Dotted paths are rooted at the loaded YAML document.
IGNORED_REGISTRY_PATHS: tuple[str, ...] = (
    "meta.generated_at",
    "meta.config_dir",
)

# Suggested-YAML keys that drift between runs.
IGNORED_SUGGESTED_PATHS: tuple[str, ...] = (
    "generated_at",
    "run_id",
    "input_mapping_sha256",
    "input_registry_sha256",
    "registry_generated_at",
    "live_source_config_sha256",
    "base_suggested_sha256",
    "previous_run_id",
    "delta_changes",
    "registry_config_check",
    # Relative path from the suggested.yaml's dir to the registry input; differs
    # between an in-place golden (path-registry.yaml) and the runner writing to
    # actual/ (../golden/path-registry.yaml). Layout-dependent, not output.
    "path_registry",
)

# Review-file prefixes whose body after the colon gets normalised to a
# fixed sentinel. Compared as text, not YAML. These carry run-to-run volatile
# content (uuids, timestamps, sha digests, machine-absolute paths, and the
# golden-vs-actual output path) that must not count as a diff — the meaningful
# review content (summary tables, blockers, per-root verdicts) is left intact.
NORMALISED_REVIEW_PREFIXES: tuple[str, ...] = (
    "- Generated at:",
    "- Run id:",
    "- Source mapping:",
    "- Suggested output:",
    "- Path registry:",
    "- Inputs:",
    "- Registry lineage:",
)


# ---------------------------------------------------------------------------
# YAML canonicalisation helpers
# ---------------------------------------------------------------------------

def _delete_path(doc, dotted: str) -> None:
    """Delete ``dotted`` (e.g. ``meta.generated_at``) from ``doc`` if present."""
    if doc is None:
        return
    parts = dotted.split(".")
    cur = doc
    for part in parts[:-1]:
        if not isinstance(cur, dict) or part not in cur:
            return
        cur = cur[part]
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)


def _canonicalise(doc, ignored: tuple[str, ...]) -> str:
    """Clone ``doc``, strip ``ignored`` dotted keys, re-dump as stable YAML."""
    clone = copy.deepcopy(doc)
    for path in ignored:
        _delete_path(clone, path)
    return yaml.dump(clone, default_flow_style=False, allow_unicode=True, sort_keys=True)


def _normalise_review(text: str) -> str:
    out_lines = []
    for line in text.splitlines():
        for prefix in NORMALISED_REVIEW_PREFIXES:
            if line.startswith(prefix):
                line = prefix + " <normalised>"
                break
        out_lines.append(line)
    return "\n".join(out_lines) + ("\n" if text.endswith("\n") else "")


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------

def _unified_diff(a: str, b: str, a_label: str, b_label: str) -> str:
    diff = difflib.unified_diff(
        a.splitlines(keepends=True),
        b.splitlines(keepends=True),
        fromfile=a_label,
        tofile=b_label,
        n=3,
    )
    return "".join(diff)


# ---------------------------------------------------------------------------
# Fixture orchestration
# ---------------------------------------------------------------------------

@dataclass
class FixtureResult:
    name: str
    registry: str                       # "pass" | "fail" | "missing-actual"
    suggested: str                      # "pass" | "fail" | "skipped"
    review: str                         # "pass" | "fail" | "skipped"
    diffs: dict[str, str]               # artifact -> diff text (only when fail)

    @property
    def ok(self) -> bool:
        return (
            self.registry == "pass"
            and self.suggested in ("pass", "skipped")
            and self.review in ("pass", "skipped")
        )


def _discover_fixtures() -> list[Path]:
    if not FIXTURES_DIR.exists():
        return []
    return sorted(
        p for p in FIXTURES_DIR.iterdir()
        if p.is_dir() and (p / "socotra-config").exists()
    )


def _run_extract_paths(fixture: Path) -> Path:
    actual_dir = fixture / "actual"
    actual_dir.mkdir(exist_ok=True)
    actual_registry = actual_dir / "path-registry.yaml"
    if actual_registry.exists():
        actual_registry.unlink()

    cmd = [
        sys.executable,
        "-m", EXTRACT_MODULE,
        "--config-dir", str(fixture / "socotra-config"),
        "--output",     str(actual_registry),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    if proc.returncode != 0:
        raise RuntimeError(
            "extract_paths.py failed for fixture {} (exit {}):\n"
            "stdout:\n{}\nstderr:\n{}".format(
                fixture.name, proc.returncode, proc.stdout, proc.stderr,
            )
        )
    return actual_registry


def _jar_has_product(fixture: Path) -> bool:
    """True if build/customer-config.jar contains the fixture's product classes.

    The JAR-backed fixture goldens were frozen against a specific product
    (e.g. ItemCare). When build/ holds a different product's JARs, the leg2
    run cannot reproduce them — skip instead of failing.
    """
    jar = REPO_ROOT / "build" / "customer-config.jar"
    if not jar.is_file():
        return False
    golden_registry = fixture / "golden" / "path-registry.yaml"
    try:
        meta = (yaml.safe_load(golden_registry.read_text(encoding="utf-8")) or {}).get("meta") or {}
        product = str(meta.get("product") or "")
    except Exception:
        return False
    if not product:
        return False
    prefix = "com/socotra/deployment/customer/{}".format(product)
    with zipfile.ZipFile(jar) as zf:
        return any(n.startswith(prefix) for n in zf.namelist())


def _run_leg2(fixture: Path) -> None:
    """Run leg2_fill_mapping.py for a JAR-backed fixture (opt-in via leg2.json).

    Deterministic run against the frozen golden registry + the build/*.jar
    set; writes <fixture>/actual/suggested.yaml + actual/review.md so the existing
    diff logic compares them against the 2.0 goldens. All paths are repo-root
    relative so the review's path bullets are stable (and normalised regardless).
    Raises RuntimeError on a non-zero exit (e.g. missing JARs — Leg2 plan D1).
    """
    actual_dir = fixture / "actual"
    actual_dir.mkdir(exist_ok=True)
    rel = lambda p: str(p.relative_to(REPO_ROOT))
    cmd = [
        sys.executable,
        "-m", LEG2_MODULE,
        "--mapping",    rel(fixture / "mapping.yaml"),
        "--registry",   rel(fixture / "golden" / "path-registry.yaml"),
        "--out",        rel(actual_dir / "suggested.yaml"),
        "--review-out", rel(actual_dir / "review.md"),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    if proc.returncode != 0:
        raise RuntimeError(
            "leg2_fill_mapping.py failed for fixture {} (exit {}):\n"
            "stdout:\n{}\nstderr:\n{}".format(
                fixture.name, proc.returncode, proc.stdout, proc.stderr,
            )
        )


def _diff_yaml(actual_path: Path, golden_path: Path,
               ignored: tuple[str, ...]) -> str | None:
    if not golden_path.exists():
        return "golden missing: {}".format(golden_path)
    with open(actual_path, "r", encoding="utf-8") as f:
        actual = yaml.safe_load(f)
    with open(golden_path, "r", encoding="utf-8") as f:
        golden = yaml.safe_load(f)
    a = _canonicalise(actual, ignored)
    g = _canonicalise(golden, ignored)
    if a == g:
        return None
    return _unified_diff(
        g, a,
        "golden/{}".format(golden_path.name),
        "actual/{}".format(actual_path.name),
    )


def _diff_review(actual_path: Path, golden_path: Path) -> str | None:
    if not golden_path.exists():
        return "golden missing: {}".format(golden_path)
    a = _normalise_review(actual_path.read_text(encoding="utf-8"))
    g = _normalise_review(golden_path.read_text(encoding="utf-8"))
    if a == g:
        return None
    return _unified_diff(
        g, a,
        "golden/{}".format(golden_path.name),
        "actual/{}".format(actual_path.name),
    )


def _evaluate_fixture(fixture: Path) -> FixtureResult:
    diffs: dict[str, str] = {}

    actual_registry = _run_extract_paths(fixture)
    golden_registry = fixture / "golden" / "path-registry.yaml"
    registry_diff = _diff_yaml(actual_registry, golden_registry, IGNORED_REGISTRY_PATHS)
    registry_status = "pass" if registry_diff is None else "fail"
    if registry_diff:
        diffs["path-registry.yaml"] = registry_diff

    # JAR-backed fixtures (leg2.json marker): run Leg 2 now so the suggested/
    # review diffs below exercise SDK-grounded 2.0 output end-to-end. Skipped
    # when build/ holds a different product's JARs than the goldens were
    # frozen against (stale actual/ outputs are cleared so the diff below
    # reports skipped, not a misleading pass/fail).
    if (fixture / LEG2_MARKER).exists():
        if _jar_has_product(fixture):
            _run_leg2(fixture)
        else:
            print("  WARNING: leg2 skipped — build/customer-config.jar lacks "
                  "this fixture's product classes")
            for name in ("suggested.yaml", "review.md"):
                stale = fixture / "actual" / name
                if stale.exists():
                    stale.unlink()

    actual_suggested = fixture / "actual" / "suggested.yaml"
    golden_suggested = fixture / "golden" / "suggested.yaml"
    if actual_suggested.exists():
        suggested_diff = _diff_yaml(actual_suggested, golden_suggested, IGNORED_SUGGESTED_PATHS)
        suggested_status = "pass" if suggested_diff is None else "fail"
        if suggested_diff:
            diffs["suggested.yaml"] = suggested_diff
    else:
        suggested_status = "skipped"

    actual_review = fixture / "actual" / "review.md"
    golden_review = fixture / "golden" / "review.md"
    if actual_review.exists():
        review_diff = _diff_review(actual_review, golden_review)
        review_status = "pass" if review_diff is None else "fail"
        if review_diff:
            diffs["review.md"] = review_diff
    else:
        review_status = "skipped"

    return FixtureResult(
        name=fixture.name,
        registry=registry_status,
        suggested=suggested_status,
        review=review_status,
        diffs=diffs,
    )


# ---------------------------------------------------------------------------
# --update-goldens
# ---------------------------------------------------------------------------

def _update_goldens(fixtures: list[Path]) -> int:
    """
    Copy every existing <fixture>/actual/<name> over the matching
    <fixture>/golden/<name>. Refuse to overwrite a golden when the
    actual counterpart is missing.
    """
    updated: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []
    for fixture in fixtures:
        for basename in ("path-registry.yaml", "suggested.yaml", "review.md"):
            actual = fixture / "actual" / basename
            golden = fixture / "golden" / basename
            if not actual.exists():
                skipped.append((fixture.name, basename))
                continue
            golden.parent.mkdir(exist_ok=True)
            shutil.copyfile(actual, golden)
            updated.append((fixture.name, basename))

    print("Golden update:")
    for name, base in updated:
        print("  wrote  conformance/fixtures/{}/golden/{}".format(name, base))
    for name, base in skipped:
        print("  skip   conformance/fixtures/{}/golden/{}  (actual missing)".format(name, base))
    if not updated:
        print("  (no goldens written — did you forget to run the suggester first?)")
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument(
        "--update-goldens", action="store_true",
        help="Copy every existing <fixture>/actual/<name> over "
             "<fixture>/golden/<name>. Use after confirming diffs are "
             "intentional.",
    )
    parser.add_argument(
        "--only", default=None, metavar="NAME",
        help="Run a single fixture by directory name (e.g. --only minimal).",
    )
    args = parser.parse_args()

    if importlib.util.find_spec(EXTRACT_MODULE) is None:
        print("ERROR: module {} not importable (run from repo root or pip install -e .)".format(EXTRACT_MODULE))
        return 2

    fixtures = _discover_fixtures()
    if args.only:
        fixtures = [f for f in fixtures if f.name == args.only]
        if not fixtures:
            print("ERROR: no fixture named {!r} under {}".format(args.only, FIXTURES_DIR))
            return 2
    if not fixtures:
        print("ERROR: no fixtures found under {}".format(FIXTURES_DIR))
        return 2

    if LEGACY_ROOT_REGISTRY.exists():
        print(
            "ERROR: legacy root-level path-registry.yaml must not exist — "
            "use registry/path-registry.yaml (see README). Remove: {}".format(
                LEGACY_ROOT_REGISTRY
            )
        )
        return 2

    if args.update_goldens:
        return _update_goldens(fixtures)

    results: list[FixtureResult] = []
    for fixture in fixtures:
        print("Running fixture: {}".format(fixture.name))
        try:
            result = _evaluate_fixture(fixture)
        except RuntimeError as exc:
            print("  ERROR: {}".format(exc))
            return 2
        results.append(result)
        for artifact, status in (
            ("registry  ", result.registry),
            ("suggested ", result.suggested),
            ("review    ", result.review),
        ):
            print("  {} {}".format(artifact, status))

    print()
    print("=" * 60)
    print("Summary: {} fixtures".format(len(results)))
    for r in results:
        flag = "PASS" if r.ok else "FAIL"
        print("  {}  {:<22}  registry={}  suggested={}  review={}".format(
            flag, r.name, r.registry, r.suggested, r.review,
        ))
    print("=" * 60)

    failing = [r for r in results if not r.ok]
    if failing:
        print()
        print("Diffs:")
        for r in failing:
            for artifact, diff in r.diffs.items():
                print("\n--- {}/{} ---".format(r.name, artifact))
                print(diff)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
