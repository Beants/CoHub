# Model Provider Visibility Design

- Date: 2026-03-26
- Status: Approved in conversation
- Scope: Hide not-ready model providers by default in the console, with a user-controlled toggle to reveal them

## Summary

The model settings page currently renders every provider returned by the backend. In the current workspace this means 18 providers appear, while only 2 are actually ready for use. The result is noisy and makes the page look broken even though the active setup is valid.

This design keeps the backend provider list unchanged and adds a frontend-only visibility filter. By default, the page shows only ready providers. A small toggle lets the user reveal all providers, including not-configured and no-model entries, whenever they need to inspect or configure them.

## Goals

- Reduce noise on the model settings page for users who only care about ready providers.
- Preserve access to not-ready providers without removing them from the product.
- Keep the change isolated to the console frontend.
- Reuse the existing readiness rules already implied by provider cards.

## Non-goals

- No backend API changes.
- No provider deletion or migration.
- No changes to provider persistence or active model selection.
- No change to provider readiness semantics.

## Design

### 1. Default visibility behavior

Add a page-level toggle on the model settings page.

- Default state: off
- Off behavior: show only ready providers
- On behavior: show all providers

This keeps the default page focused while still allowing a one-click escape hatch for configuration and debugging.

### 2. Readiness calculation

Define a shared page-level helper that mirrors the current UI logic:

- ready: provider is configured and has at least one model
- not ready, no models: provider is configured but has zero models
- not ready, not configured: provider is missing required configuration

Filtering uses only the `ready` branch. The existing card status text remains unchanged.

### 3. Filtering scope

Filtering happens before provider grouping and rendering.

- When the toggle is off, both regular and embedded/local sections receive only ready providers.
- When the toggle is on, both sections receive the full provider list.

This keeps behavior consistent across remote providers, embedded local providers, Ollama, and LM Studio.

### 4. UI placement and copy

Place the toggle in the provider section header area, beside the existing "Add Provider" action, so the control is visible without changing the card layout.

Add concise i18n strings for:

- toggle label
- short helper text describing ready-only vs all-providers behavior

No new modal or settings persistence is needed in this iteration.

## Files

- Modify `console/src/pages/Settings/Models/index.tsx`
- Modify `console/src/pages/Settings/Models/index.module.less`
- Modify `console/src/locales/zh.json`
- Modify `console/src/locales/en.json`
- Modify `console/src/locales/ja.json`
- Modify `console/src/locales/ru.json`

## Verification

- Load the model settings page with the toggle off and confirm only ready providers render.
- Turn the toggle on and confirm all providers render again.
- Confirm the active provider/model area still works.
- Confirm provider settings, model management, and add-provider flows still open normally.
- Confirm empty local providers remain hidden by default and reappear when the toggle is enabled.
