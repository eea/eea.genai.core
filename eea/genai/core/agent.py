"""Agent executor: runs pydantic_ai Agent with auto-discovered tools."""

import logging
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits
from zope.component import getUtilitiesFor, queryUtility
from zope.component.hooks import getSite
from zope.interface import implementer

from eea.genai.core.interfaces import (
    IAgentContextProvider,
    IAgentExecutor,
    IAgentSkill,
    IAgentTool,
    ILLMClient,
)
from eea.genai.core.settings import (
    get_agent_config,
    get_global_system_rules,
    is_enabled,
)

logger = logging.getLogger("eea.genai.core")


class AgentDeps:
    """Dependencies passed to agent tools via RunContext.

    This class is passed as `deps` to the pydantic_ai Agent,
    making it available in tool functions via `ctx.deps`.
    """

    def __init__(self, context=None, request=None):
        self.context = context
        self.request = request
        self.site = getSite()


@implementer(IAgentExecutor)
class PydanticAIAgentExecutor:
    """Runs an agentic loop using pydantic_ai with ZCA-registered tools."""

    def run(self, system_prompt, user_prompt, tools=None, output_type=None,
            deps=None, max_iterations=10, mcp_toolsets=None):
        """Run an agentic loop.

        Creates a pydantic_ai Agent, registers discovered tools, and
        runs the tool-calling loop until the LLM produces a final answer
        or max_iterations is reached.

        Args:
            system_prompt: System prompt string.
            user_prompt: User prompt string.
            tools: Optional list of ZCA tool names to use.
            output_type: Optional pydantic BaseModel for structured output.
            deps: Optional dependencies object passed to tools via RunContext.
            max_iterations: Max LLM requests before stopping.
            mcp_toolsets: Optional list of filtered MCP server toolsets.

        Returns:
            str or output_type instance.
        """
        if not is_enabled():
            raise RuntimeError("GenAI features are disabled in the GenAI control panel")

        client = queryUtility(ILLMClient)
        if client is None:
            raise RuntimeError("No ILLMClient utility registered")

        model = client.get_model()

        agent = Agent(
            model,
            system_prompt=system_prompt,
            output_type=output_type if output_type else str,
            deps_type=type(deps) if deps is not None else type(None),
        )

        # Register ZCA-discovered tools
        discovered = self._discover_utilities(IAgentTool, tools)
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
            logger.debug(
                "Agent running with %d MCP toolsets", len(mcp_toolsets)
            )

        result = agent.run_sync(
            user_prompt,
            deps=deps,
            usage_limits=UsageLimits(request_limit=max_iterations),
            toolsets=mcp_toolsets or None,
        )
        return result.output

    def run_with_agent(self, agent_name: str, user_prompt=None, deps=None) -> Any:
        """Run an agent by name from configuration.

        Looks up the agent config (ZCML default or control panel override),
        applies context providers and skills to enrich prompts, then executes.

        Args:
            agent_name: Name of the agent as configured.
            user_prompt: Optional user request text (the actual runtime input).
            deps: Optional dependencies object passed to tools and enrichers.

        Returns:
            The agent's output (str or structured type based on agent config).
        """
        config = get_agent_config(agent_name)
        if config is None:
            raise ValueError(f"Agent '{agent_name}' not found in configuration")

        system_prompt = config.get("system_prompt", "")
        task_prompt = config.get("task_prompt", "")

        # Prepend global system rules
        global_prompt = get_global_system_rules()
        if global_prompt:
            if system_prompt:
                system_prompt = f"{global_prompt}\n\n{system_prompt}"
            else:
                system_prompt = global_prompt

        all_tools = config.get("tools", [])

        # Split tools into ZCA tools and MCP tool refs early,
        # so _build_prompts only discovers ZCA tools for system prompt
        from eea.genai.core.mcp import parse_tool_refs

        zca_tools, mcp_refs = parse_tool_refs(all_tools)

        # Build structured prompts: SYSTEM + SKILLS → system, CONTEXT + TASK → user
        # Pass zca_tools so only ZCA tools contribute to the static system prompt.
        # MCP tool descriptions are added dynamically at runtime via run().
        build_config = dict(config)
        build_config["tools"] = zca_tools
        system_prompt, final_user_prompt = self._build_prompts(
            system_prompt, task_prompt, user_prompt, build_config, deps
        )
        max_iterations = config.get("max_iterations", 10)
        output_type_path = config.get("output_type")

        # Build MCP toolsets: filtered (from tools refs) + unfiltered (from mcp_servers)
        # Unfiltered servers take precedence — skip filtered refs for the same server.
        mcp_toolsets = []
        unfiltered_servers = set(config.get("mcp_servers") or [])
        if mcp_refs or unfiltered_servers:
            from eea.genai.core.mcp import build_filtered_mcp_servers, build_mcp_servers
            from eea.genai.core.settings import get_mcp_servers_config

            mcp_config = get_mcp_servers_config()
            # Filtered refs, excluding servers already in mcp_servers
            filtered_refs = {
                k: v for k, v in mcp_refs.items() if k not in unfiltered_servers
            }
            if filtered_refs:
                mcp_toolsets.extend(
                    build_filtered_mcp_servers(filtered_refs, mcp_config)
                )
            if unfiltered_servers:
                mcp_toolsets.extend(
                    build_mcp_servers(list(unfiltered_servers), mcp_config)
                )

        # Resolve output_type from dotted path if specified
        output_type = None
        if output_type_path and isinstance(output_type_path, str):
            output_type = self._import_output_type(output_type_path)

        return self.run(
            system_prompt=system_prompt,
            user_prompt=final_user_prompt,
            tools=zca_tools,
            output_type=output_type,
            deps=deps,
            max_iterations=max_iterations,
            mcp_toolsets=mcp_toolsets,
        )

    def _discover_utilities(self, interface, names):
        """Look up named utilities from ZCA by interface.

        Args:
            interface: The ZCA interface to look up.
            names: List of utility names to look up. Only explicitly
                listed utilities are returned.
        """
        if not names:
            return []
        found = []
        for name, util in getUtilitiesFor(interface):
            if name in names:
                found.append(util)
        return found

    def _collect_system_prompts(self, enrichers, deps):
        """Collect system prompt fragments only.

        Returns:
            list: (name, text) tuples for non-empty system prompts.
        """
        parts = []
        for enricher in enrichers:
            try:
                text = enricher.system_prompt(deps)
                if text:
                    parts.append((enricher.name, text))
            except Exception:
                logger.warning("Enricher '%s' system_prompt() failed",
                               enricher.name, exc_info=True)
        return parts

    def _collect_enricher_prompts(self, enrichers, deps):
        """Collect system and user prompt fragments from enrichers.

        Returns:
            tuple: (system_parts, user_parts) — lists of non-empty strings.
        """
        system_parts = []
        user_parts = []
        for enricher in enrichers:
            try:
                extra_system = enricher.system_prompt(deps)
                if extra_system:
                    system_parts.append(extra_system)
            except Exception:
                logger.warning("Enricher '%s' system_prompt() failed",
                               enricher.name, exc_info=True)
            try:
                extra_user = enricher.user_prompt(deps)
                if extra_user:
                    user_parts.append(extra_user)
            except Exception:
                logger.warning("Enricher '%s' user_prompt() failed",
                               enricher.name, exc_info=True)
        return system_parts, user_parts

    def _build_prompts(self, system_prompt, task_prompt, user_prompt, config, deps):
        """Build structured system and user prompts.

        Composes prompts in sections:
            SYSTEM: system_prompt + SKILLS + TOOLS
            USER:   CONTEXT + TASK + USER REQUEST

        Skills contribute behavioral instructions (system-level).
        Tools contribute usage instructions (system-level).
        Context providers contribute runtime data (user-level).
        The task_prompt becomes the TASK section in the user prompt.
        The user_prompt is the actual runtime user request (last section).

        Returns:
            tuple: (final_system_prompt, final_user_prompt)
        """
        # -- Skills (behavioral instructions → system prompt only) --
        skills = self._discover_utilities(
            IAgentSkill, config.get("skills")
        )
        skill_parts = self._collect_system_prompts(skills, deps)

        # -- Tools (usage instructions → system prompt) --
        tools = self._discover_utilities(
            IAgentTool, config.get("tools")
        )
        tool_parts = self._collect_system_prompts(tools, deps)

        # -- Context providers (runtime data) --
        context_providers = self._discover_utilities(
            IAgentContextProvider, config.get("context_providers")
        )
        ctx_system, ctx_user = self._collect_enricher_prompts(
            context_providers, deps
        )

        all_enrichers = skills + tools + context_providers
        if all_enrichers:
            logger.debug(
                "Applied %d enrichers: %s",
                len(all_enrichers),
                ", ".join(e.name for e in all_enrichers),
            )

        # -- Compose system prompt: SYSTEM + SKILLS + TOOLS --
        system_parts = []
        if system_prompt:
            system_parts.append(system_prompt)
        if skill_parts:
            section = "\n\n".join(
                f"### {name}\n\n{text}" for name, text in skill_parts
            )
            system_parts.append("## SKILLS\n\n" + section)
        if tool_parts:
            section = "\n\n".join(
                f"### {name}\n\n{text}" for name, text in tool_parts
            )
            system_parts.append("## TOOLS\n\n" + section)
        if ctx_system:
            system_parts.append("\n\n".join(ctx_system))
        final_system = "\n\n".join(system_parts)

        # -- Compose user prompt: CONTEXT + TASK + USER REQUEST --
        user_parts = []
        if ctx_user:
            user_parts.append("## CONTEXT\n\n" + "\n\n".join(ctx_user))
        if task_prompt:
            user_parts.append("## TASK\n\n" + task_prompt)
        if user_prompt:
            user_parts.append("## USER REQUEST\n\n" + user_prompt)
        final_user = "\n\n".join(user_parts)

        return final_system, final_user

    def _import_output_type(self, type_path: str):
        """Import an output type (pydantic model) from a dotted path."""
        try:
            from importlib import import_module
            parts = type_path.rsplit(".", 1)
            if len(parts) == 1:
                return None
            module_path, class_name = parts
            module = import_module(module_path)
            return getattr(module, class_name)
        except Exception:
            logger.warning("Could not import output_type: %s", type_path)
            return None
