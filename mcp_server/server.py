"""ElixirX MCP server — development automation entry point.

Loads env from backend/.env, registers database/testing/project/migration
tool groups, exposes a CLAUDE.md status resource, and runs over stdio.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from tools import (
    register_database_tools,
    register_migration_tools,
    register_project_tools,
    register_testing_tools,
)


def _resolve_project_root() -> Path:
    env_root = os.environ.get("PROJECT_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _resolve_project_root()
os.environ["PROJECT_ROOT"] = str(PROJECT_ROOT)

ENV_FILE = PROJECT_ROOT / "backend" / ".env"
if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    load_dotenv()


server = FastMCP("elixirx-dev")

register_database_tools(server)
register_testing_tools(server)
register_project_tools(server)
register_migration_tools(server)


@server.resource("elixirx://status")
def status_resource() -> str:
    """Return CLAUDE.md so the host LLM can load project conventions."""
    claude_md = PROJECT_ROOT / "CLAUDE.md"
    if not claude_md.exists():
        return f"CLAUDE.md not found at {claude_md}"
    return claude_md.read_text(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    server.run(transport="stdio")
