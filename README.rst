==============
eea.genai.core
==============
.. image:: https://ci.eionet.europa.eu/buildStatus/icon?job=volto/eea.genai.core/develop
  :target: https://ci.eionet.europa.eu/job/volto/job/eea.genai.core/job/develop/display/redirect
  :alt: Develop
.. image:: https://ci.eionet.europa.eu/buildStatus/icon?job=volto/eea.genai.core/master
  :target: https://ci.eionet.europa.eu/job/volto/job/eea.genai.core/job/master/display/redirect
  :alt: Master

Core LLM client utility for EEA GenAI packages.

Provides the ``ILLMClient`` utility and ``ILLMPromptBuilder`` interface
for building reusable LLM integrations in Plone.

.. contents::

Main features
=============

1. LLM client utility wrapping ``litellm`` for OpenAI-compatible APIs
2. ``ILLMClient`` interface for sending prompts to LLMs
3. ``ILLMPromptBuilder`` interface for content-type-specific prompt builders
4. ``eea.genai.manage`` permission for administrative operations

Install
=======

- Add ``eea.genai.core`` to your ``requirements.txt``

Environment variables
=====================

- ``LLM_MODEL`` - LLM model identifier (required)
- ``LLM_URL`` - LLM API base URL (optional)
- ``LLM_API_KEY`` - LLM API key (optional)

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
