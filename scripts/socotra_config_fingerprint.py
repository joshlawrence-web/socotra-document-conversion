#!/usr/bin/env python3
"""
Deterministic fingerprint of a Socotra config tree for registry ↔ Leg 2 alignment.

Algorithm (must stay in lockstep with SCHEMA.md "Registry config fingerprint"):
  - Root: resolved ``config_dir``.
  - Collect every ``config.json`` file under these first-level subtrees only:
    ``products/``, ``exposures/``, ``coverages/``, ``charges/``, ``accounts/``,
    ``customDataTypes/``, ``perils/`` (same subtrees ``extract_paths.py`` reads).
  - Sort by relative POSIX path (case-sensitive).
  - For each file, UTF-8-decode contents (invalid UTF-8 replaced so the walk
    never aborts on one bad file).
  - Let ``piece_i = rel_posix + "\\n" + utf8_text + "\\n"``.
  - Fingerprint is SHA256 of ``b"".join(piece.encode("utf-8") for piece in pieces)``,
    lowercase hex digest.

Changing any included ``config.json`` byte-for-byte changes the digest.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_TRACKED_SUBDIRS = (
    "products",
    "exposures",
    "coverages",
    "charges",
    "accounts",
    "customDataTypes",
    "perils",
)


def iter_tracked_config_json_files(config_dir: Path) -> list[Path]:
    root = config_dir.resolve()
    out: list[Path] = []
    for sub in _TRACKED_SUBDIRS:
        base = root / sub
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("config.json")):
            if p.is_file():
                out.append(p)
    out.sort(key=lambda p: p.relative_to(root).as_posix())
    return out


def compute_source_config_sha256(config_dir: Path) -> str:
    root = config_dir.resolve()
    h = hashlib.sha256()
    for path in iter_tracked_config_json_files(root):
        rel = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
        piece = rel + "\n" + text + "\n"
        h.update(piece.encode("utf-8"))
    return h.hexdigest()
