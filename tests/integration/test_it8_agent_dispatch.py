"""IT-8 — agent.py end-to-end dispatch (no JARs required)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent


def test_agent_list_paths_exits_zero():
    result = subprocess.run(
        [
            sys.executable,
            "-m", "velocity_converter.agent",
            "--yes",
            "RUN_PIPELINE list_paths registry=registry/path-registry.yaml",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert result.returncode == 0, (
        f"agent.py exited {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "Field catalog written to" in result.stdout


def test_catalog_content_has_system_fields():
    from velocity_converter.agent_tools import run_list_paths  # noqa: PLC0415
    catalog = run_list_paths(registry_path="registry/path-registry.yaml", out_path=None)
    assert "## System Fields" in catalog


def test_agent_rejects_unknown_op():
    result = subprocess.run(
        [sys.executable, "-m", "velocity_converter.agent", "--yes", "RUN_PIPELINE bogus_op"],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert result.returncode != 0


def test_agent_rejects_non_pipeline_text():
    result = subprocess.run(
        [sys.executable, "-m", "velocity_converter.agent", "--yes", "not a pipeline invocation"],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert result.returncode != 0
