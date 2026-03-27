# -*- coding: utf-8 -*-
"""Tests for MCP client environment propagation."""

from copaw.app.mcp.manager import MCPClientManager
from copaw.config.config import MCPClientConfig


def test_stdio_mcp_client_inherits_process_env_and_overrides_with_client_env(
    monkeypatch,
) -> None:
    """Stdio MCP children should inherit process env plus explicit overrides."""

    captured: dict[str, object] = {}

    class FakeStdIOStatefulClient:
        def __init__(
            self,
            *,
            name,
            command,
            args,
            env,
            cwd,
        ) -> None:
            captured["name"] = name
            captured["command"] = command
            captured["args"] = list(args)
            captured["env"] = dict(env)
            captured["cwd"] = cwd

    monkeypatch.setattr(
        "copaw.app.mcp.manager.StdIOStatefulClient",
        FakeStdIOStatefulClient,
    )
    monkeypatch.setenv("LIEPIN_DEBUG_DUMP_DIR", "/tmp/from-process")
    monkeypatch.setenv("SHARED_KEY", "process-value")

    client = MCPClientManager._build_client(
        MCPClientConfig(
            name="liepin_mcp",
            transport="stdio",
            command="/bin/python",
            args=["-m", "demo.server"],
            env={
                "SHARED_KEY": "client-value",
                "LIEPIN_PROFILE_DIR": "/tmp/liepin-profile",
            },
            cwd="/tmp/project",
        ),
    )

    env = captured["env"]
    assert isinstance(env, dict)
    assert env["LIEPIN_DEBUG_DUMP_DIR"] == "/tmp/from-process"
    assert env["LIEPIN_PROFILE_DIR"] == "/tmp/liepin-profile"
    assert env["SHARED_KEY"] == "client-value"
    assert getattr(client, "_copaw_rebuild_info")["env"] == env
