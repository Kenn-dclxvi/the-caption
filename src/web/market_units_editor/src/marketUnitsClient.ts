export interface FundFields {
  name: string;
  asset_class: string;
  currency: string;
  units: string;
  source_symbol: string;
  audit_match_key: string;
  csv_url: string;
}

export interface Fund extends FundFields {
  asset_id: string | null;
  draft_id: string;
}

interface MarketUnit extends FundFields {
  asset_id: string;
  asset_key: string;
}

export interface MarketUnitsDocument {
  revision: string;
  storage_state: "ready" | "uninitialized";
  updated_at: string | null;
  items: MarketUnit[];
}

interface Session {
  personal_mode?: boolean;
  authenticated: true;
  csrf_token: string;
  permissions: string[];
}

interface PendingRequest {
  body: string;
  etag: string;
  key: string;
  retryAt: number;
}

export interface FundsState {
  document: MarketUnitsDocument | null;
  items: Fund[];
  etag: string | null;
  form: { item: Fund; targetId: string | null; epoch: number } | null;
  epoch: number;
  dirty: boolean;
  loading: boolean;
  saving: boolean;
  session: Session | null;
  sessionChecked: boolean;
  authenticating: boolean;
  pending: PendingRequest | null;
  conflict: boolean;
  savedRevision: string | null;
  needsRefresh: boolean;
  notice: { tone: "success" | "error" | "info"; text: string } | null;
}

export const EMPTY_FUND: FundFields = {
  name: "", asset_class: "", currency: "", units: "",
  source_symbol: "", audit_match_key: "", csv_url: ""
};

function inputItem(item: FundFields & { asset_id: string | null }) {
  const { asset_id, name, asset_class, currency, units, source_symbol, audit_match_key, csv_url } = item;
  return { asset_id, name, asset_class, currency, units, source_symbol, audit_match_key, csv_url };
}

function draftItems(document: MarketUnitsDocument): Fund[] {
  return document.items.map((item) => ({ ...inputItem(item), draft_id: item.asset_id }));
}

export function formatUnits(value: string): string {
  const [whole, fraction] = value.split(".");
  return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (fraction === undefined ? "" : `.${fraction}`);
}

export class ApiError extends Error {
  constructor(readonly status: number, readonly code: string, detail: string, readonly retryAt = 0) {
    super(detail);
  }
}

export class MarketUnitsStore {
  private state: FundsState = {
    document: null, items: [], etag: null, form: null, epoch: 0, dirty: false,
    loading: true, saving: false, session: null, sessionChecked: false, authenticating: false,
    pending: null, conflict: false, savedRevision: null, needsRefresh: false, notice: null
  };
  private listeners = new Set<() => void>();
  private initialization: Promise<void> | null = null;

  constructor(
    private fetcher: typeof fetch = (...args) => globalThis.fetch(...args),
    private uuid: () => string = () => crypto.randomUUID()
  ) {}

  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  };
  private update(patch: Partial<FundsState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }
  private message(text: string, tone: "success" | "error" | "info" = "error") {
    this.update({ notice: { text, tone } });
  }
  private get canEdit() {
    return !!this.state.session?.permissions.includes("market-units:replace") && !!this.state.etag &&
      !this.state.loading && !this.state.saving && !this.state.pending && !this.state.needsRefresh;
  }

  async request(path: string, init: RequestInit = {}, retrySession = true): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await this.fetcher(path, {
        ...init, credentials: "same-origin", cache: "no-store", signal: controller.signal
      });
      if (!response.ok) {
        const problem = await response.json().catch(() => ({})) as {
          code?: string; detail?: string; errors?: { pointer: string; message: string }[];
        };
        if (retrySession && path !== "/api/session" && this.state.session?.personal_mode &&
            (response.status === 401 || (response.status === 403 && problem.code === "csrf_invalid"))) {
          const renewed = await this.request("/api/session");
          const session = await renewed.json() as Session;
          this.update({ session });
          const headers = new Headers(init.headers);
          if (headers.has("X-CSRF-Token")) headers.set("X-CSRF-Token", session.csrf_token);
          return this.request(path, { ...init, headers }, false);
        }
        const fields = problem.errors?.map((error) => `${error.pointer || "Request"}: ${error.message}`).join("; ");
        const retryAfter = response.headers.get("Retry-After");
        const retryAt = retryAfter
          ? /^\d+$/.test(retryAfter) ? Date.now() + Number(retryAfter) * 1000 : Date.parse(retryAfter)
          : 0;
        throw new ApiError(response.status, problem.code || "request_failed",
          [problem.detail || `Request failed (${response.status}).`, fields].filter(Boolean).join(" "), retryAt);
      }
      // Keep the timeout active until the full response body arrives, including
      // a PUT response whose headers arrived before a connection interruption.
      const body = response.status === 204 ? null : await response.text();
      return new Response(body, { status: response.status, headers: response.headers });
    } finally {
      clearTimeout(timer);
    }
  }

  initialize = () => {
    this.initialization ??= this.startSession();
    return this.initialization;
  };
  requireSignIn = () => {
    if (this.state.session?.personal_mode) {
      void this.request("/api/session")
        .then((response) => response.json())
        .then((session: Session) => {
          this.update({ session });
          this.message("Connection renewed. Your draft is preserved; retry saving.", "info");
        })
        .catch((error) => this.handleReadError(error));
      return;
    }
    this.update({ session: null, sessionChecked: true });
    this.message("Your session has expired. Sign in to continue. Existing drafts remain in this tab.", "info");
  };
  private async startSession() {
    try {
      const response = await this.request("/api/session");
      this.update({ session: await response.json() as Session, sessionChecked: true });
      await this.loadDocument();
    } catch (error) {
      this.handleReadError(error);
    } finally {
      this.update({ sessionChecked: true, loading: false });
    }
  }

  login = async (token: string) => {
    if (this.state.authenticating || this.state.saving) return;
    this.update({ authenticating: true });
    try {
      const response = await this.request("/api/session", {
        method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: "{}"
      });
      this.update({ session: await response.json() as Session, sessionChecked: true });
      if (this.state.pending) {
        this.message("Signed in. Retry the pending request to confirm its result.", "info");
      } else if (this.state.dirty || this.state.form || this.state.conflict) {
        this.message("Signed in. Your draft is preserved. Refresh to compare with the latest saved data before saving.", "info");
      } else {
        await this.loadDocument();
      }
    } catch (error) {
      this.handleReadError(error);
    } finally {
      this.update({ authenticating: false, loading: false });
    }
  };

  private handleReadError(error: unknown) {
    if (error instanceof ApiError && error.status === 401) {
      this.update({ session: null });
      this.message("Sign in to load Market Units. Existing drafts remain in this tab.", "info");
    } else if (error instanceof ApiError && error.code === "authentication_unconfigured") {
      this.message("Authentication is not configured on the server. Configure a THE CAPTION access token on the server, then sign in.");
    } else {
      this.message(error instanceof Error ? error.message : "Unable to load Market Units.");
    }
  }

  private async loadDocument(savedRevision: string | null = null) {
    this.update({ loading: true });
    try {
      const response = await this.request("/api/v1/market-units");
      const etag = response.headers.get("ETag");
      if (!etag || !/^"[^"\r\n]+"$/.test(etag)) throw new Error("The server did not provide a valid ETag. Refresh before editing.");
      const document = await response.json() as MarketUnitsDocument;
      this.update({
        document, items: draftItems(document), etag, epoch: this.state.epoch + 1,
        dirty: false, conflict: false, needsRefresh: false,
        notice: savedRevision ? {
          tone: "success", text: document.revision === savedRevision
            ? `Saved revision ${savedRevision}. Latest data loaded.`
            : `Saved revision ${savedRevision}. Another change is now current (${document.revision}); latest data loaded.`
        } : null
      });
    } finally {
      this.update({ loading: false });
    }
  }

  refresh = async () => {
    if (this.state.saving || this.state.loading || this.state.pending || !this.state.session) return;
    try {
      await this.loadDocument(this.state.needsRefresh ? this.state.savedRevision : null);
    } catch (error) {
      this.handleReadError(error);
      if (this.state.needsRefresh) this.message("Saved successfully, but loading the latest data failed. Refresh to continue; do not save again.");
    }
  };

  openForm = (id?: string) => {
    if (!this.canEdit) return;
    const item = id === undefined
      ? { ...EMPTY_FUND, asset_id: null, draft_id: this.uuid() }
      : this.state.items.find((candidate) => candidate.draft_id === id);
    if (!item) return;
    this.update({ form: { item: { ...item }, targetId: id ?? null, epoch: this.state.epoch }, notice: null });
  };
  updateForm = (patch: Partial<FundFields>) => {
    if (!this.canEdit || !this.state.form) return;
    this.update({ form: { ...this.state.form, item: { ...this.state.form.item, ...patch } } });
  };
  cancelForm = () => {
    if (this.state.saving || this.state.loading) return;
    this.update({ form: null });
  };
  applyForm = () => {
    const form = this.state.form;
    if (!this.canEdit || !form) return;
    if (form.epoch !== this.state.epoch) {
      this.message("This form belongs to an older version. Keep a copy of your edits, cancel it, and reopen the current entry before applying changes.");
      return;
    }
    if (!form.item.name.trim() || !form.item.asset_class.trim() || !form.item.currency.trim() ||
        !/^(0|[1-9][0-9]{0,17})(\.[0-9]{1,12})?$/.test(form.item.units)) {
      this.message("Name, Asset Class and Currency are required. Units must be a non-negative decimal with at most 18 integer and 12 fraction digits.");
      return;
    }
    const items = form.targetId === null ? [...this.state.items, form.item]
      : this.state.items.map((item) => item.draft_id === form.targetId ? form.item : item);
    this.update({ items, form: null, dirty: true, notice: { tone: "info", text: "Entry applied to the draft. Save to Server to persist the list." } });
  };
  deleteItem = (id: string) => {
    if (!this.canEdit) return;
    this.update({ items: this.state.items.filter((item) => item.draft_id !== id), dirty: true });
    this.message("Entry removed from the draft. Save to Server to persist the list.", "info");
  };

  save = async (clearConfirmed = false) => {
    if (!this.canEdit || this.state.conflict || !this.state.etag) return;
    const clearAll = this.state.items.length === 0;
    if (clearAll && (!clearConfirmed || !this.state.session?.permissions.includes("market-units:clear"))) {
      this.message("Saving an empty list requires explicit clear confirmation and market-units:clear permission.");
      return;
    }
    const pending = {
      body: JSON.stringify({ items: this.state.items.map(inputItem), clear_all: clearAll }),
      etag: this.state.etag, key: this.uuid(), retryAt: 0
    };
    this.update({ pending });
    await this.sendPending(pending);
  };

  retry = async () => {
    if (this.state.saving || this.state.loading || !this.state.pending || !this.state.session) return;
    if (this.state.pending.retryAt > Date.now()) {
      this.message("The server is still processing this request. Wait until Retry-After has elapsed, then retry the same request.", "info");
      return;
    }
    await this.sendPending(this.state.pending);
  };

  private async sendPending(pending: PendingRequest) {
    if (!this.state.session) return;
    this.update({ saving: true, notice: null });
    try {
      const response = await this.request("/api/v1/market-units", {
        method: "PUT", headers: {
          "Content-Type": "application/json", "If-Match": pending.etag,
          "Idempotency-Key": pending.key, "X-CSRF-Token": this.state.session.csrf_token
        }, body: pending.body
      });
      const result = await response.json() as { changed: boolean; change_id: string | null; resource: MarketUnitsDocument };
      this.update({
        document: result.resource, items: draftItems(result.resource), etag: null,
        savedRevision: result.resource.revision, pending: null, dirty: false, needsRefresh: true,
        epoch: this.state.epoch + 1
      });
      try {
        await this.loadDocument(result.resource.revision);
      } catch (error) {
        if (error instanceof ApiError && [401, 403].includes(error.status)) this.update({ session: null });
        this.message(`Saved revision ${result.resource.revision}, but loading the latest data failed. Refresh to continue; do not save again.`);
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 412) {
        this.update({ pending: null, conflict: true });
        this.message("Another client changed Market Units. Your draft is preserved. Copy the draft, then Refresh to load the latest data and reapply your changes before saving.");
      } else if (error instanceof ApiError && error.status < 500 &&
          ![401, 403, 408, 429].includes(error.status) &&
          !["idempotency_in_progress", "idempotency_result_expired"].includes(error.code)) {
        this.update({ pending: null });
        this.message(error.message);
      } else {
        if (error instanceof ApiError && [401, 403].includes(error.status)) this.update({ session: null });
        this.update({ pending: { ...pending, retryAt: error instanceof ApiError ? error.retryAt : 0 } });
        this.message(error instanceof ApiError && error.code === "idempotency_result_expired"
          ? "The saved retry result has expired. The draft and original request are preserved; contact the operator to reconcile the result before continuing."
          : `Save result is unconfirmed. The original request is preserved. ${error instanceof ApiError ? error.message + " " : ""}Retry the same request to confirm it.`);
      }
    } finally {
      this.update({ saving: false });
    }
  }
}
