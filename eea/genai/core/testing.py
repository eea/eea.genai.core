"""Lightweight fixtures for agent tests — no Plone bootstrap needed.

Use `make_deps()` to build an AgentDeps without instantiating a real
content object or request. Use `StubEnricher` to drive prompt-building
tests without registering ZCA utilities.
"""

from __future__ import annotations

from typing import Any

from eea.genai.core.agent import AgentDeps


def make_deps(context: Any = None, request: Any = None, **extras: Any) -> AgentDeps:
    """Build an AgentDeps with optional `extras` keyed arbitrarily.

    Replaces the per-package AgentDeps subclasses (summary/blocks/plotly
    each had a `.properties` field). Now any feature passes extras through
    the same constructor.
    """
    deps = AgentDeps(context=context, request=request)
    deps.extras = dict(extras)
    for key, value in extras.items():
        setattr(deps, key, value)
    return deps


class StubEnricher:
    """In-memory enricher for unit tests."""

    def __init__(self, name: str, system: str = "", user: str = ""):
        self.name = name
        self.description = f"stub:{name}"
        self._system = system
        self._user = user

    def system_prompt(self, deps):
        return self._system

    def user_prompt(self, deps):
        return self._user


class RaisingEnricher:
    """Enricher that raises in the chosen stage — for error-handling tests."""

    def __init__(self, name: str, stage: str = "system_prompt"):
        self.name = name
        self.description = f"raising:{name}"
        self._stage = stage

    def _raise(self):
        raise RuntimeError(f"boom from {self.name}")

    def system_prompt(self, deps):
        if self._stage == "system_prompt":
            self._raise()
        return ""

    def user_prompt(self, deps):
        if self._stage == "user_prompt":
            self._raise()
        return ""
