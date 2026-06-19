"""Central resolver for the ``workspace/`` user-interaction layout.

Layout::

    workspace/
      inbox/           source docs (pipeline input)
      action-needed/   FLAT — files a human must hand-edit:
                         {stem}.variants.csv
                         {stem}.path-review.csv
      output/<stem>/   per-stem machine artifacts (.final.vm, .mapping.yaml, …)

The pipeline passes the per-stem **machine** dir (``…/output/<stem>``) around as
the authoritative location. The handful of human-fill files are *projected* into
the flat sibling ``action-needed/`` dir so an author can see at a glance what
still needs their attention. These helpers map between the two locations; every
caller that reads or writes a human-fill file routes through here so there is a
single source of truth.

Back-compat: when the given output dir is not inside an ``output/`` ancestor
(e.g. a tempdir in tests, or any non-workspace layout), the human-fill files stay
co-located with the machine artifacts — nothing moves.
"""
from __future__ import annotations

from pathlib import Path

WORKSPACE_ROOT = "workspace"
INBOX = "inbox"
OUTPUT = "output"
ACTION_NEEDED = "action-needed"

# Filename suffixes that live in action-needed/. Everything else a leg writes
# stays in the machine output/<stem>/ dir.
ACTION_NEEDED_SUFFIXES = (
    ".variants.csv",
    ".path-review.csv",
)


def _output_anchor(stem_output_dir: Path) -> Path | None:
    """Return the nearest ancestor named ``output`` (inclusive), or ``None``."""
    for cand in (stem_output_dir, *stem_output_dir.parents):
        if cand.name == OUTPUT:
            return cand
    return None


def action_needed_dir(stem_output_dir) -> Path:
    """Resolve the ``action-needed/`` dir from a per-stem machine output dir.

    ``workspace/output/<stem>`` → ``workspace/action-needed``. Falls back to
    ``stem_output_dir`` itself when there is no ``output`` ancestor so files stay
    co-located in non-workspace layouts (does **not** create the directory).
    """
    p = Path(stem_output_dir)
    anchor = _output_anchor(p)
    return p if anchor is None else anchor.parent / ACTION_NEEDED


def action_needed_file(stem_output_dir, filename: str) -> Path:
    """Path for a human-fill ``filename`` given the per-stem machine dir.

    Creates the destination directory as a side effect (writers call this).
    """
    d = action_needed_dir(stem_output_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d / filename


def machine_dir_for_action_file(action_file) -> Path | None:
    """Inverse map: ``workspace/action-needed/<stem>.<suffix>`` → ``…/output/<stem>``.

    Returns ``None`` when ``action_file`` is not inside an ``action-needed`` dir
    (so callers can fall back to the file's own parent).
    """
    p = Path(action_file)
    if p.parent.name != ACTION_NEEDED:
        return None
    stem = p.name
    for suf in ACTION_NEEDED_SUFFIXES:
        if stem.endswith(suf):
            stem = stem[: -len(suf)]
            break
    return p.parent.parent / OUTPUT / stem
