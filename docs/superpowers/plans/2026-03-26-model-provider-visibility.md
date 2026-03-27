# Model Provider Visibility Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hide not-ready model providers by default on the console models page, while letting the user reveal all providers with a toggle.

**Architecture:** Keep backend provider APIs unchanged and implement visibility entirely in the console. Add a small page-level visibility helper plus a toggle in the models page header so the filtering logic stays explicit and reusable without changing provider card behavior.

**Tech Stack:** React 18, TypeScript, Vite, existing CoPaw i18n JSON locale files, Less modules

---

> Note: `console/` does not currently have a dedicated frontend unit-test harness. For this UI-only change, verification stays focused on `npm run lint`, `npm run build`, and manual page checks instead of adding new test infrastructure just for this toggle.

## Chunk 1: Visibility Logic

### Task 1: Extract provider readiness and visibility helpers

**Files:**
- Create: `console/src/pages/Settings/Models/providerVisibility.ts`
- Modify: `console/src/pages/Settings/Models/index.tsx`

- [ ] **Step 1: Add a focused visibility helper module**

```ts
import type { ProviderInfo } from "../../../api/types/provider";

export function getProviderReadiness(provider: ProviderInfo) {
  const totalModels = provider.models.length + provider.extra_models.length;
  const isConfigured =
    provider.is_local ||
    (provider.is_custom && Boolean(provider.base_url)) ||
    provider.require_api_key === false ||
    (provider.require_api_key && Boolean(provider.api_key));

  return {
    isConfigured,
    hasModels: totalModels > 0,
    isReady: isConfigured && totalModels > 0,
  };
}

export function shouldShowProvider(
  provider: ProviderInfo,
  showNotReadyProviders: boolean,
) {
  return showNotReadyProviders || getProviderReadiness(provider).isReady;
}
```

- [ ] **Step 2: Wire the models page to use the helper**

```ts
const visibleProviders = providers.filter((provider) =>
  shouldShowProvider(provider, showNotReadyProviders),
);
```

- [ ] **Step 3: Run a quick type-safety check through lint**

Run: `cd console && npm run lint`
Expected: PASS with no new TypeScript or ESLint issues in the models page.

- [ ] **Step 4: Commit the helper extraction**

```bash
git add console/src/pages/Settings/Models/providerVisibility.ts console/src/pages/Settings/Models/index.tsx
git commit -m "refactor: extract model provider visibility helpers"
```

### Task 2: Add the page-level show-all toggle

**Files:**
- Modify: `console/src/pages/Settings/Models/index.tsx`
- Modify: `console/src/pages/Settings/Models/index.module.less`

- [ ] **Step 1: Add toggle state with default-off behavior**

```ts
const [showNotReadyProviders, setShowNotReadyProviders] = useState(false);
```

- [ ] **Step 2: Render the toggle beside the existing add-provider action**

```tsx
<div className={styles.headerActions}>
  <div className={styles.visibilityToggle}>
    <span className={styles.visibilityToggleLabel}>
      {t("models.showNotReadyProviders")}
    </span>
    <Switch
      checked={showNotReadyProviders}
      onChange={setShowNotReadyProviders}
    />
  </div>
  <Button ...>{t("models.addProvider")}</Button>
</div>
```

- [ ] **Step 3: Add minimal layout styles for the new header controls**

```less
.headerActions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.visibilityToggle {
  display: flex;
  align-items: center;
  gap: 10px;
}
```

- [ ] **Step 4: Build the console to verify the toggle compiles**

Run: `cd console && npm run build`
Expected: PASS with a successful Vite production build and no TypeScript errors.

- [ ] **Step 5: Commit the toggle UI**

```bash
git add console/src/pages/Settings/Models/index.tsx console/src/pages/Settings/Models/index.module.less
git commit -m "feat: add model provider visibility toggle"
```

## Chunk 2: Copy And Verification

### Task 3: Add i18n strings for the toggle

**Files:**
- Modify: `console/src/locales/zh.json`
- Modify: `console/src/locales/en.json`
- Modify: `console/src/locales/ja.json`
- Modify: `console/src/locales/ru.json`

- [ ] **Step 1: Add the toggle label string in each locale**

```json
"showNotReadyProviders": "显示未就绪提供商"
```

- [ ] **Step 2: Add the helper copy string in each locale**

```json
"showNotReadyProvidersHint": "关闭时仅显示可用提供商，打开后显示全部。"
```

- [ ] **Step 3: Re-run lint after locale updates**

Run: `cd console && npm run lint`
Expected: PASS with no formatting or unused-import regressions from the models page changes.

- [ ] **Step 4: Commit the copy changes**

```bash
git add console/src/locales/zh.json console/src/locales/en.json console/src/locales/ja.json console/src/locales/ru.json
git commit -m "feat: add model provider visibility copy"
```

### Task 4: Run end-to-end page verification

**Files:**
- Modify: `console/src/pages/Settings/Models/index.tsx`
- Modify: `console/src/pages/Settings/Models/index.module.less`
- Modify: `console/src/pages/Settings/Models/providerVisibility.ts`

- [ ] **Step 1: Run final static verification**

Run: `cd console && npm run lint && npm run build`
Expected: PASS for both commands.

- [ ] **Step 2: Run manual UI verification in the app**

Run the existing local CoPaw/console workflow, open the Models settings page, and confirm:

- default view shows only ready providers
- enabling the toggle reveals all providers again
- add-provider still opens normally
- provider settings and model-management modals still open normally
- embedded/local providers with zero models stay hidden until the toggle is enabled

- [ ] **Step 3: Make any final polish fixes discovered during manual verification**

```ts
// Keep any follow-up changes constrained to copy, spacing, or filtering logic.
```

- [ ] **Step 4: Commit the verified final state**

```bash
git add console/src/pages/Settings/Models/index.tsx console/src/pages/Settings/Models/index.module.less console/src/pages/Settings/Models/providerVisibility.ts console/src/locales/zh.json console/src/locales/en.json console/src/locales/ja.json console/src/locales/ru.json
git commit -m "feat: hide not-ready model providers by default"
```
