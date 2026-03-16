"""Interfaces for eea.genai.core"""

import functools

from zope import schema
from zope.component.hooks import setSite
from zope.interface import Attribute, Interface, implementer
from zope.publisher.interfaces.browser import IDefaultBrowserLayer

from eea.genai.core import EEAMessageFactory as _


class IEEAGenAICoreLayer(IDefaultBrowserLayer):
    """Browser layer marker for eea.genai.core."""


class ILLMClient(Interface):
    """Utility: sends prompts to an LLM, returns response text or structured data."""

    def get_model():
        """Build and return a pydantic_ai model from control panel settings + env vars.

        Returns a pydantic_ai Model instance ready to be used with Agent().
        """

    def complete(system_prompt, user_prompt, output_type=None):
        """Send system and user prompts to the LLM.

        If output_type is None, returns str with the raw LLM response.
        If output_type is a pydantic BaseModel subclass, passes it as
        result_type to pydantic_ai Agent and returns a parsed model instance.

        Raises RuntimeError on failure.
        """


class IGenAISettings(Interface):
    """Registry-backed settings shared by all `eea.genai.*` packages."""

    enabled = schema.Bool(
        title=_("Enable GenAI features"),
        description=_("Master switch used by GenAI packages to allow/disallow LLM calls."),
        default=True,
        required=False,
    )

    llm_provider = schema.Choice(
        title=_("LLM Provider"),
        description=_(
            "Provider type for the LLM backend. "
            "'openai-compatible' works with LiteLLM proxy, vLLM, and any "
            "OpenAI-compatible API."
        ),
        values=["openai-compatible", "openai", "anthropic", "google", "ollama"],
        default="openai-compatible",
        required=False,
    )

    llm_model = schema.TextLine(
        title=_("Model name"),
        description=_(
            "Model identifier (e.g. 'gpt-4o', 'claude-sonnet-4-6', 'llama3'). "
            "Falls back to LLM_MODEL env var if empty."
        ),
        default="",
        required=False,
    )

    llm_api_url = schema.TextLine(
        title=_("API URL"),
        description=_(
            "Base URL for OpenAI-compatible or Ollama endpoints "
            "(e.g. 'http://localhost:4000/v1'). "
            "Falls back to LLM_URL env var if empty. "
            "Not used for direct OpenAI/Anthropic/Google providers."
        ),
        default="",
        required=False,
    )

    global_system_rules = schema.Text(
        title=_("Global system rules"),
        description=_(
            "Prepended to every agent's system prompt. Use this for global rules "
            "(tone, safety constraints, accessibility requirements)."
        ),
        default="",
        required=False,
    )

    agents_json = schema.Text(
        title=_("Agents Configuration (JSON)"),
        description=_(
            "JSON array of agent definitions. Each agent defines system_prompt, tools, skills, etc.\n"
            "Example: [{\"name\": \"summarizer\", \"system_prompt\": \"You are...\", "
            "\"skills\": [\"metadata_extraction\"], \"tools\": [\"extract_blocks\"]}]"
        ),
        default="[]",
        required=False,
    )

    mcp_servers_json = schema.Text(
        title=_("MCP Servers Configuration (JSON)"),
        description=_(
            'JSON object of MCP server definitions. Keys are server names. '
            'Each value has either "command"+"args" (stdio) or "url" (HTTP). '
            'Supports ${VAR_NAME} and ${VAR_NAME:-default} env var syntax in values.\n'
            'Example: {"filesystem": {"command": "npx", '
            '"args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"]}}'
        ),
        default="{}",
        required=False,
    )


class IAgentConfiguration(Interface):
    """Named utility providing a default agent configuration.

    Registered via <genai:agent> ZCML directive. Packages use this to
    declare their default agents so they are available without manual
    control panel configuration.

    Registry-configured agents (agents_json) override ZCML defaults
    with the same name.
    """

    name = Attribute("Unique agent name")
    config = Attribute("Agent config dict (system_prompt, tools, output_type, max_iterations)")


@implementer(IAgentConfiguration)
class AgentConfiguration:
    """Base class for class-based agent configurations.

    Subclass this and set class attributes to define an agent.
    Use with ``<genai:agent name="..." class=".agents.MyAgent" />``.

    Usage::

        from eea.genai.core.interfaces import AgentConfiguration

        class PlotlyGeneratorAgent(AgentConfiguration):
            name = "plotly_generator"
            system_prompt = "You are a Plotly.js chart generation expert..."
            task_prompt = "Generate a complete visualization..."
            skills = ["plotly_knowledge"]
            tools = ["get_plotly_template"]
            output_type = "eea.plotly.models.ChartGenerationResult"
            max_iterations = 10
    """

    name = ""
    system_prompt = ""
    task_prompt = ""
    context_providers = []
    skills = []
    tools = []
    mcp_servers = []
    output_type = ""
    max_iterations = 10

    @property
    def config(self):
        cfg = {"name": self.name, "max_iterations": self.max_iterations}
        if self.system_prompt:
            cfg["system_prompt"] = self.system_prompt
        if self.task_prompt:
            cfg["task_prompt"] = self.task_prompt
        if self.context_providers:
            cfg["context_providers"] = list(self.context_providers)
        if self.skills:
            cfg["skills"] = list(self.skills)
        if self.tools:
            cfg["tools"] = list(self.tools)
        if self.mcp_servers:
            cfg["mcp_servers"] = list(self.mcp_servers)
        if self.output_type:
            cfg["output_type"] = self.output_type
        return cfg


class IAgentExecutor(Interface):
    """Utility that runs a pydantic_ai Agent with auto-discovered tools."""

    def run(system_prompt, user_prompt, tools=None, result_type=None,
            deps=None, max_iterations=10):
        """Run an agentic loop.

        Args:
            system_prompt: System prompt string.
            user_prompt: User prompt string.
            tools: Optional list of tool names to use (None = all registered).
            result_type: Optional pydantic BaseModel for structured output.
            deps: Optional dependencies object passed to tools via RunContext.
            max_iterations: Max LLM requests before stopping.

        Returns:
            str or result_type instance.
        """


# Directives
class IAgentContextProvider(Interface):
    """Named utility providing dynamic prompt enrichment for agents.

    Context providers are reusable capabilities that agents reference by name.
    When an agent runs, its context providers are invoked to dynamically contribute
    to the system prompt and/or user prompt.

    Register via <genai:agentContextProvider> ZCML directive. Reference from agent
    configs (ZCML or control panel JSON) via "context_providers": ["context_provider_name"].
    """

    name = Attribute("Context provider name (matches the utility registration name)")
    description = Attribute("Human-readable description (shown in control panel UI)")

    def system_prompt(deps):
        """Return text to append to the agent's system prompt.

        Args:
            deps: AgentDeps with context, request, site.

        Returns:
            str: Text to append, or empty string.
        """

    def user_prompt(deps):
        """Return text to append to the agent's user prompt.

        Args:
            deps: AgentDeps with context, request, site.

        Returns:
            str: Text to append, or empty string.
        """


class IAgentSkill(Interface):
    """Named utility providing dynamic prompt enrichment for agents.

    Skills are reusable capabilities that agents reference by name.
    When an agent runs, its skills are invoked to dynamically contribute
    to the system prompt and/or user prompt.

    Register via <genai:agentSkill> ZCML directive. Reference from agent
    configs (ZCML or control panel JSON) via "skills": ["skill_name"].
    """

    name = Attribute("Skill name (matches the utility registration name)")
    description = Attribute("Human-readable description (shown in control panel UI)")

    def system_prompt(deps):
        """Return text to append to the agent's system prompt.

        Args:
            deps: AgentDeps with context, request, site.

        Returns:
            str: Text to append, or empty string.
        """

    def user_prompt(deps):
        """Return text to append to the agent's user prompt.

        Args:
            deps: AgentDeps with context, request, site.

        Returns:
            str: Text to append, or empty string.
        """


class IAgentTool(Interface):
    """Named utility providing a tool callable for pydantic_ai agents.

    Register as a named utility with name=tool_name.
    The agent executor discovers all IAgentTool utilities and
    registers them with the pydantic_ai Agent.

    register via ZCML directive <genai:agentTool> or programmatically.
    """

    name = Attribute("Tool name (matches the utility registration name)")
    description = Attribute("Human-readable description sent to the LLM")

    def get_callable():
        """Return a callable suitable for pydantic_ai agent.tool().

        The callable receives a RunContext as first arg plus tool-specific
        keyword arguments. Its signature is introspected by pydantic_ai to
        build the tool's JSON Schema automatically.
        """


@implementer(IAgentContextProvider)
class AgentContextProvider:
    """Base class for agent context providers.

    Subclasses override ``system_prompt()`` and/or ``user_prompt()``
    to dynamically enrich agent prompts at runtime.

    Usage::

        from eea.genai.core.interfaces import AgentContextProvider

        class GenericMetadata(AgentContextProvider):
            name = "GenericMetadata"
            description = "Adds available generic metadata to the user prompt"

            def user_prompt(self, deps):
                return get_generic_metadata_context()
    """

    name = ""
    description = ""

    def system_prompt(self, deps):
        """Override to append text to the system prompt."""
        return ""

    def user_prompt(self, deps):
        """Override to append text to the user prompt."""
        return ""


@implementer(IAgentSkill)
class AgentSkill:
    """Base class for agent skills.

    Subclasses override ``system_prompt()`` and/or ``user_prompt()``
    to dynamically enrich agent prompts at runtime.

    Usage::

        from eea.genai.core.interfaces import AgentSkill

        class BlocksKnowledgeSkill(AgentSkill):
            name = "blocks_knowledge"
            description = "Adds available block types to the system prompt"

            def system_prompt(self, deps):
                return get_block_types_description()
    """

    name = ""
    description = ""

    def system_prompt(self, deps):
        """Override to append text to the system prompt."""
        return ""

    def user_prompt(self, deps):
        """Override to append text to the user prompt."""
        return ""


@implementer(IAgentTool)
class AgentTool:
    """Base class for agent tools.

    Subclasses must implement ``execute()`` with typed parameters.
    The execute method's signature is introspected by pydantic_ai to
    build the tool's JSON Schema automatically.

    Usage::

        from eea.genai.core.interfaces import AgentTool

        class SearchContentTool(AgentTool):
            name = "search_content"
            description = "Search the site catalog for content matching a query"

            def execute(self, ctx, query: str, limit: int = 5) -> str:
                catalog = getToolByName(ctx.deps["site"], "portal_catalog")
                results = catalog(SearchableText=query)[:limit]
                return json.dumps([brain.Title for brain in results])
    """

    name = ""
    description = ""

    def system_prompt(self, deps):
        """Override to add tool usage instructions to the system prompt."""
        return ""

    def execute(self, ctx, **kwargs):
        """Override in subclasses. ctx is pydantic_ai RunContext."""
        raise NotImplementedError

    def get_callable(self):
        """Return a wrapper that sets the Zope site before calling execute.

        pydantic_ai runs sync tools in a thread pool via run_in_executor.
        The new thread doesn't inherit Zope's thread-local site, so
        plone.api calls would fail. This wrapper restores the site from
        ctx.deps.site before each tool invocation.
        """
        @functools.wraps(self.execute)
        def wrapper(ctx, *args, **kwargs):
            site = getattr(ctx.deps, "site", None)
            if site is not None:
                setSite(site)
            return self.execute(ctx, *args, **kwargs)
        return wrapper
