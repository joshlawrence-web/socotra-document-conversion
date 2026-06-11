#!/usr/bin/env python3
"""Back-compat launcher for the Velocity Converter MCP server.

install.py registers this file's absolute path in ~/.claude/settings.json;
the implementation lives in velocity_converter.mcp_server.
"""

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from velocity_converter.mcp_server import main, mcp  # noqa: E402,F401

if __name__ == "__main__":
    main()
