"""Agent executor: runs pydantic_ai Agent with auto-discovered tools."""

from __future__ import annotations

import logging
from importlib import import_module
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
from zope.component import queryUtility
from zope.component.hooks import getSite
from zope.interface import implementer

from eea.genai.core.errors import (
    AgentConfigInvalid,
    AgentDisabled,
    AgentExecutionFailed,
    AgentNotFound,
)
from eea.genai.core.interfaces import (
    IAgentExecutor,
    IAgentTool,
    IEnricher,
    ILLMClient,
)
from eea.genai.core.prompts import build_prompts
from eea.genai.core.settings import (
    get_agent_config,
    get_global_system_rules,
    is_enabled,
)
from eea.genai.core.utils import batch_get_utilities

logger = logging.getLogger("eea.genai.core")


class AgentDeps:
    """Dependencies passed to agent tools via RunContext.

    Replaces the three near-identical subclasses that used to live in
    summary / blocks / plotly. Pass feature-specific values via `extras`
    (also accessible as attributes for convenience):

        deps = AgentDeps(context=obj, request=req, properties=props)
        deps.properties        # attribute access
        deps.extras["properties"]  # dict access
    """

    def __init__(self, context: Any = None, request: Any = None, **extras: Any):
        self.context = context
        self.request = request
        self.site = getSite()
        self.extras: dict[str, Any] = dict(extras)
        for key, value in extras.items():
            setattr(self, key, value)


def _enricher_names(config: dict) -> list[str]:
    """Collect enricher names from new + legacy keys, preserving order.

    Accepts ``enrichers`` (preferred), plus legacy ``skills`` and
    ``context_providers`` for backward read of existing control-panel JSON.
    """
    names: list[str] = []
    for key in ("enrichers", "skills", "context_providers"):
        for n in config.get(key) or []:
            if n not in names:
                names.append(n)
    return names


def _import_dotted(path: str) -> Any:
    """Import ``module.attr`` from a dotted path. Raises ImportError on failure."""
    if "." not in path:
        raise ImportError(f"output_type must be dotted module.Class, got '{path}'")
    module_path, attr = path.rsplit(".", 1)
    return getattr(import_module(module_path), attr)


@implementer(IAgentExecutor)
class PydanticAIAgentExecutor:
    """Runs an agentic loop using pydantic_ai with ZCA-registered tools."""

    def run(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[str] | None = None,
        output_type: Any = None,
        deps: Any = None,
        max_iterations: int = 10,
        mcp_toolsets: list | None = None,
    ) -> Any:
        """Run a single agentic loop with already-composed prompts.

        Returns the structured output (if ``output_type`` is set) or a string.
        """
        if not is_enabled():
            raise AgentDisabled("GenAI features are disabled in the control panel")

        client = queryUtility(ILLMClient)
        if client is None:
            raise AgentExecutionFailed("No ILLMClient utility registered")

        model = client.get_model()

        agent = Agent(
            model,
            system_prompt=system_prompt,
            output_type=output_type if output_type else str,
            deps_type=type(deps) if deps is not None else type(None),
        )

        discovered = list(batch_get_utilities(IAgentTool, tools).values())
        for tool_util in discovered:
            agent.tool(name=tool_util.name, description=tool_util.description)(
                tool_util.get_callable()
            )

        if discovered:
            logger.debug(
                "Agent running with %d ZCA tools: %s",
                len(discovered),
                ", ".join(t.name for t in discovered),
            )
        if mcp_toolsets:
            logger.debug("Agent running with %d MCP toolsets", len(mcp_toolsets))

        try:
            result = agent.run_sync(
                user_prompt,
                deps=deps,
                usage_limits=UsageLimits(request_limit=max_iterations),
                toolsets=mcp_toolsets or None,
            )
        except Exception as exc:
            raise AgentExecutionFailed(f"Agent run failed: {exc}") from exc
        return result.output

    def run_with_agent(
        self, agent_name: str, user_prompt: str | None = None, deps: Any = None,
    ) -> Any:
        """Resolve agent config by name, enrich prompts, execute."""
        config = get_agent_config(agent_name)
        if config is None:
            raise AgentNotFound(f"Agent '{agent_name}' not found in configuration")

        system_prompt = config.get("system_prompt", "")
        task_prompt = config.get("task_prompt", "")

        global_prompt = get_global_system_rules()
        if global_prompt:
            system_prompt = (
                f"{global_prompt}\n\n{system_prompt}" if system_prompt else global_prompt
            )

        all_tools = config.get("tools") or []

        from eea.genai.core.mcp import parse_tool_refs

        zca_tools, mcp_refs = parse_tool_refs(all_tools)

        enrichers = list(
            batch_get_utilities(IEnricher, _enricher_names(config)).values()
        )
        tool_utils = list(batch_get_utilities(IAgentTool, zca_tools).values())

        if enrichers or tool_utils:
            logger.debug(
                "Applied %d enrichers + %d tools to agent '%s'",
                len(enrichers), len(tool_utils), agent_name,
            )

        final_system, final_user = build_prompts(
            system_prompt=system_prompt,
            task_prompt=task_prompt,
            user_prompt=user_prompt or "",
            enrichers=enrichers,
            tools=tool_utils,
            deps=deps,
        )

        mcp_toolsets = self._build_mcp_toolsets(config, mcp_refs)

        output_type_path = config.get("output_type")
        output_type = None
        if output_type_path:
            try:
                output_type = _import_dotted(output_type_path)
            except (ImportError, AttributeError) as exc:
                raise AgentConfigInvalid(
                    f"Agent '{agent_name}' has invalid output_type "
                    f"'{output_type_path}': {exc}"
                ) from exc

        return self.run(
            system_prompt=final_system,
            user_prompt=final_user,
            tools=zca_tools,
            output_type=output_type,
            deps=deps,
            max_iterations=config.get("max_iterations", 10),
            mcp_toolsets=mcp_toolsets,
        )

    @staticmethod
    def _build_mcp_toolsets(config: dict, mcp_refs: dict) -> list:
        unfiltered_servers = set(config.get("mcp_servers") or [])
        if not (mcp_refs or unfiltered_servers):
            return []
        from eea.genai.core.mcp import (
            build_filtered_mcp_servers,
            build_mcp_servers,
        )
        from eea.genai.core.settings import get_mcp_servers_config

        mcp_config = get_mcp_servers_config()
        toolsets: list = []
        filtered_refs = {
            k: v for k, v in mcp_refs.items() if k not in unfiltered_servers
        }
        if filtered_refs:
            toolsets.extend(build_filtered_mcp_servers(filtered_refs, mcp_config))
        if unfiltered_servers:
            toolsets.extend(
                build_mcp_servers(list(unfiltered_servers), mcp_config)
            )
        return toolsets
