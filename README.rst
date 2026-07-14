==============
eea.genai.core
==============
.. image:: https://ci.eionet.europa.eu/buildStatus/icon?job=eea/eea.genai.core/develop
  :target: https://ci.eionet.europa.eu/job/eea/job/eea.genai.core/job/develop/display/redirect
  :alt: Develop
.. image:: https://ci.eionet.europa.eu/buildStatus/icon?job=eea/eea.genai.core/master
  :target: https://ci.eionet.europa.eu/job/eea/job/eea.genai.core/job/master/display/redirect
  :alt: Master

Core agentic LLM layer for EEA GenAI packages.

Provides the multi-provider LLM client, the agent executor (built on
``pydantic-ai``), the unified enricher interface, MCP toolset integration,
and the control-panel-backed settings shared by all ``eea.genai.*``
packages.

.. contents::

Main features
=============

1. ``ILLMClient`` utility — multi-provider model wrapper. Supported
   providers: ``openai-compatible`` (LiteLLM, vLLM, any OpenAI API),
   ``openai``, ``anthropic``, ``google``, ``ollama``. Configured via
   control panel or env vars (``LLM_MODEL``, ``LLM_URL``,
   ``LLM_API_KEY``).
2. ``IAgentExecutor`` utility — runs a ``pydantic_ai.Agent`` loop with
   ZCA-discovered tools, MCP toolsets, structured output, and the
   enricher pipeline.
3. ``IEnricher`` named utility interface — single abstraction for
   reusable system/user prompt fragments. Replaces the previous
   ``IAgentSkill`` + ``IAgentContextProvider`` split (both kept as
   aliases).
4. ``IAgentTool`` named utility interface — tool callables exposed to
   the LLM via ``pydantic_ai`` tool calling. Thread-safe Plone site
   restoration via the ``site_scope`` context manager.
5. ``IAgentConfiguration`` named utility interface + base class —
   ship default agents from Python via ZCML; the control panel
   ``agents_json`` overrides them by name.
6. Pure-function prompt composition (``core.prompts.build_prompts``)
   testable without Plone bootstrap.
7. MCP server integration with ``${VAR}`` and ``${VAR:-default}`` env
   expansion, filtered tool refs (``server/tool``) and full toolset
   inclusion via ``mcp_servers``.
8. Typed exceptions (``AgentDisabled``, ``AgentNotFound``,
   ``AgentConfigInvalid``, ``AgentExecutionFailed``, ``EnricherFailed``)
   instead of bare ``RuntimeError``.
9. ``validate_agent_config(config)`` — fail-fast validation of tool,
   enricher, MCP server, and output-type references at config load time.
10. Built-in tools: ``extract_blocks``, ``memory``, ``code_exec``,
    ``fetch_url``.
11. ``eea.genai.manage`` permission for administrative operations.

Install
=======

- Add ``eea.genai.core`` to your ``requirements.txt``.
- Install the GenericSetup profile to enable the control panel.

Environment variables
=====================

- ``LLM_MODEL`` — model identifier (e.g. ``gpt-4o``, ``claude-sonnet-4-6``,
  ``llama3``). Falls back here if the registry value is empty.
- ``LLM_URL`` — base URL for OpenAI-compatible or Ollama endpoints
  (e.g. ``http://localhost:4000/v1``). Not used for direct
  OpenAI/Anthropic/Google providers.
- ``LLM_API_KEY`` — API key for the configured provider.
- ``ANTHROPIC_API_KEY``, ``GOOGLE_API_KEY`` — provider-specific
  overrides for direct provider mode.

API keys are **never stored in the registry**.

Quick start
===========

Define an enricher::

    from eea.genai.core.interfaces import Enricher

    class MyContextEnricher(Enricher):
        description = "Adds dataset summary to the user prompt"

        def user_prompt(self, deps):
            return f"Active dataset: {deps.context.title}"

Register it via ZCML::

    <genai:agentSkill name="my_context" class=".enrichers.MyContextEnricher" />

Define an agent::

    from eea.genai.core.interfaces import AgentConfiguration

    class MyAgent(AgentConfiguration):
        system_prompt = "You are an analyst."
        task_prompt = "Produce a one-paragraph briefing."
        enrichers = ["my_context", "generic_metadata"]
        tools = ["fetch_url"]
        output_type = "my.package.models.Briefing"
        max_iterations = 5

Register it::

    <genai:agent name="briefing" class=".agents.MyAgent" />

Run it::

    from eea.genai.core.agent import AgentDeps
    from eea.genai.core.utils import get_executor

    result = get_executor().run_with_agent(
        "briefing",
        user_prompt="Brief me on regional air quality.",
        deps=AgentDeps(context=obj, request=request),
    )

Control-panel ``agents_json`` overrides Python-defined agents by name
without code changes.

See ``ARCHITECTURE.md`` in this package for the full reference.

Copyright and license
=====================

The Initial Owner of the Original Code is European Environment Agency (EEA).
All Rights Reserved.

All contributions to this package are property of their respective authors,
and are covered by the same license.

The eea.genai.core is free software: you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by the Free
Software Foundation, either version 2 of the License, or (at your option) any
later version.

Secret Scanning
===============

This repository uses the Betterleaks GitHub Action to scan the current
repository content on every push and pull request. The scan uses the rules in
``.gitleaks.toml`` and uploads a ``betterleaks-report`` artifact when a finding
is detected.

If the optional SMTP secrets are configured, failed scans also send an email to
the last commit committer. The workflow expects these repository or
organization secrets:

- ``SMTP_URL``
- ``SMTP_PORT`` (optional, defaults to ``25``)
- ``SMTP_EMAIL``
- ``SMTP_PASSWORD`` (optional if the SMTP server does not require authentication)

Port ``465`` is sent with direct TLS; other ports use the default SMTP
handshake. The email includes a short finding summary from the redacted
Betterleaks report, including the redacted matched line from each finding.

There are three common outcomes:

1. Everything is OK. The ``Betterleaks / Scan for secrets`` check is green and
   no action is needed. Regular references to runtime values are OK, for example::

     token_from_cookie = request.cookies.get("auth_token")

2. A real secret was found. The check is red and the workflow log asks you to
   download the ``betterleaks-report`` artifact. Open the artifact from the
   GitHub Actions run and check the reported file, line and rule. Remove the
   committed value, move it to the proper secret store, and rotate it if it was
   exposed. A report entry looks like this::

     {
       "RuleID": "secret-literal-assignment",
       "File": "src/config.py",
       "StartLine": 12,
       "Secret": "[REDACTED]"
     }

3. The finding is a false positive. Keep the value only if it is clearly not
   sensitive, such as a test fixture, placeholder, or public example. Add
   ``betterleaks:allow`` on the same line and include a short explanation in the
   pull request::

     test_password = "admin"  #betterleaks:allow

Do not add ``betterleaks:allow`` to real credentials.
