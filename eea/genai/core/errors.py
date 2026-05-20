"""Typed exceptions for eea.genai.core.

Replaces RuntimeError/ValueError catch-alls with errors that carry intent.
Catch them at boundaries; let them bubble inside the executor.
"""


class GenAIError(Exception):
    """Base class for all eea.genai errors."""


class AgentDisabled(GenAIError):
    """Raised when GenAI features are disabled in the control panel."""


class AgentNotFound(GenAIError, KeyError):
    """Raised when an agent name cannot be resolved (ZCML or registry)."""


class AgentConfigInvalid(GenAIError, ValueError):
    """Raised when an agent config references unknown tools/enrichers/output types."""


class AgentExecutionFailed(GenAIError, RuntimeError):
    """Raised when the underlying LLM call or tool loop fails."""


class EnricherFailed(GenAIError, RuntimeError):
    """Raised when an enricher's system_prompt/user_prompt callback raises."""

    def __init__(self, enricher_name: str, stage: str, cause: Exception):
        self.enricher_name = enricher_name
        self.stage = stage
        self.cause = cause
        super().__init__(
            f"Enricher '{enricher_name}' failed at stage '{stage}': {cause}"
        )
