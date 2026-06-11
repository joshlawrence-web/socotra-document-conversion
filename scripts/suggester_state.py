#!/usr/bin/env python3
"""Shared Leg 2 state: registry↔config gate, file hashes, provenance blobs."""

from __future__ import annotations

import hashlib
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_compute_source_config_sha256():
    here = Path(__file__).resolve().parent
    mod_path = here / "socotra_config_fingerprint.py"
    if not mod_path.is_file():
        raise RuntimeError("Missing {}".format(mod_path))
    spec = importlib.util.spec_from_file_location("socotra_config_fingerprint", mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load fingerprint module")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.compute_source_config_sha256


@dataclass
class RegistryConfigGateResult:
    """Outcome of comparing registry ``meta.source_config_sha256`` to disk."""

    registry_config_check: str
    registry_config_verified: bool
    live_source_config_sha256: str | None
    registry_source_config_sha256: str | None
    stderr_banner: str | None = None


def evaluate_registry_config_gate(
    *,
    config_dir: Path | None,
    registry_meta: dict[str, Any],
    require_registry_config_check: bool,
    allow_stale_registry: bool,
    allow_missing_registry_fingerprint: bool,
) -> RegistryConfigGateResult:
    """
    ``registry_config_check`` values:
      matched | skipped_no_config_dir | skipped_escape_hatch | skipped_missing_registry_fingerprint | failed_mismatch
    """
    embedded = registry_meta.get("source_config_sha256")
    if isinstance(embedded, str):
        embedded_fp: str | None = embedded.strip() or None
    else:
        embedded_fp = None

    if config_dir is None:
        if require_registry_config_check:
            raise SystemExit(
                "ERROR: --require-registry-config-check was set but --config-dir was omitted.\n"
                "Pass --config-dir <socotra-config/> so the registry fingerprint can be verified."
            )
        return RegistryConfigGateResult(
            registry_config_check="skipped_no_config_dir",
            registry_config_verified=False,
            live_source_config_sha256=None,
            registry_source_config_sha256=embedded_fp,
        )

    compute = load_compute_source_config_sha256()
    live = str(compute(config_dir.resolve()))

    if embedded_fp is None:
        if allow_missing_registry_fingerprint:
            banner = (
                "WARNING: ESCAPE HATCH — registry has no meta.source_config_sha256; "
                "live hash was NOT verified against the registry. "
                "Regenerate the registry with the current extract_paths.py.\n"
                "live_source_config_sha256 (for audit): {}\n".format(live)
            )
            return RegistryConfigGateResult(
                registry_config_check="skipped_missing_registry_fingerprint",
                registry_config_verified=False,
                live_source_config_sha256=live,
                registry_source_config_sha256=None,
                stderr_banner=banner,
            )
        raise SystemExit(
            "ERROR: registry meta.source_config_sha256 is missing but --config-dir was supplied.\n"
            "Regenerate path-registry.yaml with the current extract_paths.py, or pass "
            "--allow-missing-registry-fingerprint for a one-off audit escape (stamped on outputs).\n"
            "live_source_config_sha256 would be: {}".format(live)
        )

    if live != embedded_fp:
        if allow_stale_registry:
            banner = (
                "WARNING: ESCAPE HATCH — --allow-stale-registry: config tree fingerprint does NOT match "
                "registry meta.source_config_sha256.\n"
                "  embedded (registry): {}\n"
                "  live (--config-dir): {}\n"
                "Re-run: python3 .cursor/skills/mapping-suggester/scripts/extract_paths.py "
                "--config-dir <socotra-config> --output <registry-path>\n".format(embedded_fp, live)
            )
            return RegistryConfigGateResult(
                registry_config_check="skipped_escape_hatch",
                registry_config_verified=False,
                live_source_config_sha256=live,
                registry_source_config_sha256=embedded_fp,
                stderr_banner=banner,
            )
        raise SystemExit(
            "ERROR: registry / config fingerprint mismatch — refusing to write Leg 2 outputs.\n"
            "  embedded (registry meta.source_config_sha256): {}\n"
            "  live (recomputed from --config-dir):            {}\n"
            "Regenerate the registry from the same tree, or pass --allow-stale-registry only if you "
            "intentionally accept stale paths (run will be stamped as escaped).\n".format(
                embedded_fp, live
            )
        )

    return RegistryConfigGateResult(
        registry_config_check="matched",
        registry_config_verified=True,
        live_source_config_sha256=live,
        registry_source_config_sha256=embedded_fp,
    )
