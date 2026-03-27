import { useMemo, useState } from "react";
import { Button, Input, Switch } from "@agentscope-ai/design";
import { PlusOutlined, SearchOutlined } from "@ant-design/icons";
import { useProviders } from "./useProviders";
import { filterProvidersByVisibility } from "./providerVisibility";
import {
  PageHeader,
  LoadingState,
  ProviderCard,
  CustomProviderModal,
  ModelsSection,
} from "./components";
import { useTranslation } from "react-i18next";
import type { ProviderInfo } from "../../../api/types/provider";
import styles from "./index.module.less";

/* ------------------------------------------------------------------ */
/* Main Page                                                           */
/* ------------------------------------------------------------------ */

function ModelsPage() {
  const { t } = useTranslation();
  const { providers, activeModels, loading, error, fetchAll } = useProviders();
  const [hoveredCard, setHoveredCard] = useState<string | null>(null);
  const [addProviderOpen, setAddProviderOpen] = useState(false);
  const [showAllProviders, setShowAllProviders] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const refreshProvidersSilently = () => fetchAll(false);

  const visibleProviders = useMemo(
    () => filterProvidersByVisibility(providers, showAllProviders),
    [providers, showAllProviders],
  );

  const { regularProviders, embeddedProviders } = useMemo(() => {
    const regular: ProviderInfo[] = [];
    const embedded: ProviderInfo[] = [];
    for (const p of visibleProviders) {
      if (p.is_local) embedded.push(p);
      else regular.push(p);
    }

    const query = searchQuery.trim().toLowerCase();
    if (!query) {
      return { regularProviders: regular, embeddedProviders: embedded };
    }

    return {
      regularProviders: regular.filter((p) =>
        p.name.toLowerCase().includes(query),
      ),
      embeddedProviders: embedded.filter((p) =>
        p.name.toLowerCase().includes(query),
      ),
    };
  }, [visibleProviders, searchQuery]);

  const handleMouseEnter = (providerId: string) => {
    setHoveredCard(providerId);
  };

  const handleMouseLeave = () => {
    setHoveredCard(null);
  };

  const renderProviderCards = (list: ProviderInfo[]) =>
    list.map((provider) => (
      <ProviderCard
        key={provider.id}
        provider={provider}
        activeModels={activeModels}
        onSaved={refreshProvidersSilently}
        isHover={hoveredCard === provider.id}
        onMouseEnter={() => handleMouseEnter(provider.id)}
        onMouseLeave={handleMouseLeave}
      />
    ));

  return (
    <div className={styles.settingsPage}>
      {loading ? (
        <LoadingState message={t("models.loading")} />
      ) : error ? (
        <LoadingState message={error} error onRetry={fetchAll} />
      ) : (
        <>
          {/* ---- LLM Section (top) ---- */}
          <PageHeader
            title={t("models.llmTitle")}
            description={t("models.llmDescription")}
          />
          <ModelsSection
            providers={providers}
            activeModels={activeModels}
            onSaved={fetchAll}
          />

          {/* ---- Providers Section ---- */}
          <div className={styles.providersBlock}>
            <div className={styles.sectionHeaderRow}>
              <PageHeader
                title={t("models.providersTitle")}
                description={t("models.providersDescription")}
              />
              <div className={styles.sectionHeaderActions}>
                <div className={styles.visibilityToggle}>
                  <Switch
                    checked={showAllProviders}
                    onChange={setShowAllProviders}
                  />
                  <div className={styles.visibilityToggleText}>
                    <div className={styles.visibilityToggleLabel}>
                      {t("models.showAllProvidersToggle")}
                    </div>
                    <div className={styles.visibilityToggleHint}>
                      {t("models.showAllProvidersHint")}
                    </div>
                  </div>
                </div>
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => setAddProviderOpen(true)}
                  className={styles.addProviderBtn}
                >
                  {t("models.addProvider")}
                </Button>
              </div>
            </div>

            {/* ---- Search Row ---- */}
            <div className={styles.searchRow}>
              <Input
                placeholder={t("models.searchPlaceholder")}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onPressEnter={() => {}}
                className={styles.searchInput}
                prefix={<SearchOutlined />}
                allowClear
              />
              <Button
                type="primary"
                icon={<SearchOutlined />}
                onClick={() => fetchAll()}
                className={styles.searchBtn}
              >
                {t("models.search")}
              </Button>
            </div>

            {regularProviders.length > 0 && (
              <div className={styles.providerGroup}>
                <div className={styles.providerCards}>
                  {renderProviderCards(regularProviders)}
                </div>
              </div>
            )}

            {embeddedProviders.length > 0 && (
              <div className={styles.providerGroup}>
                <h4 className={styles.providerGroupTitle}>
                  {t("models.localEmbedded")}
                </h4>
                <div className={styles.providerCards}>
                  {renderProviderCards(embeddedProviders)}
                </div>
              </div>
            )}
          </div>

          <CustomProviderModal
            open={addProviderOpen}
            onClose={() => setAddProviderOpen(false)}
            onSaved={fetchAll}
          />
        </>
      )}
    </div>
  );
}

export default ModelsPage;
