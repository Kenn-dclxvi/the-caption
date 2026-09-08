import { ApiError, MarketUnitsStore } from "./marketUnitsClient";

export type MonthlyResource = "external-assets" | "portfolio-basis";
interface ExternalEntry { entry_id: string | null; category: string; amount: string; name: string }
interface BasisEntry { entry_id: string | null; total_acquisition_cost_jpy: string }
export interface MonthlyDocument {
  revision: string;
  storage_state: "ready" | "uninitialized";
  updated_at: string | null;
  months: Record<string, { items: ExternalEntry[] } | BasisEntry>;
}
export interface MonthlyDraft {
  entry_id: string | null;
  draft_id: string;
  month: string;
  category: string;
  amount: string;
  name: string;
  total_acquisition_cost_jpy: string;
}
const EMPTY: Omit<MonthlyDraft, "draft_id"> = {
  entry_id: null, month: "default", category: "CASH_EXTERNAL", amount: "", name: "", total_acquisition_cost_jpy: ""
};
interface Pending { body: string; etag: string; key: string; retryAt: number }
interface MonthlyState {
  document: MonthlyDocument | null;
  items: MonthlyDraft[];
  emptyMonths: string[];
  form: { item: MonthlyDraft; targetId: string | null; epoch: number } | null;
  epoch: number;
  etag: string | null;
  dirty: boolean;
  loading: boolean;
  saving: boolean;
  conflict: boolean;
  pending: Pending | null;
  needsRefresh: boolean;
  savedRevision: string | null;
  notice: { text: string; tone: "error" | "info" | "success" } | null;
}
export function sortMonthKeys(a: string, b: string) {
  return a === b ? 0 : a === "default" ? 1 : b === "default" ? -1 : b.localeCompare(a);
}

export class MonthlyInputsStore {
  private state: MonthlyState = {
    document: null, items: [], emptyMonths: [], form: null, epoch: 0, etag: null, dirty: false,
    loading: false, saving: false, conflict: false, pending: null, needsRefresh: false, savedRevision: null, notice: null
  };
  private listeners = new Set<() => void>();
  constructor(readonly resource: MonthlyResource, private sessionStore: MarketUnitsStore,
              private uuid: () => string = () => crypto.randomUUID()) {}
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private update(patch: Partial<MonthlyState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }
  private message(text: string, tone: "error" | "info" | "success" = "error") { this.update({ notice: { text, tone } }); }
  get canEdit() {
    return !!this.sessionStore.getSnapshot().session?.permissions.includes(`${this.resource}:replace`) &&
      !!this.state.etag && !this.state.loading && !this.state.saving && !this.state.pending && !this.state.needsRefresh;
  }
  private readError(error: unknown) {
    if (error instanceof ApiError && (error.status === 401 || error.code === "csrf_invalid")) this.sessionStore.requireSignIn();
    this.message(error instanceof Error ? error.message : "Unable to load saved input. Existing drafts are preserved.");
  }
  private adopt(document: MonthlyDocument) {
    const items: MonthlyDraft[] = [];
    const emptyMonths: string[] = [];
    for (const [month, record] of Object.entries(document.months)) {
      const rows = "items" in record ? record.items : [record];
      if (rows.length === 0) emptyMonths.push(month);
      for (const row of rows) items.push({ ...EMPTY, ...row, month, draft_id: row.entry_id! });
    }
    return { document, items, emptyMonths, epoch: this.state.epoch + 1 };
  }
  private async load(savedRevision: string | null = null) {
    this.update({ loading: true });
    try {
      const response = await this.sessionStore.request(`/api/v1/${this.resource}`);
      const etag = response.headers.get("ETag");
      if (!etag || !/^"[^"\r\n]+"$/.test(etag)) throw new Error("A valid ETag is required before editing. Refresh to continue.");
      const document = await response.json() as MonthlyDocument;
      this.update({ ...this.adopt(document), etag, dirty: false, conflict: false, needsRefresh: false,
        notice: savedRevision ? { tone: "success", text: document.revision === savedRevision
          ? "Saved successfully. Latest data loaded." : "Saved successfully. Another client's newer version is now displayed." } : null });
    } finally { this.update({ loading: false }); }
  }
  initialize = async () => {
    if (this.state.document || this.state.dirty || this.state.form || this.state.pending) return;
    await this.refresh();
  };
  refresh = async () => {
    if (this.state.loading || this.state.saving || this.state.pending || !this.sessionStore.getSnapshot().session) return;
    try { await this.load(this.state.needsRefresh ? this.state.savedRevision : null); }
    catch (error) {
      this.readError(error);
      if (this.state.needsRefresh) this.message("Saved successfully, but loading the latest data failed. Refresh to continue; do not save again.");
    }
  };
  openForm = (id?: string) => {
    if (!this.canEdit) return;
    const months = [...this.state.items.map((row) => row.month), ...this.state.emptyMonths].sort(sortMonthKeys);
    const item = id === undefined ? { ...EMPTY, month: months.find((month) => month !== "default") ?? "default", draft_id: this.uuid() }
      : this.state.items.find((row) => row.draft_id === id);
    if (item) this.update({ form: { item: { ...item }, targetId: id ?? null, epoch: this.state.epoch }, notice: null });
  };
  updateForm = (patch: Partial<MonthlyDraft>) => {
    if (this.canEdit && this.state.form) this.update({ form: { ...this.state.form, item: { ...this.state.form.item, ...patch } } });
  };
  cancelForm = () => { if (!this.state.loading && !this.state.saving) this.update({ form: null }); };
  applyForm = () => {
    const form = this.state.form;
    if (!this.canEdit || !form) return;
    if (form.epoch !== this.state.epoch) {
      this.message("This form belongs to an older version. Copy your edits, cancel, and reopen the current entry before applying changes."); return;
    }
    const item = { ...form.item, month: form.item.month.trim(), category: form.item.category.trim(), name: form.item.name.trim() };
    if (item.month !== "default" && !/^(?!0000)[0-9]{4}-(0[1-9]|1[0-2])$/.test(item.month)) {
      this.message("Month must be YYYY-MM (0001–9999, 01–12) or default."); return;
    }
    const amount = this.resource === "external-assets" ? item.amount : item.total_acquisition_cost_jpy;
    if (!/^(0|[1-9][0-9]{0,17})(\.[0-9]{1,12})?$/.test(amount) ||
        (this.resource === "portfolio-basis" && !/[1-9]/.test(amount))) {
      this.message("Use an exact decimal with at most 18 integer and 12 fraction digits. Acquisition cost must be positive."); return;
    }
    if (this.resource === "external-assets" && (!item.category || item.category.length > 256 || item.name.length > 1024 ||
        /[\x00-\x1f\x7f-\x9f]/.test(item.category + item.name))) {
      this.message("Category is required (up to 256 characters); Name may be empty (up to 1024). Control characters are not allowed."); return;
    }
    if (this.resource === "portfolio-basis" && form.targetId === null) {
      const existing = this.state.items.find((row) => row.month === item.month);
      if (existing) { item.entry_id = existing.entry_id; item.draft_id = existing.draft_id; }
    }
    const items = this.state.items.filter((row) => row.draft_id !== form.targetId &&
      (this.resource !== "portfolio-basis" || row.month !== item.month));
    items.push(item);
    this.update({ items, emptyMonths: this.state.emptyMonths.filter((month) => month !== item.month),
      form: null, dirty: true, notice: { tone: "info", text: "Entry applied to the draft. Save to Server to persist changes." } });
  };
  deleteItem = (id: string) => {
    if (!this.canEdit) return;
    this.update({ items: this.state.items.filter((row) => row.draft_id !== id), dirty: true });
    this.message("Entry removed from the draft. Save to Server to persist changes.", "info");
  };
  payload() {
    const months: MonthlyDocument["months"] = {};
    if (this.resource === "external-assets") {
      for (const month of this.state.emptyMonths) months[month] = { items: [] };
      for (const { month, entry_id, category, amount, name } of this.state.items) {
        months[month] ??= { items: [] };
        (months[month] as { items: ExternalEntry[] }).items.push({ entry_id, category, amount, name });
      }
    } else {
      for (const { month, entry_id, total_acquisition_cost_jpy } of this.state.items) months[month] = { entry_id, total_acquisition_cost_jpy };
    }
    return { months, clear_all: this.state.items.length === 0 };
  }
  save = async (clearConfirmed = false) => {
    if (!this.canEdit || this.state.conflict || !this.state.etag) return;
    const payload = this.payload();
    if (payload.clear_all && (!clearConfirmed || !this.sessionStore.getSnapshot().session?.permissions.includes(`${this.resource}:clear`))) {
      this.message("Clearing all entries requires explicit confirmation and clear permission."); return;
    }
    const pending = { body: JSON.stringify(payload), etag: this.state.etag, key: this.uuid(), retryAt: 0 };
    this.update({ pending });
    await this.send(pending);
  };
  retry = async () => {
    if (this.state.loading || this.state.saving || !this.state.pending || !this.sessionStore.getSnapshot().session) return;
    if (this.state.pending.retryAt > Date.now()) { this.message("Wait until Retry-After has elapsed, then retry the same request.", "info"); return; }
    await this.send(this.state.pending);
  };
  private async send(pending: Pending) {
    const session = this.sessionStore.getSnapshot().session;
    if (!session) return;
    this.update({ saving: true, notice: null });
    try {
      const response = await this.sessionStore.request(`/api/v1/${this.resource}`, { method: "PUT", headers: {
        "Content-Type": "application/json", "If-Match": pending.etag, "Idempotency-Key": pending.key, "X-CSRF-Token": session.csrf_token
      }, body: pending.body });
      const result = await response.json() as { resource: MonthlyDocument };
      this.update({ ...this.adopt(result.resource), pending: null, etag: null, dirty: false,
        needsRefresh: true, savedRevision: result.resource.revision });
      try { await this.load(result.resource.revision); }
      catch (error) { this.readError(error); this.message("Saved successfully, but loading the latest data failed. Refresh to continue; do not save again."); }
    } catch (error) {
      if (error instanceof ApiError && error.status === 412) {
        this.update({ pending: null, conflict: true });
        this.message("Another client changed this input. Your draft is preserved. Copy it, then Refresh and reapply changes.");
      } else if (error instanceof ApiError && error.status < 500 && ![401, 403, 408, 429].includes(error.status) &&
          !["idempotency_in_progress", "idempotency_result_expired"].includes(error.code)) {
        this.update({ pending: null }); this.message(error.message);
      } else {
        this.readError(error);
        this.update({ pending: { ...pending, retryAt: error instanceof ApiError ? error.retryAt : 0 } });
        this.message("Save result is unconfirmed. Your draft and original request are preserved. Retry the same request to confirm the result.");
      }
    } finally { this.update({ saving: false }); }
  }
}
