"""Pure-function tests for the prompt composer — no Plone bootstrap required."""

import unittest

from eea.genai.core.prompts import build_prompts, collect_enricher_prompts
from eea.genai.core.errors import EnricherFailed


class _Stub:
    def __init__(self, name, system="", user=""):
        self.name = name
        self.description = ""
        self._s = system
        self._u = user

    def system_prompt(self, deps):
        return self._s

    def user_prompt(self, deps):
        return self._u


class _Raising:
    def __init__(self, name, stage):
        self.name = name
        self.description = ""
        self._stage = stage

    def system_prompt(self, deps):
        if self._stage == "system_prompt":
            raise RuntimeError("boom")
        return ""

    def user_prompt(self, deps):
        if self._stage == "user_prompt":
            raise RuntimeError("boom")
        return ""


class TestCollectEnricherPrompts(unittest.TestCase):

    def test_collects_named_system_and_flat_user(self):
        es = [
            _Stub("a", system="SA", user="UA"),
            _Stub("b", system="SB", user="UB"),
        ]
        sys_parts, user_parts = collect_enricher_prompts(es, deps=None)
        self.assertEqual(sys_parts, [("a", "SA"), ("b", "SB")])
        self.assertEqual(user_parts, ["UA", "UB"])

    def test_empty_strings_skipped(self):
        es = [_Stub("a"), _Stub("b", system="x")]
        sys_parts, user_parts = collect_enricher_prompts(es, deps=None)
        self.assertEqual(sys_parts, [("b", "x")])
        self.assertEqual(user_parts, [])

    def test_swallow_errors_default(self):
        es = [_Raising("bad", stage="system_prompt"), _Stub("ok", system="OK")]
        sys_parts, _ = collect_enricher_prompts(es, deps=None)
        self.assertEqual(sys_parts, [("ok", "OK")])

    def test_raise_when_swallow_disabled(self):
        es = [_Raising("bad", stage="user_prompt")]
        with self.assertRaises(EnricherFailed) as ctx:
            collect_enricher_prompts(es, deps=None, swallow_errors=False)
        self.assertEqual(ctx.exception.enricher_name, "bad")
        self.assertEqual(ctx.exception.stage, "user_prompt")


class TestBuildPrompts(unittest.TestCase):

    def test_full_composition(self):
        enrichers = [_Stub("meta", user="title: x"), _Stub("rules", system="be brief")]
        system, user = build_prompts(
            system_prompt="You are a writer.",
            task_prompt="Summarize.",
            user_prompt="Now do it.",
            enrichers=enrichers,
            tools=(),
        )
        self.assertIn("You are a writer.", system)
        self.assertIn("## ENRICHERS", system)
        self.assertIn("### rules", system)
        self.assertIn("be brief", system)
        self.assertIn("## CONTEXT", user)
        self.assertIn("title: x", user)
        self.assertIn("## TASK", user)
        self.assertIn("Summarize.", user)
        self.assertIn("## USER REQUEST", user)
        self.assertIn("Now do it.", user)

    def test_no_enrichers_no_section(self):
        system, user = build_prompts(
            system_prompt="S", task_prompt="T", user_prompt="U",
            enrichers=(), tools=(),
        )
        self.assertNotIn("## ENRICHERS", system)
        self.assertNotIn("## CONTEXT", user)
        self.assertIn("S", system)
        self.assertIn("T", user)
        self.assertIn("U", user)

    def test_only_user_prompt(self):
        system, user = build_prompts(
            system_prompt="", task_prompt="", user_prompt="hello",
            enrichers=(), tools=(),
        )
        self.assertEqual(system, "")
        self.assertIn("hello", user)
        self.assertIn("## USER REQUEST", user)

    def test_tool_section_uses_description_fallback(self):
        class _Tool:
            name = "search"
            description = "search the catalog"
        system, _ = build_prompts(
            system_prompt="", task_prompt="", user_prompt="",
            enrichers=(), tools=[_Tool()],
        )
        self.assertIn("## TOOLS", system)
        self.assertIn("### search", system)
        self.assertIn("search the catalog", system)


class TestSourceUtility(unittest.TestCase):

    def test_source_properties_override(self):
        from eea.genai.core.utils import Source

        class Obj:
            title = "from-obj"
            description = "obj-desc"

        s = Source(Obj(), {"title": "from-props"})
        self.assertEqual(s.title, "from-props")
        self.assertEqual(s.description, "obj-desc")
        self.assertIsNone(s.missing)


class TestArraySummary(unittest.TestCase):

    def test_numeric(self):
        from eea.genai.core.utils import array_summary
        out = array_summary([1, 2, 3, 2, 1])
        self.assertEqual(out["count"], 5)
        self.assertEqual(out["unique"], 3)
        self.assertEqual(out["min"], 1)
        self.assertEqual(out["max"], 3)
        self.assertEqual(out["sample"], [1, 2, 3])

    def test_strings(self):
        from eea.genai.core.utils import array_summary
        out = array_summary(["a", "b", "a", "c"])
        self.assertEqual(out["count"], 4)
        self.assertEqual(out["unique"], 3)
        self.assertIsNone(out["min"])
        self.assertIsNone(out["max"])
        self.assertEqual(out["sample"], ["a", "b", "c"])
