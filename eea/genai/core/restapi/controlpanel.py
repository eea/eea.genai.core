"""GenAI control panel adapter for `plone.restapi` controlpanels."""

from zope.component import adapter
from zope.interface import Interface

from plone.restapi.controlpanels import RegistryConfigletPanel

from eea.genai.core.interfaces import IEEAGenAICoreLayer
from eea.genai.core.interfaces import IGenAISettings


@adapter(Interface, IEEAGenAICoreLayer)
class GenAIRegistryControlpanel(RegistryConfigletPanel):
    schema = IGenAISettings
    schema_prefix = None
    configlet_id = "genai"
    configlet_category_id = "Products"
    title = "GenAI Settings"
    group = "Products"
