"""GenAI control panel adapter for `plone.restapi` controlpanels."""

from zope.component import adapter
from zope.interface import Interface

from plone.restapi.controlpanels import RegistryConfigletPanel

from eea.genai.core.interfaces import IEEAGenAICoreLayer
from eea.genai.core.settings import GENAI_SETTINGS_PREFIX, get_controlpanel_schema


@adapter(Interface, IEEAGenAICoreLayer)
class GenAIRegistryControlpanel(RegistryConfigletPanel):
    schema_prefix = GENAI_SETTINGS_PREFIX
    configlet_id = "genai"
    configlet_category_id = "Products"
    title = "GenAI Settings"
    group = "Products"

    @property
    def schema(self):
        return get_controlpanel_schema()
