"""Contracts for package-contributed controlpanel settings and public flags."""

import unittest
from types import SimpleNamespace

from plone.registry import Registry
from plone.registry.fieldfactory import (
    choicePersistentFieldAdapter,
    persistentFieldAdapter,
)
from plone.registry.interfaces import IRegistry
from zope import schema
from zope.component import getGlobalSiteManager, provideAdapter
from zope.component.testing import setUp, tearDown
from zope.interface import Interface, implementer

from eea.genai.core.interfaces import IGenAISettings, IGenAISettingsSection
from eea.genai.core.settings import (
    GENAI_SETTINGS_PREFIX,
    get_controlpanel_schema,
    get_public_settings,
    get_settings_value,
)


class IExampleSettings(Interface):
    example_enabled = schema.Bool(title="Enable example AI", default=False)


@implementer(IGenAISettingsSection)
class ExampleSection:
    schema = IExampleSettings

    def get_public_settings(self):
        return {"enabled": get_settings_value(self.schema, "example_enabled")}


class TestSettingsSections(unittest.TestCase):
    def setUp(self):
        setUp()
        self.addCleanup(tearDown)
        provideAdapter(persistentFieldAdapter)
        provideAdapter(choicePersistentFieldAdapter)
        self.sm = getGlobalSiteManager()
        self.registry = Registry()
        self.registry.registerInterface(IGenAISettings)
        self.sm.registerUtility(self.registry, IRegistry)
        self.section = ExampleSection()
        self.sm.registerUtility(self.section, IGenAISettingsSection, "example")
        self.addCleanup(self.sm.unregisterUtility, self.registry, IRegistry)
        self.addCleanup(
            self.sm.unregisterUtility, self.section, IGenAISettingsSection, "example"
        )

    def test_both_controlpanels_include_contributed_settings(self):
        from eea.genai.core.browser.controlpanel import GenAISettingsForm
        from eea.genai.core.restapi.controlpanel import GenAIRegistryControlpanel

        combined = get_controlpanel_schema()
        self.assertIn("enabled", combined)
        self.assertIn("example_enabled", combined)
        form = GenAISettingsForm(None, None)
        panel = object.__new__(GenAIRegistryControlpanel)
        self.assertIs(form.schema, combined)
        self.assertIs(panel.schema, combined)
        self.assertEqual(form.schema_prefix, GENAI_SETTINGS_PREFIX)
        self.assertEqual(panel.schema_prefix, GENAI_SETTINGS_PREFIX)

    def test_combined_settings_save_without_changing_existing_record_names(self):
        self.registry.registerInterface(IExampleSettings, prefix=GENAI_SETTINGS_PREFIX)
        proxy = self.registry.forInterface(
            get_controlpanel_schema(), prefix=GENAI_SETTINGS_PREFIX
        )
        proxy.enabled = False
        proxy.example_enabled = True
        self.assertFalse(self.registry.forInterface(IGenAISettings).enabled)
        self.assertTrue(get_settings_value(IExampleSettings, "example_enabled"))

    def test_public_defaults_work_before_addon_records_are_installed(self):
        self.assertEqual(
            get_public_settings(),
            {"enabled": True, "features": {"example": {"enabled": False}}},
        )

    def test_public_endpoint_does_not_expose_controlpanel_infrastructure(self):
        from eea.genai.core.restapi.settings import GenAISettingsGet

        self.registry.forInterface(IGenAISettings).llm_model = "private-model"
        service = GenAISettingsGet()
        service.context = SimpleNamespace(absolute_url=lambda: "http://site")
        self.assertEqual(
            service.reply(),
            {
                "@id": "http://site/@genai-settings",
                "enabled": True,
                "features": {"example": {"enabled": False}},
            },
        )

    def test_duplicate_field_names_are_rejected(self):
        class IConflictingSettings(Interface):
            enabled = schema.Bool(default=False)

        conflicting = ExampleSection()
        conflicting.schema = IConflictingSettings
        self.sm.registerUtility(conflicting, IGenAISettingsSection, "conflicting")
        self.addCleanup(
            self.sm.unregisterUtility,
            conflicting,
            IGenAISettingsSection,
            "conflicting",
        )
        with self.assertRaises(ValueError):
            get_controlpanel_schema()
