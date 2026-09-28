"""Pure-function tests for multimodal content part collection."""

import unittest

from eea.genai.core.errors import EnricherFailed
from eea.genai.core.interfaces import Enricher
from eea.genai.core.prompts import assemble_user_prompt, collect_content_parts


class _PartsStub:
    def __init__(self, name, parts=(), raises=None):
        self.name = name
        self.description = ""
        self._parts = parts if parts is None else list(parts)
        self._raises = raises

    def system_prompt(self, deps):
        return ""

    def user_prompt(self, deps):
        return ""

    def content_parts(self, deps):
        if self._raises is not None:
            raise self._raises
        return self._parts


class _TextOnly:
    """Enricher without a content_parts method — must be skipped."""

    name = "textonly"
    description = ""

    def system_prompt(self, deps):
        return ""

    def user_prompt(self, deps):
        return "u"


class TestCollectContentParts(unittest.TestCase):
    def test_flattens_parts_in_enricher_order(self):
        parts = collect_content_parts(
            [_PartsStub("a", ["p1", "p2"]), _PartsStub("b", ["p3"])],
            deps=None,
        )
        self.assertEqual(parts, ["p1", "p2", "p3"])

    def test_enrichers_without_content_parts_skipped(self):
        self.assertEqual(
            collect_content_parts([_TextOnly()], deps=None),
            [],
        )

    def test_base_enricher_default_empty(self):
        class MyEnricher(Enricher):
            name = "m"

        self.assertEqual(collect_content_parts([MyEnricher()], deps=None), [])

    def test_empty_part_lists_skipped(self):
        self.assertEqual(
            collect_content_parts(
                [_PartsStub("a", []), _PartsStub("b", None)], deps=None
            ),
            [],
        )

    def test_swallow_errors_default(self):
        parts = collect_content_parts(
            [_PartsStub("bad", raises=RuntimeError("boom")), _PartsStub("ok", ["p"])],
            deps=None,
        )
        self.assertEqual(parts, ["p"])

    def test_raise_when_swallow_disabled(self):
        with self.assertRaises(EnricherFailed) as ctx:
            collect_content_parts(
                [_PartsStub("bad", raises=RuntimeError("boom"))],
                deps=None,
                swallow_errors=False,
            )
        self.assertEqual(ctx.exception.enricher_name, "bad")
        self.assertEqual(ctx.exception.stage, "content_parts")


class TestEnricherBaseContentParts(unittest.TestCase):
    def test_default_returns_empty_list(self):
        class MyEnricher(Enricher):
            name = "m"

        self.assertEqual(MyEnricher().content_parts(deps=None), [])


class TestAssembleUserPrompt(unittest.TestCase):
    def test_no_parts_returns_text_unchanged(self):
        self.assertEqual(assemble_user_prompt("hello", []), "hello")
        self.assertEqual(assemble_user_prompt("", []), "")

    def test_parts_wrapped_with_text_content(self):
        from pydantic_ai.messages import ImageUrl, TextContent

        part = ImageUrl(url="data:image/jpeg;base64,x", media_type="image/jpeg")
        prompt = assemble_user_prompt("describe this", [part])
        self.assertIsInstance(prompt, list)
        self.assertEqual(prompt, [part, TextContent(content="describe this")])

    def test_parts_without_text(self):
        from pydantic_ai.messages import ImageUrl

        part = ImageUrl(url="data:image/jpeg;base64,x", media_type="image/jpeg")
        prompt = assemble_user_prompt("", [part])
        self.assertEqual(prompt, [part])
