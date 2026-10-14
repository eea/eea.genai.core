"""Public, SSR-safe GenAI feature flags; not administrative configuration."""

from plone.restapi.services import Service

from eea.genai.core.settings import get_public_settings


class GenAISettingsGet(Service):
    """Return only explicitly allowlisted settings to frontend consumers."""

    def reply(self):
        return {
            "@id": f"{self.context.absolute_url()}/@genai-settings",
            **get_public_settings(),
        }
