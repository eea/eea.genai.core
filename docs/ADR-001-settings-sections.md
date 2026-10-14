# ADR 001: Package-contributed GenAI settings and SSR-safe flags

Status: accepted by owner, 2026-10-14

## Context

Image AI needs its own enable switch and generation limits in the existing
GenAI controlpanel. Image-specific schema definitions belong in
`eea.genai.summary`, not core. Editors need the feature flags before SSR
rendering, following the theme's existing header-settings extender lifecycle.
The full administrative configuration is inappropriate for public SSR HTML.

## Decision

Register named `IGenAISettingsSection` utilities through standard ZCML. Each
utility provides its schema and an explicit public feature payload. Compose
schemas for both classic and REST controlpanels, reject duplicate field names,
and use the existing core registry prefix for all contributed fields.
Packages install their own records under that prefix in `registry.xml`.

`GET @genai-settings` returns only the master flag and allowlisted package
payloads. The theme loads it through an SSR async-props extender and consumes
`state.reduxAsyncConnect.genAISettings`; no separate reducer, widget fetches,
or process-global frontend configuration mutation. Frontend settings refresh
on a full page load. Generation APIs independently enforce current flags.

## Consequences

Core has no dependency on summary or Image-specific fields. Existing core
registry keys are unchanged. Standard registry controlpanel serialization and
saving remain reusable without a per-package serializer/deserializer.

Contributed field names must be globally unique within this controlpanel.
Schemas are package-owned but their registry keys share the core namespace.
An owner must import new registry records on existing sites before opening the
extended controlpanel. There are no automatic upgrades, profile version bumps,
or registry writes during public GET requests. Missing Image records use safe
runtime defaults. Existing core installation remains a prerequisite.

Feature providers are trusted package code responsible for allowlisting public
values. Only capability flags are exposed for Image AI; its generation limits
remain server-side.
