"""The _resolve_safe fence after the code-root / workspace-root split.

A data path is confined to EITHER the code root (shipped assets, resolved from
relative paths) OR the workspace root ($CONVERTER_WORKSPACE). A path escaping
both — a real traversal — is still rejected. This is the safety guarantee the
split must not weaken.
"""
import tempfile
from pathlib import Path

import pytest

from velocity_converter import agent_tools as A


def test_code_root_relative_path_accepted():
    """A shipped asset given as a repo-relative path resolves under the code root."""
    resolved = A._resolve_safe("registry/path-registry.yaml")
    assert str(resolved).startswith(str(A._find_repo_root()))


def test_workspace_path_accepted(monkeypatch):
    """An absolute path under $CONVERTER_WORKSPACE is accepted."""
    ws = str(Path(tempfile.mkdtemp()).resolve())
    monkeypatch.setenv("CONVERTER_WORKSPACE", ws)
    resolved = A._resolve_safe(ws + "/output/Doc/Doc.final.vm")
    assert str(resolved).startswith(ws)


def test_traversal_out_of_both_roots_rejected(monkeypatch):
    """A path escaping both roots raises — the fence is preserved."""
    ws = str(Path(tempfile.mkdtemp()).resolve())
    monkeypatch.setenv("CONVERTER_WORKSPACE", ws)
    with pytest.raises(ValueError, match="escapes allowed roots"):
        A._resolve_safe(ws + "/../../../../etc/passwd")


def test_workspace_defaults_to_code_root(monkeypatch):
    """Unset env ⇒ workspace root is the code root (back-compat with pre-split)."""
    monkeypatch.delenv("CONVERTER_WORKSPACE", raising=False)
    assert A._workspace_root() == A._find_repo_root()
