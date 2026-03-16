"""GenAI control panel (registry-backed)."""

from plone.app.registry.browser.controlpanel import ControlPanelFormWrapper
from plone.app.registry.browser.controlpanel import RegistryEditForm

from eea.genai.core.interfaces import IGenAISettings


class GenAISettingsForm(RegistryEditForm):
    schema = IGenAISettings
    id = "genai"
    label = "GenAI Settings"


class GenAIControlPanelFormWrapper(ControlPanelFormWrapper):
    form = GenAISettingsForm
