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
  interfaces.py      — ILLMClient, IBlockKnowledge, IBlockTextExtractor,
                        IAgentTool, IAgentSkill, IAgentExecutor, IAgentConfiguration,
                        IGenAISettings, AgentTool, AgentSkill, BlockKnowledge
  client.py         — PydanticAIClient (implements ILLMClient, uses pydantic_ai)
  agent.py          — PydanticAIAgentExecutor (implements IAgentExecutor), AgentDeps
  tools.py          — Built-in agent tools (extract_blocks, memory, code_exec, fetch_url)
  prompts.py        — Global system rules + per-feature overrides helpers
  settings.py       — plone.registry-backed settings helpers + agent config helpers
  metaconfigure.py  — ZCML directive handlers for <genai:blockKnowledge>, <genai:agentTool>,
                        <genai:agentSkill>, <genai:agent>
  meta.zcml         — Declares directives in namespace http://namespaces.eea.europa.eu/genai
  configure.zcml    — Registers PydanticAIClient, PydanticAIAgentExecutor, and tools
  permissions.zcml  — Defines eea.genai.manage permission
  browser/          — Classic UI control panel (GenAI Settings)
  restapi/          — Volto controlpanel adapter (plone.restapi)
```

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

### IAgentSkill

Named utility (name=skill_name) for dynamic prompt enrichment. Skills are reusable capabilities that agents reference by name. When an agent runs, its skills are invoked to dynamically contribute to the system prompt and/or user prompt. Registered via `<genai:agentSkill>` ZCML directive. Base class `AgentSkill` available for subclassing.

```python
from eea.genai.core.interfaces import AgentSkill

class BlocksKnowledgeSkill(AgentSkill):
    name = "blocks_knowledge"
    description = "Adds available Volto block types to the system prompt"

    def system_prompt(self, deps):
        # deps has .context, .request, .site
        return "Available block types:\n..."

    def user_prompt(self, deps):
        return ""  # This skill only enriches system prompt
```

### Registered Skills

| Skill Name | Package | Description |
|---|---|---|
| `blocks_knowledge` | eea.genai.blocks | Adds available block type schemas to system prompt |
| `metadata_extraction` | eea.genai.summary | Adds content metadata (title, description, geo/temporal) to user prompt |
| `blocks_extraction` | eea.genai.summary | Adds block text content to user prompt |
| `plotly_knowledge` | eea.plotly | Adds Plotly.js chart structure knowledge, available templates, and active theme to system prompt |

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

Dependencies passed to agent tools via RunContext:

```python
from eea.genai.core.agent import AgentDeps

deps = AgentDeps(context=context_obj, request=request, site=portal)
# Available in tools via ctx.deps.context, ctx.deps.request, ctx.deps.site
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

  <!-- Agent skill registration -->
  <genai:agentSkill
      name="my_skill"
      class=".skills.MySkill"
  />

  <!-- Default agent with skills -->
  <genai:agent
      name="my_agent"
      system_prompt="My agent behavior"
      user_prompt="My agent task"
      skills="blocks_knowledge metadata_extraction"
      tools="extract_blocks"
      output_type="my.package.models.MyResult"
      max_iterations="10"
  />

</configure>
```

### Agent Auto-Registration

Packages declare default agents via `<genai:agent>` ZCML directive. These are auto-discovered by `get_agents_config()`. Registry-configured values (via control panel JSON) override ZCML defaults with the same name.

Content-type-specific agents use a naming convention: `base_agent:ContentType` (e.g. `summarizer:EEAFigure`). The lookup via `get_agent_for_content_type("summarizer", "EEAFigure")` tries `summarizer:EEAFigure` first, then falls back to `summarizer`.

### Skills

Skills are reusable prompt-enrichment capabilities that agents reference by name. When `run_with_agent()` executes, it discovers the agent's skills and calls their `system_prompt(deps)` / `user_prompt(deps)` methods, appending the results to the respective prompts.

From the control panel, agents reference skills in the JSON config:
```json
{
  "name": "my_agent",
  "system_prompt": "You are a helpful assistant.",
  "skills": ["blocks_knowledge", "metadata_extraction"],
  "tools": ["extract_blocks"]
}
```

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
| `feature_settings_json` | Text | JSON object for feature-specific configuration |
| `agents_json` | Text | JSON array of agent definitions |

API keys are **never stored in the registry** — they come from env vars only (`LLM_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`).

Registry values override env vars. Empty registry values fall back to env vars.

### Agent Configuration

Agents are configured via `agents_json` in `IGenAISettings`:

Agent config fields:
- `name` (required) - Unique agent name
- `system_prompt` - System prompt for the agent
- `tools` - List of tool names to make available
- `output_type` - Dotted path to pydantic model for structured output (optional)
- `max_iterations` - Max tool-calling iterations (default: 10)

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

### Feature Settings Keys

Used in `feature_settings_json`:

| Key | Description |
|---|---|
| `genai.blocks.generate.agent` | Agent name for block generation |
| `genai.blocks.generate_single.agent` | Agent name for single block generation |
| `genai.blocks.rewrite.agent` | Agent name for block rewriting |
| `genai.blocks.rewrite.default_style` | Default rewriting style |

## eea.genai.summary

### Files

```
eea/genai/summary/
  behaviors.py       — ILLMSummary behavior (allow_llm_summary bool, llm_summary text)
  prompts.py        — Reference prompts for agent config, extract_metadata_prompt(), extract_blocks_prompt()
  subscribers.py   — generate_summary_for() using agents
  interfaces.py    — IGenAISummaryLayer marker
  configure.zcml   — Behavior registration, event subscriber
  restapi/
    post.py        — LLMSummaryPost (@llm-summary), LLMSummaryBatchPost (@llm-summary-batch)
    configure.zcml — Endpoint registration
```

### Summary Generation (Agent-based)

Uses `IAgentExecutor.run_with_agent()` based on agent naming convention:

1. Look up agent via `get_agent_for_content_type("summarizer", portal_type)` — tries `summarizer:<type>` first, falls back to `summarizer`
2. Run agent with `executor.run_with_agent(agent_name, deps=deps)`
3. Store result in `llm_summary` field

### Reference Prompts (prompts.py)

Prompts are kept for reference when configuring agents:

- `SUMMARY_SYSTEM_PROMPT` - Default summary system prompt
- `extract_metadata_prompt(context)` - Extract EEA metadata fields
- `extract_blocks_prompt(context)` - Extract text from Volto blocks

## eea.genai.blocks

### Files

```
eea/genai/blocks/
  text_extractor.py  — BlockTextExtractor utility, _iter_blocks_ordered()
  models.py          — Pydantic models for structured LLM output
  prompts.py         — Reference prompts for agent config
  generate.py        — generate_blocks(), generate_block() using agents
  rewrite.py         — rewrite_blocks(), rewrite_block() using agents
  knowledge.py       — Block knowledge classes (SlateBlockKnowledge, etc.)
  sanitizers.py      — Block sanitization utilities
  configure.zcml     — Block knowledge registration, tool registrations
  restapi/
    generate.py      — LLMGenerateBlocksPost
    rewrite.py       — LLMRewriteBlocksPost
    configure.zcml   — Endpoint registration
```

### Block Generation (Agent-based)

Uses agents configured in feature settings:

```python
# Uses agent from feature_settings_json key "genai.blocks.generate.agent"
generate_blocks(user_request, page_context=..., context=obj, request=req)

# Uses agent from feature_settings_json key "genai.blocks.generate_single.agent"
generate_block(user_request, block_type=..., page_context=..., context=obj, request=req)
```

### Block Rewriting (Agent-based)

Uses agents configured in feature settings:

```python
# Uses agent from feature_settings_json key "genai.blocks.rewrite.agent"
rewrite_blocks(blocks, style=..., page_context=..., context=obj, request=req)

# Uses agent from feature_settings_json key "genai.blocks.rewrite_single.agent"
rewrite_block(block, style=..., page_context=..., context=obj, request=req)
```

### Reference Prompts (prompts.py)

Prompts are kept for reference when configuring agents:

- `BLOCK_GEN_SYSTEM_PROMPT` - Base system prompt for block generation
- `BLOCK_GEN_USER_PROMPT_TEMPLATE` - User prompt template
- `get_block_types_description()` - Generates block type info from IBlockKnowledge
- `REWRITE_SYSTEM_PROMPT` - Base system prompt for block rewriting

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
  prompts.py             — Reference prompts, clean_layout(), IRRELEVANT_LAYOUT_KEYS
  llm_prompt.py          — Backward compatibility re-exports
  context_providers.py   — PlotlyVisualizationProvider (chart data → user prompt)
  skills.py              — PlotlyKnowledgeSkill (Plotly structure + templates → system prompt)
  tools.py               — GetPlotlyTemplateTool (fetch template by label)
  models.py              — ChartGenerationResult pydantic model
  generate.py            — generate_chart() helper function
  controlpanel.py        — IPlotlySettings (themes, templates)
  restapi/chart/post.py  — POST @llm-generate-chart endpoint
```

### GenAI Agents

| Agent | Description |
|---|---|
| `summarizer:visualization` | Chart interpretation — uses generic_metadata + blocks + plotly_visualization context |
| `plotly_generator` | Full visualization content generation (metadata + chart) — uses plotly_knowledge skill + get_plotly_template tool |

### Context Providers

| Name | Description |
|---|---|
| `plotly_visualization` | Injects cleaned Plotly JSON (with truncated large arrays) into user prompt |

### Reference Prompts (prompts.py)

- `PLOTLY_SYSTEM_PROMPT` - System prompt for chart summarization
- `clean_layout(layout)` - Remove cosmetic layout keys

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


BlocksContentProvider

BlocksKnowledgeSkill
