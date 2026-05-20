"""Pure prompt composition.

Splits prompt-building out of the executor so it can be tested directly
without ZCA or Plone bootstrap. Discovery (utility lookup) stays in the
executor; this module only composes already-resolved enrichers.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

logger = logging.getLogger("eea.genai.core")


def collect_enricher_prompts(
    enrichers: Iterable[Any],
    deps: Any,
    *,
    swallow_errors: bool = True,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Run each enricher's system_prompt and user_prompt callbacks.

    Args:
        enrichers: Iterable of enricher instances (must expose ``name``,
            ``system_prompt(deps)``, ``user_prompt(deps)``).
        deps: Whatever the enrichers expect — passed through unchanged.
        swallow_errors: If True (legacy behavior), failures are logged and
            ignored. If False, the underlying exception is re-raised wrapped
            in EnricherFailed.

    Returns:
        (system_parts, user_parts) where system_parts is a list of
        (name, text) tuples so callers can format per-enricher headings,
        and user_parts is a flat list of texts.
    """
    from eea.genai.core.errors import EnricherFailed

    system_parts: list[tuple[str, str]] = []
    user_parts: list[str] = []

    for enricher in enrichers:
        name = getattr(enricher, "name", enricher.__class__.__name__)

        try:
            system_text = enricher.system_prompt(deps)
        except Exception as exc:
            if swallow_errors:
                logger.exception("Enricher '%s' system_prompt() failed", name)
                system_text = ""
            else:
                raise EnricherFailed(name, "system_prompt", exc) from exc
        if system_text:
            system_parts.append((name, system_text))

        try:
            user_text = enricher.user_prompt(deps)
        except Exception as exc:
            if swallow_errors:
                logger.exception("Enricher '%s' user_prompt() failed", name)
                user_text = ""
            else:
                raise EnricherFailed(name, "user_prompt", exc) from exc
        if user_text:
            user_parts.append(user_text)

    return system_parts, user_parts


def build_prompts(
    system_prompt: str,
    task_prompt: str,
    user_prompt: str,
    enrichers: Iterable[Any],
    tools: Iterable[Any] = (),
    deps: Any = None,
) -> tuple[str, str]:
    """Compose the final system and user prompts from parts.

    Layout::

        SYSTEM = system_prompt
                 + (## ENRICHERS sections with per-enricher subheadings)
                 + (## TOOLS sections with per-tool descriptions)

        USER   = ## CONTEXT (user-prompt fragments from enrichers)
                 + ## TASK (task_prompt)
                 + ## USER REQUEST (user_prompt)

    Pure function: no ZCA, no Plone, no I/O.
    """
    enricher_system, enricher_user = collect_enricher_prompts(enrichers, deps)

    tool_descriptions: list[tuple[str, str]] = []
    for tool in tools:
        name = getattr(tool, "name", tool.__class__.__name__)
        text = ""
        try:
            text = tool.system_prompt(deps)
        except AttributeError:
            text = getattr(tool, "description", "") or ""
        except Exception:
            logger.exception("Tool '%s' system_prompt() failed", name)
        if text:
            tool_descriptions.append((name, text))

    system_chunks: list[str] = []
    if system_prompt:
        system_chunks.append(system_prompt)
    if enricher_system:
        body = "\n\n".join(f"### {name}\n\n{text}" for name, text in enricher_system)
        system_chunks.append("## ENRICHERS\n\n" + body)
    if tool_descriptions:
        body = "\n\n".join(f"### {name}\n\n{text}" for name, text in tool_descriptions)
        system_chunks.append("## TOOLS\n\n" + body)
    final_system = "\n\n".join(system_chunks)

    user_chunks: list[str] = []
    if enricher_user:
        user_chunks.append("## CONTEXT\n\n" + "\n\n".join(enricher_user))
    if task_prompt:
        user_chunks.append("## TASK\n\n" + task_prompt)
    if user_prompt:
        user_chunks.append("## USER REQUEST\n\n" + user_prompt)
    final_user = "\n\n".join(user_chunks)

    return final_system, final_user
