# -*- coding: utf-8 -*-
"""Entry point for running the BOSS MCP server."""
from cohub_recruiting.boss_mcp.server import mcp

if __name__ == "__main__":
    mcp.run()
