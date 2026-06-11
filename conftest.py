"""Auto-assign pytest markers by test directory.

Profiles: pytest -m unit | -m integration | -m jar
JAR-backed tests also keep their own skipUnless(build/*.jar) guards.
"""

from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent


def pytest_collection_modifyitems(config, items):
    for item in items:
        rel = Path(str(item.fspath)).resolve()
        try:
            parts = rel.relative_to(_REPO).parts
        except ValueError:
            continue
        if parts[:2] == ("tests", "regression"):
            item.add_marker(pytest.mark.unit)
        elif parts[:2] == ("tests", "integration"):
            item.add_marker(pytest.mark.integration)
