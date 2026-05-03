#!/usr/bin/env python3
"""Register the Velocity Converter MCP server with Claude Code.

Run once after cloning:
    python3 install.py

Writes (or updates) the mcpServers.velocity-converter entry in
~/.claude/settings.json so Claude Code can find the server from any project.
"""

import json
import sys
from pathlib import Path

SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
SERVER_NAME = "velocity-converter"
SERVER_SCRIPT = Path(__file__).parent / "mcp_server.py"


def main() -> None:
    # Load existing settings or start fresh
    if SETTINGS_PATH.exists():
        with SETTINGS_PATH.open() as f:
            settings = json.load(f)
    else:
        settings = {}
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)

    servers = settings.setdefault("mcpServers", {})
    existing = servers.get(SERVER_NAME)

    servers[SERVER_NAME] = {
        "command": sys.executable,
        "args": [str(SERVER_SCRIPT)],
    }

    with SETTINGS_PATH.open("w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")

    if existing:
        print(f"Updated {SERVER_NAME} in {SETTINGS_PATH}")
    else:
        print(f"Registered {SERVER_NAME} in {SETTINGS_PATH}")

    print(f"  command : {sys.executable}")
    print(f"  script  : {SERVER_SCRIPT}")
    print()
    print("Restart Claude Code (or reload MCP servers) for the change to take effect.")


if __name__ == "__main__":
    main()
