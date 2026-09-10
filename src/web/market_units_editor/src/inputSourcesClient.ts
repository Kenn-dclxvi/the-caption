import { ApiError, MarketUnitsStore } from './marketUnitsClient';

export interface SourceTarget { asset_id: string; quantity_unit: string; external_record_ids: string[] }
export interface SourceConfig {
  name: string; subject: string; enabled: boolean; max_age_seconds: number;
  allow_unknown_as_of: boolean; targets: SourceTarget[];
}
export interface InputSource extends SourceConfig {
  id: string; revision: string; manual_override: string[]; last_sequence: number; last_as_of: string | null;
}
export interface ImportBatch {
  id: string; source_id: string; status: 'preview' | 'committed' | 'cancelled'; diff_hash: string;
  diff: { asset_id: string; before: string; after: string; changed: boolean }[];
  request: { source_run_id: string; collected_at: string; as_of: string | null; sequence: number };
  committed_at: string | null; changed: boolean | null;
}
interface Asset { asset_id: string; name: string; asset_class: string; units: string }
interface SourceForm { id: string | null; revision: string | null; config: SourceConfig; resume_ids: string[] }
interface Pending {
  path: string; method: 'POST' | 'PUT'; body: string; key: string;
  kind: 'source' | 'batch'; retryAt: number; expired: boolean;
}
interface State {
  sources: InputSource[]; assets: Asset[]; batches: ImportBatch[]; selected: string | null;
  form: SourceForm | null; pending: Pending | null; busy: boolean; loaded: boolean;
  needsRefresh: boolean; comparisonLoaded: boolean; notice: string | null;
}

export class InputSourcesStore {
  private state: State = { sources: [], assets: [], batches: [], selected: null, form: null,
    pending: null, busy: false, loaded: false, needsRefresh: false, comparisonLoaded: false, notice: null };
  private listeners = new Set<() => void>();
  constructor(private auth: MarketUnitsStore, private uuid = () => crypto.randomUUID()) {}
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private update(patch: Partial<State>) { this.state = { ...this.state, ...patch }; this.listeners.forEach(fn => fn()); }
  has(permission: string) { return !!this.auth.getSnapshot().session?.permissions.includes(permission); }
  get canManage() { return this.has('input-sources:manage'); }
  get canWrite() { return this.canManage && !this.state.busy && !this.state.pending && !this.state.needsRefresh && this.state.loaded; }
  private error(error: unknown) {
    if (error instanceof ApiError && (error.status === 401 || error.code === 'csrf_invalid')) this.auth.requireSignIn();
    return error instanceof Error ? error.message : '操作に失敗しました。';
  }
  initialize = async () => { if (!this.state.loaded && !this.state.busy) await this.refresh(); };
  private async load(selected = this.state.selected) {
    const sources = (await (await this.auth.request('/api/v1/input-sources')).json()).sources as InputSource[];
    const assets = (await (await this.auth.request('/api/v1/market-units')).json()).items as Asset[];
    const id = sources.some(s => s.id === selected) ? selected : sources[0]?.id ?? null;
    const batches = id ? (await (await this.auth.request(`/api/v1/input-sources/${id}/batches`)).json()).batches as ImportBatch[] : [];
    this.update({ sources, assets, batches, selected: id, loaded: true, needsRefresh: false,
      comparisonLoaded: !!this.state.pending?.expired });
  }
  refresh = async () => {
    if (!this.canManage || this.state.busy || (this.state.pending && !this.state.pending.expired)) return;
    this.update({ busy: true, comparisonLoaded: false });
    try {
      await this.load();
      this.update({ notice: this.state.pending?.expired
        ? '保持期限が切れています。元の要求と入力元・履歴を照合してください。自動では再保存しません。'
        : '最新の入力元・履歴を取得しました。編集中のフォームは保持しています。' });
    } catch (error) { this.update({ notice: this.error(error) }); }
    finally { this.update({ busy: false }); }
  };
  select = async (id: string) => {
    if (this.state.busy || this.state.form || (this.state.pending && !this.state.pending.expired) || !this.canManage) return;
    this.update({ busy: true, comparisonLoaded: false });
    try { await this.load(id); } catch (error) { this.update({ notice: this.error(error) }); }
    finally { this.update({ busy: false }); }
  };
  edit = (source?: InputSource) => {
    if (!this.canWrite || this.state.form) return;
    const config: SourceConfig = source ? { name: source.name, subject: source.subject, enabled: source.enabled,
      max_age_seconds: source.max_age_seconds, allow_unknown_as_of: source.allow_unknown_as_of,
      targets: structuredClone(source.targets) } : { name: '', subject: '', enabled: false,
      max_age_seconds: 3600, allow_unknown_as_of: false, targets: [] };
    this.update({ form: { id: source?.id ?? null, revision: source?.revision ?? null, config, resume_ids: [] }, notice: null });
  };
  updateForm = (config: Partial<SourceConfig>, resume_ids?: string[]) => {
    if (!this.canWrite || !this.state.form) return;
    this.update({ form: { ...this.state.form, config: { ...this.state.form.config, ...config },
      resume_ids: resume_ids ?? this.state.form.resume_ids } });
  };
  cancelForm = () => { if (this.canWrite) this.update({ form: null }); };
  saveSource = async () => {
    const form = this.state.form;
    if (!this.canWrite || !form) return;
    if (form.id && this.state.sources.find(s => s.id === form.id)?.revision !== form.revision) {
      this.update({ notice: '設定が更新されています。編集内容を控えてフォームを閉じ、最新の設定から編集し直してください。' }); return;
    }
    const body = form.id ? { base_source_revision: form.revision, config: form.config, resume_ids: form.resume_ids } : form.config;
    await this.sendNew(form.id ? `/api/v1/input-sources/${form.id}` : '/api/v1/input-sources', form.id ? 'PUT' : 'POST', body, 'source');
  };
  actOnBatch = async (batchId: string, action: 'commit' | 'cancel') => {
    if (!this.canWrite || this.state.form || !this.has('imports:commit')) return;
    const batch = this.state.batches.find(b => b.id === batchId);
    if (!batch || batch.status !== 'preview') return;
    await this.sendNew(`/api/v1/import-batches/${batch.id}/${action}`, 'POST', { diff_hash: batch.diff_hash }, 'batch');
  };
  private async sendNew(path: string, method: 'POST' | 'PUT', body: unknown, kind: Pending['kind']) {
    const pending: Pending = { path, method, body: JSON.stringify(body), key: this.uuid(), kind, retryAt: 0, expired: false };
    this.update({ pending, comparisonLoaded: false });
    await this.send(pending);
  }
  retry = async () => {
    const pending = this.state.pending;
    if (!pending || pending.expired || this.state.busy || !this.canManage) return;
    if (pending.retryAt > Date.now()) { this.update({ notice: '指定された待機時間の経過後に再送してください。' }); return; }
    await this.send(pending);
  };
  confirmReconciliation = () => {
    if (!this.state.pending?.expired || !this.state.comparisonLoaded || this.state.busy || !this.canManage) return;
    this.update({ pending: null, form: null, comparisonLoaded: false,
      notice: '照合を確認しました。未送信の編集は破棄しました。必要な変更だけを最新の設定から編集してください。' });
  };
  private async send(pending: Pending) {
    const session = this.auth.getSnapshot().session;
    if (!session) return;
    this.update({ busy: true, notice: null });
    try {
      const result = await (await this.auth.request(pending.path, { method: pending.method, body: pending.body,
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': pending.key, 'X-CSRF-Token': session.csrf_token } })).json();
      this.update({ pending: null, needsRefresh: true, ...(pending.kind === 'source' ? { form: null } : {}) });
      try { await this.load(pending.kind === 'source' ? result.id : this.state.selected); this.update({ notice: '操作が完了しました。最新の状態を表示しています。' }); }
      catch (error) { this.error(error); this.update({ notice: '操作は完了しましたが最新状態を取得できません。再保存せず、最新状態を取得してください。' }); }
    } catch (error) {
      const message = this.error(error);
      if (error instanceof ApiError && error.code === 'idempotency_result_expired') {
        this.update({ pending: { ...pending, expired: true }, comparisonLoaded: false,
          notice: '結果の保持期限が切れています。操作済みの可能性があります。最新の入力元・履歴を取得して照合してください。' });
      } else if (error instanceof ApiError && error.status < 500 && ![401, 403, 408, 429].includes(error.status) && error.code !== 'idempotency_in_progress') {
        this.update({ pending: null, needsRefresh: error.status === 412, notice: message });
      } else {
        this.update({ pending: { ...pending, retryAt: error instanceof ApiError ? error.retryAt : 0 },
          notice: '結果が不明です。元の要求を保持しています。同じ要求を再送して確認してください。' });
      }
    } finally { this.update({ busy: false }); }
  }
}
