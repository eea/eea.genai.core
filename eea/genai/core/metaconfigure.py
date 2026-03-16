"""Custom ZCML directives for eea.genai.core"""

from zope.component.zcml import utility
from zope.configuration import fields as configuration_fields
from zope.interface import Interface
from zope.schema import TextLine

from eea.genai.core.interfaces import (
    IAgentConfiguration,
    IAgentContextProvider,
    IAgentSkill,
    IAgentTool,
)


# --- Agent configuration directive ---


class IAgentDirective(Interface):
    """Schema for the <genai:agent> ZCML directive.

    Declares a default agent configuration. Packages use this to
    register their agents so they work out of the box without manual
    control panel setup. Registry agents_json overrides these defaults.

    Provide ``name`` and ``class`` pointing to an ``AgentConfiguration``
    subclass. All configuration lives in the Python class.
    """

    name = TextLine(
        title="Agent name",
        description="Unique name for this agent",
        required=True,
    )

    class_ = configuration_fields.GlobalObject(
        title="Class",
        description=(
            "A class extending AgentConfiguration that defines system_prompt, "
            "task_prompt, skills, tools, context_providers, output_type, "
            "and max_iterations."
        ),
        required=True,
    )


def agentDirective(_context, name, class_):
    """Handler for <genai:agent> ZCML directive.

    Instantiates the AgentConfiguration subclass and registers it as
    an IAgentConfiguration named utility.
    """
    component = class_()
    component.name = name
    utility(
        _context,
        provides=IAgentConfiguration,
        name=name,
        component=component,
    )


# --- Agent context provider directive ---

class IAgentContextProviderDirective(Interface):
    """Schema for the <genai:agentContextProvider> ZCML directive."""

    name = TextLine(
        title="Context provider name",
        description="Unique name for this context provider",
        required=True,
    )

    class_ = configuration_fields.GlobalObject(
        title="Class",
        description="A class implementing IAgentContextProvider (e.g. subclass of AgentContextProvider).",
        required=True,
    )


def agentContextProviderDirective(_context, name, class_):
    """Handler for <genai:agentContextProvider> ZCML directive.

    Registers an IAgentContextProvider as a named utility so it can be
    discovered by the agent executor.
    """
    component = class_()
    component.name = name
    utility(
        _context,
        provides=IAgentContextProvider,
        name=name,
        component=component,
    )


# --- Agent skill directive ---

class IAgentSkillDirective(Interface):
    """Schema for the <genai:agentSkill> ZCML directive."""

    name = TextLine(
        title="Skill name",
        description="Unique name for this skill",
        required=True,
    )

    class_ = configuration_fields.GlobalObject(
        title="Class",
        description="A class implementing IAgentSkill (e.g. subclass of AgentSkill).",
        required=True,
    )


def agentSkillDirective(_context, name, class_):
    """Handler for <genai:agentSkill> ZCML directive.

    Registers an IAgentSkill as a named utility so it can be
    discovered by the agent executor.
    """
    component = class_()
    component.name = name
    utility(
        _context,
        provides=IAgentSkill,
        name=name,
        component=component,
    )


# --- Agent tool directive ---

class IAgentToolDirective(Interface):
    """Schema for the <genai:agentTool> ZCML directive."""

    name = TextLine(
        title="Tool name",
        description="Unique name for this tool (used in LLM function calling)",
        required=True,
    )

    class_ = configuration_fields.GlobalObject(
        title="Class",
        description="A class implementing IAgentTool (e.g. subclass of AgentTool).",
        required=True,
    )


def agentToolDirective(_context, name, class_):
    """Handler for <genai:agentTool> ZCML directive.

    Registers an IAgentTool as a named utility so it can be
    discovered by the agent executor.
    """
    component = class_()
    component.name = name
    utility(
        _context,
        provides=IAgentTool,
        name=name,
        component=component,
    )
