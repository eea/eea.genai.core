"""MCP server factory: builds pydantic_ai MCP server instances from config."""

import logging
import os
import re

from pydantic_ai.mcp import (
    MCPServerSSE,
    MCPServerStdio,
    MCPServerStreamableHTTP
)

logger = logging.getLogger("eea.genai.core")

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}:]+)(?:(:-)((?:[^}]*))?)?\}")


def _expand_env_vars(value):
    """Recursively expand ${VAR} and ${VAR:-default} in strings/dicts/lists."""
    if isinstance(value, str):

        def _replace(match):
            var_name = match.group(1)
            has_default = match.group(2) is not None
            default_value = match.group(3) if has_default else None
            if var_name in os.environ:
                return os.environ[var_name]
            if has_default:
                return default_value or ""
            raise ValueError(f"Environment variable ${{{var_name}}} is not defined")

        return _ENV_VAR_PATTERN.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    return value


def parse_tool_refs(tools_list):
    """Parse a tools list into ZCA tools and MCP refs.

    ["search_content", "filesystem/read_file", "filesystem/list_dir"]
    → (["search_content"], {"filesystem": ["read_file", "list_dir"]})
    """
    zca_tools = []
    mcp_refs = {}
    for ref in tools_list or []:
        if "/" in ref:
            server, tool = ref.split("/", 1)
            mcp_refs.setdefault(server, []).append(tool)
        else:
            zca_tools.append(ref)
    return zca_tools, mcp_refs


def build_mcp_server(name, server_config):
    """Build a pydantic_ai MCP server from a config dict.

    Args:
        name: Server name (used as tool_prefix and id).
        server_config: Dict with server config.

    Returns:
        MCPServerStdio, MCPServerSSE, or MCPServerStreamableHTTP.

    Raises:
        ValueError: If config is invalid.
    """
    config = _expand_env_vars(dict(server_config))
    timeout = config.pop("timeout", None)

    if "command" in config:
        kwargs = {
            "command": config["command"],
            "args": config.get("args", []),
        }
        if config.get("env"):
            kwargs["env"] = config["env"]
        if config.get("cwd"):
            kwargs["cwd"] = config["cwd"]
        if timeout:
            kwargs["timeout"] = timeout
        return MCPServerStdio(**kwargs)

    if "url" in config:
        transport = config.pop("transport", None)
        kwargs = {"url": config["url"]}
        if config.get("headers"):
            kwargs["headers"] = config["headers"]
        if timeout:
            kwargs["timeout"] = timeout

        if transport == "streamable-http":
            return MCPServerStreamableHTTP(**kwargs)
        return MCPServerSSE(**kwargs)

    raise ValueError(f"MCP server '{name}': must have 'command' or 'url'")


def build_mcp_servers(server_names, all_config):
    """Build unfiltered MCP server toolsets (all tools exposed).

    Args:
        server_names: list of server names.
        all_config: full mcp_servers_json dict.

    Returns:
        list of MCP server toolsets.
    """
    toolsets = []
    for server_name in server_names:
        if server_name not in all_config:
            logger.warning("MCP server '%s' not found in configuration", server_name)
            continue
        try:
            server = build_mcp_server(server_name, all_config[server_name])
            toolsets.append(server)
        except Exception:
            logger.warning(
                "Failed to build MCP server '%s'", server_name, exc_info=True
            )
    return toolsets


def build_filtered_mcp_servers(mcp_tool_refs, all_config):
    """Build filtered MCP server toolsets.

    Args:
        mcp_tool_refs: dict of server_name -> list of tool names.
        all_config: full mcp_servers_json dict.

    Returns:
        list of filtered toolsets.
    """
    toolsets = []
    for server_name, tool_names in mcp_tool_refs.items():
        if server_name not in all_config:
            logger.warning("MCP server '%s' not found in configuration", server_name)
            continue
        try:
            server = build_mcp_server(server_name, all_config[server_name])
            allowed = set(tool_names)
            filtered = server.filtered(
                lambda ctx, tool_def, _allowed=allowed: tool_def.name in _allowed
            )
            toolsets.append(filtered)
        except Exception:
            logger.warning(
                "Failed to build MCP server '%s'", server_name, exc_info=True
            )
    return toolsets
