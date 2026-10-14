"""GenAI control panel (registry-backed)."""

from plone.app.registry.browser.controlpanel import ControlPanelFormWrapper
from plone.app.registry.browser.controlpanel import RegistryEditForm

from eea.genai.core.settings import GENAI_SETTINGS_PREFIX, get_controlpanel_schema


class GenAISettingsForm(RegistryEditForm):
    schema_prefix = GENAI_SETTINGS_PREFIX
    id = "genai"
    label = "GenAI Settings"

    @property
    def schema(self):
        return get_controlpanel_schema()


class GenAIControlPanelFormWrapper(ControlPanelFormWrapper):
    form = GenAISettingsForm
