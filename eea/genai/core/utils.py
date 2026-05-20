"""Shared utilities for eea.genai.core and feature packages.

Anything that was duplicated across summary / blocks / plotly lives here.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any, Iterable

from zope.component import getUtilitiesFor, queryUtility
from zope.component.hooks import getSite, setSite

from eea.genai.core.errors import AgentExecutionFailed
from eea.genai.core.interfaces import IAgentExecutor

logger = logging.getLogger("eea.genai.core")


class Source:
    """Attribute-style accessor: properties dict overrides object attributes.

    Used by enrichers so that in-progress edit-form values are reflected
    in prompts instead of the persisted object state. Previously duplicated
    as ``_Source`` in summary, blocks, and plotly context_providers.

    Usage::

        source = Source(content_obj, properties_dict)
        title = source.title        # from properties if present, else obj.title

    Returns None for missing attributes (matches legacy behavior).
    """

    def __init__(self, context: Any, properties: dict | None = None):
        # Bypass __getattr__ on assignment.
        object.__setattr__(self, "_context", context)
        object.__setattr__(self, "_properties", properties or {})

    def __getattr__(self, name: str) -> Any:
        props = object.__getattribute__(self, "_properties")
        if name in props:
            return props[name]
        ctx = object.__getattribute__(self, "_context")
        return getattr(ctx, name, None)


def get_executor() -> IAgentExecutor:
    """Return the registered IAgentExecutor utility.

    Replaces the ``_get_agent_executor`` helper duplicated in
    blocks/generate.py, blocks/rewrite.py, plotly/generate.py.
    """
    executor = queryUtility(IAgentExecutor)
    if executor is None:
        raise AgentExecutionFailed("No IAgentExecutor utility registered")
    return executor


def batch_get_utilities(
    interface, names: Iterable[str] | None = None
) -> dict[str, Any]:
    """Return all named utilities for `interface` as a dict in one ZCA pass.

    If `names` is given, restrict the result to those names (preserves their order
    in iteration via the input list — useful for ordered enricher application).
    """
    if names is None:
        return dict(getUtilitiesFor(interface))
    requested = list(names)
    all_utils = dict(getUtilitiesFor(interface))
    return {n: all_utils[n] for n in requested if n in all_utils}


@contextlib.contextmanager
def site_scope(site):
    """Temporarily set the Zope thread-local site, restoring the previous on exit.

    pydantic_ai runs sync tools in a thread pool; the worker thread doesn't
    inherit the request's site. Wrap tool callables (or any code that uses
    plone.api) in `with site_scope(deps.site): ...`.
    """
    previous = getSite()
    if site is not None:
        setSite(site)
    try:
        yield
    finally:
        setSite(previous)


def array_summary(values: list) -> dict:
    """Single-pass summary of a numeric/categorical array.

    Returns:
        dict with keys: count, unique, min, max, sample (first 5 distinct values).

    Previously plotly/context_providers.py iterated values 3× for the
    same information.
    """
    count = 0
    unique: set = set()
    sample: list = []
    minimum: Any = None
    maximum: Any = None
    has_numeric = False

    for v in values:
        count += 1
        try:
            hv = v
            if hv not in unique:
                unique.add(hv)
                if len(sample) < 5:
                    sample.append(hv)
        except TypeError:
            # Unhashable — count but skip uniqueness tracking
            if len(sample) < 5:
                sample.append(v)

        if isinstance(v, (int, float)) and not isinstance(v, bool):
            has_numeric = True
            if minimum is None or v < minimum:
                minimum = v
            if maximum is None or v > maximum:
                maximum = v

    return {
        "count": count,
        "unique": len(unique) if unique else count,
        "min": minimum if has_numeric else None,
        "max": maximum if has_numeric else None,
        "sample": sample,
    }
