#!/usr/bin/env python3
"""Shared Leg 2 state: registry↔config gate, file hashes, provenance blobs, delta audit."""

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


def entry_locked(entry: dict[str, Any]) -> bool:
    if entry.get("locked") is True:
        return True
    st = entry.get("status")
    return isinstance(st, str) and st.lower() == "confirmed"


def compute_delta_change_set(
    *,
    base: dict[str, Any] | None,
    merged: dict[str, Any],
    prior_input_registry_sha256: str | None = None,
    prior_registry_source_config_sha256: str | None = None,
    current_input_registry_sha256: str,
    current_registry_source_config_sha256: str | None,
) -> dict[str, Any]:
    """Build ``delta_changes`` plus ``registry_or_config_changed`` for summary / sidecar."""

    def var_key(e: dict[str, Any]) -> str:
        return str(e.get("name", ""))

    def loop_key(e: dict[str, Any]) -> str:
        return str(e.get("name", ""))

    added: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []
    cleared: list[dict[str, Any]] = []
    carried: list[dict[str, Any]] = []
    resuggested: list[dict[str, Any]] = []
    would_change_locked: list[dict[str, Any]] = []

    base_vars = {var_key(v): v for v in (base or {}).get("variables") or []}
    base_loops = {loop_key(L): L for L in (base or {}).get("loops") or []}

    for v in merged.get("variables") or []:
        name = var_key(v)
        b = base_vars.get(name)
        old_ds = (b or {}).get("data_source") if isinstance((b or {}).get("data_source"), str) else ""
        new_ds = v.get("data_source") if isinstance(v.get("data_source"), str) else ""
        old_c = (b or {}).get("confidence")
        new_c = v.get("confidence")
        ctx = v.get("context") if isinstance(v.get("context"), dict) else {}
        line = ctx.get("line")
        row_base = {
            "name": name,
            "placeholder": v.get("placeholder", ""),
            "context": {"line": line},
        }
        if b is None:
            if new_ds and not old_ds:
                added.append({**row_base, "old_data_source": "", "new_data_source": new_ds})
            continue
        locked = entry_locked(b)
        if locked and (old_ds or "") != (new_ds or ""):
            would_change_locked.append(
                {
                    **row_base,
                    "old_data_source": old_ds,
                    "would_be_data_source": new_ds,
                    "old_confidence": old_c,
                    "would_be_confidence": new_c,
                }
            )
            continue
        if locked and (old_ds or "") == (new_ds or ""):
            carried.append({**row_base, "data_source": old_ds})
            continue
        if old_ds == "" and new_ds != "":
            resuggested.append({**row_base, "old_data_source": "", "new_data_source": new_ds})
        elif old_ds != "" and new_ds == "":
            cleared.append({**row_base, "old_data_source": old_ds, "new_data_source": ""})
        elif old_ds != new_ds:
            changed.append(
                {
                    **row_base,
                    "old_data_source": old_ds,
                    "new_data_source": new_ds,
                    "old_confidence": old_c,
                    "new_confidence": new_c,
                }
            )

    for L in merged.get("loops") or []:
        name = loop_key(L)
        b = base_loops.get(name)
        old_ds = (b or {}).get("data_source") if isinstance((b or {}).get("data_source"), str) else ""
        new_ds = L.get("data_source") if isinstance(L.get("data_source"), str) else ""
        old_c = (b or {}).get("confidence")
        new_c = L.get("confidence")
        ctx = L.get("context") if isinstance(L.get("context"), dict) else {}
        line = ctx.get("line")
        row_base = {
            "name": name,
            "placeholder": L.get("placeholder", ""),
            "context": {"line": line},
        }
        if b is None:
            if new_ds and not old_ds:
                added.append({**row_base, "old_data_source": "", "new_data_source": new_ds})
            continue
        locked = entry_locked(b)
        if locked and (old_ds or "") != (new_ds or ""):
            would_change_locked.append(
                {
                    **row_base,
                    "old_data_source": old_ds,
                    "would_be_data_source": new_ds,
                    "old_confidence": old_c,
                    "would_be_confidence": new_c,
                }
            )
            continue
        if locked and (old_ds or "") == (new_ds or ""):
            carried.append({**row_base, "data_source": old_ds})
            continue
        if old_ds == "" and new_ds != "":
            resuggested.append({**row_base, "old_data_source": "", "new_data_source": new_ds})
        elif old_ds != "" and new_ds == "":
            cleared.append({**row_base, "old_data_source": old_ds, "new_data_source": ""})
        elif old_ds != new_ds:
            changed.append(
                {
                    **row_base,
                    "old_data_source": old_ds,
                    "new_data_source": new_ds,
                    "old_confidence": old_c,
                    "new_confidence": new_c,
                }
            )

    reg_changed = False
    if prior_input_registry_sha256 and prior_input_registry_sha256 != current_input_registry_sha256:
        reg_changed = True
    if (
        prior_registry_source_config_sha256
        and current_registry_source_config_sha256
        and prior_registry_source_config_sha256 != current_registry_source_config_sha256
    ):
        reg_changed = True
    if prior_registry_source_config_sha256 is None and current_registry_source_config_sha256:
        # first run with fingerprint vs older base without — treat as churn signal when base had any hash field empty and now set - skip edge; only explicit mismatch above
        pass

    return {
        "added": added,
        "changed": changed,
        "cleared": cleared,
        "carried_forward_confirmed": carried,
        "re_suggested_unconfirmed": resuggested,
        "would_change_locked": would_change_locked,
        "carried_forward_count": len(carried),
        "registry_or_config_changed": reg_changed,
    }
