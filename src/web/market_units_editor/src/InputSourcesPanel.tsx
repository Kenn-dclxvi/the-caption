import { useEffect, useSyncExternalStore } from 'react';
import { MarketUnitsStore } from './marketUnitsClient';
import { InputSourcesStore } from './inputSourcesClient';

const button = 'border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-40';
const input = 'block w-full border border-slate-300 p-2 mt-1 bg-white disabled:bg-slate-50';

export function InputSourcesPanel({ store, auth }: { store: InputSourcesStore; auth: MarketUnitsStore }) {
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const session = useSyncExternalStore(auth.subscribe, auth.getSnapshot).session;
  useEffect(() => { if (session && store.canManage) void store.initialize(); }, [session, store]);
  if (!session) return <p className="p-6">入力元の管理にはサインインが必要です。</p>;

  const selected = state.sources.find(s => s.id === state.selected);
  const form = state.form;
  const assetName = (id: string) => state.assets.find(a => a.asset_id === id)?.name ?? id;
  const updateTarget = (index: number, patch: Partial<NonNullable<typeof form>['config']['targets'][number]>) => {
    if (form) store.updateForm({ targets: form.config.targets.map((target, i) => i === index ? { ...target, ...patch } : target) });
  };
  return <section className="max-w-6xl w-full mx-auto p-4 md:p-8 space-y-6">
    <div><h1 className="text-2xl">入力元と取込履歴</h1>
      <p className="text-sm text-slate-600 mt-2">許可した資産の数量だけを自動更新します。取得元の認証情報はこの画面では扱いません。</p></div>
    {!store.canManage && <p>入力元を管理する権限がありません。必要な権限で再認証してください。</p>}
    {state.notice && <p role="status" className="border border-amber-300 bg-amber-50 p-4">{state.notice}</p>}
    <div className="flex flex-wrap gap-3">
      <button className={button} onClick={() => void store.refresh()} disabled={!store.canManage || state.busy || (!!state.pending && !store.needsComparison)}>最新状態を取得</button>
      <button className={button} onClick={() => store.edit()} disabled={!store.canWrite || !!form}>入力元を登録</button>
    </div>
    {state.pending && <section className="border p-4 space-y-3" aria-label="結果の照合">
      <h2>元の要求を保持しています</h2>
      <p>入力元：{state.pending.sourceName}（{state.pending.sourceId ?? '新規登録'}）</p>
      <p>操作：{state.pending.action} ／ バッチ：{state.pending.batchId ?? '対象なし'}</p>
      <button className={button} disabled={state.busy} onClick={() => void store.refreshPermissions()}>現在の権限を再取得</button>
      <button className={button} disabled={state.busy} onClick={store.reauthenticate}>別の資格情報で再認証</button>
      <details><summary>元の要求を確認・コピー</summary><pre className="whitespace-pre-wrap break-all text-xs">{state.pending.body}</pre></details>
      {store.needsComparison ? <>
        <details><summary>最新の入力元設定を比較</summary><pre className="whitespace-pre-wrap break-all text-xs">{JSON.stringify(state.sources, null, 2)}</pre></details>
        <button className={button} disabled={state.busy || (state.pending.kind === 'batch' && !store.has('imports:read'))} onClick={() => void store.compareOriginal()}>元の要求を照合</button>
        {state.originalResult != null && <pre className="whitespace-pre-wrap break-all text-xs" aria-label="元バッチの照合結果">{JSON.stringify(state.originalResult, null, 2)}</pre>}
        <p>操作が完了しているか入力元と履歴で確認してください。残したい編集は控えてから再開してください。</p>
        <button className={button} disabled={state.busy || !state.comparisonLoaded} onClick={() => {
          if (window.confirm('照合済みとして元の要求と未送信の編集を破棄し、最新状態から再開しますか？')) store.confirmReconciliation();
        }}>照合済み・編集を破棄して再開</button>
      </> : <button className={button} disabled={state.busy} onClick={() => void store.retry()}>同じ要求を再送して確認</button>}
    </section>}
    <label className="block">入力元
      <select className={input} value={state.selected ?? ''} disabled={!store.canManage || state.busy || !!form || (!!state.pending && !store.needsComparison)} onChange={e => void store.select(e.target.value)}>
        {!state.sources.length && <option value="">登録なし</option>}
        {state.sources.map(s => <option key={s.id} value={s.id}>{s.name} — {!s.enabled ? '無効' : s.manual_override.length ? '手入力で休止中' : '有効'}</option>)}
      </select>
    </label>
    {selected && !form && <section className="border p-4 space-y-3">
      <h2 className="text-lg">{selected.name}</h2>
      <p>認証主体：{selected.subject} ／ 鮮度上限：{selected.max_age_seconds}秒</p>
      <ul className="list-disc pl-6">{selected.targets.map(t => <li key={t.asset_id}>{assetName(t.asset_id)} ／ {t.quantity_unit} ／ 外部レコード：{t.external_record_ids.join(', ')}
        {selected.manual_override.includes(t.asset_id) && <strong> — 手入力のため休止中</strong>}</li>)}</ul>
      <button className={button} disabled={!store.canWrite} onClick={() => store.edit(selected)}>設定を編集・休止を解除</button>
    </section>}
    {form && <form className="border p-4 space-y-4" onSubmit={e => { e.preventDefault(); void store.saveSource(); }}>
      <h2 className="text-lg">{form.id ? '入力元を編集' : '入力元を登録'}</h2>
      <fieldset disabled={!store.canWrite} className="space-y-4">
        <label className="block">入力元名<input className={input} required maxLength={256} value={form.config.name} onChange={e => store.updateForm({ name: e.target.value })}/></label>
        <label className="block">専用tokenの認証主体（subject）<input className={input} required maxLength={256} value={form.config.subject} onChange={e => store.updateForm({ subject: e.target.value })}/></label>
        <label className="block">鮮度上限（秒）<input className={input} type="number" min={1} max={2592000} step={1} required value={form.config.max_age_seconds} onChange={e => store.updateForm({ max_age_seconds: Number(e.target.value) })}/></label>
        <label className="block"><input type="checkbox" checked={form.config.enabled} onChange={e => store.updateForm({ enabled: e.target.checked })}/> この入力元を有効にする</label>
        <label className="block"><input type="checkbox" checked={form.config.allow_unknown_as_of} onChange={e => store.updateForm({ allow_unknown_as_of: e.target.checked })}/> 入力元の基準時点が不明な取得を許可する</label>
        <p className="text-sm">基準時点不明を許可しても、鮮度と取得順の検証は行います。</p>
        <h3>管理対象</h3>
        {form.config.targets.map((target, index) => <fieldset key={index} className="border p-3 space-y-3">
          <legend>対象 {index + 1}</legend>
          <label className="block">資産<select className={input} required value={target.asset_id} onChange={e => updateTarget(index, { asset_id: e.target.value })}>
            <option value="">選択してください</option>
            {!state.assets.some(a => a.asset_id === target.asset_id && a.asset_class !== 'FX') && target.asset_id && <option value={target.asset_id}>削除済み・対象外：{target.asset_id}</option>}
            {state.assets.filter(a => a.asset_class !== 'FX').map(a => <option key={a.asset_id} value={a.asset_id}>{a.name}（{a.asset_id.slice(0, 8)}）</option>)}
          </select></label>
          <label className="block">確認済みの数量単位<input className={input} required maxLength={64} value={target.quantity_unit} onChange={e => updateTarget(index, { quantity_unit: e.target.value })}/></label>
          <label className="block">合算対象の外部レコードID（1行1件）<textarea className={input} required rows={3} value={target.external_record_ids.join('\n')} onChange={e => updateTarget(index, { external_record_ids: e.target.value.split('\n') })}/></label>
          <button type="button" className={button} onClick={() => store.updateForm({ targets: form.config.targets.filter((_, i) => i !== index) })}>この対象を外す</button>
        </fieldset>)}
        <button type="button" className={button} onClick={() => store.updateForm({ targets: [...form.config.targets, { asset_id: '', quantity_unit: '', external_record_ids: [] }] })}>対象を追加</button>
        {form.id && selected?.manual_override.length ? <fieldset className="border border-amber-300 p-3"><legend>休止解除の確認</legend>
          <p>手入力の内容と管理範囲を確認した対象だけ選択してください。保存後も新しいpreviewが必要です。</p>
          {selected.manual_override.map(id => <label className="block" key={id}><input type="checkbox" checked={form.resume_ids.includes(id)} onChange={e => store.updateForm({}, e.target.checked ? [...form.resume_ids, id] : form.resume_ids.filter(v => v !== id))}/>{assetName(id)}の自動更新を再開する</label>)}
        </fieldset> : null}
        <div className="flex gap-3"><button className={button} type="submit" disabled={!form.config.targets.length}>設定を保存</button>
          <button className={button} type="button" onClick={store.cancelForm}>編集を破棄</button></div>
      </fieldset>
    </form>}
    <section className="space-y-4" aria-label="取込履歴"><h2 className="text-xl">取込履歴・反映前の確認</h2>
      {!state.batches.length && <p>取込バッチはありません。取込クライアントがpreviewを作成すると表示されます。</p>}
      {[...state.batches].reverse().map(batch => <article className="border p-4 space-y-3" key={batch.id}>
        <h3>{batch.request.source_run_id} — {batch.status === 'preview' ? '未反映' : batch.status === 'cancelled' ? '取消済み' : batch.changed ? '反映済み' : '確認済み・変更なし'}</h3>
        <p className="text-sm">取得：{batch.request.collected_at} ／ 基準時点：{batch.request.as_of ?? '不明'}{batch.committed_at && ` ／ 反映：${batch.committed_at}`}</p>
        <div className="overflow-auto"><table className="w-full text-sm text-left"><thead><tr><th>資産</th><th>変更前</th><th>変更後</th></tr></thead><tbody>
          {batch.diff.map(d => <tr key={d.asset_id}><td className="py-2">{assetName(d.asset_id)}</td><td>{d.before}</td><td>{d.after}{!d.changed && '（変更なし）'}</td></tr>)}
        </tbody></table></div>
        {batch.status === 'preview' && <div className="flex gap-3">
          <button className={button} disabled={!store.canWrite || !!form || !store.has('imports:commit')} onClick={() => {
            if (window.confirm('表示された変更予定の数量を反映しますか？反映直前に競合と権限を再確認します。')) void store.actOnBatch(batch.id, 'commit');
          }}>変更予定を反映</button>
          <button className={button} disabled={!store.canWrite || !!form || !store.has('imports:commit')} onClick={() => {
            if (window.confirm('この未反映バッチを取り消しますか？数量は変更しません。')) void store.actOnBatch(batch.id, 'cancel');
          }}>バッチを取消</button>
        </div>}
      </article>)}
    </section>
  </section>;
}
