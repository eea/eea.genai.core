"""Registry-backed settings helpers for `eea.genai.*` packages."""

from __future__ import annotations

import json
import logging
import os

from plone.registry.interfaces import IRegistry
from zope.component import getUtilitiesFor, queryUtility

from eea.genai.core.interfaces import (
    IAgentConfiguration,
    IGenAISettings,
)

logger = logging.getLogger("eea.genai.core")


def get_llm_provider(default: str = "openai-compatible") -> str:
    """Return provider from registry, falling back to default."""
    settings = _get_registry_settings()
    if settings is None:
        return default
    return getattr(settings, "llm_provider", default) or default


def get_llm_model() -> str:
    """Return model name from registry, falling back to LLM_MODEL env var."""
    settings = _get_registry_settings()
    value = ""
    if settings is not None:
        value = (getattr(settings, "llm_model", "") or "").strip()
    return value or os.environ.get("LLM_MODEL", "")


def get_llm_api_url() -> str:
    """Return API URL from registry, falling back to LLM_URL env var."""
    settings = _get_registry_settings()
    value = ""
    if settings is not None:
        value = (getattr(settings, "llm_api_url", "") or "").strip()
    return value or os.environ.get("LLM_URL", "")


def is_enabled(default: bool = True) -> bool:
    settings = _get_registry_settings()
    if settings is None:
        return default
    return bool(getattr(settings, "enabled", default))


def get_global_system_rules() -> str:
    settings = _get_registry_settings()
    if settings is None:
        return ""
    return (getattr(settings, "global_system_rules", "") or "").strip()


def get_mcp_servers_config() -> dict:
    """Return parsed mcp_servers_json from registry."""
    settings = _get_registry_settings()
    if settings is None:
        return {}
    raw = (getattr(settings, "mcp_servers_json", "") or "{}").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        logger.warning("Invalid mcp_servers_json; ignoring.")
        return {}
    return data if isinstance(data, dict) else {}


def get_agents_config() -> list[dict]:
    """Return agents configuration, merging ZCML defaults with registry overrides.

    ZCML-registered agents (via <genai:agent>) provide defaults.
    Registry agents_json overrides agents with the same name.
    """
    # Start with ZCML defaults
    by_name = _get_zcml_agents()

    # Override with registry-configured agents
    for agent in _get_registry_agents():
        if isinstance(agent, dict) and agent.get("name"):
            by_name[agent["name"]] = agent

    return list(by_name.values())


def get_agent_config(agent_name: str) -> dict | None:
    """Return a specific agent config by name, or None if not found.

    Checks registry first (overrides), then falls back to ZCML defaults.
    """
    # Check registry overrides first
    for agent in _get_registry_agents():
        if isinstance(agent, dict) and agent.get("name") == agent_name:
            return agent

    # Fall back to ZCML defaults
    zcml_agents = _get_zcml_agents()
    return zcml_agents.get(agent_name)


def get_agent_for_content_type(agent_name: str, content_type: str) -> str | None:
    """Return the resolved agent name for a content type.

    Tries ``agent_name:content_type`` first (e.g. ``summarizer:EEAFigure``).
    Falls back to ``agent_name`` if no content-type-specific agent exists.
    Returns None if neither is registered.
    """
    specific = f"{agent_name}:{content_type}"
    if get_agent_config(specific) is not None:
        return specific
    if get_agent_config(agent_name) is not None:
        return agent_name
    return None


def _get_registry_settings():
    registry = queryUtility(IRegistry)
    if registry is None:
        return None
    try:
        return registry.forInterface(IGenAISettings, check=False)
    except Exception:
        # Registry records may not exist if profile wasn't installed yet.
        return None


def _get_zcml_agents() -> dict[str, dict]:
    """Collect default agent configs registered via <genai:agent> ZCML directive."""
    agents = {}
    for name, util in getUtilitiesFor(IAgentConfiguration):
        agents[name] = util.config
    return agents


def _get_registry_agents() -> list[dict]:
    """Parse agents_json from the registry."""
    settings = _get_registry_settings()
    if settings is None:
        return []
    raw = getattr(settings, "agents_json", "") or "[]"
    raw = raw.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        logger.warning("Invalid agents_json; ignoring.")
        return []
    return data if isinstance(data, list) else []
