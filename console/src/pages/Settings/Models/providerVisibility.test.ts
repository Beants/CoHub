import assert from "node:assert/strict";
import test from "node:test";

import type { ProviderInfo } from "../../../api/types/provider.ts";
import {
  getProviderReadiness,
  shouldShowProvider,
} from "./providerVisibility.ts";

function createProvider(
  overrides: Partial<ProviderInfo> = {},
): ProviderInfo {
  return {
    id: "openai",
    name: "OpenAI",
    api_key_prefix: "sk-",
    chat_model: "OpenAIChatModel",
    models: [
      {
        id: "gpt-5",
        name: "GPT-5",
        supports_multimodal: false,
        supports_image: false,
        supports_video: false,
      },
    ],
    extra_models: [],
    is_custom: false,
    is_local: false,
    support_model_discovery: false,
    support_connection_check: true,
    freeze_url: true,
    require_api_key: true,
    api_key: "sk-test",
    base_url: "https://api.openai.com/v1",
    generate_kwargs: {},
    ...overrides,
  };
}

test("marks configured provider with models as ready", () => {
  const provider = createProvider();

  assert.equal(getProviderReadiness(provider), "ready");
  assert.equal(shouldShowProvider(provider, false), true);
});

test("marks configured provider without models as not ready", () => {
  const provider = createProvider({
    models: [],
    extra_models: [],
  });

  assert.equal(getProviderReadiness(provider), "no-models");
  assert.equal(shouldShowProvider(provider, false), false);
});

test("marks provider without required credentials as not configured", () => {
  const provider = createProvider({
    api_key: "",
  });

  assert.equal(getProviderReadiness(provider), "not-configured");
  assert.equal(shouldShowProvider(provider, false), false);
});

test("shows all providers when the toggle is enabled", () => {
  const provider = createProvider({
    api_key: "",
    models: [],
    extra_models: [],
  });

  assert.equal(shouldShowProvider(provider, true), true);
});

test("treats local providers without downloaded models as configured", () => {
  const provider = createProvider({
    id: "llamacpp",
    name: "llama.cpp (Local)",
    is_local: true,
    require_api_key: false,
    api_key: "",
    base_url: "",
    models: [],
    extra_models: [],
  });

  assert.equal(getProviderReadiness(provider), "no-models");
});
