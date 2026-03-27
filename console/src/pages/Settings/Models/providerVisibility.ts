import type { ProviderInfo } from "../../../api/types/provider";

export type ProviderReadiness = "ready" | "no-models" | "not-configured";

export function getProviderModelCount(provider: ProviderInfo): number {
  return (provider.models?.length ?? 0) + (provider.extra_models?.length ?? 0);
}

export function isProviderConfigured(provider: ProviderInfo): boolean {
  if (provider.is_local) return true;
  if (provider.is_custom && provider.base_url) return true;
  if (provider.require_api_key === false) return true;
  return Boolean(provider.api_key);
}

export function isProviderReady(provider: ProviderInfo): boolean {
  return isProviderConfigured(provider) && getProviderModelCount(provider) > 0;
}

export function getProviderReadiness(
  provider: ProviderInfo,
): ProviderReadiness {
  if (!isProviderConfigured(provider)) {
    return "not-configured";
  }

  if (getProviderModelCount(provider) === 0) {
    return "no-models";
  }

  return "ready";
}

export function shouldShowProvider(
  provider: ProviderInfo,
  showAllProviders: boolean,
): boolean {
  if (showAllProviders) return true;
  return isProviderReady(provider);
}

export function filterProvidersByVisibility(
  providers: ProviderInfo[],
  showAllProviders: boolean,
): ProviderInfo[] {
  return providers.filter((provider) =>
    shouldShowProvider(provider, showAllProviders),
  );
}
