import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { EMPTY_FUND, formatUnits, MarketUnitsStore } from "./marketUnitsClient";
import { MonthlyInputsStore, type MonthlyDraft } from "./monthlyInputsClient";

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

  const [fundStore] = useState(() => new MarketUnitsStore());
  const fundState = useSyncExternalStore(fundStore.subscribe, fundStore.getSnapshot);
  const funds = fundState.items;
  const loadingFunds = fundState.loading;
  const savingFunds = fundState.saving;
  const [fundsView, setFundsView] = useState<"list" | "form">("list");
  const fundFormData = fundState.form?.item ?? EMPTY_FUND;
  const editingFundId = fundState.form?.targetId ?? null;
  const [sessionToken, setSessionToken] = useState("");
  const fundsLocked = loadingFunds || savingFunds || !!fundState.pending || fundState.needsRefresh || !fundState.etag;
  const canReplaceFunds = !!fundState.session?.permissions.includes("market-units:replace");
  const formIsStale = !!fundState.form && fundState.form.epoch !== fundState.epoch;

  const [externalStore] = useState(() => new MonthlyInputsStore("external-assets", fundStore));
  const [basisStore] = useState(() => new MonthlyInputsStore("portfolio-basis", fundStore));
  const externalState = useSyncExternalStore(externalStore.subscribe, externalStore.getSnapshot);
  const basisState = useSyncExternalStore(basisStore.subscribe, basisStore.getSnapshot);
  const [externalView, setExternalView] = useState<"list" | "form">("list");
  const [basisView, setBasisView] = useState<"list" | "form">("list");
  const externalFormData = externalState.form?.item ?? EMPTY_ASSET;
  const basisFormData = basisState.form?.item ?? EMPTY_BASIS;
  const editingExternalId = externalState.form?.targetId ?? null;
  const editingBasisMonth = basisState.form?.targetId ?? null;
  const setExternalFormData = (value: ExternalAssetFormData) => externalStore.updateForm(value);
  const setBasisFormData = (value: PortfolioBasisFormData) => basisStore.updateForm(value);
  const loadingExternalAssets = externalState.loading;
  const savingExternalAssets = externalState.saving;
  const loadingPortfolioBasis = basisState.loading;
  const savingPortfolioBasis = basisState.saving;
  const externalAssets = useMemo(() => {
    const months: Record<string, { items: MonthlyDraft[] }> = {};
    for (const month of externalState.emptyMonths) months[month] = { items: [] };
    for (const row of externalState.items) { months[row.month] ??= { items: [] }; months[row.month].items.push(row); }
    return months;
  }, [externalState.items, externalState.emptyMonths]);
  const portfolioBasis = useMemo(() => Object.fromEntries(basisState.items.map((row) => [row.month, row])), [basisState.items]);

  const monthKeys = useMemo(
    () => Object.keys(externalAssets).sort(sortMonthKeys),
    [externalAssets]
  );

  const externalEntries = useMemo(
    () =>
      monthKeys.flatMap((month) =>
        (externalAssets[month]?.items ?? []).map((item, index) => ({
          ...item,
          id: item.draft_id,
          month,
          index
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
    if (fundState.dirty && !window.confirm("Refresh will replace the list draft with the latest saved data. Copy any changes you want to keep first. Continue?")) return;
    await fundStore.refresh();
  };

  const refreshMonthly = async (store: MonthlyInputsStore) => {
    if (store.getSnapshot().dirty && !window.confirm("Refresh will replace the list draft. Copy any edits you want to keep first. Continue?")) return;
    await store.refresh();
  };
  const fetchExternalAssets = () => refreshMonthly(externalStore);
  const fetchPortfolioBasis = () => refreshMonthly(basisStore);

  useEffect(() => { void fundStore.initialize(); }, [fundStore]);
  useEffect(() => {
    if (!fundState.session) return;
    void externalStore.initialize();
    void basisStore.initialize();
  }, [fundState.session, externalStore, basisStore]);

  const handleOpenFundForm = (index: number | null = null) => {
    fundStore.openForm(index === null ? undefined : funds[index]?.draft_id);
    if (fundStore.getSnapshot().form) setFundsView("form");
  };

  const handleSaveFundForm = (event: React.FormEvent) => {
    event.preventDefault();
    fundStore.applyForm();
    if (!fundStore.getSnapshot().form) setFundsView("list");
  };

  const handleDeleteFund = (index: number) => {
    if (funds[index]) fundStore.deleteItem(funds[index].draft_id);
  };

  const handleSaveFundsToCsv = async () => {
    const clearConfirmed = funds.length === 0 && window.confirm("Clear all Market Units on the server? This saves an empty asset list and requires clear permission.");
    if (funds.length === 0 && !clearConfirmed) return;
    await fundStore.save(clearConfirmed);
  };

  const handleLogin = async (event: React.FormEvent) => {
    event.preventDefault();
    const credential = sessionToken;
    setSessionToken("");
    await fundStore.login(credential);
  };

  const handleCopyDraft = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(funds.map(({ draft_id: _draftId, ...item }) => item), null, 2));
      setNotice({ tone: "info", text: "Market Units draft copied. Refresh and reapply the changes you want to keep." });
    } catch {
      setNotice({ tone: "error", text: "Clipboard is unavailable. Copy the draft shown below before refreshing." });
    }
  };

  const handleOpenExternalForm = (id: string | null = null) => {
    externalStore.openForm(id ?? undefined);
    if (externalStore.getSnapshot().form) setExternalView("form");
  };
  const handleSaveExternalForm = (event: React.FormEvent) => {
    event.preventDefault(); externalStore.applyForm();
    if (!externalStore.getSnapshot().form) setExternalView("list");
  };
  const handleDeleteExternal = (id: string) => externalStore.deleteItem(id);
  const saveMonthly = async (store: MonthlyInputsStore) => {
    const clear = store.getSnapshot().items.length === 0;
    if (clear && !window.confirm("Clear all entries on the server? This requires clear permission.")) return;
    await store.save(clear);
  };
  const handleSaveExternalAssets = () => saveMonthly(externalStore);
  const handleOpenBasisForm = (month: string | null = null) => {
    basisStore.openForm(month === null ? undefined : portfolioBasis[month]?.draft_id);
    if (basisStore.getSnapshot().form) setBasisView("form");
  };
  const handleSaveBasisForm = (event: React.FormEvent) => {
    event.preventDefault(); basisStore.applyForm();
    if (!basisStore.getSnapshot().form) setBasisView("list");
  };
  const handleDeleteBasis = (month: string) => { if (portfolioBasis[month]) basisStore.deleteItem(portfolioBasis[month].draft_id); };
  const handleSavePortfolioBasis = () => saveMonthly(basisStore);
  const monthlyStore = activeApp === "external" ? externalStore : basisStore;
  const monthlyState = activeApp === "external" ? externalState : basisState;
  const visibleNotice = (activeApp === "funds" || !fundState.session) ? fundState.notice ?? notice : monthlyState.notice ?? notice;
  const noticeClassName =
    visibleNotice?.tone === "error"
      ? "border-red-200 bg-red-50 text-red-700"
      : visibleNotice?.tone === "success"
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
  const currentState = activeApp === "funds" ? fundState : monthlyState;
  const currentStatus = currentState.loading ? "SYNCING" : currentState.saving ? "SAVING"
    : !fundState.session ? "SIGN IN" : currentState.pending ? "RESULT UNCONFIRMED"
    : activeApp !== "funds" && monthlyState.reconciliation ? "RESULT EXPIRED / COMPARE"
    : currentState.needsRefresh ? "SAVED / REFRESH NEEDED" : currentState.conflict ? "CONFLICT"
    : !currentState.etag ? "REFRESH NEEDED" : currentState.dirty ? "DRAFT" : "READY";

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
        {visibleNotice && (
          <section className="px-4 md:px-12 pt-6">
            <div className="max-w-7xl mx-auto">
              <div className={`border px-5 py-4 text-[12px] tracking-[0.12em] uppercase ${noticeClassName}`}>
                {visibleNotice.text}
              </div>
            </div>
          </section>
        )}

        {!fundState.session && fundState.sessionChecked && (
          <section className="px-4 md:px-12 py-8 border-b border-[#cbd5e1]">
            <form onSubmit={handleLogin} className="max-w-xl mx-auto space-y-4">
              <label htmlFor="session-token" className="block text-sm">Sign in with your THE CAPTION access token</label>
              <input id="session-token" type="password" autoComplete="off" value={sessionToken}
                onChange={(event) => setSessionToken(event.target.value)} disabled={fundState.authenticating}
                className="w-full border-b border-[#cbd5e1] py-2 focus:outline-none focus:border-[#c5a059]" required />
              <button type="submit" disabled={fundState.authenticating || !sessionToken.trim()}
                className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] disabled:opacity-30">
                [ {fundState.authenticating ? "Signing In" : "Sign In"} ]
              </button>
            </form>
          </section>
        )}

        {activeApp !== "funds" && (monthlyState.pending || monthlyState.conflict || monthlyState.reconciliation) && (
          <section className="px-4 md:px-12 py-4 space-y-4">
            {monthlyState.pending && <button onClick={() => void monthlyStore.retry()}
              disabled={monthlyState.saving || monthlyState.loading || !fundState.session}>[ Retry Same Request ]</button>}
            {monthlyState.reconciliation && <>
              <p>The save may have succeeded. Refresh loads comparison data without replacing your draft.
                Compare below and copy any edits you want to keep before confirming.</p>
              <details open><summary>Original request</summary>
                <pre className="overflow-auto whitespace-pre-wrap text-xs">{monthlyState.reconciliation.request.body}</pre>
              </details>
              <details open><summary>Latest saved data</summary>
                <pre className="overflow-auto whitespace-pre-wrap text-xs">{monthlyState.reconciliation.latest
                  ? JSON.stringify(monthlyState.reconciliation.latest.months, null, 2) : "Refresh to load comparison data."}</pre>
              </details>
              <details><summary>Unapplied form</summary>
                <pre className="overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(monthlyState.form?.item ?? null, null, 2)}</pre>
              </details>
              <button onClick={monthlyStore.confirmReconciliation}
                disabled={!monthlyState.reconciliation.latest || monthlyState.loading || monthlyState.saving || !fundState.session}>
                [ Comparison confirmed — use latest data and re-edit ]
              </button>
            </>}
            <details><summary>Current draft (copy before refreshing)</summary>
              <pre className="overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(monthlyStore.payload(), null, 2)}</pre>
            </details>
          </section>
        )}
        <fieldset disabled={!fundState.session} className="contents">
        <div className="border-b border-[#cbd5e1] px-4 md:px-12 py-4 sticky top-[73px] z-10 bg-white/80 backdrop-blur-sm">
          <div className="max-w-7xl mx-auto flex flex-wrap gap-6 md:gap-10">
            {activeApp === "funds" ? (
              <>
                <button
                  onClick={() => handleOpenFundForm()}
                  disabled={fundsLocked || !canReplaceFunds}
                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer"
                >
                  [ Add New ]
                </button>
                <button
                  onClick={() => void fetchFunds()}
                  disabled={loadingFunds || savingFunds || !!fundState.pending || !fundState.session}
                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer"
                >
                  [ Refresh ]
                </button>
                <button
                  onClick={() => void handleSaveFundsToCsv()}
                  disabled={fundsLocked || !canReplaceFunds || fundState.conflict || (funds.length === 0 && !fundState.session?.permissions.includes("market-units:clear"))}
                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer disabled:opacity-30"
                >
                  [ {savingFunds ? "Saving" : "Save to Server"} ]
                </button>
                {fundState.pending && (
                  <button onClick={() => void fundStore.retry()} disabled={savingFunds || !fundState.session}
                    className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] disabled:opacity-30">
                    [ Retry Same Request ]
                  </button>
                )}
                {fundState.conflict && (
                  <button onClick={() => void handleCopyDraft()} className="text-[11px] uppercase tracking-[0.15em] text-[#64748b]">
                    [ Copy Draft ]
                  </button>
                )}
              </>
            ) : activeApp === "external" ? (
              <>
                <button
                  onClick={() => handleOpenExternalForm()}
                  disabled={!externalStore.canEdit}
                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer"
                >
                  [ Add New ]
                </button>
                <button
                  onClick={() => void fetchExternalAssets()}
                  disabled={externalState.loading || externalState.saving || !!externalState.pending}
                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer"
                >
                  [ Refresh ]
                </button>
                <button
                  onClick={() => void handleSaveExternalAssets()}
                  disabled={!externalStore.canEdit || externalState.conflict || (externalState.items.length === 0 && !fundState.session?.permissions.includes("external-assets:clear"))}
                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer disabled:opacity-30"
                >
                  [ {savingExternalAssets ? "Saving" : "Save to Server"} ]
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={() => handleOpenBasisForm()}
                  disabled={!basisStore.canEdit}
                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer"
                >
                  [ Add New ]
                </button>
                <button
                  onClick={() => void fetchPortfolioBasis()}
                  disabled={basisState.loading || basisState.saving || !!basisState.pending}
                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer"
                >
                  [ Refresh ]
                </button>
                <button
                  onClick={() => void handleSavePortfolioBasis()}
                  disabled={!basisStore.canEdit || basisState.conflict || (basisState.items.length === 0 && !fundState.session?.permissions.includes("portfolio-basis:clear"))}
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
                  {fundState.conflict && (
                    <details className="text-sm">
                      <summary>Preserved draft — copy before refreshing</summary>
                      <pre className="mt-4 overflow-auto whitespace-pre-wrap">{JSON.stringify(funds.map(({ draft_id: _draftId, ...item }) => item), null, 2)}</pre>
                    </details>
                  )}
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
                            <tr key={row.draft_id} className="hover:bg-[#f8fafc] transition-colors group">
                              <td className="py-6 text-[13px] tracking-[0.05em] font-light text-[#1e293b]">
                                <div className="truncate-guard" title={row.name}>{row.name}</div>
                              </td>
                              <td className="py-6 text-[13px] text-[#64748b] uppercase tracking-[0.1em] font-light pl-4">{row.asset_class}</td>
                              <td className="py-6 text-[13px] text-[#64748b] uppercase tracking-[0.1em] font-light">{row.currency}</td>
                              <td className="py-6 text-[13px] text-right tabular-nums tracking-[-0.02em] font-extralight text-[#1e293b] pr-10">
                                {formatUnits(row.units)}
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
                                  disabled={fundsLocked || !canReplaceFunds}
                                  className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer font-light"
                                >
                                  [ Edit ]
                                </button>
                                <button
                                  onClick={() => handleDeleteFund(idx)}
                                  disabled={fundsLocked || !canReplaceFunds}
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
                      {editingFundId !== null ? "Edit Fund" : "New Fund"}
                    </h3>
                  </header>
                  {formIsStale && (
                    <p role="alert" className="mb-6 text-sm text-amber-800">
                      This form belongs to an older version. Keep a copy of your edits, cancel it, and reopen the current entry before applying changes.
                    </p>
                  )}
                  <form onSubmit={handleSaveFundForm} className="space-y-10">
                    <fieldset disabled={fundsLocked || !canReplaceFunds} className="contents">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-10">
                      <div className="space-y-3">
                        <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Name</label>
                        <input
                          className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent"
                          value={fundFormData.name}
                          onChange={(e) => fundStore.updateForm({ name: e.target.value })}
                          required
                        />
                      </div>
                      <div className="space-y-3">
                        <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Units</label>
                        <input
                          type="text"
                          inputMode="decimal"
                          pattern="(0|[1-9][0-9]{0,17})(\.[0-9]{1,12})?"
                          className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent tabular-nums"
                          value={fundFormData.units}
                          onChange={(e) => fundStore.updateForm({ units: e.target.value })}
                          required
                        />
                      </div>
                      <div className="space-y-3">
                        <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Asset Class</label>
                        <input
                          list="fund-asset-classes"
                          className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent"
                          value={fundFormData.asset_class}
                          onChange={(event) => fundStore.updateForm({ asset_class: event.target.value })}
                          required
                        />
                        <datalist id="fund-asset-classes">
                          {fundAssetClasses.map((assetClass) => <option key={assetClass} value={assetClass} />)}
                        </datalist>
                      </div>
                      <div className="space-y-3">
                        <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Currency</label>
                        <input
                          className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent"
                          value={fundFormData.currency}
                          onChange={(e) => fundStore.updateForm({ currency: e.target.value })}
                          required
                        />
                      </div>
                      <div className="space-y-3">
                        <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Source Symbol</label>
                        <input
                          className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent"
                          value={fundFormData.source_symbol}
                          onChange={(e) => fundStore.updateForm({ source_symbol: e.target.value })}
                        />
                      </div>
                      <div className="space-y-3">
                        <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">CSV URL</label>
                        <input
                          className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent"
                          value={fundFormData.csv_url}
                          onChange={(e) => fundStore.updateForm({ csv_url: e.target.value })}
                        />
                      </div>
                      <div className="space-y-3 md:col-span-2">
                        <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Audit Match Key</label>
                        <input
                          className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent"
                          value={fundFormData.audit_match_key}
                          onChange={(e) => fundStore.updateForm({ audit_match_key: e.target.value })}
                        />
                      </div>
                    </div>
                    <div className="pt-12 flex gap-10">
                      <button
                        type="submit"
                        disabled={formIsStale}
                        className="text-[11px] uppercase tracking-[0.2em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer font-light"
                      >
                        [ Save Entry ]
                      </button>
                      <button
                        type="button"
                        onClick={() => { fundStore.cancelForm(); setFundsView("list"); }}
                        className="text-[11px] uppercase tracking-[0.2em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer font-light"
                      >
                        [ Cancel ]
                      </button>
                    </div>
                    </fieldset>
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
                            {(externalAssets[month]?.items ?? []).map((item) => {
                              const entryId = item.draft_id;
                              return (
                                <tr key={entryId} className="hover:bg-[#f8fafc] transition-colors group">
                                  <td className="py-6 text-[13px] tracking-[0.05em] font-light text-[#1e293b]">{item.name || item.category}</td>
                                  <td className="py-6 text-[13px] text-right tabular-nums tracking-[-0.02em] font-extralight text-[#1e293b] pr-12">
                                    {formatUnits(item.amount)}
                                  </td>
                                  <td className="py-6 text-[13px] text-[#64748b] uppercase tracking-[0.1em] font-light pl-4">{item.category}</td>
                                  <td className="py-6 text-right space-x-6">
                                    <button
                                      onClick={() => handleOpenExternalForm(entryId)}
                                      disabled={!externalStore.canEdit}
                                      className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer font-light"
                                    >
                                      [ Edit ]
                                    </button>
                                    <button
                                      onClick={() => handleDeleteExternal(entryId)}
                                      disabled={!externalStore.canEdit}
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
                  {externalState.form && externalState.form.epoch !== externalState.epoch && <p role="alert">This form belongs to an older version. Copy your edits, cancel, and reopen the current entry.</p>}
                  <div className="space-y-3">
                    <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Month Key</label>
                    <input
                      disabled={!externalStore.canEdit}
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
                      disabled={!externalStore.canEdit}
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
                      disabled={!externalStore.canEdit}
                      type="text" inputMode="decimal"
                      className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent tabular-nums"
                      value={externalFormData.amount}
                      onChange={(e) => setExternalFormData({ ...externalFormData, amount: e.target.value })}
                      required
                    />
                  </div>
                  <div className="space-y-3">
                    <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Name</label>
                    <input
                      disabled={!externalStore.canEdit}
                      className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent"
                      value={externalFormData.name}
                      onChange={(e) => setExternalFormData({ ...externalFormData, name: e.target.value })}
                    />
                  </div>
                  <div className="pt-12 flex gap-10">
                    <button
                      type="submit"
                      disabled={!externalStore.canEdit || externalState.form?.epoch !== externalState.epoch}
                      className="text-[11px] uppercase tracking-[0.2em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer font-light"
                    >
                      [ Save Entry ]
                    </button>
                    <button
                      type="button"
                      disabled={externalState.loading || externalState.saving}
                      onClick={() => { externalStore.cancelForm(); setExternalView("list"); }}
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
                              {formatUnits(portfolioBasis[month].total_acquisition_cost_jpy)}
                            </td>
                            <td className="py-6 text-right space-x-6">
                              <button
                                onClick={() => handleOpenBasisForm(month)}
                                disabled={!basisStore.canEdit}
                                className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer font-light"
                              >
                                [ Edit ]
                              </button>
                              <button
                                onClick={() => handleDeleteBasis(month)}
                                disabled={!basisStore.canEdit}
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
                  {basisState.form && basisState.form.epoch !== basisState.epoch && <p role="alert">This form belongs to an older version. Copy your edits, cancel, and reopen the current entry.</p>}
                  <div className="space-y-3">
                    <label className="text-[11px] uppercase tracking-[0.15em] text-[#64748b] block">Month Key</label>
                    <input
                      disabled={!basisStore.canEdit}
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
                      disabled={!basisStore.canEdit}
                      type="text" inputMode="decimal"
                      className="w-full border-b border-[#cbd5e1] py-2 text-[15px] focus:outline-none focus:border-[#c5a059] transition-colors bg-transparent tabular-nums"
                      value={basisFormData.total_acquisition_cost_jpy}
                      onChange={(e) => setBasisFormData({ ...basisFormData, total_acquisition_cost_jpy: e.target.value })}
                      required
                    />
                  </div>
                  <div className="pt-12 flex gap-10">
                    <button
                      type="submit"
                      disabled={!basisStore.canEdit || basisState.form?.epoch !== basisState.epoch}
                      className="text-[11px] uppercase tracking-[0.2em] text-[#64748b] hover:text-[#1e293b] transition-colors cursor-pointer font-light"
                    >
                      [ Save Entry ]
                    </button>
                    <button
                      type="button"
                      disabled={basisState.loading || basisState.saving}
                      onClick={() => { basisStore.cancelForm(); setBasisView("list"); }}
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
        </fieldset>
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
