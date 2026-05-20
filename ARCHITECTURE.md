# EEA GenAI Architecture Reference

Context document for LLM-assisted development of the eea.genai.* packages.

## Package Map

```
eea.genai.core     — LLM client (pydantic_ai), agent executor, tools,
                     interfaces, control panel settings
eea.genai.summary  — Summary generation via agents
eea.genai.blocks   — Block generation/rewriting via agents
```

All packages live under `/develop/sources/` in the eea-website-backend repo.

## eea.genai.core

### Files

```
eea/genai/core/
  interfaces.py      — ILLMClient, IAgentTool, IEnricher, IAgentExecutor,
                        IAgentConfiguration, IGenAISettings, AgentTool,
                        Enricher, AgentConfiguration. IAgentSkill +
                        IAgentContextProvider are aliases to IEnricher
                        (and AgentSkill / AgentContextProvider to Enricher)
                        kept so existing ZCML/Python imports keep working.
  client.py         — PydanticAIClient (implements ILLMClient, uses pydantic_ai)
  agent.py          — PydanticAIAgentExecutor (implements IAgentExecutor), AgentDeps
  prompts.py        — Pure prompt composition: build_prompts(), collect_enricher_prompts()
  errors.py         — Typed exceptions: AgentDisabled, AgentNotFound,
                        AgentConfigInvalid, AgentExecutionFailed, EnricherFailed
  utils.py          — Shared helpers: Source, get_executor, batch_get_utilities,
                        site_scope context manager, array_summary
  testing.py        — make_deps() factory, StubEnricher, RaisingEnricher for unit tests
  tools.py          — Built-in agent tools (extract_blocks, memory, code_exec, fetch_url)
  mcp.py            — MCP server toolset construction
  settings.py       — plone.registry-backed settings + validate_agent_config()
  metaconfigure.py  — ZCML directive handlers for <genai:agentTool>,
                        <genai:agentSkill>, <genai:agentContextProvider>, <genai:agent>
  meta.zcml         — Declares directives in namespace http://namespaces.eea.europa.eu/genai
  configure.zcml    — Registers PydanticAIClient, PydanticAIAgentExecutor, and tools
  permissions.zcml  — Defines eea.genai.manage permission
  browser/          — Classic UI control panel (GenAI Settings)
  restapi/          — Volto controlpanel adapter (plone.restapi)
```

Registration of tools, enrichers, agents, and block knowledge is done
exclusively via ZCML directives. There is no separate decorator-based
registry — packages declare their utilities in their `configure.zcml`
and `metaconfigure.py` translates the XML into `provideUtility` calls.

### ILLMClient

Utility registered as singleton. Uses `pydantic_ai.Agent` for model-agnostic LLM access. Model/provider configured via control panel (falls back to env vars `LLM_MODEL`, `LLM_URL`, `LLM_API_KEY`).

Supported providers (configurable from control panel):
- `openai-compatible` (default) — LiteLLM proxy, vLLM, any OpenAI-compatible API
- `openai` — Direct OpenAI API
- `anthropic` — Direct Anthropic API (uses `ANTHROPIC_API_KEY` env var or `LLM_API_KEY`)
- `google` — Direct Google AI API (uses `GOOGLE_API_KEY` env var or `LLM_API_KEY`)
- `ollama` — Local Ollama instance

### IAgentTool

Named utility (name=tool_name). Provides a callable for pydantic_ai agent tool calling. Registered via `<genai:agentTool>` ZCML directive. Base class `AgentTool` available for subclassing.

```python
from eea.genai.core.interfaces import AgentTool

class SearchContentTool(AgentTool):
    name = "search_content"
    description = "Search the site catalog for content matching a query"

    def execute(self, ctx, query: str, limit: int = 5) -> str:
        # ctx is pydantic_ai RunContext, ctx.deps has dependencies
        catalog = getToolByName(ctx.deps["site"], "portal_catalog")
        results = catalog(SearchableText=query)[:limit]
        return json.dumps([brain.Title for brain in results])
```

### Built-in Tools

Registered in `configure.zcml` via `<genai:agentTool>`:

| Tool Name | Description |
|---|---|
| `extract_blocks` | Extract text content from Volto blocks on the current page |
| `memory` | Store/retrieve context from previous interactions (keyed by content UID) |
| `code_exec` | Execute Python code for data processing |
| `fetch_url` | Fetch and parse content from URLs |
| `get_plotly_template` | Fetch a predefined Plotly chart template by label (eea.plotly) |

### IEnricher

Named utility for dynamic prompt enrichment. Enrichers are reusable
capabilities agents reference by name; at run time each enricher
optionally contributes text to the system prompt and/or the user prompt.
Replaces the legacy `IAgentSkill` + `IAgentContextProvider` split — both
had identical signatures. The legacy names are kept as aliases so
existing ZCML directives (`<genai:agentSkill>`, `<genai:agentContextProvider>`)
and Python imports (`AgentSkill`, `AgentContextProvider`) continue to work.

Register via `<genai:agentSkill>` or `<genai:agentContextProvider>`
ZCML directives (interchangeable — both produce IEnricher utilities).
Base class `Enricher` available for subclassing.

```python
from eea.genai.core.interfaces import Enricher

class BlocksKnowledgeSkill(Enricher):
    name = "blocks_knowledge"
    description = "Adds available Volto block types to the system prompt"

    def system_prompt(self, deps):
        # deps has .context, .request, .site, plus any extras passed in
        return "Available block types:\n..."

    def user_prompt(self, deps):
        return ""  # this enricher only writes to the system prompt
```

In agent configs, enrichers are listed by name. The executor reads from
`"enrichers"` (preferred), and also from the legacy keys `"skills"` and
`"context_providers"` so old configs keep working:

```json
{"name": "summarizer", "enrichers": ["generic_metadata", "blocks"], ...}
```

### Registered Enrichers

| Enricher Name | Package | Description |
|---|---|---|
| `blocks_knowledge` | eea.genai.blocks | Adds available block type schemas to system prompt |
| `blocks` | eea.genai.blocks | Adds block text content of the current page to user prompt |
| `generic_metadata` | eea.genai.summary | Adds content metadata (title, description, language, geo/temporal) to user prompt |
| `plotly_knowledge` | eea.plotly | Adds Plotly.js chart structure knowledge to system prompt |
| `plotly_visualization` | eea.plotly | Adds the current chart's data + layout to user prompt |

### IAgentExecutor

Utility that runs pydantic_ai Agent with auto-discovered IAgentTool utilities.

```python
executor = queryUtility(IAgentExecutor)

# Simple run with tools
result = executor.run(
    system_prompt="You are a helpful assistant.",
    user_prompt="Find articles about climate change.",
    tools=["extract_blocks", "memory"],  # or None for all tools
    deps={"context": obj, "request": request},  # passed to tools via RunContext
    max_iterations=10,
)

# Run with named agent from control panel config
result = executor.run_with_agent(
    agent_name="summarizer",
    user_prompt="Generate a summary...",
    deps=AgentDeps(context=obj, request=request),
)
```

### AgentDeps

Single class shared by all feature packages. Feature-specific values
(e.g. `properties`, `data_sources`) are passed as `**extras` and are
accessible both as attributes and via the `.extras` dict. The legacy
per-package subclasses (`summary.AgentDeps`, `blocks.AgentDeps`,
`plotly.AgentDeps`) are gone.

```python
from eea.genai.core.agent import AgentDeps

deps = AgentDeps(context=context_obj, request=request, properties=props)
# In tools/enrichers via ctx.deps:
#   ctx.deps.context, ctx.deps.request, ctx.deps.site (auto-filled from getSite())
#   ctx.deps.properties                # attribute access
#   ctx.deps.extras["properties"]      # dict access
```

### ZCML Directives

```xml
<configure xmlns:genai="http://namespaces.eea.europa.eu/genai">
  <include package="eea.genai.core" file="meta.zcml" />

  <!-- Block knowledge registration -->
  <genai:blockKnowledge
      block_type="my_block"
      title="My Block"
      class=".knowledge.MyBlockKnowledge"
  />

  <!-- Agent tool registration -->
  <genai:agentTool
      name="my_tool"
      class=".tools.MyTool"
  />

  <!-- Enricher registration (skill / context provider — same thing now) -->
  <genai:agentSkill
      name="my_enricher"
      class=".skills.MyEnricher"
  />

  <!-- Default agent — points to a class that subclasses AgentConfiguration -->
  <genai:agent
      name="my_agent"
      class=".agents.MyAgent"
  />

</configure>
```

### Agent Auto-Registration

Packages declare default agents via `<genai:agent>` ZCML directive. These are auto-discovered by `get_agents_config()`. Registry-configured values (via control panel JSON) override ZCML defaults with the same name.

Content-type-specific agents use a naming convention: `base_agent:ContentType` (e.g. `summarizer:EEAFigure`). The lookup via `get_agent_for_content_type("summarizer", "EEAFigure")` tries `summarizer:EEAFigure` first, then falls back to `summarizer`.

### Enrichers (Skills / Context Providers)

Enrichers are reusable prompt-enrichment utilities that agents reference
by name. When `run_with_agent()` executes, it batch-discovers all
enrichers referenced by the agent config and calls their
`system_prompt(deps)` / `user_prompt(deps)` methods, appending the
non-empty results to the system and user prompts respectively.

From the control panel, agents reference enrichers in the JSON config:

```json
{
  "name": "my_agent",
  "system_prompt": "You are a helpful assistant.",
  "enrichers": ["blocks_knowledge", "generic_metadata"],
  "tools": ["extract_blocks"]
}
```

For backward compatibility, the executor also reads the legacy keys
`"skills"` and `"context_providers"` and merges them into the enricher
list, so older configs continue to work unchanged.

### Control Panel + Settings

`eea.genai.core` defines registry-backed settings (`IGenAISettings`) exposed via a classic UI configlet (`@@genai-controlpanel`) and via the REST controlpanel adapter (listed under `/@controlpanels`).

Settings fields:

| Field | Type | Description |
|---|---|---|
| `enabled` | Bool | Master switch for all GenAI features |
| `llm_provider` | Choice | Provider type: openai-compatible, openai, anthropic, google, ollama |
| `llm_model` | TextLine | Model name (falls back to `LLM_MODEL` env var) |
| `llm_api_url` | TextLine | API URL for openai-compatible/ollama/anthropic (falls back to `LLM_URL` env var) |
| `global_system_rules` | Text | Prepended to every agent's system prompt (global rules, tone, safety) |
| `agents_json` | JSONField | JSON array of agent definitions (overrides ZCML defaults by name) |
| `mcp_servers_json` | JSONField | JSON object of MCP server definitions, keyed by server name |

API keys are **never stored in the registry** — they come from env vars only (`LLM_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`).

Registry values override env vars. Empty registry values fall back to env vars.

### Agent Configuration

Agents are configured via `agents_json` in `IGenAISettings`:

Agent config fields:
- `name` (required) - Unique agent name
- `system_prompt` - System prompt for the agent
- `task_prompt` - Static task instructions appended to the user prompt as `## TASK`
- `tools` - List of tool names to make available (ZCA-registered, or `server/tool` for MCP)
- `enrichers` - List of enricher names (preferred). Legacy: `skills`, `context_providers` are still read
- `mcp_servers` - List of MCP server names whose full toolsets to attach
- `output_type` - Dotted path to pydantic model for structured output (optional)
- `max_iterations` - Max tool-calling iterations (default: 10)

`validate_agent_config(config)` in `eea.genai.core.settings` returns a
list of errors for any tools/enrichers/mcp_servers/output_type that are
not registered; an empty list means valid.

Example:
```json
[
  {
    "name": "summarizer",
    "system_prompt": "You are an expert content analyst...",
    "tools": ["extract_blocks", "memory"],
    "max_iterations": 10
  },
  {
    "name": "block_generator",
    "system_prompt": "You are a Plone content editor...",
    "tools": ["extract_blocks"],
    "output_type": "eea.genai.blocks.models.BlockGenerationResult"
  }
]
```

Content-type-specific agents use the naming convention `base:ContentType`:
```json
[
  {
    "name": "summarizer:EEAFigure",
    "system_prompt": "You are a visualization summarizer...",
    "tools": ["extract_blocks"],
    "max_iterations": 10
  }
]
```

## eea.genai.summary

### Files

```
eea/genai/summary/
  behaviors.py        — ILLMSummary behavior (allow_llm_summary, llm_summary)
  generate.py         — generate_summary_for(obj, request, properties=None)
  context_providers.py — GenericMetadataProvider enricher + extract_metadata_prompt()
  agents.py           — AgentConfiguration subclasses registered via ZCML
  agents.json         — Default agent definitions shipped with the package
  subscribers.py      — Event handlers wiring generate_summary_for to content changes
  interfaces.py       — IGenAISummaryLayer marker
  configure.zcml      — Behavior + enricher + agent + event subscriber registrations
  restapi/
    post.py           — LLMSummaryPost (@llm-summary), LLMSummaryBatchPost (@llm-summary-batch)
    configure.zcml    — Endpoint registration
```

### Summary Generation (Agent-based)

`generate_summary_for(obj, request, properties=None)`:

1. Look up agent via `get_agent_for_content_type("summarizer", portal_type)` — tries `summarizer:<type>` first, falls back to `summarizer`. Raises `AgentConfigInvalid` if neither is registered.
2. Call `get_executor().run_with_agent(agent_name, deps=AgentDeps(...))`.
3. Return `{"llm_summary": result}`. The subscriber stores it on the object.

The `GenericMetadataProvider` enricher (name `generic_metadata`) pulls
title, description, language, geographic coverage, and temporal coverage
from the object (or from `properties` if passed for in-progress edits)
and appends them to the user prompt.

## eea.genai.blocks

### Files

```
eea/genai/blocks/
  agents.py            — AgentConfiguration subclasses for the 4 block agents
  context_providers.py — BlocksContentProvider enricher (batched IBlockKnowledge lookup)
  skills.py            — BlocksKnowledgeSkill enricher (block-type descriptions to system prompt)
  models.py            — Pydantic models for structured LLM output
  knowledge.py         — Block knowledge classes (SlateBlockKnowledge, ImageBlockKnowledge, ColumnsBlockKnowledge, TabsBlockKnowledge)
  generate.py          — generate_blocks(), generate_block()
  rewrite.py           — rewrite_blocks(), rewrite_block()
  sanitizers.py        — Block sanitization utilities
  interfaces.py        — IBlockKnowledge, BlockKnowledge base class
  metaconfigure.py     — <genai:blockKnowledge> ZCML directive handler
  meta.zcml            — Declares the blockKnowledge directive
  configure.zcml       — Block knowledge + enricher + agent + tool registrations
  restapi/
    generate.py        — LLMGenerateBlocksPost
    rewrite.py         — LLMRewriteBlocksPost
    configure.zcml     — Endpoint registration
  tests/
    test_knowledge.py  — Unit tests for SlateBlockKnowledge.block_sanitizer + text_extractor
```

### Block Generation (Agent-based)

Both functions resolve the executor via `core.utils.get_executor()` and
call `run_with_agent()` with a unified `AgentDeps(context, request,
properties=properties)`:

```python
from eea.genai.blocks.generate import generate_blocks, generate_block

# Uses the "blocks_generator" agent (or its agents_json override)
generate_blocks(user_request, context=obj, request=req, properties=props)

# Uses the "blocks_generator_single" agent
generate_block(user_request, block_type="slate", context=obj, request=req)
```

### Block Rewriting (Agent-based)

```python
from eea.genai.blocks.rewrite import rewrite_blocks, rewrite_block

# Uses the "block_rewriter" agent
rewrite_blocks(blocks, style="more concise", context=obj, request=req)

# Uses the "block_rewriter_single" agent
rewrite_block(block, style=..., context=obj, request=req)
```

All four agents are declared via `<genai:agent>` in `configure.zcml` and
can be overridden by name from the control panel `agents_json`.

### Registered Enrichers

| Name | Source | Description |
|---|---|---|
| `blocks_knowledge` | skills.py | Adds the schema and example of every registered block type to the system prompt |
| `blocks` | context_providers.py | Adds the text content of the current page (extracted via `IBlockKnowledge.text_extractor`) to the user prompt |

### Pydantic Models

```python
class BlockGenerationResult(BaseModel):
    blocks: list[dict]            # Ordered list of complete block objects

class SingleBlockGenerationResult(BaseModel):
    block: dict                   # Single complete block object

class BlockRewriteResult(BaseModel):
    blocks: dict                  # {uuid: rewritten_block_data}

class SingleBlockRewriteResult(BaseModel):
    block: dict                   # Single rewritten block object
```

### REST Endpoints

`POST /@llm-generate-blocks` on ISiteRoot — permission: cmf.ModifyPortalContent

```json
{"prompt": "...", "context": "optional"}
// → {"blocks": {...}, "blocks_layout": {"items": [...]}}

{"prompt": "...", "block_type": "slate", "context": "optional"}
// or {"prompt": "...", "single": true}
// → {"block_id": "uuid", "block": {...}}
```

`POST /@llm-rewrite-blocks` on IBlocks — permission: cmf.ModifyPortalContent

```json
{"blocks": {...}, "style": "optional", "context": "optional"}
// → {"blocks": {...}}

{"block": {"@type": "...", ...}, "style": "optional", "context": "optional"}
// → {"block": {...}}
```

## Volto Block Data Structures

### Base pattern

```json
{
  "blocks": {
    "uuid": {"@type": "block_type", "...": "..."}
  },
  "blocks_layout": {
    "items": ["uuid"]
  }
}
```

### Slate block

```json
{
  "@type": "slate",
  "value": [
    {"type": "p", "children": [{"text": "Paragraph text"}]},
    {"type": "h2", "children": [{"text": "Heading"}]}
  ],
  "plaintext": "Paragraph text Heading"
}
```

**IMPORTANT**: Each slate block must contain EXACTLY ONE block element in the 'value' array.

### Registered Block Knowledge

The package ships with knowledge for these block types:

| Block Type | Title |
|---|---|
| `slate` | Rich Text (Slate) |
| `image` | Image |
| `columnsBlock` | Columns |
| `tabs_block` | Tabs |

## eea.plotly

### Files

```
eea/plotly/
  behaviors.py           — IPlotlyVisualization behavior
  prompts.py             — clean_layout(), IRRELEVANT_LAYOUT_KEYS
  context_providers.py   — PlotlyVisualizationProvider enricher (chart data → user prompt)
  skills.py              — PlotlyKnowledgeSkill enricher (Plotly structure → system prompt)
  tools.py               — GetPlotlyTemplateTool (fetch template by label)
  models.py              — ChartGenerationResult pydantic model
  agents.py              — AgentConfiguration subclasses
  generate.py            — generate_chart() helper function
  controlpanel.py        — IPlotlySettings (themes, templates)
  restapi/chart/post.py  — POST @llm-generate-chart endpoint
  io_csv.py, io_json.py  — Data input parsing (NOT part of the agent flow)
```

### GenAI Agents

| Agent | Description |
|---|---|
| `summarizer:visualization` | Chart interpretation — uses `generic_metadata` + `blocks` + `plotly_visualization` enrichers |
| `plotly_generator` | Full visualization content generation — uses `plotly_knowledge` enricher + `get_plotly_template` tool |

### Registered Enrichers

| Name | Description |
|---|---|
| `plotly_knowledge` | Adds Plotly.js JSON structure knowledge to the system prompt |
| `plotly_visualization` | Injects cleaned Plotly JSON (with large arrays summarized) into the user prompt |

### REST Endpoints

`POST /@llm-generate-chart` on IContentish — permission: cmf.ModifyPortalContent

```json
{"prompt": "Create a bar chart comparing...", "data_sources": {"Country": [...], "Value": [...]}}
// → {"title": "...", "description": "...", "visualization": {"data": [...], "layout": {...}},
//    "topics": [...], "temporal_coverage": [...], "geo_coverage": [...]}
```

## Patterns and Conventions

- All packages use Zope Component Architecture: interfaces, adapters, utilities, ZCML
- Namespace packages: `eea/__init__.py` and `eea/genai/__init__.py` use `pkg_resources.declare_namespace`
- REST endpoints use `plone.restapi.services.Service` subclass with `reply()` method
- Behaviors registered via `<plone:behavior>` in ZCML
- GenericSetup profiles in `profiles/default/` with `metadata.xml`
- Autoinclude via `[z3c.autoinclude.plugin] target = plone` in setup.py
- Permissions defined in `permissions.zcml`, role mapping in `profiles/default/rolemap.xml`

## TODO

- Improve control panel UI for agent configuration (currently raw JSON fields)
- Add web_search tool
- Run `validate_agent_config()` automatically when `agents_json` is saved in the control panel
