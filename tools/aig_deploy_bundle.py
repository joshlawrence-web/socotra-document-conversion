#!/usr/bin/env python3
"""Build + deploy the AIG BlanketSpecialRisk config bundle to the aig-bsr-dev tenant.

Rebuilds the M1 scratchpad bundle durably: copies workspace-prod/reference/socotra-config,
applies the two known deploy-blocking fixes, bakes in the current generated
SnapshotPlugin, zips, validates via the Deployments API, then deploys.

Usage:
    python3 tools/aig_deploy_bundle.py [--plugin <path.java>] [--dry-run]

Credentials from .env.ai-documents (AI_DOCUMENTS_API_URL / AI_DOCUMENTS_PAT).
Tenant pinned like tools/aig_dev_tenant_seed.py (override: AIG_DEV_TENANT_LOCATOR).
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REFERENCE = REPO / "workspace-prod/reference/socotra-config"
DEFAULT_PLUGIN = (
    REPO / "workspace-prod/output/C11697DBG(segment)/BlanketSpecialRiskDocumentDataSnapshotPluginImpl.java"
)
TENANT = os.environ.get("AIG_DEV_TENANT_LOCATOR", "4a6c9ff6-3258-4fa0-a2d4-3959ac779580")


def load_env():
    env = {}
    with open(REPO / ".env.ai-documents") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for k in ("AI_DOCUMENTS_API_URL", "AI_DOCUMENTS_PAT"):
        env[k] = os.environ.get(k, env.get(k))
    return env


def build_bundle(plugin_path: Path, work: Path) -> Path:
    cfg = work / "socotra-config"
    shutil.copytree(REFERENCE, cfg)

    # Fix 1 (M1): coverageTerms/config.json uses "Deductible" where the server
    # requires lowerCamel "deductible".
    ct = cfg / "coverageTerms/config.json"
    ct.write_text(ct.read_text().replace('"Deductible"', '"deductible"'))

    # Fix 2 (M1): header-only table CSV is rejected — add one placeholder row.
    cat = cfg / "bootstrap/resources/resourceFiles/tables/CatCashAdjustmentLookup_2017_50.csv"
    if len(cat.read_text().strip().splitlines()) < 2:
        with cat.open("a") as f:
            f.write("Alabama,1.0\n")

    # Bake in the generated + hardened SnapshotPlugin.
    plugins = cfg / "plugins/java"
    plugins.mkdir(parents=True, exist_ok=True)
    shutil.copy(plugin_path, plugins / plugin_path.name)

    zip_path = work / "aig-bsr-config.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(cfg.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(cfg))
    return zip_path


def call_zip(env, path, zip_path: Path):
    req = urllib.request.Request(
        env["AI_DOCUMENTS_API_URL"].rstrip("/") + path,
        data=zip_path.read_bytes(),
        method="POST",
        headers={
            "Authorization": f"Bearer {env['AI_DOCUMENTS_PAT']}",
            "Content-Type": "application/zip",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return resp.status, resp.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plugin", type=Path, default=DEFAULT_PLUGIN)
    ap.add_argument("--dry-run", action="store_true", help="build + validate only, no deploy")
    args = ap.parse_args()

    env = load_env()
    with tempfile.TemporaryDirectory() as td:
        zip_path = build_bundle(args.plugin, Path(td))
        print(f"bundle: {zip_path} ({zip_path.stat().st_size} bytes)", file=sys.stderr)

        status, body = call_zip(env, f"/config/{TENANT}/deployments/validate", zip_path)
        print(f"validate: HTTP {status}", file=sys.stderr)
        if status != 200:
            print(body[:4000])
            sys.exit(1)
        if args.dry_run:
            print("dry-run: validate OK, not deploying")
            return

        status, body = call_zip(env, f"/config/{TENANT}/deployments/deploy", zip_path)
        print(f"deploy: HTTP {status}", file=sys.stderr)
        print(body[:4000])
        if status != 200:
            sys.exit(1)


if __name__ == "__main__":
    main()
