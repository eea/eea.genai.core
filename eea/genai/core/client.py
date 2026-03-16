"""LLM client utility using pydantic_ai"""

import logging
import os

from pydantic_ai import Agent
from zope.interface import implementer

from eea.genai.core.interfaces import ILLMClient
from eea.genai.core.settings import (
    get_llm_api_url,
    get_llm_model,
    get_llm_provider,
    is_enabled
)

logger = logging.getLogger("eea.genai.core")


@implementer(ILLMClient)
class PydanticAIClient:
    """LLM client using pydantic_ai Agent for model-agnostic LLM access."""

    def get_model(self):
        """Build a pydantic_ai model from control panel settings + env vars."""
        provider = get_llm_provider()
        model_name = get_llm_model()
        api_url = get_llm_api_url()
        api_key = os.environ.get("LLM_API_KEY", "")

        if not model_name:
            raise RuntimeError(
                "No LLM model configured. Set it in the GenAI control panel "
                "or via the LLM_MODEL environment variable."
            )

        if provider == "openai-compatible":
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider
            kwargs = {}
            if api_url:
                kwargs["base_url"] = api_url
            if api_key:
                kwargs["api_key"] = api_key
            return OpenAIChatModel(model_name, provider=OpenAIProvider(**kwargs))

        if provider == "openai":
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider
            kwargs = {}
            if api_key:
                kwargs["api_key"] = api_key
            return OpenAIChatModel(model_name, provider=OpenAIProvider(**kwargs))

        if provider == "anthropic":
            from pydantic_ai.models.anthropic import AnthropicModel
            from pydantic_ai.providers.anthropic import AnthropicProvider
            anthropic_kwargs = {}
            if api_key:
                anthropic_kwargs["api_key"] = api_key
            if api_url:
                anthropic_kwargs["base_url"] = api_url
            return AnthropicModel(model_name, provider=AnthropicProvider(**anthropic_kwargs))

        if provider == "google":
            from pydantic_ai.models.google import GoogleModel
            from pydantic_ai.providers.google import GoogleProvider
            google_kwargs = {}
            if api_key:
                google_kwargs["api_key"] = api_key
            return GoogleModel(model_name, provider=GoogleProvider(**google_kwargs))

        if provider == "ollama":
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.ollama import OllamaProvider
            kwargs = {}
            if api_url:
                kwargs["base_url"] = api_url
            return OpenAIChatModel(model_name, provider=OllamaProvider(**kwargs))

        raise RuntimeError(f"Unknown LLM provider: {provider}")

    def complete(self, system_prompt, user_prompt, output_type=None):
        """Send prompts to the LLM and return the response.

        If output_type is None, returns the raw response as a string.
        If output_type is a pydantic BaseModel subclass, passes it as
        output_type so pydantic_ai handles structured output natively.
        """
        if not is_enabled():
            raise RuntimeError("GenAI features are disabled in the GenAI control panel")

        model = self.get_model()

        agent = Agent(
            model,
            system_prompt=system_prompt,
            output_type=output_type if output_type else str,
        )

        result = agent.run_sync(user_prompt)
        return result.output
