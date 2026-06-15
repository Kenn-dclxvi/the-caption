import { useEffect, useMemo, useState } from "react";

interface Fund {
  name: string;
  asset_class: string;
  currency: string;
  units: string;
  source_symbol: string;
  audit_match_key: string;
  csv_url: string;
}

interface ExternalAssetItem {
  category: string;
  amount: number;
  name: string;
}

interface ExternalAssetsRecord {
  items: ExternalAssetItem[];
}

type ExternalAssetsMap = Record<string, ExternalAssetsRecord>;

interface PortfolioBasisRecord {
  total_acquisition_cost_jpy: number;
}

type PortfolioBasisMap = Record<string, PortfolioBasisRecord>;

interface ExternalAssetFormData {
  month: string;
  category: string;
  amount: string;
  name: string;
}

interface PortfolioBasisFormData {
  month: string;
  total_acquisition_cost_jpy: string;
}

type ActiveApp = "funds" | "external" | "basis";
type NoticeTone = "success" | "error" | "info";

const EMPTY_FUND: Fund = {
  name: "",
  asset_class: "",
  currency: "",
  units: "",
  source_symbol: "",
  audit_match_key: "",
  csv_url: ""
};

const EMPTY_ASSET: ExternalAssetFormData = {
  month: "",
  category: "CASH_EXTERNAL",
  amount: "",
  name: ""
};

const EMPTY_BASIS: PortfolioBasisFormData = {
  month: "",
  total_acquisition_cost_jpy: ""
};

const DEFAULT_FUND_ASSET_CLASSES = ["MUTUAL_FUNDS", "JP_STOCK", "US_STOCK", "FX", "COMMODITIES"];
const DEFAULT_EXTERNAL_CATEGORIES = ["CASH_EXTERNAL"];

function sortMonthKeys(a: string, b: string): number {
  if (a === "default") {
    return 1;
  }
  if (b === "default") {
    return -1;
  }
  return b.localeCompare(a);
}

export default function App() {
  const [activeApp, setActiveApp] = useState<ActiveApp>("funds");
  const [notice, setNotice] = useState<{ tone: NoticeTone; text: string } | null>(null);

  const [funds, setFunds] = useState<Fund[]>([]);
  const [loadingFunds, setLoadingFunds] = useState(true);
  const [savingFunds, setSavingFunds] = useState(false);
  const [fundsView, setFundsView] = useState<"list" | "form">("list");
  const [editingFundIndex, setEditingFundIndex] = useState<number | null>(null);
  const [fundFormData, setFundFormData] = useState<Fund>(EMPTY_FUND);

  const [externalAssets, setExternalAssets] = useState<ExternalAssetsMap>({});
  const [loadingExternalAssets, setLoadingExternalAssets] = useState(true);
  const [savingExternalAssets, setSavingExternalAssets] = useState(false);
  const [externalView, setExternalView] = useState<"list" | "form">("list");
  const [editingExternalId, setEditingExternalId] = useState<string | null>(null);
  const [externalFormData, setExternalFormData] = useState<ExternalAssetFormData>(EMPTY_ASSET);

  const [portfolioBasis, setPortfolioBasis] = useState<PortfolioBasisMap>({});
  const [loadingPortfolioBasis, setLoadingPortfolioBasis] = useState(true);
  const [savingPortfolioBasis, setSavingPortfolioBasis] = useState(false);
  const [basisView, setBasisView] = useState<"list" | "form">("list");
  const [editingBasisMonth, setEditingBasisMonth] = useState<string | null>(null);
  const [basisFormData, setBasisFormData] = useState<PortfolioBasisFormData>(EMPTY_BASIS);

  const monthKeys = useMemo(
    () => Object.keys(externalAssets).sort(sortMonthKeys),
    [externalAssets]
  );

  const externalEntries = useMemo(
    () =>
      monthKeys.flatMap((month) =>
        (externalAssets[month]?.items ?? []).map((item, index) => ({
          id: `${month}::${index}`,
          month,
          index,
          ...item
        }))
      ),
    [externalAssets, monthKeys]
  );

  const basisMonthKeys = useMemo(
    () => Object.keys(portfolioBasis).sort(sortMonthKeys),
    [portfolioBasis]
  );

  const externalCategories = useMemo(() => {
    const categories = new Set(DEFAULT_EXTERNAL_CATEGORIES);
    for (const entry of externalEntries) {
      if (entry.category.trim()) {
        categories.add(entry.category);
      }
    }
    return Array.from(categories);
  }, [externalEntries]);

  const fundAssetClasses = useMemo(() => {
    const classes = new Set(DEFAULT_FUND_ASSET_CLASSES);
    for (const fund of funds) {
      if (fund.asset_class.trim()) {
        classes.add(fund.asset_class);
      }
    }
    return Array.from(classes);
  }, [funds]);

  const hasAuditKey = useMemo(
    () => funds.some((fund) => fund.audit_match_key.trim() !== ""),
    [funds]
  );

  const fetchFunds = async () => {
    setLoadingFunds(true);
    try {
      const res = await fetch("/api/funds");
      if (!res.ok) {
        const payload = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(payload.error || "Failed to fetch funds.");
      }
      const data = (await res.json()) as Fund[];
      setFunds(data.map((fund) => ({ ...EMPTY_FUND, ...fund })));
      setNotice(null);
    } catch (err) {
      console.error("Failed to fetch funds:", err);
      setNotice({ tone: "error", text: err instanceof Error ? err.message : "Failed to fetch funds." });
    } finally {
      setLoadingFunds(false);
    }
  };

  const fetchExternalAssets = async () => {
    setLoadingExternalAssets(true);
    try {
      const res = await fetch("/api/external-assets");
      if (!res.ok) {
        const payload = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(payload.error || "Failed to fetch external assets." );
      }
      const data = (await res.json()) as ExternalAssetsMap;
      setExternalAssets(data);
      setNotice(null);
    } catch (err) {
      console.error("Failed to fetch external assets:", err);
      setNotice({ tone: "error", text: err instanceof Error ? err.message : "Failed to fetch external assets." });
    } finally {
      setLoadingExternalAssets(false);
    }
  };

  const fetchPortfolioBasis = async () => {
    setLoadingPortfolioBasis(true);
    try {
      const res = await fetch("/api/portfolio-basis");
      if (!res.ok) {
        const payload = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(payload.error || "Failed to fetch portfolio basis.");
      }
      const data = (await res.json()) as PortfolioBasisMap;
      setPortfolioBasis(data);
      setNotice(null);
    } catch (err) {
      console.error("Failed to fetch portfolio basis:", err);
      setNotice({ tone: "error", text: err instanceof Error ? err.message : "Failed to fetch portfolio basis." });
    } finally {
      setLoadingPortfolioBasis(false);
    }
  };

  useEffect(() => {
    void fetchFunds();
    void fetchExternalAssets();
    void fetchPortfolioBasis();
  }, []);

  const handleOpenFundForm = (index: number | null = null) => {
    if (index !== null) {
      setFundFormData(funds[index]);
      setEditingFundIndex(index);
    } else {
      setFundFormData(EMPTY_FUND);
      setEditingFundIndex(null);
    }
    setNotice(null);
    setFundsView("form");
  };

  const handleSaveFundForm = (e: React.FormEvent) => {
    e.preventDefault();
    if (!fundFormData.name.trim() || !fundFormData.units.trim()) {
      setNotice({ tone: "error", text: "Name and Units are required." });
      return;
    }

    if (editingFundIndex !== null) {
      const nextFunds = [...funds];
      nextFunds[editingFundIndex] = fundFormData;
      setFunds(nextFunds);
      setNotice({ tone: "success", text: "Fund entry updated locally." });
    } else {
      setFunds([...funds, fundFormData]);
      setNotice({ tone: "success", text: "Fund entry added locally." });
    }

    setFundsView("list");
  };

  const handleDeleteFund = (index: number) => {
    setFunds(funds.filter((_, currentIndex) => currentIndex !== index));
    setNotice({ tone: "info", text: "Fund entry removed locally." });
  };

  const handleSaveFundsToCsv = async () => {
    setSavingFunds(true);
    try {
      const res = await fetch("/api/funds", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(funds)
      });
      if (!res.ok) {
        const payload = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(payload.error || "Failed to save funds.");
      }
      setNotice({ tone: "success", text: "Saved to data/collection/market_units.csv." });
    } catch (err) {
      console.error("Error saving funds:", err);
      setNotice({ tone: "error", text: err instanceof Error ? err.message : "Error saving funds." });
    } finally {
      setSavingFunds(false);
    }
  };

  const handleOpenExternalForm = (entryId: string | null = null) => {
    if (entryId !== null) {
      const entry = externalEntries.find((currentEntry) => currentEntry.id === entryId);
      if (!entry) {
        setNotice({ tone: "error", text: "External asset entry not found." });
        return;
      }
      setEditingExternalId(entryId);
      setExternalFormData({
        month: entry.month,
        category: entry.category,
        amount: String(entry.amount),
        name: entry.name
      });
    } else {
      setEditingExternalId(null);
      setExternalFormData({
        ...EMPTY_ASSET,
        month: monthKeys.find((key) => key !== "default") ?? "default"
      });
    }
    setNotice(null);
    setExternalView("form");
  };

  const handleSaveExternalForm = (e: React.FormEvent) => {
    e.preventDefault();

    const month = externalFormData.month.trim();
    const category = externalFormData.category.trim();
    const name = externalFormData.name.trim();
    const amount = Number(externalFormData.amount);

    if (!month) {
      setNotice({ tone: "error", text: "Month key is required." });
      return;
    }
    if (month !== "default" && !/^\d{4}-\d{2}$/.test(month)) {
      setNotice({ tone: "error", text: "Month key must be YYYY-MM or default." });
      return;
    }
    if (!category) {
      setNotice({ tone: "error", text: "Category is required." });
      return;
    }
    if (!name) {
      setNotice({ tone: "error", text: "Name is required." });
      return;
    }
    if (!Number.isFinite(amount)) {
      setNotice({ tone: "error", text: "Amount must be numeric." });
      return;
    }

    const nextAssets: ExternalAssetsMap = structuredClone(externalAssets);

    if (editingExternalId) {
      const [sourceMonth, sourceIndexRaw] = editingExternalId.split("::");
      const sourceIndex = Number(sourceIndexRaw);
      const sourceItems = [...(nextAssets[sourceMonth]?.items ?? [])];
      if (!Number.isInteger(sourceIndex) || !sourceItems[sourceIndex]) {
        setNotice({ tone: "error", text: "External asset entry not found." });
        return;
      }
      sourceItems.splice(sourceIndex, 1);
      if (sourceItems.length > 0) {
        nextAssets[sourceMonth] = { items: sourceItems };
      } else {
        delete nextAssets[sourceMonth];
      }
    }

    const targetItems = [...(nextAssets[month]?.items ?? [])];
    targetItems.push({ category, amount, name });
    nextAssets[month] = { items: targetItems };

    const sortedAssets: ExternalAssetsMap = {};
    for (const key of Object.keys(nextAssets).sort(sortMonthKeys)) {
      sortedAssets[key] = { items: nextAssets[key].items };
    }

    setExternalAssets(sortedAssets);
    setExternalView("list");
    setEditingExternalId(null);
    setNotice({
      tone: "success",
      text: editingExternalId ? "External asset updated locally." : "External asset added locally."
    });
  };

  const handleDeleteExternal = (entryId: string) => {
    const [month, sourceIndexRaw] = entryId.split("::");
    const sourceIndex = Number(sourceIndexRaw);
    if (!month || !Number.isInteger(sourceIndex)) {
      setNotice({ tone: "error", text: "External asset entry not found." });
      return;
    }

    const nextAssets: ExternalAssetsMap = structuredClone(externalAssets);
    const sourceItems = [...(nextAssets[month]?.items ?? [])];
    if (!sourceItems[sourceIndex]) {
      setNotice({ tone: "error", text: "External asset entry not found." });
      return;
    }

    sourceItems.splice(sourceIndex, 1);
    if (sourceItems.length > 0) {
      nextAssets[month] = { items: sourceItems };
    } else {
      delete nextAssets[month];
    }

    setExternalAssets(nextAssets);
    setNotice({ tone: "info", text: "External asset removed locally." });
  };

  const handleSaveExternalAssets = async () => {
    setSavingExternalAssets(true);
    try {
      const res = await fetch("/api/external-assets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(externalAssets)
      });
      if (!res.ok) {
        const payload = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(payload.error || "Failed to save external assets.");
      }
      setNotice({ tone: "success", text: "Saved to data/external_assets.json." });
    } catch (err) {
      console.error("Error saving external assets:", err);
      setNotice({ tone: "error", text: err instanceof Error ? err.message : "Error saving external assets." });
    } finally {
      setSavingExternalAssets(false);
    }
  };

  const handleOpenBasisForm = (month: string | null = null) => {
    if (month !== null) {
      const record = portfolioBasis[month];
      if (!record) {
        setNotice({ tone: "error", text: "Portfolio basis entry not found." });
        return;
      }
      setEditingBasisMonth(month);
      setBasisFormData({
        month,
        total_acquisition_cost_jpy: String(record.total_acquisition_cost_jpy)
      });
    } else {
      setEditingBasisMonth(null);
      setBasisFormData({
        ...EMPTY_BASIS,
        month: basisMonthKeys.find((key) => key !== "default") ?? "default"
      });
    }
    setNotice(null);
    setBasisView("form");
  };

  const handleSaveBasisForm = (e: React.FormEvent) => {
    e.preventDefault();

    const month = basisFormData.month.trim();
    const totalAcquisitionCost = Number(basisFormData.total_acquisition_cost_jpy);

    if (!month) {
      setNotice({ tone: "error", text: "Month key is required." });
      return;
    }
    if (month !== "default" && !/^\d{4}-\d{2}$/.test(month)) {
      setNotice({ tone: "error", text: "Month key must be YYYY-MM or default." });
      return;
    }
    if (!Number.isFinite(totalAcquisitionCost) || totalAcquisitionCost <= 0) {
      setNotice({ tone: "error", text: "Total acquisition cost must be a positive number." });
      return;
    }

    const nextBasis: PortfolioBasisMap = structuredClone(portfolioBasis);
    if (editingBasisMonth && editingBasisMonth !== month) {
      delete nextBasis[editingBasisMonth];
    }
    nextBasis[month] = { total_acquisition_cost_jpy: totalAcquisitionCost };

    const sortedBasis: PortfolioBasisMap = {};
    for (const key of Object.keys(nextBasis).sort(sortMonthKeys)) {
      sortedBasis[key] = nextBasis[key];
    }

    setPortfolioBasis(sortedBasis);
    setBasisView("list");
    setEditingBasisMonth(null);
    setNotice({
      tone: "success",
      text: editingBasisMonth ? "Portfolio basis updated locally." : "Portfolio basis added locally."
    });
  };

  const handleDeleteBasis = (month: string) => {
    if (!portfolioBasis[month]) {
      setNotice({ tone: "error", text: "Portfolio basis entry not found." });
      return;
    }

    const nextBasis: PortfolioBasisMap = structuredClone(portfolioBasis);
    delete nextBasis[month];
    setPortfolioBasis(nextBasis);
    setNotice({ tone: "info", text: "Portfolio basis removed locally." });
  };

  const handleSavePortfolioBasis = async () => {
    setSavingPortfolioBasis(true);
    try {
      const res = await fetch("/api/portfolio-basis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(portfolioBasis)
      });
      if (!res.ok) {
        const payload = (await res.json().catch(() => ({}))) as { error?: string };
        throw new Error(payload.error || "Failed to save portfolio basis.");
      }
      setNotice({ tone: "success", text: "Saved to data/portfolio_basis.json." });
    } catch (err) {
      console.error("Error saving portfolio basis:", err);
      setNotice({ tone: "error", text: err instanceof Error ? err.message : "Error saving portfolio basis." });
    } finally {
      setSavingPortfolioBasis(false);
    }
  };

  const noticeClassName =
    notice?.tone === "error"
      ? "border-red-200 bg-red-50 text-red-700"
      : notice?.tone === "success"
        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
        : "border-[#cbd5e1] bg-white text-[#64748b]";

  const currentPath =
    activeApp === "funds"
      ? "data/collection/market_units.csv"
      : activeApp === "external"
        ? "data/external_assets.json"
        : "data/portfolio_basis.json";
  const currentCount =
    activeApp === "funds" ? funds.length : activeApp === "external" ? externalEntries.length : basisMonthKeys.length;
  const currentStatus =
    activeApp === "funds"
      ? loadingFunds
        ? "SYNCING"
        : savingFunds
          ? "SAVING"
          : "READY"
      : activeApp === "external"
        ? loadingExternalAssets
          ? "SYNCING"
          : savingExternalAssets
            ? "SAVING"
            : "READY"
        : loadingPortfolioBasis
          ? "SYNCING"
          : savingPortfolioBasis
            ? "SAVING"
            : "READY";

  return (
    <div className="min-h-screen bg-white text-[#1e293b] font-sans font-light selection:bg-[#c5a059] selection:text-white flex flex-col">
      <div className="fixed top-0 left-0 right-0 h-1 bg-[#c5a059] z-[100]" />

      <header className="flex justify-between items-center px-4 md:px-12 py-6 bg-white border-b border-[#cbd5e1] text-[15px] sticky top-0 z-40">
        <div className="flex items-center gap-4 md:gap-12">
          <span className="tracking-[0.1em] uppercase text-[#1e293b] hidden sm:inline text-[15px]">
            The Editorial Monolith
          </span>
          <nav className="flex gap-6 md:gap-10">
            <button
              onClick={() => {
                setActiveApp("funds");
                setFundsView("list");
              }}
              className={`uppercase text-[11px] tracking-[0.15em] transition-all ${
                activeApp === "funds"
                  ? "text-[#1e293b] underline decoration-[#cbd5e1] underline-offset-[12px]"
                  : "text-[#64748b] hover:text-[#1e293b]"
              }`}
            >
              Market Units
            </button>
            <button
              onClick={() => {
                setActiveApp("external");
                setExternalView("list");
              }}
              className={`uppercase text-[11px] tracking-[0.15em] transition-all ${
                activeApp === "external"
                  ? "text-[#1e293b] underline decoration-[#cbd5e1] underline-offset-[12px]"
                  : "text-[#64748b] hover:text-[#1e293b]"
              }`}
            >
              External Assets
            </button>
            <button
              onClick={() => {
                setActiveApp("basis");
                setBasisView("list");
              }}
              className={`uppercase text-[11px] tracking-[0.15em] transition-all ${
                activeApp === "basis"
                  ? "text-[#1e293b] underline decoration-[#cbd5e1] underline-offset-[12px]"
                  : "text-[#64748b] hover:text-[#1e293b]"
              }`}
            >
              Portfolio Basis
            </button>
          </nav>
        </div>
        <div className="text-[11px] uppercase tracking-[0.15em] text-[#64748b]">
          V1.1.0 Editor Grid
        </div>
      </header>

      <main className="flex-1 flex flex-col relative pb-28">
        {notice && (
          <section className="px-4 md:px-12 pt-6">
            <div className="max-w-7xl mx-auto">
              <div className={`border px-5 py-4 text-[12px] tracking-[0.12em] uppercase ${noticeClassName}`}>
                {notice.text}
              </div>
            </div>
          </section>
        )}

        <div className="border-b border-[#cbd5e1] px-4 md:px-12 py-4 sticky top-[73px] z-10 bg-white/80 backdrop-blur-sm">
          <div className="max-w-7xl mx-auto flex flex-wrap gap-6 md:gap-10">
            {activeApp === "funds" ? (
              <>
                <button
                  onClick={() => handleOpenFundForm()}
                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer"
                >
                  [ Add New ]
                </button>
                <button
                  onClick={() => void fetchFunds()}
                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer"
                >
                  [ Refresh ]
                </button>
                <button
                  onClick={() => void handleSaveFundsToCsv()}
                  disabled={savingFunds}
                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer disabled:opacity-30"
                >
                  [ {savingFunds ? "Saving" : "Save to Server"} ]
                </button>
              </>
            ) : activeApp === "external" ? (
              <>
                <button
                  onClick={() => handleOpenExternalForm()}
                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer"
                >
                  [ Add New ]
                </button>
                <button
                  onClick={() => void fetchExternalAssets()}
                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer"
                >
                  [ Refresh ]
                </button>
                <button
                  onClick={() => void handleSaveExternalAssets()}
                  disabled={savingExternalAssets}
                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer disabled:opacity-30"
                >
                  [ {savingExternalAssets ? "Saving" : "Save to Server"} ]
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => handleOpenBasisForm()}
                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer"
                >
                  [ Add New ]
                </button>
                <button
                  onClick={() => void fetchPortfolioBasis()}
                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer"
                >
                  [ Refresh ]
                </button>
                <button
                  onClick={() => void handleSavePortfolioBasis()}
                  disabled={savingPortfolioBasis}
                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer disabled:opacity-30"
                >
                  [ {savingPortfolioBasis ? "Saving" : "Save to Server"} ]
                </button>
              </>
            )}
          </div>
        </div>

        <div className="px-4 md:px-12 py-12 md:py-20">
          <div className="max-w-7xl mx-auto">
            {activeApp === "funds" ? (
              fundsView === "list" ? (
                <div className="space-y-12">
                  <div className="overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0">
                    {loadingFunds ? (
                      <div className="py-24 text-center text-[11px] uppercase tracking-[0.2em] text-[#64748b]">
                        Syncing
                      </div>
                    ) : (
                      <table className="w-full border-collapse min-w-[920px]">
                        <thead>
                          <tr className="text-left border-b border-[#cbd5e1]">
                            <th className="py-4 text-[11px] uppercase tracking-[0.15em] text-[#64748b] font-light w-[24%]">Asset Name</th>
                            <th className="py-4 text-[11px] uppercase tracking-[0.15em] text-[#64748b] font-light pl-4 w-[14%]">Class</th>
                            <th className="py-4 text-[11px] uppercase tracking-[0.15em] text-[#64748b] font-light w-[9%]">Currency</th>
                            <th className="py-4 text-[11px] uppercase tracking-[0.15em] text-[#64748b] font-light text-right pr-10 w-[12%]">Units</th>
                            <th className="py-4 text-[11px] uppercase tracking-[0.15em] text-[#64748b] font-light w-[11%]">Source</th>
                            {hasAuditKey && (
                              <th className="py-4 text-[11px] uppercase tracking-[0.15em] text-[#64748b] font-light w-[18%]">Audit Key</th>
                            )}
                            <th className="py-4 text-[11px] uppercase tracking-[0.15em] text-[#64748b] font-light text-right w-48">Action</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#cbd5e1]/30">
                          {funds.map((row, idx) => (
                            <tr key={`${row.name}-${idx}`} className="hover:bg-[#f8fafc] transition-colors group">
                              <td className="py-6 text-[13px] tracking-[0.05em] font-light text-[#1e293b]">
                                <div className="truncate-guard" title={row.name}>{row.name}</div>
                              </td>
                              <td className="py-6 text-[13px] text-[#64748b] uppercase tracking-[0.1em] font-light pl-4">{row.asset_class}</td>
                              <td className="py-6 text-[13px] text-[#64748b] uppercase tracking-[0.1em] font-light">{row.currency}</td>
                              <td className="py-6 text-[13px] text-right tabular-nums tracking-[-0.02em] font-extralight text-[#1e293b] pr-10">
                                {Number(row.units || 0).toLocaleString(undefined, {
                                  minimumFractionDigits: 2,
                                  maximumFractionDigits: 8
                                })}
                              </td>
                              <td className="py-6 text-[13px] text-[#64748b] uppercase tracking-[0.1em] font-light">{row.source_symbol}</td>
                              {hasAuditKey && (
                                <td className="py-6 text-[13px] text-[#64748b] tracking-[0.05em] font-light">
                                  <div className="truncate-guard" title={row.audit_match_key}>{row.audit_match_key}</div>
                                </td>
                              )}
                              <td className="py-6 text-right space-x-6">
                                <button
                                  onClick={() => handleOpenFundForm(idx)}
                                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer font-light"
                                >
                                  [ Edit ]
                                </button>
                                <button
                                  onClick={() => handleDeleteFund(idx)}
                                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer font-light"
                                >
                                  [ Delete ]
                                </button>
                              </td>
                            </tr>
                          ))}
                          {funds.length === 0 && (
                            <tr>
                              <td colSpan={hasAuditKey ? 7 : 6} className="py-20 text-center text-[11px] uppercase tracking-[0.2em] text-[#64748b] opacity-40">
                                No records found
                              </td>
                            </tr>
                          )}
                        </tbody>
                      </table>
                    )}
                  </div>
                </div>
              ) : (
                <div className="max-w-xl mx-auto border border-[#cbd5e1] p-8 md:p-16 bg-white">
                  <header className="mb-12 border-b border-[#cbd5e1] pb-6">
                    <h3 className="text-[11px] uppercase tracking-[0.15em] text-[#c5a059]">
                      {editingFundIndex !== null ? "Edit Fund" : "New Fund"}
                    </h3>
                  </header>
                  <form onSubmit={handleSaveFundForm} className="space-y-10">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
                      <div className="space-y-3">
                        <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Name</label>
                        <input
                          className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent"
                          value={fundFormData.name}
                          onChange={(e) => setFundFormData({ ...fundFormData, name: e.target.value })}
                          required
                        />
                      </div>
                      <div className="space-y-3">
                        <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Units</label>
                        <input
                          type="number"
                          step="any"
                          className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent tabular-nums"
                          value={fundFormData.units}
                          onChange={(e) => setFundFormData({ ...fundFormData, units: e.target.value })}
                          required
                        />
                      </div>
                      <div className="space-y-3">
                        <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Asset Class</label>
                        <select
                          className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent cursor-pointer"
                          value={fundFormData.asset_class}
                          onChange={(e) => setFundFormData({ ...fundFormData, asset_class: e.target.value })}
                          required
                        >
                          <option value="">Select Asset Class</option>
                          {fundAssetClasses.map((assetClass) => (
                            <option key={assetClass} value={assetClass}>
                              {assetClass}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="space-y-3">
                        <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Currency</label>
                        <input
                          className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent"
                          value={fundFormData.currency}
                          onChange={(e) => setFundFormData({ ...fundFormData, currency: e.target.value })}
                          required
                        />
                      </div>
                      <div className="space-y-3">
                        <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Source Symbol</label>
                        <input
                          className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent"
                          value={fundFormData.source_symbol}
                          onChange={(e) => setFundFormData({ ...fundFormData, source_symbol: e.target.value })}
                        />
                      </div>
                      <div className="space-y-3">
                        <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">CSV URL</label>
                        <input
                          className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent"
                          value={fundFormData.csv_url}
                          onChange={(e) => setFundFormData({ ...fundFormData, csv_url: e.target.value })}
                        />
                      </div>
                      <div className="space-y-3 md:col-span-2">
                        <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Audit Match Key</label>
                        <input
                          className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent"
                          value={fundFormData.audit_match_key}
                          onChange={(e) => setFundFormData({ ...fundFormData, audit_match_key: e.target.value })}
                        />
                      </div>
                    </div>
                    <div className="pt-12 flex gap-10">
                      <button
                        type="submit"
                        className="text-[11px] uppercase tracking-[0.2em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer font-light"
                      >
                        [ Save Entry ]
                      </button>
                      <button
                        type="button"
                        onClick={() => setFundsView("list")}
                        className="text-[11px] uppercase tracking-[0.2em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer font-light"
                      >
                        [ Cancel ]
                      </button>
                    </div>
                  </form>
                </div>
              )
            ) : activeApp === "external" ? (
              externalView === "list" ? (
                <div className="space-y-20">
                {loadingExternalAssets ? (
                  <div className="py-24 text-center text-[11px] uppercase tracking-[0.2em] text-[#64748b]">
                    Syncing
                  </div>
                ) : monthKeys.length === 0 ? (
                  <div className="py-24 text-center text-[11px] uppercase tracking-[0.2em] text-[#64748b] opacity-40">
                    No entries found
                  </div>
                ) : (
                  monthKeys.map((month) => (
                    <section key={month} className="space-y-6">
                      <h3 className="text-[11px] uppercase tracking-[0.2em] text-[#c5a059] border-b border-[#cbd5e1] pb-3">
                        Chronicle: {month}
                      </h3>
                      <div className="overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0">
                        <table className="w-full border-collapse min-w-[720px]">
                          <thead>
                            <tr className="text-left border-b border-[#cbd5e1]">
                              <th className="py-4 text-[11px] uppercase tracking-[0.15em] text-[#64748b] font-light w-[40%]">Name</th>
                              <th className="py-4 text-[11px] uppercase tracking-[0.15em] text-[#64748b] font-light text-right pr-12 w-[18%]">Amount</th>
                              <th className="py-4 text-[11px] uppercase tracking-[0.15em] text-[#64748b] font-light pl-4 w-[18%]">Category</th>
                              <th className="py-4 text-[11px] uppercase tracking-[0.15em] text-[#64748b] font-light text-right w-48">Action</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-[#cbd5e1]/30">
                            {(externalAssets[month]?.items ?? []).map((item, index) => {
                              const entryId = `${month}::${index}`;
                              return (
                                <tr key={entryId} className="hover:bg-[#f8fafc] transition-colors group">
                                  <td className="py-6 text-[13px] tracking-[0.05em] font-light text-[#1e293b]">{item.name}</td>
                                  <td className="py-6 text-[13px] text-right tabular-nums tracking-[-0.02em] font-extralight text-[#1e293b] pr-12">
                                    {item.amount.toLocaleString()}
                                  </td>
                                  <td className="py-6 text-[13px] text-[#64748b] uppercase tracking-[0.1em] font-light pl-4">{item.category}</td>
                                  <td className="py-6 text-right space-x-6">
                                    <button
                                      onClick={() => handleOpenExternalForm(entryId)}
                                      className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer font-light"
                                    >
                                      [ Edit ]
                                    </button>
                                    <button
                                      onClick={() => handleDeleteExternal(entryId)}
                                      className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer font-light"
                                    >
                                      [ Delete ]
                                    </button>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </section>
                  ))
                )}
                </div>
              ) : (
                <div className="max-w-xl mx-auto border border-[#cbd5e1] p-8 md:p-16 bg-white">
                <header className="mb-12 border-b border-[#cbd5e1] pb-6">
                  <h3 className="text-[11px] uppercase tracking-[0.15em] text-[#c5a059]">
                    {editingExternalId ? "Edit Entry" : "New Entry"}
                  </h3>
                </header>
                <form onSubmit={handleSaveExternalForm} className="space-y-10">
                  <div className="space-y-3">
                    <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Month Key</label>
                    <input
                      className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent"
                      value={externalFormData.month}
                      onChange={(e) => setExternalFormData({ ...externalFormData, month: e.target.value })}
                      placeholder="YYYY-MM or default"
                      required
                    />
                  </div>
                  <div className="space-y-3">
                    <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Category</label>
                    <select
                      className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent cursor-pointer"
                      value={externalFormData.category}
                      onChange={(e) => setExternalFormData({ ...externalFormData, category: e.target.value })}
                    >
                      {externalCategories.map((category) => (
                        <option key={category} value={category}>
                          {category}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-3">
                    <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Amount (JPY)</label>
                    <input
                      type="number"
                      className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent tabular-nums"
                      value={externalFormData.amount}
                      onChange={(e) => setExternalFormData({ ...externalFormData, amount: e.target.value })}
                      required
                    />
                  </div>
                  <div className="space-y-3">
                    <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Name</label>
                    <input
                      className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent"
                      value={externalFormData.name}
                      onChange={(e) => setExternalFormData({ ...externalFormData, name: e.target.value })}
                      required
                    />
                  </div>
                  <div className="pt-12 flex gap-10">
                    <button
                      type="submit"
                      className="text-[11px] uppercase tracking-[0.2em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer font-light"
                    >
                      [ Save Entry ]
                    </button>
                    <button
                      type="button"
                      onClick={() => setExternalView("list")}
                      className="text-[11px] uppercase tracking-[0.2em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer font-light"
                    >
                      [ Cancel ]
                    </button>
                  </div>
                </form>
                </div>
              )
            ) : basisView === "list" ? (
              <div className="space-y-12">
                {loadingPortfolioBasis ? (
                  <div className="py-24 text-center text-[11px] uppercase tracking-[0.2em] text-[#64748b]">
                    Syncing
                  </div>
                ) : basisMonthKeys.length === 0 ? (
                  <div className="py-24 text-center text-[11px] uppercase tracking-[0.2em] text-[#64748b] opacity-40">
                    No entries found
                  </div>
                ) : (
                  <div className="overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0">
                    <table className="w-full border-collapse min-w-[720px]">
                      <thead>
                        <tr className="text-left border-b border-[#cbd5e1]">
                          <th className="py-4 text-[11px] uppercase tracking-[0.15em] text-[#64748b] font-light w-[24%]">Month</th>
                          <th className="py-4 text-[11px] uppercase tracking-[0.15em] text-[#64748b] font-light text-right pr-12 w-[32%]">Total Acquisition Cost</th>
                          <th className="py-4 text-[11px] uppercase tracking-[0.15em] text-[#64748b] font-light text-right w-48">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#cbd5e1]/30">
                        {basisMonthKeys.map((month) => (
                          <tr key={month} className="hover:bg-[#f8fafc] transition-colors group">
                            <td className="py-6 text-[13px] tracking-[0.1em] uppercase font-light text-[#1e293b]">{month}</td>
                            <td className="py-6 text-[13px] text-right tabular-nums tracking-[-0.02em] font-extralight text-[#1e293b] pr-12">
                              {portfolioBasis[month].total_acquisition_cost_jpy.toLocaleString()}
                            </td>
                            <td className="py-6 text-right space-x-6">
                              <button
                                onClick={() => handleOpenBasisForm(month)}
                                className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer font-light"
                              >
                                [ Edit ]
                              </button>
                              <button
                                onClick={() => handleDeleteBasis(month)}
                                className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer font-light"
                              >
                                [ Delete ]
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ) : (
              <div className="max-w-xl mx-auto border border-[#cbd5e1] p-8 md:p-16 bg-white">
                <header className="mb-12 border-b border-[#cbd5e1] pb-6">
                  <h3 className="text-[11px] uppercase tracking-[0.15em] text-[#c5a059]">
                    {editingBasisMonth ? "Edit Basis" : "New Basis"}
                  </h3>
                </header>
                <form onSubmit={handleSaveBasisForm} className="space-y-10">
                  <div className="space-y-3">
                    <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Month Key</label>
                    <input
                      className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent"
                      value={basisFormData.month}
                      onChange={(e) => setBasisFormData({ ...basisFormData, month: e.target.value })}
                      placeholder="YYYY-MM or default"
                      required
                    />
                  </div>
                  <div className="space-y-3">
                    <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Total Acquisition Cost (JPY)</label>
                    <input
                      type="number"
                      className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent tabular-nums"
                      value={basisFormData.total_acquisition_cost_jpy}
                      onChange={(e) => setBasisFormData({ ...basisFormData, total_acquisition_cost_jpy: e.target.value })}
                      required
                    />
                  </div>
                  <div className="pt-12 flex gap-10">
                    <button
                      type="submit"
                      className="text-[11px] uppercase tracking-[0.2em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer font-light"
                    >
                      [ Save Entry ]
                    </button>
                    <button
                      type="button"
                      onClick={() => setBasisView("list")}
                      className="text-[11px] uppercase tracking-[0.2em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer font-light"
                    >
                      [ Cancel ]
                    </button>
                  </div>
                </form>
              </div>
            )}
          </div>
        </div>
      </main>

      <footer className="fixed bottom-0 w-full border-t border-[#cbd5e1] bg-white/80 backdrop-blur-sm z-50">
        <div className="max-w-7xl mx-auto grid grid-cols-2 md:grid-cols-4 text-[10px] uppercase tracking-[0.15em] text-[#64748b]">
          <div className="px-4 md:px-6 py-4 flex items-center gap-3">
            <span className="opacity-40">[ SYSTEM ]</span>
            <span className="text-[#1e293b]">V1.1.0</span>
          </div>
          <div className="px-4 md:px-6 py-4 flex items-center gap-3 truncate">
            <span className="opacity-40">[ FILE ]</span>
            <span className="text-[#1e293b] truncate">{currentPath}</span>
          </div>
          <div className="px-4 md:px-6 py-4 flex items-center gap-3">
            <span className="opacity-40">[ COUNT ]</span>
            <span className="text-[#1e293b]">{currentCount}</span>
          </div>
          <div className="px-4 md:px-6 py-4 flex items-center gap-3">
            <span className="opacity-40">[ STATE ]</span>
            <span className="text-[#1e293b]">{currentStatus}</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
